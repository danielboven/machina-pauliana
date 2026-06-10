"""Rechtspraak section-boundary segmentation.

Public API:
    from rechtspraak_segmentation import segment
    result = segment("ECLI_NL_RBAMS_2012_xyz.xml")

The CLI/TUI program lives in 'interface' folder and is run with
`python -m rechtspraak_segmentation`. Look at README for more info.
"""

from .api import SegmentationResult, detect_boundaries, segment
from .core.model import Section
from .lexicon import Lexicon, UnknownCourtError, get_lexicon

__all__ = [
    "segment", "SegmentationResult", "detect_boundaries",
    "Section", "Lexicon", "UnknownCourtError", "get_lexicon",
]
