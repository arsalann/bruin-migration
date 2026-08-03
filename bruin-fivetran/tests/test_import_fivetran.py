from __future__ import annotations

import contextlib
import base64
import importlib.util
import io
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml


TESTS_DIR = Path(__file__).resolve().parent
MIGRATOR_DIR = TESTS_DIR.parent
SCRIPT = MIGRATOR_DIR / "scripts" / "import_fivetran.py"
SPEC = importlib.util.spec_from_file_location("bruin_fivetran_importer", SCRIPT)
assert SPEC and SPEC.loader
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)

SCAFFOLDER_SCRIPT = MIGRATOR_DIR / "scripts" / "initialize_bruin_project.py"
SCAFFOLDER_SPEC = importlib.util.spec_from_file_location("bruin_fivetran_scaffolder", SCAFFOLDER_SCRIPT)
assert SCAFFOLDER_SPEC and SCAFFOLDER_SPEC.loader
SCAFFOLDER = importlib.util.module_from_spec(SCAFFOLDER_SPEC)
SCAFFOLDER_SPEC.loader.exec_module(SCAFFOLDER)


class ImportFivetranTests(unittest.TestCase):
    def write_runtime_files(self, root: Path, decisions: dict | None = None) -> tuple[Path, Path, Path, Path]:
        artifacts = root / ".artifacts"
        artifacts.mkdir()
        config = artifacts / "bruin.yml"
        config.write_text(
            """environments:
  default:
    connections:
      postgres:
        - name: source_postgres
          host: example.invalid
        - name: target_postgres
          host: example.invalid
""",
            encoding="utf-8",
        )
        mapping = root / "connection-map.yml"
        mapping.write_text(
            """bruin_config: .artifacts/bruin.yml
environment: default
sources:
  connection-postgres-orders: source_postgres
destinations:
  group-postgres-fixture: target_postgres
tables:
  connection-postgres-orders:
    public.orders:
      target_schema: migration_v0
      target_table: fct_orders
""",
            encoding="utf-8",
        )
        snapshot = TESTS_DIR / "source" / "fivetran-snapshot.json"
        decision_file = root / "decisions.yml"
        if decisions is None:
            decision_file.write_text(
                (TESTS_DIR / "source" / "migration-decisions.yml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            decision_file.write_text(yaml.safe_dump(decisions, sort_keys=False), encoding="utf-8")
        return snapshot, mapping, decision_file, artifacts / "generated"

    def convert(self, snapshot: Path, mapping: Path, decisions: Path, output: Path, strict: bool = True) -> int:
        args = [
            "convert",
            "--snapshot",
            str(snapshot),
            "--connections",
            str(mapping),
            "--decisions",
            str(decisions),
            "--output-root",
            str(output),
        ]
        if strict:
            args.append("--strict")
        return IMPORTER.main(args)

    def test_strict_conversion_emits_reviewed_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, mapping, decisions, output = self.write_runtime_files(Path(directory))
            self.assertEqual(self.convert(snapshot, mapping, decisions, output), 0)
            asset = yaml.safe_load(
                (output / "connection-postgres-orders/assets/migration_v0/fct_orders.asset.yml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(asset["enabled"])
            self.assertEqual(asset["name"], "migration_v0.fct_orders")
            self.assertEqual(asset["parameters"]["sql_exclude_columns"], "legacy_note")
            self.assertEqual(
                [column["name"] for column in asset["columns"]],
                ["customer_email", "order_id", "total_cents", "updated_at"],
            )
            self.assertNotIn("_fivetran_synced", json.dumps(asset))
            report = yaml.safe_load((output / "conversion-report.yml").read_text(encoding="utf-8"))
            self.assertEqual(report["issues"], [])

    def test_missing_approval_is_disabled_and_strict_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, mapping, decisions, output = self.write_runtime_files(Path(directory), {"connections": {}})
            self.assertEqual(self.convert(snapshot, mapping, decisions, output), 1)
            asset = yaml.safe_load(
                (output / "connection-postgres-orders/assets/migration_v0/fct_orders.asset.yml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(asset["enabled"])
            report = yaml.safe_load((output / "conversion-report.yml").read_text(encoding="utf-8"))
            self.assertTrue(report["issues"])

    def test_output_must_be_inside_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, mapping, decisions, _ = self.write_runtime_files(root)
            outside = root / "generated"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.convert(snapshot, mapping, decisions, outside), 2)
            self.assertFalse(outside.exists())

    def test_conversion_refuses_to_replace_artifacts_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, mapping, decisions, output = self.write_runtime_files(root)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.convert(snapshot, mapping, decisions, output.parent), 2)
            self.assertTrue((output.parent / "bruin.yml").exists())

    def test_normalization_drops_credential_values(self) -> None:
        normalized = IMPORTER.normalize_connection(
            {
                "id": "connection",
                "group_id": "group",
                "service": "postgres",
                "config": {"host": "db.example.test", "password": "never-persist-me"},
            }
        )
        rendered = json.dumps(normalized)
        self.assertNotIn("never-persist-me", rendered)
        self.assertNotIn("password", rendered.lower())
        self.assertIn("host", normalized["source_config_field_names"])

    def test_normalization_retains_safe_replication_settings(self) -> None:
        normalized = IMPORTER.normalize_connection(
            {
                "id": "connection",
                "service": "postgres",
                "config": {
                    "update_method": "xmin",
                    "capture_deletes": True,
                    "password": "must-not-be-kept",
                },
            }
        )
        self.assertEqual(
            normalized["replication"],
            {"update_method": "xmin", "delete_capture_enabled": True},
        )
        self.assertNotIn("capture_deletes", normalized.get("unknown_safety_fields", []))
        self.assertNotIn("must-not-be-kept", json.dumps(normalized))

    def test_raw_snapshot_configuration_is_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, mapping, decisions, output = self.write_runtime_files(root)
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            payload["connections"][0]["config"] = {
                "host": "internal.example.test",
                "password": "must-not-reach-generated-output",
            }
            raw_snapshot = root / "raw-snapshot.json"
            raw_snapshot.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(self.convert(raw_snapshot, mapping, decisions, output), 1)
            generated = "\n".join(
                file.read_text(encoding="utf-8") for file in output.rglob("*") if file.is_file()
            )
            self.assertNotIn("must-not-reach-generated-output", generated)
            self.assertNotIn("internal.example.test", generated)

    def test_paginated_fivetran_list_collects_each_page(self) -> None:
        client = IMPORTER.FivetranClient("Basic ignored", 1.0, 0, "https://api.example.test/v1")
        pages = [
            {"data": {"items": [{"id": "first"}], "next_cursor": "next-page"}},
            {"data": {"items": [{"id": "second"}]}},
        ]
        seen_params: list[dict[str, str]] = []

        def fake_get(endpoint: str, params: dict[str, str] | None = None) -> dict:
            self.assertEqual(endpoint, "connections")
            seen_params.append(dict(params or {}))
            return pages.pop(0)

        client.get = fake_get  # type: ignore[method-assign]
        self.assertEqual([item["id"] for item in client.list("connections")], ["first", "second"])
        self.assertEqual(seen_params[0]["limit"], "1000")
        self.assertEqual(seen_params[1]["cursor"], "next-page")

    def test_environment_credentials_are_encoded_without_persisting_them(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TEST_FIVETRAN_KEY": "key", "TEST_FIVETRAN_SECRET": "secret"},
            clear=False,
        ):
            authorization = IMPORTER.basic_auth_from_environment_names(
                "TEST_FIVETRAN_KEY", "TEST_FIVETRAN_SECRET"
            )
        expected = "Basic " + base64.b64encode(b"key:secret").decode("ascii")
        self.assertEqual(authorization, expected)

    def test_config_credentials_do_not_expand_unrelated_generic_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".bruin.yml"
            config.write_text(
                """default_environment: default
environments:
  default:
    connections:
      generic:
        - name: fivetran_api_key
          value: ${TEST_FIVETRAN_KEY}
        - name: fivetran_api_secret
          value: ${TEST_FIVETRAN_SECRET}
        - name: unrelated_secret
          value: ${UNSET_UNRELATED_SECRET}
""",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"TEST_FIVETRAN_KEY": "key", "TEST_FIVETRAN_SECRET": "secret"},
                clear=False,
            ):
                authorization = IMPORTER.basic_auth_from_config(config, "default")
        expected = "Basic " + base64.b64encode(b"key:secret").decode("ascii")
        self.assertEqual(authorization, expected)

    def test_base64_encoded_credential_alias_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".bruin.yml"
            config.write_text(
                """default_environment: default
environments:
  default:
    connections:
      generic:
        - name: fivetran_api_key_base64_encoded
          value: a2V5OnNlY3JldA==
""",
                encoding="utf-8",
            )
            self.assertEqual(
                IMPORTER.basic_auth_from_config(config, "default"),
                "Basic a2V5OnNlY3JldA==",
            )

    def test_scaffolder_creates_placeholder_connections_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bruin_dir = Path(directory) / "bruin"
            result = SCAFFOLDER.main(
                [
                    "--snapshot",
                    str(TESTS_DIR / "source" / "fivetran-snapshot.json"),
                    "--bruin-dir",
                    str(bruin_dir),
                    "--pipeline-name",
                    "fixture-migration",
                ]
            )
            self.assertEqual(result, 0)
            config_text = (bruin_dir / ".bruin.yml").read_text(encoding="utf-8")
            config = yaml.safe_load(config_text)
            self.assertEqual(config["environments"]["default"]["connections"]["postgres"][0]["name"], "fivetran_source")
            self.assertEqual(config["environments"]["default"]["connections"]["postgres"][1]["name"], "bruin_destination")
            self.assertIn("${SOURCE_POSTGRES_HOST}", config_text)
            self.assertIn("${DESTINATION_POSTGRES_HOST}", config_text)
            self.assertNotIn("migration", config_text)
            pipeline = yaml.safe_load((bruin_dir / "pipeline.yml").read_text(encoding="utf-8"))
            self.assertEqual(pipeline, {"name": "fixture-migration", "catchup": False})

    def test_scaffolder_uses_current_bruin_connection_field_names(self) -> None:
        self.assertEqual(SCAFFOLDER.SOURCE_TYPES["mongodb"], "mongo_atlas")
        bigquery = SCAFFOLDER.fields_for("google_cloud_platform", "DESTINATION")
        self.assertIn("location", bigquery)
        databricks = SCAFFOLDER.fields_for("databricks", "DESTINATION")
        self.assertIn("path", databricks)
        self.assertNotIn("http_path", databricks)
        snowflake = SCAFFOLDER.fields_for("snowflake", "DESTINATION")
        self.assertIn("region", snowflake)


if __name__ == "__main__":
    unittest.main()
