"""Annotate a fixed sample of judgments on the faillissementspauliana.

It prompts an LLM whether the court rules on the three art. 42 Fw requirements:

    onverplicht              — verplichte vs. onverplichte rechtshandeling
    benadeling_schuldeisers  — zijn de schuldeisers benadeeld
    wetenschap               — wetenschap van benadeling (art. 42/43/45 Fw)

For each requirement the model returns a boolean plus a verbatim citation of the
sentence it bases the judgment on (empty when the requirement is not ruled on).
Results are written one JSON line per judgment, and optionally back to the
judgment table (--write-db).

By default the entire corpus is annotated; pass --eclis to restrict to a
specific set.

    python -m rag.annotate --output out.jsonl [--eclis ECLI ...] [--model ...]
        [--write-db] [--dsn ...]

The chat provider is chosen from the model-name prefix (mistral* -> Scaleway,
gpt* -> OpenAI).

Environment (read from the .env in the machina-pauliana root):
    SCALEWAY_API_KEY  — API key for Scaleway (mistral* models)
    OPENAI_API_KEY    — API key for OpenAI (gpt* models)
    DATABASE_URL      — Postgres DSN for the RAG store
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pydantic import BaseModel, Field

from .db.connection import connect

# Load the .env from the machina-pauliana root (one level up from this file).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# prefix -> (base_url, api_key_env): the OpenAI-compatible chat endpoint each
# model is routed to by the start of its name.
PROVIDERS: dict[str, tuple[str, str]] = {
    "mistral": ("https://api.scaleway.ai/v1", "SCALEWAY_API_KEY"),
    "gpt": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}

# Default model
MODEL = "mistral/mistral-medium-3.5-128b:fp8"

LLM_PARAMS = {
    "temperature": 0.1,  # 0 risks loops with structured output per Scaleway docs
    "top_p": 0.2,
    "seed": 42,
    "max_tokens": 1500,
}

# Try to keep within rate limits of the API
REQUEST_DELAY = 2
RETRY_DELAYS = [10, 30, 60]


# Structured output schema


class Oordeel(BaseModel):
    waarde: bool = Field(
        description=(
            "true als de rechter inhoudelijk over dit vereiste oordeelt, "
            "anders false."
        )
    )
    citaat: str = Field(
        default="",
        description=(
            "Letterlijke kopie van de zin in de uitspraak waarop het oordeel "
            "berust. Leeg als waarde false is."
        ),
    )


class PaulianaAnnotatie(BaseModel):
    onverplicht: Oordeel = Field(
        description="Oordeel over verplichte vs. onverplichte rechtshandeling."
    )
    benadeling_schuldeisers: Oordeel = Field(
        description="Oordeel over benadeling van de schuldeisers."
    )
    wetenschap: Oordeel = Field(
        description="Oordeel over het wetenschapsvereiste (art. 42/43/45 Fw)."
    )


# Prompts

SYSTEM_PROMPT_TEMPLATE = """Je bent expert in het lezen van Nederlandse rechterlijke uitspraken. De onderstaande uitspraak is van {court}. Beoordeel, voor zover het de faillissementspauliana van art. 42 Faillissementswet (Fw) betreft, of {court} inhoudelijk oordeelt over elk van de volgende drie vereisten:

- onverplicht: of de rechtshandeling verplicht of onverplicht is;
- benadeling_schuldeisers: of de schuldeisers zijn benadeeld;
- wetenschap: of de schuldenaar en/of de wederpartij wist of behoorde te weten dat benadeling van de schuldeisers het gevolg zou zijn (het wetenschapsvereiste).

