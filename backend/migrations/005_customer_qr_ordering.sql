ALTER TABLE table_sessions ADD COLUMN qr_token_hash TEXT;
ALTER TABLE table_sessions ADD COLUMN qr_token_issued_at TEXT;
ALTER TABLE restaurant_orders ADD COLUMN client_idempotency_key TEXT;
ALTER TABLE restaurant_orders ADD COLUMN idempotency_fingerprint TEXT;
CREATE UNIQUE INDEX table_session_qr_token_hash ON table_sessions(qr_token_hash) WHERE qr_token_hash IS NOT NULL;
CREATE UNIQUE INDEX customer_order_idempotency ON restaurant_orders(session_id, client_idempotency_key) WHERE client_idempotency_key IS NOT NULL;
