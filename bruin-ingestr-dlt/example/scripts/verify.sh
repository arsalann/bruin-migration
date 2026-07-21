#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/bruin.yml" ]] || "$example_dir/scripts/run.sh"

bruin validate "$example_dir/target/pipeline.yml" --config-file "$artifacts/bruin.yml"
bruin data-diff --config-file "$artifacts/bruin.yml" --full --fail-if-diff \
  source_duckdb:comparison.customers target_duckdb:comparison.customers
