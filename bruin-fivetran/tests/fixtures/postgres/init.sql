CREATE SCHEMA comparison;

CREATE TABLE public.orders (
  order_id bigint PRIMARY KEY,
  customer_email text NOT NULL,
  total_cents integer NOT NULL,
  updated_at timestamp NOT NULL,
  legacy_note text
);

INSERT INTO public.orders (order_id, customer_email, total_cents, updated_at, legacy_note) VALUES
  (1001, 'ada@example.test', 1299, '2025-01-01 09:00:00', 'excluded-by-fivetran-selection'),
  (1002, 'grace@example.test', 4599, '2025-01-01 10:15:00', 'excluded-by-fivetran-selection'),
  (1003, 'lin@example.test', 2599, '2025-01-02 08:30:00', 'excluded-by-fivetran-selection');

-- A common representation for the native Bruin data-diff gate. It excludes
-- the Fivetran-disabled column, as the generated target does.
CREATE TABLE comparison.v0_orders AS
SELECT order_id, customer_email, total_cents, updated_at
FROM public.orders;
