"""Create the RAG database schema.

This runs `schema.sql` (idempotent). With `--drop` it first removes the tables
and enums for a clean rebuild.

    python -m rag.db.init_db [--dsn ...] [--drop]
"""

import argparse
from pathlib import Path

from .connection import connect

SCHEMA = Path(__file__).with_name("schema.sql")

# Drop in dependency order. CASCADE clears the FKs/indexes. Types last.
DROP_SQL = """
DROP TABLE IF EXISTS relation CASCADE;
DROP TABLE IF EXISTS section  CASCADE;
DROP TABLE IF EXISTS judgment CASCADE;
DROP TYPE  IF EXISTS section_label;
DROP TYPE  IF EXISTS court;
"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Create the RAG database schema.")
    ap.add_argument("--dsn", help="Postgres DSN (else DATABASE_URL).")
    ap.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables/types first (destroys data).",
    )
    args = ap.parse_args(argv)

    with connect(args.dsn) as conn, conn.cursor() as cur:
        if args.drop:
            cur.execute(DROP_SQL)
        cur.execute(SCHEMA.read_text())
        conn.commit()
    print(f"schema ready{' (rebuilt)' if args.drop else ''}")


if __name__ == "__main__":
    main()
