"""Main entry point: a thin dispatcher over the RAG subcommands.

    python -m rag init     [--dsn ...] [--drop]      -> rag.db.init_db
    python -m rag ingest   <xml-file-or-dir> [...]   -> rag.ingest
    python -m rag embed    [--dsn ...]               -> rag.ingest.embed
    python -m rag annotate [--seed ...] [-n ...]     -> rag.annotate

Each subcommand is also runnable on its own: python -m rag.db.init_db etc.
"""

import sys

from . import annotate
from .db import init_db
from .ingest import embed
from .ingest.main import main as ingest_main

COMMANDS = {
    "init": init_db.main,
    "ingest": ingest_main,
    "embed": embed.main,
    "annotate": annotate.main,
}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        sys.exit(f"usage: python -m rag {{{'|'.join(COMMANDS)}}} [args...]")
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main()
