#!/usr/bin/env python3
"""Compare the fixture source and generated target rows exactly."""

from __future__ import annotations

import argparse
import os

import duckdb
import psycopg2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--destination-path", required=True)
    args = parser.parse_args()

    with psycopg2.connect(args.source_url) as source:
        with source.cursor() as cursor:
            cursor.execute(
                "SELECT id, email, plan, updated_at::text FROM public.customers ORDER BY id"
            )
            source_rows = cursor.fetchall()
    with duckdb.connect(args.destination_path, read_only=True) as destination:
        target_rows = destination.execute(
            "SELECT id, email, plan, CAST(updated_at AS VARCHAR) "
            "FROM public.customers ORDER BY id"
        ).fetchall()
    normalized_source = [tuple(str(value) for value in row) for row in source_rows]
    normalized_target = [tuple(str(value) for value in row) for row in target_rows]
    if normalized_source != normalized_target:
        raise SystemExit(
            "exact source/target row comparison failed: "
            f"source={normalized_source!r}, target={normalized_target!r}"
        )
    print(f"exact row comparison passed: {len(source_rows)} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
