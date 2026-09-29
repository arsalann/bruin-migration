#!/usr/bin/env python3
"""Unit tests for the fixture's comparison helpers and gate scripts.

These cover the parts of the parity gate that do not need a live database: the
engine-neutral value canonicalization, the profile assertion, and the
reviewed-decision check. Each gate is tested in both directions, because a gate
that cannot fail is not a gate.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = EXAMPLE_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fixture_tables import TABLES, canonical, canonical_row  # noqa: E402


def profile_json(row_count: int, null_keys: int = 0, duplicate_keys: int = 0) -> str:
    return json.dumps(
        [
            {
                "row_count": row_count,
                "null_primary_keys": null_keys,
                "duplicate_primary_keys": duplicate_keys,
            }
        ]
    )


class CanonicalizationTestCase(unittest.TestCase):
    def test_timestamps_are_rendered_identically_across_engines(self) -> None:
        naive = dt.datetime(2025, 4, 1, 6, 0, 0)
        aware = dt.datetime(2025, 4, 1, 6, 0, 0, tzinfo=dt.timezone.utc)
        micro = dt.datetime(2025, 4, 1, 6, 0, 0, 123456)
        self.assertEqual(canonical(naive), "2025-04-01 06:00:00.000000")
        self.assertEqual(canonical(aware), canonical(naive))
        self.assertEqual(canonical(micro), "2025-04-01 06:00:00.123456")

    def test_dates_numbers_and_nulls(self) -> None:
        self.assertEqual(canonical(dt.date(2024, 1, 31)), "2024-01-31")
        self.assertEqual(canonical(None), "\\N")
        self.assertEqual(canonical(True), "1")
        self.assertEqual(canonical(Decimal("10.50")), "10.5")
        self.assertEqual(canonical(Decimal("10.5000")), canonical(Decimal("10.5")))
        self.assertEqual(canonical(1050), "1050")

    def test_canonical_row_covers_every_declared_column(self) -> None:
        row = (1, 2, "created", dt.datetime(2025, 1, 1))
        self.assertEqual(len(canonical_row(row)), len(TABLES["order_events"]["columns"]))


class AssertProfilesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def write(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return f"{name}={path}"

    def run_gate(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "assert_profiles.py"), *arguments],
            capture_output=True,
            text=True,
        )

    def test_matching_profiles_pass(self) -> None:
        result = self.run_gate(
            self.write("source.json", profile_json(1000)),
            self.write("dlt.json", profile_json(1000)),
            self.write("bruin.json", profile_json(1000)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_row_count_mismatch_fails(self) -> None:
        result = self.run_gate(
            self.write("source.json", profile_json(1000)),
            self.write("bruin.json", profile_json(999)),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("differs from", result.stderr)

    def test_duplicate_and_null_keys_fail(self) -> None:
        duplicates = self.run_gate(
            self.write("source.json", profile_json(1000)),
            self.write("bruin.json", profile_json(1000, duplicate_keys=1)),
        )
        self.assertEqual(duplicates.returncode, 1)
        self.assertIn("duplicate keys=1", duplicates.stderr)
        nulls = self.run_gate(
            self.write("source2.json", profile_json(1000, null_keys=2)),
            self.write("bruin2.json", profile_json(1000)),
        )
        self.assertEqual(nulls.returncode, 1)
        self.assertIn("null keys=2", nulls.stderr)

    def test_unparseable_profile_fails(self) -> None:
        result = self.run_gate(self.write("broken.json", "{not json"))
        self.assertEqual(result.returncode, 2)


class DecisionCheckTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.decisions = yaml.safe_load(
            (EXAMPLE_ROOT / "fixtures" / "migration-decisions.yml").read_text(encoding="utf-8")
        )

    def run_check(self, decisions: dict) -> subprocess.CompletedProcess[str]:
        path = self.root / "decisions.yml"
        path.write_text(yaml.safe_dump(decisions, sort_keys=False), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "assert_target_matches_decisions.py"),
                "--decisions",
                str(path),
                "--pipeline",
                str(EXAMPLE_ROOT / "target" / "pipeline.yml"),
                "--assets-dir",
                str(EXAMPLE_ROOT / "target" / "assets"),
            ],
            capture_output=True,
            text=True,
        )

    def test_checked_in_reference_matches(self) -> None:
        result = self.run_check(self.decisions)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_strategy_is_caught(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["orders"]["strategy"] = "append"
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("strategy expected 'append'", result.stderr)

    def test_changed_incremental_key_is_caught(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["orders"]["incremental_key"] = "created_at"
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("incremental_key", result.stderr)

    def test_changed_primary_key_is_caught(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["customers"]["primary_key"] = ["email"]
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("primary keys expected", result.stderr)

    def test_unreviewed_strategy_mapping_is_rejected(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["order_events"]["dlt_write_disposition"] = "merge"
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a reviewed mapping", result.stderr)

    def test_python_asset_must_record_why_it_was_ported(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["pokemon"].pop("port_reason")
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires a recorded port_reason", result.stderr)

    def test_python_asset_is_rejected_when_an_ingestr_connector_exists(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["pokemon"]["ingestr_connector_available"] = True
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("must not be ported to a Python asset", result.stderr)

    def test_python_asset_declared_as_ingestr_is_caught(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["pokemon"]["asset_type"] = "ingestr"
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("type must be ingestr", result.stderr)

    def test_missing_asset_is_caught(self) -> None:
        decisions = copy.deepcopy(self.decisions)
        decisions["resources"]["invoices"] = dict(
            decisions["resources"]["orders"], target_table="bruin_v0.invoices"
        )
        result = self.run_check(decisions)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no asset named bruin_v0.invoices", result.stderr)


if __name__ == "__main__":
    unittest.main()
