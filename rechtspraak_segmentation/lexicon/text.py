"""Generic text normalisation used by the controlled heading-language gate.

Independent of court: these only reshape a line so the lexicon's vocabulary
check can be applied.
"""

import re

# Collapse letter-spaced caps used as headings, e.g. "B E S L I S S I N G".
_SPACED_CAPS_RE = re.compile(r"^\s*([A-Za-zÀ-ɏ]\s+){2,}[A-Za-zÀ-ɏ]\s*$")

# Strip a leading enumerator ("3.", "3)", "3:" or "3 ") so the bare heading
# phrase can be matched
_LEAD_ENUM_RE = re.compile(r"^\s*\d{1,2}(?:\s*[.):]\s*|\s+)")

# Include unicode letters only (word chars minus digits and underscores)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# A parenthetical qualifier on a heading, e.g. "Feiten (alles kort samengevat en
# voor zover van belang)". These are dropped before the vocabulary gate.
_PAREN_RE = re.compile(r"\([^)]*\)")


def collapse_spaced_caps(text: str) -> str:
    """Collapses 'B E S L I S S I N G'-style headings into 'BESLISSING'."""
    return re.sub(r"\s+", "", text) if _SPACED_CAPS_RE.match(text) else text


def strip_parentheticals(text: str) -> str:
    """Removes parenthetical qualifiers from `text`."""
    return _PAREN_RE.sub(" ", text)


def strip_leading_enum(text: str) -> str:
    """Strips a leading enumerator like '3.' or '3)' from `text`."""
    return _LEAD_ENUM_RE.sub("", text, count=1)


def word_tokens(text: str) -> list[str]:
    """Split text into letter-only tokens, stripping digits and punctuation."""
    return _WORD_RE.findall(text)
