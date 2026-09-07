ALTER TABLE restaurant_orders ADD COLUMN customer_name TEXT NOT NULL DEFAULT '';
ALTER TABLE restaurant_orders ADD COLUMN order_channel TEXT NOT NULL DEFAULT 'table';
