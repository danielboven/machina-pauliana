"""Gerechtshof (Court of Appeal) lexicon

Drafted from an LLM survey of the GH filtered corpus.

It reuses the rechtbank heading vocabulary and oblique-feiten patterns as base,
since the function words and the oblique facts openers ("De kern van de zaak",
"Waar gaat deze zaak over?") are shared.
"""

import re

from .base import Lexicon
from .rechtbank import RECHTBANK

# ---------------------------------------------------------------------------
# Label rules (ordered: first matching pattern wins)
# ---------------------------------------------------------------------------
_LABEL_RULES = (
    # TODO check the ones below why are these here when its regex is also included below?
    # Unambiguous dictum opener, as in rechtbank
    ("beslissing", re.compile(r"recht\s*doende", re.I)),
    # TODO same for here
    # "Feiten" and "Inleiding" is considered feiten unambiguously.
    ("feiten", re.compile(r"^\s*inleiding\b", re.I)),
    # Overwegingen/Beoordeling: reasoning by court. More variations of it listed
    # in the regex below.
    # An eiswijziging is ruled on by the hof, so it is considered reasoning too.
    (
        "overwegingen",
        re.compile(
            r"(beoordeling|overwegingen|rechtsoverwegingen|motivering|"
            r"(behandeling|bespreking)\s+van\s+(het\s+hoger\s+beroep|"
            r"(?:de\s+)?(?:\([^)]*\)\s+|\w+\s+){0,3}grieven)|"
            r"toelichting\s+op\s+(de\s+|het\s+)?(beslissing|oordeel)|"
            r"eiswijziging|wijziging\s+van\s+(de\s+)?eis|"
            r"gronden\s+van\s+de\s+beslissing|"
            r"oordeel\s+van\s+het\s+hof)",
            re.I,
        ),
    ),
    # Full facts label rules, substance is before procedure, primarily because
    # the outrank ensures facts get captured with higher precision which can
    # help to improve RAG later.
    # It excludes feitelijke instantie, that is lower court reference.
    (
        "feiten",
        re.compile(
            r"(vaststaande\s+feiten|vastgestelde\s+feiten|\bfeiten\b|"
            r"feitelijk(?!e\s+instanti)|"
            r"uitgangspunten|achtergrond)",
            re.I,
        ),
    ),
    # Geschil, often named Grief/Grieven in Court of Appeal docs.
    (
        "geschil",
        re.compile(
            r"(grieven|grief|"
            r"gronden\s+van\s+het\s+(hoger\s+)?beroep|"
            r"geschil|vordering|verzoek(?:en|schrift)?\b|verweer|standpunt|stellingen|"
            r"(oordeel|beslissing(?:en)?)\s+van\s+de\s+"
            r"(rechtbank|kantonrechter|voorzieningenrechter)|"
            r"omvang\s+van\s+(het\s+)?(geschil|appel)|"
            r"inzet|verzet)",
            re.I,
        ),
    ),
    # Procesverloop, often called geding for GH. Sometimes also referring to
    # District Court decision such as "Tussenvonnis ...", which are also caught.
    (
        "procesverloop",
        re.compile(
            r"(procesverloop|(verdere\s+)?procesgang|"
            r"(verloop|voortzetting)\s+van\s+(de|het)\s+"
            r"(procedure|geding|hoger\s+beroep|appel)|"
            r"\bgeding(en)?\b|"
            r"procedure\s+(in|bij|na)\b|"
            r"^(de\s+|het\s+)?((herstel|tussen)?vonnis|tussenarrest)\b)",
            re.I,
        ),
    ),
    # Beslissing (full). GH adds "de uitspraak" and "(de) slotsom".
    (
        "beslissing",
        re.compile(
            r"(beslissing|recht\s*doende|besluit|"
            r"\bslotsom\b|\buitspraak\b|dictum)",
            re.I,
        ),
    ),
)

# ---------------------------------------------------------------------------
# Controlled heading language: the rechtbank base plus hof-specific words.
# ---------------------------------------------------------------------------
_HOF_WORDS = frozenset(
    {
        "hoger",
        "beroep",
        "appel",
        "aanleg",
        "instantie",
        "instanties",
        "eerdere",
        "verwijzing",
        "hof",
        "arrest",
        "arresten",
        "grieven",
        "grief",
        "slotsom",
        "uitspraak",
        "behandeling",
        "ontvankelijkheid",
        "omvang",
        "feitelijk",
        "feitelijke",
        "kader",
        "bespreking",
        "voortzetting",
        "na",
        # appeal scope qualifiers that occur inside the (long) reasoning titles,
        # e.g. "De beoordeling van de grieven in het principaal en het
        # incidenteel appel".
        "principaal",
        "principale",
        "incidenteel",
        "toelichting",
        "klacht",
        "klachten",
        "voorgeschiedenis",
        "schets",
        # An eiswijziging is reasoning; first-instance vonnis-milestones are
        # procedural history
        "eiswijziging",
        "wijziging",
        "eis",
        "vonnis",
        "herstelvonnis",
        "tussenvonnis",
        "tussenarrest",
        "gedingen",
    }
)
_HEADING_VOCAB = RECHTBANK.heading_vocab | _HOF_WORDS

# GH factual openers extend RB. GH sometimes uses "De voorgeschiedenis",
# "De schets van de zaak", "Waar gaat deze procedure over", so also added.
_OBLIQUE_FEITEN_RE = re.compile(
    RECHTBANK.oblique_feiten.pattern
    + r"|voorgeschiedenis|schets\s+van\s+de\s+zaak|"
    r"waar\s+(gaat\s+)?(deze|de)\s+procedure\s+over|"
    r"waarvan\s+het\s+hof\s+uitgaat",
    re.I,
)

# Titles forced to overig in detect_structured so a fallback (not their
# other keywords) governs them:
#  "De kern van de zaak en de beslissing [van het hof/de rechtbank]"
#  "Waar gaat deze zaak over?" / "Waar deze zaak over gaat, ... de grieven"
_RECAP_OVERIG_RE = re.compile(
    r"kern\s+van\s+de\s+zaak\s+en\s+de\s+beslissing|"
    r"waar\s+(gaat\s+)?(deze|de|het)\s+(zaak|procedure|kwestie)\b.{0,60}?\bover\b|"
    r"waar\s+het\s+over\s+gaat",
    re.I,
)

# Arrest datelines used as the document header ("Arrest in kort geding van 21
# oktober 2014", "Arrest d.d. 19 juli 2016", "Arrest van 7 september 2020"). The
# "(kort) geding" inside would otherwise pull the caption to procesverloop.
_CAPTION_OVERIG_RE = re.compile(
    r"^\s*arrest\b(.{0,40}\b(19|20)\d\d\b|\s+(in\s+kort\s+geding|d\.?d\.?|van)\b)",
    re.I,
)

GERECHTSHOF = Lexicon(
    name="gerechtshof",
    label_rules=_LABEL_RULES,
    heading_vocab=_HEADING_VOCAB,
    oblique_feiten=_OBLIQUE_FEITEN_RE,
    oblique_feiten_strong=RECHTBANK.oblique_feiten_strong,
    # Hof judgments scatter each grief into its own flat sibling <section>
    # under "De beoordeling ..."; let the reasoning region absorb those
    # (see refine.absorb_overwegingen_region)
    region_overwegingen=True,
    recap_overig=_RECAP_OVERIG_RE,
    caption_overig=_CAPTION_OVERIG_RE,
)
