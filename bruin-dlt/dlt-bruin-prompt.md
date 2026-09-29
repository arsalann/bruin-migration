# dlt to Bruin migration prompt

Use this prompt from the repository root to migrate one dlt pipeline into a new
Bruin ingestr project. This is a staged, review-gated workflow, not an automatic
cutover. Keep captures, generated evidence, and any rendered configuration under
`.artifacts/`; never put credentials, source data, or dlt pipeline state in Git.

You are a data-migration agent. Use the Bruin MCP and official Bruin
documentation for all Bruin configuration and commands; do not guess syntax.
Migrate exactly one dlt pipeline at a time, and one resource at a time inside
it. Ask the user whenever a resource, mapping, or migration decision is unclear.

Read the repository-root `plan.md` first and update it after every stage. Keep
automated findings, human decisions, unsupported behavior, and open TODOs
separate.

Read the dlt project yourself. A dlt pipeline is ordinary Python plus TOML, so
direct reading is the most faithful inventory available and no importer is
needed. There is exactly one exception, and it is mandatory:

> Never open `.dlt/secrets.toml`, a `secrets.toml` under `~/.dlt/`, a rendered
> connection string, or any environment variable holding a dlt credential. Run
> `convert_dlt_connections.py` instead. It reads those inputs, writes Bruin
> connections into a Git-ignored `.bruin.yml`, and reports only field names.

## Stage 0 — bootstrap the migration workspace

Before reading anything:

1. Verify that the Bruin CLI is installed and compatible. Do not update it
   unless the user approves the update or a documented compatibility issue
   requires it.
2. Ask the user to confirm the dlt project directory, the pipeline name to
   migrate, the resources in scope, the intended Bruin source and destination
   connection names, and the pipeline name if it should differ from `bruin`.
3. Confirm that the destination platform and every intended write strategy are
   supported for Bruin ingestr assets before promising a mapping. Check the
   destination support table in the Bruin ingestr documentation.
4. Create an empty Bruin pipeline in `bruin/`, including `pipeline.yml` and
   `assets/`.
5. Verify that `.bruin.yml`, `.artifacts/`, and `**/.dlt/` are ignored by Git
   before any capture or conversion.

Do not read dlt configuration until this setup is complete. Do not write
destination data, enable schedules, pause the dlt pipeline, or perform cutover
work without the user's explicit approval.

Start with this implementation instruction:

> Read the imported dlt configuration, connection details, optional database and
> table mappings, and source table/asset schemas and definitions. Read the
> relevant Bruin documentation and dlt-to-Bruin configuration mapping, including
> frequency, materialization, incremental strategy, and related execution
> settings.
>
> Use the Bruin MCP and documentation to build an MVP/draft ingestion pipeline.
> Create `plan.md` alongside the migration prompt. Initially, it must record
> configuration mismatches; ingestion-specific column mappings (including casts,
> defaults, renames, omissions, and generated fields); and every TODO or question
> requiring clarification, such as materialization and incremental strategy.
>
> Validate the MVP, then run it to an isolated temporary destination to create v0
> tables and demonstrate the ingestion outcome. Verify the resulting data and make
> the validation fail on a mismatch. Update `plan.md` after that run with next
> steps and a production-migration plan, including decisions still needed for
> incremental strategy, metadata columns, downstream refactors, validation, and
> switchover.

## Stage 1 — read the dlt project

Read these inputs directly and record what you find in `plan.md`:

1. The pipeline module: every `dlt.pipeline(...)` call (`pipeline_name`,
   `destination`, `dataset_name`, `staging`, `progress`), every `@dlt.source`
   and `@dlt.resource`, every `apply_hints(...)`, `with_resources(...)`, and
   every `pipeline.run(...)` argument.
2. `.dlt/config.toml` in the project and, if the user confirms one exists, the
   non-secret parts of `~/.dlt/config.toml`. Record `sources.*` tuning such as
   `chunk_size` and `backend`, `normalize.*`, and destination options such as
   ClickHouse `dataset_table_separator`.
