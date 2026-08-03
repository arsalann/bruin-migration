#!/usr/bin/env bash
set -euo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$tests_dir/.artifacts"
compose_file="$tests_dir/source/docker-compose.yml"

if [[ -f "$artifacts/runtime.env" ]]; then
  source "$artifacts/runtime.env"
  docker compose -p "$COMPOSE_PROJECT_NAME" -f "$compose_file" down --volumes --remove-orphans
fi
rm -rf -- "$artifacts"
