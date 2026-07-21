#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/bruin.yml" ]] || "$example_dir/scripts/bootstrap.sh"

SQLMESH_HOME="$artifacts/sqlmesh-home" \
  "$artifacts/.venv/bin/sqlmesh" -p "$example_dir/source/sqlmesh" plan --auto-apply

bruin run "$example_dir/target/pipeline.yml" --config-file "$artifacts/bruin.yml" \
  --start-date 2025-01-01 --end-date 2025-01-03
