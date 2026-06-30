"""Relation-graph lookups over the `relation` table, via recursive CTEs.

Relations are treated as undirected: an edge (source, target) is followed both
ways, and reachability is taken transitively, so a judgment "sees" everything in
its connected component, not just its direct neighbours.

Used on both sides of retrieval:
  - pre-retrieval:  `eclis_with_propagated_label` spreads a label across the
                    component.
  - post-retrieval: `related_eclis_by_date` returns the component for context.
"""

# The three art. 42 Fw label columns on `judgment`
LABELS = {"onverplicht", "benadeling_schuldeisers", "wetenschap"}

# Undirected, transitive reachability per start node, including the node itself.
# Shared prefix for the queries below
_REACH_CTE = """
WITH RECURSIVE
edges AS (
    SELECT source_ecli AS a, target_ecli AS b FROM relation
    UNION
    SELECT target_ecli AS a, source_ecli AS b FROM relation
),
reach AS (
    SELECT ecli AS start, ecli AS node FROM judgment
    UNION
    SELECT r.start, e.b
    FROM reach r
    JOIN edges e ON e.a = r.node
)
"""


def eclis_with_propagated_label(conn, label: str) -> set[str]:
    """The ECLIs for which `label` is true once propagated across the relation
    graph: the judgment's own value is true, OR any judgment reachable from it
    through relations has it true. Used in pre-retrieval stage."""
    if label not in LABELS:
        raise ValueError(
            f"unknown label {label!r}; expected one of {sorted(LABELS)}"
        )

    with conn.cursor() as cur:
        cur.execute(
            _REACH_CTE
            + f"""
            SELECT r.start
            FROM reach r
            JOIN judgment j ON j.ecli = r.node
            GROUP BY r.start
            HAVING bool_or(j.{label})
            """
        )
        return {ecli for (ecli,) in cur.fetchall()}


def related_eclis_by_date(conn, ecli: str) -> list[str]:
    """Every ECLI in `ecli`'s connected relation component (including itself),
    ordered earliest -> latest by judgment_date. Post-retrieval expansion."""
    with conn.cursor() as cur:
        cur.execute(
            _REACH_CTE
            + """
            SELECT j.ecli
            FROM reach r
            JOIN judgment j ON j.ecli = r.node
            WHERE r.start = %s
            ORDER BY j.judgment_date, j.ecli
            """,
            (ecli,),
        )
        return [row[0] for row in cur.fetchall()]
