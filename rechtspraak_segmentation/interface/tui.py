"""TUI based on Textual: scroll a document rendered as Markdown, step between
documents, and flag any with a note.

Navigation:
    →/Enter   next document
    ←         previous document
    f         flag the current document (opens a required note)
    ↑↓        scroll
    q         quit

The body is the shared rich renderable from render.py
Flagging pushes a small modal note screen; while it is open ↑↓ still scroll the
document underneath.
A parse or court-detection error becomes a visible error page rather than a
crash, so the file can still be flagged. Each flag is appended to the TSV log
the moment its note is confirmed.

Structure:
    flag_file     — append one TSV row for a flagged document.
    Body          — focusable scroll area.
    NoteScreen    — modal note input (Enter saves, Esc cancels).
    ReviewApp     — the Textual app: one document at a time, stepping, flags.
    review_folder — public entry gathers files, runs the app, writes the log.
"""

import datetime
import sys
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static

from ..core.xmlutil import gather_xml, in_court
from .render import doc_renderable, render_doc

# TSV columns written to the flag log in this order
FLAG_LOG_COLUMNS = (
    "timestamp",
    "path",
    "ecli",
    "strategy",
    "nsections",
    "note",
)


def flag_file(root, path, meta, log_path, note):
    """Append one tab-separated row. note is whitespace-collapsed so it can
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


class Body(VerticalScroll):
    """The document scroll area. Focusable, so ↑↓ scroll natively.
    Only ←/→ are rebound (from horizontal scroll) to next/previous doc."""

    can_focus = True

    BINDINGS = [
        Binding("left", "app.prev", "Prev doc", key_display="←"),
        Binding("right", "app.next", "Next doc", key_display="→"),
    ]


class NoteScreen(ModalScreen[str | None]):
    """A flag note as a small modal docked at the bottom. It captures typing
    (so the letter keys go into the note, not the app)."""

    # No default border
    CSS = """
    NoteScreen { background: transparent; }
    #note {
        dock: bottom; width: 100%; height: 1;
        border: none; background: $panel; padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "scroll(-1)", "Scroll up", show=False),
        Binding("down", "scroll(1)", "Scroll down", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="flag note — Enter saves · Esc cancels", id="note"
        )

    def on_mount(self) -> None:
        self.query_one("#note", Input).focus()

    def _body(self) -> Body:
        return self.app.query_one("#body", Body)

    def action_scroll(self, dy: int) -> None:
        body = self._body()
        (body.scroll_down if dy > 0 else body.scroll_up)(animate=False)

    def action_page(self, dy: int) -> None:
        body = self._body()
        (body.scroll_page_down if dy > 0 else body.scroll_page_up)(
            animate=False
        )

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#note")
    def _submit(self, event: Input.Submitted) -> None:
        # An empty note is rejected (required): dismiss(None) keeps the doc.
        self.dismiss(event.value.strip() or None)


class ReviewApp(App):
    """One document at a time, go through the file list and flag docs."""

    TITLE = "Rechtspraak segmentation review"
    ENABLE_COMMAND_PALETTE = False  # disable default Ctrl+P of Textual

    CSS = "#body { height: 1fr; padding: 0 1; }"

    BINDINGS = [
        Binding("right", "next", "Next doc", show=False),
        Binding("enter", "next", "Next doc", show=False),
        Binding("f", "flag", "Flag"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, files, root, log_path):
        # ansi_color=True disables Textual ANSIToTruecolor filter, so the
        # palette ANSI colours are ussed
        super().__init__(ansi_color=True)
        self.files = files
        self.root = root
        self.log_path = log_path
        self.idx = 0
        self.meta: dict = {}
        # idx -> {"note", "meta", "path"} for every flagged document
        self.flags: dict[int, dict] = {}
        self.visited: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        # One persistent Static lives inside the scroll area for the whole
        # session. Each document just calls `.update()` on it.
        yield Body(Static(id="content"), id="body")
        yield Footer()

    async def on_mount(self) -> None:
        await self._load()

    def _update_header(self) -> None:
        path = self.files[self.idx]
        rel = (
            path.relative_to(self.root)
            if path.is_relative_to(self.root)
            else path.name
        )
        flag = "  ·  ⚑ flagged" if self.idx in self.flags else ""
        self.title = str(rel)
        self.sub_title = (
            f"[{self.idx + 1}/{len(self.files)}]  ·  "
            f"{self.meta.get('strategy', '?')} · "
            f"{self.meta.get('nsec', 0)} sections{flag}"
        )

    async def _load(self) -> None:
        path = self.files[self.idx]
        self.visited.add(self.idx)
        body = self.query_one("#body", Body)
        try:
            rd = render_doc(path.read_bytes())
        except Exception as e:  # parse / unknown-court error, show these
            self.meta = {"strategy": "error", "nsec": 0, "ecli": ""}
            renderable = f"ERROR: {e}"
        else:
            self.meta = rd.meta
            renderable = doc_renderable(rd)
        # Header and body update together: the renderable is built first, then
        # both the title (below) and content swap in the same frame.
        self._update_header()
        self.query_one("#content", Static).update(renderable)
        body.scroll_home(animate=False)
        body.focus()

    # Next and previous document
    async def action_next(self) -> None:
        if self.idx + 1 < len(self.files):
            self.idx += 1
            await self._load()
        else:
            self.exit()  # review is complete

    async def action_prev(self) -> None:
        if self.idx > 0:
            self.idx -= 1
            await self._load()

    # Flagging a document
    def action_flag(self) -> None:
        async def _save(note: str | None) -> None:
            if note:
                path = self.files[self.idx]
                meta = dict(self.meta)
                self.flags[self.idx] = {
                    "note": note,
                    "meta": meta,
                    "path": path,
                }
                # Write TSV line immediately
                flag_file(self.root, path, meta, self.log_path, note)
                await self.action_next()  # saved -> step to the next document
            else:  # cancelled / empty: stay on this document
                self.query_one("#body", Body).focus()

        self.push_screen(NoteScreen(), _save)


def review_folder(root: Path, log_path: Path, court: str = None):
    """Public entry point for the interactive review. Gathers XML files from
    root and runs the Textual app, which appends each flag to the TSV log as
    it is confirmed."""
    files = gather_xml(root)
    if court:
        files = [f for f in files if in_court(f, root, court)]
    if not files:
        print(f"No .xml files found under {root}", file=sys.stderr)
        return

    app = ReviewApp(files, root, log_path)
    app.run()

    flagged = len(app.flags)
    print(
        f"\nReviewed {len(app.visited)}/{len(files)} file(s): "
        f"{flagged} flagged."
    )
    if flagged:
        print(f"Flagged files logged to: {log_path}")
