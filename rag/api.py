"""Public API for the RAG system.

A single import surface (`rag.api`) for everything callers need:
    embed_texts / embed_text  — embed documents (sections), no instruction
    embed_query               — embed a query, with the Qwen3 instruct prefix
    retrieve                  — top-k judgments for a query vector (+ relations)
    to_markdown               — flatten retrieve results into one context string

Embedding lives here so the section embeddings stored at ingest time (see
rag.ingest.embed) and the query embedding share one model/dimension/vector
space. The retrieval implementation lives in focused submodules (retrieval.search,
retrieval.similarity, retrieval.graph); this module re-exports it so callers
never import them directly.

Environment (read from the .env in the machina-pauliana root):
    SCALEWAY_API_KEY  — API key for Scaleway (embeddings use their inference)
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from tqdm import tqdm

# Load the .env from the machina-pauliana root (one level up from this file).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Embeddings always run on Scaleway for Qwen3 embedding model
API_KEY = os.environ.get("SCALEWAY_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "SCALEWAY_API_KEY is not set. Add it to the .env in the "
        "machina-pauliana root directory."
    )

CLIENT = OpenAI(base_url="https://api.scaleway.ai/v1", api_key=API_KEY)

# Embedding model and output size. Qwen3-Embedding-8B is natively 4096-dim
# Scaleway returns Matryoshka-truncated vectors for 2000.
# 2000 stays within pgvector's HNSW index limit
EMBEDDING_MODEL = "qwen3-embedding-8b"
EMBEDDING_DIMENSIONS = 2000

# Retry on 429 with backoff (same approach as the annotate script)
RETRY_DELAYS = [30, 60, 90]


@dataclass
class EmbeddingBatch:
    """The result of one embeddings request: the vectors, plus the two numbers a
    batch caller needs to work with itself, what this request cost
    (prompt_tokens) and how much of the per-minute token budget is left
    (remaining_tokens, None when the header is absent)."""

    vectors: list[list[float]]
    prompt_tokens: int
    remaining_tokens: int | None


def embed_texts(texts: list[str]) -> EmbeddingBatch:
    """Embed several texts in one request, one vector per input in the same
    order. The embeddings endpoint accepts an array of inputs, so this is a
    multi-input call (not to be confused with async Batch API).
    Retries on 429 with backoff.

    `with_raw_response` is the OpenAI SDK's accessor for the underlying HTTP
    response, so we can read the x-ratelimit-* headers alongside the parsed
    body."""
    for attempt, wait in enumerate([0] + RETRY_DELAYS):
        if wait:
            # tqdm.write so the message doesn't break a progress bar elsewhere
            tqdm.write(
                f"  [429] rate limited — waiting {wait}s (attempt {attempt + 1})"
            )
            time.sleep(wait)
        try:
            raw = CLIENT.embeddings.with_raw_response.create(
                model=EMBEDDING_MODEL,
                input=texts,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            response = raw.parse()
            remaining = raw.headers.get("x-ratelimit-remaining-tokens")
            return EmbeddingBatch(
                # Sort by `index` to be safe regardless of output order
                vectors=[
                    d.embedding
                    for d in sorted(response.data, key=lambda d: d.index)
                ],
                prompt_tokens=response.usage.prompt_tokens,
                remaining_tokens=int(remaining)
                if remaining is not None
                else None,
            )
        except RateLimitError:
            if attempt == len(RETRY_DELAYS):
                raise
            continue

    raise RuntimeError("Max retries exceeded")


def embed_text(text: str) -> list[float]:
    """Embed one text into an EMBEDDING_DIMENSIONS-long vector. Documents
    (sections) use this. A query must use `embed_query` for the instruct prefix.
    Both land in the same vector space."""
    return embed_texts([text]).vectors[0]


# Qwen3-Embedding query instruction. The model card recommends wrapping the
# query (and not the documents, therefore assymetric) as
# "Instruct: {task}\nQuery:{query}"
# One instruction is shared across the three art. 42 Fw subroutines, so a query
# is embedded once and the vector reused for all three.
QUERY_INSTRUCTION = (
    "Given a legal question about the Dutch faillissementspauliana "
    "(art. 42 Fw), retrieve relevant passages from court judgments."
)


def embed_query(
    query: str, instruction: str = QUERY_INSTRUCTION
) -> list[float]:
    """Embed a query with the Qwen3 instruct prefix (documents need none)."""
    return embed_text(f"Instruct: {instruction}\nQuery:{query}")


# Retrieval implementation lives in rag.retrieval.search
# Re-exported here so `rag.api` is the one public surface.
# Imported at the bottom, after the embedding helpers,
# and retrieval does not import api back, so there is no import cycle.
from .retrieval.search import retrieve, to_markdown  # noqa: E402,F401
