# Maintainer-only regression fixture

This directory is not part of the end-user migration tool. The runtime surface is
[`../dlt-bruin-prompt.md`](../dlt-bruin-prompt.md), [`../plan.md`](../plan.md),
and the skill directory at `../.agents/skills/bruin-dlt-migrator/`.

## What this fixture proves

A real dlt pipeline moves a million rows from PostgreSQL into ClickHouse. The
migration workflow then produces a Bruin ingestr pipeline that loads the same
rows from the same source into an isolated ClickHouse database, and the fixture
fails unless all three systems agree exactly.

Everything is local: two Docker containers on dynamically published loopback
ports, throwaway container credentials, and generated state confined to
`.artifacts/`.

### Scope

| Concern | Covered by |
| --- | --- |
| Realistic data volume | 1,000,000 seeded rows across three PostgreSQL tables |
| Every write-strategy mapping | one `replace`, one `merge`, one `append` resource |
| Custom API source | a fourth dlt resource against `pokeapi.co`, ported to a Bruin **Python asset** |
| Port fidelity | AST tests asserting the ported paginator and transforms have not drifted |
| Incremental cursor mapping | dlt `cursor_path` to ingestr `incremental_key`, on two resources |
| Primary key mapping | dlt `primary_key` to `columns[].primary_key` |
| Credential safety | the converter writes Bruin connections; no agent reads a secret |
| Incremental correctness | a second pass with a deterministic change set |
| Cross-system parity | exact three-way comparison plus `bruin data-diff` |
| Gate integrity | a self-test that the diff gate fails on a one-row difference |

### Deliberately out of scope

`scd2`, nested and child tables, custom `last_value_func`, and CDC. The track
documents these as needing a separate approved design; a fixture that pretended to
migrate them would be misleading.

### Network dependency

The `pokemon` resource calls `https://pokeapi.co` live, on both the dlt side and
the Bruin side, so `run.sh` needs outbound network access. That is a deliberate
exception to the repository's local-fixtures rule: the point of this case is a
real custom API source, and a mock would not demonstrate the port. The first 60
records are stable, which is what makes the API usable as a fixture. Everything
else in the fixture is local and offline.

## Fixture data

| Table | Rows after the initial pass | dlt write disposition | dlt cursor | Bruin target |
| --- | --- | --- | --- | --- |
| `public.customers` | 200,000 | `replace` | none | ingestr, `create+replace` |
| `public.orders` | 300,000 | `merge` on `order_id` | `updated_at` | ingestr, `merge` |
| `public.order_events` | 500,000 | `append` | `event_ts` | ingestr, `append` |
| `pokeapi.co/pokemon` | 60 | `merge` on `pokemon_id` | none | **Python asset**, `merge` |

The API resource is small on purpose: it exists to exercise the *port*, not
throughput. Its dlt side is a hand-rolled paginator plus two `add_map` transforms,
which is what forces a Python asset rather than an ingestr asset.

All initial timestamps fall inside `[2025-01-01, 2025-03-30 23:59:59]`. The
second pass updates 1,000 orders, inserts 500 orders, inserts 1,000 events, and
updates 200 customers, all stamped inside `[2025-04-01 06:00, 2025-04-01 09:00]`.
The incremental window `[2025-04-01, 2025-04-02]` therefore captures exactly that
change set and nothing already loaded — which is what makes the `append`
resource's `unique` check a meaningful regression guard.

Expected final counts: customers 200,000, orders 300,500, order_events 501,000.

## Method

`run.sh` performs the steps in the order a real migration would, with the
human-decision stages replaced by the reviewed
[`fixtures/migration-decisions.yml`](fixtures/migration-decisions.yml):

0. Route each resource: three go to ingestr assets, the API one to a Python asset.
1. Reset only this fixture's destination state and reseed the source.
2. Convert the dlt credentials into Bruin connections and test both. The
   converter merges into the harness `bruin.yml`, so this also exercises the
   merge-into-an-existing-config path.
3. Run both dlt pipelines first, so the dlt tables are the incumbent to compare
   against.
4. Check the hand-authored `target/` reference against the reviewed decisions,
   then `bruin validate` it.
5. Run the Bruin pipeline over the initial history window.
6. Apply the change set, run dlt again, then run Bruin over the incremental
   window.
7. Compare all three systems and run the data-diff gate.

`verify.sh` re-checks all of that independently, proves the gate can fail, checks
credential hygiene, and runs the unit tests.

## Parity method, and why the diff runs on projections

`compare_parity.py` streams every row from PostgreSQL, from the dlt ClickHouse
tables, and from the Bruin ClickHouse tables, canonicalizes each value in Python,
and compares row counts, distinct keys, null keys, and order-insensitive
checksums. Hashing in Python rather than in SQL means no engine's own hash or
number formatting can hide a difference.

`bruin data-diff` runs as a second, native gate — but not directly against
ClickHouse. In Bruin CLI `v0.11.722` a ClickHouse connection cannot be summarized
([bruin-data/bruin#1223](https://github.com/bruin-data/bruin/issues/1223)), and
the attempt exits `1` while printing nothing at all
([bruin-data/bruin#2561](https://github.com/bruin-data/bruin/issues/2561)). So
`prepare_comparison.py` projects the same rows from all three systems into DuckDB
as VARCHAR columns, and the diff runs there with `--full --tolerance 0
--fail-if-diff`. `assert_gate_fails.sh` then proves that gate really fails on a
one-row difference — which is the check that would have caught a silently unrun
diff.

Generated columns are excluded from parity by construction: ingestr adds
`_ingestr_loaded_at`, and dlt may add `_dlt_load_id` and `_dlt_id`. Only the
declared source columns are compared.

## Prerequisites

- Docker Desktop with Compose v2
- `bruin` and `python3` on `PATH`
- Outbound network access, for the `pokemon` resource only

The fixture creates a virtual environment inside `.artifacts/` and installs the
pinned dependencies from [`requirements.txt`](requirements.txt). It uses
PostgreSQL `16.4-alpine`, ClickHouse `24.8-alpine`, dlt `1.30.0`, and dynamically
assigned loopback ports. `DLT_DATA_DIR` points into `.artifacts/`, so dlt never
writes to the operator's `~/.dlt`.

## Commands

```bash
./scripts/bootstrap.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/teardown.sh
```

- `bootstrap.sh` provisions only this fixture's Compose project, its
  `.artifacts/` state, and the ~1M row seed.
- `run.sh` runs both systems in two passes and gates on parity.
- `verify.sh` re-validates, re-compares, proves the gate fails on a mismatch,
  checks that no credential leaked into the report or any reviewed artifact, and
  runs the unit tests.
- `teardown.sh` stops only the explicitly named Compose project, removes its
  named volumes, and deletes this example's `.artifacts/` directory.

No task touches the repository-root `.bruin.yml`, the operator's `~/.dlt`, or any
external account.

## Layout

```text
fixtures/postgres/       DDL, the deterministic seed, and the change set
fixtures/dlt/            tracked non-secret dlt config and a secrets placeholder
fixtures/migration-decisions.yml   the reviewed answers to the workflow's questions
source/                  docker-compose, both dlt pipelines, runtime-file writers
target/                  the hand-authored Bruin reference and its completed plan
scripts/                 bootstrap, run, verify, teardown, and the gates
tests/                   unit tests for the converter and the gates
.artifacts/              generated runtime state (ignored)
```
