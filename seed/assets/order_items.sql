/* @bruin

name: bruin_ingestr.order_items
type: pg.sql
description: Five hundred and twenty-five thousand deterministic, production-shaped synthetic order-item records per seed day.
tags:
  - seed

depends:
  - bruin_ingestr.orders
  - bruin_ingestr.products

columns:
  - name: order_item_id
    type: bigint
    primary_key: true
    checks:
      - name: not_null
      - name: unique
  - name: external_order_item_id
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: order_id
    type: bigint
    checks:
      - name: not_null
  - name: product_id
    type: bigint
    checks:
      - name: not_null
  - name: line_number
    type: integer
  - name: sku
    type: string
  - name: product_name
    type: string
  - name: quantity
    type: integer
  - name: unit_price_cents
    type: bigint
  - name: list_price_cents
    type: bigint
  - name: discount_percent
    type: integer
    checks:
      - name: accepted_values
        value:
          - 0
          - 5
          - 10
          - 15
  - name: discount_cents
    type: bigint
  - name: tax_rate_basis_points
    type: integer
  - name: tax_cents
    type: bigint
  - name: line_subtotal_cents
    type: bigint
  - name: line_total_cents
    type: bigint
  - name: currency
    type: string
    checks:
      - name: accepted_values
        value:
          - EUR
          - GBP
          - USD
  - name: fulfillment_status
    type: string
    checks:
      - name: accepted_values
        value:
          - unfulfilled
          - processing
          - shipped
          - delivered
          - cancelled
  - name: warehouse_code
    type: string
  - name: is_gift
    type: boolean
  - name: returned_quantity
    type: integer
  - name: return_reason
    type: string
  - name: created_at
    type: timestamp
    checks:
      - name: not_null
  - name: updated_at
    type: timestamp
    checks:
      - name: not_null
  - name: source_updated_at
    type: timestamp
  - name: row_version
    type: integer

custom_checks:
  - name: every seeded day has five hundred and twenty-five thousand order items
    value: 0
    query: |-
      SELECT COUNT(*)
      FROM (
        SELECT (created_at AT TIME ZONE 'UTC')::date AS seed_date
        FROM bruin_ingestr.order_items
        GROUP BY 1
        HAVING COUNT(*) <> 525000
      ) AS invalid_days
  - name: every order item references an order and product
    value: 0
    query: |
      SELECT COUNT(*)
      FROM bruin_ingestr.order_items AS items
      LEFT JOIN bruin_ingestr.orders AS orders
        ON orders.order_id = items.order_id
      LEFT JOIN bruin_ingestr.products AS products
        ON products.product_id = items.product_id
      WHERE orders.order_id IS NULL OR products.product_id IS NULL
  - name: order item monetary values reconcile
    value: 0
    query: |
      SELECT COUNT(*)
      FROM bruin_ingestr.order_items
      WHERE line_subtotal_cents - discount_cents <> line_total_cents
        OR line_total_cents * tax_rate_basis_points / 10000 <> tax_cents
        OR quantity <= 0
        OR unit_price_cents <= 0
        OR list_price_cents < unit_price_cents
        OR returned_quantity < 0
        OR returned_quantity > quantity
  - name: every order total matches its order items
    value: 0
    query: |-
      WITH item_totals AS (
        SELECT
          order_id,
          COUNT(*) AS item_count,
          SUM(line_subtotal_cents) AS subtotal_cents,
          SUM(discount_cents) AS discount_cents,
          SUM(tax_cents) AS tax_cents,
          SUM(line_total_cents) AS line_total_cents
        FROM bruin_ingestr.order_items
        GROUP BY order_id
      )
      SELECT COUNT(*)
      FROM bruin_ingestr.orders AS orders
      LEFT JOIN item_totals
        ON item_totals.order_id = orders.order_id
      WHERE item_totals.order_id IS NULL
        OR orders.item_count <> item_totals.item_count
        OR orders.subtotal_cents <> item_totals.subtotal_cents
        OR orders.discount_cents <> item_totals.discount_cents
        OR orders.tax_cents <> item_totals.tax_cents
        OR orders.total_amount_cents
          <> item_totals.line_total_cents + item_totals.tax_cents + orders.shipping_cents

@bruin */

CREATE SCHEMA IF NOT EXISTS bruin_ingestr;

CREATE TABLE IF NOT EXISTS bruin_ingestr.order_items (
  order_item_id BIGINT,
  external_order_item_id TEXT,
  order_id BIGINT,
  product_id BIGINT,
  line_number INTEGER,
  sku TEXT,
  product_name TEXT,
  quantity INTEGER,
  unit_price_cents BIGINT,
  list_price_cents BIGINT,
  discount_percent INTEGER,
  discount_cents BIGINT,
  tax_rate_basis_points INTEGER,
  tax_cents BIGINT,
  line_subtotal_cents BIGINT,
  line_total_cents BIGINT,
  currency TEXT,
  fulfillment_status TEXT,
  warehouse_code TEXT,
  is_gift BOOLEAN,
  returned_quantity INTEGER,
  return_reason TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  source_updated_at TIMESTAMPTZ,
  row_version INTEGER,
  CONSTRAINT order_items_pkey PRIMARY KEY (order_item_id)
);

BEGIN;
{% if full_refresh %}
TRUNCATE TABLE bruin_ingestr.order_items;
{% endif %}

