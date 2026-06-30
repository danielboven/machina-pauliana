"""Citation edges between judgments: the second half of ingest.

Imported and called by `ingest/main.py` after judgments and sections are inserted
This file has 3 deterministic extractors, in priority order, each writing an
edge `(source_ecli -> target_ecli)` written only when both judgements are in
the database. The extractors are:

1. formal      — `<dcterms:relation ecli:resourceIdentifier="ECLI:...">` in
                 RDF metadata. Structured and no ambiguity
2. zaaknummer  — one judgment cites another one by referncing psi:zaaknummer.
                 For civil cases this zaaknummer is: C/cc/NNNNNN
                 (cc is court code, unique to court and instance).
                 Just the sequential number (NNNNNN) is only unique WITHIN a
                 court, so it is matched only when <dcterms:creator> place name
                 sits near it,  which is how a court of appeal cites the
                 instance ("zaaknummer rechtbank Overijssel 244145").
3. inhoud      — "Appel/Hoger beroep van ECLI:..." in the <inhoudsindicatie>.

Free-form body ECLI scanning is deliberately not used (many false positives).
"""

import re

from lxml import etree

from rechtspraak_segmentation.core.xmlutil import doc_ecli, get_uitspraak

DC_NS = "http://purl.org/dc/terms/"
ECLI_NS = "https://e-justice.europa.eu/ecli"
PSI_NS = "http://psi.rechtspraak.nl/"
RS_NS = "http://www.rechtspraak.nl/schema/rechtspraak-1.0"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"

# Characters on either side of a case number within which the rechtbank
# instance must be named for the number to count as a citation
PLACE_WINDOW = 60

# "Appel/Hoger beroep van ECLI:..."
INHOUD_RE = re.compile(
    r"(?:[Aa]ppel|[Hh]oger beroep) van\s+(ECLI:NL:[A-Z]+:[0-9]+:[0-9A-Z]+)"
)
# Procedure-type tokens that mark a real case number: dagvaarding (ZA),
# rekest (RK), kanton (EXPL / VERZ / FORM)
ROLLCODE_RE = re.compile(r"(ZA|RK|EXPL|VERZ|FORM|EA)")
# A district case number, e.g. "C/07/199301" (also written "C-07-199301")
# C-prefix + court code + long number is specific on its own
DISTRICT_RE = re.compile(r"C[/-]\d{2}[/-]\d{5,}")


