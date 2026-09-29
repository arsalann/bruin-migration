#!/usr/bin/env python3
"""Build DuckDB comparison projections so `bruin data-diff` can be the gate.

`bruin data-diff` cannot summarize a ClickHouse connection in CLI v0.11.722: it
exits non-zero and prints nothing. Rather than drop the gate, the fixture
projects the same logical rows from all three systems into DuckDB, which Bruin
does support, and diffs those.

Every column is projected as VARCHAR using the shared canonicalization, for two
reasons: it keeps the comparison engine-neutral, and it avoids a current DuckDB
numerical-statistics limitation in `bruin data-diff --full`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Iterator, Sequence

import duckdb
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_tables import TABLES, canonical, readers  # noqa: E402


def write_projection(
    path: Path, table: str, blocks: Iterator[Sequence[Sequence[Any]]]
) -> int:
    columns = TABLES[table]["columns"]
    schema = pa.schema([(column, pa.string()) for column in columns])
    rows = 0
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS comparison")
        connection.execute(f"DROP TABLE IF EXISTS comparison.{table}")
        definition = ", ".join(f"{column} VARCHAR" for column in columns)
        connection.execute(f"CREATE TABLE comparison.{table} ({definition})")
        for block in blocks:
            if not block:
                continue
            arrays = [
                pa.array([canonical(row[index]) for row in block], type=pa.string())
                for index in range(len(columns))
            ]
            chunk = pa.Table.from_arrays(arrays, schema=schema)
            connection.register("comparison_chunk", chunk)
            connection.execute(f"INSERT INTO comparison.{table} SELECT * FROM comparison_chunk")
            connection.unregister("comparison_chunk")
            rows += len(block)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", nargs="*", default=sorted(TABLES))
    args = parser.parse_args()

    targets = {
        "source": Path(os.environ["COMPARISON_SOURCE_PATH"]),
        "dlt": Path(os.environ["COMPARISON_DLT_PATH"]),
        "bruin": Path(os.environ["COMPARISON_BRUIN_PATH"]),
    }

    for table in args.tables:
        counts = {
            name: write_projection(targets[name], table, reader())
            for name, reader in readers(table).items()
        }
        print(f"comparison.{table}: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
