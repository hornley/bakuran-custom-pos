CREATE TABLE promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(length(trim(code)) BETWEEN 1 AND 40),
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 120),
    discount_type TEXT NOT NULL CHECK(discount_type IN ('fixed', 'percentage')),
    value TEXT NOT NULL,
    starts_on TEXT NOT NULL,
    ends_on TEXT,
    usage_limit INTEGER CHECK(usage_limit IS NULL OR (usage_limit > 0 AND usage_limit <= 1000000000)),
    usage_count INTEGER NOT NULL DEFAULT 0 CHECK(usage_count >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER REFERENCES auth_users(id) ON DELETE SET NULL,
    CHECK(ends_on IS NULL OR ends_on >= starts_on)
);
CREATE INDEX idx_promotions_status ON promotions(active, starts_on, ends_on);

CREATE TABLE applied_promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES restaurant_orders(id) ON DELETE CASCADE,
    promotion_id INTEGER NOT NULL REFERENCES promotions(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    discount_type TEXT NOT NULL CHECK(discount_type IN ('fixed', 'percentage')),
    value TEXT NOT NULL,
    discount_amount TEXT NOT NULL,
    original_subtotal TEXT NOT NULL,
    discounted_subtotal TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    applied_by_user_id INTEGER REFERENCES auth_users(id) ON DELETE SET NULL
);
CREATE INDEX idx_applied_promotions_promotion ON applied_promotions(promotion_id);
CREATE INDEX idx_applied_promotions_order ON applied_promotions(order_id);

ALTER TABLE restaurant_orders ADD COLUMN original_subtotal TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE restaurant_orders ADD COLUMN discount_amount TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE restaurant_orders ADD COLUMN discounted_subtotal TEXT NOT NULL DEFAULT '0.00';

ALTER TABLE receipts ADD COLUMN promotion_id INTEGER;
ALTER TABLE receipts ADD COLUMN promotion_code TEXT;
ALTER TABLE receipts ADD COLUMN promotion_name TEXT;
ALTER TABLE receipts ADD COLUMN promotion_discount_type TEXT;
ALTER TABLE receipts ADD COLUMN promotion_value TEXT;
ALTER TABLE receipts ADD COLUMN promotion_discount_amount TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE receipts ADD COLUMN promotion_original_subtotal TEXT;
ALTER TABLE receipts ADD COLUMN promotion_discounted_subtotal TEXT;

UPDATE restaurant_orders
SET original_subtotal = printf('%.2f', subtotal),
    discounted_subtotal = printf('%.2f', subtotal),
    discount_amount = '0.00'
WHERE original_subtotal = '0.00' AND subtotal <> 0;
