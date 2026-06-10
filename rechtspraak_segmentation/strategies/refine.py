"""Turning candidate headings into a clean, closed list of sections.

After a detector (headings.py) fires, three kinds of refinement pass run:

recover_*         add headings the chosen detector could not see (a bold
                  <emphasis>, an unnumbered opener in the preamble, unnumbered
                  reasoning/dictum heading). All read the same candidate_lines
drop_* / absorb_* delete quoted/caption noise and re-unite the court
                  reasoning that flat markup scatters
close_boundaries  sort, and span every section to just before the next

Vocabulary calls are delegated to the Lexicon. Closed-vocabulary heading
language (lex.heading_label) is what keeps recovery from giving false-positives.
"""

import re

from ..core.model import CANON_LABELS, Section
from ..core.xmlutil import el_text, iter_tag, local_tag
from .headings import NUMBERED_HEADING_RE, SUBNUMBER_RE

BIG = 1 << 30

# A bare statute citation ("Artikel 4") as a whole title is quoted
# law inside a section, not a logical section by itself
_STATUTE_CITE_RE = re.compile(
    r"^\s*(de\s+|het\s+)?(artikel|art\.?|§)\s*\d", re.I
)

# A geschil heading that refers to first instance (District Court) is also a
# geschil even inside the reasoning region (see absorb_overwegingen_region)
_FIRST_INSTANCE_RECAP = re.compile(
    r"geschil.{0,40}(eerste\s+aanleg|eerste\s+instantie|"
    r"van\s+de\s+(rechtbank|kantonrechter))",
    re.I,
)

# The dictum heading "De beslissing" is typically followed by its operative
# sentence ("Het hof, recht doende ..."), which also passes the beslissing gate
_DICTUM_SENTENCE = re.compile(
    r"(recht\s*doende|^\s*(het\s+hof|het\s+gerechtshof|de\s+rechtbank|"
    r"de\s+kantonrechter|de\s+voorzieningenrechter)\b)",
    re.I,
)


def recover_emphasis(lines, sections, lex):
    """Recover a heading the markup buries inside a <para> as a bold/underline
    <emphasis> on its own line. Line breaks are processing instructions dropped
    by text extraction, so the flat <para> text glues such a heading to the
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


def recover_leading(lines, sections, lex, order):
    """Recover an unnumbered opener ("PROCESGANG", "De vaststaande feiten", and
    for GH "De grieven"/"De beoordeling") sitting in the preamble before the
    numbering starts, where the numbered/section detectors can't see it. Looks
    ahead of the first section and fills only a missing label."""
    first_canon = min(
        (
            order.get(s.element, BIG)
            for s in sections
            if s.label in CANON_LABELS
        ),
        default=min((order.get(s.element, BIG) for s in sections), default=BIG),
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


def recover_dictum_tail(lines, sections, lex, order):
    """A vonnis always closes with a dictum. If no beslissing was found, catch a
    trailing dictum heading ("De beslissing", "Rechtdoende") at the end of the
    document, as the numbering often stops before the unnumbered dictum.
    Prefer the first that is a clean heading over the operative sentence."""
    if any(s.label == "beslissing" for s in sections):
        return []
    last_start = max((order.get(s.element, -1) for s in sections), default=-1)
    cands = [
        ln
        for ln in lines
        if ln.tag in ("para", "title", "bridgehead")
        and ln.pos > last_start
        and lex.heading_label(ln.text) == "beslissing"
    ]
    if not cands:
        return []
    pure = [ln for ln in cands if not _DICTUM_SENTENCE.search(ln.text)]
    hit = pure[0] if pure else cands[-1]
    return [
        Section("beslissing", hit.text, hit.element, strategy="dictum-tail")
    ]


def refine_structured(uitspraak, sections, lex) -> list[Section]:
    """Split a structured <section> where it hides a logical section the markup
    never broke out (e.g. a bold "4. De beoordeling" inside the <section> titled
    3, its dirty data). Look inside each numbered <section> for a clean heading
    whose major number exceeds the section's own and is not yet a <section>."""
    extra = []
    known_majors = {s.number for s in sections if s.number is not None}
    for s in sections:
        base = s.number
        if base is None or local_tag(s.element) != "section":
            continue
        for para in iter_tag(s.element, "para"):
            text = el_text(para)
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


def drop_caption_overig(sections, order) -> None:
    """A vonnis opens with a caption (court, parties, curators) before the
    procesverloop. Overig heading before the first canonical section is
    therefore often not relevant caption material."""
    # TODO check what impact would be of dropping this refinement
    first_canon = min(
        (
            order.get(s.element, BIG)
            for s in sections
            if s.label in CANON_LABELS
        ),
        default=None,
    )
    if first_canon is None:
        return
    sections[:] = [
        s
        for s in sections
        if not (s.label == "overig" and order.get(s.element, BIG) < first_canon)
    ]


def drop_embedded_overig(sections, order, lex) -> None:
    """Merge quoted citations/enumerations back into the section that contains
    them. The factual recital often quotes a contract/statute/list with items
    that are numbered. The detector promotes such an item to a boundary
    (false positive). A numbered section is embedded content when it BOTH fails
    the clean heading-language gate AND does not advance the sequence of clean
    headings."""
    ordered = sorted(sections, key=lambda s: order.get(s.element, BIG))

    def clean(s) -> bool:
        return lex.heading_label(s.raw_title) is not None

    trusted_pos_nr = [
        (order.get(s.element, BIG), s.number)
        for s in ordered
        if s.number is not None and clean(s)
    ]
    drop = set()
    seen_max = None
    for s in ordered:
        if s.label == "overig" and _STATUTE_CITE_RE.match(s.raw_title or ""):
            drop.add(id(s))
            continue
        if s.number is not None and clean(s):
            seen_max = s.number if seen_max is None else max(seen_max, s.number)
            continue
        if s.number is None:
            continue
        pos = order.get(s.element, BIG)
        regression = seen_max is not None and s.number <= seen_max
        collision = any(p > pos and nr == s.number for p, nr in trusted_pos_nr)
        if regression or collision:
            drop.add(id(s))
    if drop:
        sections[:] = [s for s in sections if id(s) not in drop]


def absorb_overwegingen_region(sections) -> None:
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
        if s.label == "geschil" and _FIRST_INSTANCE_RECAP.search(
            s.raw_title or ""
        ):
            continue
        if s.label in ("overig", "geschil"):
            s.label = "overwegingen"
            s.strategy = f"{s.strategy}+region" if s.strategy else "region"


def close_boundaries(uitspraak, sections, lex) -> list[Section]:
    """Close every boundary with one document-order interval model: a section
    spans from its own start element to just before the next section's start.
    Runs the drop/absorb cleanups first, then fills body_text."""
    if not sections:
        return sections
    order = {el: i for i, el in enumerate(uitspraak.iter())}
    drop_caption_overig(sections, order)
    drop_embedded_overig(sections, order, lex)
    if not sections:
        return sections
    sections.sort(key=lambda s: order.get(s.element, BIG))
    if getattr(lex, "region_overwegingen", False):
        absorb_overwegingen_region(sections)

    paras = iter_tag(uitspraak, "para")
    for i, s in enumerate(sections):
        start = order.get(s.element, 0)
        nxt = sections[i + 1].element if i + 1 < len(sections) else None
        end = order.get(nxt, BIG) if nxt is not None else BIG
        s.end_element = nxt
        s.body_text = " ".join(
            t
            for p in paras
            if start < order.get(p, -1) < end and (t := el_text(p))
        )
    return sections
