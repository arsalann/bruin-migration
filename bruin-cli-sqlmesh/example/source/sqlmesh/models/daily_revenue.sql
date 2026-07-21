MODEL (
  name migration_source.daily_revenue,
  kind FULL,
  audits (assert_positive_revenue),
  columns (
    order_date DATE,
    revenue DECIMAL(12, 2)
  )
);

SELECT
  order_date,
  SUM(amount) AS revenue
FROM migration_source.orders
GROUP BY order_date
ORDER BY order_date;
