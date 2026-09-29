# Fixture build handoff

Updated after every build and validation step. Newest state at the top of each
section.

## Goal

Build a review-gated dlt-to-Bruin migration workflow under `bruin-dlt/`, modelled
on `bruin-fivetran/`, and prove it end to end against a local fixture: ~1M rows
in three PostgreSQL tables, a dlt pipeline loading them into ClickHouse with
three different write dispositions, then the migrated Bruin ingestr pipeline
loading the same rows, gated on exact parity and `bruin data-diff`.

Extended after review: dlt has no connector catalogue, so the track also has to
cover custom API sources. A fourth dlt resource hits a live public API with a
hand-rolled paginator and `add_map` transforms, and is migrated to a Bruin
**Python asset** rather than an ingestr asset.

## Current state

- Track surface complete: `README.md`, `dlt-bruin-prompt.md`, `plan.md`,
  `.agents/skills/bruin-dlt-migrator/{SKILL.md,convert_dlt_connections.py}`.
- Fixture complete: Postgres + ClickHouse Compose project, 1,000,000 seeded rows,
  two dlt pipelines (`replace`/`merge`/`append` over PostgreSQL, plus a custom
  PokeAPI resource), hand-authored Bruin target reference of three ingestr assets
  and one Python asset, reviewed decisions file, four fixture scripts, five gates,
  40 unit tests.
- Routing is now an explicit stage: Stage 2.5 in the prompt, a route table in
  `plan.md`, and a three-route table in the track `README.md`.
- Full clean end-to-end run: **passed.** `teardown → bootstrap → run → verify`
  from scratch: bootstrap 28 s, run 60 s, verify 22 s. `verify.sh` was run twice
  in a row to confirm it is idempotent.
- Evidence recorded in `target/plan.md`; the repository-root `README.md` track
  table now lists `bruin-dlt`.

## Files in flight

None. The track and the fixture are complete and green.

## Changed

Everything under `bruin-dlt/` is new. Outside the track:

- `README.md` (repository root): the track table gains a `bruin-dlt` row.
- Removed `~/.dlt/pipelines/dlt_commerce_clickhouse`, which an early fixture run
  created before `DLT_DATA_DIR` was wired up. The operator's other dlt pipelines
  were left untouched.

## Failed attempts and what they changed

1. **`bruin data-diff` directly against ClickHouse.** Exits 1 with no output on
   stdout or stderr; the internal error is "connection type does not support
   table summarization". ClickHouse is not in Bruin's supported summarization set
   in CLI `v0.11.722`. Kept the gate by projecting all three systems into DuckDB
   and diffing there, and documented the limitation in the track README.
2. **Converter self-check false positive.** The fixture password was `migration`,
   which is a substring of the repository path `bruin-migration`, so the
   report's own leak check refused to print. Fixed twice over: the check now
   scans only the report's value-bearing fields, not operator-supplied paths and
   names, and the fixture uses distinct `fixture-postgres-secret` /
   `fixture-clickhouse-secret` values that `verify.sh` can grep for.
3. **`system.tables.total_rows` as a row count.** It reported 301,500 for dlt's
   merged orders table while `SELECT count()` reported the correct 300,500: dlt's
   ClickHouse merge soft-deletes through an asynchronous `ALTER TABLE ... UPDATE`
   mutation on `_row_exists`. All parity checks use `count()` and plain `SELECT`.
4. **Associative arrays in `profile_and_diff.sh`.** `declare -A` fails under the
   bash 3.2 that ships with macOS. Replaced with plain `table:key` strings.
5. **A single fixture Bruin config holding the source and destination.** Replaced
   with a harness config that holds only the DuckDB comparison connections; the
   converter adds the migrated connections, so the fixture proves the converter's
   output actually works and exercises its merge path.
6. **The hygiene gate depended on `rg`, which silently disabled it.** Under a
   minimal `PATH`, `rg: command not found` made every `if rg ... ; then fail` guard
   fall through as "clean", so the leak checks passed without running. Only the
   positive control caught it. Replaced with `grep -r -F -q`, which is always
   present, and the positive control now also serves as proof the matcher works.
   Same silent-gate failure mode as bruin-data/bruin#2561, in our own script.
7. **Two converter field-mapping bugs, found by testing destinations the fixture
   does not use.** BigQuery produced only `project_id` and `location` and
   reported nothing missing, because dlt stores a service account as flat
   `private_key`/`client_email` fields while Bruin wants one
   `service_account_json` blob — the connection would have failed to
   authenticate while the report looked clean. Databricks was written with
   `http_path`, but Bruin's field is `path`. Both are fixed, with the field names
   now checked against the structs in `pkg/config/connections.go`; a GCP
   connection with no credential material is now a blocking error, and a whole
   service-account JSON supplied as a string is parsed. Four unit tests cover
   these paths. Lesson: the fixture only exercises PostgreSQL and ClickHouse, so
   every other mapping in `FIELD_MAPS` needs unit coverage rather than trust.

