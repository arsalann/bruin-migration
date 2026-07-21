#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
compose_file="$example_dir/source/docker-compose.yml"
project_name="bruin_ingestr_dlt_${CONDUCTOR_WORKSPACE_NAME:-$(basename "$(git -C "$example_dir" rev-parse --show-toplevel)")}"
project_name=$(printf '%s' "$project_name" | tr -cs '[:alnum:]_' '_')

for command in docker bruin uv python3; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

mkdir -p "$artifacts"
uv venv "$artifacts/.venv"
uv pip install --python "$artifacts/.venv/bin/python" -r "$example_dir/source/requirements.txt"
docker compose -p "$project_name" -f "$compose_file" up -d
postgres_port=$(docker compose -p "$project_name" -f "$compose_file" port postgres 5432 | sed 's/.*://')

cat > "$artifacts/runtime.env" <<EOF
COMPOSE_PROJECT_NAME=$project_name
POSTGRES_PORT=$postgres_port
SOURCE_DATABASE_URL=postgresql://migration:migration@127.0.0.1:$postgres_port/migration
DLT_DESTINATION_PATH=$artifacts/dlt.duckdb
BRUIN_DESTINATION_PATH=$artifacts/bruin.duckdb
EOF
cat > "$artifacts/bruin.yml" <<EOF
default_environment: default
environments:
  default:
    connections:
      postgres:
        - name: source_postgres
          host: 127.0.0.1
          port: $postgres_port
          database: migration
          username: migration
          password: migration
          ssl_mode: disable
      duckdb:
        - name: source_duckdb
          path: $artifacts/dlt.duckdb
        - name: target_duckdb
          path: $artifacts/bruin.duckdb
EOF
