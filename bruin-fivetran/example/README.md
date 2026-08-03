# Maintainer-only regression fixture

This directory is not part of the end-user migration tool. The runtime surface
is `../fivetran-bruin-prompt.md`, `../plan.md`, and the skill directory at
`../.agents/skills/bruin-fivetran-migrator/`.

This deterministic fixture proves the scaffold's safe happy path without calling
Fivetran or a customer database. A local HTTP server emulates Fivetran's
read-only connection and schema endpoints; a Dockerized PostgreSQL database is
the source; generated Bruin ingestr assets load into an isolated DuckDB file.

The fixture imports the synthetic `bruin_fivetran` connection, redacts its mock
password/token, generates an approved single-table `merge` asset, runs it, and
fails if source and target differ.

The checked-in [`target/`](target/) directory is the hand-authored reference.
Verification validates it separately and requires the generated fixture
pipeline/asset to match it before accepting the run.

## Prerequisites

- Docker Desktop with Compose v2
- `bruin` and `python3` on `PATH`

The fixture creates a virtual environment inside `.artifacts/` and installs the
pinned dependencies from `requirements.txt`. It uses PostgreSQL
`16.4-alpine` and a dynamically assigned loopback port.

## Commands

```bash
./scripts/bootstrap.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/teardown.sh
```

- `bootstrap.sh` provisions only the fixture's Docker project and
  `.artifacts/` state.
- `run.sh` captures the mock Fivetran configuration, generates the candidate
  pipeline under `.artifacts/generated/` with `--strict`, validates and runs
  it, then profiles and data-diffs a string-keyed cross-dialect comparison
  projection. The projection isolates a current DuckDB numerical-statistics
  limitation in `bruin data-diff --full`; exact source/target rows are also
  compared.
- `verify.sh` repeats native Bruin validation, performs an exact row comparison,
  checks that the capture did not retain the mock password/token, and runs unit
  tests.
- `teardown.sh` stops only the explicitly named Compose project and deletes this
  example's `.artifacts/` directory.

No task accesses the repository root `.bruin.yml`, customer Fivetran account,
Cloud SQL source, or BigQuery destination.
