# dlt to Bruin migration plan

This is a reusable, reviewed plan template. During a runtime migration, replace
only the placeholder values after reading the dlt project and the converter's
non-secret connection report. Do not put credentials, connection strings, host
names, source data, or dlt cursor/state values in this file.

## Status and provenance

- Migration name: `TODO`
- dlt project directory and pipeline name: `TODO`
- dlt version and destination: `TODO`
- Resources in scope for this migration: `TODO`
- Connection report location: `.artifacts/dlt/TODO/connection-report.yml`
- Inventory time and operator: `TODO`
- Current phase: `inventoried | waiting_for_connections | drafting | waiting_for_run_approval | validating | MVP_complete`

## Source and target inventory

| dlt resource | Source table or query | dlt destination table | Write disposition / strategy | Primary key | Merge key | Incremental cursor | Proposed Bruin asset | Isolated v0 target | Dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `TODO` | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` |

## Automated findings from the dlt project

- `TODO`: record `pipeline_name`, `destination`, `dataset_name`, staging
  configuration, and whether the pipeline runs with a shared or per-run working
  directory.
- `TODO`: record every `apply_hints` and `@dlt.resource` argument per resource,
  plus `.dlt/config.toml` tuning such as `chunk_size`, `backend`, normalize
  settings, and destination-specific options.
- `TODO`: record the destination naming scheme dlt actually produced and the
  scheme Bruin ingestr will produce. They differ on destinations without real
  schemas; ClickHouse is the known case (`<dataset>___<table>` versus a real
  `<database>.<table>`).
- `TODO`: record the connection report's populated, missing, and unmapped field
  names. Never record a value.
- `TODO`: list every source-to-Bruin compatibility mismatch. Mark it as
  automated until a reviewer makes a decision.

## Route decision per resource — complete before drafting any asset

dlt has no connector catalogue, so each resource needs a target shape chosen and
justified first. Record the ingestr connector check even when the answer is no.

| dlt resource | Source kind | ingestr connector exists? | Route | Reason |
| --- | --- | --- | --- | --- |
| `TODO` | `database \| api \| file \| other` | `yes \| no \| n/a` | `ingestr \| ingestr_rewritten \| python_asset` | `TODO` |

- Route `ingestr`: database or warehouse source; configuration maps across.
- Route `ingestr_rewritten`: an ingestr connector exists for the API. This is a
  reimplementation — ingestr owns auth, pagination, and schema. `TODO`: record the
  schema differences and who approved them.
- Route `python_asset`: no connector, or custom Python in the resource. `TODO`:
  record what forced the port (paginator, `add_map`, transformer, custom cursor).

## Strategy and key mapping decisions

| dlt resource | dlt write disposition | Chosen Bruin `materialization.strategy` | `incremental_key` | Asset primary keys | Reviewer / rationale |
| --- | --- | --- | --- | --- | --- |
| `TODO` | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` |

## Hand-authored decisions

- Source and destination named Bruin connections: `TODO`.
- Target isolation and naming, including the destination naming change: `TODO`.
- Per-resource strategy, primary key, incremental key, explicit bounds, and
  schema contract: `TODO`.
- Delete/history/CDC/system-column behavior: `TODO`.
- Treatment of dlt generated columns (`_dlt_load_id`, `_dlt_id`,
  `_dlt_parent_id`) and of `_ingestr_loaded_at`: `TODO`.
- Scheduling, monitoring, alerting, ownership, and rollback: `TODO`.

## Column mappings

| dlt resource | Source column | Target column | Type/cast | Action | Rationale / reviewer |
| --- | --- | --- | --- | --- | --- |
| `TODO` | `TODO` | `TODO` | `TODO` | `keep \| rename \| cast \| default \| omit \| generated` | `TODO` |

## Unsupported features and non-mappings

- dlt credentials, `~/.dlt` configuration, pipeline state, working directory,
  load packages, retries, alerts, and deployment metadata are not migrated.
