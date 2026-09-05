"""Score the Pauliana annotation against the hand-annotated gold standard.

Each gold Markdown file (template written by `evaluation.
build_validation_dataset`) contains the three labels/criteria as booleans:

    onverplicht, wetenschap, benadeling_schuldeisers

`True` means the court rules on the property/requirement (positive class).
The reviewer's values are the gold standard. The model's predictions are read
from a JSONL file (one record per ECLI) matched to the gold files by ECLI.

Each requirement is scored as its own binary classifier. The three are pooled
into a multilabel `classification_report` (per-requirement precision/recall/F1
plus averages). One aggregated confusion matrix over all requirements pooled
together is written to PDF. Run from the repo root:

    python -m evaluation.evaluate_rechtspraak_annotation DIR MODEL.jsonl [-o PDF]

Pass -s/--svg to also write an SVG next to the PDF (same stem, .svg
extension).
"""

import argparse
import glob
import json
import os

import matplotlib
import numpy as np
import yaml
from sklearn.metrics import ConfusionMatrixDisplay, classification_report

matplotlib.use("Agg")  # render straight to PDF without display

LABELS = ("onverplicht", "wetenschap", "benadeling_schuldeisers")


def gold_labels(text: str) -> tuple[str, list[bool]]:
    """A gold file's ECLI and the three booleans, in LABELS order."""
    meta = yaml.safe_load(text.split("---", 2)[1])
    return meta["ecli"], [bool(meta[label]) for label in LABELS]


def model_predictions(path: str) -> dict[str, list[bool]]:
    """ECLI -> the model's three requirement booleans, in LABELS order."""
    preds = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                preds[rec["ecli"]] = [
                    bool(rec[label]["waarde"]) for label in LABELS
                ]
    return preds


def save_confusion(
    y_true: np.ndarray, y_pred: np.ndarray, paths: list[str]
) -> None:
    """One aggregated 2x2 confusion matrix over all requirements pooled.
    Fonts are scaled 1.5x for legibility in print. Written once per path in
    `paths`, format inferred from each extension."""
    with matplotlib.rc_context(
        {"font.size": 1.4 * matplotlib.rcParamsDefault["font.size"]}
    ):
        disp = ConfusionMatrixDisplay.from_predictions(
            y_true.ravel(),
            y_pred.ravel(),
            labels=[False, True],
            display_labels=["False", "True"],
            cmap="Blues",
        )
        disp.ax_.set_ylabel("Actual label")
        for path in paths:
            disp.figure_.savefig(path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "input", help="Directory of annotated gold-standard .md files."
    )
    ap.add_argument(
        "model", help="Model predictions as JSONL (one record per ECLI)."
    )
    ap.add_argument(
        "-o",
        "--output",
        default="evaluation/output/annotation_confusion.pdf",
        help="PDF path for the confusion matrix.",
    )
    ap.add_argument(
        "-s",
        "--svg",
        action="store_true",
        help="Also write an SVG next to the PDF output (same stem).",
    )
    args = ap.parse_args(argv)

    preds = model_predictions(args.model)
    paths = sorted(glob.glob(os.path.join(args.input, "*.md")))
    if not paths:
        raise SystemExit(f"No .md files in {args.input}")

    y_true, y_pred, missing = [], [], []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            ecli, gold = gold_labels(f.read())
        if ecli not in preds:
            missing.append(ecli)
            continue
        y_true.append(gold)
        y_pred.append(preds[ecli])

    if missing:
        print(
            f"warning: {len(missing)} gold ECLIs absent from the model file, "
            f"skipped.\n"
        )
    if not y_true:
        raise SystemExit("No gold ECLIs matched the model file.")
    y_true, y_pred = np.array(y_true), np.array(y_pred)

    print(
        f"Scored {len(y_true)} judgments on {len(LABELS)} requirements "
        f"(positive class = True).\n"
    )
    print(
        classification_report(
            y_true, y_pred, target_names=LABELS, zero_division=0
        )
    )

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    out_paths = [args.output]
    if args.svg:
        out_paths.append(os.path.splitext(args.output)[0] + ".svg")
    save_confusion(y_true, y_pred, out_paths)
    print(f"\nwrote aggregated confusion matrix to {', '.join(out_paths)}")


if __name__ == "__main__":
    main()
