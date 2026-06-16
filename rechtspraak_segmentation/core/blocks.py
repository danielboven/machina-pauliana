"""The typed block model: one Python type per meaningful XML construct.

The parser (parse.py) reads `<uitspraak>` once and produces a flat, document-
ordered stream of the blocks here, dissolving the layout-only containers
while keeping the structure that we think carry meaning
(`List`/`ListItem`, `Table`/`Row`/`Cell`, and `<section>` membership).
It's an extra level of abstraction that makes other methods and the Markdown
conversion cleaner.

This module is the model only. Each block exposes text, so the lexicon and
detectors work on plain text. Rendering blocks to Markdown
is a separate concern and lives in serialize.py, which reads these same fields.
The model never imports it.
"""

from dataclasses import dataclass, field
from typing import Optional


def _norm(s: str) -> str:
    """Collapse all whitespace runs to single spaces, matching el_text."""
    return " ".join(s.split())


# --------------------------------------------------------------------------- #
# Inline runs (content of a Para, Heading, or table Cell)
# --------------------------------------------------------------------------- #
class Run:
    """An inline fragment. `text` is the plain, lexicon-facing form."""

    def text(self) -> str:
        return ""


@dataclass
class TextRun(Run):
    value: str

    def text(self) -> str:
        return self.value


@dataclass
class Break(Run):
    """A <?linebreak?> processing instruction. In plain text this becomes
    a space to help with segmentation (leads to better results)."""

    def text(self) -> str:
        return " "


@dataclass
class Emph(Run):
    """An <emphasis>. `role` is the raw Rechtspraak role ('bold', 'italic',
    'underline' and combinations)."""

    role: str
    children: list[Run]
    pos: int = -1
    starts_line: bool = False

    def text(self) -> str:
        return "".join(c.text() for c in self.children)


@dataclass
class FootnoteRef(Run):
    """An inline <footnote-ref>. Contributes no plain text.
    serialize.py turns it into a GFM reference."""

    label: str
    linkend: str = ""

    def text(self) -> str:
        return ""


@dataclass
class InlineImage(Run):
    """An inline <inlinemediaobject> is mostly a faux letterhead artefact.
    Explicitly dropped (defined, not silently skipped)."""

    def text(self) -> str:
        return ""


def iter_blocks(blocks: list["Block"]):
    """Yield every block depth-first in document order. It descends into List
    items and Table cells (Footes are done seperately)."""
    for b in blocks:
        yield b
        if isinstance(b, List):
            for it in b.items:
                yield from iter_blocks(it.blocks)
        elif isinstance(b, Table):
            for row in b.rows:
                for cell in row.cells:
                    yield from iter_blocks(cell.blocks)


def runs_text(runs: list[Run]) -> str:
    return _norm("".join(r.text() for r in runs))


def blocks_text(blocks: list["Block"]) -> str:
    return _norm(" ".join(b.text for b in blocks if b.text))


# --------------------------------------------------------------------------- #
# Block-level
# --------------------------------------------------------------------------- #
@dataclass
class SectionBlock:
    """A structural <section> container. They hold a title and sometimes the
    role that was provided (but not always accurate). Both are used by detection
    but role only as a last resort. Logical sections never nest
    in this corpus, but `parent` is kept for the general case."""

    pos: int
    role: str = ""
    title: Optional["Heading"] = None
    parent: Optional["SectionBlock"] = None


@dataclass
class Block:
    """Shared block fields. pos is order index.
    `region` is 'info' for content inside the <uitspraak.info> letterhead."""

    pos: int
    section: Optional[SectionBlock] = None
    region: str = ""

    @property
    def text(self) -> str:
        return ""


@dataclass
class Para(Block):
    """A <para>. `marker` is the paragroup number that precedes it ('1.1.'),
    recorded separately so text stays close to actual XML text while Markdown
    can render the number."""

    runs: list[Run] = field(default_factory=list)
    marker: str = ""

    @property
    def text(self) -> str:
        return runs_text(self.runs)


@dataclass
class Heading(Block):
    """A heading line: the title of a section or a standalone <bridgehead>.
    `text` is the heading text only (first visual line, number stripped)
    `number` is the title <nr> as an int when they're present."""

    runs: list[Run] = field(default_factory=list)
    kind: str = "title"  # 'title' | 'bridgehead'
    heading_text: str = ""
    number: Optional[int] = None
    role: str = ""  # bridgehead role, if any

    @property
    def text(self) -> str:
        return self.heading_text


@dataclass
class ListItem:
    """One <listitem> and content is a list of blocks (usually Para)."""

    blocks: list[Block] = field(default_factory=list)


@dataclass
class List(Block):
    """An <itemizedlist> (bullets) or <orderedlist>. `style` is the ordered
    `numeration` (arabic/loweralpha/lowerroman/upperalpha). `mark` is the bullet
    glyph for itemized lists."""

    ordered: bool = False
    style: str = ""  # numeration for ordered lists
    mark: str = "-"  # bullet glyph for itemized lists
    items: list[ListItem] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _norm(" ".join(blocks_text(it.blocks) for it in self.items))


@dataclass
class Cell:
    """A table <entry>. `span` is how many columns it covers. Note GFM can't
    do span, so on rendering we emit the cell once and pad the rest empty."""

    blocks: list[Block] = field(default_factory=list)
    span: int = 1


@dataclass
class Row:
    cells: list[Cell] = field(default_factory=list)


@dataclass
class Table(Block):
    """An <informaltable>. Rendered as a GFM table; the first row is treated as
    the header (the source only has <tbody> and for MD we need a header)."""

    rows: list[Row] = field(default_factory=list)
    ncols: int = 0

    @property
    def text(self) -> str:
        cells = [
            t
            for row in self.rows
            for cell in row.cells
            if (t := blocks_text(cell.blocks))
        ]
        return _norm(" ".join(cells))


@dataclass
class Image(Block):
    """A block-level <mediaobject>. Explicitly dropped, like InlineImage: kept
    as a defined type so it is accounted for rather than an unknown tag."""

    @property
    def text(self) -> str:
        return ""


@dataclass
class Footnote:
    """A <footnote>, collected document-wide. `label` is the marker shown in the
    body. Its content is a list of blocks."""

    label: str
    id: str = ""
    blocks: list[Block] = field(default_factory=list)

    @property
    def text(self) -> str:
        return blocks_text(self.blocks)


@dataclass
class Document:
    """The parsed result: the flat top-level block stream, the structural
    sections, and the document-wide footnotes (keyed by label)."""

    blocks: list[Block] = field(default_factory=list)
    sections: list[SectionBlock] = field(default_factory=list)
    footnotes: dict[str, Footnote] = field(default_factory=dict)
    ecli: str = ""
