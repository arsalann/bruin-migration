#!/usr/bin/env python3
"""Three-way exact parity gate for the dlt-to-Bruin fixture.

Compares the PostgreSQL source, the dlt ClickHouse tables, and the Bruin ingestr
ClickHouse tables row for row. Hashing happens in Python so no engine's own hash
or numeric formatting can mask a difference. Exits non-zero on any mismatch.

For each table and system it computes:
  row count, distinct key count, null key count, key checksum, row checksum,
  and the cursor column's minimum and maximum.

The checksums are order-insensitive sums of per-row digests, so they detect a
changed value, a missing row, and a duplicated row without an ORDER BY over a
million rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_tables import TABLES, baseline, canonical_row, readers  # noqa: E402

MASK = (1 << 64) - 1


def digest(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def profile(
    blocks: Iterator[Sequence[Sequence[Any]]], table: str
) -> dict[str, Any]:
    definition = TABLES[table]
    key_index = definition["columns"].index(definition["key"])
    cursor_index = (
        definition["columns"].index(definition["cursor"]) if definition["cursor"] else None
    )
    row_count = 0
    null_keys = 0
    row_checksum = 0
    key_checksum = 0
    keys_seen: set[str] = set()
    cursor_min: str | None = None
    cursor_max: str | None = None

    for block in blocks:
        for raw in block:
            row = canonical_row(raw)
            row_count += 1
            key = row[key_index]
            if key == "\\N":
                null_keys += 1
            keys_seen.add(key)
            row_checksum = (row_checksum + digest("\x1f".join(row))) & MASK
            key_checksum = (key_checksum + digest(key)) & MASK
            if cursor_index is not None:
                value = row[cursor_index]
                if cursor_min is None or value < cursor_min:
                    cursor_min = value
                if cursor_max is None or value > cursor_max:
                    cursor_max = value

    return {
        "row_count": row_count,
        "distinct_keys": len(keys_seen),
        "null_keys": null_keys,
        "duplicate_keys": row_count - len(keys_seen),
        "row_checksum": row_checksum,
        "key_checksum": key_checksum,
        "cursor_min": cursor_min,
        "cursor_max": cursor_max,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="JSON profile output path")
    parser.add_argument("--tables", nargs="*", default=sorted(TABLES))
    args = parser.parse_args()

    results: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    for table in args.tables:
        profiles = {name: profile(reader(), table) for name, reader in readers(table).items()}
        results[table] = profiles
        reference = baseline(table)

        for name, values in profiles.items():
            if values["null_keys"]:
                failures.append(f"{table}/{name}: {values['null_keys']} null key(s)")
            if values["duplicate_keys"]:
                failures.append(f"{table}/{name}: {values['duplicate_keys']} duplicate key(s)")
            if values["row_count"] == 0:
                failures.append(f"{table}/{name}: no rows loaded")

        for name in profiles:
            if name == reference:
                continue
            for field in ("row_count", "distinct_keys", "key_checksum", "row_checksum"):
                if profiles[reference][field] != profiles[name][field]:
                    failures.append(
                        f"{table}: {field} differs between {reference} and {name} "
                        f"({profiles[reference][field]} != {profiles[name][field]})"
                    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    for table, profiles in sorted(results.items()):
        counts = " ".join(f"{name}={values['row_count']}" for name, values in profiles.items())
        reference = profiles[baseline(table)]
        cursor = (
            f" cursor={reference['cursor_min']}..{reference['cursor_max']}"
            if reference["cursor_min"] is not None
            else ""
        )
        print(f"{table}: {counts}{cursor}")
    if failures:
        print("\nparity gate FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"\nparity gate passed for {len(results)} table(s); profile written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
