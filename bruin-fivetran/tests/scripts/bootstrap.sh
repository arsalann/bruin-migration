#!/usr/bin/env bash
set -euo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
migration_dir=$(cd "$tests_dir/.." && pwd)
artifacts="$tests_dir/.artifacts"
compose_file="$tests_dir/source/docker-compose.yml"
workspace_name=${CONDUCTOR_WORKSPACE_NAME:-$(basename "$(git -C "$migration_dir" rev-parse --show-toplevel)")}
project_name=$(printf '%s' "bruin_fivetran_${workspace_name}" | tr -cs '[:alnum:]_' '_')

for command in docker bruin python3; do
  command -v "$command" >/dev/null || {
    echo "Missing required command: $command" >&2
    exit 1
  }
done
python3 -c 'import yaml; assert yaml.__version__ == "6.0.3", yaml.__version__'
PYTHONDONTWRITEBYTECODE=1 python3 -c \
  'import pathlib; compile(pathlib.Path("'"$migration_dir"'/scripts/import_fivetran.py").read_text(), "import_fivetran.py", "exec")'
bash -n "$tests_dir"/scripts/*.sh

mkdir -p "$artifacts"
docker compose -p "$project_name" -f "$compose_file" up -d --wait
postgres_port=$(docker compose -p "$project_name" -f "$compose_file" port postgres 5432 | awk -F: '{print $NF}')
[[ "$postgres_port" =~ ^[0-9]+$ ]] || {
  echo "Could not determine dynamically allocated PostgreSQL port" >&2
  exit 1
}

cat > "$artifacts/runtime.env" <<EOF
COMPOSE_PROJECT_NAME=$project_name
POSTGRES_PORT=$postgres_port
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
        - name: target_postgres
          host: 127.0.0.1
          port: $postgres_port
          database: migration
          username: migration
          password: migration
          ssl_mode: disable
EOF
