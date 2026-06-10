"""The segmentation data model and the label set.

The five labels are theoretically grounded in Art. 230 Rv and De weg naar het
civiele vonnis, Ahsmann, M.J.A.M. (2019).
Lexicon assigns labels, overig is catch-all others.
"""

from dataclasses import dataclass
from typing import Optional

CANON_LABELS = (
    "procesverloop",
    "feiten",
    "geschil",
    "overwegingen",
    "beslissing",
)
SECTION_LABELS = CANON_LABELS + ("overig",)


@dataclass
class Section:
    label: str
    raw_title: str
    element: object  # the start element (title or heading para)
    number: Optional[int] = None
    strategy: str = ""
    end_element: object = None  # first element of the NEXT section (None = EOF)
    body_text: str = ""  # text between this start and the next
