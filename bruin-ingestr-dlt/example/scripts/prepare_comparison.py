#!/usr/bin/env python3
"""Create comparable logical projections without dlt/ingestr load metadata."""

from __future__ import annotations

import os

import duckdb


def project(path: str, table: str) -> None:
    with duckdb.connect(path) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS comparison")
        # Bruin 0.11.682's full DuckDB data-diff cannot summarize numerical
        # columns. The string cast is isolated to this comparison projection.
        connection.execute(
            f"""CREATE OR REPLACE TABLE comparison.customers AS
            SELECT
              CAST(id AS VARCHAR) AS id,
              email,
              plan,
              updated_at
            FROM {table}"""
        )


project(os.environ["DLT_DESTINATION_PATH"], "analytics.customers")
project(os.environ["BRUIN_DESTINATION_PATH"], "public.customers")
