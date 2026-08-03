from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = EXAMPLE_ROOT / ".artifacts"
SCRIPT = EXAMPLE_ROOT / "scripts" / "generate_bruin_draft.py"


class GenerateBruinDraftTests(unittest.TestCase):
    def test_generates_enabled_approved_fixture_asset(self) -> None:
        ARTIFACT_ROOT.mkdir(exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix="generator-test-", dir=ARTIFACT_ROOT))
        try:
            capture = temporary / "capture"
            capture.mkdir()
            (capture / "connection.json").write_text(
                json.dumps({"service": "postgres"}), encoding="utf-8"
            )
            (capture / "schemas.json").write_text(
                json.dumps(
                    {
                        "schemas": {
                            "public": {
                                "enabled": True,
                                "tables": {
                                    "customers": {
                                        "enabled": True,
                                        "sync_mode": "LIVE",
                                        "columns": {
                                            "id": {"data_type": "integer"},
                                            "updated_at": {"data_type": "timestamp"},
                                        },
                                    }
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            decisions = {
                "pipeline": {"name": "fixture", "start_date": "2025-01-01"},
                "connections": {
                    "source_connection": "source_postgres",
                    "destination_connection": "target_duckdb",
                    "destination": "duckdb",
                },
                "initial_run": {
                    "scope": "single_table",
                    "approved": True,
                    "isolated_destination_approved": True,
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-02",
                },
                "tables": {
                    "public.customers": {
                        "include": True,
                        "target_schema": "public",
                        "target_table": "customers",
                        "strategy": "merge",
                        "primary_key": ["id"],
                        "incremental_key": "updated_at",
                        "schema_contract": "evolve",
                        "delete_handling": "not_applicable",
                    }
                },
            }
            decisions_path = temporary / "decisions.yml"
            decisions_path.write_text(yaml.safe_dump(decisions), encoding="utf-8")
            output = temporary / "generated"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--capture-dir",
                    str(capture),
                    "--decisions",
                    str(decisions_path),
                    "--output-dir",
                    str(output),
                    "--strict",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            asset = yaml.safe_load(
                (output / "assets" / "public" / "customers.asset.yml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(asset["enabled"])
            self.assertEqual(asset["parameters"]["source_connection"], "source_postgres")
            self.assertEqual(asset["materialization"]["strategy"], "merge")
            report = yaml.safe_load((output / "conversion-report.yml").read_text())
            self.assertTrue(report["strict"])
            self.assertIn("configuration_mismatches", report)

            decisions["initial_run"]["approved"] = False
            incomplete_path = temporary / "incomplete-decisions.yml"
            incomplete_path.write_text(yaml.safe_dump(decisions), encoding="utf-8")
            incomplete_output = temporary / "incomplete-generated"
            incomplete = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--capture-dir",
                    str(capture),
                    "--decisions",
                    str(incomplete_path),
                    "--output-dir",
                    str(incomplete_output),
                    "--strict",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(incomplete.returncode, 2)
            self.assertIn("initial_run.approved must be true", incomplete.stderr)
            self.assertFalse(incomplete_output.exists())
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
