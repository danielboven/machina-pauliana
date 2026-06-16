"""Command-line program: argument parsing and the non-interactive renderer
(full document, sections coloured). The interactive default goes to the Textual
reviewer in tui.py. Both modes display the same rich renderable (render.py),
meaning that `--print` and the TUI show identical output.
"""

import argparse
import sys
from pathlib import Path

from lxml import etree
from rich.console import Console

from ..core.xmlutil import gather_xml, in_court
from ..lexicon import UnknownCourtError
from .render import doc_renderable, render_doc
from .tui import review_folder

# Errors that are per-document (note, not fatal to a batch run)
_DOC_ERRORS = (etree.XMLSyntaxError, UnknownCourtError, NotImplementedError)


def print_document(path, xml_bytes, color):
    """Renders one document to stdout via rich."""
    rd = render_doc(xml_bytes)
    console = Console(no_color=not color)
    console.rule(f"{path.name}   (strategy: {rd.meta['strategy']})")
    console.print(doc_renderable(rd))
    console.print()


def _run_print(root, color, court):
    """Helper that iterates over XML files under `root`, printing each one.
    Skips files that fail to read or parse and logs errors to stderr."""
    files = gather_xml(root)
    if court:
        files = [f for f in files if in_court(f, root, court)]
    for path in files:
        try:
            xml_bytes = path.read_bytes()
        except OSError as e:
            print(f"ERROR reading {path}: {e}", file=sys.stderr)
            continue
        try:
            print_document(path, xml_bytes, color)
        except _DOC_ERRORS as e:
            print(f"ERROR {path}: {e}", file=sys.stderr)


def main():
    """Entry point of program. Parses CLI arguments and defaults to curses TUI
    or through --print mode to non-interactive output"""
    p = argparse.ArgumentParser(
        description="Review section boundaries in a folder of Rechtspraak XML "
        "(layout COURT/YEAR/ECLI.xml). Default mode is an "
        "interactive viewer."
    )
    p.add_argument(
        "path",
        metavar="FOLDER",
        help="Root folder (searched recursively) or a single XML file.",
    )
    p.add_argument(
        "--log",
        metavar="FILE",
        default=None,
        help="Where to log flagged files "
        "(default: <folder>/review_flagged.log).",
    )
    p.add_argument(
        "--print",
        dest="dump",
        action="store_true",
        help="Non-interactive: render each whole document as Markdown, "
        "with a banner per section.",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour (only affects --print).",
    )
    p.add_argument(
        "--court",
        type=str.upper,
        choices=["HR", "GH", "RB"],
        default=None,
        help="Only process one court family "
        "(HR=Hoge Raad, GH=hoven, RB=rechtbanken).",
    )
    args = p.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f"Path not found: {root}", file=sys.stderr)
        sys.exit(1)

    # rich auto-detects a non-TTY and drops styling (note this was not tested).
    color = not args.no_color

    if args.dump:
        _run_print(root, color, args.court)
        return

    # Default interactive review over the folder (with writing TSV log file)
    base = root if root.is_dir() else root.parent
    log_path = Path(args.log) if args.log else base / "review_flagged.log"
    review_folder(root, log_path, args.court)


if __name__ == "__main__":
    main()
