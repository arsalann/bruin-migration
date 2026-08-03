#!/usr/bin/env bash
set -euo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$tests_dir/.artifacts"
generated="$artifacts/generated"
reference="$tests_dir/target/connection-postgres-orders"

[[ -f "$generated/connection-postgres-orders/pipeline.yml" ]] || "$tests_dir/scripts/run.sh"

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$tests_dir" -p 'test_*.py' -v
diff -ru "$reference" "$generated/connection-postgres-orders"
cmp "$tests_dir/target/conversion-report.yml" "$generated/conversion-report.yml"
cmp "$tests_dir/target/migration-decisions.template.yml" "$generated/migration-decisions.template.yml"

bruin validate "$generated/connection-postgres-orders/pipeline.yml" --config-file "$artifacts/bruin.yml"
bruin data-diff --config-file "$artifacts/bruin.yml" --full --tolerance 0 --fail-if-diff \
  source_postgres:comparison.v0_orders \
  target_postgres:comparison.target_v0_orders