Afbakening: beoordeel alleen oordelen over de faillissementspauliana van art. 42 Fw (inclusief de bewijsvermoedens van art. 43 en 45 Fw). Daarbij geldt:
- Het oordeel of de rechtshandeling verplicht dan wel onverplicht is — ook de keuze tussen art. 42 en art. 47 Fw — telt als onverplicht: true, óók als {court} haar verplicht acht en de zaak vervolgens onder art. 47 Fw beoordeelt.
- Benadeling en wetenschap die uitsluitend onder een andere grondslag dan art. 42 Fw worden beoordeeld — bijvoorbeeld art. 47 Fw of de BW-pauliana (art. 3:45/3:46 BW) — tellen niet en zijn dan false.
- Bij meerdere aangevochten rechtshandelingen geldt dit per rechtshandeling: wordt voor één daarvan wél een art. 42 Fw-vereiste beoordeeld, dan is dat vereiste true.

Onverplicht: een rechtshandeling is onverplicht wanneer de schuldenaar haar verricht zonder dat een uit de wet of een overeenkomst voortvloeiende rechtsplicht hem daartoe verplichtte. Dat blijft zo wanneer de schuldenaar feitelijk nauwelijks anders kon dan de aangevochten handeling verrichten. De stelplicht en de bewijslast dat de rechtshandeling onverplicht was, rusten op de curator.

Benadeling van de schuldeisers: de benadeling moet aanwezig zijn op het moment waarop de curator zich op de pauliana beroept (leer van de middellijke benadeling). Of er benadeling is, wordt bepaald door de hypothetische situatie waarin de schuldeisers zonder de gewraakte rechtshandeling zouden hebben verkeerd te vergelijken met de situatie waarin zij feitelijk verkeren wanneer die handeling in stand blijft.

Wetenschap: dit kan gaan over de wetenschap van benadeling (bij een rechtshandeling om niet alleen die van de schuldenaar, anders die van zowel de schuldenaar als de wederpartij), al dan niet door de curator aangetoond in de zin van art. 42 Fw. Het kan ook gaan over de beoordeling van het bewijsvermoeden van art. 43 Fw (rechtshandeling binnen een jaar voor het faillissement én een van de drie categorieën: tegen een onderwaarde, voldoening of zekerheidstelling van een niet-opeisbare schuld, of een gelieerde wederpartij) of van art. 45 Fw (rechtshandeling binnen een jaar voor het faillissement). Het bewijsvermoeden kan met succes worden ingeroepen of juist worden ontzenuwd (weerlegd). Beoordeelt {court} een van deze gevallen, dan is wetenschap true.

BELANGRIJK — alleen een eigen oordeel van {court} telt:
- true: {court} beoordeelt het vereiste inhoudelijk en neemt zelf een standpunt in (acht het vervuld of niet, verwerpt of aanvaardt een verweer, past het bewijsvermoeden toe of ontzenuwt het). Het citaat is de zin waarin {court} dat oordeel uitspreekt, niet de stelling van een partij.
- false: het vereiste is niet in geschil, onbetwist of erkend ("tussen partijen is niet in geschil dat ...", "staat vast dat ..."); of het is enkel een stelling van een partij ("de curator stelt dat ...", "appellant betoogt dat ..."); of het staat alleen vast door een oordeel elders (lagere instantie of tussenuitspraak) dat {court} zonder eigen motivering overneemt, bijvoorbeeld omdat er geen grief tegen is gericht; of {court} komt er niet aan toe.

Geef het antwoord in JSON: voor elk vereiste een boolean en, als die true is, een letterlijke kopie van de zin waarin {court} het oordeel uitspreekt. Anders is de waarde false en blijft het citaat leeg."""

USER_PROMPT_TEMPLATE = """Beoordeel de onderstaande uitspraak op de drie vereisten van de faillissementspauliana (art. 42 Fw). Geef per vereiste een boolean en een letterlijk citaat van de zin waarop je oordeel berust.

Uitspraak:

