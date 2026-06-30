"""Score the segmentation against the hand-annotated gold standard.

Reads the Markdown files written by `evaluation.build_validation_dataset` (after
a reviewer has corrected the `<!-- @label -->` sections) and compares each
file's sections against the sections stored for that ECLI in the database.

Each judgment becomes a *set* of `(label, content)` spans on both sides. A span
matches only when its label and its content are identical (content is boundary-
stripped but not otherwise normalised), so a section the reviewer split or
relabelled counts as both a false positive and a false negative:

    TP = gold & pred      FP = pred - gold      FN = gold - pred

The pooled spans are fed to scikit-learn's `classification_report`, giving a
per-label precision/recall/F1 table with micro/macro/weighted averages. Run from
the repo root:

    python -m evaluation.evaluate_validation_dataset DIR [--dsn ...]
"""

import argparse
import glob
import os
import re

import yaml
from sklearn.metrics import classification_report

from evaluation.build_validation_dataset import fetch_sections
from rag.db.connection import connect

MARKER = re.compile(r"<!--\s*@(\w+)\s*-->")
# stand-in "label" for a span that has no counterpart on the other side
NONE = "∅"


def parse_gold(text: str) -> tuple[str, set[tuple[str, str]]]:
    """A gold file's ECLI and its `(label, content)` spans.

    Content runs from one `<!-- @label -->` marker to the next (or EOF) and is
    boundary-stripped to drop the newlines the marker layout introduces."""
    _, frontmatter, body = text.split("---", 2)
    ecli = yaml.safe_load(frontmatter)["ecli"]

    markers = list(MARKER.finditer(body))
    spans = set()
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(body)
        spans.add((m.group(1), body[m.end():end].strip()))
    return ecli, spans


def db_spans(conn, ecli: str) -> set[tuple[str, str]]:
    """The `(label, content)` spans stored for `ecli`, boundary-stripped."""
    return {(label, md.strip()) for label, md in fetch_sections(conn, ecli)}


def samples(gold: set, pred: set) -> tuple[list[str], list[str]]:
    """Turn one judgment's gold/pred span sets into aligned `(y_true, y_pred)`
    rows: a true positive is a (label, label) row; a false positive is
    (NONE, label); a false negative is (label, NONE)."""
    y_true, y_pred = [], []
    for label, _ in gold & pred:
        y_true.append(label); y_pred.append(label)
    for label, _ in pred - gold:
        y_true.append(NONE); y_pred.append(label)
    for label, _ in gold - pred:
        y_true.append(label); y_pred.append(NONE)
    return y_true, y_pred


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="Directory of annotated gold-standard .md files.")
    ap.add_argument("--dsn", help="Postgres DSN (else DATABASE_URL).")
    args = ap.parse_args(argv)

    paths = sorted(glob.glob(os.path.join(args.input, "*.md")))
    if not paths:
        raise SystemExit(f"No .md files in {args.input}")

    y_true, y_pred = [], []
    with connect(args.dsn) as conn:
        for path in paths:
            with open(path, encoding="utf-8") as f:
                ecli, gold = parse_gold(f.read())
            yt, yp = samples(gold, db_spans(conn, ecli))
            y_true += yt; y_pred += yp

    labels = sorted({label for label in y_true + y_pred if label != NONE})
    print(f"Scored {len(paths)} judgments, {len(y_true)} spans.\n")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))


if __name__ == "__main__":
    main()
