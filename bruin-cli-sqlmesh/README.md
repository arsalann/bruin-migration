# SQLMesh to Bruin CLI

Status: research with runnable reference example.

## What is being migrated

SQLMesh projects combine gateway configuration, models, macros, model kinds, dependencies, tests, audits, plans, environments, and scheduling metadata. Bruin targets the transformation logic as SQL/Python assets with explicit dependencies, materialization, quality checks, unit tests, connection configuration, and external orchestration.

The reference fixture uses a DuckDB SQLMesh project with a macro, source model, dependent revenue model, unit test, audit, and applied plan. Its target is an equivalent Bruin DuckDB pipeline with a seed asset, SQL transformation, custom check, unit test, and generated documentation.

## Source inventory checklist

- `config.yaml`/`config.py`, gateways, state connection, environments, model defaults, scheduling, and variables.
- Every model's name, dialect, kind, grain, dependencies, columns, audits, and physical schema behavior.
- Macros, seeds/external models, Python models, tests, audit severity, and plan/environment history.
- Deployment, notification, backfill, and ownership metadata that need a target operating model.

## Conversion approach

Convert the logical model graph first, then map each source model to a Bruin asset. Use a Bruin seed asset for deterministic input, a SQL asset for a model, `depends` for the graph, `materialization` for the table behavior, `unit_tests` for logic, and `custom_checks`/column checks for output quality. Preserve source plan history separately; a SQLMesh plan/environment is not equivalent to a Bruin file.

The example applies a local SQLMesh plan, runs the Bruin pipeline, executes both systems' tests, runs the SQLMesh audit during the plan, creates Bruin docs, and compares final tables with `bruin data-diff --full --fail-if-diff`.

## Migration guide for an existing SQLMesh project

This guide assumes the SQLMesh project, gateway, and source data are already working. It migrates the model graph and validation contract; it does not reproduce SQLMesh state or environments.

1. Inventory the project: gateway and state configuration, models, kinds, dependencies, macros, seeds, tests, audits, schedules, environments, and active plan.
2. Choose a stable baseline date and record the production model outputs, row counts, schemas, and quality results for comparison.
3. Configure Bruin connections for the target warehouse and any source schemas; keep credentials and state-store decisions outside source control.
4. Convert models in dependency order: map seeds to seed assets, SQL models to SQL assets, and dependencies to `depends` declarations.
5. Preserve each model's materialization, partition/incremental semantics, dialect behavior, and physical naming explicitly; do not infer them from SQL alone.
6. Port macros and reusable logic before dependent models, then translate tests and audits into Bruin `unit_tests`, column checks, or `custom_checks`.
7. Run `bruin validate pipeline.yml --config-file bruin.yml`, then execute a bounded backfill with `bruin run pipeline.yml --config-file bruin.yml --start-date <date> --end-date <date>`.
8. Compare every migrated final model using `bruin data-diff --config-file bruin.yml --full --fail-if-diff <source-connection>:<schema.table> <target-connection>:<schema.table>`.
9. After parity is proven, freeze the SQLMesh schedule, run the final incremental period in Bruin, verify again, and switch orchestration and alerts.

Treat SQLMesh plans, snapshots, environments, and state as operating-model decisions: document the replacement promotion, backfill, and rollback process before cutover.

## Official references

- [SQLMesh projects](https://sqlmesh.readthedocs.io/en/latest/guides/projects/), [models](https://sqlmesh.readthedocs.io/en/latest/guides/models/), [macros](https://sqlmesh.readthedocs.io/en/latest/concepts/macros/sqlmesh_macros/), [tests](https://sqlmesh.readthedocs.io/en/stable/concepts/tests/), and [audits](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/).
- [SQLMesh plans](https://sqlmesh.readthedocs.io/en/stable/concepts/plans/) and [DuckDB connection considerations](https://sqlmesh.readthedocs.io/en/stable/integrations/engines/duckdb/).
- [Bruin unit tests](https://getbruin.com/docs/bruin/quality/unit-tests.html), [Bruin docs](https://getbruin.com/docs/bruin/commands/docs.html), and [data-diff](https://getbruin.com/docs/bruin/commands/data-diff.html).

## Known gaps and human review

- SQLMesh environments, snapshots, plan categorization, and state are not artifacts that a Bruin pipeline reproduces. Decide how to operate promotion, deployment, and backfills separately.
- Review incremental model kinds, model kind-specific semantics, macros, Python models, external models, dialect differences, physical schemas, and audit severity.
- Local DuckDB is appropriate for this fixture but SQLMesh documents it as a single-user state store; use a durable state store for collaborative or production use.
- Bruin `v0.11.682` parses the target's `unit_tests` block but its `unit-test` runner cannot execute against DuckDB. Keep the declaration and run it when DuckDB support lands; the example currently validates the declaration, runs the source unit test, and compares the materialized output.

## Future automation candidates

- SQLMesh project inventory that emits model graph, kinds, macro usage, tests, audits, and unsupported constructs.
- SQLMesh SQL-to-Bruin asset generator with source comments and conversion findings.
- Fixture runner that validates target output and records expected conversion gaps.
