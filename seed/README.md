# GCP Cloud SQL seed pipeline

The `seed` pipeline creates an isolated `bruin_ingestr` schema in PostgreSQL and appends four production-shaped, relationally consistent source tables with deterministic synthetic data. It is intended to be a stable large-volume upstream fixture for ingestion-pipeline development, not production data.

## Inventory and scope

| Object | Rows per seed day | Business columns | Dependency | Load strategy | Useful ingestion fields |
| --- | ---: | ---: | --- | --- | --- |
| `bruin_ingestr.customers` | 100,000 | 29 | none | transactional, idempotent insert | `customer_id`, `updated_at`, `row_version` |
| `bruin_ingestr.products` | 25,000 | 29 | none | transactional, idempotent insert | `product_id`, `updated_at`, `row_version` |
| `bruin_ingestr.orders` | 350,000 | 30 | customers | transactional, idempotent insert | `order_id`, `customer_id`, `updated_at` |
| `bruin_ingestr.order_items` | 525,000 | 26 | orders, products | transactional, idempotent insert | `order_item_id`, `order_id`, `source_updated_at` |

- Each daily interval produces exactly 1,000,000 rows in total. A backfill produces that volume for every calendar day in its interval, and the tables retain the accumulated history.
- Source code: four warehouse-native PostgreSQL set generators. Values and primary keys are derived deterministically from the UTC seed date and per-day row identifier; volatile `random()` calls are not used.
- Target: GCP Cloud SQL instance `bruin-ingestr-demo`, PostgreSQL database `postgres`, schema `bruin_ingestr`.
- Schedule: `@daily`. A scheduler runs the preceding daily interval; local runs remain explicit.
- Credentials: local, gitignored `.bruin.yml` connection named `gcp_postgres`; no credential is tracked.
- Incremental state: the target tables themselves. Normal runs use `INSERT ... ON CONFLICT DO NOTHING`, so rerunning an interval is safe and does not duplicate it. `--full-refresh` is the intentional destructive reset path.
- Validation: per-day exact row counts, physical and metadata-level primary-key uniqueness, accepted-value checks, nonnegative amounts, timestamp ordering, referential integrity, and aggregate order/order-item monetary reconciliation.

This is a hand-authored reference pipeline. Bruin automates dependency ordering, execution, interval rendering, and checks; table shape and synthetic-data distributions are explicit human decisions. Each table is managed with explicit PostgreSQL DDL, a stable physical identity, a physical primary key, and deterministic unique indexes so it is suitable for logical-replication experiments. Relationship rules remain executable Bruin quality gates rather than foreign keys so independent fixture teardown and reload remain predictable.

The assets use Bruin's built-in `start_date` and `end_date` values as an inclusive UTC calendar-date interval. They generate every day from `start_date` through `end_date` with PostgreSQL `generate_series`; this matches Bruin's daily default, which spans the beginning through the end of yesterday. `updated_at` and `source_updated_at` also fall in their seed day, so downstream timestamp-incremental ingestion can process the same interval immediately.

The large datasets are generated inside PostgreSQL instead of being assembled in client memory and uploaded row by row. For every seed day, the first 175,000 orders have two line items and the remaining 175,000 have one, producing 525,000 order items while preserving exact aggregate monetary reconciliation. A normal rerun is an idempotent no-op for rows already seeded; it does not truncate the source tables or create a full replication workload.

## Prerequisites and connection

Tested with Bruin CLI `v0.11.690` and Cloud SQL Auth Proxy `v2.23.0`. Start the proxy on loopback before testing or executing any asset:

```bash
cloud-sql-proxy \
  --address 127.0.0.1 \
  --port 5433 \
  bruin-playground-arsalan:europe-west6:bruin-ingestr-demo
```

The `gcp_postgres` connection targets `127.0.0.1:5433` with `ssl_mode: disable`. This disables TLS only on the local loopback hop; the Cloud SQL Auth Proxy authenticates with ADC and establishes the encrypted connection to GCP. Public-IP authorized networks can remain empty.

## Commands

Bootstrap (with the proxy running, fail if the configured connection cannot run Bruin's test query):

```bash
bruin connections test --name gcp_postgres --env default
```

Validate the pipeline without changing the database:

```bash
bruin validate seed
```

Run one explicit daily interval. A single worker deliberately limits pressure on the Cloud SQL instance:

```bash
bruin run seed/pipeline.yml \
  --start-date 2026-07-21 \
  --end-date 2026-07-21 \
  --workers 1 \
  --timeout 3600
```

Backfill a date range; both dates are included, so this creates seven million rows across 2026-07-01 through 2026-07-07:

```bash
bruin run seed/pipeline.yml \
  --start-date 2026-07-01 \
  --end-date 2026-07-07 \
  --workers 1 \
  --timeout 3600
```

To replace a legacy one-time seed, explicitly reset the four seed tables and load only the supplied range. Do not use `--full-refresh` for a normal daily run or additive backfill:

```bash
bruin run seed/pipeline.yml \
  --full-refresh \
  --start-date 2026-07-21 \
  --end-date 2026-07-21 \
  --workers 1 \
  --timeout 3600
```

Verify the already-loaded tables. This command exits nonzero if any declared quality check fails:

```bash
bruin run seed/pipeline.yml --only checks
```

Optional teardown (destructive; removes only the explicitly named seed schema and its four tables):

```bash
bruin query \
  --connection gcp_postgres \
  --description "remove the disposable bruin_ingestr seed schema" \
  --query "DROP SCHEMA IF EXISTS bruin_ingestr CASCADE"
```

## Official references

- [PostgreSQL connection and asset support](https://getbruin.com/docs/bruin/platforms/postgres)
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy)
- [PostgreSQL series-generating functions](https://www.postgresql.org/docs/current/functions-srf.html), [`INSERT`](https://www.postgresql.org/docs/current/sql-insert.html), and [`TRUNCATE`](https://www.postgresql.org/docs/current/sql-truncate.html)
- [Asset definitions, dependencies, and checks](https://getbruin.com/docs/bruin/assets/definition-schema.html)
- [Bruin templating and built-in interval variables](https://getbruin.com/docs/bruin/assets/templating/templating.html)
- [Bruin pipeline schedules](https://getbruin.com/docs/bruin/pipelines/definition.html)
- [`.bruin.yml` configuration](https://getbruin.com/docs/bruin/secrets/bruinyml.html)
