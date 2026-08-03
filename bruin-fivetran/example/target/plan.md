# Fixture Fivetran-to-Bruin plan

This hand-authored reference demonstrates the required durable plan shape using
only synthetic fixture data. Runtime imports and generated drafts stay under
`.artifacts/`; they never overwrite this file.

## Automated findings

- Synthetic Fivetran connection: `bruin_fivetran`, PostgreSQL source service.
- Selected object: `public.customers`, `LIVE` sync mode.
- Source column configuration records `id` as an integer primary key and
  `updated_at` as a timestamp.

## Hand-authored decisions

- Source: the fixture-local `source_postgres` connection.
- Target: isolated `target_duckdb:public.customers`.
- Initial-run scope: one table in the explicit
  `2025-01-01` through `2025-01-02` interval.
- Materialization: `merge` with `id` primary key and `updated_at` incremental
  key.
- Delete handling: not applicable to the fixture's `LIVE` table.

## Unsupported features and open review items

- Fivetran credentials, checkpoints, schedule ownership, alerting, and
  production cutover are outside this deterministic fixture.
- A real `SOFT_DELETE`, `HISTORY`, or Query-Based source requires a separate
  human decision before any asset is enabled.

## Validation evidence

- The fixture validates both this reference and the generated candidate with
  Bruin.
- It runs the candidate against the local PostgreSQL source and DuckDB target.
- It fails on an invalid key profile, a normalized zero-tolerance Bruin
  data-diff, a generated/reference file mismatch, or an exact row mismatch.
