"""Rechtspraak XML to typed-block parser.

build_document function walks `<uitspraak>` once and converts every
element into a block (see blocks.py), which abstracts away from XML but keeping
the meaningful structure. Every tag that occurs under <uitspraak> is handled
explicitly, it's mapped to a block or discarded explicitly and any tag the
parser does not recognise raises `UnregisteredElementError`.
"""

from .blocks import (
    Block,
    Break,
    Cell,
    Document,
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
    SectionBlock,
    Table,
    TextRun,
)
from .xmlutil import local_tag

# linebreaks become a sentinel inside the flattened title so title_text can
# split on visual lines.
_LINEBREAK = "\x00"

# Tags consumed by their parent (never reached as a standalone block) or that
# carry no flowing content of their own. Listed so the dispatch stays explicit.
_CONSUMED = {"nr", "title", "colspec", "tgroup", "tbody"}

# Inline element tags allowed inside a <para>/<title> run stream.
_INLINE = {"emphasis", "footnote-ref", "inlinemediaobject"}


class UnregisteredElementError(NotImplementedError):
    """An element under <uitspraak> has no registered block mapping. Raised so
    unknown markup is found, not silently dropped. Subclasses
    NotImplementedError so the batch CLI already treats it as per-document."""

    def __init__(self, tag: str, ecli: str = ""):
        self.tag = tag
        self.ecli = ecli
        super().__init__(
            f"unregistered element <{tag}>" + (f" in {ecli}" if ecli else "")
        )


class _Builder:
    """Holds the per-document context while walking the tree: the document-order
    index, the footnote table, and a stack of pending paragroup numbers."""

    def __init__(self, uitspraak, ecli: str):
        self.ecli = ecli
        self.order = {el: i for i, el in enumerate(uitspraak.iter())}
        self.footnotes: dict[str, Footnote] = {}  # keyed by label (GFM marker)
        self._by_id: dict[str, Footnote] = {}  # keyed by id, for ref resolution
        self.doc = Document(ecli=ecli)

    def pos(self, el) -> int:
        return self.order.get(el, -1)

    def fail(self, tag: str):
        raise UnregisteredElementError(tag, self.ecli)

    def runs(self, el, brk_value: str = " ") -> list[Run]:
        """Flatten an element's inline content into runs. `brk_value` lets the
        title path keep a sentinel for visual-line splitting."""
        out: list[Run] = []
        if el.text:
            out.append(TextRun(el.text))
        for child in el:
            tag = local_tag(child)
            if not isinstance(child.tag, str):  # processing instruction
                if getattr(child, "target", None) == "linebreak":
                    out.append(
                        TextRun(brk_value) if brk_value != " " else Break()
                    )
            elif tag == "emphasis":
                out.append(self._emph(child))
            elif tag == "footnote-ref":
                out.append(self._footnote_ref(child))
            elif tag == "inlinemediaobject":
                out.append(InlineImage())
            elif tag == "nr":
                # A <title>'s number sits inline
                out.extend(self.runs(child, brk_value))
            else:
                self.fail(tag)
            if child.tail:
                out.append(TextRun(child.tail))
        return out

    def _emph(self, el) -> Emph:
        return Emph(
            role=el.get("role", ""),
            children=self.runs(el),
            pos=self.pos(el),
            starts_line=_starts_line(el),
        )

    def _footnote_ref(self, el) -> FootnoteRef:
        linkend = el.get("linkend", "")
        # Resolve to the footnote's own label. Fall back to the linkend.
        fn = self._by_id.get(linkend)
        label = fn.label if fn is not None else linkend
        return FootnoteRef(label=label, linkend=linkend)

    # -- headings -------------------------------------------------------- #
    def _nr_int(self, parent) -> int | None:
        nr = _child(parent, "nr")
        if nr is not None and nr.text:
            try:
                return int(nr.text.strip().rstrip("."))
            except ValueError:
                return None
        return None

    def _title(self, title_el, section: SectionBlock | None) -> Heading:
        runs = self.runs(title_el, brk_value=_LINEBREAK)
        return Heading(
            pos=self.pos(title_el),
            section=section,
            runs=runs,
            kind="title",
            heading_text=_first_line(runs, _nr_text(title_el)),
            number=self._nr_int(title_el),
        )

    def _bridgehead(self, el, section, region) -> Heading:
        runs = self.runs(el)
        return Heading(
            pos=self.pos(el),
            section=section,
            region=region,
            runs=runs,
            kind="bridgehead",
            heading_text=_runs_first_line(runs),
            role=el.get("role", ""),
        )


def _child(el, name: str):
    from .xmlutil import find_child

    return find_child(el, name)


def _nr_text(title_el) -> str:
    nr = _child(title_el, "nr")
    return (nr.text or "").strip().rstrip(".") if nr is not None else ""


def _starts_line(el) -> bool:
    """Whether `el` opens a visual line: preceded by a linebreak PI, or the
    first child of its parent with no leading text."""
    prev = el.getprevious()
    if prev is not None and not isinstance(prev.tag, str):
        return (
            getattr(prev, "target", None) == "linebreak"
            and not (prev.tail or "").strip()
        )
    p = el.getparent()
    return (
        p is not None and len(p) and p[0] is el and not (p.text or "").strip()
    )


