"""The segmentation data model and the label set.

The five labels are theoretically grounded in Art. 230 Rv and
De weg naar het civiele vonnis, Ahsmann, M.J.A.M. (2019).
Lexicon assigns labels, overig is catch-all others.
"""

from dataclasses import dataclass, field
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
    element: object
    number: Optional[int] = None
    strategy: str = ""
    end_element: object = None  # first block of the NEXT section (None = EOF)
    body_text: str = ""  # plain text between this start and the next
    blocks: list = field(default_factory=list)  # body blocks, for Markdown

    @property
    def pos(self) -> int:
        """Document-order index of the boundary (every boundary object carries
        one)."""
        return getattr(self.element, "pos", -1)
