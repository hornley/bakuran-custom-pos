import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import app


def stock(client, product_id=1, warehouse_id=1):
    response = client.get(f"/api/inventory?warehouse_id={warehouse_id}")
    assert response.status_code == 200
    return next(row for row in response.json()["products"] if row["product_id"] == product_id)


def create_purchase(client, *, warehouse_id=1, product_ids=(1,), quantity=10):
    response = client.post("/api/purchases", json={"supplier_id": 1})
    assert response.status_code == 200
    pid = response.json()["id"]
    for product_id in product_ids:
        line = client.post(
            f"/api/purchases/{pid}/lines",
            json={"product_id": product_id, "warehouse_id": warehouse_id, "quantity": quantity, "unit_cost": 8},
        )
        assert line.status_code == 200
    return pid


def test_inventory_is_warehouse_aware_and_adjustments_require_reason(client):
    assert client.get("/api/warehouses").json()[0]["code"] == "MAIN"
    created = client.post("/api/warehouses", json={"code": "COLD", "name": "Cold Store"})
    assert created.status_code == 200
    warehouse_id = created.json()["id"]

    assert client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "warehouse_id": warehouse_id, "quantity": 4},
    ).status_code == 422

    adjusted = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "warehouse_id": warehouse_id, "quantity": 4, "reason": "Cycle count"},
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["product"]["on_hand"] == 4
    assert adjusted.json()["product"]["warehouse_id"] == warehouse_id

    invalid = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "warehouse_id": warehouse_id, "quantity": -5, "reason": "Bad count"},
    )
    assert invalid.status_code == 409
    assert stock(client, warehouse_id=warehouse_id)["on_hand"] == 4


def test_stock_adjustment_cannot_cross_reserved_or_non_negative_bounds(client):
    with db.connect() as connection:
        connection.execute("UPDATE inventory SET reserved=15 WHERE product_id=1 AND warehouse_id=1")
    rejected = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "quantity": -6, "reason": "Damaged stock"},
    )
    assert rejected.status_code == 409
    assert stock(client)["on_hand"] == 20

    negative = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "quantity": -21, "reason": "Impossible count"},
    )
    assert negative.status_code == 409
    assert stock(client)["on_hand"] == 20


def test_invalid_active_references_are_rejected(client):
    assert client.get("/api/inventory?warehouse_id=999").status_code == 404
    assert client.post(
        "/api/stock/adjustment",
        json={"product_id": 999, "quantity": 1, "reason": "Unknown product"},
    ).status_code == 404
    pid = create_purchase(client)
    assert client.post(
        f"/api/purchases/{pid}/lines",
        json={"product_id": 1, "warehouse_id": 999, "quantity": 1, "unit_cost": 1},
    ).status_code == 404

    with db.connect() as connection:
        connection.execute("UPDATE menu_items SET active=0 WHERE id=2")
        connection.execute("UPDATE warehouses SET active=0 WHERE id=1")
    assert client.get("/api/inventory?warehouse_id=1").status_code == 404
    assert client.post(
        "/api/stock/adjustment",
        json={"product_id": 2, "warehouse_id": 1, "quantity": 1, "reason": "Inactive"},
    ).status_code == 404


def test_low_stock_includes_reorder_visibility(client):
    updated = client.put(
        "/api/inventory/reorder-level",
        json={"product_id": 1, "warehouse_id": 1, "reorder_level": 25, "idempotency_key": "level-1"},
    )
    assert updated.status_code == 200
    response = client.get("/api/inventory/low-stock?warehouse_id=1")
    assert response.status_code == 200
    row = next(item for item in response.json() if item["product_id"] == 1)
    assert row["reorder_level"] == 25
    assert row["available"] == row["on_hand"] - row["reserved"]
    assert row["low_stock"] is True
    assert row["reorder_quantity"] == 5
    assert client.get("/api/inventory/reorder").status_code == 200


