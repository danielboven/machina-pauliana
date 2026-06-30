"""Write a manual-validation dataset from the RAG store.

Samples `n` judgments at random from the database and writes one Markdown file
per judgment into a flat output directory. Each file reconstructs the ingested
sections in document order, so a reviewer can manually:

  - segmentation: the labelled sections, in order, as stored in the DB
  - the pre-retrieval annotation (`onverplicht`, `wetenschap`,
    `benadeling_schuldeisers`). Put in as template, but left blank in output
    here so reviewer can manually fill these in.

Each section is identified by a `<!-- @label -->` marker
Run from the repo root:

    python -m evaluation.build_validation_dataset -n 25 [-o DIR] [--dsn ...]
"""

import argparse
import os
import random
import sys

from rag.annotate import all_eclis
from rag.db.connection import connect

# the three pre-retrieval labels, put in but blank for reviewer
ANNOTATION_FIELDS = ("onverplicht", "wetenschap", "benadeling_schuldeisers")


def fetch_sections(conn, ecli: str) -> list[tuple[str, str]]:
    """The judgment's sections as (label, markdown), in document order."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT label, markdown FROM section "
            "WHERE ecli = %s ORDER BY position",
            (ecli,),
        )
        return cur.fetchall()


def render_document(ecli: str, sections: list[tuple[str, str]]) -> str:
    """The full Markdown file: preamble/frontmatter, then each section preceded
    by the `<!-- @label -->` marker, with no blank line between sections."""
    fields = "".join(f"{name}: \n" for name in ANNOTATION_FIELDS)
    frontmatter = f"---\necli: {ecli}\n{fields}---\n"
    blocks = [f"<!-- @{label} -->\n{md}" for label, md in sections]
    return frontmatter + "\n".join(blocks) + "\n"


def filename(ecli: str) -> str:
    """ECLI:NL:RBAMS:2020:1234 -> ECLI_NL_RBAMS_2020_1234.md (flat filename)."""
    return ecli.replace(":", "_") + ".md"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-n",
        "--count",
        type=int,
        required=True,
        help="Number of judgments to sample.",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="evaluation/output",
        help="Output directory (flat). Default: evaluation/output",
    )
    ap.add_argument("--dsn", help="Postgres DSN (else DATABASE_URL).")
    args = ap.parse_args(argv)

    with connect(args.dsn) as conn:
        eclis = all_eclis(conn)
        if args.count > len(eclis):
            sys.exit(
                f"Asked for {args.count} judgments but the database holds "
                f"only {len(eclis)}."
            )
        sample = random.sample(eclis, args.count)

        os.makedirs(args.output, exist_ok=True)
        for ecli in sample:
            sections = fetch_sections(conn, ecli)
            path = os.path.join(args.output, filename(ecli))
            with open(path, "w", encoding="utf-8") as f:
                f.write(render_document(ecli, sections))

    print(f"wrote {len(sample)} files to {args.output}")


if __name__ == "__main__":
    main()
