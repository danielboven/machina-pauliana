"""Database connection for the RAG store.

A single place that resolves the DSN and opens a psycopg connection. The DSN is
read from the environment `DATABASE_URL` or passed explicitly
with `--dsn`. A .env file is loaded if present (python-dotenv).
"""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def resolve_dsn(dsn: str | None = None) -> str:
    """The DSN to connect with: explicit arg, else DATABASE_URL"""
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "No database DSN. Set DATABASE_URL in the environment "
            "or a .env file, or pass --dsn."
        )
    return dsn


def connect(dsn: str | None = None) -> psycopg.Connection:
    """Open a psycopg connection to the resolved DSN."""
    return psycopg.connect(resolve_dsn(dsn))
