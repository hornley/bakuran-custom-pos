from datetime import date, timedelta
from decimal import Decimal

from app import db
from app.tax import effective_rule


def start_order(client, item_id=1, quantity=1):
    created = client.post("/api/counter/orders")
    assert created.status_code == 200
    order_id = created.json()["order"]["id"]
    added = client.post(
        f"/api/orders/{order_id}/lines",
        json={"menu_item_id": item_id, "quantity": quantity},
    )
    assert added.status_code == 200
    return order_id


def configure(client, **overrides):
    payload = {
        "name": "VAT",
        "rate": "10",
        "policy": "exclusive",
        "effective_from": "2020-01-01",
    }
    payload.update(overrides)
    return client.post("/api/tax/configuration", json=payload)


def confirm(client, order_id):
    return client.post(f"/api/orders/{order_id}/confirm", json={"customer_name": "Mika"})


def test_configured_exclusive_tax_is_snapshotted_on_confirmation(client):
    configured = configure(client)
    assert configured.status_code == 201

    order_id = start_order(client)
    confirmed = confirm(client, order_id)

    assert confirmed.status_code == 200
    order = confirmed.json()["order"]
    assert Decimal(str(order["taxable_subtotal"])) == Decimal("18.00")
    assert Decimal(str(order["tax_amount"])) == Decimal("1.80")
    assert Decimal(str(order["total"])) == Decimal("19.80")
    assert order["tax_policy"] == "exclusive"
    assert order["tax_rule_id"] == configured.json()["id"]
    assert order["tax_snapshot_at"]

    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tax_rules").fetchone()[0] == 1


def test_no_rule_preserves_zero_tax_total(client):
    order_id = start_order(client)
    confirmed = confirm(client, order_id)
    order = confirmed.json()["order"]
    assert confirmed.status_code == 200
    assert order["tax_policy"] == "none"
    assert Decimal(str(order["tax_amount"])) == Decimal("0.00")
    assert Decimal(str(order["total"])) == Decimal("18.00")
    assert order["tax_rate"] == "0.00"


def test_zero_tax_breakdown_uses_stable_decimal_strings(client):
    order_id = start_order(client)
    confirmed = confirm(client, order_id)
    assert confirmed.json()["tax"] == {
        "rule_id": None,
        "name": "",
        "rate": "0.00",
        "policy": "none",
        "taxable_subtotal": "18.00",
        "tax_amount": "0.00",
        "total": "18.00",
        "snapshot_at": confirmed.json()["order"]["tax_snapshot_at"],
    }


def test_inclusive_tax_uses_tax_inclusive_total(client):
    assert configure(client, policy="inclusive").status_code == 201
    order_id = start_order(client)
    order = confirm(client, order_id).json()["order"]
    assert Decimal(str(order["taxable_subtotal"])) == Decimal("16.36")
    assert Decimal(str(order["tax_amount"])) == Decimal("1.64")
    assert Decimal(str(order["total"])) == Decimal("18.00")


def test_payment_requires_tax_inclusive_order_total(client):
    assert configure(client).status_code == 201
    order_id = start_order(client)
    confirm(client, order_id)
    assert client.post(f"/api/orders/{order_id}/pay", json={"amount": "18.00", "method": "cash"}).status_code == 409
    paid = client.post(f"/api/orders/{order_id}/pay", json={"amount": "19.80", "method": "cash"})
    assert paid.status_code == 200
    assert Decimal(str(paid.json()["payment"]["amount"])) == Decimal("19.80")


def test_rule_validation_and_overlap_are_rejected(client):
    assert configure(client, rate="100.00001").status_code == 422
    assert configure(client, effective_from="2020-01-01", effective_to="2019-12-31").status_code == 422
    assert configure(client).status_code == 201
    assert configure(client, effective_from="2021-01-01").status_code == 409
    assert configure(client, rate="NaN").status_code == 422
    assert configure(client, rate="1e1000").status_code == 422
    assert configure(client, rate="0.12345").status_code == 422
    assert configure(client, effective_from="not-a-date").status_code == 422
    assert configure(client, name="   ").status_code == 422


def test_adjacent_tax_periods_are_allowed_but_shared_dates_overlap(client):
    assert configure(client, effective_from="2020-01-01", effective_to="2020-12-31").status_code == 201
    assert configure(client, name="Future VAT", effective_from="2021-01-01").status_code == 201
    assert configure(client, name="Overlap", effective_from="2020-12-31", effective_to="2021-01-01").status_code == 409


