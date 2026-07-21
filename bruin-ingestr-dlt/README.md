# dlt to ingestr / Bruin

Status: research with runnable reference example.

## What is being migrated

dlt pipelines are Python programs that build sources and resources, apply schema or write-disposition hints, persist incremental state, and load data into a destination. The target is a declarative Bruin `ingestr` asset plus a Bruin connection configuration.

The example uses dlt's SQL database source against PostgreSQL and loads a merge/incremental resource into DuckDB. The matching Bruin asset uses the same PostgreSQL source, an `incremental_key`, a primary key, and `merge` strategy to land the data in a separate DuckDB file.

## Source inventory checklist

- Python pipeline, source/resource definitions, selected resources, transformations, schemas, configuration, and secrets.
- Destination, dataset naming, write disposition, primary/merge keys, incremental cursor, state location, and refresh behavior.
- Deployment metadata, schedules, retries, environment variables, and any source-specific pagination or ordering semantics.
- Data contracts, expected tables, row-level quality assumptions, and load audit requirements.

## Conversion approach

Map one dlt resource at a time to a Bruin `ingestr` asset. Preserve the source connection and table/query, then choose `replace`, `append`, `merge`, or `delete+insert` deliberately. Merge requires both an incremental key and primary key. Attach target column checks and custom checks where they state durable data expectations.

The runnable example runs an initial load, changes one source row and inserts another, executes both pipelines again, and checks equivalent DuckDB outputs with `bruin data-diff --full --fail-if-diff`.

## Migration guide for an existing dlt pipeline

This guide assumes the dlt source and destination are working. Migrate one resource at a time; do not reuse or modify the live dlt state during comparison.

1. Inventory the pipeline and select one resource; record its source query/table, destination table, write disposition, primary key, incremental cursor, state, schedule, and expected volume.
2. Choose a migration boundary and preserve the dlt cursor value; use it to define the backfill window and prevent gaps or duplicate processing.
3. Configure Bruin source and destination connections with equivalent access, keeping credentials outside committed pipeline files.
4. Create an `ingestr` asset that names the source table or query, destination table, write strategy, `incremental_key`, and primary key.
5. Add column and custom checks for durable expectations, such as required fields, allowed values, uniqueness, and row-level reconciliation rules.
6. Run `bruin validate pipeline.yml --config-file bruin.yml`, then backfill a bounded window with `bruin run pipeline.yml --config-file bruin.yml --start-date <date> --end-date <date>`.
7. Compare source and target with `bruin data-diff --config-file bruin.yml --full --fail-if-diff <source-connection>:<schema.table> <target-connection>:<schema.table>`; fix every mismatch before continuing.
8. Repeat for each resource, then pause the dlt schedule, run a final incremental window in Bruin, verify counts and keys, and enable the Bruin schedule.

Keep custom Python transformations out of a plain `ingestr` asset: port them explicitly as Bruin Python or SQL assets and validate their output separately.

## Official references

- [dlt incremental loading](https://dlthub.com/docs/general-usage/incremental-loading) and [SQL database tutorial](https://dlthub.com/docs/tutorial/sql-database).
- [dlt incremental troubleshooting](https://dlthub.com/docs/general-usage/incremental/troubleshooting) — pipeline name, destination, dataset, and state must remain stable across runs.
- [Bruin ingestr assets](https://getbruin.com/docs/bruin/assets/ingestr.html) and [ingestr incremental loading](https://getbruin.com/docs/ingestr/getting-started/incremental-loading.html).
- [Bruin data-diff](https://getbruin.com/docs/bruin/commands/data-diff.html).

## Known gaps and human review

- dlt resources may contain arbitrary Python logic that cannot become a simple database-to-database `ingestr` asset. Keep transformations as Bruin Python or SQL assets when necessary.
- Review source naming, dlt normalization, nested-data behavior, schema evolution, dlt state resets, and per-resource write dispositions.
- dlt deployment metadata and orchestration do not migrate automatically; recreate schedule, retries, alerts, and secret handling in the target operating environment.

## Future automation candidates

- Static inventory of dlt resources, destinations, hints, and incremental state configuration.
- An asset generator for plain database resources, with an explicit report for resources containing custom Python transformations.
- Regression runner that exercises initial and incremental fixtures against both systems.
