UPDATE public.customers
SET plan = 'enterprise', updated_at = '2025-01-02 10:00:00'
WHERE id = 2;

INSERT INTO public.customers (id, email, plan, updated_at) VALUES
  (4, 'margaret@example.test', 'team', '2025-01-02 10:05:00');
