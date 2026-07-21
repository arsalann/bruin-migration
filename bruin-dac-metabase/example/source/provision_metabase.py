#!/usr/bin/env python3
"""Provision the smallest useful Metabase dashboard through its HTTP API."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.environ["METABASE_URL"].rstrip("/")
OUTPUT = Path(os.environ["METABASE_DASHBOARD_OUTPUT"])


def api(path: str, *, method: str = "GET", body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    request = Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        details = error.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} failed: {error.code} {details}") from error


def main() -> int:
    properties = api("/api/session/properties")
    setup_token = properties.get("setup-token")
    if not setup_token:
        raise RuntimeError("Metabase is already initialized; remove .artifacts/metabase and retry")

    api(
        "/api/setup",
        method="POST",
        body={
            "token": setup_token,
            "user": {
                "first_name": "Migration",
                "last_name": "Fixture",
                "email": "fixture@example.test",
                "password": "Fixture-Password-2025!",
            },
            "prefs": {"site_name": "Bruin Migration Fixture", "allow_tracking": False},
            "database": None,
        },
    )
    session = api(
        "/api/session",
        method="POST",
        body={"username": "fixture@example.test", "password": "Fixture-Password-2025!"},
    )
    token = session["id"]

    database = api(
        "/api/database",
        method="POST",
        token=token,
        body={
            "engine": "postgres",
            "name": "Migration Fixture Postgres",
            "details": {
                "host": "postgres",
                "port": 5432,
                "dbname": "metabase",
                "user": "metabase",
                "password": "metabase",
                "ssl": False,
            },
            "is_full_sync": True,
            "is_on_demand": False,
            "auto_run_queries": True,
        },
    )
    database_id = database["id"]
    # Native SQL cards do not depend on Metabase table metadata. Trigger a
    # schema sync for parity with a real source, but do not wait for its
    # asynchronous completion before creating the deterministic fixture.
    api(f"/api/database/{database_id}/sync_schema", method="POST", token=token, body={})

    card = api(
        "/api/card",
        method="POST",
        token=token,
        body={
            "name": "Daily revenue",
            "database_id": database_id,
            "display": "line",
            "dataset_query": {
                "database": database_id,
                "type": "native",
                "native": {
                    "query": """SELECT order_date, SUM(amount) AS revenue
FROM public.orders
GROUP BY order_date
ORDER BY order_date""",
                    "template-tags": {},
                },
            },
            "visualization_settings": {
                "graph.dimensions": ["order_date"],
                "graph.metrics": ["revenue"],
            },
        },
    )
    dashboard = api(
        "/api/dashboard",
        method="POST",
        token=token,
        body={"name": "Migration Fixture Dashboard"},
    )
    api(
        f"/api/dashboard/{dashboard['id']}",
        method="PUT",
        token=token,
        body={
            "name": "Migration Fixture Dashboard",
            "dashcards": [
                {
                    "id": -1,
                    "card_id": card["id"],
                    "row": 0,
                    "col": 0,
                    "size_x": 12,
                    "size_y": 6,
                }
            ],
        },
    )
    captured = api(f"/api/dashboard/{dashboard['id']}", token=token)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(captured, indent=2) + "\n")
    print(f"Saved dashboard {dashboard['id']} to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
