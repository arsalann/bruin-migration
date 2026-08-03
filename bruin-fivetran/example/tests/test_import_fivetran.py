from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MIGRATION_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = MIGRATION_ROOT / ".agents" / "skills" / "bruin-fivetran-migrator" / "import_fivetran.py"
SPEC = importlib.util.spec_from_file_location("import_fivetran", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ImportFivetranTests(unittest.TestCase):
    def test_redacts_config_values_and_secret_fields(self) -> None:
        value = {
            "id": "fixture",
            "config": {"host": "example", "password": "never-store"},
            "authorization": "never-store",
            "nested": {"token": "never-store", "safe": "ok"},
        }
        redacted = MODULE.redact(value)
        self.assertEqual(
            redacted["config"],
            {"redacted": True, "field_names": ["host", "password"]},
        )
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["safe"], "ok")

    def test_name_matching_can_use_connection_schema(self) -> None:
        connection = MODULE.select_connection(
            [{"id": "one", "schema": "bruin_fivetran"}],
            "bruin_fivetran",
            None,
        )
        self.assertEqual(connection["id"], "one")

    def test_connection_config_keeps_only_field_names(self) -> None:
        normalized = MODULE.redact(
            {
                "id": "fixture",
                "config": {
                    "host": "do-not-store",
                    "password": "do-not-store",
                },
            }
        )
        self.assertEqual(
            normalized["config"],
            {"redacted": True, "field_names": ["host", "password"]},
        )

    def test_rejects_output_outside_artifact_root(self) -> None:
        with self.assertRaises(MODULE.ImportError):
            MODULE.require_artifact_path(Path("/tmp/not-an-artifact"))


if __name__ == "__main__":
    unittest.main()
