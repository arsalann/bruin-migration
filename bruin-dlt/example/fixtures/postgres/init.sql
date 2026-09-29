-- Source schema for the dlt-to-Bruin regression fixture.
-- Rows are inserted separately by source/seed_postgres.py so container startup
-- stays fast and reseeding stays idempotent.

CREATE TABLE IF NOT EXISTS public.customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    plan TEXT NOT NULL,
    country TEXT NOT NULL,
    signup_date DATE NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS public.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    amount_cents BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS public.order_events (
    event_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS orders_updated_at_idx ON public.orders (updated_at);
CREATE INDEX IF NOT EXISTS order_events_event_ts_idx ON public.order_events (event_ts);
