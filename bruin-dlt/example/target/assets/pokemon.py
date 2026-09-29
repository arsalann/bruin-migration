""" @bruin
name: bruin_v0.pokemon
type: python
image: python:3.13
connection: dlt_target_clickhouse

description: >-
  Migrated from the dlt resource `pokemon` of pipeline dlt_pokeapi. That resource
  is a hand-rolled paginator plus `add_map` row transforms, which a declarative
  ingestr asset cannot express, so the migration target is a Bruin Python asset.
  The dlt code ports almost unchanged; what changes is the wrapper: dlt's
  @dlt.resource + pipeline.run become materialize(), and Bruin's materialization
  block owns the write strategy that dlt's write_disposition used to.

materialization:
  type: table
  strategy: merge

columns:
  - name: pokemon_id
    type: bigint
    primary_key: true
    description: Derived in Python from the API's URL field; dlt primary_key hint.
    checks:
      - name: not_null
      - name: unique
  - name: name
    type: varchar
    checks:
      - name: not_null
  - name: name_upper
    type: varchar
    description: dlt add_map transform, ported verbatim.
    checks:
      - name: not_null
  - name: name_length
    type: bigint
    description: dlt add_map transform, ported verbatim.
    checks:
      - name: not_null
      - name: positive
@bruin """

import os
from typing import Any

import pandas as pd
import requests

API_BASE = "https://pokeapi.co/api/v2"
PAGE_SIZE = 20
REQUEST_TIMEOUT = 30
TOTAL_RECORDS = int(os.environ.get("POKEAPI_TOTAL_RECORDS", "60"))


def pokemon_id_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def add_derived_columns(record: dict[str, Any]) -> dict[str, Any]:
    """Ported unchanged from the dlt resource's add_map transform."""
    record["pokemon_id"] = pokemon_id_from_url(record["url"])
    record["name_upper"] = record["name"].upper()
    record["name_length"] = len(record["name"])
    return record


def fetch_pages(total: int) -> list[dict[str, Any]]:
    """Ported from the dlt resource generator; the paginator is unchanged."""
    records: list[dict[str, Any]] = []
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
            break
        records.extend(add_derived_columns(record) for record in results)
        offset += len(results)
    return records


def materialize() -> pd.DataFrame:
    """Bruin loads the returned frame to the destination through ingestr.

    Only the declared columns are returned. The API's `url` field is dropped on
    purpose: it was an input to the transform, not part of the target schema, and
    dropping it here is the documented column-mapping decision.
    """
    frame = pd.DataFrame(fetch_pages(TOTAL_RECORDS))
    return frame[["pokemon_id", "name", "name_upper", "name_length"]]
