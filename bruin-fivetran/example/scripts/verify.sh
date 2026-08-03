#!/usr/bin/env bash
set -euo pipefail

example_dir=$(cd "$(dirname "$0")/.." && pwd)
artifacts="$example_dir/.artifacts"
[[ -f "$artifacts/generated/pipeline.yml" ]] || "$example_dir/scripts/run.sh"
source "$artifacts/runtime.env"

bruin validate "$artifacts/generated/pipeline.yml" --config-file "$artifacts/bruin.yml"
bruin validate "$example_dir/target/pipeline.yml" --config-file "$artifacts/bruin.yml"
diff -u "$example_dir/target/pipeline.yml" "$artifacts/generated/pipeline.yml"
diff -u "$example_dir/target/assets/public/customers.asset.yml" \
  "$artifacts/generated/assets/public/customers.asset.yml"
"$artifacts/.venv/bin/python" "$example_dir/scripts/verify_rows.py" \
  --source-url "$SOURCE_DATABASE_URL" \
  --destination-path "$BRUIN_DESTINATION_PATH"

if rg --quiet --fixed-strings "fixture-password" "$artifacts/fivetran"; then
  echo "Fivetran capture retained a password" >&2
  exit 1
fi
if rg --quiet --fixed-strings "fixture-token" "$artifacts/fivetran"; then
  echo "Fivetran capture retained a token" >&2
  exit 1
fi
if rg --quiet --fixed-strings "fixture-password" "$artifacts/connection-handoff.bruin.yml.example"; then
  echo "Connection handoff retained a password" >&2
  exit 1
fi
if rg --quiet --fixed-strings "fixture-token" "$artifacts/connection-handoff.bruin.yml.example"; then
  echo "Connection handoff retained a token" >&2
  exit 1
fi
"$artifacts/.venv/bin/python" -m unittest discover -s "$example_dir/tests" -v

echo "Fixture verification passed."
