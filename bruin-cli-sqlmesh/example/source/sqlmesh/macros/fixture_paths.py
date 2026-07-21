from sqlmesh import macro


@macro()
def fixture_orders_path(evaluator):
    """Return the local CSV path as a DuckDB string literal."""
    return "'fixtures/orders.csv'"
