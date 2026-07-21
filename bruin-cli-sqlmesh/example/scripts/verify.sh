#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/bruin.yml" ]] || "$example_dir/scripts/run.sh"

SQLMESH_HOME="$artifacts/sqlmesh-home" \
  "$artifacts/.venv/bin/sqlmesh" -p "$example_dir/source/sqlmesh" test
bruin validate "$example_dir/target/pipeline.yml" --config-file "$artifacts/bruin.yml"
# The target declares a Bruin unit_tests block. Bruin v0.11.682 cannot run
# unit tests against a DuckDB connection, so validation parses that block and
# the SQLMesh test plus final data-diff exercise the equivalent logic here.
BRUIN_CONFIG_FILE="$artifacts/bruin.yml" \
  bruin docs "$example_dir/target/pipeline.yml" --output "$artifacts/bruin-docs.html"
bruin data-diff --config-file "$artifacts/bruin.yml" --full --fail-if-diff \
  source_duckdb:migration_source.daily_revenue target_duckdb:migration_target.daily_revenue
