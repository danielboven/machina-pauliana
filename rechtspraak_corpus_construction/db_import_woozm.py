#!/usr/bin/env python3
"""Import WooZM dossier records from a gzipped JSON file into Postgres."""

import argparse
import gzip

import ijson
import psycopg

# Selected columns that are not null on data dump
COLS = [
    "dc_identifier",
    "dc_title",
    "dc_type",
    "dc_description",
    "dc_source",
    "dc_publisher",
    "dc_creator",
    "tooiwl_topic",
    "foi_decisionDate",
    "foi_nrDocuments",
    "foi_retrievedDate",
    "foi_publishedDate",
    "foi_active",
    "dc_date_year",
    "foi_approved",
    "foi_updateDate",
]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", required=True, help="Postgres connection string")
    p.add_argument("--input", required=True, help="Gzipped JSON input file")
    args = p.parse_args()

    sql = f"COPY dossiers ({','.join(COLS)}) FROM STDIN"
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        with cur.copy(sql) as cp, gzip.open(args.input, "rb") as f:
            for rec in ijson.items(f, "item"):
                cp.write_row([rec.get(c) for c in COLS])


if __name__ == "__main__":
    main()
