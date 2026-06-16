"""Hoge Raad (Supreme Court) lexicon

Drafted from an LLM survey of the HR filtered corpus.

The cassation judgment is the cleanest of the three instances
HR does not establish facts itself, can only enumerate what was established as
facts in earlier instances.

It reuses some rechtbank heading vocabulary and oblique-feiten patterns as base,
cassation specific ones are added on top.
"""

import re

from .base import Lexicon
from .rechtbank import RECHTBANK

# ---------------------------------------------------------------------------
# Label rules (ordered: first matching pattern wins)
# ---------------------------------------------------------------------------
_LABEL_RULES = (
    # Unambiguous dictum opener, kept for consistency with the other courts.
    ("beslissing", re.compile(r"recht\s*doende", re.I)),
    # Overwegingen/Beoordeling: the Hoge Raad's reasoning on the cassation
    # grounds ("het middel"/"de middelen"), tested BEFORE procesverloop and
    # feiten so the answer to prejudicial questions ("Beantwoording van de
    # prejudiciele vragen") and ontvankelijkheid rulings are caught here, not
    # confused with "De prejudiciele procedure" (procesverloop) below.
    (
        "overwegingen",
        re.compile(
            r"(beoordeling|overwegingen|rechtsoverwegingen|motivering|"
            r"beantwoording\s+van\s+de\s+prejudici\w+\s+vragen|"
            r"oordeel\s+van\s+de\s+hoge\s+raad|"
            r"gronden\s+van\s+de\s+beslissing)",
            re.I,
        ),
    ),
    # Feiten: at the Hoge Raad the established facts return as the points of
    # departure ("Uitgangspunten (en feiten) in cassatie")
    (
        "feiten",
        re.compile(
            r"(uitgangspunten|vaststaande\s+feiten|vastgestelde\s+feiten|"
            r"\bfeiten\b|achtergrond)",
            re.I,
        ),
    ),
    # Procesverloop: the course of proceedings is split into the fact-finding
    # instances and the cassation proceedings ("Het geding in feitelijke/
    # voorgaande instanties", "Het (tweede/derde) geding in cassatie")
    (
        "procesverloop",
        re.compile(
            r"(procesverloop|\bgeding(en)?\b|"
            r"prejudici\w+\s+procedure|"
            r"(feitelijke|voorgaande)\s+instanti)",
            re.I,
        ),
    ),
    # Beslissing.
    (
        "beslissing",
        re.compile(r"(beslissing|recht\s*doende|besluit|dictum)", re.I),
    ),
)

# ---------------------------------------------------------------------------
# Controlled heading language: basis of RB and specific words for HR.
# ---------------------------------------------------------------------------
_HR_WORDS = frozenset(
    {
        # course-of-proceedings vocabulary for cassation
        "cassatie",
        "feitelijke",
        "feitelijk",
        "instantie",
        "instanties",
        "voorgaande",
        "prejudiciele",
        "prejudiciële",
        # reasoning
        "middel",
        "middelen",
        "principaal",
        "principale",
        "incidenteel",
        "incidentele",
        "voorwaardelijk",
        "voorwaardelijke",
        "ontvankelijkheid",
        "beantwoording",
        "vragen",
        # Hoge Raad named as actor inside headings
        "hoge",
        "raad",
    }
)
_HEADING_VOCAB = RECHTBANK.heading_vocab | _HR_WORDS

# HR factual openers extend RB. The classic cassation facts opener recites the
# points of departure established below ("In cassatie kan van het volgende
# worden uitgegaan", "Uitgangspunten en feiten").
# It's used as a fallback (primarily for the pre 2019 HR format).
_OBLIQUE_FEITEN_RE = re.compile(
    RECHTBANK.oblique_feiten.pattern
    + r"|in\s+cassatie\s+kan\s+.{0,40}?worden\s+uitgegaan|"
    r"uitgangspunten\s+(en\s+feiten|in\s+cassatie)",
    re.I,
)

# Both eras embed the facts as a sub-numbered item ("3.1 ...") inside "3.
# Beoordeling van het middel" rather than in a section of their own.
# It is closed at the next sibling item (3.1 -> 3.2).
# This matches the opener sentence only.
_EMBEDDED_FEITEN_RE = re.compile(
    r"in\s+cassatie\s+(kan|moet|wordt)\b.*?uitgegaan"
    r"|bij\s+de\s+beantwoording\s+van\s+de\s+prejudici\w+\s+vragen\b"
    r".*?(uitgegaan|uit\s+van).*?\bfeit",
    re.I,
)

HOGE_RAAD = Lexicon(
    name="hoge_raad",
    label_rules=_LABEL_RULES,
    heading_vocab=_HEADING_VOCAB,
    oblique_feiten=_OBLIQUE_FEITEN_RE,
    oblique_feiten_strong=RECHTBANK.oblique_feiten_strong,
    region_overwegingen=False,
    embedded_feiten=_EMBEDDED_FEITEN_RE,
)