def test_effective_rule_selection_is_server_side_and_date_aware(client):
    first = configure(client, effective_from="2020-01-01", effective_to="2020-12-31")
    second = configure(client, name="Future VAT", rate="20", effective_from="2021-01-01")
    assert first.status_code == second.status_code == 201
    with db.connect() as connection:
        assert effective_rule(connection, "2020-06-01")["id"] == first.json()["id"]
        assert effective_rule(connection, "2021-06-01")["id"] == second.json()["id"]
        assert effective_rule(connection, "2019-12-31") is None


def test_tax_snapshot_and_receipt_are_immutable_and_idempotent(client):
    assert configure(client).status_code == 201
    order_id = start_order(client)
    first = confirm(client, order_id).json()
    assert client.post(f"/api/orders/{order_id}/pay", json={"amount": "19.80", "method": "cash"}).status_code == 200
    ticket = client.get(f"/api/orders/{order_id}").json()["ticket"]["id"]
    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket}/{action}").status_code == 200
    first_close = client.post(f"/api/orders/{order_id}/close")
    second_close = client.post(f"/api/orders/{order_id}/close")
    assert first_close.status_code == second_close.status_code == 200
    assert first_close.json()["receipt"] == second_close.json()["receipt"]
    receipt = first_close.json()["receipt"]
    assert Decimal(str(receipt["total"])) == Decimal("19.80")
    assert receipt["tax_rule_id"] == first["order"]["tax_rule_id"]
    assert receipt["tax_name"] == first["order"]["tax_name"]
    assert receipt["tax_rate"] == first["order"]["tax_rate"]
    assert receipt["tax_policy"] == first["order"]["tax_policy"]
    assert receipt["taxable_subtotal"] == "18.00"
    assert receipt["tax_amount"] == "1.80"
    assert receipt["tax_snapshot_at"] == first["order"]["tax_snapshot_at"]
    assert receipt["tax_effective_from"] == first["order"]["tax_effective_from"]
    assert receipt["tax_effective_to"] == first["order"]["tax_effective_to"]
    assert first_close.json()["order"]["tax_amount"] == first["order"]["tax_amount"]
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM receipts WHERE order_id=?", (order_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM payments WHERE order_id=?", (order_id,)).fetchone()[0] == 1
    listed_receipt = client.get("/api/receipts").json()[0]
    assert listed_receipt["tax_rule_id"] == receipt["tax_rule_id"]
    assert listed_receipt["tax_amount"] == receipt["tax_amount"]
    assert listed_receipt["tax_snapshot_at"] == receipt["tax_snapshot_at"]