def test_reorder_level_idempotency_replays_and_rejects_conflicts(client):
    payload = {"product_id": 1, "warehouse_id": 1, "reorder_level": 25, "idempotency_key": "level-replay"}
    first = client.put("/api/inventory/reorder-level", json=payload)
    second = client.put("/api/inventory/reorder-level", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    conflict = client.put(
        "/api/inventory/reorder-level",
        json={**payload, "reorder_level": 30},
    )
    assert conflict.status_code == 409


def test_purchase_lifecycle_partial_receipt_and_close(client):
    pid = create_purchase(client)
    assert client.post(f"/api/purchases/{pid}/order").json()["status"] == "ordered"

    partial = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 4}], "idempotency_key": "receive-1"},
    )
    assert partial.status_code == 200
    assert partial.json()["purchase"]["status"] == "partially_received"
    assert partial.json()["lines"][0]["received_quantity"] == 4
    assert stock(client)["on_hand"] == 24

    final = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 6}], "idempotency_key": "receive-2"},
    )
    assert final.status_code == 200
    assert final.json()["purchase"]["status"] == "received"
    assert final.json()["lines"][0]["received_quantity"] == 10
    assert stock(client)["on_hand"] == 30

    closed = client.post(f"/api/purchases/{pid}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.post(f"/api/purchases/{pid}/close").json()["status"] == "closed"


def test_purchase_creation_and_line_idempotency_are_durable(client):
    payload = {"supplier_id": 1, "idempotency_key": "purchase-create-once"}
    first = client.post("/api/purchases", json=payload)
    second = client.post("/api/purchases", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    pid = first.json()["id"]

    line_payload = {
        "product_id": 1,
        "warehouse_id": 1,
        "quantity": 2,
        "unit_cost": 8,
        "idempotency_key": "purchase-line-once",
    }
    first_line = client.post(f"/api/purchases/{pid}/lines", json=line_payload)
    second_line = client.post(f"/api/purchases/{pid}/lines", json=line_payload)
    assert first_line.status_code == second_line.status_code == 200
    assert first_line.json() == second_line.json()
    conflict = client.post(f"/api/purchases/{pid}/lines", json={**line_payload, "quantity": 3})
    assert conflict.status_code == 409


def test_purchase_is_received_only_after_every_line_is_received(client):
    pid = create_purchase(client, product_ids=(1, 2), quantity=2)
    assert client.post(f"/api/purchases/{pid}/order").status_code == 200
    first = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 2}], "idempotency_key": "line-one"},
    )
    assert first.status_code == 200
    assert first.json()["purchase"]["status"] == "partially_received"
    assert {line["received_quantity"] for line in first.json()["lines"]} == {0, 2}
    second = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 2, "quantity": 2}], "idempotency_key": "line-two"},
    )
    assert second.status_code == 200
    assert second.json()["purchase"]["status"] == "received"


def test_legacy_receive_call_still_receives_draft_purchase(client):
    pid = create_purchase(client, quantity=3)
    response = client.post(f"/api/purchases/{pid}/receive")
    assert response.status_code == 200
    assert response.json()["status"] == "received"
    assert stock(client)["on_hand"] == 23


def test_over_receipt_rolls_back_without_authorized_override(client):
    pid = create_purchase(client)
    assert client.post(f"/api/purchases/{pid}/order").status_code == 200
    before = stock(client)["on_hand"]
    rejected = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 11}], "idempotency_key": "too-many"},
    )
    assert rejected.status_code == 409
    assert stock(client)["on_hand"] == before
    purchase = client.get("/api/purchases").json()
    assert next(row for row in purchase if row["id"] == pid)["status"] == "ordered"


def test_over_receipt_requires_a_reason_even_when_auth_is_disabled(client):
    pid = create_purchase(client)
    client.post(f"/api/purchases/{pid}/order")
    rejected = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 11}], "allow_over_receipt": True},
    )
    assert rejected.status_code == 422
    assert stock(client)["on_hand"] == 20


def test_over_receipt_override_is_explicit_and_audited(client):
    pid = create_purchase(client)
    assert client.post(f"/api/purchases/{pid}/order").status_code == 200
    response = client.post(
        f"/api/purchases/{pid}/receive",
        json={
            "lines": [{"product_id": 1, "quantity": 11}],
            "allow_over_receipt": True,
            "override_reason": "Supplier shipped an extra case",
            "idempotency_key": "override-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["purchase"]["status"] == "received"
    assert response.json()["lines"][0]["received_quantity"] == 11
    assert stock(client)["on_hand"] == 31
    audit = client.get("/api/audit-events").json()
    assert any(event["event_type"] == "purchasing.receipt" and "extra case" in event["detail"] for event in audit)


def test_receipt_and_adjustment_idempotency_do_not_double_mutate(client):
    first = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "quantity": 2, "reason": "Count", "idempotency_key": "adj-1"},
    )
    second = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "quantity": 2, "reason": "Count", "idempotency_key": "adj-1"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert stock(client)["on_hand"] == 22

    conflict = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "quantity": 3, "reason": "Different", "idempotency_key": "adj-1"},
    )
    assert conflict.status_code == 409

    pid = create_purchase(client)
    client.post(f"/api/purchases/{pid}/order")
    first = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 3}], "idempotency_key": "receipt-1"},
    )
    second = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 3}], "idempotency_key": "receipt-1"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert stock(client)["on_hand"] == 25
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM stock_movements WHERE idempotency_key='receipt-1'").fetchone()[0] == 1


def test_concurrent_receipt_retries_are_durable_and_atomic(client):
    pid = create_purchase(client, quantity=5)
    assert client.post(f"/api/purchases/{pid}/order").status_code == 200

    def receive():
        with TestClient(app) as concurrent_client:
            return concurrent_client.post(
                f"/api/purchases/{pid}/receive",
                json={"lines": [{"product_id": 1, "quantity": 5}], "idempotency_key": "parallel-receipt"},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: receive(), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert stock(client)["on_hand"] == 25
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM stock_movements WHERE idempotency_key='parallel-receipt'").fetchone()[0] == 1


def test_inventory_mutation_rolls_back_if_a_multi_line_receipt_fails(client):
    pid = create_purchase(client, product_ids=(1, 2), quantity=2)
    client.post(f"/api/purchases/{pid}/order")
    before = {product_id: stock(client, product_id)["on_hand"] for product_id in (1, 2)}
    result = client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 1}, {"product_id": 2, "quantity": 3}]},
    )
    assert result.status_code == 409
    assert {product_id: stock(client, product_id)["on_hand"] for product_id in (1, 2)} == before


