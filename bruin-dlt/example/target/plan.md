# dlt to Bruin migration plan — fixture instance

This is the completed `../../plan.md` for the fixture's synthetic dlt pipeline. It
is the reviewed reference for what a filled-in runtime plan looks like. The
migration is complete only through the approved v0 run; cutover is deliberately
not performed.

## Status and provenance

- Migration name: `dlt_commerce_clickhouse` to `dlt_commerce_to_bruin`
- dlt project directory and pipeline name: fixture `.artifacts/dlt-project`,
  pipeline `dlt_commerce_clickhouse`
- dlt version and destination: dlt `1.30.0`, ClickHouse `24.8`
- Resources in scope: `customers`, `orders`, `order_events` (all three)
- Connection report location: `.artifacts/connection-report.yml`
- Inventory operator: fixture `run.sh`; no human pause is possible, so the Stage 2
  and Stage 4 answers come from `../fixtures/migration-decisions.yml`
- Current phase: `MVP_complete`

## Source and target inventory

| dlt resource | Source table | dlt destination table | Write disposition | Primary key | Merge key | Incremental cursor | Bruin asset | Isolated v0 target | Dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `customers` | `public.customers` | `migration.dlt_analytics___customers` | `replace` | `customer_id` | none | none | `bruin_v0.customers` | `bruin_v0.customers` | none |
| `orders` | `public.orders` | `migration.dlt_analytics___orders` | `merge` | `order_id` | none | `updated_at` | `bruin_v0.orders` | `bruin_v0.orders` | none |
| `order_events` | `public.order_events` | `migration.dlt_analytics___order_events` | `append` | `event_id` (ignored by append) | none | `event_ts` | `bruin_v0.order_events` | `bruin_v0.order_events` | none |

## Automated findings from the dlt project

- `dlt.pipeline(pipeline_name="dlt_commerce_clickhouse", destination="clickhouse",
  dataset_name="dlt_analytics")`, no staging destination, `progress=None`,
  `loader_file_format="jsonl"`.
- Source is `dlt.sources.sql_database.sql_database(schema="public")` restricted to
  three tables. Hints are applied per resource with `apply_hints`, with
  `dlt.sources.incremental(..., initial_value=datetime(2025, 1, 1))` on the two
  incremental resources.
- `.dlt/config.toml` sets `sources.sql_database.chunk_size = 50000`,
  `sources.sql_database.backend = "pyarrow"`, and
  `destination.clickhouse.dataset_table_separator = "___"`.
- **Destination naming differs.** dlt wrote `migration.dlt_analytics___<table>`
  because ClickHouse has no schema namespace and dlt prefixes the dataset. Bruin
  ingestr wrote a real database, `bruin_v0.<table>`. Downstream queries must be
  repointed. Recorded as an accepted, reviewed change.
- **Generated columns differ.** With the pyarrow backend dlt added no `_dlt_id`
  or `_dlt_load_id` to these tables. ingestr added
  `_ingestr_loaded_at Nullable(DateTime64(6, 'UTC'))`. Excluded from parity.
- **Type mapping matched exactly** between the two systems for this fixture:
  `BIGINT → Int64`, `TEXT → String`, `DATE → Date`,
  `TIMESTAMP → DateTime64(6)`.
- **dlt's ClickHouse merge soft-deletes asynchronously.** After the incremental
  pass, `system.tables.total_rows` reported 301,500 for the dlt orders table while
  `SELECT count()` reported the correct 300,500; the `ALTER TABLE ... UPDATE
  _row_exists` mutation had not yet merged parts. Row counts for dlt ClickHouse
  tables must come from `count()`, never from `system.tables`.
- Connection report: `postgres` populated `database, host, password, port,
  username` with `schema` and `ssl_mode` absent from dlt; `clickhouse` populated
  all seven fields. No field was left unmapped. No value was recorded.

## Strategy and key mapping decisions

| dlt resource | dlt write disposition | Bruin `materialization.strategy` | `incremental_key` | Asset primary keys | Rationale |
| --- | --- | --- | --- | --- | --- |
| `customers` | `replace` | `create+replace` | none | `customer_id` | Full reload each run; no cursor existed, so there is no window to preserve. `truncate+insert` was not needed because nothing depends on the table object surviving. |
| `orders` | `merge` | `merge` | `updated_at` | `order_id` | dlt's merge had a primary key, which is what an ingestr `merge` requires. |
| `order_events` | `append` | `append` | `event_ts` | `event_id` | Insert-only. The primary key is declared for metadata and duplicate detection only; append does not use it. |

## Column mappings

Every column is a straight pass-through: no cast, rename, default, or omission.
The only differences are generated columns.

| Resource | Source column | Target column | Type | Action |
| --- | --- | --- | --- | --- |
| `customers` | `customer_id, email, plan, country, signup_date, updated_at` | same | `Int64, String, String, String, Date, DateTime64(6)` | keep |
| `orders` | `order_id, customer_id, status, amount_cents, created_at, updated_at` | same | `Int64, Int64, String, Int64, DateTime64(6), DateTime64(6)` | keep |
| `order_events` | `event_id, order_id, event_type, event_ts` | same | `Int64, Int64, String, DateTime64(6)` | keep |
| all | — | `_ingestr_loaded_at` | `Nullable(DateTime64(6, 'UTC'))` | generated, excluded from parity |

