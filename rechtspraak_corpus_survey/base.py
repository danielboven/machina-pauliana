"""Rechtspraak corpus survey shared pipeline

Identifies the structural sections of Dutch rechterlijke uitspraken using an
OpenAI-compatible API (eg. Scaleway Generative APIs).

This module holds everything that is identical across courts: the API/model
settings, the structured-output schema, the XML extraction, the LLM call and
the running the batch. The court-specific material, such as system prompt,
user prompt and few-shot examples, live in a seperate `Profile` and are selected
at the command line via `--court` argument.

Theoretical basis: art. 230 Rv:
  procesverloop  — art. 230b
  geschil        — art. 230c
  feiten         — art. 230e (only when structurally separate)
  overwegingen   — art. 230e (juridische beoordeling)
  beslissing     — art. 230f
  overig         — sections outside the standard structure

Each section type is a list to support multiple occurrences of the same type
within one document (e.g. "De beoordeling in conventie", "De beoordeling in
reconventie").

Primary references:
  Törnberg (2024), Best Practices for Text Annotation with LLMs.
  Ahsmann (2020), De weg naar het civiele vonnis.

Environment (required, read from the .env in the machina-pauliana root):
    OPENAI_API_KEY  — API key (Scaleway or any OpenAI-compatible key)
"""

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pydantic import BaseModel, Field

# Load the .env from the machina-pauliana root (two levels up from this file).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not set; add it to the .env in the "
        "machina-pauliana root directory."
    )

# API / model settings
CLIENT = OpenAI(
    base_url="https://api.scaleway.ai/v1",
    api_key=API_KEY,
)
MODEL = "mistral-small-3.2-24b-instruct-2506"

LLM_PARAMS = {
    "temperature": 0.1, # 0 risks loops with structured output per Scaleway docs
    "top_p": 0.2,
    "seed": 42,
    "max_tokens": 1200, # increased to handle multiple sections per type
}

# Try to keep within rate limits of API
REQUEST_DELAY = 2
RETRY_DELAYS = [10, 30, 60]


# ---------------------------------------------------------------------------
# Structured output schema (shared across courts)
#
# Each section type is a list[str] so that multiple occurrences within one
# document are captured (e.g. "Overwegingen in conventie" AND "Overwegingen in
# reconventie"). An empty list means the section is absent.
# ---------------------------------------------------------------------------


class OverigSectie(BaseModel):
    label: str = Field(
        description=(
            "Korte beschrijving van het type sectie, bijv. 'wrakingsverzoek'."
        )
    )
    begin: str = Field(
        description=(
            "Openingstag inclusief volledige <title>-inhoud, max 120 tekens."
        ),
    )


class Annotatie(BaseModel):
    # N.B. no `ecli` field: the ECLI is set deterministically from the XML
    # metadata (see extract_ecli), never by the LLM.
    procesverloop: list[str] = Field(
        default_factory=list,
        description=(
            "Lijst van openingstags voor alle procesverloop-secties. "
            "Leeg als afwezig."
        ),
    )
    feiten: list[str] = Field(
        default_factory=list,
        description=(
            "Lijst van openingstags voor alle feiten-secties (alleen aparte "
            "secties met eigen titel). Leeg als afwezig."
        ),
    )
    geschil: list[str] = Field(
        default_factory=list,
        description=(
            "Lijst van openingstags voor alle geschil-/vordering-secties "
            "(in hoger beroep ook de grieven). Leeg als afwezig."
        ),
    )
    overwegingen: list[str] = Field(
        default_factory=list,
        description=(
            "Lijst van openingstags voor alle beoordeling-/overweging-secties, "
            "inclusief 'in conventie', 'in reconventie', enz. Leeg als afwezig."
        ),
    )
    beslissing: list[str] = Field(
        default_factory=list,
        description=(
            "Lijst van openingstags voor alle beslissing-/dictum-secties. "
            "Leeg als afwezig."
        ),
    )

    # Catch-all for non-standard sections
    overig: list[OverigSectie] = Field(
        default_factory=list,
        description=(
            "Secties die expliciet niet tot de vijf standaardtypen behoren, "
            "bijv. wrakingsverzoek. Leeg als afwezig."
        ),
    )


# ---------------------------------------------------------------------------
# Profile: the court-specific bundle
#
# Everything that differs between a rechtbankvonnis and a gerechtshofarrest is
# the prompting. A Profile is a frozen bundle of the two prompts; the matching
# pipeline below is identical across courts. Concrete courts are instances
# (see rechtbank.py / gerechtshof.py), not subclasses.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    name: str
    system_prompt: str
    # Must contain a single "{xml_content}" placeholder.
    user_prompt_template: str


# ---------------------------------------------------------------------------
# XML extraction
# ---------------------------------------------------------------------------


NS = "http://www.rechtspraak.nl/schema/rechtspraak-1.0"
DCTERMS = "http://purl.org/dc/terms/"


