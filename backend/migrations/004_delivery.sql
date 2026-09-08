CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at);

CREATE TABLE IF NOT EXISTS delivery_drivers (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_delivery_drivers_active ON delivery_drivers(active, name);

CREATE TABLE IF NOT EXISTS delivery_orders (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES restaurant_orders(id) ON DELETE CASCADE,
    address TEXT NOT NULL CHECK(length(trim(address)) >= 5),
    contact TEXT NOT NULL CHECK(length(trim(contact)) >= 7),
    contact_name TEXT NOT NULL DEFAULT '' CHECK(length(trim(contact_name)) <= 80),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'assigned', 'out_for_delivery', 'delivered', 'failed', 'cancelled')),
    driver_id INTEGER REFERENCES delivery_drivers(id),
    failure_reason TEXT,
    cancellation_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    assigned_at TEXT,
    out_for_delivery_at TEXT,
    delivered_at TEXT,
    failed_at TEXT,
    cancelled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_delivery_orders_status ON delivery_orders(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_delivery_orders_driver ON delivery_orders(driver_id, status);

CREATE TABLE IF NOT EXISTS delivery_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER NOT NULL REFERENCES delivery_orders(id) ON DELETE CASCADE,
    driver_id INTEGER NOT NULL REFERENCES delivery_drivers(id),
    status TEXT NOT NULL CHECK(status IN ('active', 'reassigned', 'completed', 'failed', 'cancelled')),
    assigned_at TEXT NOT NULL,
    unassigned_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_delivery_assignments_delivery ON delivery_assignments(delivery_id, id);
CREATE INDEX IF NOT EXISTS idx_delivery_assignments_active ON delivery_assignments(delivery_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_delivery_assignment
    ON delivery_assignments(delivery_id) WHERE status='active';

CREATE TABLE IF NOT EXISTS delivery_idempotency_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER NOT NULL REFERENCES delivery_orders(id) ON DELETE CASCADE,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(delivery_id, operation, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_delivery_idempotency_delivery ON delivery_idempotency_keys(delivery_id, created_at);