def test_tax_configuration_is_audited(client):
    assert configure(client).status_code == 201
    with db.connect() as connection:
        event = connection.execute("SELECT event_type, detail FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
    assert event["event_type"] == "tax.rule_created"
    assert "tax_rule_id=1" in event["detail"]


def test_historical_order_snapshot_survives_a_later_effective_rule(client):
    today = date.today()
    assert configure(client, effective_from=today.isoformat(), effective_to=today.isoformat()).status_code == 201
    order_id = start_order(client)
    confirmed = confirm(client, order_id).json()
    tomorrow = today + timedelta(days=1)
    later = configure(
        client,
        name="Future VAT",
        rate="20",
        effective_from=tomorrow.isoformat(),
    )
    assert later.status_code == 201

    loaded = client.get(f"/api/orders/{order_id}").json()
    assert loaded["order"]["tax_rule_id"] == confirmed["order"]["tax_rule_id"]
    assert loaded["order"]["tax_amount"] == confirmed["order"]["tax_amount"]
    assert loaded["tax"]["total"] == confirmed["tax"]["total"]


def test_reset_recreates_tax_and_audit_tables_without_using_operational_database(client):
    assert db.DATABASE_PATH.name == "app.db"
    assert "backend/data" not in str(db.DATABASE_PATH)
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tax_rules").fetchone()[0] == 0
        assert connection.execute("SELECT 1 FROM audit_events").fetchone() is None
    db.reset()
    with db.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"tax_rules", "audit_events", "receipts"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1


def test_deterministic_seed_keeps_legacy_receipt_as_a_zero_tax_snapshot(client):
    with db.connect() as connection:
        receipt = connection.execute("SELECT * FROM receipts WHERE id=1").fetchone()
        assert receipt["tax_policy"] == "none"
        assert receipt["tax_rate"] == "0.00"
        assert receipt["taxable_subtotal"] == "23.00"
        assert receipt["tax_amount"] == "0.00"
        assert receipt["tax_snapshot_at"] == "2026-01-01T00:00:00Z"


def test_health_requires_tax_schema_to_be_ready(client):
    with db.connect() as connection:
        connection.execute("DROP TABLE tax_rules")
    assert client.get("/api/health").status_code == 503


def test_migrating_a_pre_tax_database_backfills_completed_zero_tax_history(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "pre-tax.db")
    with db.connect() as connection:
        connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for path in db.MIGRATIONS[:3]:
            for statement in db._migration_statements(path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (int(path.name[:3]), db.SEED_TIMESTAMP))
        connection.execute("INSERT INTO dining_areas VALUES (1,'MAIN','Main Dining Room')")
        connection.execute("INSERT INTO dining_tables VALUES (1,1,'T01','Table 1',2,'available')")
        connection.execute("INSERT INTO table_sessions VALUES (1,'SES-LEGACY',1,'closed',?,?)", (db.SEED_TIMESTAMP, db.SEED_TIMESTAMP))
        connection.execute("INSERT INTO restaurant_orders(id,order_number,session_id,status,subtotal,total,created_at,sent_at,served_at,paid_at,closed_at,customer_name,order_channel) VALUES (1,'ORD-LEGACY',1,'closed',12.34,12.34,?,?,?,?,?,'Legacy','table')", (db.SEED_TIMESTAMP,db.SEED_TIMESTAMP,db.SEED_TIMESTAMP,db.SEED_TIMESTAMP,db.SEED_TIMESTAMP))
        connection.execute("INSERT INTO receipts(id,receipt_number,order_id,total,issued_at) VALUES (1,'REC-LEGACY',1,12.34,?)", (db.SEED_TIMESTAMP,))
    db.initialize()
    with db.connect() as connection:
        order = connection.execute("SELECT tax_policy, tax_rate, taxable_subtotal, tax_amount, tax_snapshot_at FROM restaurant_orders WHERE id=1").fetchone()
        receipt = connection.execute("SELECT tax_policy, tax_rate, taxable_subtotal, tax_amount, tax_snapshot_at FROM receipts WHERE id=1").fetchone()
    assert tuple(order) == ("none", "0.00", "12.34", "0.00", db.SEED_TIMESTAMP)
    assert tuple(receipt) == ("none", "0.00", "12.34", "0.00", db.SEED_TIMESTAMP)


def test_tax_configuration_is_available_without_auth_in_default_local_deployment(client):
    response = configure(client)
    assert response.status_code == 201
    assert client.get("/api/auth/session").json() == {"authenticated": False, "auth_enabled": False}


def test_tax_configuration_rejects_payment_amount_mismatch_after_idempotent_paid_retry(client):
    assert configure(client).status_code == 201
    order_id = start_order(client)
    assert confirm(client, order_id).status_code == 200
    assert client.post(f"/api/orders/{order_id}/pay", json={"amount": "19.80", "method": "cash"}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/pay", json={"amount": "18.00", "method": "cash"}).status_code == 409
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM payments WHERE order_id=?", (order_id,)).fetchone()[0] == 1


def test_payment_amount_with_more_than_two_decimal_places_is_rejected_without_mutation(client):
    order_id = start_order(client)
    assert confirm(client, order_id).status_code == 200
    response = client.post(f"/api/orders/{order_id}/pay", json={"amount": "18.001", "method": "cash"})
    assert response.status_code == 422
    loaded = client.get(f"/api/orders/{order_id}").json()
    assert loaded["order"]["status"] == "awaiting_payment"
    assert loaded["payment"] is None


def test_payment_float_payload_is_rejected_to_keep_money_decimal_only(client):
    order_id = start_order(client)
    assert confirm(client, order_id).status_code == 200
    response = client.post(f"/api/orders/{order_id}/pay", json={"amount": 18.0, "method": "cash"})
    assert response.status_code == 422


def test_legacy_paid_order_without_tax_snapshot_keeps_zero_tax_when_rule_is_added_later(client):
    order_id = start_order(client)
    with db.connect() as connection:
        order = connection.execute("SELECT total, session_id FROM restaurant_orders WHERE id=?", (order_id,)).fetchone()
        connection.execute(
            "UPDATE restaurant_orders SET status='paid', paid_at=? WHERE id=?",
            ("2026-01-01T00:00:00Z", order_id),
        )
        connection.execute(
            "INSERT INTO payments(id,payment_number,order_id,amount,method,status,paid_at) VALUES(?,?,?,?,?,'paid',?)",
            (2, "PAY-0002", order_id, order["total"], "cash", "2026-01-01T00:00:00Z"),
        )
    assert configure(client, effective_from=date.today().isoformat()).status_code == 201
    closed = client.post(f"/api/orders/{order_id}/close")
    assert closed.status_code == 200
    assert closed.json()["receipt"]["tax_amount"] == "0.00"