def extract_uitspraak(xml_path: Path) -> str:
    """Return only the <uitspraak> element, stripping RDF metadata.
    Falls back to full file text if parsing fails."""
    ET.register_namespace("", NS)
    try:
        root = ET.parse(xml_path).getroot()
        uitspraak = root.find(f"{{{NS}}}uitspraak")
        if uitspraak is not None:
            return ET.tostring(uitspraak, encoding="unicode")
    except ET.ParseError:
        pass
    return xml_path.read_text(encoding="utf-8")


def extract_ecli(xml_path: Path) -> str | None:
    """Return the ECLI from the XML metadata, deterministically (never from the
    LLM). Reads the bare <dcterms:identifier> in the RDF block; falls back to
    the <uitspraak> id attribute, then to the filename stem."""
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return _ecli_from_name(xml_path)

    for ident in root.iter(f"{{{DCTERMS}}}identifier"):
        text = (ident.text or "").strip()
        if text.startswith("ECLI:"):
            return text

    uitspraak = root.find(f"{{{NS}}}uitspraak")
    if uitspraak is not None:
        doc_id = uitspraak.get("id", "")
        if doc_id.startswith("ECLI:"):
            return doc_id.removesuffix(":DOC")

    return _ecli_from_name(xml_path)


def _ecli_from_name(xml_path: Path) -> str | None:
    """Reconstruct the ECLI from a filename like ECLI_NL_HR_1992_ZC0615.xml."""
    stem = xml_path.stem
    return stem.replace("_", ":") if stem.startswith("ECLI") else None


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def call_llm(xml_content: str, profile: Profile) -> dict:
    """Send one document to the API using structured output (Pydantic schema).
    Uses the prompts from `profile`. Retries on 429 with backoff. Returns a
    plain dict."""

    for attempt, wait in enumerate([0] + RETRY_DELAYS):
        if wait:
            print(
                f"  [429] Rate limited — wachten {wait}s (poging {attempt + 1})"
            )
            time.sleep(wait)

        try:
            response = CLIENT.beta.chat.completions.parse(
                model=MODEL,
                messages=[
                    {"role": "system", "content": profile.system_prompt},
                    {
                        "role": "user",
                        "content": profile.user_prompt_template.format(
                            xml_content=xml_content
                        ),
                    },
                ],
                response_format=Annotatie,
                **LLM_PARAMS,
            )
            return response.choices[0].message.parsed.model_dump()

        except RateLimitError:
            if attempt == len(RETRY_DELAYS):
                raise
            continue

    raise RuntimeError("Max retries exceeded")


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------


def _empty_result(identifier: str, error: str | None = None) -> dict:
    """Return a blank result dict with empty lists for all section types."""
    result = {
        "ecli": identifier,
        "procesverloop": [],
        "feiten": [],
        "geschil": [],
        "overwegingen": [],
        "beslissing": [],
        "overig": [],
    }
    if error:
        result["error"] = error
    return result


def process_file(xml_path: Path, profile: Profile) -> dict:
    """Annotate one XML file tagging the result with its ECLI and source
    filename. The ECLI is taken deterministically from the XML metadata, not
    from the LLM. Falls back to an empty result carrying the error message on
    failure."""
    xml_content = extract_uitspraak(xml_path)
    ecli = extract_ecli(xml_path)
    try:
        result = call_llm(xml_content, profile)
    except Exception as e:
        result = _empty_result(ecli, error=str(e))
    return {"ecli": ecli, **result, "source_file": xml_path.name}


def in_court(path: Path, root: Path, prefix: str) -> bool:
    """Checks whether `path` belongs to a court whose folder starts with
    `prefix` (N.B. folder layout COURT/YEAR/ECLI.xml, e.g. GHAMS/... for GH).
    Returns True when the file sits directly in `root` (no court folder)."""
    rel = path.relative_to(root)
    return rel.parts[0].startswith(prefix) if len(rel.parts) > 1 else True


def run(
    input_dir: str, output_path: str, profile: Profile, court: str | None = None
) -> None:
    """Process every XML file under `input_dir`, writing one JSON line per
    document to `output_path` and waiting between requests to respect limits.
    When court is given, only files under matching court folders (GH*) are
    processed."""
    root = Path(input_dir)
    xml_files = sorted(root.glob("**/*.xml"))
    if court:
        xml_files = [f for f in xml_files if in_court(f, root, court)]
    if not xml_files:
        print(f"Geen XML-bestanden gevonden in: {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Court:     {profile.name}")
    print(f"Bestanden: {len(xml_files)}")
    print(f"Model:     {MODEL}")
    print(f"Output:    {output_path}")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as out:
        for i, xml_path in enumerate(xml_files, 1):
            print(f"[{i}/{len(xml_files)}] {xml_path.name}")
            result = process_file(xml_path, profile)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            if i < len(xml_files):
                time.sleep(REQUEST_DELAY)

    print(f"Klaar. Output: {output_path}")