def _norm(text: str) -> str:
    """Uppercase, strip everything but A-Z0-9."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _parse_case_number(raw: str) -> set[str]:
    """Normalized case number keys from one psi:zaaknummer value.

    A field may hold several case numbers. Two specific shapes are recognized.
    Two shapes are recognized, the rest is dropped (too generic):
    - district case numbers `C/dd/NNNNNN`, specific by their prefix for civil.
    - rollcode case numbers carrying a procedure token, >= 12 chars
    """
    keys = {_norm(m) for m in DISTRICT_RE.findall(raw)}
    for chunk in re.split(r"\s+en\s+|&", raw):
        key = _norm(chunk)
        if len(key) >= 12 and ROLLCODE_RE.search(key):
            keys.add(key)
    return keys


def _court(ecli: str) -> str:
    """RB / GH / HR etc. from the ECLI code."""
    parts = ecli.split(":")
    return parts[2][:2] if len(parts) > 2 else ""


def _formal_targets(root) -> list[str]:
    """Every ECLI referenced by a <dcterms:relation> formal relation."""
    out = []
    for rel in root.iterfind(f".//{{{DC_NS}}}relation"):
        target = rel.get(f"{{{ECLI_NS}}}resourceIdentifier")
        if target and target.startswith("ECLI:"):
            out.append(target)
    return out


def _inhoud_target(root) -> str | None:
    """Get ECLI from fixed line Appel/Hoger beroep van ECLI: ..."""
    inh = root.find(f".//{{{RS_NS}}}inhoudsindicatie")
    if inh is None:
        return None
    match = INHOUD_RE.search(" ".join(inh.itertext()))
    return match.group(1) if match else None


def _zaaknummer_keys(root) -> set[str]:
    """All case number keys for the judgment from psi:zaaknummer."""
    keys: set[str] = set()
    for el in root.iterfind(f".//{{{PSI_NS}}}zaaknummer"):
        if el.text:
            keys |= _parse_case_number(el.text)
    return keys


def _zaaknummer_cores(root) -> set[str]:
    """Sequential case numbers (>= 6 digits) without C and court code prefix
    from psi:zaaknummer values."""
    cores: set[str] = set()
    for el in root.iterfind(f".//{{{PSI_NS}}}zaaknummer"):
        if el.text:
            cores |= set(re.findall(r"\d{6,}", el.text))
    return cores


def _creator_place(root) -> str:
    """The district court instance/place from <dcterms:creator>"""
    for el in root.iterfind(f".//{{{DC_NS}}}creator"):
        if el.get(f"{{{RDFS_NS}}}label") == "Instantie" and el.text:
            return el.text.replace("Rechtbank", "").strip().lower()
    return ""


def _flat(text: str) -> str:
    """Whitespace-collapsed, lowercased text for place-proximity checks."""
    return re.sub(r"\s+", " ", text).lower()


def _place_near(flat_text: str, number: str, place: str) -> bool:
    """True if `place` occurs within PLACE_WINDOW chars of the case number
    without prefix (ie without C and court code)."""
    for m in re.finditer(rf"(?<!\d){number}(?!\d)", flat_text):
        window = flat_text[
            max(0, m.start() - PLACE_WINDOW) : m.end() + PLACE_WINDOW
        ]
        if place in window:
            return True
    return False


def add_relations(conn, files) -> int:
    """Extract edges from files and insert those whose endpoints are both in
    the store. Returns the number of distinct edges found."""
    with conn.cursor() as cur:
        cur.execute("SELECT ecli FROM judgment")
        in_store = {ecli for (ecli,) in cur.fetchall()}

    edges: set[tuple[str, str]] = set()
    # full case number key -> RB ecli
    rb_case_numbers: dict[str, str] = {}
    rb_bare: list[
        tuple[str, set[str], str]
    ] = []  # (RB ecli, core numbers, place)
    gh_docs: list[tuple[str, str, str]] = []  # (GH ecli, body_norm, body_flat)

    for path in files:
        try:
            root = etree.fromstring(path.read_bytes())
            ecli = doc_ecli(root)
        except etree.XMLSyntaxError:
            continue
        if ecli not in in_store:
            continue

        # Extractors 1 (formal relation) and 3 (inhoud): both yield an ECLI
        # directly, so just check store membership before adding the edge.
        for target in _formal_targets(root):
            if target != ecli and target in in_store:
                edges.add((ecli, target))
        inhoud = _inhoud_target(root)
        if inhoud and inhoud != ecli and inhoud in in_store:
            edges.add((ecli, inhoud))

        # Extractor 2 (case number): collect RB case numbers and GH body text.
        # Cross-match after the loop (RB may appear after GH in the walk)
        court = _court(ecli)
        if court == "RB":
            for key in _zaaknummer_keys(root):
                rb_case_numbers.setdefault(key, ecli)
            cores = _zaaknummer_cores(root)
            if cores:
                rb_bare.append((ecli, cores, _creator_place(root)))
        elif court == "GH":
            body = " ".join(get_uitspraak(root).itertext())
            gh_docs.append((ecli, _norm(body), _flat(body)))

    for gh_ecli, body_norm, body_flat in gh_docs:
        # full case number (C/cc/... or rollcode): specific, match directly
        for key, rb_ecli in rb_case_numbers.items():
            if rb_ecli != gh_ecli and key in body_norm:
                edges.add((gh_ecli, rb_ecli))
        # bare sequential number: prefilter to numbers actually in this body,
        # so the proximity scan only runs on real hits. Then require the
        # rechtbank to be named beside one of them
        body_numbers = set(re.findall(r"\d{6,}", body_flat))
        for rb_ecli, cores, place in rb_bare:
            if rb_ecli == gh_ecli or not place:
                continue
            hits = cores & body_numbers
            if hits and any(_place_near(body_flat, n, place) for n in hits):
                edges.add((gh_ecli, rb_ecli))

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO relation (source_ecli, target_ecli) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            sorted(edges),
        )
    conn.commit()
    return len(edges)
