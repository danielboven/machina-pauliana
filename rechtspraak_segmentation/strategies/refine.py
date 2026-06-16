"""Turning candidate headings into a clean, closed list of sections.

After a detector (headings.py) fires, three kinds of refinement pass run:

recover_*         add headings the chosen detector could not see (a bold Emph
                  run, an unnumbered opener in the preamble, an unnumbered
                  reasoning/dictum heading). All read the same candidate_lines.
drop_* / absorb_* delete quoted/caption noise and re-unite the court
                  reasoning that flat markup scatters
close_boundaries  sort, and span every section to just before the next

Vocabulary calls are delegated to the Lexicon. Closed-vocabulary heading
language (lex.heading_label) is what keeps recovery from giving false-positives.
"""

import re

from ..core.blocks import (
    Break,
    Emph,
    Para,
    SectionBlock,
    blocks_text,
    iter_blocks,
)
from ..core.model import CANON_LABELS, Section
from .headings import NUMBERED_HEADING_RE, SUBNUMBER_RE

# Sentinel for when document index (pos) is not set, use as fallback
BIG = 1 << 30


def _pos(s) -> int:
    """Document-order index of a section's boundary, BIG when unset."""
    return s.pos if s.pos >= 0 else BIG


def recover_emphasis(lines, sections, lex):
    """Recover a heading the markup buries inside a <para> as a bold/underline
    Emph run on its own line. Line breaks are processing instructions dropped by
    text extraction, so the flat <para> text glues such a heading to the
    surrounding text and the detectors miss it.
    """
    present = {s.label for s in sections}
    extra = []
    for ln in lines:
        if not ln.emphasis:
            continue
        label = lex.heading_label(ln.text)
        if label is not None and label not in present:
            extra.append(
                Section(label, ln.text, ln.element, strategy="emphasis")
            )
            present.add(label)
    return extra


def recover_leading(lines, sections, lex):
    """Recover an unnumbered opener ("PROCESGANG", "De vaststaande feiten", and
    for GH "De grieven"/"De beoordeling") sitting in the preamble before the
    numbering starts, where the numbered/section detectors can't see it. Looks
    ahead of the first section and fills only a missing label."""
    first_canon = min(
        (_pos(s) for s in sections if s.label in CANON_LABELS),
        default=min((_pos(s) for s in sections), default=BIG),
    )
    wanted = {"procesverloop", "feiten"}
    if getattr(lex, "region_overwegingen", False):
        wanted |= {"geschil", "overwegingen"}
    present = {s.label for s in sections}
    extra = []
    for ln in lines:
        if ln.emphasis or ln.pos >= first_canon:
            continue
        label = lex.heading_label(ln.text)
        if label in wanted and label not in present:
            extra.append(
                Section(label, ln.text, ln.element, strategy="leading-head")
            )
            present.add(label)
    return extra


def recover_reasoning_opener(lines, sections, lex):
    """Hof only: recover an unnumbered reasoning opener ("De beoordeling van het
    hoger beroep") that numbered-para missed, so the region pass can fold the
    per-grief siblings into it.
    This is a tighter scope, only when no overwegingen exists and only over
    clean headings so it cant over-segment."""
    if not getattr(lex, "region_overwegingen", False):
        return []
    if any(s.label == "overwegingen" for s in sections):
        return []
    have = {id(s.element) for s in sections}
    extra = []
    for ln in lines:
        if ln.emphasis or ln.tag not in ("para", "title", "bridgehead"):
            continue
        if id(ln.element) in have:
            continue
        if lex.heading_label(ln.text) == "overwegingen":
            extra.append(
                Section("overwegingen", ln.text, ln.element, strategy="keyword")
            )
            have.add(id(ln.element))
    return extra


