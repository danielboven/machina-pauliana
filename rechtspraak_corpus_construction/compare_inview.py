#!/usr/bin/env python3
"""This program helps to list the cases (files) not present in the data folder,
but that are present in a CSV file from Wolters Kluwer Inview (formerly known
as Navigator).

You can go to the "Uitspraken" tab for the specific article (ie Art. 42 Fw) on
Inview and use the Instant Data Scraper Chrome Extension to get the visible
table as CSV. Please note that this text and datamining from Inview is allowed
here within the context of scientific research under Art. 15n of The Dutch
Copyright Act (Auteurswet).
The program prints how many ECLIs from Inview are not present in the corpus.
"""

import argparse
import csv
import re
from pathlib import Path

from lxml import etree

# Ie ECLI:NL:HR:2001:AD4499 (the DOC at the end of ECLI are ignored)
ECLI_RE = re.compile(r"ECLI:[A-Z]{2}:[A-Za-z0-9.]+:\d{4}:[A-Za-z0-9.]+")


def corpus_eclis(matches_dir: Path) -> set[str]:
    """Retrieve ECLI from every XML from the <dcterms:identifier>."""
    found = set()
    for xml in matches_dir.rglob("*.xml"):
        try:
            root = etree.parse(str(xml)).getroot()
        except etree.XMLSyntaxError:
            continue
        for el in root.iter():
            if el.tag.split("}")[-1] == "identifier" and (
                el.text or ""
            ).startswith("ECLI:"):
                found.add(el.text.strip())
                break
    return found


def csv_eclis(csv_path: Path) -> set[str]:
    """First ECLI found in each CSV row (the column position is disregarded
    here)."""
    found = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            for cell in row:
                if m := ECLI_RE.search(cell):
                    found.add(m.group())
                    break
    return found


def ecli_to_path(root: Path, ecli: str) -> Path:
    """This tries to find the XML file path like rechtspraak_fetcher.build_path,
    structure is <root>/<court>/<year>/<ECLI-with-underscores>.xml."""
    parts = ecli.split(":")
    return root / parts[2] / parts[3] / (ecli.replace(":", "_") + ".xml")


def main() -> None:
    """Main CLI program, accepts CSV from Inview first, then the filtered corpus
    then optionally the full corpus.
    When the full corpus is set, files not present in the local corpus will
    also be tested against the full corpus (ie all civil law decisions)."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", type=Path, help="inview CSV export")
    p.add_argument(
        "matches_dir", type=Path, help="corpus folder (xml_output_matches)"
    )
    p.add_argument(
        "full_corpus",
        type=Path,
        nargs="?",
        default=None,
        help="optional: full unfiltered civil corpus, to check whether "
        "each missing ECLI was fetched at all",
    )
    args = p.parse_args()

    have = corpus_eclis(args.matches_dir)
    want = csv_eclis(args.csv)
    missing = sorted(want - have)

    print(
        f"inview ECLIs: {len(want)}  |  in corpus: {len(have)}  |  "
        f"missing from corpus: {len(missing)}"
    )

    if args.full_corpus is None:
        for ecli in missing:
            print(ecli)
        return

    # Annotate each missing ECLI with whether its file exists in the full corpus
    fetched = 0
    for ecli in missing:
        present = ecli_to_path(args.full_corpus, ecli).is_file()
        fetched += present
        print(f"{ecli}\t{'in full corpus' if present else 'NOT fetched'}")
    print(
        f"\nof the {len(missing)} missing: {fetched} present in full corpus, "
        f"{len(missing) - fetched} not fetched"
    )


if __name__ == "__main__":
    main()
