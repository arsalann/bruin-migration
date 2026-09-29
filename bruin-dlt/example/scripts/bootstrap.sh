#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "$0")/.." && pwd)
artifacts="$example_dir/.artifacts"
source_dir="$example_dir/source"
compose_file="$source_dir/docker-compose.yml"

for command in docker bruin python3; do
  command -v "$command" >/dev/null ||
    { echo "Missing required command: $command" >&2; exit 1; }
done

workspace_name=$(printenv CONDUCTOR_WORKSPACE_NAME || basename "$example_dir")
project_name=$(printf '%s' "bruin_dlt_$workspace_name" | tr -cs '[:alnum:]_' '_')

if [[ -f "$artifacts/runtime.env" ]]; then
  # shellcheck disable=SC1091
  source "$artifacts/runtime.env"
  if docker compose -p "$COMPOSE_PROJECT_NAME" -f "$compose_file" ps \
      --status running --services 2>/dev/null | grep -q clickhouse; then
    echo "Fixture is already bootstrapped: $artifacts"
    exit 0
  fi
  "$example_dir/scripts/teardown.sh"
fi

mkdir -p "$artifacts"
python3 -m venv "$artifacts/.venv"
"$artifacts/.venv/bin/pip" install --quiet --upgrade pip
"$artifacts/.venv/bin/pip" install --quiet -r "$example_dir/requirements.txt"

docker compose -p "$project_name" -f "$compose_file" up -d --wait
postgres_port=$(docker compose -p "$project_name" -f "$compose_file" port postgres 5432 | sed 's/.*://')
clickhouse_native_port=$(docker compose -p "$project_name" -f "$compose_file" port clickhouse 9000 | sed 's/.*://')
clickhouse_http_port=$(docker compose -p "$project_name" -f "$compose_file" port clickhouse 8123 | sed 's/.*://')

"$artifacts/.venv/bin/python" "$source_dir/write_runtime_files.py" \
  --artifacts "$artifacts" \
  --postgres-port "$postgres_port" \
  --clickhouse-native-port "$clickhouse_native_port" \
  --clickhouse-http-port "$clickhouse_http_port" \
  --compose-project "$project_name"

# shellcheck disable=SC1091
source "$artifacts/runtime.env"
"$artifacts/.venv/bin/python" "$source_dir/seed_postgres.py" \
  --source-url "$SOURCE_DATABASE_URL" \
  --sql-file "$example_dir/fixtures/postgres/seed.sql"

echo "Bootstrapped fixture runtime state: $artifacts"
