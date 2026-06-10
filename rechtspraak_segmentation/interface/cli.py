"""Command-line program: argument parsing and non-interactive ANSI renderer
(full document with sections coloured). The interactive default goes to
curses TUI in tui.py. Both modes draw the same view-model (render.py).
"""

import argparse
import sys
from pathlib import Path

from lxml import etree

from ..core.xmlutil import gather_xml, in_court
from ..lexicon import UnknownCourtError
from .render import render_document
from .tui import review_folder

LABEL_COLORS = {
    "procesverloop": "\033[36m",
    "feiten": "\033[33m",
    "geschil": "\033[35m",
    "overwegingen": "\033[34m",
    "beslissing": "\033[32m",
    "overig": "\033[90m",
    "preamble": "\033[90m",
}
RESET = "\033[0m"
BOLD = "\033[1m"

# Errors that are per-document (note, not fatal to a batch run)
_DOC_ERRORS = (etree.XMLSyntaxError, UnknownCourtError, NotImplementedError)


def supports_color() -> bool:
    """Returns True if stdout is a real TTY and likely supports ANSI colors."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _banner(path, strategy, show_strategy):
    """Helper that builds the separator banner printed above each document.
    Includes the filename and optionally the segmentation strategy used."""
    line = "─" * 64
    head = f"{line}\n  {path.name}"
    if show_strategy:
        head += f"   (strategy: {strategy})"
    return f"{head}\n{line}"


def print_document(path, xml_bytes, color):
    """Prints a rendered document to stdout one line at a time.
    Each section gets its ANSI color from LABEL_COLORS when color isTrue."""
    lines, meta = render_document(xml_bytes)
    print(_banner(path, meta["strategy"], True))
    for ln in lines:
        if ln.kind == "blank":
            print()
            continue
        prefix = "" if ln.kind == "banner" else "  │ "
        text = prefix + ln.text
        if color:
            c = LABEL_COLORS.get(ln.label, "")
            attr = BOLD if ln.kind == "banner" else ""
            print(f"{attr}{c}{text}{RESET}")
        else:
            print(text)
    print()


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
        help="Non-interactive: print each whole document, coloured "
        "by section (ANSI).",
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

    color = supports_color() and not args.no_color

    if args.dump:
        _run_print(root, color, args.court)
        return

    # Default interactive review over the folder (with writing TSV log file)
    base = root if root.is_dir() else root.parent
    log_path = Path(args.log) if args.log else base / "review_flagged.log"
    review_folder(root, log_path, args.court)


if __name__ == "__main__":
    main()
