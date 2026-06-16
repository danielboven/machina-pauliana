"""Shared render model: segment a document and display it in labelled sections.

Segmentation, layout and its rendering is written once here:
`doc_renderable` turns a segmented document into renderable MD using rich. Both
CLI and TUI display that same object.

Each section becomes a banner and the body serialized to Markdown, 
displayed with a colour for each section.
Footnote definitions are gathered once for the whole document and rendered
seperately somewhat like Github does (Note, there is no real support for
footnotes in rich rendering).
"""

from dataclasses import dataclass, field

from lxml import etree
from markdown_it import MarkdownIt
from rich.console import Group, RenderableType
from rich.markdown import Heading, Markdown
from rich.rule import Rule
from rich.styled import Styled
from rich.text import Text

from ..api import detect_boundaries, resolve_lexicon
from ..core.parse import build_document
from ..core.serialize import footnote_def, to_markdown
from ..core.xmlutil import doc_ecli, get_uitspraak

BIG = 1 << 30
PREAMBLE = "preamble"

# One palette, expressed as rich styles
LABEL_COLORS = {
    "procesverloop": "cyan",
    "feiten": "yellow",
    "geschil": "magenta",
    "overwegingen": "blue",
    "beslissing": "green",
    "overig": "bright_black",
    PREAMBLE: "bright_black",
}


def rich_style(label: str) -> str:
    """The rich style for a label's text (empty -> default, when unknown)."""
    return LABEL_COLORS.get(label, "")


class _BodyHeading(Heading):
    """In-body heading (a bridgehead or sub-title serialized as `## ...`).
    We discard the rich rendering and output in bold with section colour."""

    def on_enter(self, context) -> None:
        self.text = Text()
        context.enter_style("bold")


class _DocMarkdown(Markdown):
    """Markdown tuned for these judgments, used by both front-ends:
    Multiple Markdown rendering parts are turned off as plain text to Markdown
    is not escaped (this is within the goal of trying to stay close to judgement
    text). Turning these off prevents rendering problems.
    """

    elements = {**Markdown.elements, "heading_open": _BodyHeading}

    def __init__(self, markup: str, **kwargs) -> None:
        super().__init__(markup, **kwargs)
        parser = (
            MarkdownIt()
            .enable("strikethrough")
            .enable("table")
            .disable("list")
            .disable("code")
            .disable("fence")
            .disable("backticks")
        )
        self.parsed = parser.parse(markup)


@dataclass
class RenderedSection:
    """One section ready to display: its label, the banner line, and the body
    serialized to Markdown."""

    label: str
    banner: str
    body_md: str


@dataclass
class RenderedDoc:
    sections: list[RenderedSection] = field(default_factory=list)
    footnotes_md: str = ""
    meta: dict = field(default_factory=dict)


def _banner(label: str) -> str:
    """`§ SECTION`, the label for the section type."""
    return f"§ {label.upper()}"


def render_doc(xml_bytes: bytes, lexicon=None, court=None) -> RenderedDoc:
    """Segment the document and return its sections (preamble first, if any),
    the document-wide footnote definitions, and the status-bar meta."""
    root = etree.fromstring(xml_bytes)
    uitspraak = get_uitspraak(root)
    lex = resolve_lexicon(uitspraak, lexicon, court)
    doc = build_document(uitspraak, doc_ecli(root))
    sections, strategy = detect_boundaries(doc, lex)

    starts = sorted(sections, key=lambda s: s.pos)
    # The preamble ends at the first section's first block. That can precede
    # its boundary pos (an Emph heading's enclosing <para>), so cut on the
    # block slice, not s.pos, to avoid rendering the heading twice.
    first = (
        min((b.pos for b in starts[0].blocks), default=starts[0].pos)
        if starts
        else BIG
    )

    out: list[RenderedSection] = []
    preamble = [b for b in doc.blocks if b.pos < first]
    if preamble and (body := to_markdown(preamble)):
        out.append(
            RenderedSection(
                PREAMBLE, "§ (preamble — outside any boundary)", body
            )
        )
    for s in starts:
        out.append(
            RenderedSection(
                s.label,
                _banner(s.label),
                to_markdown(s.blocks),
            )
        )

    # Blank line between definitions so each renders as its own paragraph.
    footnotes_md = "\n\n".join(
        footnote_def(fn) for fn in doc.footnotes.values()
    )
    meta = {
        "strategy": strategy,
        "nsec": len(sections),
        "ecli": doc.ecli,
        "court": lex.name,
    }
    return RenderedDoc(out, footnotes_md, meta)


def document_markdown(xml_bytes: bytes, lexicon=None, court=None):
    """Returns (markdown, meta): the whole document as one labelled-Markdown
    string with a `## §LABEL` heading per section and footnote definitions at
    the end."""
    rd = render_doc(xml_bytes, lexicon, court)
    parts = []
    for sec in rd.sections:
        parts.append(
            f"## {sec.banner}\n\n{sec.body_md}"
            if sec.body_md
            else f"## {sec.banner}"
        )
    md = "\n\n".join(parts)
    if rd.footnotes_md:
        md = f"{md}\n\n---\n\n{rd.footnotes_md}"
    return md, rd.meta


def _section_renderables(sec: RenderedSection):
    """The rich renderables for one section: a bold banner then its Markdown
    body, both tinted with the label colour."""
    style = rich_style(sec.label)
    yield Text(sec.banner, style=f"bold {style}".strip())
    if sec.body_md:
        yield Styled(_DocMarkdown(sec.body_md), style)


def doc_renderable(rd: RenderedDoc) -> RenderableType:
    """The whole document as a single rich renderable: one block per section
    (banner + coloured Markdown body) followed by the footnote definitions.
    This is the one renderer both front-ends display, so they stay identical."""
    parts: list[RenderableType] = []
    for sec in rd.sections:
        parts.extend(_section_renderables(sec))
        parts.append(Text())  # blank line between sections
    if rd.footnotes_md:
        parts.append(Rule("footnotes"))
        parts.append(
            Styled(_DocMarkdown(rd.footnotes_md), rich_style("overig"))
        )
    return Group(*parts)
