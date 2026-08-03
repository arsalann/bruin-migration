#!/usr/bin/env python3
"""Fail a migration validation when profile counts or key checks are unhealthy."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    raw_columns = value.get("columns")
    raw_rows = value.get("rows")
    if isinstance(raw_columns, list) and isinstance(raw_rows, list):
        names = [
            column.get("name")
            for column in raw_columns
            if isinstance(column, dict) and isinstance(column.get("name"), str)
        ]
        if names:
            return [
                dict(zip(names, row))
                for row in raw_rows
                if isinstance(row, list) and len(row) == len(names)
            ]
    for key in ("rows", "data", "result", "results"):
        nested = value.get(key)
        found = records(nested)
        if found:
            return found
    return [value] if "row_count" in value else []


def numeric(record: dict[str, Any], name: str) -> int:
    value = record.get(name)
    if isinstance(value, bool):
        raise ValueError(f"{name} is not numeric")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is missing or not numeric") from exc


def profile(path: Path) -> tuple[int, int, int]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    rows = records(value)
    if len(rows) != 1:
        raise ValueError(f"{path} must contain one profile record")
    row = rows[0]
    return (
        numeric(row, "row_count"),
        numeric(row, "null_primary_keys"),
        numeric(row, "duplicate_primary_keys"),
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: assert_profiles.py SOURCE_JSON DESTINATION_JSON", file=sys.stderr)
        return 2
    try:
        source = profile(Path(sys.argv[1]))
        destination = profile(Path(sys.argv[2]))
    except ValueError as exc:
        print(f"profile validation failed: {exc}", file=sys.stderr)
        return 1
    for label, values in (("source", source), ("destination", destination)):
        _, nulls, duplicates = values
        if nulls or duplicates:
            print(
                f"profile validation failed: {label} has null keys={nulls}, duplicate keys={duplicates}",
                file=sys.stderr,
            )
            return 1
    if source[0] != destination[0]:
        print(
            f"profile validation failed: source rows={source[0]}, destination rows={destination[0]}",
            file=sys.stderr,
        )
        return 1
    print(f"profile checks passed: rows={source[0]}, null_keys=0, duplicate_keys=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