def recover_dictum_tail(lines, sections, lex):
    """A vonnis always closes with a dictum. If no beslissing was found, catch a
    trailing dictum heading ("De beslissing", "Rechtdoende") at the end of the
    document, as the numbering often stops before the unnumbered dictum.
    Prefer the first that is a clean heading over the operative sentence."""
    if any(s.label == "beslissing" for s in sections):
        return []
    last_start = max((s.pos for s in sections), default=-1)
    cands = [
        ln
        for ln in lines
        if ln.tag in ("para", "title", "bridgehead")
        and ln.pos > last_start
        and lex.heading_label(ln.text) == "beslissing"
    ]
    if not cands:
        return []
    pure = [ln for ln in cands if not lex.dictum_sentence.search(ln.text)]
    hit = pure[0] if pure else cands[-1]
    return [
        Section("beslissing", hit.text, hit.element, strategy="dictum-tail")
    ]


def _embedded_subnumber(line):
    """Structured docs can carry a subnumber on a paragroup (`Para.marker` ==
    "3.1"); older flat docs print it at the front of the line text instead.
    None when the line carries no sub-number."""
    src = getattr(line.element, "marker", "") or line.text
    m = re.match(r"\s*(\d+)\.(\d+)", src)
    return (int(m.group(1)), int(m.group(2))) if m else None


def recover_embedded_feiten(lines, sections, lex):
    """HR only: get the facts enumeration that hides as a sub-numbered item
    ("3.1 In cassatie kan ... worden uitgegaan") inside the reasoning. The Hoge
    Raad notes the relevant facts under "3. Beoordeling van het middel" as
    item 3.1. The next paragraphs (3.2 the claim, 3.3+ the assessment) lack a
    reliable boundary, so only the facts are recovered, and only when no feiten
    section exists yet."""
    if any(s.label == "feiten" for s in sections):
        return []
    reasoning = min(
        (_pos(s) for s in sections if s.label == "overwegingen"),
        default=BIG,
    )
    opener = next(
        (
            ln
            for ln in lines
            if ln.pos > reasoning
            and lex.embedded_feiten.search(ln.text)
            and _embedded_subnumber(ln) is not None
        ),
        None,
    )
    if opener is None:
        return []
    # The facts run until the next sibling item (3.1 -> 3.2)
    # Re-opening overwegingen from there.
    major, minor = _embedded_subnumber(opener)
    next_item = re.compile(rf"^\s*{major}\.{minor + 1}(?!\d)")

    def at_next_item(ln) -> bool:
        return bool(
            next_item.match(getattr(ln.element, "marker", "") or ln.text)
        )

    closer = next(
        (ln for ln in lines if ln.pos > opener.pos and at_next_item(ln)),
        None,
    )
    if closer is None:
        return []
    return [
        Section(
            "feiten", opener.text, opener.element, strategy="embedded-feiten"
        ),
        Section(
            "overwegingen",
            closer.text,
            closer.element,
            strategy="embedded-feiten",
        ),
    ]


# A heading where the reasoning resumes after embedded facts
_RESUME_LABELS = ("overwegingen", "geschil", "procesverloop")


def _resumes_reasoning(line, lex) -> bool:
    """A buried emphasis run that reads as the heading where the court picks the
    reasoning back up: a short section-keyword line, not a long sentence.
    Also means a heading should not have punctuation"""
    t = line.text.strip()
    return (
        line.emphasis
        and len(t) <= 90
        and t[-1] not in ".:;!?\"'’"
        and lex.label(t) in _RESUME_LABELS
    )


def _interrupts_reasoning(s, lex) -> bool:
    """True when the section sits inside the reasoning region but is not
    absorbed by it a feiten recital or a first-instance geschil recap and can
    therefore leave the court's own reasoning stranded after it."""
    return s.label == "feiten" or (
        s.label == "geschil"
        and lex.first_instance_recap.search(s.raw_title or "")
    )


