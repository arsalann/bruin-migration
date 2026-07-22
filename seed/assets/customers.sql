/* @bruin

name: bruin_ingestr.customers
type: pg.sql
description: One million deterministic, production-shaped synthetic customer records.
tags:
  - seed

columns:
  - name: customer_id
    type: bigint
    primary_key: true
    checks:
      - name: not_null
      - name: unique
  - name: external_customer_id
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: email
    type: string
    checks:
      - name: not_null
      - name: unique
  - name: first_name
    type: string
  - name: last_name
    type: string
  - name: phone_number
    type: string
  - name: date_of_birth
    type: date
  - name: country_code
    type: string
    checks:
      - name: accepted_values
        value:
          - DE
          - FR
          - GB
          - NL
          - CA
          - US
  - name: region
    type: string
  - name: city
    type: string
  - name: postal_code
    type: string
  - name: address_line_1
    type: string
  - name: preferred_language
    type: string
    checks:
      - name: accepted_values
        value:
          - de
          - en
          - fr
          - nl
  - name: segment
    type: string
    checks:
      - name: accepted_values
        value:
          - consumer
          - smb
          - enterprise
  - name: acquisition_channel
    type: string
    checks:
      - name: accepted_values
        value:
          - organic
          - paid_search
          - referral
          - partner
          - outbound
  - name: marketing_opt_in
    type: boolean
  - name: loyalty_tier
    type: string
    checks:
      - name: accepted_values
        value:
          - none
          - bronze
          - silver
          - gold
          - platinum
  - name: lifetime_value_cents
    type: bigint
  - name: credit_limit_cents
    type: bigint
  - name: account_status
    type: string
    checks:
      - name: accepted_values
        value:
          - active
          - dormant
          - suspended
          - closed
  - name: is_active
    type: boolean
  - name: signup_source
    type: string
  - name: referral_code
    type: string
  - name: support_priority
    type: string
    checks:
      - name: accepted_values
        value:
          - normal
          - elevated
          - critical
  - name: created_at
    type: timestamp
    checks:
      - name: not_null
  - name: updated_at
    type: timestamp
    checks:
      - name: not_null
  - name: last_login_at
    type: timestamp
  - name: row_version
    type: integer
  - name: source_system
    type: string

custom_checks:
  - name: has exactly one million customers
    value: 1000000
    query: SELECT COUNT(*) FROM bruin_ingestr.customers
  - name: customer values and timestamps are valid
    value: 0
    query: |-
      SELECT COUNT(*)
      FROM bruin_ingestr.customers
      WHERE lifetime_value_cents < 0
        OR credit_limit_cents < 0
        OR updated_at < created_at
        OR last_login_at < created_at
        OR row_version < 1

@bruin */

CREATE SCHEMA IF NOT EXISTS bruin_ingestr;

CREATE TABLE IF NOT EXISTS bruin_ingestr.customers (
  customer_id BIGINT,
  external_customer_id TEXT,
  email TEXT,
  first_name TEXT,
  last_name TEXT,
  phone_number TEXT,
  date_of_birth DATE,
  country_code TEXT,
  region TEXT,
  city TEXT,
  postal_code TEXT,
  address_line_1 TEXT,
  preferred_language TEXT,
  segment TEXT,
  acquisition_channel TEXT,
  marketing_opt_in BOOLEAN,
  loyalty_tier TEXT,
  lifetime_value_cents BIGINT,
  credit_limit_cents BIGINT,
  account_status TEXT,
  is_active BOOLEAN,
  signup_source TEXT,
  referral_code TEXT,
  support_priority TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  row_version INTEGER,
  source_system TEXT,
  CONSTRAINT customers_pkey PRIMARY KEY (customer_id)
);

BEGIN;
TRUNCATE TABLE bruin_ingestr.customers;

