#!/usr/bin/env bash
set -euo pipefail

# Native-toolchain parity gate. Profiles the PostgreSQL source, the dlt
# ClickHouse table, and the Bruin ClickHouse table with `bruin query`, asserts
# they agree, then runs `bruin data-diff --full --tolerance 0 --fail-if-diff`
# over the DuckDB comparison projections.
#
# The diff runs over projections, not directly against ClickHouse, because
# `bruin data-diff` cannot summarize a ClickHouse connection in CLI v0.11.722:
# it exits non-zero and prints nothing. The projections hold the same rows in a
# dialect Bruin does support, so the gate stays a real pass/fail check.

example_dir=$(cd "$(dirname "$0")/.." && pwd)
artifacts="$example_dir/.artifacts"
run_id=${1:-manual}
[[ $run_id =~ ^[A-Za-z0-9_.-]+$ ]] ||
  { echo "run id contains unsupported characters" >&2; exit 2; }

# shellcheck disable=SC1091
source "$artifacts/runtime.env"
config="$artifacts/bruin.yml"
verification="$artifacts/verification/$run_id"
mkdir -p "$verification"

# table:primary-key:dlt-dataset triples, kept as plain strings so the script
# also runs under the bash 3.2 that ships with macOS. `pokemon` has no
# PostgreSQL side — its source is a public API — so it is profiled and diffed
# dlt-versus-Bruin only.
TABLE_KEYS="customers:customer_id:analytics orders:order_id:analytics \
order_events:event_id:analytics pokemon:pokemon_id:api"

profile_query() {
  local table=$1 key=$2
  printf '%s' "SELECT COUNT(*) AS row_count, \
SUM(CASE WHEN $key IS NULL THEN 1 ELSE 0 END) AS null_primary_keys, \
COUNT(*) - COUNT(DISTINCT $key) AS duplicate_primary_keys FROM $table"
}

run_profile() {
  local connection=$1 description=$2 query=$3 output=$4
  bruin query --config-file "$config" --connection "$connection" \
    --description "$description" --output json --query "$query" > "$output"
}

for triple in $TABLE_KEYS; do
  table=${triple%%:*}
  rest=${triple#*:}
  key=${rest%%:*}
  which_dataset=${rest##*:}
  if [[ $which_dataset == api ]]; then
    dataset=$DLT_API_DATASET
    profile_args=""
    diff_pairs="comparison_dlt:dlt"
  else
    dataset=$DLT_DATASET
    run_profile dlt_source_postgres "profile the migration source $table" \
      "$(profile_query "public.$table" "$key")" \
      "$verification/$table.source-profile.json"
    profile_args="source:$table=$verification/$table.source-profile.json"
    diff_pairs="comparison_source:source comparison_dlt:dlt"
  fi

  run_profile dlt_target_clickhouse "profile the dlt destination $table" \
    "$(profile_query "$CLICKHOUSE_DATABASE.${dataset}___$table" "$key")" \
    "$verification/$table.dlt-profile.json"
  run_profile dlt_target_clickhouse "profile the Bruin v0 destination $table" \
    "$(profile_query "$BRUIN_DATABASE.$table" "$key")" \
    "$verification/$table.bruin-profile.json"

  # shellcheck disable=SC2086
  "$artifacts/.venv/bin/python" "$example_dir/scripts/assert_profiles.py" \
    $profile_args \
    "dlt:$table=$verification/$table.dlt-profile.json" \
    "bruin:$table=$verification/$table.bruin-profile.json"

  for pair in $diff_pairs; do
    left_connection=${pair%%:*}
    label=${pair##*:}
    bruin data-diff --config-file "$config" \
      --full --tolerance 0 --fail-if-diff --output json \
      "$left_connection:comparison.$table" "comparison_bruin:comparison.$table" \
      > "$verification/$table.data-diff-$label-vs-bruin.json"
    echo "data-diff passed: $label vs bruin for $table"
  done
done

echo "Profiles and zero-tolerance data diffs passed: $verification"