def recover_region_resumption(lines, sections, lex):
    """Hof region only: open reasoning again after an embedded section.

    The markup buries the feiten (or a restated first-instance geschil) inside
    the "De beoordeling" <section> as a bold <emphasis>.
    recover_emphasis opens it, but the reasoning that resumes lower down is
    another buried emphasis the detectors can no longer relabel (overwegingen
    is already open), so the recital body runs on to the dictum.
    """
    if not getattr(lex, "region_overwegingen", False):
        return []
    ordered = sorted(sections, key=_pos)
    first_overwegingen = min(
        (_pos(s) for s in ordered if s.label == "overwegingen"), default=BIG
    )
    out = []
    for i, s in enumerate(ordered):
        if _pos(s) < first_overwegingen or not _interrupts_reasoning(s, lex):
            continue
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        if nxt is not None and nxt.label != "beslissing":
            continue
        end = _pos(nxt) if nxt is not None else BIG
        resume = next(
            (
                ln
                for ln in lines
                if _pos(s) < ln.pos < end and _resumes_reasoning(ln, lex)
            ),
            None,
        )
        if resume is not None:
            out.append(
                Section(
                    "overwegingen",
                    resume.text,
                    resume.element,
                    strategy="region-resume",
                )
            )
    return out


def refine_structured(doc, sections, lex) -> list[Section]:
    """Split a structured <section> where it hides a logical section the markup
    never broke out (e.g. a bold "4. De beoordeling" inside the <section> titled
    3, its dirty data). Look inside each numbered <section> for a clean heading
    whose major number exceeds the section's own and is not yet a <section>."""
    extra = []
    known_majors = {s.number for s in sections if s.number is not None}
    paras = [b for b in iter_blocks(doc.blocks) if isinstance(b, Para)]
    for s in sections:
        base = s.number
        if base is None or not isinstance(s.element, SectionBlock):
            continue
        for para in (p for p in paras if p.section is s.element):
            text = para.text
            if not text or len(text) > 100 or SUBNUMBER_RE.match(text):
                continue
            m = NUMBERED_HEADING_RE.match(text)
            if not m:
                continue
            major = int(m.group(1))
            label = lex.label(m.group(2))
            if major <= base or major in known_majors or label == "overig":
                continue
            if lex.heading_label(text) is None:
                continue
            known_majors.add(major)
            extra.append(
                Section(label, text, para, number=major, strategy="embedded")
            )
    return extra


def refine_feiten(sections, lex) -> None:
    """Fallback only: if there is no explicit feiten heading, relabel an oblique
    factual heading ("De kern van de zaak", "Wat is er gebeurd?", "Inleiding")
    from overig to feiten."""
    if any(s.label == "feiten" for s in sections):
        return
    candidates = [
        s
        for s in sections
        if s.label == "overig" and lex.is_oblique_feiten(s.raw_title or "")
    ]
    if not candidates:
        return
    strong = [
        s for s in candidates if lex.is_narrative_feiten(s.raw_title or "")
    ]
    (strong or candidates)[0].label = "feiten"


def drop_caption_overig(sections) -> None:
    """A vonnis opens with a caption (court, parties, curators) before the
    procesverloop. Overig heading before the first canonical section is
    therefore often not relevant caption material."""
    first_canon = min(
        (_pos(s) for s in sections if s.label in CANON_LABELS),
        default=None,
    )
    if first_canon is None:
        return
    sections[:] = [
        s
        for s in sections
        if not (s.label == "overig" and _pos(s) < first_canon)
    ]


def drop_embedded_overig(sections, lex) -> None:
    """Merge quoted citations/enumerations back into the section that contains
    them. The factual recital often quotes a contract/statute/list with items
    that are numbered. The detector promotes such an item to a boundary
    (false positive). A numbered section is embedded content when it BOTH fails
    the clean heading-language gate AND does not advance the sequence of clean
    headings."""
    ordered = sorted(sections, key=_pos)

    def clean(s) -> bool:
        return lex.heading_label(s.raw_title) is not None

    trusted_pos_nr = [
        (_pos(s), s.number)
        for s in ordered
        if s.number is not None and clean(s)
    ]
    drop = set()
    seen_max = None
    for s in ordered:
        if s.label == "overig" and lex.statute_cite.match(s.raw_title or ""):
            drop.add(id(s))
            continue
        if s.number is not None and clean(s):
            seen_max = s.number if seen_max is None else max(seen_max, s.number)
            continue
        if s.number is None:
            continue
        pos = _pos(s)
        regression = seen_max is not None and s.number <= seen_max
        collision = any(p > pos and nr == s.number for p, nr in trusted_pos_nr)
        if regression or collision:
            drop.add(id(s))
    if drop:
        sections[:] = [s for s in sections if id(s) not in drop]


