#!/usr/bin/env python3
"""The custom-API dlt source fixture: the case ingestr cannot express.

dlt has no built-in connector catalogue, so an API source is ordinary Python: a
generator that pages through an endpoint, plus `add_map` row transforms. None of
that fits a declarative ingestr asset, so the migration target is a Bruin
**Python asset** instead.

This resource deliberately uses every shape that forces that choice:

  - a hand-rolled paginator over `?limit=&offset=`
  - a derived column parsed out of a URL (`pokemon_id`)
  - `add_map` row transforms (`name_upper`, `name_length`)
  - a `merge` write disposition keyed on the derived column

Source: https://pokeapi.co — free, unauthenticated, and stable for the first N
records, which is what makes it usable as a fixture.
"""

from __future__ import annotations

import argparse
from typing import Any, Iterator

import dlt
import requests

PIPELINE_NAME = "dlt_pokeapi"
DATASET_NAME = "dlt_api"
API_BASE = "https://pokeapi.co/api/v2"
PAGE_SIZE = 20
TOTAL_RECORDS = 60
REQUEST_TIMEOUT = 30


def pokemon_id_from_url(url: str) -> int:
    """PokeAPI only returns a URL; the id has to be parsed out of it."""
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def add_derived_columns(record: dict[str, Any]) -> dict[str, Any]:
    """The `add_map` transform. Pure row-level Python, no ingestr equivalent."""
    record["pokemon_id"] = pokemon_id_from_url(record["url"])
    record["name_upper"] = record["name"].upper()
    record["name_length"] = len(record["name"])
    return record


@dlt.resource(
    name="pokemon",
    primary_key="pokemon_id",
    write_disposition="merge",
    columns={
        "pokemon_id": {"data_type": "bigint", "nullable": False},
        "name": {"data_type": "text", "nullable": False},
        "name_upper": {"data_type": "text", "nullable": False},
        "name_length": {"data_type": "bigint", "nullable": False},
    },
)
def pokemon(total: int = TOTAL_RECORDS) -> Iterator[list[dict[str, Any]]]:
    """Hand-rolled paginator: the part an importer could never extract."""
    offset = 0
    while offset < total:
        response = requests.get(
            f"{API_BASE}/pokemon",
            params={"limit": min(PAGE_SIZE, total - offset), "offset": offset},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()["results"]
        if not results:
            return
        yield results
        offset += len(results)


def build_resource(total: int):
    return pokemon(total).add_map(add_derived_columns)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, default=TOTAL_RECORDS)
    parser.add_argument("--pass-label", default="initial")
    args = parser.parse_args()

    pipeline = dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination="clickhouse",
        dataset_name=DATASET_NAME,
        progress=None,
    )
    load_info = pipeline.run(build_resource(args.total), loader_file_format="jsonl")
    print(f"dlt API {args.pass_label} load complete")
    print(load_info)


if __name__ == "__main__":
    main()
