"""Command-line program: argument parsing and dispatch.

Selects a court Profile via --court (RB / GH / HR) and hands it to the shared
batch runner in base.py.

Usage:
    python -m rechtspraak_corpus_survey --court RB --input_dir ./xml_files
      --output ./report.jsonl
"""

import argparse

from . import COURT_CHOICES, get_profile, run


def main():
    parser = argparse.ArgumentParser(
        description="LLM corpus survey voor rechtspraak XML-structuurannotatie"
    )
    parser.add_argument(
        "--court",
        type=str.upper,
        choices=COURT_CHOICES,
        required=True,
        help="Welk gerecht (RB=rechtbank, GH=gerechtshof, HR=Hoge Raad).",
    )
    parser.add_argument(
        "--input_dir", required=True, help="Map met XML-bestanden"
    )
    parser.add_argument(
        "--output", default="report.jsonl", help="Uitvoerbestand (JSONL)"
    )
    args = parser.parse_args()

    profile = get_profile(args.court)
    run(args.input_dir, args.output, profile, court=args.court)


if __name__ == "__main__":
    main()
