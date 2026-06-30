"""Shared LLM infrastructure for the neuro-symbolic model.

The neuro-symbolic model resolves the inputs using multiple LLM routines:
a coroutine that resolves the factual inputs without case law, and three RAG
subroutines that apply case-based reasoning.

This module is the general/API layer. It routes a model name to the right
OpenAI-compatible provider (base URL + API key) by its prefix and runs the
structured-output call.
The case is embedded once (:func:`embed_casus`) and that one vector
is reused across the three subroutines — what ``rag.api`` is built for.

The provider is chosen from the model-name prefix:

    gemini*   -> Google Gemini (GEMINI_API_KEY)
    mistral*  -> Scaleway      (SCALEWAY_API_KEY)
    gpt*      -> OpenAI        (OPENAI_API_KEY)

Add the matching keys to the .env file in this repos root.
"""

import asyncio
import os
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel

from rag import api as rag_api
from rag.db.connection import connect

# Load the .env from the machina-pauliana root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# prefix -> (base_url, api_key_env)
PROVIDERS: dict[str, tuple[str, str]] = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
    ),
    "mistral": ("https://api.scaleway.ai/v1", "SCALEWAY_API_KEY"),
    "gpt": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}

# Default model: Mistral on Scaleway
DEFAULT_MODEL = "mistral/mistral-medium-3.5-128b:fp8"

# Default RAG top-k. Carried through the API for the subroutines
DEFAULT_K = 5

LLM_PARAMS = {
    "temperature": 0.1,
    "top_p": 0.2,
    "seed": 42,
    "max_tokens": 10000,
}

# Retry budget for 429
RETRY_DELAYS = [10, 30, 60]

T = TypeVar("T", bound=BaseModel)


def _provider_for(model: str) -> tuple[str, str]:
    """The (base_url, api_key_env) whose prefix matches `model`, else error."""
    for prefix, provider in PROVIDERS.items():
        if model.lower().startswith(prefix):
            return provider
    raise ValueError(
        f"Unknown model {model!r}: its name must start with one of "
        f"{', '.join(PROVIDERS)}."
    )


def client_for(model: str) -> AsyncOpenAI:
    """An async OpenAI client pointed at the provider that serves `model`.
    Created per call and used as an async context manager."""
    base_url, key_env = _provider_for(model)
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(
            f"{key_env} is not set. Add it to the .env in the "
            f"machina-pauliana root directory (needed for model {model!r})."
        )
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def params_for(model: str) -> dict:
    """Sampling params for `model`. The reasoning backends (gemini*, gpt*) run
    at medium reasoning effort. OpenAI gpt-* models additionally reject
    temperature/top_p and rename max_tokens to max_completion_tokens., etc"""
    m = model.lower()
    if m.startswith("gpt"):
        return {
            "seed": LLM_PARAMS["seed"],
            "max_completion_tokens": LLM_PARAMS["max_tokens"],
            "reasoning_effort": "medium",
        }
    if m.startswith("gemini"):
        return {
            "temperature": LLM_PARAMS["temperature"],
            "top_p": LLM_PARAMS["top_p"],
            "max_tokens": LLM_PARAMS["max_tokens"],
            "reasoning_effort": "medium",
        }
    return LLM_PARAMS


async def complete(
    model: str,
    system_prompt: str,
    user_content: str,
    response_format: type[T],
) -> T:
    """Run one structured-output completion and return the parsed Pydantic
    object. Awaitable, so several can run concurrently and retries on 429.."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    async with client_for(model) as client:
        for attempt, wait in enumerate([0] + RETRY_DELAYS):
            if wait:
                print(
                    f"  [429] Rate limited — waiting {wait}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(wait)
            try:
                response = await client.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    response_format=response_format,
                    **params_for(model),
                )
                return response.choices[0].message.parsed
            except RateLimitError:
                if attempt == len(RETRY_DELAYS):
                    raise
                continue
    raise RuntimeError("Max retries exceeded")


# Markdown header above the RAG intro and the retrieved judgments
RAG_HEADER = "# Mogelijk relevante uitspraken"

# Prompt shared across the RAG subroutines: introduces the retrieved judgments
RAG_INTRO = """De onderstaande uitspraken zijn mogelijk relevant voor het bepalen van de variabele(n) en de bijbehorende overwegingen. Je kunt er in de overwegingen naar verwijzen met het ECLI-nummer. De uitspraken staan in chronologische volgorde: sommige zijn opgevolgd door een latere uitspraak die erna staat. Dat kan een tussenvonnis gevolgd door een eindvonnis van de rechtbank zijn, een hoger beroep van het gerechtshof tegen een uitspraak van de rechtbank, of een cassatie-arrest van de Hoge Raad na het hof. Worden eerdere overwegingen in een hogere instantie verworpen, ga dan uit van de overwegingen van de hogere instantie."""


def embed_casus(casus: str) -> list[float]:
    """Embed the case facts once into the shared query vector (Qwen3 instruct
    prefix). `rag.api` uses one query instruction across the three art. 42 Fw
    subroutines by design, so the same vector serves every label."""
    return rag_api.embed_query(casus)


async def embed_casus_async(casus: str) -> list[float]:
    """Awaitable wrapper around :func:`embed_casus` (the embedding HTTP call in
    `rag.api` is synchronous), run in a worker thread to keep the loop free."""
    return await asyncio.to_thread(embed_casus, casus)


def retrieve_examples(query_vec: list[float], *, label: str, k: int) -> str:
    """Top-k example judgments for `label`, rendered as one Markdown context
    string (chronologically ordered per relation chain).

    `query_vec` is the shared case embedding from :func:`embed_casus`; `label` is
    one of the art. 42 Fw requirement columns (onverplicht,
    benadeling_schuldeisers, wetenschap)."""
    with connect() as conn:
        hits = rag_api.retrieve(conn, query_vec, label=label, k=k)
    return rag_api.to_markdown(hits)


async def subroutine_rag(
    casus: str, query_vec: list[float] | None, *, label: str, k: int
) -> str:
    """The RAG context for one subroutine: top-k judgments for `label` as one
    Markdown string. Empty when k < 1.

    Uses the orchestrator's precomputed `query_vec` when given — embedded once
    and reused across the three labels — and falls back to embedding `casus`
    itself when called standalone with no vector. The blocking DB retrieval is
    run in a worker thread to keep the loop free."""
    if k < 1:
        return ""
    if query_vec is None:
        query_vec = await embed_casus_async(casus)
    return await asyncio.to_thread(
        retrieve_examples, query_vec, label=label, k=k
    )


def subroutine_prompt(casus: str, rag_markdown: str = "") -> str:
    """The subroutine user prompt: the case facts, then (when present) a header,
    the RAG intro, and the retrieved example judgments."""
    parts = [f"# Casus\n\n{casus}"]
    if rag_markdown.strip():
        parts += [RAG_HEADER, RAG_INTRO, rag_markdown]
    return "\n\n".join(parts)
