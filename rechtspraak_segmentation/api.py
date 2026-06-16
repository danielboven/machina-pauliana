"""Public segmentation API.

    from rechtspraak_segmentation import segment
    result = segment("ECLI_NL_RBAMS_2012_xyz.xml")
    for s in result.sections:
        print(s.label, len(s.body_text))

`segment` parses one document, uses the court lexicon (strictly, from the
ECLI), runs the strategy fallback chain, and returns a SegmentationResult.
Pass raw XML bytes or a path. Can override the lexicon with `lexicon=`/`court=`.
"""

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .core.model import CANON_LABELS, Section
from .core.parse import build_document
from .core.xmlutil import doc_ecli, get_uitspraak
from .lexicon import Lexicon, get_lexicon, lexicon_for
from .strategies.headings import (
    candidate_lines,
    detect_bridgehead,
    detect_keyword,
    detect_numbered,
    detect_structured,
)
from .strategies.refine import (
    close_boundaries,
    recover_dictum_tail,
    recover_embedded_feiten,
    recover_emphasis,
    recover_leading,
    recover_reasoning_opener,
    recover_region_resumption,
    refine_feiten,
    refine_structured,
)


@dataclass
class SegmentationResult:
    sections: list[Section]
    strategy: str
    ecli: str
    court: str


def resolve_lexicon(
    uitspraak, lexicon: Lexicon = None, court: str = None
) -> Lexicon:
    """Explicit lexicon has priority, then court, finally just by ECLI."""
    if lexicon is not None:
        return lexicon
    if court is not None:
        return get_lexicon(court)
    return lexicon_for(uitspraak)


def _refine_flat(doc, lines, secs, lex) -> list[Section]:
    """Call refinement strategies for flat docs: recover the headings the chosen
    detector could not see (bold emphasis, the unnumbered opener/reasoning/
    dictum), apply the oblique-feiten fallback, then close every boundary."""
    secs += recover_emphasis(lines, secs, lex)
    secs += recover_leading(lines, secs, lex)
    secs += recover_reasoning_opener(lines, secs, lex)
    secs += recover_dictum_tail(lines, secs, lex)
    secs += recover_embedded_feiten(lines, secs, lex)
    secs += recover_region_resumption(lines, secs, lex)
    refine_feiten(secs, lex)
    return close_boundaries(doc, secs, lex)


def detect_boundaries(doc, lex: Lexicon) -> tuple[list[Section], str]:
    """Run the four detection strategies in priority order, falling back until
    one works, then call the refinement/recoveries. All strategies and
    recoveries read one stream of candidate heading lines (headings.py)."""
    lines = candidate_lines(doc)

    secs = detect_structured(doc, lex)
    # Only commit to the structured era if the <section> markup actually carries
    # content structure (>=1 actual section). Some casees wrap each caption
    # party in its own <section> (titles = party names -> all 'overig'); those
    # must fall through to the flat strategies, that works better on those.
    if any(s.label in CANON_LABELS for s in secs):
        secs += detect_bridgehead(lines, lex)
        secs += refine_structured(doc, secs, lex)
        secs += recover_emphasis(lines, secs, lex)
        secs += recover_leading(lines, secs, lex)
        secs += recover_dictum_tail(lines, secs, lex)
        secs += recover_embedded_feiten(lines, secs, lex)
        secs += recover_region_resumption(lines, secs, lex)
        refine_feiten(secs, lex)
        return close_boundaries(doc, secs, lex), "section"

    # Flat fallback: bridgehead first, accepted only if it gives >=1 section.
    secs = detect_bridgehead(lines, lex)
    if any(s.label in CANON_LABELS for s in secs):
        return _refine_flat(doc, lines, secs, lex), "bridgehead"

    # Numbered-para vs keyword. Commit to numbered-para only when the numbering
    # is the section structure (>=1 numbered line is itself a clean heading).
    # Older docs number their paragraphs, not the sections: there the numbered
    # "headings" are body sentences, and when the unnumbered headings instead
    # form a real section spine (>=3 of the canonical labels) those are used.
    numbered = detect_numbered(lines, lex)
    keyword = detect_keyword(lines, lex)
    numbered_canon = [s for s in numbered if s.label in CANON_LABELS]
    numbered_heads_sections = any(
        lex.heading_label(s.raw_title) for s in numbered_canon
    )
    keyword_spine = {s.label for s in keyword if s.label in CANON_LABELS}
    if numbered_canon and (numbered_heads_sections or len(keyword_spine) < 3):
        return _refine_flat(doc, lines, numbered, lex), "numbered-para"
    return _refine_flat(doc, lines, keyword, lex), "keyword"


def _read_bytes(source) -> bytes:
    """Helper, read source file to bytes."""
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


def segment(
    source, lexicon: Lexicon = None, court: str = None
) -> SegmentationResult:
    """Segment one document. `source` is raw XML bytes or a path to XML."""
    root = etree.fromstring(_read_bytes(source))
    uitspraak = get_uitspraak(root)
    lex = resolve_lexicon(uitspraak, lexicon, court)
    ecli = doc_ecli(root)
    doc = build_document(uitspraak, ecli)
    sections, strategy = detect_boundaries(doc, lex)
    return SegmentationResult(sections, strategy, ecli, lex.name)
