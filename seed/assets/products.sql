/* @bruin

name: bruin_ingestr.products
type: pg.sql
description: Twenty-five thousand deterministic, production-shaped synthetic product records per seed day.
tags:
  - seed

columns:
  - name: product_id
    type: bigint
    primary_key: true
    checks:
      - name: not_null
      - name: unique
  - name: external_product_id
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: sku
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: product_name
    type: string
  - name: product_description
    type: string
  - name: category
    type: string
    checks:
      - name: accepted_values
        value:
          - hardware
          - software
          - service
          - accessory
  - name: subcategory
    type: string
  - name: brand
    type: string
  - name: supplier_id
    type: bigint
  - name: warehouse_code
    type: string
  - name: currency
    type: string
    checks:
      - name: accepted_values
        value:
          - EUR
          - GBP
          - USD
  - name: unit_price_cents
    type: bigint
  - name: cost_price_cents
    type: bigint
  - name: tax_rate_basis_points
    type: integer
  - name: weight_grams
    type: integer
  - name: length_mm
    type: integer
  - name: width_mm
    type: integer
  - name: height_mm
    type: integer
  - name: stock_quantity
    type: bigint
  - name: reorder_level
    type: integer
  - name: safety_stock
    type: integer
  - name: rating_x100
    type: integer
  - name: review_count
    type: bigint
  - name: is_active
    type: boolean
  - name: is_digital
    type: boolean
  - name: created_at
    type: timestamp
    checks:
      - name: not_null
  - name: updated_at
    type: timestamp
    checks:
      - name: not_null
  - name: discontinued_at
    type: timestamp
  - name: row_version
    type: integer

custom_checks:
  - name: every seeded day has twenty-five thousand products
    value: 0
    query: |-
      SELECT COUNT(*)
      FROM (
        SELECT (created_at AT TIME ZONE 'UTC')::date AS seed_date
        FROM bruin_ingestr.products
        GROUP BY 1
        HAVING COUNT(*) <> 25000
      ) AS invalid_days
  - name: product prices inventory and timestamps are valid
    value: 0
    query: |-
      SELECT COUNT(*)
      FROM bruin_ingestr.products
      WHERE unit_price_cents <= 0
        OR cost_price_cents <= 0
        OR cost_price_cents > unit_price_cents
        OR stock_quantity < 0
        OR reorder_level < safety_stock
        OR updated_at < created_at
        OR discontinued_at < updated_at

@bruin */

CREATE SCHEMA IF NOT EXISTS bruin_ingestr;

CREATE TABLE IF NOT EXISTS bruin_ingestr.products (
  product_id BIGINT,
  external_product_id TEXT,
  sku TEXT,
  product_name TEXT,
  product_description TEXT,
  category TEXT,
  subcategory TEXT,
  brand TEXT,
  supplier_id BIGINT,
  warehouse_code TEXT,
  currency TEXT,
  unit_price_cents BIGINT,
  cost_price_cents BIGINT,
  tax_rate_basis_points INTEGER,
  weight_grams INTEGER,
  length_mm INTEGER,
  width_mm INTEGER,
  height_mm INTEGER,
  stock_quantity BIGINT,
  reorder_level INTEGER,
  safety_stock INTEGER,
  rating_x100 INTEGER,
  review_count BIGINT,
  is_active BOOLEAN,
  is_digital BOOLEAN,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  discontinued_at TIMESTAMPTZ,
  row_version INTEGER,
  CONSTRAINT products_pkey PRIMARY KEY (product_id)
);

BEGIN;
{% if full_refresh %}
TRUNCATE TABLE bruin_ingestr.products;
{% endif %}

