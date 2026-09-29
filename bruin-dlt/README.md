# dlt to Bruin ingestr

Status: agent migration template with a runnable regression fixture.

This track migrates one dlt pipeline into a new Bruin ingestr project through a
staged, review-gated workflow. The runtime surface is:

| File | Purpose |
| --- | --- |
| [`dlt-bruin-prompt.md`](dlt-bruin-prompt.md) | The staged migration prompt the user runs |
| [`plan.md`](plan.md) | The reviewed plan template kept current through every stage |
| [`.agents/skills/bruin-dlt-migrator/SKILL.md`](.agents/skills/bruin-dlt-migrator/SKILL.md) | Skill entry point and safety rules |
| [`.agents/skills/bruin-dlt-migrator/convert_dlt_connections.py`](.agents/skills/bruin-dlt-migrator/convert_dlt_connections.py) | The only automated step: dlt credentials to Bruin connections |
| [`example/`](example/README.md) | Maintainer-only regression fixture; not part of the user-facing tool |

## Migration method at a glance

**Approach**

- **One pipeline at a time, one resource at a time** — scope stays small enough to verify and reverse.
- **The agent reads the dlt project directly** — pipeline Python and `config.toml` are plain configuration, so there is no importer.
- **One script converts credentials** — it writes Bruin connections and reports only field names, so no secret enters the agent's context.

**Mapping**

- **Write disposition becomes a write strategy** — `replace`, `append`, and `merge` map onto Bruin `materialization.strategy`.
- **Incremental cursor becomes the incremental key** — dlt's `cursor_path` becomes `materialization.incremental_key`.
- **Primary keys move into column metadata** — dlt's `primary_key` hint becomes `columns[].primary_key`, which `merge` requires.
- **Incremental state does not transfer** — ingestr keeps its own, so each load window comes from the Bruin run interval.
- **Unsupported dlt Python is flagged, not guessed** — transformers, `scd2`, and nested tables need a separate Bruin design.

**Control and proof**

- **Every decision and gap lands in `plan.md`** — automated findings, human choices, and open TODOs stay separate.
- **The workflow pauses before any destination write** — connection review and TODO resolution are hard gates, not reminders.
- **The first load targets isolated v0 tables** — production tables are never written during validation.
- **Parity is the pass/fail gate** — row counts, keys, and a zero-tolerance `bruin data-diff` must all agree.
- **dlt stays the system of record** — it is never paused, dropped, or cut over without explicit approval.

## What is being migrated

A dlt pipeline is a Python program. It builds sources and resources, attaches
hints (write disposition, primary key, incremental cursor, column types),
persists incremental state in a pipeline working directory, and loads into a
destination. The target is a declarative Bruin `ingestr` asset plus a Bruin
connection configuration.

Almost all of that is plain, readable configuration. The migration is therefore
a reading-and-mapping exercise, not a conversion-tool exercise.

## Why there is one script and no importer

The build rule for this track was to prefer direct reading and to justify any
script only where direct parsing is fragile. The evaluation:

| dlt input | Approach | Why |
| --- | --- | --- |
| Pipeline Python, `@dlt.resource`, `apply_hints`, `pipeline.run` | Agent reads it | Static, small, and full of intent an extractor would flatten away. An AST-based extractor would also be defeated by any dynamically built source, which is common in dlt. |
| `.dlt/config.toml` | Agent reads it | Non-secret TOML. Reading it directly is exact. |
| Source schemas | Agent reads them through Bruin | The live source is the authority, not dlt's cached schema. |
| dlt pipeline state and load packages | Not read | Not transferable, and reading it invites accidental mutation of a live pipeline. |
| **`.dlt/secrets.toml`, connection strings, credential environment variables** | **Script** | **This is the fragile case.** A credential must not enter the agent's context, and dlt accepts the same credential in at least three shapes: a TOML table, a single connection-string URL, and `SOURCES__<NAME>__CREDENTIALS__<FIELD>` environment variables. Asking an agent to "read it but do not remember it" is not a control. |

So `convert_dlt_connections.py` exists to move credentials from dlt to Bruin
without an agent ever seeing one.

**By default it writes the real secret values.** Passwords, tokens, private keys,
AWS secret access keys, and reassembled GCP service-account JSON are copied
verbatim from dlt into the Bruin connection. That is the point of the script: the
output is a working `.bruin.yml`, not a template. Two consequences follow:

