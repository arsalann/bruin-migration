#!/usr/bin/env bash
set -euo pipefail

# Re-checks everything the fixture claims, independently of the run that
# produced it: native Bruin validation, the reviewed-decision check, the
# three-way exact parity gate, the data-diff gate, a proof that the gate can
# fail, credential hygiene, and unit tests.

example_dir=$(cd "$(dirname "$0")/.." && pwd)
track_dir=$(cd "$example_dir/.." && pwd)
artifacts="$example_dir/.artifacts"

[[ -f "$artifacts/verification/fixture/parity.json" ]] || "$example_dir/scripts/run.sh"
set -a
# shellcheck disable=SC1091
source "$artifacts/runtime.env"
set +a
python="$artifacts/.venv/bin/python"
config="$artifacts/bruin.yml"

echo "== native validation and reviewed decisions =="
bruin validate "$example_dir/target/pipeline.yml" --config-file "$config"
"$python" "$example_dir/scripts/assert_target_matches_decisions.py" \
  --decisions "$example_dir/fixtures/migration-decisions.yml" \
  --pipeline "$example_dir/target/pipeline.yml" \
  --assets-dir "$example_dir/target/assets"

echo "== three-way exact parity =="
"$python" "$example_dir/scripts/compare_parity.py" \
  --output "$artifacts/verification/verify/parity.json"

echo "== data-diff gate, and proof that it can fail =="
"$example_dir/scripts/profile_and_diff.sh" verify
"$example_dir/scripts/assert_gate_fails.sh"

echo "== credential hygiene =="
# `grep -r -F` rather than `rg`: this gate must not depend on a tool that might
# be absent, because a missing binary makes every `if grep ...` guard below fall
# through as "clean" and the leak checks would pass without running.
command -v grep >/dev/null || { echo "grep is required for the hygiene gate" >&2; exit 1; }

contains_secret() {
  grep -r -F -q -- "$1" "${@:2}" 2>/dev/null
}

for secret in fixture-postgres-secret fixture-clickhouse-secret; do
  if contains_secret "$secret" "$artifacts/connection-report.yml"; then
    echo "connection report retained the $secret value" >&2
    exit 1
  fi
  if contains_secret "$secret" "$artifacts/verification"; then
    echo "verification evidence retained the $secret value" >&2
    exit 1
  fi
  if contains_secret "$secret" \
      "$example_dir/target" "$example_dir/fixtures/migration-decisions.yml" \
      "$track_dir/plan.md" "$track_dir/README.md" "$track_dir/dlt-bruin-prompt.md"; then
    echo "a reviewed artifact retained the $secret value" >&2
    exit 1
  fi
  # Positive control: the conversion is only meaningful if the value did land in
  # the Git-ignored Bruin configuration. This also proves the checks above ran
  # against a working matcher rather than silently finding nothing.
  if ! contains_secret "$secret" "$config"; then
    echo "the converter did not write the $secret value into $config" >&2
    exit 1
  fi
done
permissions=$(stat -f '%Lp' "$config" 2>/dev/null || stat -c '%a' "$config")
if [[ $permissions != "600" ]]; then
  echo "$config must be mode 600, found $permissions" >&2
  exit 1
fi

echo "== unit tests =="
"$python" -m unittest discover -s "$example_dir/tests" -v

echo "Fixture verification passed."
