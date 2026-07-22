# bruin-migration

Evidence-backed migration research and runnable reference implementations for moving analytics workloads to the Bruin ecosystem.

The repository includes four migration tracks:

| Track | Source | Target | Reference implementation |
| --- | --- | --- | --- |
| [`bruin-dac-metabase`](bruin-dac-metabase/README.md) | Metabase dashboards | DAC | Dockerized Metabase + PostgreSQL, imported and checked dashboard |
| [`bruin-ingestr-dlt`](bruin-ingestr-dlt/README.md) | dlt pipeline | ingestr / Bruin | PostgreSQL source, dlt and Bruin loads into separate DuckDB files |
| [`bruin-ingestr-fivetran`](bruin-ingestr-fivetran/README.md) | Fivetran PostgreSQL connector | ingestr / Bruin | Four Cloud SQL-to-BigQuery ingestr assets with isolated comparison tables |
| [`bruin-cli-sqlmesh`](bruin-cli-sqlmesh/README.md) | SQLMesh project | Bruin CLI | DuckDB SQLMesh project and equivalent Bruin assets |

## Repository contract

Every migration track is named `bruin-<target>-<source>`. Fixture-backed tracks follow this layout:

```text
bruin-<target>-<source>/
  README.md                 # research, inventory, scope, and gaps
  example/
    README.md               # prerequisites and exact commands
    fixtures/               # deterministic sample data and source inputs
    source/                 # source-platform implementation
    target/                 # hand-authored Bruin/DAC reference implementation
    scripts/                # idempotent bootstrap, run, verify, teardown
    .artifacts/             # generated runtime state (ignored)
    manual-setup.md         # only for source features that require a UI
```

`source/` and `target/` are intentionally separate: the target is the reviewed, hand-authored reference. Future converters write their output into `.artifacts/` and are validated against the same fixtures and gates without replacing the reference implementation.

Connection-backed operational tracks may instead keep `pipeline.yml` and `assets/` at the track root. They must keep credentials outside Git, document the external-state boundary, and use deterministic source provisioning such as the `seed` utility.

## Migration lifecycle

1. Inventory the source objects, configurations, dependencies, schedules, credentials, and source-specific semantics.
2. Record official documentation, conversion options, known gaps, and items requiring human review in the track README.
3. Build deterministic local fixtures before relying on UI instructions or external accounts.
4. Implement the target reference in version-controlled Bruin or DAC files.
5. Validate syntax, connections, output data, and rendered artifacts. Treat failures as migration findings, not details to skip.
6. Preserve UI-only steps as a reproducible manual fallback and capture any export only under ignored `.artifacts/`.

## Bruin and DAC capabilities exercised here

- `dac import metabase`, `dac check`, and `dac build` for dashboard migrations.
- Bruin `ingestr` assets with source and destination connections, incremental merge behavior, schema declarations, and quality checks.
- Bruin SQL assets with dependencies, table materializations, custom checks, unit tests, documentation, and `bruin data-diff` validation.

## Common validation gates

Each runnable example must provide these commands in its `example/README.md`:

- `bootstrap`: check prerequisites and create only local runtime state.
- `run`: execute source and target workloads against deterministic fixtures.
- `verify`: run the target’s native validation and compare expected outputs.
- `teardown`: remove only that example’s isolated Docker and `.artifacts/` state.

Generated state must be scoped under its example’s `.artifacts/` directory. Docker examples use an explicit Compose project name and dynamically published ports, so parallel Conductor workspaces do not clash.

## Utility pipelines

- [`seed`](seed/README.md) creates deterministic synthetic commerce tables in an isolated PostgreSQL schema for use as ingestion-pipeline sources. Unlike the migration examples above, it targets a user-configured external database and is run on demand.

## Adding a migration track

Copy the layout above, write the research README first, and build a small source fixture that demonstrates the high-value conversion path. Pin source runtimes and Python dependencies in the example. Do not add real credentials, production exports, or generated artifacts to Git. See [`AGENTS.md`](AGENTS.md) for the full contributor rules.

## Running examples

Start in the desired `example/` directory and follow its README. The examples only use local Docker, local DuckDB files, and credentials created for the fixture. They require the tools named in each README; no cloud account or production database is needed.
