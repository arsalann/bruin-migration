#!/usr/bin/env python3
"""Convert dlt credentials into Bruin connections without exposing any value.

This is the one step of the dlt-to-Bruin migration that a migration agent must
not perform by reading files itself. dlt keeps credentials in
`.dlt/secrets.toml`, in environment variables, or inside a connection string,
and any of those would put a live secret into the agent's context.

The converter reads those inputs, writes the matching Bruin connection entries
into a Git-ignored `.bruin.yml`, and prints only a non-secret report: which
connections were written, which Bruin fields were populated, where each value
came from, and which fields still need a human decision. Every secret value
that passes through the process is checked against the report and against
stdout before anything is printed.

Everything else in a dlt project — the pipeline Python, `.dlt/config.toml`,
resource hints, write dispositions, incremental cursors — is plain
configuration that the agent should read and map directly.

Usage:
    python3 convert_dlt_connections.py \\
      --dlt-project-dir path/to/dlt/project \\
      --output .bruin.yml \\
      --source-connection dlt_source \\
      --destination-connection dlt_destination

Add `--placeholders` to emit `${ENV_VAR}` references instead of real values,
`--allow-env` to fill fields from dlt's environment-variable names, and
`--replace` to overwrite connections that already exist under those names.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment setup error
    raise SystemExit("PyYAML is required: python3 -m pip install PyYAML") from exc


SECRET_FIELDS = frozenset(
    {
        "password",
        "token",
        "access_token",
        "private_key",
        "private_key_passphrase",
        "client_secret",
        "api_key",
        "secret_access_key",
        "service_account_json",
        "credentials_json",
    }
)

# dlt destination or SQLAlchemy driver name -> Bruin connection type.
DLT_TO_BRUIN_TYPE = {
    "athena": "athena",
    "bigquery": "google_cloud_platform",
    "clickhouse": "clickhouse",
    "databricks": "databricks",
    "duckdb": "duckdb",
    "motherduck": "motherduck",
    "mssql": "mssql",
    "mysql": "mysql",
    "postgres": "postgres",
    "postgresql": "postgres",
    "redshift": "redshift",
    "snowflake": "snowflake",
    "synapse": "mssql",
}

# Bruin connection type -> (bruin_field, dlt_field_candidates, required).
FIELD_MAPS: dict[str, tuple[tuple[str, tuple[str, ...], bool], ...]] = {
    "postgres": (
        ("host", ("host",), True),
        ("port", ("port",), True),
        ("database", ("database", "dbname"), True),
        ("username", ("username", "user"), True),
        ("password", ("password",), True),
        ("schema", ("schema",), False),
        ("ssl_mode", ("sslmode", "ssl_mode"), False),
    ),
    "redshift": (
        ("host", ("host",), True),
        ("port", ("port",), True),
        ("database", ("database", "dbname"), True),
        ("username", ("username", "user"), True),
        ("password", ("password",), True),
        ("ssl_mode", ("sslmode", "ssl_mode"), False),
    ),
    "mysql": (
        ("host", ("host",), True),
        ("port", ("port",), True),
        ("database", ("database", "dbname"), True),
        ("username", ("username", "user"), True),
        ("password", ("password",), True),
    ),
    "mssql": (
        ("host", ("host", "server"), True),
        ("port", ("port",), True),
        ("database", ("database", "dbname"), True),
        ("username", ("username", "user"), True),
        ("password", ("password",), True),
    ),
    "clickhouse": (
        ("host", ("host",), True),
        ("port", ("port",), True),
        ("http_port", ("http_port",), False),
        ("database", ("database", "dataset_name"), True),
        ("username", ("username", "user"), True),
        ("password", ("password",), True),
        ("secure", ("secure",), False),
    ),
    "snowflake": (
        ("account", ("host", "account"), True),
        ("username", ("username", "user"), True),
        ("password", ("password",), False),
        ("private_key", ("private_key",), False),
        ("database", ("database",), True),
        ("warehouse", ("warehouse",), False),
        ("schema", ("schema",), False),
        ("role", ("role",), False),
    ),
    "google_cloud_platform": (
        ("project_id", ("project_id",), True),
        ("location", ("location",), False),
        ("service_account_json", ("service_account_json", "credentials_json"), False),
        ("service_account_file", ("service_account_file",), False),
        ("access_token", ("access_token",), False),
    ),
    "databricks": (
        # Bruin's Databricks connection field is `path`, not `http_path`.
        ("host", ("server_hostname", "host"), True),
        ("path", ("http_path", "path"), True),
        ("token", ("access_token", "token"), True),
        ("catalog", ("catalog",), False),
        ("schema", ("schema",), False),
    ),
    "duckdb": (("path", ("database", "path"), True),),
    "motherduck": (
        ("database", ("database",), True),
        ("token", ("password", "token"), True),
    ),
    "athena": (
        ("region", ("region_name", "region"), True),
        ("access_key_id", ("aws_access_key_id", "access_key_id"), False),
        ("secret_access_key", ("aws_secret_access_key", "secret_access_key"), False),
        ("query_results_path", ("query_result_bucket", "query_results_path"), False),
    ),
}

ENV_PREFIXES = {"source": "SOURCES", "destination": "DESTINATION"}

# dlt stores a GCP service account as flat fields, while Bruin wants one JSON
# blob in `service_account_json`. These are the flat fields to reassemble from.
GCP_SERVICE_ACCOUNT_FIELDS = (
    "private_key",
    "private_key_id",
    "client_email",
    "client_id",
    "token_uri",
    "auth_uri",
    "auth_provider_x509_cert_url",
    "client_x509_cert_url",
)
# At least one of these must end up populated, or the GCP connection cannot
# authenticate at all.
GCP_CREDENTIAL_FIELDS = ("service_account_json", "service_account_file", "access_token")

# Report fields that hold operator-supplied identifiers rather than anything
# derived from dlt credentials. The secret self-check skips them.
IDENTIFIER_REPORT_FIELDS = frozenset({"role", "dlt_section", "bruin_connection_name"})


class ConversionError(RuntimeError):
    """A safe-to-display conversion failure. Never carries a secret value."""


def fail(message: str) -> None:
    raise ConversionError(message)


def normalize_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        fail(f"cannot parse {path.name}: line {getattr(exc, 'lineno', 'unknown')}")
    except OSError:
        fail(f"cannot read {path.name}")
    return {}


def gcp_service_account_json(fields: dict[str, Any], project_id: Any) -> str | None:
    """Rebuild a GCP service-account JSON blob from dlt's flat credential fields.

    dlt keeps `private_key`, `client_email`, and friends as separate TOML keys.
    Bruin needs the single JSON document Google's auth libraries expect, so the
    minimum viable set is reassembled here rather than reported as unmappable.
    """
    if not fields.get("private_key") or not fields.get("client_email"):
        return None
    document: dict[str, Any] = {
        "type": fields.get("type") or "service_account",
        "project_id": project_id,
        "token_uri": fields.get("token_uri") or "https://oauth2.googleapis.com/token",
    }
    for field in GCP_SERVICE_ACCOUNT_FIELDS:
        if field == "token_uri":
            continue
        if fields.get(field) is not None:
            document[field] = fields[field]
    return json.dumps(document)


def parse_connection_string(value: str) -> tuple[str | None, dict[str, Any]]:
    """Split a dlt connection string into a driver name and credential fields."""
    parsed = urlparse(value)
    if not parsed.scheme:
        return None, {}
    driver = normalize_key(parsed.scheme.split("+", 1)[0])
    fields: dict[str, Any] = {}
    if parsed.hostname:
        fields["host"] = parsed.hostname
    if parsed.port:
        fields["port"] = parsed.port
    if parsed.username:
        fields["username"] = unquote(parsed.username)
    if parsed.password:
        fields["password"] = unquote(parsed.password)
    database = parsed.path.lstrip("/")
    if database:
        fields["database"] = database
    for key, query_value in parse_qsl(parsed.query):
        fields.setdefault(normalize_key(key), query_value)
    return driver, fields


def credential_fields(raw: Any) -> tuple[str | None, dict[str, Any]]:
    """Return (driver_hint, flat credential fields) for a dlt credentials value."""
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            # dlt also accepts a whole service-account JSON document as a string.
            try:
                return credential_fields(json.loads(stripped))
            except json.JSONDecodeError:
                fail("credentials look like JSON but could not be parsed")
        return parse_connection_string(raw)
    if not isinstance(raw, dict):
        return None, {}
    fields = {normalize_key(key): value for key, value in raw.items() if value is not None}
    driver = fields.pop("drivername", None) or fields.pop("driver", None)
    connection_string = fields.pop("connection_string", None)
    if isinstance(connection_string, str):
        nested_driver, nested_fields = parse_connection_string(connection_string)
        driver = driver or nested_driver
        for key, value in nested_fields.items():
            fields.setdefault(key, value)
    query = fields.pop("query", None)
    if isinstance(query, dict):
        for key, value in query.items():
            fields.setdefault(normalize_key(key), value)
    if isinstance(driver, str):
        driver = normalize_key(driver.split("+", 1)[0])
    return driver if isinstance(driver, str) else None, fields


def env_name(role: str, dlt_name: str, field: str) -> str:
    return f"{ENV_PREFIXES[role]}__{dlt_name.upper()}__CREDENTIALS__{field.upper()}"


def placeholder_name(role: str, connection_type: str, field: str) -> str:
    return f"{role.upper()}_{connection_type.upper()}_{field.upper()}"


def discover(secrets: dict[str, Any], config: dict[str, Any], role: str) -> tuple[str, Any]:
    """Find the single dlt source or destination section to convert."""
    if role == "destination":
        merged: dict[str, Any] = {}
        for document in (config, secrets):
            section = document.get("destination")
            if isinstance(section, dict):
                for key, value in section.items():
                    if isinstance(value, dict):
                        merged.setdefault(key, {}).update(value)
                    else:
                        merged.setdefault(key, value)
        candidates = {
            name: value.get("credentials", value)
            for name, value in merged.items()
            if isinstance(value, dict) and name not in {"credentials"}
        }
        if "credentials" in merged and not candidates:
            candidates = {"unnamed": merged["credentials"]}
    else:
        merged = {}
        for document in (config, secrets):
            section = document.get("sources")
            if isinstance(section, dict):
                for key, value in section.items():
                    if isinstance(value, dict):
                        merged.setdefault(key, {}).update(value)
        candidates = {
            name: value["credentials"]
            for name, value in merged.items()
            if isinstance(value, dict) and "credentials" in value
        }
        if not candidates:
            for document in (secrets, config):
                if "credentials" in document:
                    candidates = {"unnamed": document["credentials"]}
                    break
    usable = {name: value for name, value in candidates.items() if value is not None}
    if not usable:
        fail(
            f"no dlt {role} credentials found; pass --{role}-dlt-name and confirm the "
            "dlt project directory, or supply the values through environment variables "
            "with --allow-env"
        )
    if len(usable) > 1:
        fail(
            f"found {len(usable)} dlt {role} sections ({', '.join(sorted(usable))}); "
            f"migrate one at a time with --{role}-dlt-name"
        )
    return next(iter(usable.items()))


def build_connection(
    role: str,
    dlt_name: str,
    raw_credentials: Any,
    bruin_name: str,
    allow_env: bool,
    placeholders: bool,
    forced_type: str | None,
) -> tuple[str, dict[str, Any], dict[str, Any], set[str]]:
    driver, fields = credential_fields(raw_credentials)
    lookup = forced_type or driver or dlt_name
    connection_type = DLT_TO_BRUIN_TYPE.get(normalize_key(lookup))
    if connection_type is None:
        fail(
            f"no reviewed Bruin mapping for dlt {role} {normalize_key(lookup)!r}; "
            "add the connection by hand and record it as an open decision, or pass "
            f"--{role}-bruin-type with a supported type "
            f"({', '.join(sorted(set(DLT_TO_BRUIN_TYPE.values())))})"
        )

    connection: dict[str, Any] = {"name": bruin_name}
    populated: list[str] = []
    from_env: list[str] = []
    missing_required: list[str] = []
    missing_optional: list[str] = []
    secrets_seen: set[str] = set()

    for bruin_field, candidates, required in FIELD_MAPS[connection_type]:
        value = None
        for candidate in candidates:
            if candidate in fields:
                value = fields[candidate]
                break
        source = "dlt-config"
        if value is None and allow_env:
            for candidate in candidates:
                env_value = os.environ.get(env_name(role, dlt_name, candidate))
                if env_value is not None:
                    value, source = env_value, "environment"
                    break
        if value is None:
            (missing_required if required else missing_optional).append(bruin_field)
            continue
        if placeholders:
            connection[bruin_field] = f"${{{placeholder_name(role, connection_type, bruin_field)}}}"
        else:
            connection[bruin_field] = value
            if bruin_field in SECRET_FIELDS and isinstance(value, str) and len(value) >= 4:
                secrets_seen.add(value)
        populated.append(bruin_field)
        if source == "environment":
            from_env.append(bruin_field)

    if connection_type == "google_cloud_platform":
        if not any(field in connection for field in GCP_CREDENTIAL_FIELDS):
            rebuilt = gcp_service_account_json(fields, connection.get("project_id"))
            if rebuilt is not None:
                if placeholders:
                    connection["service_account_json"] = (
                        f"${{{placeholder_name(role, connection_type, 'service_account_json')}}}"
                    )
                else:
                    connection["service_account_json"] = rebuilt
                    secrets_seen.add(str(fields["private_key"]))
                populated.append("service_account_json")
                missing_optional = [
                    field for field in missing_optional if field != "service_account_json"
                ]
        # A GCP connection with no credential material cannot authenticate, so
        # this is blocking rather than an optional field the user may ignore.
        if not any(field in connection for field in GCP_CREDENTIAL_FIELDS):
            missing_required.append(" or ".join(GCP_CREDENTIAL_FIELDS))

    mapped_names = {name for _, names, _ in FIELD_MAPS[connection_type] for name in names}
    if connection_type == "google_cloud_platform" and "service_account_json" in connection:
        mapped_names |= {*GCP_SERVICE_ACCOUNT_FIELDS, "type"}
    unmapped = sorted(key for key in fields if key not in mapped_names)
    report = {
        "role": role,
        "dlt_section": f"{'destination' if role == 'destination' else 'sources'}.{dlt_name}",
        "bruin_connection_type": connection_type,
        "bruin_connection_name": bruin_name,
        "values_written": "env-var placeholders" if placeholders else "real values",
        "fields_populated": sorted(populated),
        "fields_from_environment": sorted(from_env),
        "fields_missing_required": sorted(missing_required),
        "fields_missing_optional": sorted(missing_optional),
        "dlt_fields_without_bruin_mapping": unmapped,
    }
    return connection_type, connection, report, secrets_seen


def merge_into_config(
    output: Path,
    environment: str,
    entries: list[tuple[str, dict[str, Any]]],
    replace: bool,
) -> None:
    document: dict[str, Any] = {}
    if output.is_file():
        try:
            loaded = yaml.safe_load(output.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            fail(f"cannot parse existing Bruin config: {output}")
        if not isinstance(loaded, dict):
            fail(f"existing Bruin config is not a mapping: {output}")
        document = loaded
    document.setdefault("default_environment", environment)
    environments = document.setdefault("environments", {})
    if not isinstance(environments, dict):
        fail("existing Bruin config has an invalid `environments` section")
    target = environments.setdefault(environment, {})
    if not isinstance(target, dict):
        fail(f"existing Bruin environment {environment!r} is not a mapping")
    connections = target.setdefault("connections", {})
    if not isinstance(connections, dict):
        fail(f"existing Bruin environment {environment!r} has an invalid `connections` section")

    for connection_type, connection in entries:
        bucket = connections.setdefault(connection_type, [])
        if not isinstance(bucket, list):
            fail(f"existing `{connection_type}` connections are not a list")
        index = next(
            (
                position
                for position, existing in enumerate(bucket)
                if isinstance(existing, dict) and existing.get("name") == connection["name"]
            ),
            None,
        )
        if index is None:
            bucket.append(connection)
            continue
        if not replace:
            fail(
                f"connection {connection['name']!r} already exists in {output.name}; "
                "review it and re-run with --replace to overwrite it"
            )
        bucket[index] = connection

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    output.chmod(0o600)


def assert_no_secrets(reports: list[dict[str, Any]], secrets: set[str]) -> None:
    """Check the report's value-bearing fields against every secret read.

    Operator-supplied identifiers — the dlt project path, the output path, the
    environment, and the Bruin connection names — are excluded on purpose. They
    are chosen by the user, not copied out of dlt credentials, and a credential
    that happens to be a substring of one of them must not block the conversion.
    """
    surface: list[str] = []
    for report in reports:
        for key, value in report.items():
            if key in IDENTIFIER_REPORT_FIELDS:
                continue
            surface.extend(value if isinstance(value, list) else [str(value)])
    scanned = "\n".join(surface)
    for secret in secrets:
        if secret in scanned:
            fail("refusing to emit a report that contains a credential value")


def convert(args: argparse.Namespace) -> None:
    project = Path(args.dlt_project_dir).expanduser().resolve()
    dlt_dir = project / ".dlt"
    if not project.is_dir():
        fail(f"dlt project directory does not exist: {project}")
    secrets = read_toml(dlt_dir / "secrets.toml")
    config = read_toml(dlt_dir / "config.toml")
    if not secrets and not config and not args.allow_env:
        fail(f"no .dlt/config.toml or .dlt/secrets.toml under {project}")

    output = Path(args.output).expanduser().resolve()
    entries: list[tuple[str, dict[str, Any]]] = []
    reports: list[dict[str, Any]] = []
    secrets_seen: set[str] = set()

    roles = (
        ("source", args.source_connection, args.source_dlt_name, args.source_bruin_type),
        (
            "destination",
            args.destination_connection,
            args.destination_dlt_name,
            args.destination_bruin_type,
        ),
    )
    for role, bruin_name, forced_dlt_name, forced_type in roles:
        if bruin_name is None:
            continue
        if forced_dlt_name:
            section = "destination" if role == "destination" else "sources"
            raw = None
            for document in (secrets, config):
                candidate = document.get(section, {})
                if isinstance(candidate, dict) and forced_dlt_name in candidate:
                    entry = candidate[forced_dlt_name]
                    raw = entry.get("credentials", entry) if isinstance(entry, dict) else entry
                    if raw is not None:
                        break
            if raw is None and not args.allow_env:
                fail(f"dlt {role} section {section}.{forced_dlt_name} was not found")
            dlt_name, raw_credentials = forced_dlt_name, raw if raw is not None else {}
        else:
            dlt_name, raw_credentials = discover(secrets, config, role)
        connection_type, connection, report, found = build_connection(
            role,
            dlt_name,
            raw_credentials,
            bruin_name,
            args.allow_env,
            args.placeholders,
            forced_type,
        )
        entries.append((connection_type, connection))
        reports.append(report)
        secrets_seen |= found

    if not entries:
        fail("nothing to convert: pass --source-connection and/or --destination-connection")

    blocking = [
        f"{report['bruin_connection_name']}: {', '.join(report['fields_missing_required'])}"
        for report in reports
        if report["fields_missing_required"]
    ]
    report_document = {
        "converter": "convert_dlt_connections.py",
        "dlt_project_dir": str(project),
        "bruin_config_file": str(output),
        "environment": args.environment,
        "connections": reports,
        "required_fields_missing": blocking,
        "note": (
            "This report is non-secret by construction. No credential value is read "
            "back, printed, or stored here."
        ),
    }
    assert_no_secrets(reports, secrets_seen)
    rendered = yaml.safe_dump(report_document, sort_keys=False)

    merge_into_config(output, args.environment, entries, args.replace)
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    print(f"Wrote {len(entries)} Bruin connection(s) to {output} (mode 600).")
    if blocking:
        print(
            "Required fields are missing. Fill them in by hand, then test both "
            "connections before continuing.",
            file=sys.stderr,
        )


def parser() -> argparse.ArgumentParser:
    parsed = argparse.ArgumentParser(description=__doc__)
    parsed.add_argument("--dlt-project-dir", required=True)
    parsed.add_argument("--output", required=True, help="path to a Git-ignored .bruin.yml")
    parsed.add_argument("--environment", default="default")
    parsed.add_argument("--source-connection", default=None)
    parsed.add_argument("--destination-connection", default=None)
    parsed.add_argument("--source-dlt-name", default=None)
    parsed.add_argument("--destination-dlt-name", default=None)
    parsed.add_argument("--source-bruin-type", default=None)
    parsed.add_argument("--destination-bruin-type", default=None)
    parsed.add_argument("--report", default=None, help="write the non-secret report here too")
    parsed.add_argument("--allow-env", action="store_true")
    parsed.add_argument("--placeholders", action="store_true")
    parsed.add_argument("--replace", action="store_true")
    parsed.set_defaults(handler=convert)
    return parsed


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