def test_audit_events_capture_inventory_and_purchase_mutations(client):
    client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "quantity": 1, "reason": "Audit test", "idempotency_key": "audit-adj"},
    )
    pid = create_purchase(client)
    client.post(f"/api/purchases/{pid}/order")
    client.post(
        f"/api/purchases/{pid}/receive",
        json={"lines": [{"product_id": 1, "quantity": 1}], "idempotency_key": "audit-receipt"},
    )
    events = client.get("/api/audit-events").json()
    event_types = {event["event_type"] for event in events}
    assert "inventory.adjustment" in event_types
    assert "purchasing.created" in event_types
    assert "purchasing.line_added" in event_types
    assert "purchasing.ordered" in event_types
    assert "purchasing.receipt" in event_types


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth, "auth_enabled", lambda: True)
    monkeypatch.setenv("AUTH_BOOTSTRAP_USERNAME", "bootstrap")
    monkeypatch.setenv("AUTH_BOOTSTRAP_PASSWORD", "bootstrap-password")
    db.initialize(reset=True)
    with TestClient(app) as test_client:
        yield test_client


def role_client(test_client, username, role):
    with db.connect() as connection:
        cursor = connection.execute(
            "INSERT INTO auth_users(username,password_hash,created_at) VALUES (?,?,?)",
            (username, auth._password_hash("operator-password"), "2026-01-01T00:00:00Z"),
        )
        role_id = connection.execute("SELECT id FROM auth_roles WHERE name=?", (role,)).fetchone()[0]
        connection.execute("INSERT INTO auth_user_roles(user_id,role_id) VALUES (?,?)", (cursor.lastrowid, role_id))
    session, csrf = auth._new_session(cursor.lastrowid)
    test_client.cookies.set("local_session", session)
    test_client.cookies.set("local_csrf", csrf)
    test_client.headers.update({"X-CSRF-Token": csrf})
    return test_client


def test_operator_cannot_use_over_receipt_override_when_auth_enabled(auth_client):
    operator = role_client(auth_client, "operator", "operator")
    pid = create_purchase(operator)
    assert operator.post(f"/api/purchases/{pid}/order").status_code == 200
    denied = operator.post(
        f"/api/purchases/{pid}/receive",
        json={
            "lines": [{"product_id": 1, "quantity": 11}],
            "allow_over_receipt": True,
            "override_reason": "Not enough authority",
        },
    )
    assert denied.status_code == 403
    assert stock(operator)["on_hand"] == 20


def test_manager_can_use_over_receipt_override_when_auth_enabled(auth_client):
    manager = role_client(auth_client, "manager", "manager")
    pid = create_purchase(manager)
    assert manager.post(f"/api/purchases/{pid}/order").status_code == 200
    allowed = manager.post(
        f"/api/purchases/{pid}/receive",
        json={
            "lines": [{"product_id": 1, "quantity": 11}],
            "allow_over_receipt": True,
            "override_reason": "Manager-approved supplier variance",
        },
    )
    assert allowed.status_code == 200
    with db.connect() as connection:
        audit = connection.execute(
            "SELECT actor_user_id,detail FROM audit_events WHERE event_type='purchasing.receipt_override' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert audit["actor_user_id"] is not None
    assert "Manager-approved" in audit["detail"]


def test_operator_cannot_replay_a_manager_override_key(auth_client):
    manager = role_client(auth_client, "manager-replay", "manager")
    pid = create_purchase(manager)
    assert manager.post(f"/api/purchases/{pid}/order").status_code == 200
    payload = {
        "lines": [{"product_id": 1, "quantity": 11}],
        "allow_over_receipt": True,
        "override_reason": "Approved variance",
        "idempotency_key": "manager-override-replay",
    }
    assert manager.post(f"/api/purchases/{pid}/receive", json=payload).status_code == 200
    operator = role_client(auth_client, "operator-replay", "operator")
    denied = operator.post(f"/api/purchases/{pid}/receive", json=payload)
    assert denied.status_code == 403


def test_database_has_concurrent_safe_inventory_constraints(client):
    with db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO inventory(product_id,warehouse_id,on_hand,reserved,updated_at) VALUES (1,1,1,0,'now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO inventory(product_id,warehouse_id,on_hand,reserved,updated_at) VALUES (999,999,1,0,'now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO inventory(product_id,warehouse_id,on_hand,reserved,updated_at) VALUES (1,999,1,0,'now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO inventory(product_id,warehouse_id,on_hand,reserved,updated_at) VALUES (1,1,1,2,'now')"
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchone() is None
