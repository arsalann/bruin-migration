# Agent prompt: migrate Fivetran to Bruin

Copy the following into an agent working from the root of this template:

```text
Migrate one Fivetran connection to a new Bruin ingestion project using this
workspace. Work as a staged, review-gated migration—not as a one-shot
conversion. Read README.md and plan.md first. Keep plan.md current after every
stage, separating automated findings, hand-authored decisions, unsupported
behavior, and user TODOs. Never store credentials or raw customer data in
tracked files or chat.

Stage 1: import Fivetran configuration. Ask the user to set scoped Fivetran API
credentials in local environment variables; never ask them to paste a secret.
Use scripts/import_fivetran.py with GET-only access to discover connections and
capture the selected connection and schemas into
fivetran/.artifacts/<run-id>/. Update plan.md with the source/destination
inventory, schedule/state findings, missing metadata, and next actions.

Stage 2: create the new Bruin project. Use
scripts/initialize_bruin_project.py to create bruin/pipeline.yml and an
untracked bruin/.bruin.yml with placeholders for source and destination
connections. Update plan.md, then STOP. Tell the user to fill in the connection
details and test access locally, then ask them to tell you to continue. Do not
create assets or run any connection test until they return.

Stage 3: after the user continues, test both named Bruin connections. Read the
sanitized Fivetran configuration, use Bruin MCP and current Bruin documentation,
and build bruin/pipeline.yml and bruin/assets/**/*.asset.yml from scratch. Use
the importer conversion draft only as reviewable evidence. Update plan.md as
you work with every mapping, cast, rename, omission, default, generated field,
materialization, incremental strategy, dependency, schema-policy difference,
and unresolved question. Do not run ingestion yet.

Stage 4: before any run, resolve every TODO with the user one at a time. Update
the relevant asset and plan.md after each answer. Explicitly ask the user to
choose exactly one initial-run scope: full historical refresh; a bounded
historical range or data subset; one table only; or another defined scope. Also
obtain explicit approval for the isolated destination write, keys, delete
semantics, source-write consistency boundary, validation queries, and rollback.
Do not run until all of these are concrete and approved.

Stage 5: validate and run only the approved scope. Use bruin query with a
description against both source and destination to compare aggregates, key
uniqueness, null rates, and incremental min/max values; profile aggregates, not
customer rows. Run relevant quality checks, put evidence under
fivetran/.artifacts/<run-id>/run/, summarize ingestion status and discrepancies,
and update plan.md. Then pause and ask whether to stop, run more tables/ranges,
or do something else.

Stage 6: only if the user asks for final review and metadata updates, review the
pipeline, run `bruin ai enhance bruin --codex`, validate the result, and create
bruin/README.md with pipeline, asset, mapping, validation, ownership, and known
limitation details. Update plan.md's Completing the migration section with
final parity, Fivetran shutdown/coexistence, Bruin schedule enablement,
downstream refactors, monitoring, rollback, owners, action items, and risks.
Only declare the migration completed with the user's agreement. End with the
created directory tree and recommended next steps.
```

For the full command patterns and safeguards, see the bundled agent skill at
`.agents/skills/migrate-fivetran-to-bruin/SKILL.md` and its
`references/runtime-commands.md`.
