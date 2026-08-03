#!/usr/bin/env python3
"""Create a bare Bruin project and an untracked connection-placeholder file.

This helper never reads connection values from Fivetran. It derives only the
connection *types* from a sanitized snapshot and writes environment-variable
placeholders that the user must fill before an agent proceeds.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SOURCE_TYPES = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "google_cloud_postgresql": "postgres",
    "mysql": "mysql",
    "mssql": "mssql",
    "sql_server": "mssql",
    "sqlserver": "mssql",
    "mongo": "mongo_atlas",
    "mongodb": "mongo_atlas",
    "mongo_atlas": "mongo_atlas",
}
DESTINATION_TYPES = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "bigquery": "google_cloud_platform",
    "google_bigquery": "google_cloud_platform",
    "google_cloud_platform": "google_cloud_platform",
    "snowflake": "snowflake",
    "redshift": "redshift",
    "databricks": "databricks",
    "mssql": "mssql",
    "sql_server": "mssql",
    "duckdb": "duckdb",
}
DATABASE_FIELDS = {
    "postgres": ("host", "port", "database", "username", "password", "ssl_mode"),
    "mysql": ("host", "port", "database", "username", "password"),
    "mssql": ("host", "port", "database", "username", "password"),
    "redshift": ("host", "port", "database", "username", "password"),
    "snowflake": ("account", "username", "password", "database", "schema", "warehouse", "role", "region"),
    "databricks": ("host", "path", "port", "catalog", "schema", "token"),
}


class ScaffoldError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ScaffoldError(message)


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"snapshot not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid snapshot JSON: {exc}")
    if not isinstance(value, dict):
        fail("snapshot must be a JSON object")
    return value


def choose_connection(snapshot: dict[str, Any], requested: str | None) -> dict[str, Any]:
    connections = snapshot.get("connections", snapshot.get("connectors", []))
    if not isinstance(connections, list):
        fail("snapshot connections must be a list")
    candidates = [item for item in connections if isinstance(item, dict)]
    if requested:
        candidates = [item for item in candidates if item.get("id") == requested]
    if len(candidates) != 1:
        label = requested or "the only connection"
        fail(f"snapshot must contain exactly one selected connection for {label!r}")
    return candidates[0]


def choose_destination(snapshot: dict[str, Any], connection: dict[str, Any]) -> dict[str, Any]:
    destinations = snapshot.get("destinations", [])
    if not isinstance(destinations, list):
        return {}
    for destination in destinations:
        if not isinstance(destination, dict):
            continue
        if destination.get("id") == connection.get("destination_id"):
            return destination
        if destination.get("group_id") == connection.get("group_id"):
            return destination
    return {}


def safe_name(value: str, label: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        fail(f"{label} must use letters, digits, and underscores and cannot start with a digit")
    return value


def placeholder(role: str, connection_type: str, field: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]", "_", connection_type).upper()
    return f"${{{role}_{token}_{field.upper()}}}"


def fields_for(connection_type: str, role: str) -> dict[str, str]:
    if connection_type in DATABASE_FIELDS:
        return {field: placeholder(role, connection_type, field) for field in DATABASE_FIELDS[connection_type]}
    if connection_type == "mongo_atlas":
        return {
            "username": placeholder(role, connection_type, "username"),
            "password": placeholder(role, connection_type, "password"),
            "host": placeholder(role, connection_type, "host"),
            "database": placeholder(role, connection_type, "database"),
        }
    if connection_type == "google_cloud_platform":
        return {
            "project_id": placeholder(role, "bigquery", "project_id"),
            "location": placeholder(role, "bigquery", "location"),
            "service_account_file": placeholder(role, "bigquery", "service_account_file"),
        }
    if connection_type == "duckdb":
        return {"path": placeholder(role, "duckdb", "path")}
    fail(f"no safe placeholder schema is bundled for connection type {connection_type!r}")


def add_connection(config: dict[str, Any], connection_type: str, name: str, role: str) -> None:
    connections = config["environments"]["default"]["connections"]
    entries = connections.setdefault(connection_type, [])
    entries.append({"name": name, **fields_for(connection_type, role)})


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def build(args: argparse.Namespace) -> int:
    snapshot = load_snapshot(Path(args.snapshot))
    connection = choose_connection(snapshot, args.connection_id)
    source_type = SOURCE_TYPES.get(str(connection.get("service", "")).lower())
    if not source_type:
        fail(f"unsupported Fivetran source service {connection.get('service')!r}")
    destination = choose_destination(snapshot, connection)
    destination_input = args.destination_type or destination.get("service")
    destination_type = DESTINATION_TYPES.get(str(destination_input or "").lower())
    if not destination_type:
        fail(
            "destination type is unknown; provide --destination-type using a supported Bruin connection type"
        )

    source_name = safe_name(args.source_connection, "source connection name")
    destination_name = safe_name(args.destination_connection, "destination connection name")
    project_dir = Path(args.bruin_dir).expanduser().resolve()
    config_path = project_dir / ".bruin.yml"
    pipeline_path = project_dir / "pipeline.yml"
    if not args.force and (config_path.exists() or pipeline_path.exists()):
        fail(f"{project_dir} already has a pipeline.yml or .bruin.yml; use --force only after review")

    config: dict[str, Any] = {
        "default_environment": "default",
        "environments": {"default": {"connections": {}}},
    }
    add_connection(config, source_type, source_name, "SOURCE")
    add_connection(config, destination_type, destination_name, "DESTINATION")
    pipeline = {
        "name": args.pipeline_name,
        "catchup": False,
    }
    write_yaml(config_path, config)
    write_yaml(pipeline_path, pipeline)
    (project_dir / "assets").mkdir(exist_ok=True)
    print(f"Created {pipeline_path}")
    print(f"Created {config_path} with placeholders only; do not continue until the user fills and tests both connections.")
    return 0


def parser() -> argparse.ArgumentParser:
    parsed = argparse.ArgumentParser(description=__doc__)
    parsed.add_argument("--snapshot", required=True, help="sanitized Fivetran snapshot under fivetran/.artifacts")
    parsed.add_argument("--bruin-dir", default="bruin")
    parsed.add_argument("--connection-id", help="required when the snapshot contains multiple connections")
    parsed.add_argument("--source-connection", default="fivetran_source")
    parsed.add_argument("--destination-connection", default="bruin_destination")
    parsed.add_argument("--destination-type", help="override or supply the Bruin destination connection type")
    parsed.add_argument("--pipeline-name", default="fivetran-migration")
    parsed.add_argument("--force", action="store_true")
    return parsed


def main(argv: list[str] | None = None) -> int:
    try:
        return build(parser().parse_args(argv))
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
