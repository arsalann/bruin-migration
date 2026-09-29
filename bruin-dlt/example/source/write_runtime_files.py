#!/usr/bin/env python3
"""Write fixture-local, disposable runtime state for the dlt migration example.

Everything written here lives under the example's ignored `.artifacts/`
directory and uses throwaway container credentials:

  bruin.yml                     fixture-local Bruin configuration
  runtime.env                   shell variables shared by the fixture scripts
  dlt-project/.dlt/config.toml  copied from the tracked non-secret template
  dlt-project/.dlt/secrets.toml rendered with fixture credentials and ports
  dlt-project/dlt_pipeline.py   copied from the tracked source pipeline
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_DATABASE = "migration"
POSTGRES_USER = "migration"
POSTGRES_PASSWORD = "fixture-postgres-secret"
CLICKHOUSE_DATABASE = "migration"
CLICKHOUSE_USER = "migration"
CLICKHOUSE_PASSWORD = "fixture-clickhouse-secret"
DLT_DATASET = "dlt_analytics"
DLT_API_DATASET = "dlt_api"
BRUIN_DATABASE = "bruin_v0"
DLT_PIPELINES = ("dlt_pipeline.py", "dlt_api_pipeline.py")

SECRETS_TEMPLATE = """# Rendered fixture secrets. Throwaway container credentials only.
# A migration agent must not read this file; the connection converter does.

[sources.sql_database.credentials]
drivername = "postgresql"
database = "{postgres_database}"
username = "{postgres_username}"
password = "{postgres_password}"
host = "127.0.0.1"
port = {postgres_port}

[destination.clickhouse.credentials]
database = "{clickhouse_database}"
username = "{clickhouse_username}"
password = "{clickhouse_password}"
host = "127.0.0.1"
port = {clickhouse_native_port}
http_port = {clickhouse_http_port}
secure = 0
"""


def bruin_config(artifacts: Path) -> dict:
    """Return the fixture's harness-only Bruin configuration.

    The migrated source and destination connections are deliberately absent.
    `run.sh` adds them by running the connection converter against the fixture's
    dlt project, which is what the migration workflow does and which also
    exercises the converter's merge-into-an-existing-config path.
    """
    return {
        "default_environment": "default",
        "environments": {
            "default": {
                "connections": {
                    "duckdb": [
                        {
                            "name": "comparison_source",
                            "path": str(artifacts / "comparison-source.duckdb"),
                        },
                        {
                            "name": "comparison_dlt",
                            "path": str(artifacts / "comparison-dlt.duckdb"),
                        },
                        {
                            "name": "comparison_bruin",
                            "path": str(artifacts / "comparison-bruin.duckdb"),
                        },
                    ],
                }
            }
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--postgres-port", required=True, type=int)
    parser.add_argument("--clickhouse-native-port", required=True, type=int)
    parser.add_argument("--clickhouse-http-port", required=True, type=int)
    parser.add_argument("--compose-project", required=True)
    args = parser.parse_args()

    artifacts = Path(args.artifacts).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)

    config_path = artifacts / "bruin.yml"
    config_path.write_text(
        yaml.safe_dump(bruin_config(artifacts), sort_keys=False), encoding="utf-8"
    )
    config_path.chmod(0o600)

    dlt_project = artifacts / "dlt-project"
    dlt_config_dir = dlt_project / ".dlt"
    dlt_config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        EXAMPLE_ROOT / "fixtures" / "dlt" / "config.toml", dlt_config_dir / "config.toml"
    )
    for pipeline_file in DLT_PIPELINES:
        shutil.copyfile(EXAMPLE_ROOT / "source" / pipeline_file, dlt_project / pipeline_file)
    secrets_path = dlt_config_dir / "secrets.toml"
    secrets_path.write_text(
        SECRETS_TEMPLATE.format(
            postgres_database=POSTGRES_DATABASE,
            postgres_username=POSTGRES_USER,
            postgres_password=POSTGRES_PASSWORD,
            postgres_port=args.postgres_port,
            clickhouse_database=CLICKHOUSE_DATABASE,
            clickhouse_username=CLICKHOUSE_USER,
            clickhouse_password=CLICKHOUSE_PASSWORD,
            clickhouse_native_port=args.clickhouse_native_port,
            clickhouse_http_port=args.clickhouse_http_port,
        ),
        encoding="utf-8",
    )
    secrets_path.chmod(0o600)

    runtime = "\n".join(
        [
            f"COMPOSE_PROJECT_NAME={args.compose_project}",
            f"POSTGRES_PORT={args.postgres_port}",
            f"CLICKHOUSE_NATIVE_PORT={args.clickhouse_native_port}",
            f"CLICKHOUSE_HTTP_PORT={args.clickhouse_http_port}",
            "SOURCE_DATABASE_URL=postgresql://"
            f"{POSTGRES_USER}:{POSTGRES_PASSWORD}@127.0.0.1:{args.postgres_port}/{POSTGRES_DATABASE}",
            f"CLICKHOUSE_HTTP_URL=http://127.0.0.1:{args.clickhouse_http_port}",
            f"CLICKHOUSE_USER={CLICKHOUSE_USER}",
            f"CLICKHOUSE_PASSWORD={CLICKHOUSE_PASSWORD}",
            f"CLICKHOUSE_DATABASE={CLICKHOUSE_DATABASE}",
            f"DLT_DATASET={DLT_DATASET}",
            f"DLT_API_DATASET={DLT_API_DATASET}",
            f"BRUIN_DATABASE={BRUIN_DATABASE}",
            f"DLT_PROJECT_DIR={dlt_project}",
            # Keeps dlt's pipeline working directory and state inside this
            # example's .artifacts/ instead of the operator's ~/.dlt.
            f"DLT_DATA_DIR={artifacts / 'dlt-data'}",
            f"BRUIN_CONFIG_FILE={config_path}",
            f"COMPARISON_SOURCE_PATH={artifacts / 'comparison-source.duckdb'}",
            f"COMPARISON_DLT_PATH={artifacts / 'comparison-dlt.duckdb'}",
            f"COMPARISON_BRUIN_PATH={artifacts / 'comparison-bruin.duckdb'}",
            "",
        ]
    )
    (artifacts / "runtime.env").write_text(runtime, encoding="utf-8")
    (artifacts / "runtime.env").chmod(0o600)
    print(f"Wrote fixture runtime state: {artifacts}")


if __name__ == "__main__":
    main()
