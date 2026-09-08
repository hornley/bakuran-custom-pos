CREATE TABLE tax_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    rate TEXT NOT NULL,
    policy TEXT NOT NULL CHECK(policy IN ('exclusive','inclusive')),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    CHECK(effective_to IS NULL OR effective_to >= effective_from)
);
CREATE INDEX idx_tax_rules_effective ON tax_rules(effective_from, effective_to);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at);

ALTER TABLE restaurant_orders ADD COLUMN tax_rule_id INTEGER;
ALTER TABLE restaurant_orders ADD COLUMN tax_name TEXT NOT NULL DEFAULT '';
ALTER TABLE restaurant_orders ADD COLUMN tax_rate TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE restaurant_orders ADD COLUMN tax_policy TEXT NOT NULL DEFAULT 'none';
ALTER TABLE restaurant_orders ADD COLUMN taxable_subtotal TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE restaurant_orders ADD COLUMN tax_amount TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE restaurant_orders ADD COLUMN tax_snapshot_at TEXT;
ALTER TABLE restaurant_orders ADD COLUMN tax_effective_from TEXT;
ALTER TABLE restaurant_orders ADD COLUMN tax_effective_to TEXT;

ALTER TABLE receipts ADD COLUMN tax_rule_id INTEGER;
ALTER TABLE receipts ADD COLUMN tax_name TEXT NOT NULL DEFAULT '';
ALTER TABLE receipts ADD COLUMN tax_rate TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE receipts ADD COLUMN tax_policy TEXT NOT NULL DEFAULT 'none';
ALTER TABLE receipts ADD COLUMN taxable_subtotal TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE receipts ADD COLUMN tax_amount TEXT NOT NULL DEFAULT '0.00';
ALTER TABLE receipts ADD COLUMN tax_snapshot_at TEXT;
ALTER TABLE receipts ADD COLUMN tax_effective_from TEXT;
ALTER TABLE receipts ADD COLUMN tax_effective_to TEXT;

-- Preserve pre-tax completed records as immutable zero-tax history. Open
-- orders remain unsnapshotted so confirmation can select the current rule.
UPDATE restaurant_orders
SET tax_rate = '0.00',
    tax_policy = 'none',
    taxable_subtotal = printf('%.2f', subtotal),
    tax_amount = '0.00',
    tax_snapshot_at = COALESCE(closed_at, paid_at, created_at)
WHERE tax_snapshot_at IS NULL AND status <> 'open';

UPDATE receipts
SET tax_rate = '0.00',
    tax_policy = 'none',
    taxable_subtotal = printf('%.2f', total),
    tax_amount = '0.00',
    tax_snapshot_at = issued_at
WHERE tax_snapshot_at IS NULL;
