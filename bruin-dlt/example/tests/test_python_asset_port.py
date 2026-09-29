#!/usr/bin/env python3
"""Prove the dlt resource's Python was ported faithfully into the Bruin asset.

The custom-API case is a *port*, not a translation: the same paginator and the
same row transforms must exist on both sides. If someone edits one and not the
other, parity would only fail later, during a live run against the API. These
tests catch it immediately and without network access, pandas, or dlt.

Both files are read and the shared functions are extracted with `ast`, so
importing the modules — and therefore importing `dlt`, `pandas`, and `requests`
— is not required.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DLT_RESOURCE = EXAMPLE_ROOT / "source" / "dlt_api_pipeline.py"
BRUIN_ASSET = EXAMPLE_ROOT / "target" / "assets" / "pokemon.py"
PORTED_FUNCTIONS = ("pokemon_id_from_url", "add_derived_columns")
SHARED_CONSTANTS = ("API_BASE", "PAGE_SIZE", "REQUEST_TIMEOUT")


def functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }


def constants(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in SHARED_CONSTANTS:
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return found


def body_source(node: ast.FunctionDef) -> str:
    """Unparse a function's statements, ignoring its docstring and decorators."""
    statements = list(node.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    return "\n".join(ast.unparse(statement) for statement in statements)


def compiled(path: Path, *names: str) -> dict[str, object]:
    """Compile the named functions into one shared namespace so they can call
    each other, without importing the module or its heavy dependencies."""
    available = functions(path)
    body: list[ast.stmt] = [
        # The real modules use `from __future__ import annotations`; without it
        # the extracted annotations would be evaluated and fail on `Any`.
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations", asname=None)], level=0
        )
    ]
    for name in names:
        node = available[name]
        node.decorator_list = []
        body.append(node)
    module = ast.Module(body=body, type_ignores=[])
    namespace: dict[str, object] = {}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace


class PortFidelityTestCase(unittest.TestCase):
    def test_ported_functions_exist_on_both_sides(self) -> None:
        for name in PORTED_FUNCTIONS:
            self.assertIn(name, functions(DLT_RESOURCE), f"{name} missing from the dlt resource")
            self.assertIn(name, functions(BRUIN_ASSET), f"{name} missing from the Bruin asset")

    def test_ported_functions_are_identical(self) -> None:
        dlt_side = functions(DLT_RESOURCE)
        bruin_side = functions(BRUIN_ASSET)
        for name in PORTED_FUNCTIONS:
            with self.subTest(function=name):
                self.assertEqual(
                    body_source(dlt_side[name]),
                    body_source(bruin_side[name]),
                    f"{name} has drifted between the dlt resource and the Bruin asset",
                )

    def test_shared_api_constants_match(self) -> None:
        self.assertEqual(constants(DLT_RESOURCE), constants(BRUIN_ASSET))
        self.assertEqual(len(constants(BRUIN_ASSET)), len(SHARED_CONSTANTS))

    def test_transform_behaviour(self) -> None:
        namespace = compiled(BRUIN_ASSET, *PORTED_FUNCTIONS)
        transform = namespace["add_derived_columns"]
        parse_id = namespace["pokemon_id_from_url"]
        record = transform(
            {"name": "bulbasaur", "url": "https://pokeapi.co/api/v2/pokemon/1/"}
        )
        self.assertEqual(record["pokemon_id"], 1)
        self.assertEqual(record["name_upper"], "BULBASAUR")
        self.assertEqual(record["name_length"], 9)
        self.assertEqual(parse_id("https://pokeapi.co/api/v2/pokemon/60"), 60)

    def test_both_paginators_page_over_the_same_window(self) -> None:
        """The loops differ in shape (generator vs list) but not in coverage."""
        dlt_body = body_source(functions(DLT_RESOURCE)["pokemon"])
        bruin_body = body_source(functions(BRUIN_ASSET)["fetch_pages"])
        # Fragments are written as `ast.unparse` renders them, not as authored.
        for fragment in ("f'{API_BASE}/pokemon'", "min(PAGE_SIZE, total - offset)", "offset +="):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, dlt_body)
                self.assertIn(fragment, bruin_body)

    def test_asset_declares_only_the_target_schema(self) -> None:
        """`url` feeds the transform but must not reach the destination."""
        source = BRUIN_ASSET.read_text(encoding="utf-8")
        self.assertIn('["pokemon_id", "name", "name_upper", "name_length"]', source)
        materialize = functions(BRUIN_ASSET)["materialize"]
        self.assertNotIn('"url"', body_source(materialize))


if __name__ == "__main__":
    unittest.main()
