#!/usr/bin/env python3
"""Apply a tracked fixture SQL file to the fixture PostgreSQL database."""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg2

TABLES = ("public.customers", "public.orders", "public.order_events")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--sql-file", required=True)
    args = parser.parse_args()

    statements = Path(args.sql_file).read_text(encoding="utf-8")
    with psycopg2.connect(args.source_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statements)
        connection.commit()
        with connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"{table}: {cursor.fetchone()[0]} row(s)")


if __name__ == "__main__":
    main()
