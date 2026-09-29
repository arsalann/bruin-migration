-- Deterministic ~1M row seed for the dlt-to-Bruin regression fixture.
-- Row counts: customers 200,000 + orders 300,000 + order_events 500,000 = 1,000,000.
-- All values are pure functions of the generated key, so reseeding is idempotent.
-- All initial timestamps fall inside [2025-01-01 00:00:00, 2025-03-30 23:59:59].

TRUNCATE public.customers, public.orders, public.order_events;

INSERT INTO public.customers (customer_id, email, plan, country, signup_date, updated_at)
SELECT id,
       'customer' || id || '@example.test',
       (ARRAY['starter', 'team', 'enterprise'])[(id % 3) + 1],
       (ARRAY['US', 'DE', 'GB', 'JP'])[(id % 4) + 1],
       DATE '2024-01-01' + (id % 365),
       TIMESTAMP '2025-01-01 00:00:00'
         + ((id % 30) * INTERVAL '1 day')
         + ((id % 86400) * INTERVAL '1 second')
FROM generate_series(1, 200000) AS id;

INSERT INTO public.orders (order_id, customer_id, status, amount_cents, created_at, updated_at)
SELECT id,
       ((id - 1) % 200000) + 1,
       (ARRAY['pending', 'paid', 'shipped', 'cancelled'])[(id % 4) + 1],
       1000 + (id % 90000),
       TIMESTAMP '2025-01-01 00:00:00'
         + ((id % 88) * INTERVAL '1 day')
         + ((id % 86400) * INTERVAL '1 second'),
       TIMESTAMP '2025-01-01 00:00:00'
         + ((id % 88) * INTERVAL '1 day')
         + ((id % 86400) * INTERVAL '1 second')
FROM generate_series(1, 300000) AS id;

INSERT INTO public.order_events (event_id, order_id, event_type, event_ts)
SELECT id,
       ((id - 1) % 300000) + 1,
       (ARRAY['created', 'payment_authorized', 'fulfilled', 'refunded'])[(id % 4) + 1],
       TIMESTAMP '2025-01-01 00:00:00'
         + ((id % 88) * INTERVAL '1 day')
         + ((id % 86400) * INTERVAL '1 second')
FROM generate_series(1, 500000) AS id;

ANALYZE public.customers;
ANALYZE public.orders;
ANALYZE public.order_events;
