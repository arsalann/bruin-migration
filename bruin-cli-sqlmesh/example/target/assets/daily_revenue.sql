/* @bruin
name: migration_target.daily_revenue
type: duckdb.sql
connection: target_duckdb
description: Equivalent of the SQLMesh daily revenue model.

materialization:
  type: table

depends:
  - migration_target.orders

columns:
  - name: order_date
    type: date
    checks:
      - name: not_null
  - name: revenue
    type: numeric
    checks:
      - name: positive

custom_checks:
  - name: every order day is represented
    value: 0
    query: |
      SELECT CASE
        WHEN (SELECT COUNT(DISTINCT order_date) FROM migration_target.orders)
           = (SELECT COUNT(*) FROM migration_target.daily_revenue)
        THEN 0 ELSE 1
      END

unit_tests:
  - name: aggregates_orders_by_day
    inputs:
      - asset: migration_target.orders
        rows:
          - {id: 1, order_date: 2025-01-01, amount: 120.00}
          - {id: 2, order_date: 2025-01-01, amount: 80.00}
          - {id: 3, order_date: 2025-01-02, amount: 50.00}
    expected:
      match: exact
      rows:
        - {order_date: 2025-01-01, revenue: 200.00}
        - {order_date: 2025-01-02, revenue: 50.00}
@bruin */

SELECT
  order_date,
  SUM(amount) AS revenue
FROM migration_target.orders
GROUP BY order_date
ORDER BY order_date;
