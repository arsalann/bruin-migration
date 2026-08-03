#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "$0")/.." && pwd)
artifact_root="$example_dir/.artifacts"


usage() {
  cat <<'EOF'
Usage:
  profile_and_compare.sh --config-file FILE --source-connection NAME \
    --source-table SCHEMA.TABLE --destination-connection NAME \
    --destination-table SCHEMA.TABLE --primary-key COLUMN [--environment NAME] \
    [--comparison-source-connection NAME --comparison-source-table SCHEMA.TABLE] \
    [--artifact-root TRACK_ARTIFACTS] [--run-id ID]
EOF
}

config_file=
source_connection=
source_table=
destination_connection=
destination_table=
primary_key=
environment=
comparison_source_connection=
comparison_source_table=
requested_artifact_root=
run_id=$(date -u +%Y%m%dT%H%M%SZ)

while (($#)); do
  case "$1" in
    --config-file) config_file=$2; shift 2 ;;
    --source-connection) source_connection=$2; shift 2 ;;
    --source-table) source_table=$2; shift 2 ;;
    --destination-connection) destination_connection=$2; shift 2 ;;
    --destination-table) destination_table=$2; shift 2 ;;
    --primary-key) primary_key=$2; shift 2 ;;
    --environment|--env) environment=$2; shift 2 ;;
    --comparison-source-connection) comparison_source_connection=$2; shift 2 ;;
    --comparison-source-table) comparison_source_table=$2; shift 2 ;;
    --artifact-root) requested_artifact_root=$2; shift 2 ;;
    --run-id) run_id=$2; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done


[[ -n $config_file && -n $source_connection && -n $source_table ]] ||
  { usage >&2; exit 2; }
[[ -n $destination_connection && -n $destination_table && -n $primary_key ]] ||
  { usage >&2; exit 2; }
[[ $source_table =~ ^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$ ]] ||
  { echo "source table must be SCHEMA.TABLE with simple identifiers" >&2; exit 2; }
[[ $destination_table =~ ^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$ ]] ||
  { echo "destination table must be SCHEMA.TABLE with simple identifiers" >&2; exit 2; }
[[ $primary_key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
  { echo "primary key must be a simple identifier" >&2; exit 2; }
if [[ -n $comparison_source_connection || -n $comparison_source_table ]]; then
  [[ -n $comparison_source_connection && -n $comparison_source_table ]] ||
    { echo "both comparison source options are required together" >&2; exit 2; }
  [[ $comparison_source_table =~ ^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$ ]] ||
    { echo "comparison source table must be SCHEMA.TABLE with simple identifiers" >&2; exit 2; }
fi
[[ $run_id =~ ^[A-Za-z0-9_.-]+$ ]] ||
  { echo "run id contains unsupported characters" >&2; exit 2; }

if [[ -n $requested_artifact_root ]]; then
  artifact_root=$requested_artifact_root
fi
case "$artifact_root" in
  "$example_dir/.artifacts") ;;
  *) echo "artifact root must be this fixture's .artifacts directory" >&2; exit 2 ;;
esac
artifact_dir="$artifact_root/verification/$run_id"
mkdir -p "$artifact_dir"
profile_query() {
  local table=$1
  printf '%s' "SELECT COUNT(*) AS row_count, COALESCE(SUM(CASE WHEN $primary_key IS NULL THEN 1 ELSE 0 END), 0) AS null_primary_keys, COUNT(*) - COUNT(DISTINCT $primary_key) AS duplicate_primary_keys FROM $table"
}
diff_source_connection=$source_connection
diff_source_table=$source_table
if [[ -n $comparison_source_connection ]]; then
  diff_source_connection=$comparison_source_connection
  diff_source_table=$comparison_source_table
fi


run_profile() {
  local connection=$1
  local description=$2
  local query=$3
  local output=$4
  if [[ -n $environment ]]; then
    bruin query --config-file "$config_file" --environment "$environment" \
      --connection "$connection" --description "$description" --output json \
      --query "$query" > "$output"
  else
    bruin query --config-file "$config_file" \
      --connection "$connection" --description "$description" --output json \
      --query "$query" > "$output"
  fi
}

run_profile "$source_connection" \
  "profile the approved Fivetran migration source table" \
  "$(profile_query "$source_table")" \
  "$artifact_dir/source-profile.json"
run_profile "$destination_connection" \
  "profile the approved Fivetran migration destination table" \
  "$(profile_query "$destination_table")" \
  "$artifact_dir/destination-profile.json"

python3 "$example_dir/scripts/assert_profiles.py" \
  "$artifact_dir/source-profile.json" "$artifact_dir/destination-profile.json"

if [[ -n $environment ]]; then
  bruin data-diff --config-file "$config_file" --environment "$environment" \
    --full --tolerance 0 --fail-if-diff --output json \
    "$diff_source_connection:$diff_source_table" "$destination_connection:$destination_table" \
    > "$artifact_dir/data-diff.json"
else
  bruin data-diff --config-file "$config_file" \
    --full --tolerance 0 --fail-if-diff --output json \
    "$diff_source_connection:$diff_source_table" "$destination_connection:$destination_table" \
    > "$artifact_dir/data-diff.json"
fi

echo "Profiles and zero-tolerance data diff passed: $artifact_dir"
