#!/usr/bin/env python3
"""Generate a disabled, reviewable Bruin ingestr draft from a Fivetran capture."""

from __future__ import annotations

import argparse
import json
import re
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
SCRIPT_VERSION = "1.0.0"
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DESTINATION_DEFAULT_CONNECTION_TYPES = {
    "bigquery": "google_cloud_platform",
    "duckdb": "duckdb",
    "postgres": "postgres",
    "snowflake": "snowflake",
    "redshift": "redshift",
    "databricks": "databricks",
}
SOURCE_CONNECTION_TYPES = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "google_cloud_postgresql": "postgres",
    "mysql": "mysql",
    "mssql": "mssql",
    "sql_server": "mssql",
    "mongo": "mongo",
    "mongodb": "mongo",
    "mongo_atlas": "mongo",
}
SUPPORTED_STRATEGIES = {"replace", "append", "merge", "delete+insert"}
SUPPORTED_INITIAL_SCOPES = {
    "full_history",
    "bounded_history",
    "single_table",
    "other",
}


class GenerationError(RuntimeError):
    """A safe-to-display draft generation failure."""


def fail(message: str) -> None:
    raise GenerationError(message)


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


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing capture file: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"capture file must contain an object: {path}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing decision file: {path}")
    except yaml.YAMLError as exc:
        fail(f"invalid YAML in {path}: {exc}")
    if not isinstance(value, dict):
        fail("decision file must contain a YAML mapping")
    return value


