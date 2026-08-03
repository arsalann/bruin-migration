#!/usr/bin/env python3
"""Create cross-dialect comparison projections for the local fixture."""

from __future__ import annotations

import argparse

import duckdb
import psycopg2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--destination-path", required=True)
    parser.add_argument("--source-comparison-path", required=True)
    args = parser.parse_args()

    with psycopg2.connect(args.source_url) as source:
        with source.cursor() as cursor:
            cursor.execute(
                "SELECT CAST(id AS TEXT), email, plan, CAST(updated_at AS TEXT) "
                "FROM public.customers"
            )
            source_rows = cursor.fetchall()
        source.commit()
    with duckdb.connect(args.source_comparison_path) as source_comparison:
        source_comparison.execute("CREATE SCHEMA IF NOT EXISTS comparison")
        source_comparison.execute("DROP TABLE IF EXISTS comparison.customers")
        source_comparison.execute(
            "CREATE TABLE comparison.customers "
            "(id VARCHAR, email VARCHAR, plan VARCHAR, updated_at VARCHAR)"
        )
        source_comparison.executemany(
            "INSERT INTO comparison.customers VALUES (?, ?, ?, ?)", source_rows
        )
    with duckdb.connect(args.destination_path) as destination:
        destination.execute("CREATE SCHEMA IF NOT EXISTS comparison")
        destination.execute(
            "CREATE OR REPLACE TABLE comparison.customers AS "
            "SELECT CAST(id AS VARCHAR) AS id, email, plan, CAST(updated_at AS VARCHAR) AS updated_at "
            "FROM public.customers"
        )


if __name__ == "__main__":
    main()
