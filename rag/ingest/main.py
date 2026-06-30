"""Populate the RAG store from rechtspraak XML.

Runs over XML files directory, segments each judgment with the existing
pipeline, merges consecutive sections with the same label, and writes a
`judgment` row plus its ordered `section` rows. Relations and embeddings are
filled in later passes (not here). Labels per judgment are NULL.

Inserts plainly, one file at a time. To re-ingest, rebuild first with
`python -m rag.db.init_db --drop`.

    python -m rag.ingest <xml-file-or-dir> [--dsn ...]
"""

import argparse
import sys
from pathlib import Path

from lxml import etree
from tqdm import tqdm

from rechtspraak_segmentation import UnknownCourtError
from rechtspraak_segmentation.interface.render import render_doc

from ..db.connection import connect
from .relations import add_relations

DC_NS = "http://purl.org/dc/terms/"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"

# the 6 labels/types, anything else (such as preamble opening section)
# is stored as "overig"
CANON_LABELS = {
    "procesverloop",
    "feiten",
    "geschil",
    "overwegingen",
    "beslissing",
    "overig",
}


def merge_runs(items: list[list]) -> list[list]:
    """Fold adjacent sections that share a label into one section, joining their
    markdown with a blank line. `items` is a list of [label, markdown]."""
    out: list[list] = []
    for label, md in items:
        if out and out[-1][0] == label:
            out[-1][1] = f"{out[-1][1]}\n\n{md}"
        else:
            out.append([label, md])
    return out


def judgment_date(root) -> str | None:
    """The Uitspraakdatum (decision date, ISO yyyy-mm-dd) from the metadata's
    <dcterms:date rdfs:label="Uitspraakdatum">. None if absent."""
    for el in root.iterfind(f".//{{{DC_NS}}}date"):
        if el.get(f"{{{RDFS_NS}}}label") == "Uitspraakdatum" and el.text:
            return el.text.strip()
    return None


def build_sections(xml_bytes: bytes):
    """Segment one judgment, or None if it has no renderable section content."""
    rd = render_doc(xml_bytes)
    meta = rd.meta

    items: list[list] = []
    for sec in rd.sections:
        label = sec.label if sec.label in CANON_LABELS else "overig"
        body = (sec.body_md or "").strip()
        if body:  # drop empty sections
            items.append([label, body])
    if not items:
        return None

    if rd.footnotes_md:  # GitHub-style footnote list as a final overig section
        items.append(["overig", rd.footnotes_md])

    # folds the footnotes into a final overig, if there is any
    merged = merge_runs(
        items
    )

    date = judgment_date(etree.fromstring(xml_bytes))
    return meta["ecli"], meta["court"], meta["strategy"], date, merged


def insert_judgment(
    cur, ecli: str, court, strategy: str, date: str | None
) -> None:
    cur.execute(
        "INSERT INTO judgment (ecli, court, strategy, judgment_date) "
        "VALUES (%s, %s, %s, %s)",
        (ecli, court, strategy, date),
    )


def insert_sections(cur, ecli: str, merged: list[list]) -> None:
    cur.executemany(
        "INSERT INTO section (ecli, position, label, markdown) "
        "VALUES (%s, %s, %s, %s)",
        [(ecli, i, label, md) for i, (label, md) in enumerate(merged)],
    )


def iter_xml(source: Path):
    """The XML file, or every `*.xml` under the directory (sorted)."""
    if source.is_file():
        yield source
    else:
        yield from sorted(source.rglob("*.xml"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Ingest judgments into the RAG store."
    )
    ap.add_argument("source", type=Path, help="XML file or directory.")
    ap.add_argument("--dsn", help="Postgres DSN (else DATABASE_URL).")
    args = ap.parse_args(argv)

    files = list(iter_xml(args.source))
    ingested = skipped = 0
    with connect(args.dsn) as conn:
        # pass 1: judgments  and sections
        for path in tqdm(files, desc="ingest", unit="doc"):
            try:
                result = build_sections(path.read_bytes())
                if result is None:
                    skipped += 1
                    continue
                ecli, court, strategy, date, merged = result
                with conn.cursor() as cur:
                    insert_judgment(cur, ecli, court, strategy, date)
                    insert_sections(cur, ecli, merged)
                conn.commit()
                ingested += 1
            except (UnknownCourtError, etree.XMLSyntaxError, ValueError) as exc:
                conn.rollback()
                skipped += 1
                print(f"skip {path.name}: {exc}", file=sys.stderr)

        # pass 2: relations between judgements (procedural chain)
        relations = add_relations(conn, files)

    print(
        f"ingested {ingested} judgments, skipped {skipped}, "
        f"{relations} relations"
    )


if __name__ == "__main__":
    main()
