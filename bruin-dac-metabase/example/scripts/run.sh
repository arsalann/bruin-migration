#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/runtime.env" ]] || "$example_dir/scripts/bootstrap.sh"
source "$artifacts/runtime.env"

METABASE_URL="http://127.0.0.1:${METABASE_PORT}" \
METABASE_DASHBOARD_OUTPUT="$artifacts/metabase-dashboard.json" \
python3 "$example_dir/source/provision_metabase.py"

dac import metabase \
  --input "$artifacts/metabase-dashboard.json" \
  --connection fixture-postgres \
  --output "$artifacts/imported-dashboard.yml" \
  --force
