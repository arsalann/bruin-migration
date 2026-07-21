# Runnable dlt to ingestr reference

This example compares a dlt SQL database resource and a Bruin `ingestr` asset over the same local PostgreSQL source. Both targets are local DuckDB databases kept under `.artifacts/`.

## Prerequisites

- Docker Desktop with Compose v2
- `bruin`, `uv`, and `python3` on `PATH`

Pinned dependencies: PostgreSQL `16.4-alpine`, `dlt[duckdb,sql_database]==1.29.0`. The bootstrap script creates an example-local virtual environment; it does not install dlt globally.

## Commands

```bash
./scripts/bootstrap.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/teardown.sh
```

`run.sh` deliberately performs two passes:

1. Initial dlt and Bruin loads of `public.customers`.
2. A fixture update that modifies one customer and inserts one customer, followed by second incremental loads.

`verify.sh` runs Bruin validation and `bruin data-diff --full --fail-if-diff` between logical `comparison.customers` projections of the dlt and Bruin DuckDB outputs. The projection excludes dlt/ingestr load metadata; it also casts the identifier to `VARCHAR` solely to work around a current Bruin `data-diff --full` DuckDB numerical-statistics defect.
