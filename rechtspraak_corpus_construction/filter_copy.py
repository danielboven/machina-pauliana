#!/usr/bin/env python3
"""Script that copies Rechtspraak XML files filtered, ie that reference art.
42/43/45 Fw, into a new folder.

Walks an input directory (e.g. xml_output/RBAMS/2012/ECLI_NL_xyz.xml), matches
each file against the article regexes, and copies matches into the output
directory while preserving the subfolder structure.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

# Match (case-insensitive): art / art. / artt. / artikel, up to 30 chars, the
# article number, up to 30 chars, then Fw / Faillissementswet.
PREFIX = r"(?:artt?\.?|artikel)\b"
GAP = r"[\s\S]{0,30}?"
SUFFIX = r"(?:Fw|Faillissementswet)\b"
ARTICLES = [42, 43, 45]

PATTERNS = [
    re.compile(
        PREFIX + GAP + r"\b" + str(nr) + r"\b" + GAP + SUFFIX, re.IGNORECASE
    )
    for nr in ARTICLES
]


def matches(text: str) -> bool:
    """Match function for all Regexes outlined above."""
    return any(p.search(text) for p in PATTERNS)


def copy_matches(input_dir: Path, output_dir: Path) -> None:
    """Main copy function, takes entire xml directory as input and the new
    output xml directory. Goes through all xml files in the directories.
    Note that it only includes RB, GH and HR, other courts are excluded."""
    xml_files = sorted(
        p
        for p in input_dir.rglob("*.xml")
        # only Rechtbank (RB), Gerechtshof (GH) and Hoge Raad (HR), exclude PHR
        if p.relative_to(input_dir).parts[0].startswith(("RB", "GH", "HR"))
    )
    if not xml_files:
        sys.exit(f"No XML files found under '{input_dir}'.")

    copied = 0
    progress = tqdm(xml_files, unit="file", desc="Scanning")
    for src in progress:
        if not matches(src.read_text(encoding="utf-8", errors="ignore")):
            continue
        dst = output_dir / src.relative_to(input_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
        progress.set_postfix(copied=copied)

    print(f"Copied {copied}/{len(xml_files)} files to '{output_dir}'.")


def main() -> None:
    """Main function taking the input (root) directory and the output
    (destination) directory to copy to."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_dir", type=Path, help="Root directory to scan")
    p.add_argument("output_dir", type=Path, help="Destination root for matches")
    args = p.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"Input directory '{args.input_dir}' does not exist.")
    copy_matches(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