{judgment_md}"""

# Court enum to its name mapping
COURT_LABELS = {
    "rechtbank": "de rechtbank",
    "gerechtshof": "het gerechtshof",
    "hoge_raad": "de Hoge Raad",
}


# Loading judgments


def all_eclis(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT ecli FROM judgment")
        return [row[0] for row in cur.fetchall()]


def judgment_markdown(conn, eclis: list[str]) -> dict[str, str]:
    """Reconstruct each judgment's text for the prompt, joined by a blank line.

    To focus the model on the reasoning, this only returns grounds of decision:
    every section from the first 'overwegingen' section to the last one
    (inclusive), so any geschil/feiten that happens to sit between two
    overwegingen sections is kept. Judgments without any 'overwegingen' section
    (ie bad segmentation) fall back to the full document."""
    sections: dict[str, list[tuple[str, str]]] = {ecli: [] for ecli in eclis}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ecli, label, markdown FROM section "
            "WHERE ecli = ANY(%s) ORDER BY ecli, position",
            (eclis,),
        )
        for ecli, label, markdown in cur.fetchall():
            sections[ecli].append((label, markdown))

    docs: dict[str, str] = {}
    for ecli, parts in sections.items():
        labels = [label for label, _ in parts]
        if "overwegingen" in labels:
            first = labels.index("overwegingen")
            last = len(labels) - 1 - labels[::-1].index("overwegingen")
            parts = parts[first : last + 1]
        docs[ecli] = "\n\n".join(md for _, md in parts)
    return docs


def judgment_courts(conn, eclis: list[str]) -> dict[str, str]:
    """The court enum per ECLI ({ecli: 'rechtbank' | 'gerechtshof' |
    'hoge_raad'}), used to tailor the prompt."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ecli, court FROM judgment WHERE ecli = ANY(%s)", (eclis,)
        )
        return {ecli: court for ecli, court in cur.fetchall()}


