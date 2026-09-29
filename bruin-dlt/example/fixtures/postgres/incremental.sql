-- Deterministic pass-2 change set, applied between the initial and incremental
-- load passes. Every changed or inserted row is stamped inside
-- [2025-04-01 06:00:00, 2025-04-01 09:00:00] so the incremental window
-- [2025-04-01, 2025-04-02] captures exactly this change set and nothing else.
-- Re-running this file produces the same source state.

UPDATE public.orders
SET status = 'shipped',
    updated_at = TIMESTAMP '2025-04-01 06:00:00'
WHERE order_id <= 1000;

INSERT INTO public.orders (order_id, customer_id, status, amount_cents, created_at, updated_at)
SELECT id,
       ((id - 1) % 200000) + 1,
       'pending',
       1000 + (id % 90000),
       TIMESTAMP '2025-04-01 07:00:00',
       TIMESTAMP '2025-04-01 07:00:00'
FROM generate_series(300001, 300500) AS id
ON CONFLICT (order_id) DO UPDATE
SET customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    amount_cents = EXCLUDED.amount_cents,
    created_at = EXCLUDED.created_at,
    updated_at = EXCLUDED.updated_at;

INSERT INTO public.order_events (event_id, order_id, event_type, event_ts)
SELECT id,
       ((id - 1) % 300000) + 1,
       'fulfilled',
       TIMESTAMP '2025-04-01 08:00:00'
FROM generate_series(500001, 501000) AS id
ON CONFLICT (event_id) DO NOTHING;

UPDATE public.customers
SET plan = 'enterprise',
    updated_at = TIMESTAMP '2025-04-01 09:00:00'
WHERE customer_id <= 200;
