#!/usr/bin/env python3
"""Fail when the hand-authored target reference drifts from the reviewed decisions.

The runtime workflow gets its strategy, key, and incremental-key answers from a
human. The fixture records those answers in `fixtures/migration-decisions.yml`,
so this check is what keeps the checked-in reference honest: an asset cannot
quietly change its write strategy or keys without the decision file changing too.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

BRUIN_BLOCK = re.compile(r'"""\s*@bruin\s*(?P<body>.*?)@bruin\s*"""', re.DOTALL)
STRATEGY_TO_DLT_DISPOSITION = {
    "create+replace": {"replace"},
    "truncate+insert": {"replace"},
    "append": {"append"},
    "merge": {"merge"},
    "delete+insert": {"merge"},
}


def load(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def load_python_asset(path: Path):
    """Parse the `@bruin` YAML block out of a Bruin Python asset."""
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")
    match = BRUIN_BLOCK.search(body)
    if match is None:
        raise SystemExit(f"{path} has no @bruin configuration block")
    try:
        return yaml.safe_load(match.group("body"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"cannot parse the @bruin block in {path}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--assets-dir", required=True)
    args = parser.parse_args()

    decisions = load(Path(args.decisions))
    pipeline = load(Path(args.pipeline))
    failures: list[str] = []

    expected_pipeline = decisions["pipeline"]
    for field in ("name", "catchup"):
        if pipeline.get(field) != expected_pipeline[field]:
            failures.append(
                f"pipeline.{field}: expected {expected_pipeline[field]!r}, "
                f"found {pipeline.get(field)!r}"
            )
    if str(pipeline.get("start_date")) != str(expected_pipeline["start_date"]):
        failures.append(
            f"pipeline.start_date: expected {expected_pipeline['start_date']!r}, "
            f"found {pipeline.get('start_date')!r}"
        )
    default_connections = pipeline.get("default_connections") or {}
    destination = decisions["connections"]["destination"]
    if default_connections.get(destination) != decisions["connections"]["destination_connection"]:
        failures.append(
            f"pipeline.default_connections.{destination}: expected "
            f"{decisions['connections']['destination_connection']!r}, "
            f"found {default_connections.get(destination)!r}"
        )

    assets = {}
    for path in sorted(Path(args.assets_dir).glob("*.asset.yml")):
        asset = load(path)
        assets[asset["name"]] = (path, asset)
    for path in sorted(Path(args.assets_dir).glob("*.py")):
        asset = load_python_asset(path)
        assets[asset["name"]] = (path, asset)

    for resource, expected in decisions["resources"].items():
        if not expected.get("include", True):
            continue
        target = expected["target_table"]
        if target not in assets:
            failures.append(f"{resource}: no asset named {target}")
            continue
        path, asset = assets[target]
        label = f"{path.name} ({resource})"
        parameters = asset.get("parameters") or {}
        materialization = asset.get("materialization") or {}

        asset_type = expected.get("asset_type", "ingestr")
        if asset_type == "python":
            # A ported dlt resource. There is no ingestr source connection; the
            # asset's own Python owns extraction, so only the destination and the
            # write semantics are checked against the decision.
            if asset.get("type") != "python":
                failures.append(f"{label}: type must be python, found {asset.get('type')!r}")
            if asset.get("connection") != decisions["connections"]["destination_connection"]:
                failures.append(
                    f"{label}: connection expected "
                    f"{decisions['connections']['destination_connection']!r}, "
                    f"found {asset.get('connection')!r}"
                )
            if expected.get("ingestr_connector_available"):
                failures.append(
                    f"{label}: an ingestr connector is recorded as available, so this "
                    "resource must not be ported to a Python asset"
                )
            if not expected.get("port_reason"):
                failures.append(f"{label}: a Python asset requires a recorded port_reason")
        else:
            if asset.get("type") != "ingestr":
                failures.append(f"{label}: type must be ingestr, found {asset.get('type')!r}")
            if parameters.get("source_table") != expected["source_table"]:
                failures.append(
                    f"{label}: source_table expected {expected['source_table']!r}, "
                    f"found {parameters.get('source_table')!r}"
                )
            if (
                parameters.get("source_connection")
                != decisions["connections"]["source_connection"]
            ):
                failures.append(
                    f"{label}: source_connection expected "
                    f"{decisions['connections']['source_connection']!r}, "
                    f"found {parameters.get('source_connection')!r}"
                )
            if parameters.get("destination") != decisions["connections"]["destination"]:
                failures.append(
                    f"{label}: destination expected {decisions['connections']['destination']!r}, "
                    f"found {parameters.get('destination')!r}"
                )
            if parameters.get("schema_contract") != expected["schema_contract"]:
                failures.append(
                    f"{label}: schema_contract expected {expected['schema_contract']!r}, "
                    f"found {parameters.get('schema_contract')!r}"
                )
        strategy = materialization.get("strategy")
        if strategy != expected["strategy"]:
            failures.append(
                f"{label}: strategy expected {expected['strategy']!r}, found {strategy!r}"
            )
        allowed = STRATEGY_TO_DLT_DISPOSITION.get(expected["strategy"], set())
        if expected["dlt_write_disposition"] not in allowed:
            failures.append(
                f"{label}: strategy {expected['strategy']!r} is not a reviewed mapping for "
                f"dlt write_disposition {expected['dlt_write_disposition']!r}"
            )
        if materialization.get("incremental_key") != expected["incremental_key"]:
            failures.append(
                f"{label}: incremental_key expected {expected['incremental_key']!r}, "
                f"found {materialization.get('incremental_key')!r}"
            )
        if expected["incremental_key"] != expected["dlt_incremental_cursor"]:
            failures.append(
                f"{label}: incremental_key {expected['incremental_key']!r} does not match the "
                f"dlt cursor {expected['dlt_incremental_cursor']!r}"
            )
        keys = [
            column["name"]
            for column in asset.get("columns") or []
            if column.get("primary_key")
        ]
        if keys != expected["primary_key"]:
            failures.append(
                f"{label}: primary keys expected {expected['primary_key']!r}, found {keys!r}"
            )
        if expected["strategy"] == "merge" and not keys:
            failures.append(f"{label}: an ingestr merge requires at least one primary key")

    declared = {
        expected["target_table"]
        for expected in decisions["resources"].values()
        if expected.get("include", True)
    }
    for name in sorted(set(assets) - declared):
        failures.append(f"{name}: asset is not covered by a reviewed decision")

    if failures:
        print("target reference does not match the reviewed decisions:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"target reference matches the reviewed decisions for {len(declared)} asset(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