- The output must be Git-ignored. The script writes it with mode `600` and the
  workflow verifies the ignore rule before running.
- The agent must not read the output afterwards. Reading it would reintroduce
  exactly the exposure the script exists to prevent.

Use `--placeholders` when you would rather not have values in a file at all: it
writes `${SOURCE_POSTGRES_PASSWORD}`-style references, and never reads the secret
into the written document. The resulting connection needs those variables set at
run time.

Either way the script prints only a non-secret report: which connections were
written, which Bruin fields were populated, whether each value came from TOML or
the environment, which required fields are still missing, and which dlt fields
have no Bruin mapping. Before printing, it checks its own report against every
credential value it read.

Credential shapes it handles: TOML tables, a single connection-string URL, dlt's
`SOURCES__<NAME>__CREDENTIALS__<FIELD>` environment variables (with
`--allow-env`), and a whole service-account JSON document supplied as a string.
For GCP it reassembles dlt's flat `private_key`/`client_email` fields into the
single `service_account_json` blob Bruin expects, and treats a GCP connection
with no credential material at all as a blocking error rather than an optional
missing field.

Nothing else is automated. There is deliberately no asset generator: the
strategy, key, and boundary decisions in the table below are the migration, and
a generator would turn them into silent defaults.

## Scope: not every dlt resource becomes an ingestr asset

dlt has no built-in connector catalogue. A dlt source is Python, so there is no
connector-to-connector mapping to make. Each resource takes one of three routes,
and choosing between them is the first real decision of the migration.

| Route | When | Target | Nature of the work |
| --- | --- | --- | --- |
| **1. ingestr asset** | Database or warehouse source | `type: ingestr` | **Migration.** Config maps across; see the tables below. |
| **2. ingestr asset, rewritten** | API source *and* ingestr ships a connector for it | `type: ingestr` | **Reimplementation.** ingestr's connector owns auth, pagination, and schema; the dlt code is discarded, not translated. Schemas may differ — diff them before accepting. |
| **3. Bruin Python asset** | No ingestr connector, or custom Python in the resource | `type: python` | **Port.** The dlt code moves nearly unchanged into `materialize()`. |

Route 3 is required whenever the resource contains a hand-rolled paginator,
`add_map`/`add_filter`, a transformer, a custom `last_value_func`, or any
row-level Python. Check ingestr's connector list before assuming route 3: if a
connector exists, route 2 is usually cheaper to operate, at the cost of a schema
that is ingestr's rather than yours.

### dlt resource to Bruin Python asset

| dlt | Bruin Python asset |
| --- | --- |
| `@dlt.resource(...)` decorator args | the `@bruin` block's `materialization` and `columns` |
| resource generator body | called from `materialize()`, unchanged |
| `add_map` / `add_filter` transforms | plain functions, unchanged |
| `write_disposition` | `materialization.strategy` |
| `primary_key` | `columns[].primary_key` |
| `columns={...}` hints | the `@bruin` block's `columns` |
| `pipeline.run(...)` | Bruin runs the asset; `materialize()` returns a DataFrame |
| `dlt.secrets` / `dlt.config` | `secrets:` in the `@bruin` block, injected as connection JSON |
| destination client | none — Bruin loads the returned frame through ingestr |
| `dlt.sources.incremental` | `BRUIN_START_DATE` / `BRUIN_END_DATE` read in Python |

What does **not** carry over: dlt's state, retries, and load packages. An
incremental Python asset must derive its own window from the Bruin run interval.

