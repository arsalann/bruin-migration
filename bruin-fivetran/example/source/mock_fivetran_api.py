#!/usr/bin/env python3
"""Serve deterministic Fivetran read-only API responses for the local fixture."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def handler_factory(fixture: dict[str, object]):
    expected = str(fixture["expected_authorization"])
    pages = fixture["connection_pages"]
    details = fixture["details"]
    schemas = fixture["schemas"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def write_json(self, status: HTTPStatus, body: dict[str, object]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            if self.headers.get("Authorization") != expected:
                self.write_json(HTTPStatus.UNAUTHORIZED, {"code": "Unauthorized"})
                return
            parsed = urlparse(self.path)
            if parsed.path == "/v1/connections":
                cursor = parse_qs(parsed.query).get("cursor", ["first"])[0]
                page = pages.get(cursor)
                if not isinstance(page, dict):
                    self.write_json(HTTPStatus.NOT_FOUND, {"code": "NotFound"})
                    return
                self.write_json(HTTPStatus.OK, {"data": page})
                return
            prefix = "/v1/connections/"
            if not parsed.path.startswith(prefix):
                self.write_json(HTTPStatus.NOT_FOUND, {"code": "NotFound"})
                return
            suffix = parsed.path[len(prefix) :]
            if suffix.endswith("/schemas"):
                connection_id = suffix[: -len("/schemas")]
                schema = schemas.get(connection_id)
                if not isinstance(schema, dict):
                    self.write_json(HTTPStatus.NOT_FOUND, {"code": "NotFound"})
                    return
                self.write_json(HTTPStatus.OK, {"data": schema})
                return
            detail = details.get(suffix)
            if not isinstance(detail, dict):
                self.write_json(HTTPStatus.NOT_FOUND, {"code": "NotFound"})
                return
            self.write_json(HTTPStatus.OK, {"data": detail})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--port-file", required=True)
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(fixture))
    Path(args.port_file).write_text(str(server.server_port), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
