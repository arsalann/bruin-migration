#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/imported-dashboard.yml" ]] || "$example_dir/scripts/run.sh"

dac validate --dir "$example_dir/target"
dac check --config "$artifacts/bruin.yml" --dir "$example_dir/target"
dac build --config "$artifacts/bruin.yml" --dir "$example_dir/target" \
  --dashboard "Migration Fixture Dashboard" --output "$artifacts/reference-build"

mkdir -p "$artifacts/imported"
cp "$artifacts/imported-dashboard.yml" "$artifacts/imported/dashboard.yml"
dac validate --dir "$artifacts/imported"
dac check --config "$artifacts/bruin.yml" --dir "$artifacts/imported"
dac build --config "$artifacts/bruin.yml" --dir "$artifacts/imported" \
  --dashboard "Migration Fixture Dashboard" --output "$artifacts/imported-build"
