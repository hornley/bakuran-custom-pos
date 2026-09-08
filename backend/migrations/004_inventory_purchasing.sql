CREATE TABLE warehouses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL
);

INSERT INTO warehouses(id, code, name, active, created_at)
VALUES (1, 'MAIN', 'Main Warehouse', 1, '2026-01-01T00:00:00Z');

CREATE TABLE inventory_new (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES menu_items(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    on_hand INTEGER NOT NULL CHECK(on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0 AND reserved <= on_hand),
    updated_at TEXT NOT NULL,
    reorder_level INTEGER NOT NULL DEFAULT 5 CHECK(reorder_level >= 0),
    UNIQUE(product_id, warehouse_id)
);
INSERT INTO inventory_new(id, product_id, warehouse_id, on_hand, reserved, updated_at, reorder_level)
SELECT MIN(id),
       product_id,
       1,
       SUM(on_hand),
       CASE WHEN SUM(reserved) > SUM(on_hand) THEN SUM(on_hand) ELSE SUM(reserved) END,
       MAX(updated_at),
       5
FROM inventory
GROUP BY product_id;
DROP TABLE inventory;
ALTER TABLE inventory_new RENAME TO inventory;
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id, product_id);

CREATE TABLE stock_movements_new (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES menu_items(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    movement_type TEXT NOT NULL CHECK(movement_type IN ('receipt','sale','adjustment')),
    quantity INTEGER NOT NULL CHECK(quantity != 0),
    reference TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT,
    created_at TEXT NOT NULL
);
INSERT INTO stock_movements_new(id, product_id, warehouse_id, movement_type, quantity, reference, reason, idempotency_key, created_at)
SELECT id, product_id, 1, movement_type, quantity, reference, '', NULL, created_at
FROM stock_movements;
DROP TABLE stock_movements;
ALTER TABLE stock_movements_new RENAME TO stock_movements;
CREATE INDEX idx_stock_movements_product_warehouse ON stock_movements(product_id, warehouse_id, id);

CREATE TABLE idempotency_keys (
    key TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_idempotency_operation ON idempotency_keys(operation);

CREATE TABLE IF NOT EXISTS auth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS auth_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS auth_user_roles (
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES auth_roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES auth_users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_audit_events_created ON audit_events(created_at);

CREATE TABLE purchase_lines_backup (
    id INTEGER PRIMARY KEY,
    purchase_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER NOT NULL DEFAULT 1,
    quantity INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    received_quantity INTEGER NOT NULL DEFAULT 0
);
INSERT INTO purchase_lines_backup(id, purchase_id, product_id, warehouse_id, quantity, unit_cost, received_quantity)
SELECT id, purchase_id, product_id, 1, quantity, unit_cost, 0
FROM purchase_lines;
DROP TABLE purchase_lines;

CREATE TABLE purchases_new (
    id INTEGER PRIMARY KEY,
    purchase_number TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    status TEXT NOT NULL CHECK(status IN ('draft','ordered','partially_received','received','closed')),
    total REAL NOT NULL DEFAULT 0 CHECK(total >= 0),
    created_at TEXT NOT NULL,
    ordered_at TEXT,
    received_at TEXT,
    closed_at TEXT
);
INSERT INTO purchases_new(id, purchase_number, supplier_id, status, total, created_at, ordered_at, received_at, closed_at)
SELECT id,
       purchase_number,
       supplier_id,
       status,
       total,
       created_at,
       CASE WHEN status IN ('ordered','partially_received','received','closed') THEN created_at ELSE NULL END,
       received_at,
       NULL
FROM purchases;
DROP TABLE purchases;
ALTER TABLE purchases_new RENAME TO purchases;

CREATE TABLE purchase_lines (
    id INTEGER PRIMARY KEY,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES menu_items(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
    received_quantity INTEGER NOT NULL DEFAULT 0 CHECK(received_quantity >= 0),
    UNIQUE(purchase_id, product_id, warehouse_id)
);
INSERT INTO purchase_lines(id, purchase_id, product_id, warehouse_id, quantity, unit_cost, received_quantity)
SELECT b.id,
       b.purchase_id,
       b.product_id,
       b.warehouse_id,
       b.quantity,
       b.unit_cost,
       CASE WHEN p.status IN ('received', 'closed') THEN b.quantity ELSE b.received_quantity END
FROM purchase_lines_backup b
JOIN purchases p ON p.id = b.purchase_id;
DROP TABLE purchase_lines_backup;
CREATE INDEX idx_purchase_lines_purchase ON purchase_lines(purchase_id);