def write_labels(conn, ecli: str, result: dict) -> None:
    """Persist the three boolean verdicts onto the judgment row (overwrites)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE judgment SET onverplicht = %s, benadeling_schuldeisers = %s, "
            "wetenschap = %s WHERE ecli = %s",
            (
                result["onverplicht"]["waarde"],
                result["benadeling_schuldeisers"]["waarde"],
                result["wetenschap"]["waarde"],
                ecli,
            ),
        )


# LLM call


def _provider_for(model: str) -> tuple[str, str]:
    """The (base_url, api_key_env) whose prefix matches `model`, else error."""
    for prefix, provider in PROVIDERS.items():
        if model.lower().startswith(prefix):
            return provider
    raise ValueError(
        f"Unknown model {model!r}: its name must start with one of "
        f"{', '.join(PROVIDERS)}."
    )


def client_for(model: str) -> OpenAI:
    """An OpenAI client pointed at the provider that serves `model`."""
    base_url, key_env = _provider_for(model)
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(
            f"{key_env} is not set; add it to the .env in the "
            f"machina-pauliana root directory (needed for model {model!r})."
        )
    return OpenAI(base_url=base_url, api_key=api_key)


def params_for(model: str) -> dict:
    """Sampling params for `model`. OpenAI gpt-* (reasoning) models reject
    temperature/top_p and replaced max_tokens with max_completion_tokens."""
    if model.lower().startswith("gpt"):
        return {
            "seed": LLM_PARAMS["seed"],
            "max_completion_tokens": LLM_PARAMS["max_tokens"],
        }
    return LLM_PARAMS


def call_llm(judgment_md: str, court: str, model: str) -> dict:
    """Annotate one judgment using structured output with `model`. The system
    prompt is tailored to `court`. Retries on 429 with backoff. Returns a plain
    dict."""
    client = client_for(model)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(court=COURT_LABELS[court])
    for attempt, wait in enumerate([0] + RETRY_DELAYS):
        if wait:
            print(
                f"  [429] Rate limited — wachten {wait}s (poging {attempt + 1})"
            )
            time.sleep(wait)

        try:
            response = client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(
                            judgment_md=judgment_md
                        ),
                    },
                ],
                response_format=PaulianaAnnotatie,
                **params_for(model),
            )
            return response.choices[0].message.parsed.model_dump()

        except RateLimitError:
            if attempt == len(RETRY_DELAYS):
                raise
            continue

    raise RuntimeError("Max retries exceeded")


def _empty_result(error: str | None = None) -> dict:
    """A blank annotation (all requirements false) carrying an error message."""
    blank = {"waarde": False, "citaat": ""}
    result = {
        "onverplicht": dict(blank),
        "benadeling_schuldeisers": dict(blank),
        "wetenschap": dict(blank),
    }
    if error:
        result["error"] = error
    return result


def annotate_judgment(
    ecli: str, judgment_md: str, court: str, model: str
) -> dict:
    """Annotate one judgment, falling back to an empty result on failure."""
    try:
        result = call_llm(judgment_md, court, model)
    except Exception as e:  # noqa: BLE001 — record and continue the batch
        result = _empty_result(error=str(e))
    return {"ecli": ecli, "court": court, **result}


# CLI

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Annotate judgments on the faillissementspauliana "
        "(art. 42 Fw): the entire corpus, or a given --eclis set."
    )
    ap.add_argument(
        "--eclis",
        nargs="+",
        metavar="ECLI",
        help="Annotate exactly these ECLIs. Default is the entire corpus. "
        "Unknown ECLIs are skipped with a warning.",
    )
    ap.add_argument(
        "--model",
        default=MODEL,
        help=f"Model id (default: {MODEL}). The provider is chosen from the "
        "name prefix: mistral* -> Scaleway (SCALEWAY_API_KEY), gpt* -> OpenAI "
        "(OPENAI_API_KEY)",
    )
    ap.add_argument(
        "--output",
        required=True,
        help="Output JSONL file (required).",
    )
    ap.add_argument(
        "--write-db",
        action="store_true",
        help="Also write the three booleans to the judgment table.",
    )
    ap.add_argument("--dsn", help="Postgres DSN (else DATABASE_URL).")
    args = ap.parse_args(argv)

    with connect(args.dsn) as conn:
        corpus = all_eclis(conn)
        if not corpus:
            sys.exit(
                "No judgments in the RAG store, run `python -m rag.ingest`."
            )
        if args.eclis:
            corpus_set = set(corpus)
            missing = [e for e in args.eclis if e not in corpus_set]
            if missing:
                print(
                    f"warning: not in corpus, skipping: {missing}",
                    file=sys.stderr,
                )
            chosen = [e for e in args.eclis if e in corpus_set]
            if not chosen:
                sys.exit("None of the given --eclis are in the RAG store.")
            selection = f"{len(chosen)} (explicit --eclis)"
        else:
            chosen = sorted(corpus)
            selection = f"{len(chosen)} (entire corpus)"
        docs = judgment_markdown(conn, chosen)
        courts = judgment_courts(conn, chosen)

    print(f"Corpus:    {len(corpus)} judgments")
    print(f"Selection: {selection}")
    print(f"Model:     {args.model}")
    print(f"Write DB:  {args.write_db}")
    print(f"Output:    {args.output}")

    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Separate connection kept open for per-judgment label writes
    db = connect(args.dsn) if args.write_db else None
    try:
        with output_file.open("w", encoding="utf-8") as out:
            for i, ecli in enumerate(chosen, 1):
                print(f"[{i}/{len(chosen)}] {ecli}")
                result = annotate_judgment(
                    ecli, docs[ecli], courts[ecli], args.model
                )
                out.write(json.dumps(result, ensure_ascii=False) + "\n")
                out.flush()
                if db is not None and "error" not in result:
                    write_labels(db, ecli, result)
                    db.commit()
                if i < len(chosen):
                    time.sleep(REQUEST_DELAY)
    finally:
        if db is not None:
            db.close()

    print(f"Done, output: {args.output}")


if __name__ == "__main__":
    main()
