#!/usr/bin/env python3
"""Create no-secret Bruin connection placeholders from a redacted capture.

The resulting file is an artifact-only handoff. A user copies it to an
untracked runtime `.bruin.yml` and supplies values themselves; this script
never reads source connection configuration or writes credentials.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment setup error
    raise SystemExit("PyYAML is required: python3 -m pip install PyYAML") from exc


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = EXAMPLE_ROOT / ".artifacts"
SOURCE_TYPES = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "google_cloud_postgresql": "postgres",
    "mysql": "mysql",
    "mssql": "mssql",
    "sql_server": "mssql",
    "mongo": "mongo",
    "mongodb": "mongo",
    "mongo_atlas": "mongo_atlas",
}
DESTINATION_TYPES = {
    "bigquery": "google_cloud_platform",
    "google_cloud_platform": "google_cloud_platform",
    "duckdb": "duckdb",
    "postgres": "postgres",
    "postgresql": "postgres",
    "snowflake": "snowflake",
    "redshift": "redshift",
    "databricks": "databricks",
}


class ScaffoldError(RuntimeError):
    """A safe-to-display scaffold failure."""


def fail(message: str) -> None:
    raise ScaffoldError(message)


def artifact_roots() -> tuple[Path, ...]:
    return (ARTIFACT_ROOT.resolve(),)


def require_artifact_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    for root in artifact_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    fail(
        "output must be under "
        f"{ARTIFACT_ROOT.resolve()}"
    )


def load_connection(capture_dir: Path) -> dict[str, Any]:
    try:
        value = json.loads((capture_dir / "connection.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing capture file: {capture_dir / 'connection.json'}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in capture connection: {exc}")
    if not isinstance(value, dict):
        fail("capture connection must contain an object")
    return value


def placeholders(connection_type: str, name: str, role: str) -> dict[str, Any]:
    prefix = f"{role}_{connection_type.upper()}"
    if connection_type in {"postgres", "mysql", "mssql", "redshift"}:
        return {
            "name": name,
            "host": f"${{{prefix}_HOST}}",
            "port": f"${{{prefix}_PORT}}",
            "database": f"${{{prefix}_DATABASE}}",
            "username": f"${{{prefix}_USERNAME}}",
            "password": f"${{{prefix}_PASSWORD}}",
            "ssl_mode": "require",
        }
    if connection_type == "mongo_atlas":
        return {
            "name": name,
            "host": f"${{{prefix}_HOST}}",
            "database": f"${{{prefix}_DATABASE}}",
            "username": f"${{{prefix}_USERNAME}}",
            "password": f"${{{prefix}_PASSWORD}}",
        }
    if connection_type == "google_cloud_platform":
        return {
            "name": name,
            "project_id": f"${{{prefix}_PROJECT_ID}}",
            "location": f"${{{prefix}_LOCATION}}",
            "use_application_default_credentials": True,
        }
    if connection_type == "duckdb":
        return {"name": name, "path": f"${{{prefix}_PATH}}"}
    if connection_type == "snowflake":
        return {
            "name": name,
            "account_id": f"${{{prefix}_ACCOUNT_ID}}",
            "username": f"${{{prefix}_USERNAME}}",
            "password": f"${{{prefix}_PASSWORD}}",
            "database": f"${{{prefix}_DATABASE}}",
            "warehouse": f"${{{prefix}_WAREHOUSE}}",
            "schema": f"${{{prefix}_SCHEMA}}",
        }
    if connection_type == "databricks":
        return {
            "name": name,
            "host": f"${{{prefix}_HOST}}",
            "http_path": f"${{{prefix}_HTTP_PATH}}",
            "token": f"${{{prefix}_TOKEN}}",
        }
    fail(f"no placeholder fields are defined for Bruin connection type {connection_type!r}")


def build_template(
    connection: dict[str, Any], source_name: str, destination_name: str, destination: str
) -> dict[str, Any]:
    service = connection.get("service")
    if not isinstance(service, str) or not service:
        fail("capture connection is missing a source service")
    source_type = SOURCE_TYPES.get(service.lower())
    if source_type is None:
        fail(f"unsupported Fivetran source service for placeholder scaffold: {service!r}")
    destination_type = DESTINATION_TYPES.get(destination.lower())
    if destination_type is None:
        fail(f"unsupported Bruin destination type for placeholder scaffold: {destination!r}")
    return {
        "default_environment": "default",
        "environments": {
            "default": {
                "connections": {
                    source_type: [placeholders(source_type, source_name, "SOURCE")],
                    destination_type: [
                        placeholders(destination_type, destination_name, "DESTINATION")
                    ],
                }
            }
        },
    }


def scaffold(args: argparse.Namespace) -> None:
    output = require_artifact_path(Path(args.output))
    if output.exists():
        if not args.replace:
            fail(f"scaffold output already exists: {output}; use --replace after review")
        if output in artifact_roots():
            fail("refusing to replace the .artifacts root")
    template = build_template(
        load_connection(Path(args.capture_dir)),
        args.source_connection,
        args.destination_connection,
        args.destination,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    temporary = temporary_dir / output.name
    try:
        temporary.write_text(
            "# Copy this file to an untracked .bruin.yml, fill every placeholder,\n"
            "# test both named connections, then explicitly tell the agent to continue.\n"
            "# This generated handoff contains placeholders only.\n"
            + yaml.safe_dump(template, sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(output)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)
    print(f"Generated no-secret connection placeholder handoff at {output}")


def parser() -> argparse.ArgumentParser:
    parsed = argparse.ArgumentParser(description=__doc__)
    parsed.add_argument("--capture-dir", required=True)
    parsed.add_argument("--destination", required=True)
    parsed.add_argument("--source-connection", default="fivetran_source")
    parsed.add_argument("--destination-connection", default="bruin_destination")
    parsed.add_argument("--output", required=True)
    parsed.add_argument("--replace", action="store_true")
    parsed.set_defaults(handler=scaffold)
    return parsed


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