- dlt's incremental cursor state is not transferable. ingestr keeps its own
  state and derives the window from the Bruin run interval. `TODO`: record the
  approved migration boundary and how gaps and duplicates are prevented.
- `@dlt.transformer`, `add_map`, `add_filter`, `add_yield_map`, and any
  row-level Python in a resource cannot become a plain ingestr asset. `TODO`:
  record the selected Bruin Python or SQL asset design.
- Nested and child tables (`_dlt_parent_id`, `_dlt_list_idx`, dlt's
  `max_table_nesting`) have no ingestr equivalent. `TODO`: record the treatment.
- `merge` with `strategy="scd2"`, a custom `last_value_func`, or
  `last_value_func=min` has no direct ingestr equivalent. `TODO`: record the
  treatment.
- `merge_key` without a primary key is not an ingestr `merge`. `TODO`: confirm
  `delete+insert` on the approved key or a different design.
- dlt schema contracts at column and data-type granularity are coarser in
  ingestr's `schema_contract`. `TODO`: record the accepted difference.
- `TODO`: list destination features the generated ingestr asset cannot express.

## Open human-review items — must be empty before a write

- [ ] Exact initial-run scope: full history, bounded history, one resource, or
  another scope; list resources and explicit start/end bounds.
- [ ] Isolated destination target is confirmed; replace/truncate permission is
  explicit when relevant.
- [ ] Source/destination connection preflight passed using the converted
  connections.
- [ ] Primary keys, incremental keys, materialization, delete handling, and
  schema ownership are approved for each in-scope resource.
- [ ] Append-strategy windows are confirmed non-overlapping with anything
  already loaded.
- [ ] Destination naming change and the downstream queries it affects are
  reviewed.
- [ ] Column mapping, quality checks, validation boundary, expected cost, and
  rollback condition are approved.
- [ ] Schedule/monitoring ownership is assigned; the dlt pipeline remains active
  and untouched until cutover criteria are met.

## v0 run and validation evidence

- Requested scope and approval: `TODO`.
- `bruin validate` result: `TODO`.
- Run command, dates, and resulting target tables: `TODO`.
- Source profile: row count `TODO`, null keys `TODO`, duplicate keys `TODO`.
- Bruin target profile: row count `TODO`, null keys `TODO`, duplicate keys
  `TODO`.
- dlt target profile for the same resource: `TODO`.
- `bruin data-diff --full --tolerance 0 --fail-if-diff` result, including the
  connections compared and whether a comparison projection was required:
  `TODO`.
- Mismatches, accepted differences, and follow-up: `TODO`.

## Run history

Add one dated entry for every connection preflight, validation attempt, and v0
run. Keep detailed output only in `.artifacts/`; this plan records the reviewable
summary and the next human decision.

### `YYYY-MM-DDTHH:MM:SSZ` — `preflight | validation | v0_run`

- Approved scope and source consistency boundary: `TODO`.
- Source/target connections and isolated tables: `TODO`.
- Commands and evidence locations under `.artifacts/`: `TODO`.
- Result: `passed | failed | paused`; profile/data-diff outcome: `TODO`.
- Mismatches, rollback decision, owner, and next action: `TODO`.

## Completing the migration

Complete this section only after the user requests final review and metadata
updates.

- [ ] Review pipeline/column metadata and any approved AI-assisted changes.
- [ ] Publish a pipeline README and assign an operating owner.
- [ ] Run final bounded reconciliation and document a rollback decision.
- [ ] Refactor downstream assets, models, and dashboards away from dlt table
  names, dlt system columns, and the dlt dataset naming scheme.
- [ ] Enable approved Bruin scheduling, monitoring, alerting, and runbook.
- [ ] Pause the dlt pipeline only after the documented validation boundary and
  rollback window are satisfied. Keep its state intact for the rollback window.
- [ ] Retire dlt credentials, deployment, and legacy artifacts under the owner's
  change-control process.
