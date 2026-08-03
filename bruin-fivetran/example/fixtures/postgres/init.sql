CREATE TABLE public.customers (
  id integer PRIMARY KEY,
  email text NOT NULL,
  plan text NOT NULL,
  updated_at timestamp NOT NULL
);

INSERT INTO public.customers (id, email, plan, updated_at) VALUES
  (1, 'ada@example.test', 'starter', '2025-01-01 09:00:00'),
  (2, 'lin@example.test', 'team', '2025-01-01 09:05:00'),
  (3, 'grace@example.test', 'enterprise', '2025-01-01 09:10:00');
