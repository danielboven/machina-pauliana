"""Lexicon registry and court detection.

Court is derived strictly from the ECLI code on the <uitspraak> element:
    HR    -> hoge_raad
    GH*   -> gerechtshof
    RB*   -> rechtbank
Anything else raises UnknownCourtError, its then a different legal institution
(e.g. PHR = Parket bij de Hoge Raad) that this segmenter does not handle, and
silently treating it as a rechtbank would be a misfire.
"""

from .base import Lexicon, UnknownCourtError
from .rechtbank import RECHTBANK
from .gerechtshof import GERECHTSHOF
from .hoge_raad import HOGE_RAAD

_LEXICONS: dict[str, Lexicon | None] = {
    "rechtbank": RECHTBANK,
    "gerechtshof": GERECHTSHOF,
    "hoge_raad": HOGE_RAAD,
}


def court_of(ecli: str) -> str:
    """Classify an ECLI string into a court key, or raise UnknownCourtError."""
    parts = ecli.split(":")
    if len(parts) < 3 or parts[0].upper() != "ECLI":
        raise UnknownCourtError(f"not an ECLI: {ecli!r}")
    code = parts[2].upper()
    if code == "HR":
        return "hoge_raad"
    if code.startswith("GH"):
        return "gerechtshof"
    if code.startswith("RB"):
        return "rechtbank"
    raise UnknownCourtError(f"unsupported court code {code!r} in {ecli!r}")


def detect_court(uitspraak) -> str:
    """Reads the ECLI from `uitspraak` and classifies it into a court key."""
    return court_of(uitspraak.get("id", ""))


def get_lexicon(court: str) -> Lexicon:
    """Returns the Lexicon for `court`. Raises if unknown or unimplemented."""
    if court not in _LEXICONS:
        raise UnknownCourtError(f"no lexicon for court {court!r}")
    lex = _LEXICONS[court]
    if lex is None:
        raise NotImplementedError(f"{court} lexicon is not yet implemented")
    return lex


def lexicon_for(uitspraak) -> Lexicon:
    """Returns the Lexicon for the court detected from `uitspraak`."""
    return get_lexicon(detect_court(uitspraak))


# TODO this one does not seem updated do we need to update it or remove?
__all__ = [
    "Lexicon",
    "UnknownCourtError",
    "RECHTBANK",
    "court_of",
    "detect_court",
    "get_lexicon",
    "lexicon_for",
]
