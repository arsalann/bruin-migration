# bruin-dlt: plain-English summary

## What was done

- Built a new `bruin-dlt/` migration track, modelled on `bruin-fivetran/`.
- Wrote a staged migration prompt with seven review gates.
- Wrote a reusable `plan.md` template the agent keeps updated.
- Wrote a skill file with the agent's safety rules.
- Built one helper script: dlt credentials into Bruin connections.
- The agent reads everything else in dlt directly.
- The script prints field names only, never a credential value.
- It does write real passwords and keys into the ignored Bruin yml.
- Fixed two bugs in it: BigQuery service keys and Databricks path.
- Wrote a full dlt-to-ingestr mapping table in the track README.
- Built a local fixture: Postgres plus ClickHouse in Docker.
- Seeded exactly 1,000,000 rows across three Postgres tables.
- Wrote a dlt pipeline covering replace, merge, and append.
- Ran dlt first; it loaded all one million rows into ClickHouse.
- Hand-authored the migrated Bruin pipeline and three ingestr assets.
- Ran the Bruin pipeline into an isolated ClickHouse database.
- Ran a second pass with a deterministic change set.
- Row counts, keys, and checksums matched across all three systems.
- All 23 Bruin quality checks passed on both passes.
- Ran `bruin data-diff` with zero tolerance as the parity gate.
- Added a self-test proving the gate fails on one differing row.
- Wrote 40 unit tests for the converter, gates, and Python port.
- Wrote a fixture README explaining test scope and method.
- Wrote a handoff file recording every step and dead end.
- Clean run from scratch: bootstrap 28s, run 60s, verify 22s.
- Added the track to the repository-root README table.

## What assumptions I made

- The 1M rows split 200k customers, 300k orders, 500k events.
- ClickHouse was a good destination since the plan named it.
- "One replace, one merge, one incremental" maps to three resources.
- Append plus an incremental cursor is the "incremental" case.
- The fixture stands in for human approvals with a decisions file.
- Docker named volumes are safer than bind mounts for ClickHouse.
- dlt state belongs under `.artifacts/`, never in your `~/.dlt`.
- Integer cents avoid decimal-rendering noise in comparisons.
- Second-precision timestamps avoid engine precision differences.
- Pinned dlt 1.30.0, ClickHouse 24.8, Postgres 16.4.
- The handoff file lives in the example, updated per step.
- Only credentials justify a script; everything else is read directly.

## What questions are outstanding

- Should the track cover destinations beyond ClickHouse in the fixture?
- Do you want an asset generator, which I deliberately did not build?
- Do you want me to send the one-line `main.go` fix for issue 2561?
- Bruin MCP was unauthorized here; docs were used instead. Fine?
- Should `merge_key` without a primary key get a real fixture case?
- Should a dlt transformer case be demonstrated, not just flagged?
- Is `bruin-dlt` the right track name, versus `bruin-ingestr-dlt`?
- Do you want this on a PR now, or more review first?

## Next steps

- Review the mapping table with someone who ran a real dlt migration.
- Open a PR from this branch against `main`.
- Watch bruin issue 1223 (ClickHouse support) and 2561 (silent exit).
- Drop the DuckDB projection step once 1223 ships.
- Add a `delete+insert` fixture case for `merge_key`-only merges.
- Add a fixture case for row-level Python in a dlt resource.
- Consider testing the converter against a real customer dlt project.
- Decide whether other tracks should adopt the same gate self-test.

## Things worth knowing

- `bruin data-diff` cannot read ClickHouse; it exits 1 and prints nothing.
- ClickHouse support was already open as bruin issue 1223, so no duplicate.
- The silent exit was unreported; filed as bruin issue 2561.
- The gate still works by diffing DuckDB copies of the same rows.
- dlt writes `migration.dlt_analytics___orders`; Bruin writes `bruin_v0.orders`.
- That naming change breaks every downstream query and is documented.
- dlt's ClickHouse merge deletes asynchronously, so `system.tables` lies.
- All parity checks use `SELECT count()` instead.
- ingestr adds `_ingestr_loaded_at`; it is excluded from comparisons.
- I removed one stray dlt state directory the fixture created in `~/.dlt`.
- Your other dlt pipelines in `~/.dlt` were left untouched.