INSERT INTO bruin_ingestr.order_items (
  order_item_id,
  external_order_item_id,
  order_id,
  product_id,
  line_number,
  sku,
  product_name,
  quantity,
  unit_price_cents,
  list_price_cents,
  discount_percent,
  discount_cents,
  tax_rate_basis_points,
  tax_cents,
  line_subtotal_cents,
  line_total_cents,
  currency,
  fulfillment_status,
  warehouse_code,
  is_gift,
  returned_quantity,
  return_reason,
  created_at,
  updated_at,
  source_updated_at,
  row_version
)
WITH seed_days AS (
  SELECT
    seed_day::date AS seed_date,
    (seed_day::date - DATE '2020-01-01')::bigint AS day_offset
  FROM generate_series(
    '{{ start_date }}'::date,
    '{{ end_date }}'::date,
    INTERVAL '1 day'
  ) AS days(seed_day)
), mapped AS (
  SELECT
    seed_date,
    day_offset,
    (day_offset * 525000 + item_sequence)::bigint AS order_item_id,
    CASE
      WHEN item_sequence <= 350000 THEN ((item_sequence - 1) / 2 + 1)::bigint
      ELSE (item_sequence - 175000)::bigint
    END AS order_sequence,
    CASE
      WHEN item_sequence <= 350000 THEN ((item_sequence - 1) % 2 + 1)::int
      ELSE 1
    END AS line_number
  FROM seed_days
  CROSS JOIN generate_series(1, 525000) AS sequences(item_sequence)
), generated AS (
  SELECT
    order_item_id,
    (day_offset * 350000 + order_sequence)::bigint AS order_id,
    line_number,
    md5('order-item-' || order_item_id::text) AS digest,
    (
      day_offset * 25000 + 1 + (
        order_sequence * 104729
        + line_number * 7919
      ) % 25000
    )::bigint AS product_id,
    (1 + order_sequence % 4)::int AS quantity,
    CASE
      WHEN order_sequence % 10 < 6 THEN 0
      WHEN order_sequence % 10 < 8 THEN 5
      WHEN order_sequence % 10 < 9 THEN 10
      ELSE 15
    END AS discount_percent,
    (ARRAY[1900, 2000, 700])[(order_sequence % 3)::int + 1] AS tax_rate_basis_points,
    CASE
      WHEN order_sequence % 100 < 5 THEN 'pending'
      WHEN order_sequence % 100 < 20 THEN 'paid'
      WHEN order_sequence % 100 < 45 THEN 'shipped'
      WHEN order_sequence % 100 < 95 THEN 'completed'
      ELSE 'cancelled'
    END AS order_status,
    (seed_date::timestamp AT TIME ZONE 'UTC')
      + (((order_sequence * 43) % 82800)::int * INTERVAL '1 second') AS created_at
  FROM mapped
), priced AS (
  SELECT
    *,
    (499 + (order_id * 7919) % 49501)::bigint AS unit_price_cents
  FROM generated
), money AS (
  SELECT
    *,
    (quantity * unit_price_cents)::bigint AS line_subtotal_cents,
    (quantity * unit_price_cents * discount_percent / 100)::bigint AS discount_cents
  FROM priced
), totals AS (
  SELECT
    *,
    line_subtotal_cents - discount_cents AS line_total_cents,
    (
      (line_subtotal_cents - discount_cents)
      * tax_rate_basis_points
      / 10000
    )::bigint AS tax_cents
  FROM money
)
SELECT
  order_item_id,
  'itm_' || substr(digest, 1, 20) AS external_order_item_id,
  order_id,
  product_id,
  line_number,
  'SKU-' || lpad(product_id::text, 10, '0') AS sku,
  (ARRAY['Adaptive', 'Compact', 'Essential', 'Modular', 'Prime', 'Smart'])[(product_id % 6)::int + 1]
    || ' '
    || (ARRAY['Console', 'Gateway', 'Hub', 'Kit', 'Plan', 'Sensor', 'Suite', 'Workspace'])[((product_id * 7) % 8)::int + 1]
    || ' '
    || product_id::text AS product_name,
  quantity,
  unit_price_cents,
  (unit_price_cents * 110 / 100)::bigint AS list_price_cents,
  discount_percent,
  discount_cents,
  tax_rate_basis_points,
  tax_cents,
  line_subtotal_cents,
  line_total_cents,
  (ARRAY['EUR', 'GBP', 'USD'])[(order_id % 3)::int + 1] AS currency,
  CASE order_status
    WHEN 'pending' THEN 'unfulfilled'
    WHEN 'paid' THEN 'processing'
    WHEN 'shipped' THEN 'shipped'
    WHEN 'completed' THEN 'delivered'
    ELSE 'cancelled'
  END AS fulfillment_status,
  'WH-' || lpad((1 + product_id % 250)::text, 3, '0') AS warehouse_code,
  order_id % 20 = 0 AS is_gift,
  CASE WHEN order_status = 'completed' AND order_id % 25 = 0 THEN 1 ELSE 0 END AS returned_quantity,
  CASE
    WHEN order_status = 'completed' AND order_id % 25 = 0
      THEN (ARRAY['damaged', 'not_as_described', 'wrong_item', 'changed_mind'])[(order_id % 4)::int + 1]
  END AS return_reason,
  created_at,
  created_at
    + ((order_item_id % 3600)::int * INTERVAL '1 second') AS updated_at,
  created_at
    + ((order_item_id % 3600)::int * INTERVAL '1 second') AS source_updated_at,
  (1 + order_item_id % 16)::int AS row_version
FROM totals
ON CONFLICT (order_item_id) DO NOTHING;

COMMIT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'bruin_ingestr.order_items'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE bruin_ingestr.order_items
      ADD CONSTRAINT order_items_pkey PRIMARY KEY (order_item_id);
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS order_items_external_order_item_id_uidx
  ON bruin_ingestr.order_items (external_order_item_id);
CREATE UNIQUE INDEX IF NOT EXISTS order_items_order_line_uidx
  ON bruin_ingestr.order_items (order_id, line_number);
