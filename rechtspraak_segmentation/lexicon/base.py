"""The Lexicon type: a court's controlled vocabulary and label rules.

The matching algorithm is identical across courts. First matching ordered rule
wins for labelling; a heading must be a short line whose every word is in a
closed vocabulary. Only the data differs per court.
So a Lexicon is a frozen bundle of that data plus the shared methods; concrete
courts are instances (see rechtbank.py), not subclasses.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .text import (
    collapse_spaced_caps,
    strip_leading_enum,
    strip_parentheticals,
    word_tokens,
)

# Default role -> label fallback for structured <section> containers whose own
# title is uninformative. Rechtspraak applies `role` coarsely, so it is only a
# last resort behind the title (see detect_structured).
_DEFAULT_ROLE_FALLBACK = frozenset(
    {"procesverloop", "overwegingen", "beslissing"}
)

# Gates for the controlled heading language
_MAX_HEADING_CHARS = 100
_MAX_HEADING_WORDS = 16

# Default for the optional "narrative facts": matches nothing
_NEVER = re.compile(r"(?!x)x")

# A bare statute citation as a standalone title ("Artikel 4") is embedded law,
# not a logical section boundary.
_STATUTE_CITE_RE = re.compile(
    r"^\s*(de\s+|het\s+)?(artikel|art\.?|§)\s*\d", re.I
)

# A geschil heading that refers to first-instance proceedings is kept as
# geschil even inside the reasoning region, not absorbed as overwegingen.
_FIRST_INSTANCE_RECAP_RE = re.compile(
    r"geschil.{0,40}(eerste\s+aanleg|eerste\s+instantie|"
    r"van\s+de\s+(rechtbank|kantonrechter))",
    re.I,
)

# The dictum heading is sometimes followed by its operative sentence
# ("Het hof, recht doende ..."), which also passes the beslissing label gate.
_DICTUM_SENTENCE_RE = re.compile(
    r"(recht\s*doende|^\s*(het\s+hof|het\s+gerechtshof|de\s+rechtbank|"
    r"de\s+kantonrechter|de\s+voorzieningenrechter)\b)",
    re.I,
)


class UnknownCourtError(ValueError):
    """The ECLI court code maps to no segmentation lexicon (e.g PHR)."""


@dataclass(frozen=True)
class Lexicon:
    name: str
    # Ordered (label, pattern); first whose pattern matches a line wins.
    label_rules: tuple[tuple[str, re.Pattern], ...]
    # Closed "heading language": determiners, qualifiers and section keywords
    heading_vocab: frozenset[str]
    # Oblique factual openers ("De kern van de zaak") used only as a fallback
    oblique_feiten: re.Pattern
    role_fallback: frozenset[str] = field(default=_DEFAULT_ROLE_FALLBACK)
    # Narrative-facts subset ("Wat is er gebeurd") preferred over summary/intro
    # openers ("De kern van de zaak", "Inleiding") when both are present
    oblique_feiten_strong: re.Pattern = field(default=_NEVER)
    # When True, the reasoning region absorbs the per grief sub-sections that
    # the (flat) markup strands after the "De beoordeling" heading. This is
    # mainly prevelent for GH and improves segmentation precision.
    region_overwegingen: bool = False
    # Recap titles that might name beslissing but are NOT it ("De kern van de
    # zaak en de beslissing van het hof" is an up-front summary). When this
    # matches a <section> title it is forced to 'overig', overriding both the
    # "beslissing" keyword and a role="beslissing" container.
    recap_overig: re.Pattern = field(default=_NEVER)
    # Document-header captions that happen to contain a section keyword.
    # Forced to overig so the caption drop removes it and the real
    # "Het geding" actually opens procesverloop.
    caption_overig: re.Pattern = field(default=_NEVER)
    # A sub-numbered facts recital embedded in the reasoning ("3.1 In cassatie
    # kan ... worden uitgegaan").
    embedded_feiten: re.Pattern = field(default=_NEVER)
    # Statute citation as a standalone section title: embedded quoted law, not a
    # logical boundary (e.g. "Artikel 4" inside a factual recital).
    statute_cite: re.Pattern = field(default=_STATUTE_CITE_RE)
    # Geschil title that names first-instance proceedings: kept as geschil
    # rather than absorbed as overwegingen inside the reasoning region.
    first_instance_recap: re.Pattern = field(default=_FIRST_INSTANCE_RECAP_RE)
    # Operative dictum sentence ("Het hof, recht doende ...") that also passes
    # the beslissing label gate but is not itself a heading.
    dictum_sentence: re.Pattern = field(default=_DICTUM_SENTENCE_RE)

    def label(self, text: str) -> str:
        """Map a heading line to a canonical label, else 'overig'."""
        s = text.strip()
        for lbl, pattern in self.label_rules:
            if pattern.search(s):
                return lbl
        return "overig"

    def heading_label(self, text: str) -> Optional[str]:
        """The section label if text is a stand-alone heading in the
        controlled heading language, else None. The line must be short,
        AND map to a known section label, AND consist only of closed-
        vocabulary words."""
        t = strip_leading_enum(collapse_spaced_caps(text)).strip()
        if not t or len(t) > _MAX_HEADING_CHARS:
            return None
        # Drop parenthetical qualifiers for BOTH the label and the vocabulary
        # check, so a heading like "Feiten (alles kort samengevat ...)" is
        # judged on "Feiten" alone.
        bare = strip_parentheticals(t)
        words = word_tokens(bare.lower())
        if not words or len(words) > _MAX_HEADING_WORDS:
            return None
        label = self.label(bare)
        if label == "overig":
            return None
        if any(w not in self.heading_vocab for w in words):
            return None
        return label

    def is_oblique_feiten(self, text: str) -> bool:
        """Checks whether `text` is an oblique facts opener used as fallback."""
        return bool(self.oblique_feiten.search(text or ""))

    def is_narrative_feiten(self, text: str) -> bool:
        """Checks if `text` is a narrative facts opener."""
        return bool(self.oblique_feiten_strong.search(text or ""))
