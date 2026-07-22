# Fivetran to ingestr / Bruin

Status: hand-authored Cloud SQL PostgreSQL-to-BigQuery comparison pipeline.

## Pipeline

This directory contains one Bruin pipeline with exactly four ingestr assets. It reads the seeded Cloud SQL tables through the `gcp_postgres` connection and writes isolated comparison tables through the `bruin-playground-arsalan` Google Cloud Platform connection.

Bruin writes its target tables to the `bruin_ingestr` BigQuery dataset, with a `_bruin` suffix on each target table.

| PostgreSQL source | Rows | Columns | Primary key | Incremental key | BigQuery target |
| --- | ---: | ---: | --- | --- | --- |
| `bruin_ingestr.customers` | 1,000,000 | 29 | `customer_id` | `updated_at` | `bruin_ingestr.customers_bruin` |
| `bruin_ingestr.products` | 1,000,000 | 29 | `product_id` | `updated_at` | `bruin_ingestr.products_bruin` |
| `bruin_ingestr.orders` | 10,000,000 | 30 | `order_id` | `updated_at` | `bruin_ingestr.orders_bruin` |
| `bruin_ingestr.order_items` | 12,000,000 | 26 | `order_item_id` | `updated_at` | `bruin_ingestr.order_items_bruin` |

The complete deterministic source DDL and column inventory lives in [`../seed/assets/`](../seed/assets/).

## Runtime behavior

- All four assets use ingestr `v1.1.6`, `schema_contract: evolve`, and incremental `merge`.
- Physical PostgreSQL primary keys drive BigQuery upserts, and the included checks reject null or duplicate target keys.
- Every source writer must advance `updated_at` on inserts and updates.
- `customers` and `products` can load in parallel. `orders` waits for `customers`; `order_items` waits for `orders` and `products`.
- The pipeline has no schedule and runs only when invoked.
- Credentials and endpoints remain in an untracked `.bruin.yml`. The current local source connection uses the Cloud SQL Auth Proxy; BigQuery uses Application Default Credentials.

## Commands

Point Bruin at the untracked configuration that defines `gcp_postgres` and `bruin-playground-arsalan`:

```bash
export BRUIN_CONFIG_FILE=/path/to/.bruin.yml
```

Test both endpoints and validate the pipeline before moving data:

```bash
bruin connections test --name gcp_postgres
bruin connections test --name bruin-playground-arsalan
bruin validate ./bruin-ingestr-fivetran/pipeline.yml
```

Run the initial historical load explicitly as a full refresh. Normal runs after that are bounded incremental merges:

```bash
bruin run --full-refresh ./bruin-ingestr-fivetran/pipeline.yml
bruin run ./bruin-ingestr-fivetran/pipeline.yml
```

After the initial load, run a zero-tolerance, failure-on-difference profile against every source table:

```bash
for table in customers products orders order_items; do
  bruin data-diff --full --tolerance 0 --fail-if-diff \
    "gcp_postgres:bruin_ingestr.${table}" \
    "bruin-playground-arsalan:bruin_ingestr.${table}_bruin"
done
```

Do not run the seed pipeline immediately before an incremental load: seeding truncates and rebuilds the source tables. Use a full refresh after an intentional reseed.

## Migration boundary and review decisions

- The four assets are reviewed, hand-authored references. No converter imports Fivetran account configuration, schema selections, schedules, alerts, historical state, or destination settings.
- Fivetran system columns such as `_fivetran_synced` and `_fivetran_deleted` are not recreated in the Bruin tables. Downstream consumers must not assume those columns exist.
- Timestamp-based merge captures inserts and updates, but not hard deletes. Delete parity requires PostgreSQL logical decoding and a separately designed CDC cutover.
- The Cloud SQL instance's logical-decoding settings are not changed by this pipeline.
- Changes to table selection, target naming, incremental keys, delete semantics, or scheduling require human review before cutover.

## Official references

- [Bruin ingestr assets](https://getbruin.com/docs/bruin/assets/ingestr.html)
- [ingestr incremental loading](https://getbruin.com/docs/ingestr/getting-started/incremental-loading.html)
- [ingestr PostgreSQL source](https://getbruin.com/docs/ingestr/supported-sources/postgres.html)
- [Bruin BigQuery platform](https://getbruin.com/docs/bruin/platforms/bigquery.html)
- [Bruin database import](https://getbruin.com/docs/bruin/commands/import.html)
- [Bruin data-diff](https://getbruin.com/docs/bruin/commands/data-diff.html)
