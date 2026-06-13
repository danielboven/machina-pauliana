"""Profile registry and court selection.

The corpus survey runs the SAME pipeline (base.py) for every court; only the
prompting differs, bundled into a `Profile`. The court is chosen explicitly on
the command line via --court:
    RB -> rechtbank
    GH -> gerechtshof
    HR -> hoge raad
"""

from .base import Profile, run
from .rechtbank import RECHTBANK
from .gerechtshof import GERECHTSHOF
from .hoge_raad import HOGE_RAAD

_PROFILES: dict[str, Profile] = {
    "RB": RECHTBANK,
    "GH": GERECHTSHOF,
    "HR": HOGE_RAAD,
}

COURT_CHOICES = tuple(_PROFILES)


def get_profile(court: str) -> Profile:
    """Returns the Profile for a court code ('RB' / 'GH' / 'HR'). Raises on unknown."""
    code = court.upper()
    if code not in _PROFILES:
        raise ValueError(
            f"unsupported court {court!r}; choose one of {', '.join(COURT_CHOICES)}"
        )
    return _PROFILES[code]


__all__ = [
    "Profile",
    "run",
    "RECHTBANK",
    "GERECHTSHOF",
    "HOGE_RAAD",
    "COURT_CHOICES",
    "get_profile",
]
