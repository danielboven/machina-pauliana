"""Finding the blocks that can open a section.

One idea spans every court era: a section boundary is a short block that reads
as a heading.

structured docs (post ~2013)  a <section>'s <title> (a Heading, kind='title')
older flat docs               a <bridgehead> Heading, a numbered Para ("3. De
                              feiten"), a bare keyword Para ("PROCESVERLOOP")
                              or a bold <emphasis> run starting its own line
                              inside a paragraph.

`candidate_lines` collects that uniform stream once from the typed block tree
The era detectors below and the recovery passes in refine.py are thin filters
over it. Deciding what a line means is left to the lexicon.
"""

import re
from dataclasses import dataclass

from ..core.blocks import Emph, Heading, Para, iter_blocks
from ..core.model import Section

# Separator after the number is required but flexible: "1.De procedure",
# "1. ...", "1) ...", "1: ..." and the older without dots "1 Het verloop ..."
# all match
NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d{1,2})(?:\s*[.):]\s*|\s+)([A-ZÀ-ɏ].{1,100}?)\s*$"
)
SUBNUMBER_RE = re.compile(r"^\s*\d+\.\d+")


@dataclass
class Line:
    """A candidate heading line. `element` is the block (Para/Heading) or Emph
    run it came from. Every candidate carries pos (index).
    `emphasis` is True for a bold/underline run that starts its own line."""

    element: object
    text: str
    pos: int  # document-order index
    tag: str  # 'para' | 'title' | 'bridgehead' | 'emphasis'
    emphasis: bool = False


def candidate_lines(doc) -> list[Line]:
    """Collects all candidate heading lines from `doc` in document order:
    every Para and Heading, plus any line-starting Emph run inside a Para."""
    out = []
    for b in iter_blocks(doc.blocks):
        if isinstance(b, Heading):
            if b.text:
                out.append(Line(b, b.text, b.pos, b.kind))
        elif isinstance(b, Para):
            if b.text:
                out.append(Line(b, b.text, b.pos, "para"))
            for run in b.runs:
                if isinstance(run, Emph) and run.starts_line and run.text():
                    out.append(
                        Line(
                            run, run.text(), run.pos, "emphasis", emphasis=True
                        )
                    )
    out.sort(key=lambda ln: ln.pos)
    return out


def detect_structured(doc, lex) -> list[Section]:
    """Strategy 1: top-level <section> blocks (non-overlapping boundaries).

    The section's own <title> is a more specific signal than role on section
    (role is often dirty data) so trust the title whenever it yields a label
    and fall back to the role only when the title is uninformative.
    """
    out = []
    for sec in doc.sections:
        if sec.parent is not None:
            continue  # subsection: a sub-boundary, not a top-level one
        if sec.title is None:
            continue
        raw = sec.title.text
        if not raw:
            continue

        role = sec.role
        title_label = lex.label(raw)
        if lex.recap_overig.search(raw) or lex.caption_overig.search(raw):
            label = "overig"
        elif title_label != "overig":
            label = title_label
        elif role in lex.role_fallback:
            label = role
        else:
            label = "overig"

        out.append(
            Section(label, raw, sec, sec.title.number, strategy="section")
        )
    return out


def detect_bridgehead(lines, lex) -> list[Section]:
    """Strategy 2: <bridgehead> emphasis headings (top-level only). A bridgehead
    nested in a <section> is a sub-heading."""
    out = []
    for ln in lines:
        if ln.tag != "bridgehead" or ln.element.section is not None:
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
    """Strategy 4: flat docs with no <section>/<bridgehead>/numbering.
    Promote any stand-alone <para> that is a heading in the controlled heading
    language. The closed-vocabulary gate helps to prevent accidentally firing
    on short body sentences."""
    out = []
    for ln in lines:
        if ln.tag != "para" or len(ln.text) > 90:
            continue
        label = lex.heading_label(ln.text)
        if label is not None:
            out.append(Section(label, ln.text, ln.element, strategy="keyword"))
    return out
