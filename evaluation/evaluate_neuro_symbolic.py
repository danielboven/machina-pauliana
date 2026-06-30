"""Compare the neuro-symbolic model's boolean variables to the gold standard.

For every model/k output JSON in an input dir, this script compares the boolean
inputs and final verdict across every judgment and reports micro-averaged
precision/recall/F1 against the hand-annotated gold standard. `True`
(requirement holds / act is voidable) is the positive class. Following the
Catala symbolic resolver, every null is read as False. Reporting is as follows:

    TP  gold True  & pred True      FP  gold False & pred True
    FN  gold True  & pred False     TN  gold False & pred False

Two tables are printed. The first one combines all (legal) booleans, including
the booleans in the nested `handeling` and the `vernietigbaar` verdict,
into one micro average. The second groups the booleans per subroutine that
computes them (onverplicht, benadeling schuldeisers, wetenschap), so each
subroutine gets its own micro average. Membership is read straight from the
subroutine schemas, so it stays in step with the model.

A bar chart of the final-verdict (voidable legal act) accuracy is written as a
graph to PDF. Gold is extracted from MD files YAML opening. Run:

python -m evaluation.evaluate_neuro_symbolic data/neuro_symbolic_model
    -o verdict.pdf
"""

import argparse
import glob
import json
import os
from typing import get_args

import matplotlib
import matplotlib.pyplot as plt
import yaml
from pydantic import BaseModel
from sklearn.metrics import precision_recall_fscore_support

from neuro_symbolic_model.schema import NeuroSymbolicResult
from neuro_symbolic_model.subroutine_benadeling_schuldeisers import (
    BenadelingSchuldeisersOutput,
)
from neuro_symbolic_model.subroutine_onverplicht import OnverplichtOutput
from neuro_symbolic_model.subroutine_wetenschap import WetenschapOutput

matplotlib.use("Agg")  # render graph straight to PDF (no display needed)

GOLD_DEFAULT = "data/gold_standard/neuro_symbolic_model/full_judgments"

# Mapping of model name (matched by keyword) to the bar colour and report order
MODEL_COLOURS = (
    ("mistral", "tab:orange"),
    ("gpt", "tab:green"),
    ("gemini", "tab:blue"),
)

# The three subroutines, in report order, each with its output schema
SUBROUTINES = (
    ("onverplicht", OnverplichtOutput),
    ("benadeling schuldeisers", BenadelingSchuldeisersOutput),
    ("wetenschap", WetenschapOutput),
)


def bool_paths(model: type[BaseModel], prefix: str = "") -> list[str]:
    """List every boolean field in a schema, including optional booleans.

    Nested fields use periods between their names; for example, the
    ``onverplicht`` field inside ``handeling`` is returned as
    ``handeling.onverplicht``. These are the variables scored by this script.
    """
    paths = []
    for name, field in model.model_fields.items():
        ann = field.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            paths += bool_paths(ann, f"{prefix}{name}.")
        elif ann is bool or set(get_args(ann)) == {bool, type(None)}:
            paths.append(prefix + name)
    return paths


def subroutine_groups(all_paths: list[str]) -> list[tuple[str, list[str]]]:
    """Group unified result fields by the subroutine that computes them.

    A subroutine's output schema is flat, while the unified result may place
    the same field inside a nested object. Matching by the final field name
    therefore maps, for example, ``onverplicht`` to
    ``handeling.onverplicht``. Coroutine-only fields and the final verdict are
    not assigned to a subroutine group.
    """
    groups = []
    for label, model in SUBROUTINES:
        leaves = set(bool_paths(model))
        groups.append(
            (label, [p for p in all_paths if p.split(".")[-1] in leaves])
        )
    return groups


def at(record: dict | None, path: str) -> bool:
    """Read a boolean from nested dictionaries using a field name as its path.

    For example, ``handeling.onverplicht`` reads ``onverplicht`` from the
    nested ``handeling`` dictionary. A missing field, missing dictionary, or
    null value is read as False, matching the Catala resolver.
    """
    for part in path.split("."):
        record = record.get(part) if isinstance(record, dict) else None
    return bool(record)


def present(record: dict, path: str) -> bool:
    """Whether gold actually declares this path (null counts as declared)."""
    *branches, leaf = path.split(".")
    for branch in branches:
        record = record.get(branch) if isinstance(record, dict) else None
    return isinstance(record, dict) and leaf in record


def load_gold(folder: str, paths: list[str]) -> dict[str, dict[str, bool]]:
    """Load boolean gold values from each judgment's opening YAML block.

    The returned dictionary is keyed by the Markdown filename without its
    ``.md`` extension, matching the identifiers used in model-result files.
    Each value maps the requested field names to their boolean gold values.
    """
    gold = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.md"))):
        stem = os.path.basename(path)[:-3]
        with open(path, encoding="utf-8") as f:
            meta = yaml.safe_load(f.read().split("---", 2)[1])
        if not isinstance(meta, dict):
            raise SystemExit(f"{stem}: frontmatter is not a mapping")
        for p in paths:
            if not present(meta, p):
                print(f"warning: {stem} omits boolean '{p}', read as False")
        gold[stem] = {p: at(meta, p) for p in paths}
    return gold