INSERT INTO bruin_ingestr.products (
  product_id,
  external_product_id,
  sku,
  product_name,
  product_description,
  category,
  subcategory,
  brand,
  supplier_id,
  warehouse_code,
  currency,
  unit_price_cents,
  cost_price_cents,
  tax_rate_basis_points,
  weight_grams,
  length_mm,
  width_mm,
  height_mm,
  stock_quantity,
  reorder_level,
  safety_stock,
  rating_x100,
  review_count,
  is_active,
  is_digital,
  created_at,
  updated_at,
  discontinued_at,
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
    (day_offset * 25000 + product_sequence)::bigint AS product_id,
    md5('product-' || (day_offset * 25000 + product_sequence)::text) AS digest,
    (499 + ((day_offset * 25000 + product_sequence)::bigint * 7919) % 49501)::bigint AS unit_price_cents,
    (seed_date::timestamp AT TIME ZONE 'UTC')
      + (((product_sequence * 41) % 82800)::int * INTERVAL '1 second') AS created_at
  FROM seed_days
  CROSS JOIN generate_series(1, 25000) AS sequences(product_sequence)
), shaped AS (
  SELECT
    *,
    created_at
      + ((product_id % 3600)::int * INTERVAL '1 second') AS updated_at
  FROM generated
)
SELECT
  product_id,
  'prd_' || substr(digest, 1, 20) AS external_product_id,
  'SKU-' || lpad(product_id::text, 10, '0') AS sku,
  (ARRAY['Adaptive', 'Compact', 'Essential', 'Modular', 'Prime', 'Smart'])[(product_id % 6)::int + 1]
    || ' '
    || (ARRAY['Console', 'Gateway', 'Hub', 'Kit', 'Plan', 'Sensor', 'Suite', 'Workspace'])[((product_id * 7) % 8)::int + 1]
    || ' '
    || product_id::text AS product_name,
  'Synthetic catalog item ' || product_id::text || ' for production-scale ingestion testing.' AS product_description,
  (ARRAY['hardware', 'software', 'service', 'accessory'])[(product_id % 4)::int + 1] AS category,
  (ARRAY['compute', 'network', 'security', 'storage', 'support', 'analytics', 'automation', 'peripheral'])[(product_id % 8)::int + 1] AS subcategory,
  (ARRAY['Northstar', 'Acme', 'Globex', 'Initech', 'Umbrella', 'Stark', 'Wayne', 'Wonka'])[(product_id % 8)::int + 1] AS brand,
  (1 + product_id % 10000)::bigint AS supplier_id,
  'WH-' || lpad((1 + product_id % 250)::text, 3, '0') AS warehouse_code,
  (ARRAY['EUR', 'GBP', 'USD'])[(product_id % 3)::int + 1] AS currency,
  unit_price_cents,
  (unit_price_cents * (40 + product_id % 35) / 100)::bigint AS cost_price_cents,
  (ARRAY[0, 700, 1900])[(product_id % 3)::int + 1] AS tax_rate_basis_points,
  (50 + product_id % 25000)::int AS weight_grams,
  (20 + product_id % 980)::int AS length_mm,
  (20 + (product_id * 3) % 780)::int AS width_mm,
  (5 + (product_id * 7) % 495)::int AS height_mm,
  ((product_id * 3571) % 50000)::bigint AS stock_quantity,
  (50 + product_id % 450)::int AS reorder_level,
  (10 + product_id % 40)::int AS safety_stock,
  (300 + product_id % 201)::int AS rating_x100,
  ((product_id * 104729) % 250000)::bigint AS review_count,
  product_id % 20 <> 0 AS is_active,
  product_id % 4 IN (1, 2) AS is_digital,
  created_at,
  updated_at,
  CASE
    WHEN product_id % 20 = 0
      THEN updated_at + ((1 + product_id % 90)::int * INTERVAL '1 day')
  END AS discontinued_at,
  (1 + product_id % 20)::int AS row_version
FROM shaped
ON CONFLICT (product_id) DO NOTHING;

COMMIT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'bruin_ingestr.products'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE bruin_ingestr.products
      ADD CONSTRAINT products_pkey PRIMARY KEY (product_id);
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS products_external_product_id_uidx
  ON bruin_ingestr.products (external_product_id);
CREATE UNIQUE INDEX IF NOT EXISTS products_sku_uidx
  ON bruin_ingestr.products (sku);
