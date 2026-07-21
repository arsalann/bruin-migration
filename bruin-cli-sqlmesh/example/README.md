# Runnable SQLMesh to Bruin reference

This example runs a self-contained DuckDB SQLMesh project and a hand-authored Bruin equivalent. It has no Docker or cloud dependency.

## Prerequisites

- `bruin`, `uv`, and `python3` on `PATH`

Pinned Python dependencies: `sqlmesh==0.236.0` and `duckdb==1.4.4`. `bootstrap.sh` installs them into `.artifacts/.venv` only. SQLMesh and Bruin DuckDB databases, SQLMesh home/cache, and generated documentation remain under `.artifacts/`.

## Commands

```bash
./scripts/bootstrap.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/teardown.sh
```

`run.sh` applies the SQLMesh plan with `--auto-apply` (which runs the SQLMesh unit test and audit) and runs the Bruin target. `verify.sh` reruns SQLMesh tests, validates the Bruin pipeline and its declared `unit_tests` block, generates `bruin-docs.html`, and runs the strict data-diff gate.

Bruin `v0.11.682` currently cannot execute `bruin unit-test` against a DuckDB connection (the CLI reports that the connection cannot run queries). The target keeps its native `unit_tests` declaration, which `bruin validate` parses; when DuckDB support reaches the runner, add `BRUIN_CONFIG_FILE=.artifacts/bruin.yml bruin unit-test target/pipeline.yml --environment default` back to the verify gate.
