"""Run the neuro-symbolic model over a folder of input cases.

Reads every Markdown file in an input directory (each holding the natural
language input, i.e. facts/dispute of a case), resolves it with the
neuro-symbolic model (LLM routines + Catala), and writes one JSON file with
the run's model and k at the top and the resolved cases keyed by input filename:

    {
      "model": "...",
      "k": 5,
      "results": {
        "JOR_2009_46": { ...resolved variables + vernietigbaar... },
        ...
      }
    }

Run from the repo root:

    python -m evaluation.build_neuro_symbolic_dataset INPUTS_DIR -o OUT.json
        [--model ...] [-k 5]
"""

import argparse
import asyncio
import json
from pathlib import Path

from neuro_symbolic_model import resolve
from neuro_symbolic_model.model import DEFAULT_K, DEFAULT_MODEL

# Delay between cases to stay within inference provider rate limits
REQUEST_DELAY = 60


async def resolve_dir(input_dir: Path, model: str, k: int) -> dict[str, dict]:
    """Resolve every MD input file, keyed by filename.

    Cases are processed one at a time (each `resolve` already runs its routines
    concurrently), in sorted order, with a short delay between them."""
    results: dict[str, dict] = {}
    paths = sorted(input_dir.glob("*.md"))
    for i, path in enumerate(paths, 1):
        print(f"[{i}/{len(paths)}] resolving {path.name}")
        result = await resolve(
            path.read_text(encoding="utf-8"), model=model, k=k
        )
        results[path.stem] = result.model_dump()
        if i < len(paths):
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
    args = ap.parse_args(argv)

    results = asyncio.run(resolve_dir(args.input_dir, args.model, args.k))

    payload = {"model": args.model, "k": args.k, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(results)} results to {args.output}")


if __name__ == "__main__":
    main()
