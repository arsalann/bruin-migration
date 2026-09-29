#!/usr/bin/env python3
"""Shared fixture table definitions and engine-neutral row canonicalization.

Both the parity gate and the comparison projection compare the *same* logical
rows across three systems: the PostgreSQL source, the dlt ClickHouse tables, and
the Bruin ingestr ClickHouse tables. Neither dlt's nor ingestr's generated
columns are part of that comparison.
"""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal
from typing import Any, Iterator, Sequence

TABLES: dict[str, dict[str, Any]] = {
    "customers": {
        "columns": ("customer_id", "email", "plan", "country", "signup_date", "updated_at"),
        "key": "customer_id",
        "cursor": None,
        "systems": ("source", "dlt", "bruin"),
        "dlt_dataset_env": "DLT_DATASET",
    },
    "orders": {
        "columns": (
            "order_id",
            "customer_id",
            "status",
            "amount_cents",
            "created_at",
            "updated_at",
        ),
        "key": "order_id",
        "cursor": "updated_at",
        "systems": ("source", "dlt", "bruin"),
        "dlt_dataset_env": "DLT_DATASET",
    },
    "order_events": {
        "columns": ("event_id", "order_id", "event_type", "event_ts"),
        "key": "event_id",
        "cursor": "event_ts",
        "systems": ("source", "dlt", "bruin"),
        "dlt_dataset_env": "DLT_DATASET",
    },
    # The custom-API resource. There is no PostgreSQL side: the source is
    # https://pokeapi.co, so parity is dlt versus the migrated Bruin Python
    # asset. `url` is excluded on purpose — it feeds the transform but is not
    # part of the target schema, which is a recorded column-mapping decision.
    "pokemon": {
        "columns": ("pokemon_id", "name", "name_upper", "name_length"),
        "key": "pokemon_id",
        "cursor": None,
        "systems": ("dlt", "bruin"),
        "dlt_dataset_env": "DLT_API_DATASET",
    },
}


def systems(table: str) -> tuple[str, ...]:
    return TABLES[table]["systems"]


def baseline(table: str) -> str:
    """The system every other system is compared against for this table."""
    return systems(table)[0]

CHUNK_ROWS = 100_000


def canonical(value: Any) -> str:
    """Render one value identically regardless of the engine that produced it."""
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, dt.datetime):
        return value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return format(Decimal(repr(value)).normalize(), "f")
    return str(value)


def canonical_row(row: Sequence[Any]) -> tuple[str, ...]:
    return tuple(canonical(value) for value in row)


def postgres_source(url: str, table: str) -> Iterator[list[tuple[Any, ...]]]:
    import psycopg2
    import psycopg2.extras

    columns = ", ".join(TABLES[table]["columns"])
    connection = psycopg2.connect(url)
    try:
        cursor = connection.cursor(name=f"parity_{table}")
        cursor.itersize = CHUNK_ROWS
        cursor.execute(f"SELECT {columns} FROM public.{table}")
        while True:
            rows = cursor.fetchmany(CHUNK_ROWS)
            if not rows:
                break
            yield rows
        cursor.close()
    finally:
        connection.close()


def clickhouse_client():
    import clickhouse_connect

    url = os.environ["CLICKHOUSE_HTTP_URL"]
    host, port = url.removeprefix("http://").split(":")
    return clickhouse_connect.get_client(
        host=host,
        port=int(port),
        username=os.environ["CLICKHOUSE_USER"],
        password=os.environ["CLICKHOUSE_PASSWORD"],
    )


def clickhouse_source(qualified: str, table: str) -> Iterator[list[tuple[Any, ...]]]:
    columns = ", ".join(TABLES[table]["columns"])
    client = clickhouse_client()
    try:
        with client.query_row_block_stream(f"SELECT {columns} FROM {qualified}") as stream:
            for block in stream:
                yield block
    finally:
        client.close()


def dlt_table(database: str, dataset: str, separator: str, table: str) -> str:
    return f"{database}.{dataset}{separator}{table}"


def bruin_table(database: str, table: str) -> str:
    return f"{database}.{table}"


def readers(table: str) -> dict[str, Any]:
    """Return one row-block reader per system that holds this table."""
    database = os.environ["CLICKHOUSE_DATABASE"]
    separator = os.environ.get("DLT_DATASET_TABLE_SEPARATOR", "___")
    dataset = os.environ[TABLES[table]["dlt_dataset_env"]]
    available = {
        "source": lambda: postgres_source(os.environ["SOURCE_DATABASE_URL"], table),
        "dlt": lambda: clickhouse_source(
            dlt_table(database, dataset, separator, table), table
        ),
        "bruin": lambda: clickhouse_source(
            bruin_table(os.environ["BRUIN_DATABASE"], table), table
        ),
    }
    return {name: available[name] for name in systems(table)}
