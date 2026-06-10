"""Finding the lines that can open a section.

One idea spans every court era: a section boundary is a short line that reads as
a heading.

structured docs (post ~2013)  a <section>'s <title>
older flat docs               a <bridgehead>, a numbered <para> ("3. De
                              feiten"), a bare keyword <para> ("PROCESVERLOOP")
                              or a bold <emphasis> on its own line inside a
                              paragraph.

`candidate_lines` collects that uniform stream once (every <para>/<title>/
<bridgehead>, plus each line-starting <emphasis>); the era detectors below and
recovery passes in refine.py are then thin filters over it.
Deciding what a line means is left to the lexicon.
here.
"""

import re
from dataclasses import dataclass

from ..core.model import Section
from ..core.xmlutil import (
    el_text,
    find_child,
    has_section_ancestor,
    iter_tag,
    local_tag,
    title_text,
)

# Separator after the number is required but flexible: "1.De procedure",
# "1. ...", "1) ...", "1: ..." and the older without dots "1 Het verloop ..."
# all match
NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d{1,2})(?:\s*[.):]\s*|\s+)([A-ZÀ-ɏ].{1,100}?)\s*$"
)
SUBNUMBER_RE = re.compile(r"^\s*\d+\.\d+")


@dataclass
class Line:
    """A candidate heading line. tag is element's local name. emphasis is
    True for a bold/underline run that starts its own line inside a <para>."""

    element: object
    text: str
    pos: int  # document-order index
    tag: str
    emphasis: bool = False


def _starts_line(el) -> bool:
    """Checks whether `el` starts a visual line — either preceded by a
    <?linebreak?> PI, or the first child of its parent with no leading text."""
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


def candidate_lines(uitspraak) -> list[Line]:
    """Collects all candidate heading lines from `uitspraak` in document order.
    Includes <para>, <title>, <bridgehead>, and any line-starting <emphasis>."""
    out = []
    for pos, el in enumerate(uitspraak.iter()):
        tag = local_tag(el)
        if tag in ("para", "title", "bridgehead"):
            text = el_text(el)
            if text:
                out.append(Line(el, text, pos, tag))
        elif tag == "emphasis" and _starts_line(el):
            text = el_text(el)
            if text:
                out.append(Line(el, text, pos, tag, emphasis=True))
    return out


def detect_structured(uitspraak, lex) -> list[Section]:
    """Strategy 1: top-level <section> elements (non-overlapping boundaries).

    The section's own <title> is a more specific signal than role on section,
    (role is often dirty data) so trust the title whenever it yields a label
    and fall back to the role only when the title is uninformative.
    """
    out = []
    for sec in iter_tag(uitspraak, "section"):
        if has_section_ancestor(sec):
            continue  # subsection: a sub-boundary, not a top-level one
        title_el = find_child(sec, "title")
        if title_el is None:
            continue
        raw = title_text(title_el)
        if not raw:
            continue

        role = sec.get("role", "")
        title_label = lex.label(raw)
        if lex.recap_overig.search(raw) or lex.caption_overig.search(raw):
            label = "overig"
        elif title_label != "overig":
            label = title_label
        elif role in lex.role_fallback:
            label = role
        else:
            label = "overig"

        number = None
        nr_el = find_child(title_el, "nr")
        if nr_el is not None and nr_el.text:
            try:
                number = int(nr_el.text.strip())
            except ValueError:
                pass
        out.append(Section(label, raw, sec, number, strategy="section"))
    return out


def detect_bridgehead(lines, lex) -> list[Section]:
    """Strategy 2: <bridgehead> emphasis headings (top-level only). A bridgehead
    nested in a <section> is a sub-heading."""
    out = []
    for ln in lines:
        if ln.tag != "bridgehead" or has_section_ancestor(ln.element):
            continue
        if len(ln.text) > 120 or lex.caption_overig.search(ln.text):
            continue
        label = lex.label(ln.text)
        if label != "overig":
            out.append(
                Section(label, ln.text, ln.element, strategy="bridgehead")
            )
    return out


def detect_numbered(lines, lex) -> list[Section]:
    """Strategy 3: numbered <para> headings ("1. De procedure"). A line is a
    boundary only when its numbering stays roughly sequential.
    A number that regresses or jumps is almost always a quoted/enumerated body
    item and a long numbered sentence must also pass the controlled language."""
    out = []
    last_nr = 0
    for ln in lines:
        if (
            ln.tag != "para"
            or len(ln.text) > 120
            or SUBNUMBER_RE.match(ln.text)
        ):
            continue
        m = NUMBERED_HEADING_RE.match(ln.text)
        if not m:
            continue
        nr = int(m.group(1))
        label = lex.label(m.group(2))
        if len(m.group(2)) > 80 and lex.heading_label(ln.text) is None:
            continue
        if label == "overig" and nr != last_nr + 1:
            continue
        if nr < 1 or nr > last_nr + 3:
            continue
        last_nr = nr
        out.append(
            Section(
                label, ln.text, ln.element, number=nr, strategy="numbered-para"
            )
        )
    return out


def detect_keyword(lines, lex) -> list[Section]:
    """Strategy 4: flat docs with no <section>/<bridgehead>/numbering.=
    Promote any stand-alone <para> that is a heading in the controlled heading
    language. The closed-vocabulary gate helsp to prevent firing on short body
    sentences."""
    out = []
    for ln in lines:
        if ln.tag != "para" or len(ln.text) > 90:
            continue
        label = lex.heading_label(ln.text)
        if label is not None:
            out.append(Section(label, ln.text, ln.element, strategy="keyword"))
    return out
