#!/usr/bin/env python3
"""Fail a migration validation when `bruin query` profiles disagree.

Takes one or more `label=path.json` arguments produced by
`bruin query --output json`. Every profile must report zero null keys and zero
duplicate keys, and every profile must report the same row count as the first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED = ("row_count", "null_primary_keys", "duplicate_primary_keys")


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
        found = records(value.get(key))
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
        raise ValueError(f"{path} must contain exactly one profile record")
    return tuple(numeric(rows[0], name) for name in REQUIRED)  # type: ignore[return-value]


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: assert_profiles.py LABEL=PROFILE_JSON [LABEL=PROFILE_JSON ...]",
              file=sys.stderr)
        return 2
    profiles: list[tuple[str, tuple[int, int, int]]] = []
    for argument in sys.argv[1:]:
        if "=" not in argument:
            print(f"expected LABEL=PATH, found {argument!r}", file=sys.stderr)
            return 2
        label, path = argument.split("=", 1)
        try:
            profiles.append((label, profile(Path(path))))
        except ValueError as exc:
            print(f"profile validation failed: {exc}", file=sys.stderr)
            return 1

    failures: list[str] = []
    for label, (rows, nulls, duplicates) in profiles:
        if nulls or duplicates:
            failures.append(f"{label}: null keys={nulls}, duplicate keys={duplicates}")
    baseline_label, (baseline_rows, _, _) = profiles[0]
    for label, (rows, _, _) in profiles[1:]:
        if rows != baseline_rows:
            failures.append(
                f"{label}: row count {rows} differs from {baseline_label} ({baseline_rows})"
            )
    if failures:
        print("profile validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    labels = ", ".join(label for label, _ in profiles)
    print(f"profile checks passed for {labels}: rows={baseline_rows}, null_keys=0, duplicate_keys=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
