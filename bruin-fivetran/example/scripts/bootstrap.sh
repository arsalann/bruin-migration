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

if [[ -f "$artifacts/runtime.env" ]]; then
  source "$artifacts/runtime.env"
  if kill -0 "$MOCK_FIVETRAN_PID" 2>/dev/null; then
    echo "Fixture is already bootstrapped: $artifacts"
    exit 0
  fi
  "$example_dir/scripts/teardown.sh"
fi

mkdir -p "$artifacts"
python3 -m venv "$artifacts/.venv"
"$artifacts/.venv/bin/pip" install --quiet -r "$example_dir/requirements.txt"

workspace_name=$(printenv CONDUCTOR_WORKSPACE_NAME || basename "$example_dir")
project_name=$(printf '%s' "bruin_fivetran_$workspace_name" | tr -cs '[:alnum:]_' '_')
docker compose -p "$project_name" -f "$compose_file" up -d --wait
postgres_port=$(docker compose -p "$project_name" -f "$compose_file" port postgres 5432 | sed 's/.*://')

nohup "$artifacts/.venv/bin/python" "$source_dir/mock_fivetran_api.py" \
  --fixture "$example_dir/fixtures/fivetran/responses.json" \
  --port-file "$artifacts/mock-fivetran.port" \
  > "$artifacts/mock-fivetran.log" 2>&1 &
mock_pid=$!
printf '%s\n' "$mock_pid" > "$artifacts/mock-fivetran.pid"

for _ in $(seq 1 50); do
  [[ -s "$artifacts/mock-fivetran.port" ]] && break
  sleep 0.1
done
[[ -s "$artifacts/mock-fivetran.port" ]] ||
  { echo "Mock Fivetran API did not start" >&2; exit 1; }
mock_port=$(<"$artifacts/mock-fivetran.port")

"$artifacts/.venv/bin/python" "$source_dir/write_runtime_files.py" \
  --artifacts "$artifacts" \
  --postgres-port "$postgres_port" \
  --mock-port "$mock_port" \
  --compose-project "$project_name"

echo "Bootstrapped fixture runtime state: $artifacts"
