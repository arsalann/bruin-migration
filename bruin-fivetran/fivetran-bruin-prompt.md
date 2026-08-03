# Fivetran to Bruin migration prompt

Use this prompt from the repository root to migrate one Fivetran connection
into a new Bruin ingestr project. This is a staged, review-gated workflow, not
an automatic cutover. Keep customer captures and generated evidence under
`bruin-fivetran/.artifacts/`; never put credentials or source data in Git.

Read `bruin-fivetran/plan.md` first and update it after every stage. Keep
automated findings, human decisions, unsupported behavior, and open TODOs
separate.

Start with this implementation instruction:

> Read the imported Fivetran configuration, connection details, optional
> database and table mappings, and source table/asset schemas and definitions.
> Read the relevant Bruin documentation and Fivetran-to-Bruin configuration
> mapping, including frequency, materialization, incremental strategy, and
> related execution settings.
>
> Use the Bruin MCP and documentation to build an MVP/draft ingestion pipeline.
> Create `plan.md` alongside the migration prompt. Initially, it must record
> configuration mismatches; ingestion-specific column mappings (including
> casts, defaults, renames, omissions, and generated fields); and every TODO or
> question requiring clarification, such as materialization and incremental
> strategy.
>
> Validate the MVP, then run it to an isolated temporary destination to create
> v0 tables and demonstrate the ingestion outcome. Verify the resulting data
> and make the validation fail on a mismatch. Update `plan.md` after that run
> with next steps and a production-migration plan, including decisions still
> needed for incremental strategy, metadata columns, downstream refactors,
> validation, and switchover.

## Stage 1 — import Fivetran configuration

Ask the user to identify one connection by name or ID. Then capture exactly
that connection using only GET requests:

```bash
python3 bruin-fivetran/.agents/skills/bruin-fivetran-migrator/import_fivetran.py \
  --config-file .bruin.yml \
  --connector-name <approved-connection-name> \
  --output-dir bruin-fivetran/.artifacts/fivetran/<capture-id>
```

Read the redacted `connection.json` and `schemas.json`. Update
`bruin-fivetran/plan.md` with the source/destination inventory, schedule/state,
selected tables, missing metadata, compatibility gaps, and next user actions.

## Stage 2 — create the Bruin project, then pause

Create a new `bruin/` project with `pipeline.yml`, `assets/`, and an untracked
`bruin/.bruin.yml` containing source/destination connection placeholders only.
Do not add real connection values. Explain what the user must fill in, update
the plan, and stop. Resume only when the user explicitly says the connections
are ready; then test both named connections and record the result.

## Stage 3 — draft the MVP

Read the imported capture, source definitions, Bruin documentation, and Bruin
MCP. Build the Bruin ingestr pipeline and assets from scratch. For every table,
record in `plan.md` the mapping, casts, renames, omissions, generated fields,
materialization, keys, incremental strategy, schema ownership, schedule choice,
and unsupported Fivetran behavior. Do not run ingestion yet.

## Stage 4 — resolve TODOs

Walk through every open TODO with the user before any destination write. Obtain
explicit answers for initial-run scope, isolated target names, date bounds,
primary and incremental keys, materialization, delete/history behavior, schema
handling, validation boundary, rollback, and operational ownership. Update the
pipeline and plan after each answer. Stay paused if any required decision is
missing.

## Stage 5 — approved v0 run

After explicit approval, validate and run only the approved scope to isolated
v0 tables. Use `bruin query` to compare source and target row counts, null and
duplicate keys, and incremental ranges. Run relevant quality checks and
`bruin data-diff --full --tolerance 0 --fail-if-diff` when a reviewed common
representation exists. Treat every mismatch as a failure, preserve evidence in
`.artifacts/`, update the plan's Run history, summarize the result, and pause.

## Stage 6 — final review only on request

Ask whether the user wants a final review and metadata update. Only if they say
yes, review the assets, run `bruin ai enhance --codex`, validate the result,
create `bruin/README.md`, and complete the migration/cutover checklist in
`plan.md`. Do not disable Fivetran or enable a Bruin schedule without separate,
explicit approval.
