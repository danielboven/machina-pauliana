"""Interactive curses review: scroll a document, arror right is OK / arrow left
is flag for review.

It renders with the shared view-model (render.py) with a curses colour palette.
A parse or court-detection error becomes a visible error line intead of a crash,
so the reviewer can flag the file and go to the next.

Structure:
    DocView       — one document on screen: scrolling, drawing, the flag-note
                    editor, and the per-file key loop.
    _run_review   — walk the file list, construct a DocView per file, log flags.
    review_folder — public entry; runs _run_review inside curses.wrapper so the
                    terminal is always restored, even on an unexpected error.
"""

import curses
import datetime
import sys
from pathlib import Path

from ..core.xmlutil import gather_xml, in_court
from .render import Line, render_document, wrap_lines

CURSES_PALETTE = {
    "procesverloop": curses.COLOR_CYAN,
    "feiten": curses.COLOR_YELLOW,
    "geschil": curses.COLOR_MAGENTA,
    "overwegingen": curses.COLOR_BLUE,
    "beslissing": curses.COLOR_GREEN,
    "overig": curses.COLOR_WHITE,
    "preamble": curses.COLOR_WHITE,
}
_PAIR = {}


def _init_colors():
    """Initializes curses color pairs from CURSES_PALETTE.
    Tries a transparent background first, falls back to black."""
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    for i, (label, col) in enumerate(CURSES_PALETTE.items(), start=1):
        curses.init_pair(i, col, bg)
        _PAIR[label] = i


def _attr(label, kind):
    """Returns the curses display attribute for a line.
    Color comes from `label`. Banners get bold and underline,
    preamble gets dim."""
    pair = curses.color_pair(_PAIR.get(label, _PAIR["overig"]))
    if kind == "banner":
        return pair | curses.A_BOLD | curses.A_UNDERLINE
    if label == "preamble":
        return pair | curses.A_DIM
    return pair


def _addstr(stdscr, y, x, text, w, attr=0):
    """Wraps addnstr to silently ignore writes to the last cell."""
    try:
        stdscr.addnstr(y, x, text, w, attr)
    except curses.error:
        pass


# TSV columns written to the flag log, in order
FLAG_LOG_COLUMNS = (
    "timestamp",
    "path",
    "ecli",
    "strategy",
    "nsections",
    "note",
)


def flag_file(root, path, meta, log_path, note):
    """Append one tab-separated row. `note` is whitespace-collapsed so it can
    never contain a tab/newline that would break the TSV."""
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    clean_note = " ".join(str(note).split())
    row = (
        stamp,
        str(rel),
        meta.get("ecli", ""),
        meta.get("strategy", ""),
        str(meta.get("nsec", 0)),
        clean_note,
    )
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write("\t".join(row) + "\n")


