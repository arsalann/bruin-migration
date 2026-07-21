#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
compose_file="$example_dir/source/docker-compose.yml"
project_name="bruin_dac_metabase_${CONDUCTOR_WORKSPACE_NAME:-$(basename "$(git -C "$example_dir" rev-parse --show-toplevel)")}"
project_name=$(printf '%s' "$project_name" | tr -cs '[:alnum:]_' '_')

for command in curl docker python3 dac bruin; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

mkdir -p "$artifacts"
docker compose -p "$project_name" -f "$compose_file" up -d

postgres_port=$(docker compose -p "$project_name" -f "$compose_file" port postgres 5432 | sed 's/.*://')
metabase_port=$(docker compose -p "$project_name" -f "$compose_file" port metabase 3000 | sed 's/.*://')

for _ in $(seq 1 120); do
  if curl --fail --silent "http://127.0.0.1:${metabase_port}/api/health" >/dev/null; then
    break
  fi
  sleep 2
done
curl --fail --silent "http://127.0.0.1:${metabase_port}/api/health" >/dev/null || {
  echo "Metabase did not become healthy; inspect: docker compose -p $project_name -f $compose_file logs" >&2
  exit 1
}

cat > "$artifacts/runtime.env" <<EOF
COMPOSE_PROJECT_NAME=$project_name
POSTGRES_PORT=$postgres_port
METABASE_PORT=$metabase_port
EOF
cat > "$artifacts/bruin.yml" <<EOF
default_environment: default
environments:
  default:
    connections:
      postgres:
        - name: fixture-postgres
          host: 127.0.0.1
          port: $postgres_port
          database: metabase
          username: metabase
          password: metabase
          ssl_mode: disable
EOF

echo "Metabase: http://127.0.0.1:${metabase_port}"
