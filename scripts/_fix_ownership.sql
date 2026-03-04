-- Fix table ownership and create indexes
-- Run as postgres superuser:
--   psql -U postgres -d datachat_db -f scripts/_fix_ownership.sql

ALTER TABLE public.orders OWNER TO datachat_user;
ALTER SEQUENCE public.orders_row_id_seq OWNER TO datachat_user;

CREATE INDEX IF NOT EXISTS idx_orders_order_date ON public.orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_category ON public.orders(category);
CREATE INDEX IF NOT EXISTS idx_orders_sub_category ON public.orders(sub_category);
CREATE INDEX IF NOT EXISTS idx_orders_region ON public.orders(region);
CREATE INDEX IF NOT EXISTS idx_orders_state ON public.orders(state);
CREATE INDEX IF NOT EXISTS idx_orders_segment ON public.orders(segment);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON public.orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_product_id ON public.orders(product_id);

SELECT 'Ownership transferred and indexes created' AS status;