INSERT INTO bruin_ingestr.customers (
  customer_id,
  external_customer_id,
  email,
  first_name,
  last_name,
  phone_number,
  date_of_birth,
  country_code,
  region,
  city,
  postal_code,
  address_line_1,
  preferred_language,
  segment,
  acquisition_channel,
  marketing_opt_in,
  loyalty_tier,
  lifetime_value_cents,
  credit_limit_cents,
  account_status,
  is_active,
  signup_source,
  referral_code,
  support_priority,
  created_at,
  updated_at,
  last_login_at,
  row_version,
  source_system
)
WITH generated AS (
  SELECT
    id::bigint AS customer_id,
    md5('customer-' || id::text) AS digest,
    TIMESTAMPTZ '2021-01-01 00:00:00+00'
      + ((id % 1460)::int * INTERVAL '1 day')
      + ((id % 1440)::int * INTERVAL '1 minute') AS created_at
  FROM generate_series(1, 1000000) AS ids(id)
), shaped AS (
  SELECT
    customer_id,
    digest,
    created_at,
    created_at
      + ((customer_id % 120)::int * INTERVAL '1 day')
      + ((customer_id % 720)::int * INTERVAL '1 minute') AS updated_at
  FROM generated
)
SELECT
  customer_id,
  'cus_' || substr(digest, 1, 20) AS external_customer_id,
  'customer' || customer_id::text || '@example.test' AS email,
  (ARRAY['Alex', 'Amara', 'Chen', 'Diego', 'Fatima', 'Hana', 'Jonas', 'Leila', 'Maya', 'Noah', 'Priya', 'Sofia'])[(customer_id % 12)::int + 1] AS first_name,
  (ARRAY['Bauer', 'Brown', 'Dubois', 'Garcia', 'Jansen', 'Khan', 'Kim', 'Martin', 'Miller', 'Novak', 'Patel', 'Silva'])[((customer_id * 7) % 12)::int + 1] AS last_name,
  '+' || (ARRAY['49', '33', '44', '31', '1', '1'])[(customer_id % 6)::int + 1]
    || lpad((customer_id % 10000000000)::text, 10, '0') AS phone_number,
  make_date(
    1950 + (customer_id % 55)::int,
    1 + (customer_id % 12)::int,
    1 + (customer_id % 28)::int
  ) AS date_of_birth,
  (ARRAY['DE', 'FR', 'GB', 'NL', 'CA', 'US'])[(customer_id % 6)::int + 1] AS country_code,
  (ARRAY['DACH', 'Western Europe', 'United Kingdom', 'Benelux', 'North America', 'North America'])[(customer_id % 6)::int + 1] AS region,
  (ARRAY['Berlin', 'Paris', 'London', 'Amsterdam', 'Toronto', 'New York'])[(customer_id % 6)::int + 1] AS city,
  lpad((10000 + customer_id % 89999)::text, 5, '0') AS postal_code,
  (1 + customer_id % 9999)::text || ' Example Street' AS address_line_1,
  (ARRAY['de', 'fr', 'en', 'nl', 'en', 'en'])[(customer_id % 6)::int + 1] AS preferred_language,
  CASE
    WHEN customer_id % 100 < 70 THEN 'consumer'
    WHEN customer_id % 100 < 94 THEN 'smb'
    ELSE 'enterprise'
  END AS segment,
  (ARRAY['organic', 'paid_search', 'referral', 'partner', 'outbound'])[(customer_id % 5)::int + 1] AS acquisition_channel,
  customer_id % 5 <> 0 AS marketing_opt_in,
  CASE
    WHEN customer_id % 100 < 45 THEN 'none'
    WHEN customer_id % 100 < 70 THEN 'bronze'
    WHEN customer_id % 100 < 87 THEN 'silver'
    WHEN customer_id % 100 < 97 THEN 'gold'
    ELSE 'platinum'
  END AS loyalty_tier,
  ((customer_id * 7919) % 50000000)::bigint AS lifetime_value_cents,
  (50000 + (customer_id * 3571) % 4950000)::bigint AS credit_limit_cents,
  CASE
    WHEN customer_id % 100 < 92 THEN 'active'
    WHEN customer_id % 100 < 96 THEN 'dormant'
    WHEN customer_id % 100 < 99 THEN 'suspended'
    ELSE 'closed'
  END AS account_status,
  customer_id % 100 < 92 AS is_active,
  (ARRAY['web', 'ios', 'android', 'sales', 'partner_import'])[(customer_id % 5)::int + 1] AS signup_source,
  CASE WHEN customer_id % 4 = 0 THEN 'REF-' || upper(substr(digest, 1, 8)) END AS referral_code,
  CASE
    WHEN customer_id % 1000 = 0 THEN 'critical'
    WHEN customer_id % 50 = 0 THEN 'elevated'
    ELSE 'normal'
  END AS support_priority,
  created_at,
  updated_at,
  updated_at + ((customer_id % 30)::int * INTERVAL '1 day') AS last_login_at,
  (1 + customer_id % 12)::int AS row_version,
  (ARRAY['commerce_web', 'mobile_app', 'crm_import'])[(customer_id % 3)::int + 1] AS source_system
FROM shaped;

COMMIT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'bruin_ingestr.customers'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE bruin_ingestr.customers
      ADD CONSTRAINT customers_pkey PRIMARY KEY (customer_id);
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS customers_external_customer_id_uidx
  ON bruin_ingestr.customers (external_customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS customers_email_uidx
  ON bruin_ingestr.customers (email);
