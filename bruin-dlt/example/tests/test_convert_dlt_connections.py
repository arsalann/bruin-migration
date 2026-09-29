#!/usr/bin/env python3
"""Unit tests for the dlt-to-Bruin connection converter."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
CONVERTER_PATH = (
    EXAMPLE_ROOT.parent / ".agents" / "skills" / "bruin-dlt-migrator" / "convert_dlt_connections.py"
)

SPEC = importlib.util.spec_from_file_location("convert_dlt_connections", CONVERTER_PATH)
assert SPEC and SPEC.loader
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)

TABLE_SECRETS = """
[sources.sql_database.credentials]
drivername = "postgresql"
database = "shop"
username = "reader"
password = "unit-test-postgres-secret"
host = "db.internal"
port = 5432

[destination.clickhouse.credentials]
database = "warehouse"
username = "writer"
password = "unit-test-clickhouse-secret"
host = "ch.internal"
port = 9000
http_port = 8123
secure = 1
"""

URL_SECRETS = """
[sources.sql_database]
credentials = "postgresql://reader:unit%2Dtest%2Dsecret@db.internal:6543/shop?sslmode=require"

[destination.duckdb.credentials]
database = "/tmp/warehouse.duckdb"
"""


class ConverterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "dlt-project"
        (self.project / ".dlt").mkdir(parents=True)
        self.output = self.root / ".bruin.yml"
        self.addCleanup(self.temporary.cleanup)

    def write_secrets(self, body: str) -> None:
        (self.project / ".dlt" / "secrets.toml").write_text(body, encoding="utf-8")

    def write_config(self, body: str) -> None:
        (self.project / ".dlt" / "config.toml").write_text(body, encoding="utf-8")

    def run_converter(self, *extra: str) -> int:
        arguments = [
            "--dlt-project-dir",
            str(self.project),
            "--output",
            str(self.output),
            "--source-connection",
            "dlt_source",
            "--destination-connection",
            "dlt_destination",
            *extra,
        ]
        namespace = converter.parser().parse_args(arguments)
        try:
            namespace.handler(namespace)
        except converter.ConversionError as exc:
            self.last_error = str(exc)
            return 2
        return 0

    def connections(self) -> dict[str, list[dict[str, object]]]:
        document = yaml.safe_load(self.output.read_text(encoding="utf-8"))
        return document["environments"]["default"]["connections"]

    def test_toml_tables_map_to_bruin_connections(self) -> None:
        self.write_secrets(TABLE_SECRETS)
        self.assertEqual(self.run_converter(), 0)
        connections = self.connections()
        self.assertEqual(
            connections["postgres"][0],
            {
                "name": "dlt_source",
                "host": "db.internal",
                "port": 5432,
                "database": "shop",
                "username": "reader",
                "password": "unit-test-postgres-secret",
            },
        )
        self.assertEqual(
            connections["clickhouse"][0],
            {
                "name": "dlt_destination",
                "host": "ch.internal",
                "port": 9000,
                "http_port": 8123,
                "database": "warehouse",
                "username": "writer",
                "password": "unit-test-clickhouse-secret",
                "secure": 1,
            },
        )

    def test_output_is_not_world_readable(self) -> None:
        self.write_secrets(TABLE_SECRETS)
        self.assertEqual(self.run_converter(), 0)
        self.assertEqual(os.stat(self.output).st_mode & 0o777, 0o600)

    def test_report_never_contains_a_credential(self) -> None:
        self.write_secrets(TABLE_SECRETS)
        report = self.root / "report.yml"
        self.assertEqual(self.run_converter("--report", str(report)), 0)
        body = report.read_text(encoding="utf-8")
        self.assertNotIn("unit-test-postgres-secret", body)
        self.assertNotIn("unit-test-clickhouse-secret", body)
        self.assertIn("password", body)
        self.assertIn("bruin_connection_type: postgres", body)

    def test_connection_string_credentials_are_parsed(self) -> None:
        self.write_secrets(URL_SECRETS)
        self.assertEqual(self.run_converter(), 0)
        connections = self.connections()
        source = connections["postgres"][0]
        self.assertEqual(source["host"], "db.internal")
        self.assertEqual(source["port"], 6543)
        self.assertEqual(source["database"], "shop")
        self.assertEqual(source["password"], "unit-test-secret")
        self.assertEqual(source["ssl_mode"], "require")
        self.assertEqual(connections["duckdb"][0]["path"], "/tmp/warehouse.duckdb")

    def test_placeholders_never_write_a_value(self) -> None:
        self.write_secrets(TABLE_SECRETS)
        self.assertEqual(self.run_converter("--placeholders"), 0)
        body = self.output.read_text(encoding="utf-8")
        self.assertNotIn("unit-test-postgres-secret", body)
        self.assertIn("${SOURCE_POSTGRES_PASSWORD}", body)
        self.assertIn("${DESTINATION_CLICKHOUSE_PASSWORD}", body)

    def test_environment_variables_fill_missing_fields(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'database = "shop"\n'
            'host = "db.internal"\n'
            "port = 5432\n"
            "\n"
            "[destination.duckdb.credentials]\n"
            'database = "/tmp/warehouse.duckdb"\n'
        )
        os.environ["SOURCES__SQL_DATABASE__CREDENTIALS__USERNAME"] = "env-reader"
        os.environ["SOURCES__SQL_DATABASE__CREDENTIALS__PASSWORD"] = "env-secret-value"
        self.addCleanup(os.environ.pop, "SOURCES__SQL_DATABASE__CREDENTIALS__USERNAME", None)
        self.addCleanup(os.environ.pop, "SOURCES__SQL_DATABASE__CREDENTIALS__PASSWORD", None)
        report = self.root / "report.yml"
        self.assertEqual(self.run_converter("--allow-env", "--report", str(report)), 0)
        source = self.connections()["postgres"][0]
        self.assertEqual(source["username"], "env-reader")
        self.assertEqual(source["password"], "env-secret-value")
        body = yaml.safe_load(report.read_text(encoding="utf-8"))
        source_report = next(item for item in body["connections"] if item["role"] == "source")
        self.assertEqual(source_report["fields_from_environment"], ["password", "username"])

    def test_missing_required_fields_are_reported_not_invented(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'host = "db.internal"\n'
            "\n"
            "[destination.duckdb.credentials]\n"
            'database = "/tmp/warehouse.duckdb"\n'
        )
        report = self.root / "report.yml"
        self.assertEqual(self.run_converter("--report", str(report)), 0)
        body = yaml.safe_load(report.read_text(encoding="utf-8"))
        self.assertEqual(body["required_fields_missing"], ["dlt_source: database, password, port, username"])
        self.assertNotIn("password", self.connections()["postgres"][0])

    def test_gcp_service_account_is_reassembled_into_one_json_blob(self) -> None:
        # dlt keeps the service account as flat fields; Bruin needs one JSON blob.
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'database = "shop"\n'
            'username = "reader"\n'
            'password = "unit-test-postgres-secret"\n'
            'host = "db.internal"\n'
            "port = 5432\n"
            "\n"
            "[destination.bigquery.credentials]\n"
            'project_id = "unit-test-project"\n'
            'private_key = "-----BEGIN PRIVATE KEY-----\\nUNITKEY\\n-----END PRIVATE KEY-----\\n"\n'
            'client_email = "loader@unit-test-project.iam.gserviceaccount.com"\n'
            'location = "US"\n'
        )
        report = self.root / "report.yml"
        self.assertEqual(self.run_converter("--report", str(report)), 0)
        connection = self.connections()["google_cloud_platform"][0]
        document = json.loads(connection["service_account_json"])
        self.assertEqual(document["type"], "service_account")
        self.assertEqual(document["project_id"], "unit-test-project")
        self.assertIn("UNITKEY", document["private_key"])
        self.assertEqual(
            document["client_email"], "loader@unit-test-project.iam.gserviceaccount.com"
        )
        self.assertEqual(document["token_uri"], "https://oauth2.googleapis.com/token")
        body = yaml.safe_load(report.read_text(encoding="utf-8"))
        destination = next(item for item in body["connections"] if item["role"] == "destination")
        self.assertIn("service_account_json", destination["fields_populated"])
        self.assertEqual(destination["dlt_fields_without_bruin_mapping"], [])
        self.assertNotIn("UNITKEY", report.read_text(encoding="utf-8"))

    def test_gcp_without_credential_material_is_blocking(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'database = "shop"\n'
            'username = "reader"\n'
            'password = "unit-test-postgres-secret"\n'
            'host = "db.internal"\n'
            "port = 5432\n"
            "\n"
            "[destination.bigquery.credentials]\n"
            'project_id = "unit-test-project"\n'
        )
        report = self.root / "report.yml"
        self.assertEqual(self.run_converter("--report", str(report)), 0)
        body = yaml.safe_load(report.read_text(encoding="utf-8"))
        self.assertEqual(
            body["required_fields_missing"],
            ["dlt_destination: service_account_json or service_account_file or access_token"],
        )
        self.assertNotIn("service_account_json", self.connections()["google_cloud_platform"][0])

    def test_service_account_supplied_as_a_json_string(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'database = "shop"\n'
            'username = "reader"\n'
            'password = "unit-test-postgres-secret"\n'
            'host = "db.internal"\n'
            "port = 5432\n"
            "\n"
            "[destination.bigquery]\n"
            "credentials = "
            '"{\\"type\\":\\"service_account\\",\\"project_id\\":\\"json-proj\\",'
            '\\"private_key\\":\\"UNITKEY\\",'
            '\\"client_email\\":\\"a@json-proj.iam.gserviceaccount.com\\"}"\n'
        )
        self.assertEqual(self.run_converter(), 0)
        connection = self.connections()["google_cloud_platform"][0]
        self.assertEqual(connection["project_id"], "json-proj")
        self.assertEqual(json.loads(connection["service_account_json"])["private_key"], "UNITKEY")

    def test_databricks_uses_the_bruin_path_field(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'database = "shop"\n'
            'username = "reader"\n'
            'password = "unit-test-postgres-secret"\n'
            'host = "db.internal"\n'
            "port = 5432\n"
            "\n"
            "[destination.databricks.credentials]\n"
            'server_hostname = "adb-123.example.net"\n'
            'http_path = "/sql/1.0/warehouses/abc"\n'
            'access_token = "unit-test-databricks-token"\n'
        )
        self.assertEqual(self.run_converter(), 0)
        connection = self.connections()["databricks"][0]
        self.assertEqual(connection["path"], "/sql/1.0/warehouses/abc")
        self.assertNotIn("http_path", connection)
        self.assertEqual(connection["token"], "unit-test-databricks-token")

    def run_destination_only(self, *extra: str) -> int:
        arguments = [
            "--dlt-project-dir",
            str(self.project),
            "--output",
            str(self.output),
            "--destination-connection",
            "dst",
            *extra,
        ]
        namespace = converter.parser().parse_args(arguments)
        try:
            namespace.handler(namespace)
        except converter.ConversionError as exc:
            self.last_error = str(exc)
            return 2
        return 0

    def test_every_mapped_type_writes_its_bruin_fields(self) -> None:
        """Cover the mappings the PostgreSQL/ClickHouse fixture never exercises.

        Field names come from `pkg/config/connections.go`; this asserts the
        converter emits those exact names rather than dlt's.
        """
        cases = [
            (
                "mssql",
                'drivername = "mssql"\nhost = "sql.internal"\nport = 1433\n'
                'database = "warehouse"\nusername = "svc"\npassword = "unit-test-mssql"\n',
                "mssql",
                {
                    "name": "dst",
                    "host": "sql.internal",
                    "port": 1433,
                    "database": "warehouse",
                    "username": "svc",
                    "password": "unit-test-mssql",
                },
            ),
            (
                "synapse",
                'host = "syn.internal"\nport = 1433\ndatabase = "warehouse"\n'
                'username = "svc"\npassword = "unit-test-synapse"\n',
                "mssql",
                {
                    "name": "dst",
                    "host": "syn.internal",
                    "port": 1433,
                    "database": "warehouse",
                    "username": "svc",
                    "password": "unit-test-synapse",
                },
            ),
            (
                "redshift",
                'host = "rs.internal"\nport = 5439\ndatabase = "analytics"\n'
                'username = "svc"\npassword = "unit-test-redshift"\nsslmode = "require"\n',
                "redshift",
                {
                    "name": "dst",
                    "host": "rs.internal",
                    "port": 5439,
                    "database": "analytics",
                    "username": "svc",
                    "password": "unit-test-redshift",
                    "ssl_mode": "require",
                },
            ),
            (
                "snowflake",
                'host = "myorg-myacct"\nusername = "SVC"\ndatabase = "ANALYTICS"\n'
                'private_key = "unit-test-snowflake-key"\nwarehouse = "WH"\nrole = "LOADER"\n',
                "snowflake",
                {
                    "name": "dst",
                    "account": "myorg-myacct",
                    "username": "SVC",
                    "private_key": "unit-test-snowflake-key",
                    "database": "ANALYTICS",
                    "warehouse": "WH",
                    "role": "LOADER",
                },
            ),
            (
                "motherduck",
                'database = "analytics"\npassword = "unit-test-md-token"\n',
                "motherduck",
                {"name": "dst", "database": "analytics", "token": "unit-test-md-token"},
            ),
            (
                "athena",
                'region_name = "eu-central-1"\naws_access_key_id = "AKIAUNITTEST"\n'
                'aws_secret_access_key = "unit-test-aws-secret"\n'
                'query_result_bucket = "s3://results/"\n',
                "athena",
                {
                    "name": "dst",
                    "region": "eu-central-1",
                    "access_key_id": "AKIAUNITTEST",
                    "secret_access_key": "unit-test-aws-secret",
                    "query_results_path": "s3://results/",
                },
            ),
        ]
        for dlt_name, credentials, bruin_type, expected in cases:
            with self.subTest(destination=dlt_name):
                self.output.unlink(missing_ok=True)
                self.write_secrets(
                    f"[destination.{dlt_name}.credentials]\n{credentials}"
                )
                self.assertEqual(self.run_destination_only(), 0)
                self.assertEqual(self.connections()[bruin_type][0], expected)

    def test_mysql_source_drivername_maps_to_the_mysql_connection(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "mysql+pymysql"\n'
            'host = "mysql.internal"\n'
            "port = 3306\n"
            'database = "shop"\n'
            'username = "reader"\n'
            'password = "unit-test-mysql"\n'
            "\n"
            "[destination.duckdb.credentials]\n"
            'database = "/tmp/warehouse.duckdb"\n'
        )
        self.assertEqual(self.run_converter(), 0)
        self.assertEqual(
            self.connections()["mysql"][0],
            {
                "name": "dlt_source",
                "host": "mysql.internal",
                "port": 3306,
                "database": "shop",
                "username": "reader",
                "password": "unit-test-mysql",
            },
        )

    def test_unsupported_destination_fails_loudly(self) -> None:
        self.write_secrets(
            "[sources.sql_database.credentials]\n"
            'drivername = "postgresql"\n'
            'database = "shop"\n'
            'username = "reader"\n'
            'password = "unit-test-postgres-secret"\n'
            'host = "db.internal"\n'
            "port = 5432\n"
            "\n"
            "[destination.weaviate.credentials]\n"
            'url = "https://example.invalid"\n'
        )
        self.assertEqual(self.run_converter(), 2)
        self.assertIn("no reviewed Bruin mapping", self.last_error)
        self.assertFalse(self.output.exists())

    def test_multiple_destinations_require_an_explicit_choice(self) -> None:
        self.write_secrets(
            TABLE_SECRETS + '\n[destination.duckdb.credentials]\ndatabase = "/tmp/a.duckdb"\n'
        )
        self.assertEqual(self.run_converter(), 2)
        self.assertIn("migrate one at a time", self.last_error)
        self.assertEqual(
            self.run_converter("--destination-dlt-name", "clickhouse"), 0
        )
        self.assertIn("clickhouse", self.connections())

    def test_existing_connections_are_preserved_and_not_silently_replaced(self) -> None:
        self.output.write_text(
            yaml.safe_dump(
                {
                    "default_environment": "default",
                    "environments": {
                        "default": {
                            "connections": {
                                "duckdb": [{"name": "unrelated", "path": "/tmp/keep.duckdb"}],
                                "postgres": [{"name": "dlt_source", "host": "stale"}],
                            }
                        }
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.write_secrets(TABLE_SECRETS)
        self.assertEqual(self.run_converter(), 2)
        self.assertIn("already exists", self.last_error)
        self.assertEqual(self.run_converter("--replace"), 0)
        connections = self.connections()
        self.assertEqual(connections["duckdb"][0]["name"], "unrelated")
        self.assertEqual(len(connections["postgres"]), 1)
        self.assertEqual(connections["postgres"][0]["host"], "db.internal")

    def test_config_toml_options_are_not_mistaken_for_credentials(self) -> None:
        self.write_secrets(TABLE_SECRETS)
        self.write_config(
            "[sources.sql_database]\nchunk_size = 50000\nbackend = \"pyarrow\"\n"
            "\n[destination.clickhouse]\ndataset_table_separator = \"___\"\n"
        )
        report = self.root / "report.yml"
        self.assertEqual(self.run_converter("--report", str(report)), 0)
        body = yaml.safe_load(report.read_text(encoding="utf-8"))
        for entry in body["connections"]:
            self.assertEqual(entry["dlt_fields_without_bruin_mapping"], [])
        self.assertNotIn("dataset_table_separator", self.output.read_text(encoding="utf-8"))

    def test_missing_project_directory_fails(self) -> None:
        self.assertEqual(
            self.run_converter("--dlt-project-dir", str(self.root / "absent")), 2
        )
        self.assertIn("does not exist", self.last_error)


if __name__ == "__main__":
    unittest.main()
