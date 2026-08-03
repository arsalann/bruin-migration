#!/usr/bin/env python3
"""Write fixture-local, disposable Bruin configuration and shell environment."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--postgres-port", required=True, type=int)
    parser.add_argument("--mock-port", required=True, type=int)
    parser.add_argument("--compose-project", required=True)
    args = parser.parse_args()

    artifacts = Path(args.artifacts).resolve()
    config = {
        "default_environment": "default",
        "environments": {
            "default": {
                "connections": {
                    "postgres": [
                        {
                            "name": "source_postgres",
                            "host": "127.0.0.1",
                            "port": args.postgres_port,
                            "database": "migration",
                            "username": "migration",
                            "password": "migration",
                            "ssl_mode": "disable",
                        }
                    ],
                    "duckdb": [
                        {
                            "name": "source_comparison_duckdb",
                            "path": str(artifacts / "source-comparison.duckdb"),
                        },
                        {
                            "name": "target_duckdb",
                            "path": str(artifacts / "target.duckdb"),
                        }
                    ],
                    "generic": [
                        {"name": "fivetran_api_key", "value": "fixture-key"},
                        {"name": "fivetran_api_secret", "value": "fixture-secret"},
                    ],
                }
            }
        },
    }
    (artifacts / "bruin.yml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    runtime = "\n".join(
        [
            f"COMPOSE_PROJECT_NAME={args.compose_project}",
            f"POSTGRES_PORT={args.postgres_port}",
            f"MOCK_FIVETRAN_PORT={args.mock_port}",
            f"MOCK_FIVETRAN_PID={Path(artifacts / 'mock-fivetran.pid').read_text(encoding='utf-8').strip()}",
            f"SOURCE_DATABASE_URL=postgresql://migration:migration@127.0.0.1:{args.postgres_port}/migration",
            f"BRUIN_DESTINATION_PATH={artifacts / 'target.duckdb'}",
            f"SOURCE_COMPARISON_PATH={artifacts / 'source-comparison.duckdb'}",
            "",
        ]
    )
    (artifacts / "runtime.env").write_text(runtime, encoding="utf-8")


if __name__ == "__main__":
    main()
