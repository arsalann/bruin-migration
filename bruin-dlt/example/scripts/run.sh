#!/usr/bin/env bash
set -euo pipefail

# Runs the whole fixture: the dlt source pipeline first, then the migration
# workflow's automated steps against the reviewed target reference, in two
# passes (initial history, then a deterministic change set).
#
# The stage comments map each step onto the stage of ../dlt-bruin-prompt.md it
# stands in for. Stages that exist only to ask a human for a decision are
# represented by fixtures/migration-decisions.yml.

example_dir=$(cd "$(dirname "$0")/.." && pwd)
track_dir=$(cd "$example_dir/.." && pwd)
artifacts="$example_dir/.artifacts"
converter="$track_dir/.agents/skills/bruin-dlt-migrator/convert_dlt_connections.py"
run_id=fixture

[[ -f "$artifacts/runtime.env" ]] || "$example_dir/scripts/bootstrap.sh"
set -a
# shellcheck disable=SC1091
source "$artifacts/runtime.env"
set +a
python="$artifacts/.venv/bin/python"
config="$artifacts/bruin.yml"

if ! docker compose -p "$COMPOSE_PROJECT_NAME" -f "$example_dir/source/docker-compose.yml" \
    ps --status running --services 2>/dev/null | grep -q clickhouse; then
  "$example_dir/scripts/bootstrap.sh"
  set -a
  # shellcheck disable=SC1091
  source "$artifacts/runtime.env"
  set +a
fi

echo "== reset only this fixture's destination and dlt state =="
"$python" "$example_dir/scripts/reset_destinations.py"
"$python" "$example_dir/source/seed_postgres.py" \
  --source-url "$SOURCE_DATABASE_URL" \
  --sql-file "$example_dir/fixtures/postgres/seed.sql"

echo "== stage 2: convert dlt credentials into Bruin connections =="
"$python" "$converter" \
  --dlt-project-dir "$DLT_PROJECT_DIR" \
  --output "$config" \
  --source-connection dlt_source_postgres \
  --destination-connection dlt_target_clickhouse \
  --report "$artifacts/connection-report.yml" \
  --replace
bruin connections test --config-file "$config" --name dlt_source_postgres
bruin connections test --config-file "$config" --name dlt_target_clickhouse

echo "== source of truth: run both dlt pipelines first (initial load) =="
(cd "$DLT_PROJECT_DIR" && "$python" dlt_pipeline.py --pass-label initial)
# The custom-API pipeline needs outbound network access to https://pokeapi.co.
(cd "$DLT_PROJECT_DIR" && "$python" dlt_api_pipeline.py --pass-label initial)

echo "== stage 3: check the reviewed target reference, then validate it =="
"$python" "$example_dir/scripts/assert_target_matches_decisions.py" \
  --decisions "$example_dir/fixtures/migration-decisions.yml" \
  --pipeline "$example_dir/target/pipeline.yml" \
  --assets-dir "$example_dir/target/assets"
bruin validate "$example_dir/target/pipeline.yml" --config-file "$config"

echo "== stage 5: approved v0 run over the initial history window =="
bruin run "$example_dir/target/pipeline.yml" \
  --config-file "$config" \
  --start-date 2025-01-01 \
  --end-date 2025-03-31 \
  --workers 1 \
  --timeout 1800

echo "== second pass: apply the deterministic change set =="
"$python" "$example_dir/source/seed_postgres.py" \
  --source-url "$SOURCE_DATABASE_URL" \
  --sql-file "$example_dir/fixtures/postgres/incremental.sql"
(cd "$DLT_PROJECT_DIR" && "$python" dlt_pipeline.py --pass-label incremental)
# Re-run unchanged: proves the API resource's merge is idempotent on both sides.
(cd "$DLT_PROJECT_DIR" && "$python" dlt_api_pipeline.py --pass-label incremental)
bruin run "$example_dir/target/pipeline.yml" \
  --config-file "$config" \
  --start-date 2025-04-01 \
  --end-date 2025-04-02 \
  --workers 1 \
  --timeout 1800

echo "== parity: three-way exact comparison and the data-diff gate =="
"$python" "$example_dir/scripts/compare_parity.py" \
  --output "$artifacts/verification/$run_id/parity.json"
"$python" "$example_dir/scripts/prepare_comparison.py"
"$example_dir/scripts/profile_and_diff.sh" "$run_id"

echo "Fixture run complete. Evidence: $artifacts/verification/$run_id"