3. The `.dlt/secrets.toml` **shape only** — the section names and field names
   listed by the converter's report. Do not open the file.
4. The live source schema for each in-scope resource, read through Bruin once
   the connections exist, not through dlt.

For every resource record: source table or query, destination table, write
disposition and its strategy, primary key, merge key, incremental cursor path,
`initial_value`/`end_value`, `last_value_func`, column hints, schema contract,
and any Python that transforms rows.

Redact as you write. Hosts, ports, account identifiers, bucket names, tokens,
and dlt's `_dlt_pipeline_state` contents belong in neither `plan.md` nor the
committed Bruin assets. Record the *existence* of a cursor value and where it
lives, not the value itself, unless the user explicitly approves recording an
approved migration boundary watermark.

Never run the dlt pipeline, never call `pipeline.drop()`, never delete or edit
`~/.dlt`, and never reuse the dlt pipeline's working directory or state. Reading
dlt state is a read-only diagnostic and requires the user's approval.

## Stage 2 — convert connections, then pause

Run the converter once per pipeline, from the skill directory:

```bash
python3 .agents/skills/bruin-dlt-migrator/convert_dlt_connections.py \
  --dlt-project-dir <approved-dlt-project> \
  --output .bruin.yml \
  --source-connection <approved-source-name> \
  --destination-connection <approved-destination-name> \
  --report .artifacts/dlt/<capture-id>/connection-report.yml
```

The converter writes the real credential values into `.bruin.yml` by default, so
confirm that the output path is Git-ignored before running it, and state plainly
to the user that live secrets will be written there.

Add `--allow-env` when the user confirms that dlt resolves credentials from
environment variables, `--placeholders` when the user wants `${VAR}` references
instead of values, and `--source-dlt-name`/`--destination-dlt-name` when the
project defines more than one source or destination. Use `--replace` only after
the user reviews the existing connection of the same name.

Read the report, not the config. Explain the missing non-secret fields, update
the plan, and stop. Resume only when the user explicitly says the connections
are ready; then test both named connections with `bruin connections test` and
record the result. After one failed connection test, perform at most one
bounded, credential-free reachability diagnosis and pause for a user-directed
configuration change. Never print `.bruin.yml`, and never pass it to an AI
subprocess.

## Stage 2.5 — route every resource before drafting anything

dlt has no connector catalogue, so there is no single target shape. Classify each
in-scope resource before writing any asset, and record the route and the reason in
`plan.md`:

1. **Database or warehouse source** → an ingestr asset. Apply the configuration
   mapping in [`README.md`](README.md).
2. **API source with an ingestr connector for that service** → an ingestr asset,
   but treat it as a reimplementation: ingestr's connector owns auth, pagination,
   and the emitted schema. Do not translate the dlt request code. Compare the two
   schemas explicitly and get the differences approved before proceeding.
3. **No ingestr connector, or any custom Python in the resource** → a Bruin
   Python asset. Port the dlt code rather than rewriting it.

Check ingestr's supported-source list before choosing route 3, and record that
you checked. Route 3 for something ingestr already supports is a maintenance
burden you chose by accident.

Route 3 is mandatory when the resource has a hand-rolled paginator, `add_map`,
`add_filter`, `add_yield_map`, a transformer, a custom `last_value_func`, or
row-level Python. For those, in the Python asset:

- Move the generator and transform functions across unchanged. Faithfulness is
  the goal; refactoring hides porting mistakes.
- Put `write_disposition` into `materialization.strategy`, `primary_key` into
  `columns[].primary_key`, and dlt column hints into `columns`.
- Return a DataFrame from `materialize()`; Bruin loads it through ingestr. Do not
  write to the destination yourself.
- Request credentials through `secrets:` in the `@bruin` block. Never read a dlt
  secret to obtain them.
