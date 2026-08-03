#!/usr/bin/env python3
"""Read-only Fivetran inventory capture and review-gated Bruin conversion.

``discover`` and ``capture`` use only GET requests against Fivetran's REST
API. ``convert`` works from a captured, sanitized snapshot and never reads or
writes Fivetran credentials into generated files. Generated files are confined
to a caller-selected ``.artifacts`` directory.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib import error, parse, request

import yaml


CONVERTER_VERSION = "1.0.0"
SNAPSHOT_FORMAT_VERSION = "1"
NORMALIZATION_VERSION = "1"
INGESTR_VERSION = "v1.1.7"
FIVETRAN_API_BASE = "https://api.fivetran.com/v1"

SOURCE_SERVICES = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "google_cloud_postgresql": "postgres",
    "mysql": "mysql",
    "mssql": "mssql",
    "sql_server": "mssql",
    "sqlserver": "mssql",
    "mongodb": "mongo",
    "mongo": "mongo",
    "mongo_atlas": "mongo",
}
SOURCE_CONNECTION_TYPES = {
    "postgres": {"postgres", "postgresql"},
    "mysql": {"mysql"},
    "mssql": {"mssql", "sql_server", "sqlserver"},
    "mongo": {"mongo", "mongodb", "mongo_atlas"},
}
DESTINATION_BY_CONNECTION_TYPE = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "duckdb": "duckdb",
    "google_cloud_platform": "bigquery",
    "bigquery": "bigquery",
    "snowflake": "snowflake",
    "redshift": "redshift",
    "databricks": "databricks",
    "mssql": "mssql",
}
SECRET_FIELD_RE = re.compile(
    r"(?:api[_-]?key|secret|password|passwd|token|authorization|private[_-]?key|"
    r"client[_-]?secret|connection[_-]?string|credential)",
    re.IGNORECASE,
)
SAFETY_FIELD_RE = re.compile(
    r"(?:replicat|capture|delete|history|sync|schema|network|proxy|private|tunnel|"
    r"ssh|ssl|update[_-]?method|change[_-]?tracking|cdc)",
    re.IGNORECASE,
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
REPLICATION_FIELD_ALIASES = {
    "update_method": ("update_method", "replication_method"),
    "delete_capture_enabled": (
        "delete_capture_enabled",
        "capture_deletes",
        "capture_deletes_enabled",
    ),
    "soft_delete_enabled": ("soft_delete_enabled", "soft_delete"),
}


class ImporterError(RuntimeError):
    """A safe-to-display validation or operational error."""


def fail(message: str) -> None:
    raise ImporterError(message)


def load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    except FileNotFoundError:
        fail(f"file not found: {path}")
    except yaml.YAMLError as exc:
        fail(f"invalid YAML in {path}: {exc}")
    return {} if value is None else value


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        fail(f"file not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")


def dump_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(value, handle, sort_keys=False, default_flow_style=False)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def require_artifacts_path(path: Path) -> Path:
    """Reject generated/captured output outside an explicitly named artifact tree."""
    resolved = path.expanduser().resolve()
    if ".artifacts" not in resolved.parts:
        fail(f"output path must be inside a .artifacts directory: {path}")
    return resolved


def ensure_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        fail(f"{label} must be a simple SQL identifier, got {value!r}")
    return value


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "connection"


def bool_value(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def expand_environment(value: Any) -> Any:
    """Expand runtime secrets only in memory; never persist the expanded value."""
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1) or match.group(2)
            if name not in os.environ:
                fail(f"environment variable {name} is required by the Bruin config")
            return os.environ[name]

        return ENV_RE.sub(replace, value)
    if isinstance(value, list):
        return [expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_environment(item) for key, item in value.items()}
    return value


def selected_environment(config: dict[str, Any], name: str) -> dict[str, Any]:
    environments = config.get("environments", {})
    if isinstance(environments, dict):
        environment = environments.get(name)
        if isinstance(environment, dict):
            return environment
    if isinstance(environments, list):
        for environment in environments:
            if isinstance(environment, dict) and environment.get("name") == name:
                return environment
    if name == "default":
        return config
    fail(f"environment {name!r} was not found in the Bruin config")


def generic_values(environment: dict[str, Any], expand: bool) -> dict[str, Any]:
    connections = environment.get("connections", {})
    if not isinstance(connections, dict):
        return {}
    generic = connections.get("generic", [])
    values: dict[str, Any] = {}
    if isinstance(generic, list):
        for item in generic:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                values[item["name"]] = item.get("value")
    elif isinstance(generic, dict):
        for name, value in generic.items():
            values[str(name)] = value.get("value") if isinstance(value, dict) else value
    return expand_environment(values) if expand else values


def bruin_connection_types(environment: dict[str, Any]) -> dict[str, str]:
    """Read names and types only; deliberately ignore all connection values."""
    connections = environment.get("connections", {})
    if not isinstance(connections, dict):
        return {}
    output: dict[str, str] = {}
    for connection_type, entries in connections.items():
        if connection_type == "generic":
            continue
        if isinstance(entries, list):
            candidates = entries
        elif isinstance(entries, dict) and isinstance(entries.get("name"), str):
            candidates = [entries]
        elif isinstance(entries, dict):
            candidates = []
            for name, item in entries.items():
                if isinstance(item, dict):
                    candidate = dict(item)
                    candidate.setdefault("name", str(name))
                    candidates.append(candidate)
        else:
            candidates = []
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("name"), str):
                output[candidate["name"]] = str(candidate.get("type", connection_type)).lower()
    return output


def basic_auth_from_config(config_path: Path, environment_name: str) -> str:
    config = load_yaml(config_path)
    if not isinstance(config, dict):
        fail("Bruin config must be a YAML mapping")
    environment = selected_environment(config, environment_name)
    values = generic_values(environment, expand=False)
    key = expand_environment(values.get("fivetran_api_key"))
    secret = expand_environment(values.get("fivetran_api_secret"))
    encoded_values: list[str] = []
    for name in ("fivetran_api_key_base64", "fivetran_api_key_base64_encoded"):
        if name not in values:
            continue
        value = expand_environment(values[name])
        if not isinstance(value, str):
            fail(f"{name} must be a string")
        encoded_values.append(value)
    if len(set(encoded_values)) > 1:
        fail("Fivetran Base64 credential values disagree")
    encoded = encoded_values[0] if encoded_values else None
    pair: str | None = None
    if isinstance(key, str) or isinstance(secret, str):
        if not isinstance(key, str) or not isinstance(secret, str):
            fail("both fivetran_api_key and fivetran_api_secret are required")
        pair = f"{key}:{secret}"
    if isinstance(encoded, str):
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            fail(f"fivetran_api_key_base64 is not valid Base64: {exc}")
        if pair is not None and decoded != pair:
            fail("Fivetran key/secret and fivetran_api_key_base64 disagree")
        pair = decoded
    if not pair or ":" not in pair:
        fail(
            "provide Fivetran credentials as generic fivetran_api_key and "
            "fivetran_api_secret, or fivetran_api_key_base64"
        )
    return "Basic " + base64.b64encode(pair.encode("utf-8")).decode("ascii")


def basic_auth_from_environment_names(key_name: str, secret_name: str) -> str:
    """Build API authentication from environment variables without persisting them."""
    key = os.environ.get(key_name)
    secret = os.environ.get(secret_name)
    if not key or not secret:
        fail(
            f"set both {key_name} and {secret_name}, or provide --config-file with "
            "Fivetran generic credentials"
        )
    pair = f"{key}:{secret}"
    return "Basic " + base64.b64encode(pair.encode("utf-8")).decode("ascii")


def without_secrets(value: Any) -> Any:
    """Drop credential-shaped fields recursively before snapshot persistence."""
    if isinstance(value, dict):
        return {
            str(key): without_secrets(item)
            for key, item in value.items()
            if not SECRET_FIELD_RE.search(str(key))
        }
    if isinstance(value, list):
        return [without_secrets(item) for item in value]
    return value


def add_unknown_fields(output: dict[str, Any], raw: dict[str, Any], known: Iterable[str]) -> None:
    known_set = set(known)
    fields = sorted(
        str(name)
        for name in raw
        if name not in known_set and not SECRET_FIELD_RE.search(str(name))
    )
    safety = [name for name in fields if SAFETY_FIELD_RE.search(name)]
    informational = [name for name in fields if name not in safety]
    if safety:
        output["unknown_safety_fields"] = safety
    if informational:
        output["unmodeled_fields"] = informational


def blocking_unknown_fields(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    fields = value.get("unknown_safety_fields", [])
    return [str(field) for field in fields] if isinstance(fields, list) else []


def normalize_group(raw: dict[str, Any]) -> dict[str, Any]:
    output = {key: raw[key] for key in ("id", "name") if key in raw}
    add_unknown_fields(output, raw, ("id", "name", "created_at"))
    return output


def normalize_destination(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = ("id", "group_id", "service", "name", "region", "time_zone", "setup_status")
    output = {key: without_secrets(raw[key]) for key in allowed if key in raw}
    add_unknown_fields(
        output,
        raw,
        set(allowed) | {"created_at", "config", "private_link_id", "proxy_agent_id"},
    )
    output["private_networking_configured"] = bool(raw.get("private_link_id") or raw.get("proxy_agent_id"))
    return output


def safe_control_setting(value: Any) -> Any:
    """Keep only scalar replication settings, never arbitrary config objects."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return {"captured": False, "value_type": type(value).__name__}


