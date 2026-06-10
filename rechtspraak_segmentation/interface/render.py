"""Shared render model: turn a document into labelled logical lines.

Both the print (cli.py) and the curses review tool (tui.py) use this,
so the layout/colouring logic is written once here and reused.
"""

import re
from dataclasses import dataclass

from lxml import etree

from ..api import detect_boundaries, resolve_lexicon
from ..core.xmlutil import (
    doc_ecli,
    el_text,
    find_child,
    get_uitspraak,
    local_tag,
)


@dataclass
class Line:
    text: str
    label: str  # section label or 'preamble'
    kind: str  # 'banner' | 'body' | 'blank'


def render_document(xml_bytes: bytes, lexicon=None, court=None):
    """Returns (lines, meta): the full document as labelled lines in order.
    Every paragraph is tagged with its section. Section starts get a banner.
    `meta` carries strategy, counts, and ecli for the status bar."""
    root = etree.fromstring(xml_bytes)
    uitspraak = get_uitspraak(root)
    lex = resolve_lexicon(uitspraak, lexicon, court)
    sections, strategy = detect_boundaries(uitspraak, lex)

    order = {el: i for i, el in enumerate(uitspraak.iter())}

    # Resolves each section to the element where its banner should appear.
    # Structured <section> elements banner at their <title>; everything else
    # banners at the start element itself. Needed because <emphasis> markers
    # are not printable lines and would be silently skipped by the main loop.
    def marker(s):
        if local_tag(s.element) == "section":
            t = find_child(s.element, "title")
            if t is not None:
                return t
        return s.element

    starts = sorted(
        ((order[m], s) for s in sections if (m := marker(s)) in order),
        key=lambda t: t[0],
    )
    marker_ids = {id(marker(s)) for s in sections}

    printable = sorted(
        (
            (order[el], el)
            for el in uitspraak.iter()
            if local_tag(el) in {"para", "title", "bridgehead"}
        ),
        key=lambda t: t[0],
    )

    lines: list[Line] = []
    current = None
    saw_preamble = False

    def open_section(s):
        nonlocal current
        if lines:
            lines.append(Line("", s.label, "blank"))
        head = s.raw_title.strip()
        if s.number is not None and not re.match(r"^\s*\d", head):
            head = f"{s.number}. {head}"
        lines.append(Line(f"§ {s.label.upper()}  —  {head}", s.label, "banner"))
        current = s

    si = 0
    for pos, el in printable:
        # Open every section whose marker is at or before this element. An
        # <emphasis> marker sorts just after its containing <para>, so that para
        # closes the previous section.
        while si < len(starts) and starts[si][0] <= pos:
            open_section(starts[si][1])
            si += 1
        if id(el) in marker_ids:
            continue
        txt = el_text(el)
        if not txt:
            continue
        if current is None:
            if not saw_preamble:
                lines.append(
                    Line(
                        "(preamble — outside any boundary)",
                        "preamble",
                        "banner",
                    )
                )
                saw_preamble = True
            lines.append(Line(txt, "preamble", "body"))
        else:
            lines.append(Line(txt, current.label, "body"))

    # Trailing sections whose marker sits past the last printable element (eg
    # bare dictum heading at the very end) still get the banner.
    while si < len(starts):
        open_section(starts[si][1])
        si += 1

    meta = {
        "strategy": strategy,
        "nsec": len(sections),
        "ecli": doc_ecli(root),
        "court": lex.name,
    }
    return lines, meta


def wrap_lines(lines: list[Line], width: int) -> list[Line]:
    """Wraps body lines at `width` characters.
    Banners and blanks pass through."""
    out = []
    for ln in lines:
        if ln.kind != "body" or len(ln.text) <= width:
            out.append(ln)
            continue
        cur = ""
        for w in ln.text.split():
            if cur and len(cur) + len(w) + 1 > width:
                out.append(Line(cur, ln.label, "body"))
                cur = w
            else:
                cur = f"{cur} {w}" if cur else w
        if cur:
            out.append(Line(cur, ln.label, "body"))
    return out
