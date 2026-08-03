#!/usr/bin/env bash
set -euo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
migration_dir=$(cd "$tests_dir/.." && pwd)
artifacts="$tests_dir/.artifacts"
generated="$artifacts/generated"

[[ -f "$artifacts/bruin.yml" ]] || "$tests_dir/scripts/bootstrap.sh"
source "$artifacts/runtime.env"

python3 "$migration_dir/scripts/import_fivetran.py" convert \
  --snapshot "$tests_dir/source/fivetran-snapshot.json" \
  --connections "$tests_dir/source/connection-map.yml" \
  --decisions "$tests_dir/source/migration-decisions.yml" \
  --output-root "$generated" \
  --strict

pipeline="$generated/connection-postgres-orders/pipeline.yml"
bruin validate "$pipeline" --config-file "$artifacts/bruin.yml"
bruin run --full-refresh "$pipeline" \
  --config-file "$artifacts/bruin.yml" \
  --start-date 2025-01-01T00:00:00Z \
  --end-date 2025-01-03T00:00:00Z

# Ingestr adds a target-only load timestamp and may choose wider physical
# PostgreSQL types. Compare the source and target through an explicit common
# representation, while retaining the raw target table for migration review.
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$tests_dir/source/docker-compose.yml" \
  exec -T postgres psql -U migration -d migration <<'SQL'
CREATE OR REPLACE VIEW comparison.target_v0_orders AS
SELECT
  order_id,
  customer_email,
  total_cents::integer AS total_cents,
  updated_at::timestamp AS updated_at
FROM migration_v0.fct_orders;
SQL
