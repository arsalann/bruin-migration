# Reviewed Fivetran-to-Bruin plan — fixture reference

This is a hand-authored review record for the deterministic fixture, not a
production approval. In a real migration, create and maintain the living plan
at the migration workspace root as `plan.md`; do not put it under
`.artifacts/`.

## Automated findings

- The sanitized Fivetran connection is a PostgreSQL connection with selected
  object `public.orders` and original destination name `analytics.fct_orders`.
- The source configuration includes four selected business columns, one disabled
  source column (`legacy_note`), and the Fivetran-only `_fivetran_synced`
  metadata column. The converter excludes the disabled and Fivetran-only
  columns.
- Fivetran's `auto` / 15-minute schedule is recorded only as a candidate. No
  Bruin schedule is emitted.
- The source Fivetran schema policy is `BLOCK_ALL`; the reviewed Bruin policy is
  `freeze`. They are related but not assumed equivalent.

## Hand-authored decisions

- Map the local source to `source_postgres` and write only to
  `target_postgres:migration_v0.fct_orders`, an isolated v0 target.
- Use `merge` with reviewed primary key `order_id` and incremental key
  `updated_at`; use explicit UTC bounds from 2025-01-01 through 2025-01-03 for
  the initial run.
- Treat hard deletes as intentionally unsupported by this timestamp merge and
  document the acknowledged `ignore` strategy for the fixture.
- Use a consistent snapshot boundary for the local data comparison.

## Unsupported or non-portable behavior

- Fivetran credentials, endpoint settings, networking, schedules, retries,
  alerts, control-plane state, and checkpoint state are never copied.
- Fivetran history mode, custom transformations, hashed columns, automatic
  discovery, and Fivetran system-column semantics are not converted.
- Timestamp merge does not give delete parity. A production migration needs a
  separately reviewed CDC, tombstone, or periodic-replace design.

## Open human-review items for a real migration

- Confirm the full physical source schema, key uniqueness, nullability, and
  exact column selection; the Fivetran schema API may omit unedited columns.
- Test the mapped Bruin source and destination connections using the exact
  runtime configuration. Record connection fingerprints without secrets.
- Approve an isolated destination, backfill bounds, source-write boundary,
  schema-contract owner, hard-delete handling, monitoring, rollback, and an
  explicit cron before any cutover.
- Run parity against a common representation and retain the raw result under
  `.artifacts/<run-id>/validation/`. Keep Fivetran active until the agreed final
  boundary passes.

## Fixture validation result

The fixture's `run.sh` creates the isolated v0 target with the generated
pipeline. Its `verify.sh` validates the pipeline with Bruin and runs a
zero-tolerance `bruin data-diff --full --fail-if-diff` between normalized source
and target views. The command exits nonzero for a mismatch.
