"""Run the neuro-symbolic model over a folder of input cases.

Reads every Markdown file in an input directory, resolves it with the
neuro-symbolic model (LLM routines + Catala), and writes one JSON file with
the run's model and k at the top and the resolved cases keyed by input filename:

    {
      "model": "...",
      "k": 5,
      "ablation": {"ECLI_NL_GHARL_2013_822": ["ECLI:NL:RBARN:2011:BQ8538"]},
      "results": {
        "JOR_2009_46": { ...resolved variables + vernietigbaar... },
        ...
      }
    }

Each input file opens with a YAML block containg case metadata. Text below this
block is the natural language input sent to the model.

`ablation` names one ECLI, or a list of them, to remove from RAG retrieval for
that case.

Run from the repo root:

    python -m evaluation.build_neuro_symbolic_dataset INPUTS_DIR -o OUT.json
        [--model ...] [-k 5] [--no-ablation]
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from neuro_symbolic_model import resolve
from neuro_symbolic_model.model import DEFAULT_K, DEFAULT_MODEL

# Delay between cases to stay within inference provider rate limits
REQUEST_DELAY = 60


@dataclass(frozen=True)
class CaseInput:
    """One input case: the YAML opening block and the facts text below it. Only
    `casus` is sent to the model; the frontmatter block is metadata for this
    script."""

    stem: str
    meta: dict
    casus: str

    @property
    def ablation(self) -> tuple[str, ...]:
        """The ECLIs this case ablates from retrieval, read from the `ablation`
        frontmatter key. Accepts a single ECLI or a list."""
        value = self.meta.get("ablation") or []
        if isinstance(value, str):
            value = [value]
        return tuple(value)


def load_case(path: Path) -> CaseInput:
    """Read one input file, splitting off a leading YAML opening block."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return CaseInput(path.stem, {}, text)
    _, frontmatter, body = text.split("---", 2)
    meta = yaml.safe_load(frontmatter) or {}
    if not isinstance(meta, dict):
        raise SystemExit(f"{path.name}: frontmatter is not a mapping")
    return CaseInput(path.stem, meta, body.lstrip("\n"))


async def resolve_dir(
    cases: list[CaseInput], model: str, k: int
) -> dict[str, dict]:
    """Resolve every input case, keyed by filename.

    Cases are processed one at a time (each `resolve` already runs its routines
    concurrently), in sorted order, with a short delay between them."""
    results: dict[str, dict] = {}
    for i, case in enumerate(cases, 1):
        ablating = (
            f" (ablating {', '.join(case.ablation)})" if case.ablation else ""
        )
        print(f"[{i}/{len(cases)}] resolving {case.stem}{ablating}")
        result = await resolve(
            case.casus, model=model, k=k, exclude=case.ablation
        )
        results[case.stem] = result.model_dump()
        if i < len(cases):
            await asyncio.sleep(REQUEST_DELAY)
    return results


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "input_dir", type=Path, help="Directory of input .md case files."
    )
    ap.add_argument(
        "-o", "--output", type=Path, required=True, help="Output JSON file."
    )
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model id (default: {DEFAULT_MODEL}).",
    )
    ap.add_argument(
        "-k",
        type=int,
        default=DEFAULT_K,
        help=f"RAG top-k (default: {DEFAULT_K}).",
    )
    ap.add_argument(
        "--no-ablation",
        action="store_true",
        help="Ignore the `ablation` frontmatter key and retrieve over the "
        "full corpus (the contaminated baseline arm).",
    )
    args = ap.parse_args(argv)

    cases = [load_case(p) for p in sorted(args.input_dir.glob("*.md"))]
    # Ablation only removes judgments from retrieval ie at k >= 1
    if args.no_ablation or args.k < 1:
        cases = [CaseInput(c.stem, {}, c.casus) for c in cases]

    results = asyncio.run(resolve_dir(cases, args.model, args.k))

    ablation = {c.stem: list(c.ablation) for c in cases if c.ablation}
    payload = {
        "model": args.model,
        "k": args.k,
        # JSON key omitted when nothing is ablated, rather than written empty
        **({"ablation": ablation} if ablation else {}),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(results)} results to {args.output}")


if __name__ == "__main__":
    main()
