CREATE TABLE public.orders (
  id integer PRIMARY KEY,
  order_date date NOT NULL,
  region text NOT NULL,
  amount numeric(12, 2) NOT NULL
);

INSERT INTO public.orders (id, order_date, region, amount) VALUES
  (1, '2025-01-01', 'North', 120.00),
  (2, '2025-01-01', 'South', 85.00),
  (3, '2025-01-02', 'North', 210.00),
  (4, '2025-01-02', 'West', 160.00),
  (5, '2025-01-03', 'South', 95.00),
  (6, '2025-01-03', 'West', 190.00);