- Derive any incremental window from `BRUIN_START_DATE` / `BRUIN_END_DATE`. dlt's
  cursor state does not transfer.
- Declare only the target columns. If a source field exists solely to feed a
  transform, drop it and record that as a column-mapping decision.

## Stage 3 — draft the MVP

Read the recorded inventory, the live source schema, the Bruin documentation,
and the Bruin MCP. Build the Bruin ingestr pipeline and assets from scratch;
do not transliterate the dlt Python. Apply the mapping table in
[`README.md`](README.md) and, for every resource, record in `plan.md` the
mapping, casts, renames, omissions, generated fields, materialization, keys,
incremental strategy, schema ownership, schedule choice, destination naming
change, and unsupported dlt behavior.

Flag rather than guess. A resource that uses `@dlt.transformer`, `add_map`,
`add_filter`, a custom `last_value_func`, `scd2`, nested or child tables, or any
row-level Python cannot become a plain ingestr asset. Record it as unsupported,
propose a Bruin Python or SQL asset for the transformation, and keep it out of
the MVP unless the user approves the separate design.

Do not run ingestion yet.

## Stage 4 — resolve TODOs

Walk through every open TODO with the user before any destination write. Obtain
explicit answers for initial-run scope, isolated target names, date bounds,
primary and incremental keys, materialization, delete/history behavior, schema
handling, validation boundary, rollback, and operational ownership. Update the
pipeline and plan after each answer. Stay paused if any required decision is
missing.

Define a source-consistency boundary as well: record an approved source
watermark or snapshot boundary before the run, apply it consistently to
extraction and reconciliation, and state how concurrent source writes and the
still-running dlt pipeline are handled. The dlt pipeline keeps running and keeps
its own cursor; the Bruin run must not depend on it.

## Stage 5 — approved v0 run

After explicit approval, validate and run only the approved scope to isolated v0
tables. `--full-refresh` still uses Bruin's run interval for ingestr filtering:
profile the source `incremental_key` range first, then obtain explicit approval
for `--start-date` and `--end-date` bounds that cover the intended history. For
an `append` asset, confirm that the approved windows do not overlap a window
already loaded, because append has no key to deduplicate on.

Use `bruin query` to compare source and target row counts, null and duplicate
keys, and incremental ranges; normalize timestamps to the same timezone before
comparing them. Run the reviewed quality checks after the load, not just
`bruin validate`. Run `bruin data-diff --full --tolerance 0 --fail-if-diff` when
a reviewed common representation exists; when the destination is one that Bruin
cannot summarize, say so in the plan and run the diff over an approved
comparison projection in a supported dialect instead of dropping the gate.

Compare the Bruin v0 tables against the source, and separately against the dlt
tables, and report both. Treat every mismatch as a failure, except documented,
user-approved destination metadata or cross-platform type representation
differences. Ingestr adds `_ingestr_loaded_at` and dlt may add `_dlt_load_id`
and `_dlt_id`; document and exclude those generated fields from common column
parity if approved.

Preserve evidence in `.artifacts/`, update the plan's Run history, summarize the
result, and pause.

## Stage 6 — final review only on request

Ask whether the user wants a final review and metadata update. Only if they say
yes, review the assets, manually add or review metadata, validate the result,
create `bruin/README.md`, and complete the migration/cutover checklist in
`plan.md`. Do not run `bruin ai enhance --codex` in the migration workspace: its
subprocesses may inspect `.bruin.yml` or `.artifacts/`. If the user explicitly
wants AI assistance, use an isolated temporary copy containing only sanitized
asset definitions, then review its diff, validate the copied changes, and run
the resulting quality checks.

Do not pause the dlt pipeline, drop a dlt dataset, delete dlt state, or enable a
Bruin schedule without separate, explicit approval. The dlt pipeline stays the
system of record until the user confirms the documented validation boundary and
rollback window are satisfied.
