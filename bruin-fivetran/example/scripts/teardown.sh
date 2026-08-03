#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "$0")/.." && pwd)
artifacts="$example_dir/.artifacts"
compose_file="$example_dir/source/docker-compose.yml"

if [[ -f "$artifacts/runtime.env" ]]; then
  source "$artifacts/runtime.env"
  if [[ -n $MOCK_FIVETRAN_PID ]] && kill -0 "$MOCK_FIVETRAN_PID" 2>/dev/null; then
    kill "$MOCK_FIVETRAN_PID" || true
    wait "$MOCK_FIVETRAN_PID" 2>/dev/null || true
  fi
  docker compose -p "$COMPOSE_PROJECT_NAME" -f "$compose_file" down \
    --volumes --remove-orphans || true
fi

rm -rf "$artifacts"
echo "Removed fixture runtime state: $artifacts"
