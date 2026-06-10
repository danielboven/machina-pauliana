"""Rechtspraak XML helpers.

Based on IVO Rechtspraak, 2019, and on sample documents (emperical).
Every lookup tries the namespaced form first and falls back to the local name.
TODO check if we need fallback actually for the data?
"""

from pathlib import Path

RS_NS = "http://www.rechtspraak.nl/schema/rechtspraak-1.0"


def ns(tag: str) -> str:
    return f"{{{RS_NS}}}{tag}"


def local_tag(el) -> str:
    """Namespace-stripped tag name; '' for comments / PIs."""
    t = getattr(el, "tag", None)
    if not isinstance(t, str):
        return ""
    return t.split("}", 1)[1] if t.startswith("{") else t


# Sentinel for a real <?linebreak?> PI, distinct from source whitespace newlines
_LINEBREAK = "\x00"


def _flatten(el, brk: str) -> str:
    """Flatten function for text content of `el`. Inserts brk at each
    <?linebreak?> processing instruction. Rechtspraak encodes line breaks as
    PIs. Emitting a break keeps the words (and visual lines) separated."""
    parts: list[str] = []

    def walk(node):
        if node.text:
            parts.append(node.text)
        for child in node:
            if isinstance(child.tag, str):
                walk(child)
            elif getattr(child, "target", None) == "linebreak":
                parts.append(brk)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return "".join(parts)


def el_text(el) -> str:
    """A linebreak PI becomes a space so words do not glue
    .split() then collapses it together with ordinary whitespace.
    Reason for not doing full linebreaks is that it causes many
    false positives on final segmentation."""
    return " ".join(_flatten(el, " ").split())


def title_text(title_el) -> str:
    """Heading text of a <title> element. The <nr> is stripped,
    and only the first non-empty  visual line is used.
    Titles vary: the heading may sit inline with the nr
    ('2 Inleiding | subtitle | body') or on the line after a bare nr
    ('3 | 3. Het geschil'). Either way anything after the heading line
    is dropped."""
    nr_el = find_child(title_el, "nr")
    nr = (nr_el.text or "").strip().rstrip(".") if nr_el is not None else ""
    for i, line in enumerate(_flatten(title_el, _LINEBREAK).split(_LINEBREAK)):
        line = " ".join(line.split())
        if i == 0 and nr and line.startswith(nr):
            line = line[len(nr) :].lstrip(". ").strip()
        if line:
            return line
    return ""


def get_uitspraak(root):
    """Gets root element <uitspraak> in XML."""
    for finder in (f".//{ns('uitspraak')}", ".//uitspraak"):
        el = root.find(finder)
        if el is not None:
            return el
    return root


def iter_tag(context, name: str):
    """Returns all descendants of `context` with local tag `name`.
    Tries the namespaced form first, falls back to the plain tag."""
    found = list(context.iter(ns(name)))
    return found if found else list(context.iter(name))


def find_child(el, name: str):
    """Finds the first direct child of `el` with local tag `name`.
    Tries the namespaced form first, falls back to the plain tag."""
    return el.find(ns(name)) if el.find(ns(name)) is not None else el.find(name)


def has_section_ancestor(el) -> bool:
    """Checks whether `el` has a <section> anywhere up its ancestor chain."""
    p = el.getparent()
    while p is not None:
        if local_tag(p) == "section":
            return True
        p = p.getparent()
    return False


def doc_ecli(root) -> str:
    """Returns the ECLI identifier from the `id` attribute on <uitspraak>."""
    # TODO rewrite this one to remove :DOC at the end?
    el = get_uitspraak(root)
    return el.get("id", "") if el is not None else ""


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
