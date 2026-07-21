#!/usr/bin/env python3
"""The dlt source fixture: a PostgreSQL table with merge + incremental state."""

from __future__ import annotations

import os

import dlt
from dlt.sources.sql_database import sql_database


def main() -> None:
    source = sql_database(credentials=os.environ["SOURCE_DATABASE_URL"], schema="public")
    customers = source.with_resources("customers")
    customers.customers.apply_hints(
        primary_key="id",
        write_disposition="merge",
        incremental=dlt.sources.incremental("updated_at"),
    )
    pipeline = dlt.pipeline(
        pipeline_name="dlt_postgres_customers",
        destination=dlt.destinations.duckdb(os.environ["DLT_DESTINATION_PATH"]),
        dataset_name="analytics",
    )
    load_info = pipeline.run(customers)
    print(load_info)


if __name__ == "__main__":
    main()
