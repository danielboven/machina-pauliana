"""Rechtspraak XML helpers.

Based on IVO Rechtspraak, 2019, and on sample documents (emperical).
Every lookup works based on the namespaced form (spec).
"""

from pathlib import Path

RS_NS = "http://www.rechtspraak.nl/schema/rechtspraak-1.0"
DC_NS = "http://purl.org/dc/terms/"


def ns(tag: str) -> str:
    return f"{{{RS_NS}}}{tag}"


def local_tag(el) -> str:
    """Namespace-stripped tag name; '' for comments / PIs."""
    t = getattr(el, "tag", None)
    if not isinstance(t, str):
        return ""
    return t.split("}", 1)[1] if t.startswith("{") else t


def get_uitspraak(root):
    """The <uitspraak> element, or root itself when absent (e.g. PHR conclusies,
    which carry no <uitspraak> and are rejected later by court)."""
    el = root.find(f".//{ns('uitspraak')}")
    return el if el is not None else root


def find_child(el, name: str):
    """The first direct child of `el` with tag `name`."""
    return el.find(ns(name))


def doc_ecli(root) -> str:
    """The bare ECLI for the document, from <dcterms:identifier>."""
    for el in root.findall(f".//{{{DC_NS}}}identifier"):
        text = (el.text or "").strip()
        if text.startswith("ECLI:"):
            return text
    return ""


def gather_xml(path: Path) -> list[Path]:
    """Returns a sorted list of all .xml files under `path`, or just
    `[path]` if `path` is a single file."""
    if path.is_dir():
        return sorted(p for p in path.rglob("*.xml"))
    return [path]


def in_court(path: Path, root: Path, prefix: str) -> bool:
    """Checks whether `path` belongs to a court whose folder starts with
    `prefix` (N.B. folder layout COURT/YEAR/ECLI.xml).
    Returns True when root is a single file since there is no court folder."""
    rel = path.relative_to(root)
    return rel.parts[0].startswith(prefix) if len(rel.parts) > 1 else True