`amount_cents` is an integer on purpose. A `NUMERIC` column would have made the
comparison depend on each engine's decimal scale rendering, which is a fixture
design choice, not a migration finding.

## Unsupported features and non-mappings

- dlt credentials, `~/.dlt` configuration, pipeline state, load packages, and
  deployment metadata were not migrated. The fixture's dlt state stayed under
  `.artifacts/` via `DLT_DATA_DIR`.
- dlt's incremental cursor state was not transferred. ingestr derived both windows
  from the Bruin run interval instead: `2025-01-01 → 2025-03-31` for history and
  `2025-04-01 → 2025-04-02` for the change set.
- The fixture contains no transformer, `add_map`, `add_filter`, `scd2`, custom
  `last_value_func`, nested table, or CDC resource. Those remain documented as
  unsupported in a plain ingestr asset; nothing here claims to migrate them.
- `bruin data-diff` cannot summarize a ClickHouse connection in CLI `v0.11.722`
  (bruin-data/bruin#1223), and the attempt exits 1 while printing nothing
  (bruin-data/bruin#2561). The gate was kept by diffing DuckDB projections of the
  same rows. This is a tooling gap, not an accepted data difference.

## Open human-review items — must be empty before a write

- [x] Initial-run scope: all three resources, history window `2025-01-01` to
  `2025-03-31`.
- [x] Isolated destination confirmed: ClickHouse database `bruin_v0`, separate
  from dlt's `migration` database.
- [x] Source and destination connection preflight passed with the converted
  connections.
- [x] Primary keys, incremental keys, materialization, and schema contract
  approved per resource.
- [x] Append windows confirmed disjoint: initial data ends `2025-03-30 23:59:59`,
  the change set starts `2025-04-01 06:00:00`.
- [x] Destination naming change reviewed and recorded.
- [x] Column mapping, quality checks, and validation boundary approved.
- [x] Ownership: the fixture is maintainer-owned; the dlt pipeline was never
  paused or modified.

## v0 run and validation evidence

- Requested scope and approval: all three resources, per
  `../fixtures/migration-decisions.yml`.
- `bruin validate`: 3 assets across 1 pipeline, no issues.
- Initial run: `bruin run target/pipeline.yml --start-date 2025-01-01
  --end-date 2025-03-31 --workers 1` — 200,000 / 300,000 / 500,000 rows,
  23 quality checks passed.
- Incremental run: `bruin run target/pipeline.yml --start-date 2025-04-01
  --end-date 2025-04-02 --workers 1` — customers fully reloaded (200,000),
  1,500 orders upserted, 1,000 events appended; 23 quality checks passed.
- Final counts, identical across PostgreSQL, dlt ClickHouse, and Bruin
  ClickHouse:

  | Table | Rows | Distinct keys | Null keys | Duplicate keys | Row checksum |
  | --- | --- | --- | --- | --- | --- |
  | `customers` | 200,000 | 200,000 | 0 | 0 | `17969692976280668231` |
  | `orders` | 300,500 | 300,500 | 0 | 0 | `8380077222790720011` |
  | `order_events` | 501,000 | 501,000 | 0 | 0 | `13563545329820441994` |

- Cursor ranges observed in the source: `orders.updated_at` `2025-01-01
  00:00:16` to `2025-04-01 07:00:00`; `order_events.event_ts` `2025-01-01
  00:00:16` to `2025-04-01 08:00:00`.
- `bruin data-diff --full --tolerance 0 --fail-if-diff`: six comparisons passed
  (source vs Bruin and dlt vs Bruin, per table) over the DuckDB comparison
  projections.
- Gate integrity: `assert_gate_fails.sh` confirmed the same command exits
  non-zero on a one-row difference.
- Mismatches: none. Accepted differences: `_ingestr_loaded_at`, and the
  destination naming change.

## Run history

### fixture run — `v0_run`

- Approved scope and source consistency boundary: the fixture's source is static
  between passes, so the boundary is the change set itself, applied once between
  the two passes and stamped inside `[2025-04-01 06:00, 2025-04-01 09:00]`.
- Connections: `dlt_source_postgres` (PostgreSQL 16.4), `dlt_target_clickhouse`
  (ClickHouse 24.8), both produced by the converter. Isolated target database
  `bruin_v0`.
- Commands and evidence: `scripts/run.sh`, evidence under
  `.artifacts/verification/fixture/`.
- Result: `passed`. All profiles agreed; all six data diffs passed.
- Next action: none for the fixture. A real migration would continue to the
  cutover checklist below.

## Completing the migration

Not performed. The fixture stops at a validated v0 and leaves the dlt pipeline as
the system of record, which is the behavior the prompt requires.

- [ ] Review pipeline/column metadata and any approved AI-assisted changes.
- [ ] Publish a pipeline README and assign an operating owner.
- [ ] Run final bounded reconciliation and document a rollback decision.
- [ ] Repoint downstream consumers from `migration.dlt_analytics___<table>` to
  `bruin_v0.<table>` and drop assumptions about dlt system columns.
- [ ] Enable approved Bruin scheduling, monitoring, alerting, and runbook.
- [ ] Pause the dlt pipeline only after the validation boundary and rollback
  window are satisfied, keeping its state for the rollback window.
- [ ] Retire dlt credentials, deployment, and legacy artifacts under change
  control.
