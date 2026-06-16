"""Serializer to turn block abstraction into Markdown.

The single serialization stage of the pipeline. It reads the typed blocks
(blocks.py) and renders them. This stage does not concern with any XML or
segmentation, so the output format can change here without touching either.

`to_markdown` renders a block range (a whole document, or one section's body).
Footnote definitions are appended only when a `footnotes` map is supplied, so a
caller rendering section-by-section can instead collect all definitions once at
the very end.
"""

from .blocks import (
    Block,
    Break,
    Emph,
    Footnote,
    FootnoteRef,
    Heading,
    Image,
    InlineImage,
    List,
    ListItem,
    Para,
    Row,
    Run,
    Table,
    TextRun,
)

# --------------------------------------------------------------------------- #
# Inline runs
# --------------------------------------------------------------------------- #
# Symbol/Wingdings-font glyphs are not so clean in the Markdown, they're almost
# all used for bullets, so these are converted to markdown bullets.
_PUA_GLYPHS = {
    "\uf020": " ",  # symbol-font space
    "\uf02d": "-",  # symbol-font hyphen
    "\uf0a7": "-",  # Wingdings square bullet -> Markdown bullet
    "\uf0b7": "-",  # Wingdings round bullet -> Markdown bullet
    "\uf0e0": "-",  # Wingdings arrow -> Markdown bullet
}
_PUA_TABLE = str.maketrans(_PUA_GLYPHS)


def _clean_glyphs(s: str) -> str:
    if s.isascii():
        return s
    return "".join(
        c for c in s.translate(_PUA_TABLE) if not 0xE000 <= ord(c) <= 0xF8FF
    )


def _emph_md(run: Emph) -> str:
    inner = "".join(run_md(c) for c in run.children)
    core = inner.strip()
    if not core:
        return inner
    # CommonMark won't emphasize "** x **": whitespace must sit OUTSIDE the
    # markers, so keep the surrounding space and wrap only the core. Underline
    # (and caps/smallcaps) has no Markdown equivalent and stays plain.
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()) :]
    pre = post = ""
    if "bold" in run.role:
        pre, post = pre + "**", "**" + post
    if "italic" in run.role:
        pre, post = pre + "*", "*" + post
    return f"{lead}{pre}{core}{post}{trail}"


def run_md(run: Run) -> str:
    if isinstance(run, TextRun):
        return _clean_glyphs(run.value)
    if isinstance(run, Break):
        return "  \n"  # GFM hard line break
    if isinstance(run, Emph):
        return _emph_md(run)
    if isinstance(run, FootnoteRef):
        return f"[^{run.label}]"
    if isinstance(run, InlineImage):
        return ""  # explicitly dropped
    return ""


def runs_md(runs: list[Run]) -> str:
    return "".join(run_md(r) for r in runs).strip()


# --------------------------------------------------------------------------- #
# Ordered-list markers, Roman style list using greedy subtraction
# --------------------------------------------------------------------------- #
_ROMAN = [
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
]


def _to_roman(n: int) -> str:
    out = []
    for val, sym in _ROMAN:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def _ordered_label(style: str, i: int) -> str:
    """The literal marker for ordered-list item `i` (1-based), per numeration.
    GFM has no lettered/roman lists, so the computed marker is emitted as text
    to preserve the original lettering."""
    if style == "loweralpha":
        return f"{chr(ord('a') + i - 1)}."
    if style == "upperalpha":
        return f"{chr(ord('A') + i - 1)}."
    if style == "lowerroman":
        return f"{_to_roman(i)}."
    return f"{i}."  # arabic / default


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #
def _item_md(item: ListItem) -> str:
    return " ".join(b for b in (block_md(x) for x in item.blocks) if b)


def _list_md(lst: List) -> str:
    out = []
    for i, it in enumerate(lst.items, 1):
        label = _ordered_label(lst.style, i) if lst.ordered else "-"
        out.append(f"{label} {_item_md(it)}")
    return "\n".join(out)


def _table_md(table: Table) -> str:
    """Render a Table as a GFM table. Column spans are flattened: a spanning
    cell occupies its first column, the covered columns are emitted empty."""
    if not table.rows:
        return ""
    ncols = table.ncols or max(sum(c.span for c in r.cells) for r in table.rows)

    def row_cells(row: Row) -> list[str]:
        flat: list[str] = []
        for cell in row.cells:
            text = (
                " ".join(b for b in (block_md(x) for x in cell.blocks) if b)
                .replace("|", "\\|")
                .replace("\n", " ")
            )
            flat.append(text)
            flat.extend([""] * (cell.span - 1))
        flat += [""] * (ncols - len(flat))
        return flat[:ncols]

    rows = [row_cells(r) for r in table.rows]
    head, *body = rows
    lines = ["| " + " | ".join(head) + " |"]
    lines.append("| " + " | ".join(["---"] * ncols) + " |")
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def block_md(block: Block) -> str:
    if isinstance(block, Para):
        body = runs_md(block.runs)
        return f"{block.marker} {body}".strip() if block.marker else body
    if isinstance(block, Heading):
        nr = f"{block.number} " if block.number is not None else ""
        return f"## {nr}{block.heading_text}".rstrip()
    if isinstance(block, List):
        return _list_md(block)
    if isinstance(block, Table):
        return _table_md(block)
    if isinstance(block, Image):
        return ""  # explicitly dropped
    return ""


# --------------------------------------------------------------------------- #
# Footnotes & document range
# --------------------------------------------------------------------------- #
def footnote_def(fn: Footnote) -> str:
    body = " ".join(b for b in (block_md(x) for x in fn.blocks) if b)
    return f"[^{fn.label}]: {body}".strip()


def _used_footnotes(
    blocks: list[Block], footnotes: dict[str, Footnote]
) -> list[str]:
    """Labels of footnotes referenced (in order) by the given blocks."""
    seen: list[str] = []

    def scan_runs(runs: list[Run]) -> None:
        for r in runs:
            if isinstance(r, FootnoteRef):
                if r.label in footnotes and r.label not in seen:
                    seen.append(r.label)
            elif isinstance(r, Emph):
                scan_runs(r.children)

    def scan_block(b: Block) -> None:
        if isinstance(b, Para):
            scan_runs(b.runs)
        elif isinstance(b, List):
            for it in b.items:
                for sub in it.blocks:
                    scan_block(sub)
        elif isinstance(b, Table):
            for row in b.rows:
                for cell in row.cells:
                    for sub in cell.blocks:
                        scan_block(sub)

    for b in blocks:
        scan_block(b)
    return seen


def to_markdown(
    blocks: list[Block], footnotes: dict[str, Footnote] | None = None
) -> str:
    """Serialize a block range to MD. When `footnotes` is given, the definitions
    of any footnotes referenced within the range are appended. Pass None to emit
    the body only (e.g. to collect all definitions once at the document end)."""
    body = "\n\n".join(md for md in (block_md(b) for b in blocks) if md)
    used = _used_footnotes(blocks, footnotes) if footnotes else []
    if used:
        defs = "\n\n".join(footnote_def(footnotes[lbl]) for lbl in used)
        body = f"{body}\n\n{defs}" if body else defs
    return body