def absorb_overwegingen_region(sections, lex) -> None:
    """Re-unite the appeal reasoning that flat hof markup scatters: each grief
    is its own top-level <section>, labelling as 'overig', though it is
    logically a reasoning subsection (semi-hierarchy in textual layout that is
    not visible straight from the XML). Once an 'overwegingen' section opens,
    relabel every following overig/geschil to overwegingen up to the first
    beslissing."""
    started = False
    for s in sections:
        if not started:
            started = s.label == "overwegingen"
            continue
        if s.label == "beslissing":
            break
        if s.label == "geschil" and lex.first_instance_recap.search(
            s.raw_title or ""
        ):
            continue
        if s.label in ("overig", "geschil"):
            s.label = "overwegingen"
            s.strategy = f"{s.strategy}+region" if s.strategy else "region"


def close_boundaries(doc, sections, lex) -> list[Section]:
    """Close every boundary with one document-order interval model: a section
    spans from its own start to just before the next section's start. Runs the
    drop/absorb cleanups first, then fills body_text (plain text) and the
    body block range (Markdown)."""
    if not sections:
        return sections
    drop_caption_overig(sections)
    drop_embedded_overig(sections, lex)
    if not sections:
        return sections
    sections.sort(key=_pos)
    if getattr(lex, "region_overwegingen", False):
        absorb_overwegingen_region(sections, lex)

    # One contiguous-slice model: a section spans from its (resolved) start to
    # just before the next section's start, heading included. An Emph
    # boundary is a heading run inside a paragraph
    # _emph_slices splits that paragraph so the heading opens the new section.
    blocks, starts = _emph_slices(doc, sections)
    for i, s in enumerate(sections):
        start = starts[i]
        end = starts[i + 1] if i + 1 < len(sections) else BIG
        s.end_element = (
            sections[i + 1].element if i + 1 < len(sections) else None
        )
        s.blocks = [b for b in blocks if start <= b.pos < end]
        s.body_text = blocks_text(s.blocks)
    return sections


def _emph_slices(doc, sections):
    """Return (blocks, starts): the document block stream with each Emph
    boundary's carrier paragraph split at the heading, and the resolved
    slice-start pos for every section.

    An Emph boundary is a heading run living inside a paragraph (older flat
    docs put a bold opener at the start of a line, Structured Hof docs append
    an underlined heading after the previous line). When real text precedes
    the run it belongs to the previous section, so split the paragraph."""
    blocks = list(doc.blocks)
    starts: list[int] = []
    for s in sections:
        if not isinstance(s.element, Emph):
            starts.append(s.pos)
            continue
        carrier = next(
            (
                b
                for b in blocks
                if isinstance(b, Para) and any(r is s.element for r in b.runs)
            ),
            None,
        )
        if carrier is None:
            starts.append(s.pos)
            continue
        idx = next(i for i, r in enumerate(carrier.runs) if r is s.element)
        head = carrier.runs[:idx]
        while head and isinstance(head[-1], Break):  # drop the line separator
            head = head[:-1]
        if any(r.text().strip() for r in head):
            head_para = Para(
                pos=carrier.pos,
                section=carrier.section,
                region=carrier.region,
                runs=head,
                marker=carrier.marker,  # the paragroup number prefixes the head
            )
            tail_para = Para(
                pos=s.element.pos,
                section=carrier.section,
                region=carrier.region,
                runs=carrier.runs[idx:],
            )
            at = blocks.index(carrier)
            blocks[at : at + 1] = [head_para, tail_para]
            starts.append(s.element.pos)
        else:  # the paragraph is the heading alone: it opens the new section
            starts.append(carrier.pos)
    return blocks, starts
