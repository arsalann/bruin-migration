/* @bruin

name: bruin_ingestr.orders
type: pg.sql
description: Three hundred and fifty thousand deterministic, production-shaped synthetic order records per seed day.
tags:
  - seed

depends:
  - bruin_ingestr.customers

columns:
  - name: order_id
    type: bigint
    primary_key: true
    checks:
      - name: not_null
      - name: unique
  - name: external_order_id
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: customer_id
    type: bigint
    checks:
      - name: not_null
  - name: order_number
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: status
    type: string
    checks:
      - name: accepted_values
        value:
          - pending
          - paid
          - shipped
          - completed
          - cancelled
  - name: payment_status
    type: string
    checks:
      - name: accepted_values
        value:
          - pending
          - paid
          - refunded
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
  - name: sales_channel
    type: string
  - name: currency
    type: string
    checks:
      - name: accepted_values
        value:
          - EUR
          - GBP
          - USD
  - name: subtotal_cents
    type: bigint
  - name: discount_cents
    type: bigint
  - name: tax_cents
    type: bigint
  - name: shipping_cents
    type: bigint
  - name: total_amount_cents
    type: bigint
  - name: item_count
    type: integer
  - name: shipping_method
    type: string
  - name: shipping_country_code
    type: string
  - name: billing_country_code
    type: string
  - name: coupon_code
    type: string
  - name: payment_method
    type: string
  - name: risk_score
    type: integer
  - name: is_gift
    type: boolean
  - name: device_type
    type: string
  - name: ordered_at
    type: timestamp
    checks:
      - name: not_null
  - name: paid_at
    type: timestamp
  - name: shipped_at
    type: timestamp
  - name: delivered_at
    type: timestamp
  - name: cancelled_at
    type: timestamp
  - name: updated_at
    type: timestamp
    checks:
      - name: not_null
  - name: row_version
    type: integer

custom_checks:
  - name: every seeded day has three hundred and fifty thousand orders
    value: 0
    query: |-
      SELECT COUNT(*)
      FROM (
        SELECT (ordered_at AT TIME ZONE 'UTC')::date AS seed_date
        FROM bruin_ingestr.orders
        GROUP BY 1
        HAVING COUNT(*) <> 350000
      ) AS invalid_days
  - name: every order references a customer
    value: 0
    query: |
      SELECT COUNT(*)
      FROM bruin_ingestr.orders AS orders
      LEFT JOIN bruin_ingestr.customers AS customers
        ON customers.customer_id = orders.customer_id
      WHERE customers.customer_id IS NULL
  - name: order monetary values reconcile
    value: 0
    query: |
      SELECT COUNT(*)
      FROM bruin_ingestr.orders
      WHERE subtotal_cents - discount_cents + tax_cents + shipping_cents
          <> total_amount_cents
        OR subtotal_cents <= 0
        OR discount_cents < 0
        OR tax_cents < 0
        OR shipping_cents < 0
  - name: order lifecycle timestamps are valid
    value: 0
    query: |-
      SELECT COUNT(*)
      FROM bruin_ingestr.orders
      WHERE updated_at < ordered_at
        OR paid_at < ordered_at
        OR shipped_at < paid_at
        OR delivered_at < shipped_at
        OR cancelled_at < ordered_at

@bruin */

CREATE SCHEMA IF NOT EXISTS bruin_ingestr;

CREATE TABLE IF NOT EXISTS bruin_ingestr.orders (
  order_id BIGINT,
  external_order_id TEXT,
  customer_id BIGINT,
  order_number TEXT,
  status TEXT,
  payment_status TEXT,
  fulfillment_status TEXT,
  sales_channel TEXT,
  currency TEXT,
  subtotal_cents BIGINT,
  discount_cents BIGINT,
  tax_cents BIGINT,
  shipping_cents BIGINT,
  total_amount_cents BIGINT,
  item_count INTEGER,
  shipping_method TEXT,
  shipping_country_code TEXT,
  billing_country_code TEXT,
  coupon_code TEXT,
  payment_method TEXT,
  risk_score INTEGER,
  is_gift BOOLEAN,
  device_type TEXT,
  ordered_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  shipped_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  row_version INTEGER,
  CONSTRAINT orders_pkey PRIMARY KEY (order_id)
);

BEGIN;
{% if full_refresh %}
TRUNCATE TABLE bruin_ingestr.orders;
{% endif %}