def _first_line(runs: list[Run], nr: str) -> str:
    """First non-empty visual line of a <title>, with a leading bare number
    stripped."""
    text = "".join(
        r.value if isinstance(r, TextRun) else r.text() for r in runs
    )
    for i, line in enumerate(text.split(_LINEBREAK)):
        line = " ".join(line.split())
        if i == 0 and nr and line.startswith(nr):
            line = line[len(nr) :].lstrip(". ").strip()
        if line:
            return line
    return ""


def _runs_first_line(runs: list[Run]) -> str:
    return " ".join("".join(r.text() for r in runs).split())


def build_document(uitspraak, ecli: str = "") -> Document:
    """Parse one `<uitspraak>` element into a Document of typed blocks."""
    b = _Builder(uitspraak, ecli)
    # Footnotes are collected first so inline refs can resolve to their labels.
    _collect_footnotes(b, uitspraak)
    b.doc.blocks = _emit(b, uitspraak, section=None, region="")
    b.doc.footnotes = b.footnotes
    return b.doc


def _collect_footnotes(b: _Builder, uitspraak) -> None:
    for el in uitspraak.iter():
        if local_tag(el) == "footnote":
            label = el.get("label") or el.get("id") or str(len(b.footnotes) + 1)
            fn = Footnote(label=label, id=el.get("id", ""))
            fn.blocks = _emit(b, el, section=None, region="")
            b.footnotes[label] = fn  # keyed by label for serialization
            if el.get("id"):
                b._by_id[el.get("id")] = fn  # keyed by id for ref resolution


def _emit(b: _Builder, parent, section, region) -> list[Block]:
    """Walk the block-level children of `parent`, returning the flat block
    stream. Transparent containers (parablock/paragroup) are dissolved.
    Note the paragroup <nr> is attached as a marker to the first block."""
    out: list[Block] = []

    for el in parent:
        tag = local_tag(el)
        if not isinstance(el.tag, str):
            continue  # comment or PI at block level: no flowing content
        if tag in ("footnote",):
            continue  # collected separately, not part of the flow
        if tag == "para":
            out.append(
                Para(
                    pos=b.pos(el),
                    section=section,
                    region=region,
                    runs=b.runs(el),
                )
            )
        elif tag == "parablock":
            out.extend(_emit(b, el, section, region))
        elif tag == "paragroup":
            sub = _emit(b, el, section, region)
            nr = _child(el, "nr")
            if nr is not None and (nr.text or "").strip():
                # Attach the paragroup number ("1.1.") to the first paragraph
                # beneath it that has no marker yet.
                marker = " ".join((nr.text or "").split())
                for blk in sub:
                    if isinstance(blk, Para) and not blk.marker:
                        blk.marker = marker
                        break
            out.extend(sub)
        elif tag == "bridgehead":
            out.append(b._bridgehead(el, section, region))
        elif tag in ("itemizedlist", "orderedlist"):
            out.append(_list(b, el, section, region))
        elif tag == "informaltable":
            out.append(_table(b, el, section, region))
        elif tag == "mediaobject":
            out.append(Image(pos=b.pos(el), section=section, region=region))
        elif tag == "section":
            out.extend(_section(b, el, section))
        elif tag == "uitspraak.info":
            out.extend(_emit(b, el, section, region="info"))
        elif tag in _CONSUMED:
            continue
        else:
            b.fail(tag)
    return out


def _section(b: _Builder, el, parent_section) -> list[Block]:
    sec = SectionBlock(
        pos=b.pos(el), role=el.get("role", ""), parent=parent_section
    )
    title_el = _child(el, "title")
    if title_el is not None:
        sec.title = b._title(title_el, sec)
    b.doc.sections.append(sec)
    blocks: list[Block] = []
    if sec.title is not None:
        blocks.append(sec.title)
    blocks.extend(_emit(b, el, section=sec, region=""))
    return blocks


def _list(b: _Builder, el, section, region) -> List:
    ordered = local_tag(el) == "orderedlist"
    lst = List(
        pos=b.pos(el),
        section=section,
        region=region,
        ordered=ordered,
        style=el.get("numeration", "") if ordered else "",
        mark=el.get("mark", "-") if not ordered else "-",
    )
    for item_el in el:
        if local_tag(item_el) != "listitem":
            if isinstance(item_el.tag, str):
                b.fail(local_tag(item_el))
            continue
        lst.items.append(ListItem(blocks=_emit(b, item_el, section, region)))
    return lst


def _table(b: _Builder, el, section, region) -> Table:
    table = Table(pos=b.pos(el), section=section, region=region)
    ncols = 0
    for row_el in el.iter():
        if local_tag(row_el) != "row":
            continue
        row = Row()
        for entry in row_el:
            if local_tag(entry) != "entry":
                if isinstance(entry.tag, str):
                    b.fail(local_tag(entry))
                continue
            row.cells.append(
                Cell(blocks=_emit(b, entry, section, region), span=_span(entry))
            )
        ncols = max(ncols, sum(c.span for c in row.cells))
        table.rows.append(row)
    table.ncols = ncols
    return table


def _span(entry) -> int:
    """Column span of a table <entry>."""
    start, end = entry.get("namest"), entry.get("nameend")
    if not start or not end:
        return 1
    digits = "".join(ch for ch in start if ch.isdigit())
    edigits = "".join(ch for ch in end if ch.isdigit())
    if digits and edigits:
        return max(1, int(edigits) - int(digits) + 1)
    return 1
