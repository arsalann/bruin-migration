#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
artifacts="$example_dir/.artifacts"

for command in bruin uv python3; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

mkdir -p "$artifacts"
uv venv "$artifacts/.venv"
uv pip install --python "$artifacts/.venv/bin/python" -r "$example_dir/source/requirements.txt"

cat > "$artifacts/bruin.yml" <<EOF
default_environment: default
environments:
  default:
    connections:
      duckdb:
        - name: source_duckdb
          path: $artifacts/sqlmesh_source.duckdb
        - name: target_duckdb
          path: $artifacts/bruin.duckdb
EOF
