#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/runtime.env" ]] || "$example_dir/scripts/bootstrap.sh"
source "$artifacts/runtime.env"

run_dlt() {
  DLT_DATA_DIR="$artifacts/dlt-state" \
  SOURCE_DATABASE_URL="$SOURCE_DATABASE_URL" \
  DLT_DESTINATION_PATH="$DLT_DESTINATION_PATH" \
  "$artifacts/.venv/bin/python" "$example_dir/source/dlt_pipeline.py"
}

run_bruin() {
  bruin run "$example_dir/target/pipeline.yml" \
    --config-file "$artifacts/bruin.yml" \
    --start-date 2025-01-01 --end-date 2025-01-03
}

run_dlt
run_bruin

DLT_DESTINATION_PATH="$DLT_DESTINATION_PATH" \
BRUIN_DESTINATION_PATH="$BRUIN_DESTINATION_PATH" \
  "$artifacts/.venv/bin/python" "$example_dir/scripts/prepare_comparison.py"

docker compose -p "$COMPOSE_PROJECT_NAME" -f "$example_dir/source/docker-compose.yml" \
  exec -T postgres psql -U migration -d migration < "$example_dir/fixtures/postgres/incremental.sql"

run_dlt
run_bruin
