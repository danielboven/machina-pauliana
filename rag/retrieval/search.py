"""RAG retrieval setup.

This ties everything together, ie take a query vector, find the most relevant
judgments by weighted cosine similarity over their feiten/overwegingen section
embeddings, and expand each match with its related judgments (in full Markdown).

Pure read path. Imports the scoring maths (similarity)
Note that api re-exports `retrieve` and adds text wrapper, so callers should use
rag.api.
"""

from pgvector.psycopg import register_vector

from .graph import eclis_with_propagated_label, related_eclis_by_date
from .similarity import score_document

# The two section types that carry embeddings (see rag.ingest.embed).
EMBED_LABELS = ("feiten", "overwegingen")


def candidate_sections(conn, eclis=None) -> dict[str, dict[str, list]]:
    """The embedded feiten/overwegingen vectors of each judgment, grouped per
    ECLI.
    register_vector makes pgvector return the embeddings as numpy arrays."""
    register_vector(conn)
    sql = (
        "SELECT ecli, label, embedding FROM section "
        "WHERE label = ANY(%s) AND embedding IS NOT NULL"
    )
    params: list = [list(EMBED_LABELS)]
    if eclis is not None:
        sql += " AND ecli = ANY(%s)"
        params.append(list(eclis))

    grouped: dict[str, dict[str, list]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for ecli, label, embedding in cur.fetchall():
            doc = grouped.setdefault(ecli, {"feiten": [], "overwegingen": []})
            doc[label].append(embedding)
    return grouped


def render_judgment(conn, ecli: str) -> str:
    """One judgment as full Markdown: `# Uitspraak {ecli}` heading followed by
    all its sections in document order, each separated by a blank line."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT markdown FROM section WHERE ecli = %s ORDER BY position",
            (ecli,),
        )
        sections = [row[0] for row in cur.fetchall()]
    return f"# Uitspraak {ecli}\n\n" + "\n\n".join(sections)


def retrieve(
    conn, query_vec, label: str | None = None, k: int = 5
) -> list[dict]:
    """Retrieve top-k judgments most similar to `query_vec`.

    Pre-retrieval: when `label` is given, only judgments for which that label is
    true (propagated across relations) are candidates.

    Post-retrieval: for every match, the related judgments are added and
    rendered as Markdown, ordered earliest -> latest by judgment_date.

    Returns, ranked by score: [{"ecli", "score",
    "related": [{"ecli", "markdown"}, ...]}, ...]."""
    allowed = eclis_with_propagated_label(conn, label) if label else None
    candidates = candidate_sections(conn, allowed)

    scored = sorted(
        (
            (
                score_document(query_vec, doc["feiten"], doc["overwegingen"]),
                ecli,
            )
            for ecli, doc in candidates.items()
        ),
        reverse=True,
    )

    results = []
    for score, ecli in scored[:k]:
        related = [
            {"ecli": rel, "markdown": render_judgment(conn, rel)}
            for rel in related_eclis_by_date(conn, ecli)
        ]
        results.append({"ecli": ecli, "score": score, "related": related})
    return results


def to_markdown(hits: list[dict]) -> str:
    """Flatten `retrieve` results into one Markdown context string: each hit's
    related component in date order, hits in rank order. A judgment that falls
    in more than one hit is emitted , ie first occurrence kept)."""
    seen: set[str] = set()
    blocks: list[str] = []
    for hit in hits:
        for judgment in hit["related"]:
            if judgment["ecli"] not in seen:
                seen.add(judgment["ecli"])
                blocks.append(judgment["markdown"])
    return "\n\n".join(blocks)