class DocView:
    """One document on screen: scroll it, then approve, flag (with a required
    note) or quit. Consumes the shared render model from render.py."""

    VIEW_HINT = (
        "→/Enter OK   ←/f Flag   ↑↓/PgUp/PgDn scroll   g/G top/end   q quit"
    )
    NOTE_HINT = (
        "Enter save (required) · Esc cancel · ↑↓/PgUp/PgDn/Home/End scroll"
    )

    def __init__(self, stdscr, path, root, idx, total):
        self.stdscr = stdscr
        self.path = path
        self.root = root
        self.idx = idx
        self.total = total
        self.top = 0  # index of the first visible (wrapped) line
        self.max_top = 0  # furthest you can scroll; set each draw
        try:
            self.lines, self.meta = render_document(path.read_bytes())
        except Exception as e:  # parse / unknown-court -> show it, allow flag
            self.lines = [Line(f"ERROR: {e}", "overig", "body")]
            self.meta = {"strategy": "error", "nsec": 0, "ecli": ""}

    def scroll(self, key, page):
        """Move the viewport. `page` is the body height (for PgUp/PgDn). Letter
        shortcuts work in view mode. In note mode (on flagging) only the
        KEY_* keys reach here, so the letters fall through as typed text."""
        if key in (curses.KEY_DOWN, ord("j")):
            self.top += 1
        elif key in (curses.KEY_UP, ord("k")):
            self.top -= 1
        elif key == curses.KEY_NPAGE:
            self.top += page
        elif key == curses.KEY_PPAGE:
            self.top -= page
        elif key in (curses.KEY_HOME, ord("g")):
            self.top = 0
        elif key in (curses.KEY_END, ord("G")):
            self.top = self.max_top

    def _draw(self, note):
        """Render a frame. When `note` is not None the sticky two-row editor is
        drawn just above the status bar (and the body shrinks to fit). Returns
        the visible body height so callers can size PgUp/PgDn paging."""
        stdscr = self.stdscr
        h, w = stdscr.getmaxyx()
        body_h = max(1, h - 2 - (2 if note is not None else 0))

        visual = wrap_lines(self.lines, w - 1)
        self.max_top = max(0, len(visual) - body_h)
        self.top = max(0, min(self.top, self.max_top))

        stdscr.erase()
        rel = (
            self.path.relative_to(self.root)
            if self.path.is_relative_to(self.root)
            else self.path.name
        )
        title = (
            f"[{self.idx + 1}/{self.total}] {rel}   "
            f"{self.meta['strategy']} · {self.meta['nsec']} sections"
        )
        _addstr(stdscr, 0, 0, title.ljust(w - 1), w - 1, curses.A_REVERSE)

        for row in range(body_h):
            li = self.top + row
            if li >= len(visual):
                break
            ln = visual[li]
            if ln.kind == "blank":
                continue
            prefix = "" if ln.kind == "banner" else "  "
            _addstr(
                stdscr,
                row + 1,
                0,
                (prefix + ln.text)[: w - 1],
                w - 1,
                _attr(ln.label, ln.kind),
            )

        if note is not None:
            sep = " FLAG NOTE — what is wrong with the segmentation? "
            _addstr(
                stdscr, h - 3, 0, sep.ljust(w - 1, "─"), w - 1, curses.A_BOLD
            )
            shown = "note> " + note
            if len(shown) > w - 1:  # keep the typing end in view
                shown = shown[len(shown) - (w - 1) :]
            _addstr(stdscr, h - 2, 0, shown.ljust(w - 1), w - 1, curses.A_BOLD)

        pct = 100 if self.max_top == 0 else int(100 * self.top / self.max_top)
        hint = self.NOTE_HINT if note is not None else self.VIEW_HINT
        _addstr(
            stdscr,
            h - 1,
            0,
            f" {pct:3d}%  {hint}".ljust(w - 1),
            w - 1,
            curses.A_REVERSE,
        )
        stdscr.refresh()
        return body_h

    def review(self):
        """View-mode loop. Returns (action, note) with action in
        {'next', 'flag', 'quit'}; note is set only for 'flag'."""
        while True:
            page = self._draw(note=None)
            k = self.stdscr.getch()
            if k in (curses.KEY_RIGHT, 10, 13, curses.KEY_ENTER):
                return "next", None
            if k in (curses.KEY_LEFT, ord("f")):
                note = self._prompt_note()
                if note is not None:
                    return "flag", note  # else Esc cancelled -> keep viewing
            elif k == ord("q"):
                return "quit", None
            else:
                self.scroll(k, page)

    def _prompt_note(self):
        """Sticky-editor loop. Returns a non-empty note on Enter, or None if
        cancelled with Esc. The document stays scrollable while typing:
        printable keys build the note, KEY_* keys scroll the body underneath."""
        note = ""
        while True:
            page = self._draw(note=note)
            try:
                # get_wch -> str for normal chars (incl. accented), int for keys
                ch = self.stdscr.get_wch()
            except curses.error:
                continue
            if isinstance(ch, str):
                if ch in ("\n", "\r"):
                    if note.strip():
                        return note.strip()  # empty note is rejected (required)
                elif ch == "\x1b":
                    return None
                elif ch in ("\x7f", "\b"):
                    note = note[:-1]
                elif ch.isprintable():
                    note += ch
            elif ch == curses.KEY_BACKSPACE:
                note = note[:-1]
            else:
                self.scroll(ch, page)


def _run_review(stdscr, files, root, log_path):
    """Helper that runs the review loop inside a curses session.
    Walks files in order and returns (approved, flagged, reached) counts."""
    # curses waits after \x1b to decide: bare Esc or start of a key sequence?
    # 25ms is enough for sequences to arrive but feels instant on Esc press
    curses.set_escdelay(25)
    curses.curs_set(0)
    stdscr.keypad(True)
    _init_colors()

    idx = approved = flagged = 0
    while 0 <= idx < len(files):
        view = DocView(stdscr, files[idx], root, idx, len(files))
        action, note = view.review()
        if action == "quit":
            break
        if action == "flag":
            flag_file(root, files[idx], view.meta, log_path, note)
            flagged += 1
        else:
            approved += 1
        idx += 1
    return approved, flagged, idx


def review_folder(root: Path, log_path: Path, court: str = None):
    """Public entry point for the interactive review. Gathers XML files from
    `root` and runs the loop via curses.wrapper so the terminal is always
    restored on exit or crash."""
    files = gather_xml(root)
    if court:
        files = [f for f in files if in_court(f, root, court)]
    if not files:
        print(f"No .xml files found under {root}", file=sys.stderr)
        return
    approved, flagged, reached = curses.wrapper(
        _run_review, files, root, log_path
    )
    print(
        f"\nReviewed {reached}/{len(files)} file(s): "
        f"{approved} OK, {flagged} flagged."
    )
    if flagged:
        print(f"Flagged files logged to: {log_path}")