def normalize_replication_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Capture allowlisted Fivetran replication behavior without config secrets."""
    config = raw.get("config", {})
    sources = (raw, config) if isinstance(config, dict) else (raw,)
    output: dict[str, Any] = {}
    for canonical, aliases in REPLICATION_FIELD_ALIASES.items():
        for source in sources:
            for alias in aliases:
                if alias in source:
                    output[canonical] = safe_control_setting(source[alias])
                    break
            if canonical in output:
                break
    return output


def normalize_connection(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "id", "group_id", "destination_id", "service", "schema", "paused", "schedule_type",
        "sync_frequency", "setup_state", "sync_state", "service_version", "created_at", "succeeded_at",
    )
    output = {key: without_secrets(raw[key]) for key in allowed if key in raw}
    replication_aliases = {
        alias for aliases in REPLICATION_FIELD_ALIASES.values() for alias in aliases
    }
    config = raw.get("config", {})
    if isinstance(config, dict):
        fields = sorted(str(key) for key in config if not SECRET_FIELD_RE.search(str(key)))
        if fields:
            output["source_config_field_names"] = fields
        safety_fields = [
            field for field in fields
            if SAFETY_FIELD_RE.search(field) and field not in replication_aliases
        ]
        if safety_fields:
            output["unknown_safety_fields"] = safety_fields
    replication = normalize_replication_settings(raw)
    if replication:
        output["replication"] = replication
    add_unknown_fields(
        output,
        raw,
        set(allowed)
        | replication_aliases
        | {"config", "status", "connected_by", "private_link_id", "proxy_agent_id"},
    )
    output["private_networking_configured"] = bool(raw.get("private_link_id") or raw.get("proxy_agent_id"))
    return output


def normalize_schema_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"schemas": {}}
    output: dict[str, Any] = {
        key: without_secrets(raw[key])
        for key in ("enable_new_by_default", "schema_change_handling", "is_type_locked")
        if key in raw
    }
    schemas = raw.get("schemas", {})
    normalized_schemas: dict[str, Any] = {}
    if not isinstance(schemas, dict):
        output["schemas"] = {}
        output["unknown_safety_fields"] = ["schemas_not_mapping"]
        return output
    for schema_name, raw_schema in sorted(schemas.items()):
        if not isinstance(raw_schema, dict):
            continue
        schema: dict[str, Any] = {
            "enabled": bool_value(raw_schema.get("enabled"), True),
            "name_in_destination": raw_schema.get("name_in_destination", schema_name),
            "tables": {},
        }
        add_unknown_fields(schema, raw_schema, ("enabled", "name_in_destination", "tables"))
        tables = raw_schema.get("tables", {})
        if isinstance(tables, dict):
            for table_name, raw_table in sorted(tables.items()):
                if not isinstance(raw_table, dict):
                    continue
                table: dict[str, Any] = {
                    "enabled": bool_value(raw_table.get("enabled"), True),
                    "name_in_destination": raw_table.get("name_in_destination", table_name),
                    "sync_mode": raw_table.get("sync_mode"),
                    "is_history_mode_enabled": bool_value(raw_table.get("is_history_mode_enabled")),
                    "columns": {},
                }
                add_unknown_fields(
                    table,
                    raw_table,
                    (
                        "enabled", "name_in_destination", "sync_mode", "is_history_mode_enabled", "columns",
                        "hashed_columns", "has_custom_columns", "new_table_auto_discovery",
                    ),
                )
                for key in ("hashed_columns", "has_custom_columns", "new_table_auto_discovery"):
                    if key in raw_table:
                        table[key] = without_secrets(raw_table[key])
                columns = raw_table.get("columns", {})
                if isinstance(columns, dict):
                    for column_name, raw_column in sorted(columns.items()):
                        if not isinstance(raw_column, dict):
                            continue
                        column: dict[str, Any] = {
                            "enabled": bool_value(raw_column.get("enabled"), True),
                            "name_in_destination": raw_column.get("name_in_destination", column_name),
                        }
                        for key in ("data_type", "is_primary_key", "primary_key", "hashed", "is_hashed"):
                            if key in raw_column:
                                column[key] = without_secrets(raw_column[key])
                        add_unknown_fields(
                            column,
                            raw_column,
                            (
                                "enabled", "name_in_destination", "data_type", "is_primary_key", "primary_key",
                                "hashed", "is_hashed", "enabled_patch_settings",
                            ),
                        )
                        table["columns"][str(column_name)] = column
                schema["tables"][str(table_name)] = table
        normalized_schemas[str(schema_name)] = schema
    output["schemas"] = normalized_schemas
    add_unknown_fields(
        output,
        raw,
        ("enable_new_by_default", "schema_change_handling", "is_type_locked", "schemas"),
    )
    return output


class FivetranClient:
    def __init__(self, authorization: str, timeout: float, retries: int, base_url: str) -> None:
        self.authorization = authorization
        self.timeout = timeout
        self.retries = retries
        self.base_url = base_url.rstrip("/")

    def get(self, endpoint: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            url = f"{url}?{parse.urlencode(params)}"
        headers = {
            "Accept": "application/json;version=2",
            "Authorization": self.authorization,
        }
        for attempt in range(self.retries + 1):
            try:
                req = request.Request(url, headers=headers, method="GET")
                with request.urlopen(req, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    fail("Fivetran returned a non-object JSON response")
                return payload
            except error.HTTPError as exc:
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < self.retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        delay = min(float(retry_after), 30.0) if retry_after else float(2**attempt)
                    except ValueError:
                        delay = float(2**attempt)
                    time.sleep(max(0.0, delay))
                    continue
                fail(f"Fivetran GET {endpoint} failed with HTTP {exc.code}")
            except (error.URLError, TimeoutError) as exc:
                if attempt < self.retries:
                    time.sleep(float(2**attempt))
                    continue
                fail(f"Fivetran GET {endpoint} failed: {type(exc).__name__}")
            except json.JSONDecodeError:
                fail(f"Fivetran GET {endpoint} returned invalid JSON")
        raise AssertionError("retry loop must return or fail")

    def data(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        response = self.get(endpoint, params)
        if "data" not in response:
            fail(f"Fivetran GET {endpoint} omitted data")
        return response["data"]

    def list(self, endpoint: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        current = dict(params or {})
        current.setdefault("limit", "1000")
        result: list[dict[str, Any]] = []
        cursors: set[str] = set()
        while True:
            response = self.get(endpoint, current)
            data = response.get("data")
            if isinstance(data, dict):
                items = data.get("items", data.get("data"))
                next_cursor = data.get("next_cursor") or response.get("next_cursor")
            elif isinstance(data, list):
                items = data
                next_cursor = response.get("next_cursor")
            else:
                fail(f"Fivetran GET {endpoint} returned an invalid collection wrapper")
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                fail(f"Fivetran GET {endpoint} returned invalid collection items")
            result.extend(items)
            if not next_cursor:
                return result
            cursor = str(next_cursor)
            if cursor in cursors:
                fail(f"Fivetran GET {endpoint} repeated a pagination cursor")
            cursors.add(cursor)
            current["cursor"] = cursor


def client_from_args(args: argparse.Namespace) -> FivetranClient:
    if args.config_file:
        config_path = Path(args.config_file).expanduser().resolve()
        authorization = basic_auth_from_config(config_path, args.environment)
    elif args.api_key_env and args.api_secret_env:
        authorization = basic_auth_from_environment_names(args.api_key_env, args.api_secret_env)
    else:
        fail(
            "provide --config-file, or both --api-key-env and --api-secret-env; "
            "do not pass Fivetran credentials as command-line values"
        )
    return FivetranClient(authorization, args.timeout, args.retries, args.base_url)


def discover(args: argparse.Namespace) -> int:
    client = client_from_args(args)
    selected_groups = set(args.group or [])
    selected_connections = set(args.connection or [])
    groups = [normalize_group(item) for item in client.list("groups")]
    destinations = [normalize_destination(item) for item in client.list("destinations")]
    connections = [normalize_connection(item) for item in client.list("connections")]
    if selected_groups:
        groups = [item for item in groups if item.get("id") in selected_groups]
        destinations = [item for item in destinations if item.get("group_id") in selected_groups]
        connections = [item for item in connections if item.get("group_id") in selected_groups]
    if selected_connections:
        connections = [item for item in connections if item.get("id") in selected_connections]
        selected_connection_groups = {item.get("group_id") for item in connections}
        groups = [item for item in groups if item.get("id") in selected_connection_groups]
        destinations = [item for item in destinations if item.get("group_id") in selected_connection_groups]
    output = {
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "snapshot_kind": "discovery",
        "provenance": {
            "source": "Fivetran REST API",
            "api_base": args.base_url,
            "endpoints": ["GET /v1/groups", "GET /v1/destinations", "GET /v1/connections"],
            "read_only": True,
        },
        "captured_at": datetime.now(UTC).isoformat(),
        "groups": sorted(groups, key=lambda item: str(item.get("id", ""))),
        "destinations": sorted(destinations, key=lambda item: str(item.get("id", ""))),
        "connections": sorted(connections, key=lambda item: str(item.get("id", ""))),
    }
    dump_json(require_artifacts_path(Path(args.output)), output)
    return 0


def capture(args: argparse.Namespace) -> int:
    client = client_from_args(args)
    connection_id = args.connection
    connection_raw = client.data(f"connections/{parse.quote(connection_id, safe='')}")
    schema_raw = client.data(f"connections/{parse.quote(connection_id, safe='')}/schemas")
    if not isinstance(connection_raw, dict):
        fail("Fivetran connection detail response must be an object")
    connection = normalize_connection(connection_raw)
    if connection.get("id") and connection.get("id") != connection_id:
        fail("Fivetran connection detail id does not match --connection")
    connection["id"] = connection_id
    group_id = connection.get("group_id")
    destination: dict[str, Any] | None = None
    if isinstance(group_id, str):
        for raw_destination in client.list("destinations"):
            if raw_destination.get("group_id") == group_id:
                destination = normalize_destination(raw_destination)
                break
    output = {
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "snapshot_kind": "capture",
        "provenance": {
            "source": "Fivetran REST API",
            "api_base": args.base_url,
            "endpoints": [
                f"GET /v1/connections/{connection_id}",
                f"GET /v1/connections/{connection_id}/schemas",
                "GET /v1/destinations",
            ],
            "read_only": True,
        },
        "captured_at": datetime.now(UTC).isoformat(),
        "missing_metadata": [
            "Fivetran schema responses may omit unedited columns.",
            "Physical source keys, source row counts, timestamp bounds, dependencies, and CDC prerequisites require source-side enrichment.",
        ],
        "connections": [connection],
        "destinations": [destination] if destination else [],
        "schema_configs": {connection_id: normalize_schema_config(schema_raw)},
    }
    dump_json(require_artifacts_path(Path(args.output)), output)
    return 0


def mapping_value(mapping: Any, keys: Iterable[str]) -> str | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def table_mapping(mapping: dict[str, Any], connection_id: str, source_identity: str) -> dict[str, Any]:
    tables = mapping.get("tables", {})
    if not isinstance(tables, dict):
        return {}
    per_connection = tables.get(connection_id, {})
    if not isinstance(per_connection, dict):
        return {}
    value = per_connection.get(source_identity, {})
    return value if isinstance(value, dict) else {}


def read_connection_map(path: Path) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    mapping = load_yaml(path)
    if not isinstance(mapping, dict):
        fail("connection map must be a YAML mapping")
    issues: list[str] = []
    config_value = mapping.get("bruin_config")
    env_name = mapping.get("environment", "default")
    types: dict[str, str] = {}
    if not isinstance(config_value, str) or not config_value:
        issues.append("connection map must set bruin_config so types can be checked")
    elif not isinstance(env_name, str):
        issues.append("connection-map environment must be a string")
    else:
        config_path = Path(config_value)
        if not config_path.is_absolute():
            config_path = path.parent / config_path
        config = load_yaml(config_path.resolve())
        if not isinstance(config, dict):
            fail("referenced Bruin config must be a YAML mapping")
        types = bruin_connection_types(selected_environment(config, env_name))
    return mapping, types, issues


def decision_for(decisions: dict[str, Any], connection_id: str, source_identity: str) -> tuple[dict[str, Any], dict[str, Any]]:
    connections = decisions.get("connections", {}) if isinstance(decisions, dict) else {}
    connection = connections.get(connection_id, {}) if isinstance(connections, dict) else {}
    if not isinstance(connection, dict):
        connection = {}
    tables = connection.get("tables", {})
    table = tables.get(source_identity, {}) if isinstance(tables, dict) else {}
    return connection, table if isinstance(table, dict) else {}


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return []
    return list(value)


def bruin_type(value: Any) -> str:
    source = str(value or "string").lower()
    aliases = {
        "int": "integer",
        "int4": "integer",
        "int8": "bigint",
        "integer": "integer",
        "bigint": "bigint",
        "smallint": "smallint",
        "decimal": "decimal",
        "numeric": "numeric",
        "float": "float",
        "double": "float",
        "boolean": "boolean",
        "bool": "boolean",
        "timestamp": "timestamp",
        "timestamptz": "timestamp",
        "datetime": "timestamp",
        "date": "date",
        "json": "json",
        "jsonb": "json",
        "object": "json",
        "variant": "json",
        "string": "string",
        "text": "string",
        "varchar": "string",
        "character varying": "string",
    }
    return aliases.get(source, "string")


def approved_bounds(table_decision: dict[str, Any], issues: list[str], context: str) -> dict[str, str] | None:
    snapshot = table_decision.get("initial_snapshot", {})
    if not isinstance(snapshot, dict):
        issues.append(f"{context}: initial_snapshot must be a mapping")
        return None
    start = snapshot.get("start")
    end = snapshot.get("end")
    if not bool_value(snapshot.get("bounds_approved")):
        issues.append(f"{context}: initial snapshot bounds are not approved")
        return None
    if not isinstance(start, str) or not isinstance(end, str):
        issues.append(f"{context}: initial snapshot start and end are required")
        return None
    try:
        start_value = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_value = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        issues.append(f"{context}: initial snapshot bounds must be ISO-8601 timestamps")
        return None
    if start_value.tzinfo is None or end_value.tzinfo is None or start_value >= end_value:
        issues.append(f"{context}: initial snapshot bounds must be timezone-aware and increasing")
        return None
    return {"start": start, "end": end}


def schedule_candidate(connection: dict[str, Any]) -> dict[str, Any]:
    return {
        "fivetran_paused": bool_value(connection.get("paused")),
        "fivetran_schedule_type": connection.get("schedule_type"),
        "fivetran_sync_frequency_minutes": connection.get("sync_frequency"),
        "conversion": "not automatic; approve an explicit Bruin cron separately",
    }


def build_table(
    connection: dict[str, Any],
    schema_name: str,
    schema: dict[str, Any],
    table_name: str,
    table: dict[str, Any],
    mapping: dict[str, Any],
    source_connection: str | None,
    destination_connection: str | None,
    source_connection_type: str | None,
    destination_connection_type: str | None,
    connection_decision: dict[str, Any],
    table_decision: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    """Return asset, inventory, review, and explicit blocking/review issues."""
    source_identity = f"{schema_name}.{table_name}"
    context = f"{connection.get('id')}:{source_identity}"
    issues: list[str] = []
    source_service = SOURCE_SERVICES.get(str(connection.get("service", "")).lower())
    if source_service is None:
        issues.append(f"{context}: unsupported Fivetran source service {connection.get('service')!r}")
    if not source_connection:
        issues.append(f"{context}: source connection mapping is missing")
    elif source_service and source_connection_type not in SOURCE_CONNECTION_TYPES[source_service]:
        issues.append(
            f"{context}: source mapping {source_connection!r} is not a compatible {source_service} Bruin connection"
        )
    destination = DESTINATION_BY_CONNECTION_TYPE.get(str(destination_connection_type or "").lower())
    if not destination_connection:
        issues.append(f"{context}: destination connection mapping is missing")
    elif not destination:
        issues.append(
            f"{context}: destination mapping {destination_connection!r} has unsupported connection type "
            f"{destination_connection_type!r}"
        )
    if not bool_value(connection_decision.get("connection_preflight_completed")):
        issues.append(f"{context}: mapped connections have not passed runtime preflight")
    if not bool_value(table_decision.get("source_metadata_reviewed")):
        issues.append(
            f"{context}: Fivetran schema config is not an exhaustive source schema; source metadata review is required"
        )
    if not bool_value(table_decision.get("approved")):
        issues.append(f"{context}: table conversion is not approved")
    if not bool_value(table_decision.get("target_write_approved")):
        issues.append(f"{context}: target write is not approved")
    if not (
        bool_value(table_decision.get("target_isolated"))
        or bool_value(table_decision.get("existing_target_write_acknowledged"))
    ):
        issues.append(f"{context}: target must be isolated or explicitly acknowledged as an existing target")

    sync_mode = str(table.get("sync_mode") or "").upper()
    if sync_mode == "HISTORY" or bool_value(table.get("is_history_mode_enabled")):
        issues.append(f"{context}: Fivetran history mode is not automatically convertible to a Bruin ingestr asset")
    if table.get("hashed_columns") or table.get("has_custom_columns"):
        issues.append(f"{context}: Fivetran hashed/custom columns require hand-authored target logic")
    if table.get("new_table_auto_discovery"):
        issues.append(f"{context}: Fivetran new-table discovery is not portable")
    for value in (connection, schema, table):
        fields = blocking_unknown_fields(value)
        if fields:
            issues.append(f"{context}: unknown safety-sensitive fields require review: {fields}")

    target_schema_raw = mapping.get("target_schema", schema.get("name_in_destination", schema_name))
    target_table_raw = mapping.get("target_table", table.get("name_in_destination", table_name))
    try:
        target_schema = ensure_identifier(target_schema_raw, f"{context} target schema")
        target_table = ensure_identifier(target_table_raw, f"{context} target table")
    except ImporterError as exc:
        target_schema, target_table = "review_required", slug(table_name).replace("-", "_")
        issues.append(str(exc))

    schema_contract = connection_decision.get("schema_contract", "freeze")
    if schema_contract not in {"freeze", "evolve", "discard_row", "discard_value"}:
        issues.append(f"{context}: schema_contract must be freeze, evolve, discard_row, or discard_value")
        schema_contract = "freeze"
    if not bool_value(connection_decision.get("schema_policy_acknowledged")):
        issues.append(f"{context}: target schema-evolution policy is not acknowledged")
    validation_boundary = connection_decision.get("validation_boundary", {})
    if not isinstance(validation_boundary, dict) or validation_boundary.get("strategy") not in {
        "frozen_writes",
        "consistent_snapshot",
        "source_recheck",
    }:
        issues.append(f"{context}: choose a validation boundary strategy")
    elif not bool_value(validation_boundary.get("approved")):
        issues.append(f"{context}: validation boundary is not approved")

    load_mode = table_decision.get("load_mode")
    if load_mode not in {"merge", "append", "delete+insert", "create+replace"}:
        issues.append(f"{context}: choose load_mode merge, append, delete+insert, or create+replace")
        load_mode = "merge"
    primary_keys = string_list(table_decision.get("primary_keys"))
    incremental_key = table_decision.get("incremental_key")
    if load_mode == "merge" and not primary_keys:
        issues.append(f"{context}: merge requires reviewed primary_keys")
    if load_mode in {"merge", "append", "delete+insert"}:
        if not isinstance(incremental_key, str) or not incremental_key:
            issues.append(f"{context}: {load_mode} requires an incremental_key")
        approved_bounds(table_decision, issues, context)
    if load_mode == "create+replace" and not bool_value(table_decision.get("full_replace_acknowledged")):
        issues.append(f"{context}: create+replace requires full_replace_acknowledged")
    delete_strategy = table_decision.get("hard_delete_strategy")
    if delete_strategy not in {"ignore", "source_tombstones", "periodic_replace"}:
        issues.append(f"{context}: hard_delete_strategy must be ignore, source_tombstones, or periodic_replace")
    elif not bool_value(table_decision.get("hard_delete_handling_approved")):
        issues.append(f"{context}: hard-delete strategy is not approved")
    elif delete_strategy == "ignore" and not bool_value(table_decision.get("delete_loss_acknowledged")):
        issues.append(f"{context}: ignore delete strategy requires delete_loss_acknowledged")

    raw_columns = table.get("columns", {})
    if not isinstance(raw_columns, dict) or not raw_columns:
        issues.append(f"{context}: no columns were captured; enrich source metadata before conversion")
        raw_columns = {}
    output_columns: list[dict[str, Any]] = []
    disabled_columns: list[str] = []
    system_columns: list[str] = []
    source_columns: set[str] = set()
    target_columns: set[str] = set()
    for source_name, raw_column in sorted(raw_columns.items()):
        if not isinstance(raw_column, dict):
            continue
        source_name = str(source_name)
        source_columns.add(source_name)
        if source_name.lower().startswith("_fivetran_"):
            system_columns.append(source_name)
            continue
        if not bool_value(raw_column.get("enabled"), True):
            disabled_columns.append(source_name)
            continue
        target_name_raw = raw_column.get("name_in_destination", source_name)
        try:
            target_name = ensure_identifier(target_name_raw, f"{context} destination column")
        except ImporterError as exc:
            issues.append(str(exc))
            continue
        if target_name in target_columns:
            issues.append(f"{context}: multiple source columns map to target column {target_name!r}")
            continue
        target_columns.add(target_name)
        column: dict[str, Any] = {"name": target_name, "type": bruin_type(raw_column.get("data_type"))}
        if target_name != source_name:
            column["source_column"] = source_name
        if source_name in primary_keys:
            column["primary_key"] = True
        output_columns.append(column)
    for primary_key in primary_keys:
        if primary_key not in source_columns:
            issues.append(f"{context}: primary key {primary_key!r} is not in captured source columns")
    if isinstance(incremental_key, str) and incremental_key and incremental_key not in source_columns:
        issues.append(f"{context}: incremental key {incremental_key!r} is not in captured source columns")
    if not output_columns:
        issues.append(f"{context}: no enabled non-system columns are available for the target asset")

    parameters: dict[str, Any] = {
        "version": INGESTR_VERSION,
        "source_connection": source_connection or "REVIEW_SOURCE_CONNECTION",
        "source_table": source_identity,
        "destination": destination or "REVIEW_DESTINATION",
        "destination_connection": destination_connection or "REVIEW_DESTINATION_CONNECTION",
        "schema_contract": schema_contract,
        "enforce_schema": True,
    }
    if disabled_columns:
        parameters["sql_exclude_columns"] = ",".join(disabled_columns)
    materialization: dict[str, Any] = {"type": "table", "strategy": load_mode}
    if load_mode in {"merge", "append", "delete+insert"} and isinstance(incremental_key, str) and incremental_key:
        materialization["incremental_key"] = incremental_key
    asset = {
        "name": f"{target_schema}.{target_table}",
        "type": "ingestr",
        "enabled": not issues,
        "description": f"Review-gated Bruin candidate imported from Fivetran {source_identity}.",
        "parameters": parameters,
        "materialization": materialization,
        "columns": output_columns,
    }
    inventory = {
        "source_identity": source_identity,
        "fivetran_target": f"{schema.get('name_in_destination', schema_name)}.{table.get('name_in_destination', table_name)}",
        "reviewed_target": asset["name"],
        "selected_source_columns": [column["name"] for column in output_columns],
        "disabled_source_columns": disabled_columns,
        "fivetran_system_columns_not_ported": system_columns,
        "source_sync_mode": table.get("sync_mode"),
        "fivetran_replication": connection.get("replication", {}),
    }
    review = {
        "source_identity": source_identity,
        "enabled": asset["enabled"],
        "load_mode": load_mode,
        "primary_keys": primary_keys,
        "incremental_key": incremental_key if isinstance(incremental_key, str) else "",
        "hard_delete_strategy": delete_strategy,
        "fivetran_replication": connection.get("replication", {}),
        "required_human_decisions": sorted(set(issues)),
    }
    return asset, inventory, review, issues


def decision_template(snapshot: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"connections": {}}
    for connection in snapshot.get("connections", []):
        if not isinstance(connection, dict) or not isinstance(connection.get("id"), str):
            continue
        connection_id = connection["id"]
        schema_config = snapshot.get("schema_configs", {}).get(connection_id, {})
        schemas = schema_config.get("schemas", {}) if isinstance(schema_config, dict) else {}
        tables: dict[str, Any] = {}
        if isinstance(schemas, dict):
            for schema_name, schema in sorted(schemas.items()):
                if not isinstance(schema, dict):
                    continue
                for table_name, table in sorted((schema.get("tables") or {}).items()):
                    if isinstance(table, dict) and bool_value(table.get("enabled"), True):
                        tables[f"{schema_name}.{table_name}"] = {
                            "approved": False,
                            "target_write_approved": False,
                            "target_isolated": False,
                            "existing_target_write_acknowledged": False,
                            "source_metadata_reviewed": False,
                            "load_mode": "merge",
                            "primary_keys": [],
                            "incremental_key": "",
                            "initial_snapshot": {"start": "", "end": "", "bounds_approved": False},
                            "full_replace_acknowledged": False,
                            "hard_delete_strategy": "ignore",
                            "hard_delete_handling_approved": False,
                            "delete_loss_acknowledged": False,
                        }
        output["connections"][connection_id] = {
            "connection_preflight_completed": False,
            "schema_contract": "freeze",
            "schema_policy_acknowledged": False,
            "schedule_approved": False,
            "schedule": "",
            "validation_boundary": {"strategy": "source_recheck", "approved": False},
            "tables": tables,
        }
    return output


def atomic_replace_directory(output_root: Path, build: Any) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="fivetran-convert-", dir=output_root.parent))
    try:
        build(temporary)
        if output_root.exists():
            shutil.rmtree(output_root)
        os.replace(temporary, output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def convert(args: argparse.Namespace) -> int:
    snapshot = load_json(Path(args.snapshot))
    if not isinstance(snapshot, dict):
        fail("Fivetran snapshot must be a JSON object")
    if snapshot.get("normalization_version") != NORMALIZATION_VERSION:
        fail(
            f"unsupported snapshot normalization_version {snapshot.get('normalization_version')!r}; "
            f"expected {NORMALIZATION_VERSION!r}"
        )
    connections = snapshot.get("connections", snapshot.get("connectors", []))
    if not isinstance(connections, list) or not all(isinstance(item, dict) for item in connections):
        fail("snapshot connections must be a list of objects")
    raw_destinations = snapshot.get("destinations", [])
    if not isinstance(raw_destinations, list) or not all(isinstance(item, dict) for item in raw_destinations):
        fail("snapshot destinations must be a list of objects")
    captured_destinations = [without_secrets(item) for item in raw_destinations]
    for destination in captured_destinations:
        destination.pop("config", None)
    schema_configs = snapshot.get("schema_configs", {})
    if not isinstance(schema_configs, dict):
        fail("snapshot schema_configs must be a mapping")
    connection_map_path = Path(args.connections).expanduser().resolve()
    mapping, connection_types, map_issues = read_connection_map(connection_map_path)
    decisions = load_yaml(Path(args.decisions)) if args.decisions else {}
    if not isinstance(decisions, dict):
        fail("migration decisions must be a YAML mapping")
    output_root = require_artifacts_path(Path(args.output_root))
    if output_root.name == ".artifacts":
        fail("output-root must be a run-specific child of .artifacts, not the .artifacts root")

    all_issues = list(map_issues)
    results: list[dict[str, Any]] = []

    def build(root: Path) -> None:
        nonlocal all_issues
        for connection in sorted(connections, key=lambda item: str(item.get("id", ""))):
            raw_connection = connection
            connection = without_secrets(connection)
            connection_id = connection.get("id")
            if not isinstance(connection_id, str) or not connection_id:
                all_issues.append("snapshot contains a connection without an id")
                continue
            connection_issues: list[str] = []
            if "config" in raw_connection:
                # A normalized capture never contains this object. Do not make
                # a manually supplied raw configuration silently usable or
                # persist even its non-secret source settings in the inventory.
                connection.pop("config", None)
                connection_issues.append(
                    f"{connection_id}: raw Fivetran config was discarded; recapture with the read-only importer"
                )
            if blocking_unknown_fields(connection):
                connection_issues.append(
                    f"{connection_id}: unknown safety-sensitive connection fields "
                    f"{blocking_unknown_fields(connection)}"
                )
            sources = mapping.get("sources", {})
            destination_mappings = mapping.get("destinations", {})
            source_connection = mapping_value(sources, (connection_id,))
            destination_connection = mapping_value(
                destination_mappings,
                (str(connection.get("destination_id", "")), str(connection.get("group_id", ""))),
            )
            fivetran_destination = next(
                (
                    destination
                    for destination in captured_destinations
                    if destination.get("id") == connection.get("destination_id")
                    or destination.get("group_id") == connection.get("group_id")
                ),
                {},
            )
            schema_config = schema_configs.get(connection_id, {})
            if not isinstance(schema_config, dict):
                schema_config = {}
                connection_issues.append(f"{connection_id}: schema configuration is missing or malformed")
            if blocking_unknown_fields(schema_config):
                connection_issues.append(
                    f"{connection_id}: unknown safety-sensitive schema fields "
                    f"{blocking_unknown_fields(schema_config)}"
                )
            connection_decision, _ = decision_for(decisions, connection_id, "")
            connector_root = root / slug(connection_id)
            assets_root = connector_root / "assets"
            inventories: list[dict[str, Any]] = []
            reviews: list[dict[str, Any]] = []
            schemas = schema_config.get("schemas", {})
            if not isinstance(schemas, dict):
                schemas = {}
                connection_issues.append(f"{connection_id}: schema configuration schemas must be a mapping")
            for schema_name, schema in sorted(schemas.items()):
                if not isinstance(schema, dict) or not bool_value(schema.get("enabled"), True):
                    continue
                if blocking_unknown_fields(schema):
                    connection_issues.append(
                        f"{connection_id}:{schema_name}: unknown safety-sensitive schema fields "
                        f"{blocking_unknown_fields(schema)}"
                    )
                    continue
                tables = schema.get("tables", {})
                if not isinstance(tables, dict):
                    connection_issues.append(f"{connection_id}:{schema_name}: tables must be a mapping")
                    continue
                for table_name, table in sorted(tables.items()):
                    if not isinstance(table, dict) or not bool_value(table.get("enabled"), True):
                        continue
                    source_identity = f"{schema_name}.{table_name}"
                    _, table_decision = decision_for(decisions, connection_id, source_identity)
                    asset, inventory, review, table_issues = build_table(
                        connection,
                        str(schema_name),
                        schema,
                        str(table_name),
                        table,
                        table_mapping(mapping, connection_id, source_identity),
                        source_connection,
                        destination_connection,
                        connection_types.get(source_connection or ""),
                        connection_types.get(destination_connection or ""),
                        connection_decision,
                        table_decision,
                    )
                    asset["enabled"] = bool(asset["enabled"] and not connection_issues)
                    if connection_issues:
                        review["enabled"] = False
                        review["required_human_decisions"] = sorted(
                            set(review["required_human_decisions"] + connection_issues)
                        )
                    target_schema, target_table = asset["name"].split(".", 1)
                    dump_yaml(assets_root / target_schema / f"{target_table}.asset.yml", asset)
                    inventories.append(inventory)
                    reviews.append(review)
                    all_issues.extend(table_issues)
            schedule = connection_decision.get("schedule")
            pipeline: dict[str, Any] = {"name": f"fivetran-{slug(connection_id)}", "catchup": False}
            if bool_value(connection_decision.get("schedule_approved")):
                if isinstance(schedule, str) and schedule.strip():
                    pipeline["schedule"] = schedule.strip()
                else:
                    connection_issues.append(f"{connection_id}: schedule is approved but no explicit cron was supplied")
            dump_yaml(connector_root / "pipeline.yml", pipeline)
            connector_report = {
                "connection_id": connection_id,
                "generated": bool(inventories),
                "issues": sorted(set(connection_issues)),
                "schedule_candidate": schedule_candidate(connection),
                "configuration_mismatches": [
                    "Fivetran schedules and private checkpoint state are not migrated automatically.",
                    "Fivetran system columns are not reproduced; review downstream dependencies.",
                    "Fivetran schema selection does not prove a complete source-column inventory.",
                ],
            }
            dump_yaml(
                connector_root / "inventory.yml",
                {
                    "connection": connection,
                    "fivetran_destination": fivetran_destination,
                    "source_connection": source_connection,
                    "source_connection_type": connection_types.get(source_connection or ""),
                    "destination_connection": destination_connection,
                    "destination_connection_type": connection_types.get(destination_connection or ""),
                    "fivetran_schema_policy": {
                        key: schema_config[key]
                        for key in ("schema_change_handling", "enable_new_by_default", "is_type_locked")
                        if key in schema_config
                    },
                    "tables": inventories,
                },
            )
            dump_yaml(
                connector_root / "review.yml",
                {
                    "connection_id": connection_id,
                    "schedule_candidate": schedule_candidate(connection),
                    "validation_boundary": connection_decision.get("validation_boundary", {}),
                    "tables": reviews,
                },
            )
            dump_yaml(connector_root / "conversion-report.yml", connector_report)
            results.append(connector_report)
            all_issues.extend(connection_issues)
        dump_yaml(root / "migration-decisions.template.yml", decision_template(snapshot))
        dump_yaml(
            root / "conversion-report.yml",
            {
                "converter_version": CONVERTER_VERSION,
                "normalization_version": NORMALIZATION_VERSION,
                "issues": sorted(set(all_issues)),
                "connections": results,
            },
        )

    atomic_replace_directory(output_root, build)
    if args.strict and all_issues:
        return 1
    return 0


def parser() -> argparse.ArgumentParser:
    parsed = argparse.ArgumentParser(description=__doc__)
    commands = parsed.add_subparsers(dest="command", required=True)

    def add_api_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--config-file", help="untracked Bruin config containing Fivetran generic credentials")
        command.add_argument("--api-key-env", help="environment variable that contains the Fivetran API key")
        command.add_argument("--api-secret-env", help="environment variable that contains the Fivetran API secret")
        command.add_argument("--environment", default="default")
        command.add_argument("--base-url", default=FIVETRAN_API_BASE)
        command.add_argument("--timeout", type=float, default=30.0)
        command.add_argument("--retries", type=int, default=3)

    discover_parser = commands.add_parser("discover", help="read safe Fivetran account inventory using GET only")
    add_api_options(discover_parser)
    discover_parser.add_argument("--group", action="append")
    discover_parser.add_argument("--connection", action="append")
    discover_parser.add_argument("--output", required=True)
    discover_parser.set_defaults(handler=discover)

    capture_parser = commands.add_parser("capture", help="capture one sanitized connection and schema configuration")
    add_api_options(capture_parser)
    capture_parser.add_argument("--connection", required=True)
    capture_parser.add_argument("--output", required=True)
    capture_parser.set_defaults(handler=capture)

    convert_parser = commands.add_parser("convert", help="convert an offline Fivetran snapshot into Bruin candidates")
    convert_parser.add_argument("--snapshot", required=True)
    convert_parser.add_argument("--connections", required=True, help="connection/table mapping YAML")
    convert_parser.add_argument("--decisions", help="reviewed approval YAML")
    convert_parser.add_argument("--output-root", required=True)
    convert_parser.add_argument("--strict", action="store_true", help="return nonzero for any unresolved review item")
    convert_parser.set_defaults(handler=convert)
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except ImporterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