def score(
    results: dict, gold: dict, paths: list[str]
) -> tuple[float, float, float]:
    """Micro precision/recall/F1 over every (judgment, variable) pair"""
    y_true, y_pred = [], []
    for stem, gold_vars in gold.items():
        if stem not in results:
            print(f"warning: model output has no prediction for {stem}")
            continue
        for p in paths:
            y_true.append(gold_vars[p])
            y_pred.append(at(results[stem], p))
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", pos_label=True, zero_division=0
    )
    return p, r, f


def header(label: int, ks: list[int], block: int) -> str:
    """Outputs the two-line column header shared by both tables."""
    metrics = f"{'precision':>9}{'recall':>9}{'f1-score':>9}   "
    return (
        " " * label
        + "".join(f"k = {k}".center(block) for k in ks)
        + "\n"
        + " " * label
        + metrics * len(ks)
    )


def cells(by_k: dict[int, tuple], ks: list[int], block: int) -> str:
    """Outputs row with precision/recall/f1-score blocks, one per k."""
    out = ""
    for k in ks:
        if k in by_k:
            p, r, f = by_k[k]
            out += f"{p:>9.2f}{r:>9.2f}{f:>9.2f}   "
        else:
            out += " " * block
    return out


def print_overall(
    scores: dict, ks: list[int], label: int, block: int = 30
) -> None:
    """Prints as rows, one pooled micro average per k."""
    print(header(label, ks, block))
    for model in sorted(scores):
        print(f"{model:<{label}}" + cells(scores[model], ks, block))


def print_grouped(
    grouped: dict, ks: list[int], label: int, block: int = 30
) -> None:
    """Here print grouped through a heading, then one row per subroutine."""
    print(header(label, ks, block))
    for model in sorted(grouped):
        print(model)
        for sub, _ in SUBROUTINES:
            row = f'  Subroutine "{sub}"'
            print(f"{row:<{label}}" + cells(grouped[model][sub], ks, block))


def model_style(model: str) -> tuple[int, str]:
    """A model style (order, colour) from its name."""
    for i, (keyword, colour) in enumerate(MODEL_COLOURS):
        if keyword in model.lower():
            return i, colour
    return len(MODEL_COLOURS), "tab:gray"


def verdict_counts(runs: dict, gold: dict) -> dict[str, dict[int, int]]:
    """(model -> k -> ) number of judgments whose verdict matches gold."""
    counts: dict[str, dict[int, int]] = {}
    for (model, k), results in runs.items():
        correct = sum(
            at(results.get(stem), "vernietigbaar") == gold_vars["vernietigbaar"]
            for stem, gold_vars in gold.items()
        )
        counts.setdefault(model, {})[k] = correct
    return counts


def save_verdict_plot(counts: dict, ks: list[int], n: int, path: str) -> None:
    """Grouped bar chart of correct final verdicts:
    a group per k, a bar per model."""
    models = sorted(counts, key=lambda m: model_style(m)[0])
    width = 0.8 / len(models)
    x = list(range(len(ks)))
    fig, ax = plt.subplots()
    for i, model in enumerate(models):
        offset = (i - (len(models) - 1) / 2) * width
        heights = [counts[model][k] for k in ks]
        ax.bar(
            [xi + offset for xi in x],
            heights,
            width,
            label=model.split("/")[-1],
            color=model_style(model)[1],
        )
    ax.set_xticks(x, [f"k = {k}" for k in ks])
    ax.set_ylim(0, n)
    ax.set_yticks(range(n + 1))
    ax.set_xlabel("Retrieved examples (k)")
    ax.set_ylabel(f"Correct final verdicts (out of {n})")
    ax.set_title('Final-verdict accuracy ("vernietigbaar") against gold')
    ax.legend(title="Model")
    fig.savefig(path, bbox_inches="tight")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="Directory of model-output JSON files.")
    ap.add_argument(
        "-g", "--gold", default=GOLD_DEFAULT, help="Gold judgments dir."
    )
    ap.add_argument(
        "-o",
        "--output",
        required=True,
        help="PDF path for the final-verdict accuracy bar chart.",
    )
    args = ap.parse_args(argv)

    paths = bool_paths(NeuroSymbolicResult)
    groups = subroutine_groups(paths)
    gold = load_gold(args.gold, paths)

    runs = {}
    for fp in sorted(glob.glob(os.path.join(args.input, "*.json"))):
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        runs[(data["model"], data["k"])] = data["results"]
    if not runs:
        raise SystemExit(f"No model JSON files in {args.input}")

    ks = sorted({k for _, k in runs})
    overall: dict[str, dict] = {}
    grouped: dict[str, dict] = {}
    for (model, k), results in runs.items():
        overall.setdefault(model, {})[k] = score(results, gold, paths)
        by_sub = grouped.setdefault(model, {label: {} for label, _ in groups})
        for label, sub_paths in groups:
            by_sub[label][k] = score(results, gold, sub_paths)

    label_w = (
        max(
            [len(m) for m in overall]
            + [len(f'  Subroutine "{s}"') for s, _ in SUBROUTINES]
        )
        + 2
    )

    print(
        f"\nMicro-averaged over {len(gold)} judgments × {len(paths)} boolean "
        f"variables (positive class = True):\n"
    )
    print_overall(overall, ks, label_w)
    print("\n\nThe same, but grouped per subroutine:\n")
    print_grouped(grouped, ks, label_w)

    save_verdict_plot(verdict_counts(runs, gold), ks, len(gold), args.output)
    print(f"\n\nwrote final-verdict accuracy plot to {args.output}")


if __name__ == "__main__":
    main()
