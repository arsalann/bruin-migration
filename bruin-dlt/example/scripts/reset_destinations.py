#!/usr/bin/env python3
"""Reset only this fixture's destination state so `run.sh` is repeatable.

Drops the dlt dataset tables, the Bruin v0 database, ingestr's staging database,
and dlt's pipeline working directory. Every target is derived from the fixture's
own runtime environment, and the dlt working directory must live under the
example's `.artifacts/` — the operator's `~/.dlt` is never touched.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_tables import clickhouse_client  # noqa: E402

BRUIN_STAGING_DATABASE = "_bruin_staging"


def main() -> int:
    clickhouse_database = os.environ["CLICKHOUSE_DATABASE"]
    datasets = [os.environ["DLT_DATASET"], os.environ["DLT_API_DATASET"]]
    bruin_database = os.environ["BRUIN_DATABASE"]
    example_artifacts = Path(__file__).resolve().parents[1] / ".artifacts"
    dlt_data_dir = Path(os.environ["DLT_DATA_DIR"]).resolve()
    if example_artifacts.resolve() not in dlt_data_dir.parents:
        print(
            f"refusing to remove a dlt data directory outside {example_artifacts}: "
            f"{dlt_data_dir}",
            file=sys.stderr,
        )
        return 2

    client = clickhouse_client()
    try:
        tables = []
        for dataset in datasets:
            tables.extend(
                client.query(
                    "SELECT name FROM system.tables WHERE database = {db:String} "
                    "AND (name LIKE {prefix:String} OR name LIKE {staging_prefix:String})",
                    parameters={
                        "db": clickhouse_database,
                        "prefix": f"{dataset}%",
                        "staging_prefix": f"{dataset}_staging%",
                    },
                ).result_rows
            )
        for (name,) in tables:
            client.command(f"DROP TABLE IF EXISTS `{clickhouse_database}`.`{name}`")
        for database in (bruin_database, BRUIN_STAGING_DATABASE):
            client.command(f"DROP DATABASE IF EXISTS `{database}`")
        print(
            f"dropped {len(tables)} dlt table(s) in {clickhouse_database} and "
            f"databases {bruin_database}, {BRUIN_STAGING_DATABASE}"
        )
    finally:
        client.close()

    if dlt_data_dir.exists():
        shutil.rmtree(dlt_data_dir)
        print(f"removed dlt pipeline state: {dlt_data_dir}")

    for name in ("COMPARISON_SOURCE_PATH", "COMPARISON_DLT_PATH", "COMPARISON_BRUIN_PATH"):
        path = Path(os.environ[name])
        for candidate in (path, path.with_suffix(path.suffix + ".wal")):
            if candidate.exists():
                candidate.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
