#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"
compose_file="$example_dir/source/docker-compose.yml"

if [[ -f "$artifacts/runtime.env" ]]; then
  source "$artifacts/runtime.env"
  docker compose -p "$COMPOSE_PROJECT_NAME" -f "$compose_file" down --volumes --remove-orphans
fi
rm -rf "$artifacts"
