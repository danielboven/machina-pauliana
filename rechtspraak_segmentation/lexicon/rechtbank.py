"""Rechtbank (District Court) lexicon

Drafted from an LLM survey of the RB filtered corpus.

Contains the rules and vocabulary distilled from first-instance vonnissen.
"""

import re

from .base import Lexicon

# ---------------------------------------------------------------------------
# Label rules (ordered: first matching pattern wins)
# ---------------------------------------------------------------------------
_LABEL_RULES = (
    # "Rechtdoende" / "beslissing" is the unambiguous dictum opener
    ("beslissing", re.compile(r"recht\s*doende", re.I)),
    # Procesverloop / verloop van de procedure and others
    (
        "procesverloop",
        re.compile(
            r"(procesverloop|(verdere\s+)?verloop\s+(van\s+(de|het)\s+)?(procedure|geding)|"
            r"loop\s+van\s+(het|de)\s+geding|verdere\s+verloop|"
            r"(verdere\s+)?procesgang|procedure)",
            re.I,
        ),
    ),
    # Feiten
    (
        "feiten",
        re.compile(
            r"(vaststaande\s+feiten|vastgestelde\s+feiten|feiten|"
            r"uitgangspunten|achtergrond)",
            re.I,
        ),
    ),
    # overwegingen is tested BEFORE geschil so that a heading like
    # "De beoordeling van het geschil" is classified first as overwegingen
    (
        "overwegingen",
        re.compile(
            r"(beoordeling|overwegingen|rechtsoverwegingen|motivering|"
            r"gronden\s+van\s+de\s+beslissing|"
            r"oordeel\s+van\s+de\s+(rechtbank|voorzieningenrechter|kantonrechter))",
            re.I,
        ),
    ),
    # geschil vocabulary also covers the recurring synonyms seen in the corpus:
    # "(gronden van het) verzet", "het beroep", "de inzet van ...",
    # "de reactie(s) van ..." all of those frame the parties' dispute/claim
    (
        "geschil",
        re.compile(
            r"(geschil|vordering|(?<!wrakings)verzoek(?:en|schrift)?\b|verweer|"
            r"standpunt|stellingen|verzet|beroep|inzet|reactie)",
            re.I,
        ),
    ),
    ("beslissing", re.compile(r"(beslissing|recht\s*doende|besluit)", re.I)),
)

# ---------------------------------------------------------------------------
# Controlled "heading language" of a vonnis
# ---------------------------------------------------------------------------
# Empirically a section heading is a short, stand-alone line built ONLY from a
# closed vocabulary: a section keyword (the head) plus determiners, connectives
# and case/scope qualifiers ("in conventie", "van het geschil", "in de
# hoofdzaak", ...). A line that contains any other (content) words, ie a verb, a
# name, a substantive noun, etc, is running text, not a heading. Gating on this
# closed vocabulary keeps recall high on heading variants while refusing to
# promote sentence fragments.
_HEADING_VOCAB = frozenset(
    {
        # determiners / connectives / prepositions
        "de",
        "het",
        "een",
        "van",
        "in",
        "voor",
        "en",
        "met",
        "over",
        "op",
        "te",
        "tot",
        "der",
        "den",
        "ten",
        "ter",
        "aan",
        "bij",
        "dit",
        "deze",
        "die",
        "of",
        "dan",
        "wel",
        "danwel",
        "alsmede",
        "respectievelijk",
        "zowel",
        "alle",
        "beide",
        "zover",
        "belang",
        "daarvan",
        "ervan",
        "thans",
        # scope / case-type qualifiers
        "conventie",
        "reconventie",
        "voorwaardelijke",
        "onvoorwaardelijke",
        "hoofdzaak",
        "hoofdzaken",
        "vrijwaring",
        "vrijwaringszaak",
        "ondervrijwaring",
        "ondervrijwaringszaak",
        "incident",
        "incidenten",
        "incidentele",
        "tussenkomst",
        "voeging",
        "zaak",
        "zaken",
        "kort",
        "primaire",
        "subsidiaire",
        "meer",
        "eerste",
        "tweede",
        "derde",
        "verdere",
        "verder",
        "nadere",
        "nader",
        "vervolg",
        # institutional actors that occur inside headings
        "rechtbank",
        "voorzieningenrechter",
        "kantonrechter",
        "rechter",
        "curator",
        "partijen",
        # section keyword stems and their multi-word components
        "procesverloop",
        "procedure",
        "verloop",
        "loop",
        "geding",
        "procesgang",
        "gang",
        "feiten",
        "feit",
        "vaststaande",
        "vastgestelde",
        "uitgangspunten",
        "achtergrond",
        "omstandigheden",
        "geschil",
        "geschillen",
        "vordering",
        "vorderingen",
        "verzoek",
        "verzoeken",
        "verweer",
        "standpunt",
        "standpunten",
        "stellingen",
        "verzet",
        "beroep",
        "inzet",
        "reactie",
        "reacties",
        "beoordeling",
        "overwegingen",
        "overweging",
        "rechtsoverwegingen",
        "motivering",
        "oordeel",
        "gronden",
        "beslissing",
        "beslissingen",
        "rechtdoende",
        "doende",
        "recht",
        "besluit",
        "dictum",
    }
)

# Fallback mapping for facts when unambiguous facts are absent.
# They include "De kern van de zaak", "Wat is er gebeurd?", "Inleiding", etc
# It never overrides an explicit feiten heading.
_OBLIQUE_FEITEN_RE = re.compile(
    r"(kern\s+van\s+(de\s+zaak|het\s+geschil|de\s+kwestie|de\s+zaak)|de\s+kern\b|"
    r"waar\s+(gaat\s+)?(deze|de)\s+zaak\s+over|waar\s+het\s+over\s+gaat|"
    r"wat\s+er\s+(is\s+)?gebeurd|wat\s+is\s+er\s+gebeurd|"
    r"de\s+zaak\s+in\s+het\s+kort|inleiding)",
    re.I,
)

# Narrative "what happened / what the case is about" openers: these are the real
# factual recital, preferred over a summary/intro ("De kern van de zaak",
# "Inleiding") when a document heads both.
_NARRATIVE_FEITEN_RE = re.compile(
    r"(wat\s+(er\s+(is\s+)?|is\s+er\s+)gebeurd|wat\s+er\s+speelt|"
    r"waar\s+(gaat\s+)?(deze|de)\s+zaak\s+over|waar\s+het\s+over\s+gaat)",
    re.I,
)

RECHTBANK = Lexicon(
    name="rechtbank",
    label_rules=_LABEL_RULES,
    heading_vocab=_HEADING_VOCAB,
    oblique_feiten=_OBLIQUE_FEITEN_RE,
    oblique_feiten_strong=_NARRATIVE_FEITEN_RE,
)
