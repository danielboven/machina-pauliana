"""Compute and store section embeddings for the RAG store.

Embeds every 'feiten' and 'overwegingen' section whose Markdown is at least
MIN_CHARS characters long, and writes the vector to that section's `embedding`
column. Shorter sections and the other labels are left NULL.

Only sections that do not have an embedding yet are processed, so the run is
resumable (re-run after an interruption)
Sections are embedded in batches (one multi-input request per batch), and
between requests we wait only when Scaleway reports the per-minute budget is
nearly used up, pacing from the rate-limit headers rather than a blind gap.

    python -m rag.ingest.embed [--dsn ...]
"""

import argparse
import time

from pgvector.psycopg import register_vector
from tqdm import tqdm

from ..api import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, embed_texts
from ..db.connection import connect

# Which sections get embedded: two sections, and only when
# long enough to carry retrievable meaning
EMBED_LABELS = ("feiten", "overwegingen")
MIN_CHARS = 70

# Sections per embedding request. Scaleway allows up to 2,048. Higher means
# fewer requests but more time in between runs (rate limiting)
BATCH_SIZE = 64

# Scaleway's rate limit is per-minute. After a batch, the only time we need to
# wait is when the token budget it reports left can't fit another batch like the
# one we just sent. Then we pause one full window for the budget to reset. (The
# 429 backoff in rag.api still covers anything this misses.)
RATE_LIMIT_DELAY = 60


def sections_to_embed(conn) -> list[tuple[int, str]]:
    """The (id, markdown) of every still-unembedded section we should embed: a
    feiten/overwegingen section of at least MIN_CHARS, ordered by id for stable,
    resumable progress."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, markdown FROM section "
            "WHERE label = ANY(%s) "
            "  AND char_length(markdown) >= %s "
            "  AND embedding IS NULL "
            "ORDER BY id",
            (list(EMBED_LABELS), MIN_CHARS),
        )
        return cur.fetchall()


def store_embeddings(conn, rows: list[tuple[int, list[float]]]) -> None:
    """Write a batch of (section_id, embedding) pairs."""
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE section SET embedding = %s WHERE id = %s",
            [(embedding, section_id) for section_id, embedding in rows],
        )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Compute and store embeddings for feiten/overwegingen "
        "sections in the RAG store."
    )
    ap.add_argument("--dsn", help="Postgres DSN (else DATABASE_URL).")
    args = ap.parse_args(argv)

    # A single, sequential connection: batches are sent to Scaleway one after
    # another, so there is no concurrency and no pool is warranted. Register
    # the pgvector type so Python lists adapt to the `vector` column.
    with connect(args.dsn) as conn:
        register_vector(conn)
        pending = sections_to_embed(conn)

        print(f"Model:      {EMBEDDING_MODEL} ({EMBEDDING_DIMENSIONS} dims)")
        print(
            f"Sections:   {len(pending)} to embed "
            f"({'/'.join(EMBED_LABELS)}, >= {MIN_CHARS} chars, not yet done)"
        )
        if not pending:
            print("Nothing to do.")
            return

        batches = [
            pending[start : start + BATCH_SIZE]
            for start in range(0, len(pending), BATCH_SIZE)
        ]

        # Drive the bar manually so it advances the moment a batch is stored
        embedded = 0
        with tqdm(total=len(batches), desc="embed", unit="batch") as bar:
            for i, batch in enumerate(batches):
                ids = [section_id for section_id, _ in batch]
                result = embed_texts([markdown for _, markdown in batch])
                store_embeddings(conn, list(zip(ids, result.vectors)))
                # persist each batch, so an interrupted run loses at most one
                conn.commit()
                embedded += len(batch)
                bar.update(
                    1
                )
                # Wait only when the reported token budget can't fit another
                # batch like this one. Otherwise keep going at full speed.
                low_budget = (
                    result.remaining_tokens is not None
                    and result.remaining_tokens < result.prompt_tokens
                )
                if i < len(batches) - 1 and low_budget:
                    time.sleep(RATE_LIMIT_DELAY)

    print(f"Done, embedded {embedded} sections.")


if __name__ == "__main__":
    main()
