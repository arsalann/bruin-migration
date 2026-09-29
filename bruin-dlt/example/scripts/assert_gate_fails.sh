#!/usr/bin/env bash
set -euo pipefail

# Proves the parity gate can actually fail.
#
# A validation command that never fails is not a validation command. This builds
# two tiny DuckDB tables that differ by exactly one row, and asserts that
# `bruin data-diff --full --tolerance 0 --fail-if-diff` exits non-zero for the
# differing pair and zero for an identical pair. It runs against its own
# throwaway config so it cannot touch the fixture's comparison projections.

example_dir=$(cd "$(dirname "$0")/.." && pwd)
artifacts="$example_dir/.artifacts"
selftest="$artifacts/selftest"

rm -rf "$selftest"
mkdir -p "$selftest"

"$artifacts/.venv/bin/python" - "$selftest" <<'PY'
import sys
from pathlib import Path

import duckdb

selftest = Path(sys.argv[1])
rows = [(str(index), f"value-{index}") for index in range(1, 11)]
for name, payload in (("left", rows), ("right", rows[:-1]), ("copy", rows)):
    with duckdb.connect(str(selftest / f"{name}.duckdb")) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS comparison")
        connection.execute("CREATE TABLE comparison.selftest (id VARCHAR, label VARCHAR)")
        connection.executemany("INSERT INTO comparison.selftest VALUES (?, ?)", payload)
PY

cat > "$selftest/bruin.yml" <<YML
default_environment: default
environments:
  default:
    connections:
      duckdb:
        - name: selftest_left
          path: $selftest/left.duckdb
        - name: selftest_right
          path: $selftest/right.duckdb
        - name: selftest_copy
          path: $selftest/copy.duckdb
YML

status=0
bruin data-diff --config-file "$selftest/bruin.yml" --full --tolerance 0 --fail-if-diff \
  selftest_left:comparison.selftest selftest_right:comparison.selftest \
  > "$selftest/differing.txt" 2>&1 || status=$?
if [[ $status -eq 0 ]]; then
  echo "gate self-test failed: data-diff accepted a one-row difference" >&2
  exit 1
fi

bruin data-diff --config-file "$selftest/bruin.yml" --full --tolerance 0 --fail-if-diff \
  selftest_left:comparison.selftest selftest_copy:comparison.selftest \
  > "$selftest/identical.txt" 2>&1 ||
  { echo "gate self-test failed: data-diff rejected an identical pair" >&2; exit 1; }

echo "gate self-test passed: data-diff fails on a one-row difference and passes on a copy"