INSERT INTO bruin_ingestr.orders (
  order_id,
  external_order_id,
  customer_id,
  order_number,
  status,
  payment_status,
  fulfillment_status,
  sales_channel,
  currency,
  subtotal_cents,
  discount_cents,
  tax_cents,
  shipping_cents,
  total_amount_cents,
  item_count,
  shipping_method,
  shipping_country_code,
  billing_country_code,
  coupon_code,
  payment_method,
  risk_score,
  is_gift,
  device_type,
  ordered_at,
  paid_at,
  shipped_at,
  delivered_at,
  cancelled_at,
  updated_at,
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
), generated AS (
  SELECT
    (day_offset * 350000 + order_sequence)::bigint AS order_id,
    md5('order-' || (day_offset * 350000 + order_sequence)::text) AS digest,
    (day_offset * 100000 + 1 + (order_sequence::bigint * 7919) % 100000)::bigint AS customer_id,
    CASE
      WHEN order_sequence % 100 < 5 THEN 'pending'
      WHEN order_sequence % 100 < 20 THEN 'paid'
      WHEN order_sequence % 100 < 45 THEN 'shipped'
      WHEN order_sequence % 100 < 95 THEN 'completed'
      ELSE 'cancelled'
    END AS status,
    (seed_date::timestamp AT TIME ZONE 'UTC')
      + (((order_sequence * 43) % 82800)::int * INTERVAL '1 second') AS ordered_at,
    (1 + order_sequence % 4)::int AS quantity,
    CASE WHEN order_sequence <= 175000 THEN 2 ELSE 1 END::int AS item_count,
    CASE
      WHEN order_sequence % 10 < 6 THEN 0
      WHEN order_sequence % 10 < 8 THEN 5
      WHEN order_sequence % 10 < 9 THEN 10
      ELSE 15
    END AS discount_percent,
    (ARRAY[1900, 2000, 700])[(order_sequence % 3)::int + 1] AS tax_rate_basis_points
  FROM seed_days
  CROSS JOIN generate_series(1, 350000) AS sequences(order_sequence)
), priced AS (
  SELECT
    *,
    (499 + (order_id * 7919) % 49501)::bigint AS unit_price_cents
  FROM generated
), per_line AS (
  SELECT
    *,
    (quantity * unit_price_cents)::bigint AS line_subtotal_cents,
    (quantity * unit_price_cents * discount_percent / 100)::bigint AS line_discount_cents
  FROM priced
), totals AS (
  SELECT
    *,
    (line_subtotal_cents * item_count)::bigint AS subtotal_cents,
    (line_discount_cents * item_count)::bigint AS discount_cents,
    (
      (line_subtotal_cents - line_discount_cents)
      * tax_rate_basis_points
      / 10000
      * item_count
    )::bigint AS tax_cents,
    CASE
      WHEN (line_subtotal_cents - line_discount_cents) * item_count >= 10000 THEN 0
      ELSE 499
    END::bigint AS shipping_cents
  FROM per_line
), lifecycle AS (
  SELECT
    *,
    CASE
      WHEN status <> 'pending'
        THEN ordered_at + ((5 + order_id % 180)::int * INTERVAL '1 minute')
    END AS paid_at,
    CASE
      WHEN status IN ('shipped', 'completed')
        THEN ordered_at + ((1 + order_id % 4)::int * INTERVAL '1 day')
    END AS shipped_at,
    CASE
      WHEN status = 'completed'
        THEN ordered_at + ((4 + order_id % 8)::int * INTERVAL '1 day')
    END AS delivered_at,
    CASE
      WHEN status = 'cancelled'
        THEN ordered_at + ((4 + order_id % 48)::int * INTERVAL '1 hour')
    END AS cancelled_at
  FROM totals
)
SELECT
  order_id,
  'ord_' || substr(digest, 1, 20) AS external_order_id,
  customer_id,
  'ORD-' || lpad(order_id::text, 12, '0') AS order_number,
  status,
  CASE
    WHEN status = 'pending' THEN 'pending'
    WHEN status = 'cancelled' THEN 'refunded'
    ELSE 'paid'
  END AS payment_status,
  CASE status
    WHEN 'pending' THEN 'unfulfilled'
    WHEN 'paid' THEN 'processing'
    WHEN 'shipped' THEN 'shipped'
    WHEN 'completed' THEN 'delivered'
    ELSE 'cancelled'
  END AS fulfillment_status,
  (ARRAY['web', 'ios', 'android', 'marketplace', 'sales'])[(order_id % 5)::int + 1] AS sales_channel,
  (ARRAY['EUR', 'GBP', 'USD'])[(order_id % 3)::int + 1] AS currency,
  subtotal_cents,
  discount_cents,
  tax_cents,
  shipping_cents,
  subtotal_cents - discount_cents + tax_cents + shipping_cents AS total_amount_cents,
  item_count,
  (ARRAY['standard', 'express', 'pickup', 'digital'])[(order_id % 4)::int + 1] AS shipping_method,
  (ARRAY['DE', 'FR', 'GB', 'NL', 'CA', 'US'])[(order_id % 6)::int + 1] AS shipping_country_code,
  (ARRAY['DE', 'FR', 'GB', 'NL', 'CA', 'US'])[((order_id * 5) % 6)::int + 1] AS billing_country_code,
  CASE WHEN order_id % 10 < 3 THEN 'SAVE' || (5 + order_id % 20)::text END AS coupon_code,
  (ARRAY['card', 'paypal', 'bank_transfer', 'wallet', 'invoice'])[(order_id % 5)::int + 1] AS payment_method,
  ((order_id * 3571) % 1000)::int AS risk_score,
  order_id % 20 = 0 AS is_gift,
  (ARRAY['desktop', 'mobile', 'tablet', 'api'])[(order_id % 4)::int + 1] AS device_type,
  ordered_at,
  paid_at,
  shipped_at,
  delivered_at,
  cancelled_at,
  ordered_at
    + ((order_id % 3600)::int * INTERVAL '1 second') AS updated_at,
  (1 + order_id % 16)::int AS row_version
FROM lifecycle
ON CONFLICT (order_id) DO NOTHING;

COMMIT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'bruin_ingestr.orders'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE bruin_ingestr.orders
      ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS orders_external_order_id_uidx
  ON bruin_ingestr.orders (external_order_id);
CREATE UNIQUE INDEX IF NOT EXISTS orders_order_number_uidx
  ON bruin_ingestr.orders (order_number);
