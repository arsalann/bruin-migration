# Fivetran-to-Bruin migration plan

Status: not started

This is the living, hand-maintained plan for one migration. The agent updates
it after every stage and never stores credentials or raw customer data here.

## Migration inventory

| Area | Current finding | Decision / owner | Status |
| --- | --- | --- | --- |
| Fivetran connection | Not imported | User selects connection | Open |
| Source objects and columns | Not imported | Agent captures selection; user confirms complete source metadata | Open |
| Original Fivetran destination | Not imported | Inventory only | Open |
| Bruin source connection | Not created | User fills `bruin/.bruin.yml` | Open |
| Bruin destination connection | Not created | User fills `bruin/.bruin.yml` | Open |
| Target tables and schema | Not designed | Agent proposes isolated v0 names | Open |
| Materialization and incrementality | Not reviewed | User approves per table | Open |
| Schedule, checkpoint, and delete semantics | Not reviewed | Human decision required | Open |
| Validation boundary and rollback | Not reviewed | Human decision required | Open |

## Automated findings

Add only facts observed from the sanitized Fivetran capture, Bruin validation,
or run evidence. Link to the relevant path under `fivetran/.artifacts/<run-id>/`.

## Hand-authored decisions

Record approved mappings, destination names, materializations, keys, initial
scope, validation rules, owners, and dates here.

## User TODOs

- [ ] Select and authorize one Fivetran connection for read-only capture.
- [ ] Fill and test the source and destination connections in `bruin/.bruin.yml`.
- [ ] Confirm source schema, primary keys, incremental candidates, and delete behavior.
- [ ] Approve the isolated first-run destination and first-run scope.

## First-run scope

Do not leave this section implicit. Record exactly one approved option:

- [ ] Full historical refresh
- [ ] Bounded historical range or data subset: `<define>`
- [ ] One table only: `<define>`
- [ ] Other: `<define>`

Record the source-write consistency boundary, run command, quality checks,
aggregate comparison queries, expected result, and rollback path before running.

## Run history

Add a dated entry after every execution: approved scope, asset/table, status,
row-count/key/null/incremental-range comparisons, quality outcomes, evidence
paths, and unresolved discrepancies.

## Completing the migration

Complete this section only during final review:

- [ ] Confirm final parity at an agreed boundary.
- [ ] Decide Fivetran shutdown or coexistence timing and owner.
- [ ] Enable the Bruin schedule only after explicit approval.
- [ ] Refactor downstream assets/models/tables away from Fivetran-only fields.
- [ ] Confirm monitoring, alerting, on-call ownership, rollback, and cleanup.
- [ ] Publish `bruin/README.md` and review metadata/quality checks.

## Risks and unsupported behavior

Record non-portable Fivetran behavior, unresolved schema/deletion issues,
source limitations, cost/volume risks, and required manual work.
