MODEL (
  name migration_source.orders,
  kind FULL,
  columns (
    id INT,
    order_date DATE,
    amount DECIMAL(12, 2)
  )
);

SELECT
  CAST(id AS INT) AS id,
  CAST(order_date AS DATE) AS order_date,
  CAST(amount AS DECIMAL(12, 2)) AS amount
FROM read_csv_auto(@fixture_orders_path(), header = true);