## Next steps

1. Open a PR for the track and have the mapping table in `README.md` reviewed by
   someone who has migrated a real dlt pipeline.
2. Track the two upstream issues. ClickHouse `data-diff` support was already open
   as bruin-data/bruin#1223, so no duplicate was filed; field evidence was added
   as a comment. The silent exit 1 was not reported and is now
   bruin-data/bruin#2561, with an offer to send the `main.go` fix. Drop the DuckDB
   projection step once #1223 lands.
3. Consider a second fixture resource that exercises `merge_key` without a
   primary key, so the `delete+insert` mapping is covered by a run and not only
   by documentation.
4. Decide whether route 2 — an API that ingestr *does* have a connector for —
   needs its own fixture case. It is the one route with no runnable proof, and it
   is the riskiest, because it is a reimplementation whose schema may differ from
   dlt's.
5. Consider replacing the live PokeAPI call with a recorded fixture if offline
   runs become a requirement. Today `run.sh` needs network for that one resource.

## Step log

### Step 1 — research and feasibility

- Confirmed the Bruin ingestr ClickHouse destination supports `replace`,
  `append`, `merge`, `delete+insert`, and `truncate+insert`.
- Confirmed dlt's ClickHouse destination loads directly, with no staging bucket,
  and supports all write dispositions.
- Found that Bruin writes a real `database.table` on ClickHouse while dlt writes
  `<dataset>___<table>` in one database. Recorded as a migration decision.
- Found the ClickHouse `data-diff` gap described above.

### Step 2 — fixture provisioning

- Compose project `bruin_dlt_<workspace>` with PostgreSQL `16.4-alpine` and
  ClickHouse `24.8-alpine` on dynamic loopback ports, named volumes only.
- Seeded 200,000 + 300,000 + 500,000 = 1,000,000 deterministic rows.

### Step 3 — dlt source pipeline

- Initial dlt load: 200,000 / 300,000 / 500,000 rows into
  `migration.dlt_analytics___*`. Completed in ~14 s.

### Step 4 — connection conversion

- The converter produced working `postgres` and `clickhouse` Bruin connections
  from `.dlt/secrets.toml`; both passed `bruin connections test`. The report
  listed field names only.

### Step 5 — Bruin target reference and v0 run

- `bruin validate`: 3 assets, no issues.
- Initial window `2025-01-01 → 2025-03-31`: 200,000 / 500,000 / 300,000 rows
  loaded, all 23 column checks passed.
- Incremental window `2025-04-01 → 2025-04-02`: 200,000 (full reload) / 1,000
  appended / 1,500 upserted. Final counts 200,000 / 300,500 / 501,000.

### Step 6 — parity

- Three-way exact parity passed on 1,001,500 rows: row counts, distinct keys,
  key checksums, and row checksums matched across source, dlt, and Bruin.
- `bruin query` profiles agreed for all three systems on all three tables.
- Six `bruin data-diff --full --tolerance 0 --fail-if-diff` comparisons passed
  (source vs Bruin and dlt vs Bruin, per table).
- Gate self-test confirmed the diff fails on a one-row difference.
- 40 unit tests pass.

### Step 7 — custom API source and the Bruin Python asset

- Added `source/dlt_api_pipeline.py`: a dlt resource over `https://pokeapi.co`
  with a hand-rolled `?limit=&offset=` paginator, an id parsed out of a URL, two
  `add_map` transforms, and `merge` on the derived key. dlt loaded 60 rows into
  `migration.dlt_api___pokemon`.
- Added `target/assets/pokemon.py`, a Bruin Python asset. `materialize()` returns
  a DataFrame; Bruin loads it through ingestr. The paginator and both transforms
  were ported unchanged; `requirements.txt` sits beside the asset so Bruin's
  upward search does not pick up the fixture's own dlt dependencies.
- Confirmed the generated-column difference is real and asymmetric: the dlt API
  table carries `url`, `_dlt_load_id`, and `_dlt_id`; the Bruin table carries only
  the four declared columns plus `_ingestr_loaded_at`. Dropping `url` is a recorded
  column-mapping decision, since it feeds the transform but is not target schema.
- Parity: 60 rows, 60 distinct keys, identical row checksums, and a passing
  `bruin data-diff` between dlt and Bruin. The full run is now 4 assets and 29
  quality checks over two passes.
- Added `tests/test_python_asset_port.py`: extracts both implementations with
  `ast` and fails if the ported paginator, transforms, or shared constants drift.
  It needs neither network nor `dlt`/`pandas` installed.
- Taught `assert_target_matches_decisions.py` to parse `@bruin` blocks, and made
  it reject a Python asset with no recorded `port_reason` or one where an ingestr
  connector was available.
