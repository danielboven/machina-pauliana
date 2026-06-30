"""Similarity scoring for RAG retrieval.

Turn a query vector and a judgment's section vectors into a single relevance
score. Kept separate from retrieval so the similarity measure and the weighting
are easy to change in one place here.

Scoring is a weighted combination of two "maxp" scores (BERT-IR, 2019): for each
section type we take the cosine of the query against every section of that type
and keep the best one. The feiten and overwegingen maxp scores are then combined
with weights, renormalized over whichever types the judgment actually has.
"""

import numpy as np

# Relative importance of each section type in the document score. When a
# judgment lacks one type, the present weight is renormalized to 1.
W_FEITEN = 0.75
W_OVERWEGINGEN = 0.25


def cosine_similarity(vec1, vec2) -> float:
    """Cosine similarity of two vectors."""
    vec1 = np.asarray(vec1, dtype=float)
    vec2 = np.asarray(vec2, dtype=float)
    return float(
        np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    )


def _maxp(query_vec, section_vecs) -> float | None:
    """The best (maxp) cosine of the query against any section of this type, or
    None when there are none. argmax mirrors the BERT-IR maxp aggregation."""
    if len(section_vecs) == 0:
        return None
    scores = np.array(
        [cosine_similarity(query_vec, vec) for vec in section_vecs]
    )
    return float(scores[np.argmax(scores)])


def score_document(query_vec, feiten_vecs, overwegingen_vecs) -> float:
    """A judgment's relevance to the query: the weighted sum of the feiten and
    overwegingen maxp scores, renormalized over the types that are present.

        both present -> W_FEITEN * f + W_OVERWEGINGEN * o   (weights sum to 1)
        one missing  -> the present score at weight 1.0

    Raises ValueError if neither type is present (do not score judgment)."""
    parts = [
        (weight, score)
        for weight, score in (
            (W_FEITEN, _maxp(query_vec, feiten_vecs)),
            (W_OVERWEGINGEN, _maxp(query_vec, overwegingen_vecs)),
        )
        if score is not None
    ]
    if not parts:
        raise ValueError(
            "judgment has no feiten or overwegingen sections to score"
        )
    total_weight = sum(weight for weight, _ in parts)
    return sum(weight * score for weight, score in parts) / total_weight
