# GCP Cloud SQL seed pipeline

The `seed` pipeline creates an isolated `bruin_ingestr` schema in PostgreSQL and loads four production-shaped, relationally consistent source tables with deterministic synthetic data. It is intended to be a stable large-volume upstream fixture for ingestion-pipeline development, not production data.

## Inventory and scope

| Object | Rows | Business columns | Dependency | Load strategy | Useful ingestion fields |
| --- | ---: | ---: | --- | --- | --- |
| `bruin_ingestr.customers` | 1,000,000 | 29 | none | transactional truncate/insert | `customer_id`, `updated_at`, `row_version` |
| `bruin_ingestr.products` | 1,000,000 | 29 | none | transactional truncate/insert | `product_id`, `updated_at`, `row_version` |
| `bruin_ingestr.orders` | 10,000,000 | 30 | customers | transactional truncate/insert | `order_id`, `customer_id`, `updated_at` |
| `bruin_ingestr.order_items` | 12,000,000 | 26 | orders, products | transactional truncate/insert | `order_item_id`, `order_id`, `source_updated_at` |

- Source code: four warehouse-native PostgreSQL set generators. Values are derived deterministically from row identifiers; volatile `random()` calls are not used.
- Target: GCP Cloud SQL instance `bruin-ingestr-demo`, PostgreSQL database `postgres`, schema `bruin_ingestr`.
- Schedule: intentionally omitted; this is an on-demand seed operation.
- Credentials: local, gitignored `.bruin.yml` connection named `gcp_postgres`; no credential is tracked.
- Incremental state: none. Every run transactionally reloads the same complete 24-million-row fixture.
- Validation: exact row counts, physical and metadata-level primary-key uniqueness, accepted-value checks, nonnegative amounts, timestamp ordering, referential integrity, and aggregate order/order-item monetary reconciliation.

This is a hand-authored reference pipeline. Bruin automates dependency ordering, execution, and checks; table shape and synthetic-data distributions are explicit human decisions. Each table is managed with explicit PostgreSQL DDL, a stable physical identity, a physical primary key, and deterministic unique indexes so it is suitable for logical-replication experiments. Relationship rules remain executable Bruin quality gates rather than foreign keys so independent fixture teardown and reload remain predictable.

The large datasets are generated inside PostgreSQL with `generate_series` instead of being assembled in client memory and uploaded row by row. This materially reduces client memory and network transfer for the 24-million-row rebuild. The first two million orders have two line items and the remaining eight million have one, producing 12 million order items while preserving exact aggregate monetary reconciliation.

Run the seed before attaching a CDC connector. A rerun uses `TRUNCATE` followed by a full deterministic insert and is meant to reset this disposable fixture; it is not an incremental production write pattern and would intentionally generate a large replication workload.

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

Run all four assets. A single worker deliberately limits pressure on the Cloud SQL instance:

```bash
bruin run seed/pipeline.yml --workers 1 --timeout 3600
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
- [PostgreSQL series-generating functions](https://www.postgresql.org/docs/current/functions-srf.html) and [`TRUNCATE`](https://www.postgresql.org/docs/current/sql-truncate.html)
- [Asset definitions, dependencies, and checks](https://getbruin.com/docs/bruin/assets/definition-schema.html)
- [`.bruin.yml` configuration](https://getbruin.com/docs/bruin/secrets/bruinyml.html)