The fixture demonstrates route 3 end to end against
[pokeapi.co](https://pokeapi.co) — a hand-rolled paginator and two `add_map`
transforms, ported into a Python asset whose output is then diffed against the
dlt table it replaced.

## Connection mapping

The converter maps a dlt source drivername or destination name onto a Bruin
connection type. Field names come from `pkg/config/connections.go` in the Bruin
CLI rather than from prose, and every row below is covered by a unit test.

A missing **required** field is reported as blocking, and the workflow stops until
a human supplies it. A missing optional field is reported and left alone. Nothing
is ever invented.

| dlt name | Bruin type | Applies to | Required fields | Also mapped when present |
| --- | --- | --- | --- | --- |
| `postgres`, `postgresql` | `postgres` | source + destination | `host`, `port`, `database`, `username`, `password` | `schema`, `ssl_mode` |
| `mysql` | `mysql` | source | `host`, `port`, `database`, `username`, `password` | — |
| `mssql` | `mssql` | source + destination | `host`, `port`, `database`, `username`, `password` | — |
| `synapse` | `mssql` | destination | `host`, `port`, `database`, `username`, `password` | — |
| `redshift` | `redshift` | destination | `host`, `port`, `database`, `username`, `password` | `ssl_mode` |
| `clickhouse` | `clickhouse` | source + destination | `host`, `port`, `database`, `username`, `password` | `http_port`, `secure` |
| `snowflake` | `snowflake` | source + destination | `account`, `username`, `database` | `password`, `private_key`, `warehouse`, `schema`, `role` |
| `bigquery` | `google_cloud_platform` | destination | `project_id`, and one of `service_account_json` / `service_account_file` / `access_token` | `location` |
| `databricks` | `databricks` | destination | `host`, `path`, `token` | `catalog`, `schema` |
| `athena` | `athena` | destination | `region` | `access_key_id`, `secret_access_key`, `query_results_path` |
| `duckdb` | `duckdb` | source + destination | `path` | — |
| `motherduck` | `motherduck` | destination | `database`, `token` | — |

Redshift also appears as a source through the `postgresql` drivername, which maps
to `postgres`. Anything not listed fails with an explicit error naming the
supported types, rather than producing a half-filled connection.

### Field names that change

Most fields carry across unchanged. These do not, and they are the ones worth
checking in a review:

| dlt field | Bruin field | Where |
| --- | --- | --- |
| `drivername` | (selects the connection type) | any SQL source |
| `host` | `account` | Snowflake |
| `http_path` | `path` | Databricks |
| `access_token` | `token` | Databricks |
| `password` | `token` | MotherDuck |
| `region_name` | `region` | Athena |
| `query_result_bucket` | `query_results_path` | Athena |
| `database` | `path` | DuckDB |
| `sslmode` | `ssl_mode` | PostgreSQL, Redshift |
| `private_key` + `client_email` + `project_id` | assembled into `service_account_json` | BigQuery |

### How far each mapping is proven

- **PostgreSQL and ClickHouse are proven end to end.** The fixture converts them
  from a real `.dlt/secrets.toml`, passes `bruin connections test`, and loads a
  million rows through the resulting connections.
- **Every other type is verified at the field-mapping level by unit tests.** The
  field names are checked against the Bruin structs and the converter's output is
  asserted key by key, but no live connection is made to those platforms.

Treat the second group as reviewed, not as field-tested: run
`bruin connections test` before trusting one, which the workflow requires anyway.

## Configuration mapping

Verified against Bruin CLI `v0.11.722` and dlt `1.30.0`.

### Write disposition to write strategy

| dlt | Bruin ingestr | Notes |
| --- | --- | --- |
| `write_disposition="replace"` | `materialization.strategy: create+replace` | dlt's default replace strategy is `truncate-and-insert`; use `truncate+insert` instead when the destination table object, its grants, or its engine settings must survive the load. |
| `write_disposition="append"` | `append` | No key to deduplicate on. Approved run windows must not overlap an already-loaded window. |
| `write_disposition="merge"` with `primary_key` | `merge` | Requires both `incremental_key` and at least one `columns[].primary_key: true`. |
| `write_disposition="merge"` with only `merge_key` | `delete+insert` | Not an ingestr `merge`. Confirm the delete key with the user. |
| `write_disposition={"disposition": "merge", "strategy": "upsert"}` | `merge` | Equivalent intent. |
| `write_disposition={"disposition": "merge", "strategy": "scd2"}` | none | No ingestr equivalent. Needs a separate Bruin design. |
| `write_disposition="skip"` | asset `enabled: false` or omitted | Record why the resource is skipped. |

### Incremental loading

| dlt | Bruin ingestr |
| --- | --- |
| `dlt.sources.incremental("<cursor_path>")` | `materialization.incremental_key: <cursor_path>` |
| `initial_value` / `end_value` | `bruin run --start-date` / `--end-date` |
| `last_value_func=max` (default) | Implicit; ingestr advances forward |
| `last_value_func=min` or a custom callable | No equivalent — flag it |
| `primary_key=(...)` | One `columns[].primary_key: true` per key column |
| `merge_key` | No direct equivalent; use `delete+insert` on the approved key |
| Cursor state in the pipeline working directory | Not transferable; ingestr keeps its own state and derives the window from the Bruin run interval |
| `refresh="drop_sources"` / `drop_resources` | An approved `create+replace` run, or `--full-refresh` with explicit bounds |

### Schema, columns, and tuning

| dlt | Bruin ingestr |
| --- | --- |
| `columns={...}` type hints | `columns` plus `parameters.enforce_schema: true` |
| `schema_contract` (`evolve`, `freeze`, `discard_row`, `discard_value`) | `parameters.schema_contract`, same vocabulary |
| `sources.<name>.chunk_size` | `parameters.page_size` |
| `sources.<name>.backend` (`sqlalchemy`, `pyarrow`) | `parameters.sql_backend` |
| `loader_file_format` | `parameters.loader_file_format` |
| `parallelize()` on a resource | `parameters.extract_parallelism` (plus `extract_partition_by`) |
| `max_table_nesting`, child tables | No equivalent — flag it |
| A `query:` style custom SQL resource | `source_table: "query:select ... where updated_at > :interval_start"` |

### Naming, state, and generated columns

| dlt | Bruin ingestr |
| --- | --- |
| `pipeline_name` | Not migrated; Bruin identifies the pipeline by `pipeline.yml` `name` |
| `dataset_name` | The schema/database part of the asset `name` |
| `_dlt_load_id`, `_dlt_id` | Not produced by ingestr |
| `_dlt_parent_id`, `_dlt_list_idx` | Not produced by ingestr |
| (none) | `_ingestr_loaded_at` is added by ingestr |

## Destination naming changes

On destinations that have no real schema namespace, dlt prefixes the dataset onto
the table name using `dataset_table_separator` (default `___`), while Bruin
ingestr writes a real `database.table`. In the fixture, dlt produced
`migration.dlt_analytics___orders` and Bruin produced `bruin_v0.orders` from the
same source table.

This is a migration decision, not a detail: every downstream query, dashboard,
and model that names a dlt table has to be rewritten. Record it in `plan.md`
before the v0 run.

## Known gaps and human review

- **`bruin data-diff` cannot summarize ClickHouse.** `pkg/clickhouse` has no
  `GetTableSummary`, so a ClickHouse connection never satisfies
  `diff.TableSummarizer`. Tracked upstream in
  [bruin-data/bruin#1223](https://github.com/bruin-data/bruin/issues/1223). The
  supported set is DuckDB, BigQuery, PostgreSQL, Redshift, Snowflake, and
  MongoDB. When the destination is unsupported, keep the gate by diffing an
  approved comparison projection in a supported dialect and say so in the plan.
  The fixture does exactly that.
- **That failure is silent, so do not trust a bare non-zero exit.** In CLI
  `v0.11.722`, `bruin data-diff` against ClickHouse exits `1` and prints nothing
  on stdout or stderr, even with `--debug`: `main.go` passes the error to
  `cli.HandleExitCoder`, which discards errors that are not `cli.ExitCoder`.
  Under `--fail-if-diff` that makes "this platform cannot be diffed"
  indistinguishable from "the data differs". Reported as
  [bruin-data/bruin#2561](https://github.com/bruin-data/bruin/issues/2561).
  Until it is fixed, treat an empty diff output as an unrun gate, not a passing
  one.
- dlt resources can contain arbitrary Python. Transformers, `add_map`,
  `add_filter`, custom cursor functions, and nested-data flattening have no
  ingestr equivalent and must be ported as Bruin Python or SQL assets and
  validated separately.
- dlt's incremental state cannot be handed over. Any migration needs an approved
  boundary watermark, and `append` resources need non-overlapping windows to
  avoid duplicate rows.
- dlt deployment metadata, schedules, retries, and alerting do not migrate.
  Recreate them in the target operating environment.
- Type representation differs across engines even when values match. Confirm what
  counts as an accepted difference before treating a diff as a failure.

## Official references

- [dlt incremental loading](https://dlthub.com/docs/general-usage/incremental-loading),
  [SQL database source](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database),
  [ClickHouse destination](https://dlthub.com/docs/dlt-ecosystem/destinations/clickhouse).
- [dlt incremental troubleshooting](https://dlthub.com/docs/general-usage/incremental/troubleshooting)
  — pipeline name, destination, dataset, and state must stay stable across runs.
- [Bruin ingestr assets](https://getbruin.com/docs/bruin/assets/ingestr.html),
  [Bruin ClickHouse platform](https://getbruin.com/docs/bruin/platforms/clickhouse.html),
  [Bruin data-diff](https://getbruin.com/docs/bruin/commands/data-diff.html).
