---
name: migrate-fivetran-to-bruin
description: Guide an agent-led, review-gated migration from a Fivetran connection to a new Bruin ingestr project. Use when importing Fivetran configuration, creating Bruin connection placeholders, generating ingestr assets, deciding a first-run scope, validating a migration, or completing Fivetran cutover planning.
---

# Migrate Fivetran to Bruin

Run this as a staged conversation, not a one-shot converter. Maintain the root
`plan.md` throughout. Treat `bruin/` as the user’s hand-authored target project
and `fivetran/.artifacts/<run-id>/` as private, ignored migration evidence.

## Workspace contract

- Use `scripts/import_fivetran.py` for Fivetran access. It only performs GET
  requests and must never receive credentials as literal command-line values.
- Store Fivetran discovery, captures, generated drafts, query results, and run
  evidence under `fivetran/.artifacts/<run-id>/` only.
- Keep `bruin/.bruin.yml` untracked. Create it with placeholders, then let the
  user supply connection details themselves.
- Do not run a Bruin pipeline, write to a destination, change a Fivetran
  connection, or enable a schedule without the user’s explicit approval.
- Keep `plan.md` factual. Separate completed work, automated findings,
  hand-authored decisions, unsupported behavior, and open user actions.

## Stage 1 — import Fivetran and establish the plan

1. Read the existing `plan.md`; preserve prior decisions.
2. Ask the user to set a scoped Fivetran API key and secret in their local
   environment if they are not already available. Do not ask them to paste
   secrets into chat.
3. Run discovery to `fivetran/.artifacts/<run-id>/discovery.json`:

   ```bash
   python scripts/import_fivetran.py discover \
     --api-key-env FIVETRAN_API_KEY \
     --api-secret-env FIVETRAN_API_SECRET \
     --output fivetran/.artifacts/<run-id>/discovery.json
   ```

   An untracked config file with `fivetran_api_key` and
   `fivetran_api_secret` generic connections is an acceptable alternative to
   the environment-variable flags.
4. If more than one relevant connection exists, show safe identity metadata and
   ask the user to choose one. Capture only that connection:

   ```bash
   python scripts/import_fivetran.py capture \
     --api-key-env FIVETRAN_API_KEY \
     --api-secret-env FIVETRAN_API_SECRET \
     --connection <connection-id> \
     --output fivetran/.artifacts/<run-id>/fivetran-snapshot.json
   ```

5. Update `plan.md` with the selected connection, objects, original destination,
   schedule/state findings, missing source metadata, and the next action items.

## Stage 2 — scaffold connections, then pause

1. Use the sanitized snapshot to create a bare project and placeholder
   connections:

   ```bash
   python scripts/initialize_bruin_project.py \
     --snapshot fivetran/.artifacts/<run-id>/fivetran-snapshot.json \
     --bruin-dir bruin \
     --source-connection fivetran_source \
     --destination-connection bruin_destination
   ```

2. Update `plan.md` with the generated connection names, required user setup,
   and the intended isolated target naming.
3. Stop here. Tell the user that `bruin/.bruin.yml` contains placeholders and
   ask them to fill in or replace the two connections, then tell you to
   continue. Do not create assets or test connections until they return.

## Stage 3 — build the Bruin project after the user continues

1. Test the named source and destination connections with the exact untracked
   config. Record only success/failure and non-secret diagnostics in `plan.md`.
2. Create a reviewable connection/table map in
   `fivetran/.artifacts/<run-id>/connection-map.yml` and run conversion without
   strict mode to obtain drafts:

   ```bash
   python scripts/import_fivetran.py convert \
     --snapshot fivetran/.artifacts/<run-id>/fivetran-snapshot.json \
     --connections fivetran/.artifacts/<run-id>/connection-map.yml \
     --output-root fivetran/.artifacts/<run-id>/generated
   ```

3. Use Bruin MCP and current Bruin documentation to build `bruin/pipeline.yml`
   and `bruin/assets/**/*.asset.yml` from scratch. Use drafts as evidence, not
   as unreviewed production output.
4. As assets are built, update `plan.md` with every column mapping, cast,
   rename, omission, default, generated field, materialization choice,
   incremental strategy, schema policy, and dependency. Add unresolved items to
   the **User TODOs** section.
5. Do not run or test ingestion in this stage.

## Stage 4 — resolve TODOs before the first run

Walk through unresolved TODOs one at a time. After each answer, update the
asset and `plan.md`, then ask the next question. Always ask for the initial-run
scope explicitly:

- full historical refresh;
- a bounded historical date range or subset of data;
- one table only; or
- another user-defined scope.

Also resolve destination write approval, primary/incremental keys, delete
semantics, source-write/consistency boundary, validation queries, and rollback.
Do not proceed until the user has approved a concrete first run.

## Stage 5 — run, inspect, and pause

1. Validate the exact pipeline and run only the approved assets and interval.
2. Use `bruin query` against both source and destination to compare aggregate
   counts, key uniqueness, null rates, and incremental min/max values. Include
   `--description` on every query. Profile aggregates rather than dumping
   customer rows into chat.
3. Run relevant Bruin quality checks and retain machine-readable evidence under
   `fivetran/.artifacts/<run-id>/run/`.
4. Summarize the run, ingestion status, quality results, and mismatches for the
   user. Update `plan.md`.
5. Pause and ask: **stop here, run more tables/ranges, or do something else?**

## Stage 6 — optional final review and completion

Ask whether the user wants final metadata and migration review. Only if they
say yes:

1. Review every asset and run `bruin ai enhance bruin --codex` (or the user’s
   approved provider). Review the resulting changes, then validate the pipeline.
2. Create `bruin/README.md` covering the pipeline, assets, source/target
   mappings, schedules, validation evidence, operational ownership, and known
   limitations.
3. Add a **Completing the migration** section to `plan.md` covering final
   parity, Fivetran shutdown timing, Bruin schedule enablement, downstream
   refactors, monitoring, rollback, ownership, and risks.
4. Mark the migration complete only when the user agrees. Present the created
   directory tree and concise recommended next steps.

Read [runtime-commands.md](references/runtime-commands.md) before executing or
profiling a first run.
