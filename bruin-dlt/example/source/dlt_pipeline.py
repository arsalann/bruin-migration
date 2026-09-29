#!/usr/bin/env python3
"""The dlt source fixture that the migration workflow is tested against.

Three PostgreSQL tables are loaded into ClickHouse with three different
write dispositions, so the fixture exercises each dlt-to-ingestr strategy
mapping:

  public.customers    -> replace                       (full reload)
  public.orders       -> merge on order_id + updated_at (upsert)
  public.order_events -> append on event_ts             (insert-only)

Credentials and the destination are resolved by dlt from
`.dlt/config.toml` and `.dlt/secrets.toml` in the working directory, exactly
as they would be in a real dlt project. Nothing is hard-coded here.
"""

from __future__ import annotations

import argparse
from datetime import datetime

import dlt
from dlt.sources.sql_database import sql_database

PIPELINE_NAME = "dlt_commerce_clickhouse"
DATASET_NAME = "dlt_analytics"
INCREMENTAL_START = datetime(2025, 1, 1)
TABLES = ("customers", "orders", "order_events")


def build_source():
    """Return the configured dlt source with per-resource hints applied."""
    source = sql_database(schema="public", table_names=list(TABLES))

    source.customers.apply_hints(
        primary_key="customer_id",
        write_disposition="replace",
    )
    source.orders.apply_hints(
        primary_key="order_id",
        write_disposition="merge",
        incremental=dlt.sources.incremental("updated_at", initial_value=INCREMENTAL_START),
    )
    source.order_events.apply_hints(
        primary_key="event_id",
        write_disposition="append",
        incremental=dlt.sources.incremental("event_ts", initial_value=INCREMENTAL_START),
    )
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pass-label",
        default="initial",
        help="label recorded in the printed load summary (initial or incremental)",
    )
    args = parser.parse_args()

    pipeline = dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination="clickhouse",
        dataset_name=DATASET_NAME,
        progress=None,
    )
    load_info = pipeline.run(build_source(), loader_file_format="jsonl")
    print(f"dlt {args.pass_label} load complete")
    print(load_info)


if __name__ == "__main__":
    main()
