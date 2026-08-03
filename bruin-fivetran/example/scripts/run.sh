#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "$0")/.." && pwd)
track_dir=$(cd "$example_dir/.." && pwd)
importer="$track_dir/.agents/skills/bruin-fivetran-migrator/import_fivetran.py"
artifacts="$example_dir/.artifacts"
if [[ ! -f "$artifacts/runtime.env" ]]; then
  "$example_dir/scripts/bootstrap.sh"
else
  source "$artifacts/runtime.env"
  if ! kill -0 "$MOCK_FIVETRAN_PID" 2>/dev/null; then
    "$example_dir/scripts/bootstrap.sh"
  fi
fi
source "$artifacts/runtime.env"

"$artifacts/.venv/bin/python" "$importer" \
  --config-file "$artifacts/bruin.yml" \
  --connector-name bruin_fivetran \
  --api-base "http://127.0.0.1:$MOCK_FIVETRAN_PORT/v1" \
  --output-dir "$artifacts/fivetran" \
  --replace

"$artifacts/.venv/bin/python" "$example_dir/scripts/scaffold_bruin_connections.py" \
  --capture-dir "$artifacts/fivetran" \
  --destination duckdb \
  --source-connection source_postgres \
  --destination-connection target_duckdb \
  --output "$artifacts/connection-handoff.bruin.yml.example" \
  --replace

"$artifacts/.venv/bin/python" "$example_dir/scripts/generate_bruin_draft.py" \
  --capture-dir "$artifacts/fivetran" \
  --decisions "$example_dir/fixtures/migration-decisions.yml" \
  --output-dir "$artifacts/generated" \
  --strict \
  --replace

bruin validate "$artifacts/generated/pipeline.yml" --config-file "$artifacts/bruin.yml"
bruin run "$artifacts/generated/pipeline.yml" \
  --config-file "$artifacts/bruin.yml" \
  --start-date 2025-01-01 \
  --end-date 2025-01-02 \
  --workers 1 \
  --timeout 300

"$artifacts/.venv/bin/python" "$example_dir/scripts/prepare_comparison.py" \
  --source-url "$SOURCE_DATABASE_URL" \
  --destination-path "$BRUIN_DESTINATION_PATH" \
  --source-comparison-path "$SOURCE_COMPARISON_PATH"

"$example_dir/scripts/profile_and_compare.sh" \
  --config-file "$artifacts/bruin.yml" \
  --source-connection source_postgres \
  --source-table public.customers \
  --destination-connection target_duckdb \
  --destination-table comparison.customers \
  --primary-key id \
  --comparison-source-connection source_comparison_duckdb \
  --comparison-source-table comparison.customers \
  --artifact-root "$artifacts" \
  --run-id fixture

echo "Ran generated fixture pipeline and validation."
