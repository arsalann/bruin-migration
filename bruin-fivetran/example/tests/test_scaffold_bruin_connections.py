from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = EXAMPLE_ROOT / "scripts" / "scaffold_bruin_connections.py"
SPEC = importlib.util.spec_from_file_location("scaffold_bruin_connections", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ScaffoldBruinConnectionsTests(unittest.TestCase):
    def test_uses_redacted_source_service_and_destination_type(self) -> None:
        template = MODULE.build_template(
            {"service": "postgres", "config": {"password": "never-store"}},
            "fixture_source",
            "fixture_target",
            "bigquery",
        )
        connections = template["environments"]["default"]["connections"]
        self.assertEqual(connections["postgres"][0]["name"], "fixture_source")
        self.assertEqual(
            connections["postgres"][0]["password"], "${SOURCE_POSTGRES_PASSWORD}"
        )
        self.assertEqual(
            connections["google_cloud_platform"][0]["name"], "fixture_target"
        )

    def test_rejects_output_outside_artifact_root(self) -> None:
        with self.assertRaises(MODULE.ScaffoldError):
            MODULE.require_artifact_path(Path("/tmp/not-an-artifact"))


if __name__ == "__main__":
    unittest.main()