def dump_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def text_value(value: Any, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback


def identifier(value: Any, label: str) -> str:
    text = text_value(value)
    if not IDENTIFIER_RE.fullmatch(text):
        fail(f"{label} must be a simple SQL identifier: {text!r}")
    return text


def as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return []


def type_for_ingestr(value: Any) -> str:
    raw = text_value(value).lower()
    if raw in {"int", "int2", "int4", "integer", "smallint"}:
        return "integer"
    if raw in {"int8", "bigint", "long"}:
        return "bigint"
    if raw in {"float", "float4", "float8", "double", "double precision"}:
        return "float"
    if raw in {"decimal", "numeric", "number"}:
        return "numeric"
    if raw in {"bool", "boolean"}:
        return "boolean"
    if raw in {"date"}:
        return "date"
    if "timestamp" in raw or raw in {"datetime"}:
        return "timestamp"
    if raw in {"json", "jsonb", "variant"}:
        return "json"
    return "varchar"


def destination_connection_type(destination: str) -> str:
    return DESTINATION_DEFAULT_CONNECTION_TYPES.get(destination, destination)


def source_connection_type(service: str) -> str:
    return SOURCE_CONNECTION_TYPES.get(service.lower(), "TODO_source_type")


def unresolved(value: Any) -> bool:
    return not isinstance(value, str) or not value or value.startswith("TODO")


def table_records(schemas: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    records: list[tuple[str, str, dict[str, Any]]] = []
    raw_schemas = schemas.get("schemas", {})
    if not isinstance(raw_schemas, dict):
        return records
    for schema_name, schema in sorted(raw_schemas.items()):
        if not isinstance(schema, dict) or schema.get("enabled") is False:
            continue
        raw_tables = schema.get("tables", {})
        if not isinstance(raw_tables, dict):
            continue
        for table_name, table in sorted(raw_tables.items()):
            if isinstance(table, dict) and table.get("enabled") is not False:
                records.append((str(schema_name), str(table_name), table))
    return records


def strict_decision_issues(
    capture: dict[str, Any], schemas: dict[str, Any], decisions: dict[str, Any]
) -> list[str]:
    """Return every decision that must be explicit before strict generation."""
    issues: list[str] = []
    pipeline = decisions.get("pipeline")
    pipeline = pipeline if isinstance(pipeline, dict) else {}
    connections = decisions.get("connections")
    connections = connections if isinstance(connections, dict) else {}
    initial_run = decisions.get("initial_run")
    initial_run = initial_run if isinstance(initial_run, dict) else {}
    tables = decisions.get("tables")
    tables = tables if isinstance(tables, dict) else {}

    for field in ("name", "start_date"):
        if unresolved(pipeline.get(field)):
            issues.append(f"pipeline.{field} is unresolved")
    for field in ("source_connection", "destination_connection", "destination"):
        if unresolved(connections.get(field)):
            issues.append(f"connections.{field} is unresolved")
    destination = text_value(connections.get("destination"))
    if destination and destination not in DESTINATION_DEFAULT_CONNECTION_TYPES:
        issues.append(f"connections.destination {destination!r} is unsupported")
    service = text_value(capture.get("service"))
    if source_connection_type(service).startswith("TODO"):
        issues.append(f"captured Fivetran service {service!r} is unsupported")

    scope = text_value(initial_run.get("scope"))
    if scope not in SUPPORTED_INITIAL_SCOPES:
        issues.append("initial_run.scope must be full_history, bounded_history, single_table, or other")
    if not initial_run.get("approved"):
        issues.append("initial_run.approved must be true")
    if not initial_run.get("isolated_destination_approved"):
        issues.append("initial_run.isolated_destination_approved must be true")
    for field in ("start_date", "end_date"):
        if unresolved(initial_run.get(field)):
            issues.append(f"initial_run.{field} is unresolved")

    selected_tables = 0
    for source_schema, source_table, source in table_records(schemas):
        key = f"{source_schema}.{source_table}"
        decision = tables.get(key)
        if not isinstance(decision, dict) or not isinstance(decision.get("include"), bool):
            issues.append(f"{key}: include must be explicitly true or false")
            continue
        if not decision["include"]:
            continue
        selected_tables += 1
        for field in ("target_schema", "target_table", "strategy", "schema_contract", "delete_handling"):
            if unresolved(decision.get(field)):
                issues.append(f"{key}: {field} is unresolved")
        strategy = text_value(decision.get("strategy"))
        if strategy and strategy not in SUPPORTED_STRATEGIES:
            issues.append(f"{key}: strategy {strategy!r} is unsupported")
        primary_keys = as_string_list(decision.get("primary_key"))
        if strategy == "merge" and not primary_keys:
            issues.append(f"{key}: merge requires primary_key values")
        if strategy in {"append", "merge", "delete+insert"} and unresolved(
            decision.get("incremental_key")
        ):
            issues.append(f"{key}: {strategy} requires incremental_key")
        for label, value in (
            ("target_schema", decision.get("target_schema")),
            ("target_table", decision.get("target_table")),
            *[("primary_key", primary_key) for primary_key in primary_keys],
        ):
            try:
                identifier(value, f"{key} {label}")
            except GenerationError as exc:
                issues.append(str(exc))
        if strategy in {"append", "merge", "delete+insert"}:
            try:
                identifier(decision.get("incremental_key"), f"{key} incremental_key")
            except GenerationError as exc:
                issues.append(str(exc))
        sync_mode = text_value(source.get("sync_mode"), "unknown")
        if sync_mode.upper() in {"SOFT_DELETE", "HISTORY"} and unresolved(
            decision.get("delete_handling")
        ):
            issues.append(f"{key}: Fivetran {sync_mode} requires delete/history treatment")
    if not selected_tables:
        issues.append("at least one captured table must be explicitly included")
    return sorted(set(issues))


def column_definitions(
    source_columns: dict[str, Any], primary_keys: list[str]
) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    known_targets: set[str] = set()
    for source_name, source in sorted(source_columns.items()):
        if not isinstance(source, dict) or source.get("enabled") is False:
            continue
        target_name = text_value(source.get("name_in_destination"), source_name)
        if not IDENTIFIER_RE.fullmatch(target_name):
            continue
        column: dict[str, Any] = {
            "name": target_name,
            "type": type_for_ingestr(source.get("data_type")),
        }
        if target_name != source_name:
            column["source_column"] = source_name
        if target_name in primary_keys:
            column["primary_key"] = True
            column["checks"] = [{"name": "not_null"}, {"name": "unique"}]
        columns.append(column)
        known_targets.add(target_name)
    for key in primary_keys:
        if key not in known_targets and IDENTIFIER_RE.fullmatch(key):
            columns.append(
                {
                    "name": key,
                    "type": "varchar",
                    "primary_key": True,
                    "checks": [{"name": "not_null"}, {"name": "unique"}],
                }
            )
    return columns


def draft_asset(
    source_schema: str,
    source_table: str,
    source: dict[str, Any],
    decision: dict[str, Any],
    connections: dict[str, Any],
    initial_run: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    key = f"{source_schema}.{source_table}"
    issues: list[str] = []
    target_schema = text_value(decision.get("target_schema"), source_schema)
    target_table = text_value(
        decision.get("target_table"),
        text_value(source.get("name_in_destination"), source_table),
    )
    try:
        target_schema = identifier(target_schema, f"{key} target_schema")
        target_table = identifier(target_table, f"{key} target_table")
    except GenerationError as exc:
        return None, [str(exc)]

    source_connection = text_value(connections.get("source_connection"))
    destination_connection = text_value(connections.get("destination_connection"))
    destination = text_value(connections.get("destination"))
    strategy = text_value(decision.get("strategy"), "replace")
    primary_keys = as_string_list(decision.get("primary_key"))
    incremental_key = text_value(decision.get("incremental_key"))
    schema_contract = text_value(decision.get("schema_contract"), "evolve")
    sync_mode = text_value(source.get("sync_mode"), "unknown")

    if not source_connection or source_connection.startswith("TODO"):
        issues.append(f"{key}: source_connection is unresolved")
    if not destination_connection or destination_connection.startswith("TODO"):
        issues.append(f"{key}: destination_connection is unresolved")
    if not destination or destination.startswith("TODO"):
        issues.append(f"{key}: destination type is unresolved")
    if strategy not in SUPPORTED_STRATEGIES:
        issues.append(f"{key}: strategy {strategy!r} is unsupported or unresolved")
        strategy = "replace"
    if strategy == "merge" and not primary_keys:
        issues.append(f"{key}: merge requires reviewed primary_key values")
    if strategy in {"append", "merge", "delete+insert"} and not incremental_key:
        issues.append(f"{key}: {strategy} requires a reviewed incremental_key")
    if sync_mode.upper() in {"SOFT_DELETE", "HISTORY"} and (
        not text_value(decision.get("delete_handling"))
        or text_value(decision.get("delete_handling")).startswith("TODO")
    ):
        issues.append(f"{key}: Fivetran {sync_mode} semantics need a delete/history decision")

    enabled = bool(initial_run.get("approved")) and bool(
        initial_run.get("isolated_destination_approved")
    )
    if issues:
        enabled = False

    parameters: dict[str, Any] = {
        "version": "v1",
        "source_connection": source_connection or "TODO_source_connection",
        "source_table": f"{source_schema}.{source_table}",
        "destination": destination or "TODO_destination",
        "schema_contract": schema_contract,
    }
    materialization: dict[str, Any] = {"type": "table", "strategy": strategy}
    if strategy in {"append", "merge", "delete+insert"}:
        materialization["incremental_key"] = incremental_key or "TODO_incremental_key"

    asset: dict[str, Any] = {
        "name": f"{target_schema}.{target_table}",
        "type": "ingestr",
        "enabled": enabled,
        "description": (
            f"Draft Fivetran migration for {source_schema}.{source_table}; "
            "review all materialization and delete semantics before enabling."
        ),
        "parameters": parameters,
        "materialization": materialization,
    }
    columns = column_definitions(source.get("columns", {}), primary_keys)
    if columns:
        asset["columns"] = columns
    return asset, issues


def plan_update(issues: list[str], asset_count: int, enabled_count: int) -> str:
    marker = chr(96)
    lines = [
        "## Draft-generation update",
        "",
        f"- Generated {asset_count} ingestr candidate(s); {enabled_count} are enabled.",
        "- Generated files remain under .artifacts and are not reviewed target material.",
        "",
        "## Open human-review items",
        "",
    ]
    if issues:
        lines.extend(f"- [ ] {issue}" for issue in issues)
    else:
        lines.append(
            f"- [ ] Review the approved initial-run scope and generated asset "
            f"mappings before issuing {marker}bruin run{marker}."
        )
    lines.append("")
    return "\n".join(lines)


def build_output(
    root: Path,
    capture: dict[str, Any],
    schemas: dict[str, Any],
    decisions: dict[str, Any],
    strict: bool,
) -> dict[str, Any]:
    pipeline_decision = decisions.get("pipeline", {})
    pipeline_decision = pipeline_decision if isinstance(pipeline_decision, dict) else {}
    connections = decisions.get("connections", {})
    connections = connections if isinstance(connections, dict) else {}
    initial_run = decisions.get("initial_run", {})
    initial_run = initial_run if isinstance(initial_run, dict) else {}
    table_decisions = decisions.get("tables", {})
    table_decisions = table_decisions if isinstance(table_decisions, dict) else {}

    destination = text_value(connections.get("destination"), "TODO_destination")
    destination_connection = text_value(
        connections.get("destination_connection"), "TODO_destination_connection"
    )
    pipeline_name = text_value(pipeline_decision.get("name"), "TODO_fivetran_migration")
    start_date = text_value(pipeline_decision.get("start_date"), "2025-01-01")
    catchup = bool(pipeline_decision.get("catchup", False))
    pipeline = {
        "name": pipeline_name,
        "start_date": start_date,
        "catchup": catchup,
        "default_connections": {
            destination_connection_type(destination): destination_connection
        },
    }
    dump_yaml(root / "pipeline.yml", pipeline)

    issues: list[str] = []
    generated_assets: list[dict[str, Any]] = []
    enabled_count = 0
    for source_schema, source_table, source in table_records(schemas):
        table_key = f"{source_schema}.{source_table}"
        raw_decision = table_decisions.get(table_key, {})
        decision = raw_decision if isinstance(raw_decision, dict) else {}
        if decision.get("include") is False:
            continue
        asset, table_issues = draft_asset(
            source_schema,
            source_table,
            source,
            decision,
            connections,
            initial_run,
        )
        issues.extend(table_issues)
        if asset is None:
            continue
        target_schema, target_table = asset["name"].split(".", maxsplit=1)
        asset_path = root / "assets" / target_schema / f"{target_table}.asset.yml"
        dump_yaml(asset_path, asset)
        generated_assets.append(
            {
                "source": table_key,
                "target": asset["name"],
                "enabled": asset["enabled"],
                "sync_mode": source.get("sync_mode", "unknown"),
                "issues": table_issues,
            }
        )
        enabled_count += int(bool(asset["enabled"]))

    source_service = text_value(capture.get("service"), "unknown")
    template = {
        "default_environment": "default",
        "environments": {
            "default": {
                "connections": {
                    source_connection_type(source_service): [
                        {
                            "name": text_value(
                                connections.get("source_connection"),
                                "TODO_source_connection",
                            ),
                            "TODO_required_fields": "fill from imported service and Bruin docs",
                        }
                    ],
                    destination_connection_type(destination): [
                        {
                            "name": destination_connection,
                            "TODO_required_fields": "fill from destination and Bruin docs",
                        }
                    ],
                }
            }
        },
    }
    dump_yaml(root / ".bruin.yml.example", template)
    selected_sync_modes = sorted(
        {
            text_value(source.get("sync_mode"), "unknown")
            for _, _, source in table_records(schemas)
        }
    )
    configuration_mismatches = [
        "Fivetran credentials and checkpoint state are not portable to Bruin.",
        "Fivetran schedules, retries, alerts, and private networking require separate ownership decisions.",
        "Fivetran schema selection does not establish reviewed source primary or incremental keys.",
    ]
    if any(mode.upper() in {"SOFT_DELETE", "HISTORY"} for mode in selected_sync_modes):
        configuration_mismatches.append(
            "Fivetran SOFT_DELETE or HISTORY behavior requires a hand-authored target design."
        )
    report = {
        "generator_version": SCRIPT_VERSION,
        "strict": strict,
        "source": {
            "service": source_service,
            "selected_sync_modes": selected_sync_modes,
            "suggested_bruin_connection_type": source_connection_type(source_service),
        },
        "target": {
            "destination": destination,
            "suggested_bruin_connection_type": destination_connection_type(destination),
            "connection_name": destination_connection,
        },
        "initial_run": {
            "scope": initial_run.get("scope"),
            "approved": bool(initial_run.get("approved")),
            "isolated_destination_approved": bool(
                initial_run.get("isolated_destination_approved")
            ),
        },
        "assets": generated_assets,
        "configuration_mismatches": configuration_mismatches,
        "assumptions": [
            "Connection types are inferred only from the redacted Fivetran service and reviewed destination type.",
            "Column types and destination renames come from captured schema metadata; casts and generated fields remain human-reviewed.",
            "Generated assets remain drafts until a reviewer accepts them into target reference material.",
        ],
        "unsupported_features": [
            "Fivetran credentials, checkpoints, managed schedules, retry policy, alerts, and private networking.",
            "Automatic handling of Fivetran system columns, Query-Based PostgreSQL semantics, CDC, SOFT_DELETE, and HISTORY mode.",
        ],
        "human_review_items": sorted(set(issues)),
        "next_step": (
            "Keep the draft disabled and resolve every issue in the migration plan."
            if issues or not enabled_count
            else "Validate only after the user confirms the approved v0 run."
        ),
    }
    dump_yaml(root / "conversion-report.yml", report)
    (root / "plan-update.md").write_text(
        plan_update(sorted(set(issues)), len(generated_assets), enabled_count),
        encoding="utf-8",
    )
    return report


def generate(args: argparse.Namespace) -> None:
    capture_dir = Path(args.capture_dir)
    connection = load_json(capture_dir / "connection.json")
    schemas = load_json(capture_dir / "schemas.json")
    decisions = load_yaml(Path(args.decisions))
    output = require_artifact_path(Path(args.output_dir))
    if args.strict:
        issues = strict_decision_issues(connection, schemas, decisions)
        if issues:
            fail(
                "strict draft generation requires complete reviewed decisions:\n- "
                + "\n- ".join(issues)
            )
    if output.exists():
        if not args.replace:
            fail(f"output directory already exists: {output}; use --replace or a new path")
        if output in artifact_roots():
            fail("refusing to replace the .artifacts root")
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        build_output(temporary, connection, schemas, decisions, args.strict)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(f"Generated reviewable draft under {output}")


def parser() -> argparse.ArgumentParser:
    parsed = argparse.ArgumentParser(description=__doc__)
    parsed.add_argument("--capture-dir", required=True)
    parsed.add_argument("--decisions", required=True)
    parsed.add_argument("--output-dir", required=True)
    parsed.add_argument(
        "--strict",
        action="store_true",
        help="fail before generation unless every selected-table and initial-run decision is explicit",
    )
    parsed.add_argument(
        "--replace",
        action="store_true",
        help="replace only the explicit output directory beneath .artifacts",
    )
    parsed.set_defaults(handler=generate)
    return parsed


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
