import sqlite3
import runpy
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "app.db")
    db.initialize(reset=True)
    with TestClient(app) as c: yield c

def test_seed_reset_and_sqlite_safety_are_stable(client):
    with db.connect() as c:
        first = [tuple(r) for r in c.execute("SELECT * FROM menu_items ORDER BY id")]
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert c.execute("PRAGMA foreign_key_check").fetchone() is None
    db.initialize(); db.reset()
    with db.connect() as c: assert [tuple(r) for r in c.execute("SELECT * FROM menu_items ORDER BY id")] == first

def test_seed_module_exposes_documented_reset_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "initialize", lambda reset=False: calls.append(reset))
    monkeypatch.setattr(sys, "argv", ["app.seed", "--reset"])
    runpy.run_module("app.seed", run_name="__main__")
    assert calls == [True]

def test_reset_recreates_seed_after_inventory_purchase_and_audit_data(client):
    adjustment = client.post(
        "/api/stock/adjustment",
        json={"product_id": 1, "warehouse_id": 1, "quantity": 1, "reason": "Reset regression", "idempotency_key": "reset-adjustment"},
    )
    assert adjustment.status_code == 200

    purchase = client.post("/api/purchases", json={"supplier_id": 1, "idempotency_key": "reset-purchase"})
    assert purchase.status_code == 200
    purchase_id = purchase.json()["id"]
    line = client.post(
        f"/api/purchases/{purchase_id}/lines",
        json={"product_id": 1, "warehouse_id": 1, "quantity": 2, "unit_cost": 8, "idempotency_key": "reset-line"},
    )
    assert line.status_code == 200

    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM inventory WHERE product_id=1").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM purchase_lines WHERE purchase_id=?", (purchase_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] >= 3

    db.reset()

    with db.connect() as connection:
        assert connection.execute("SELECT code FROM warehouses WHERE id=1").fetchone()[0] == "MAIN"
        assert connection.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchone() is None

def lifecycle(client):
    opened = client.post("/api/tables/2/open"); assert opened.status_code == 200
    session = opened.json()["session"]["id"]
    order = client.post(f"/api/sessions/{session}/orders").json()["order"]
    oid = order["id"]
    return oid, session

def test_complete_floor_kitchen_payment_close_workflow(client):
    oid, session = lifecycle(client)
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":1,"quantity":1}).status_code == 200
    assert client.post(f"/api/orders/{oid}/confirm", json={"customer_name":"Mika"}).status_code == 200
    paid = client.post(f"/api/orders/{oid}/pay", json={"amount":18,"method":"cash"})
    assert paid.status_code == 200
    ticket = paid.json()["ticket"]["id"]
    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket}/{action}").status_code == 200
    closed = client.post(f"/api/orders/{oid}/close")
    assert closed.status_code == 200 and closed.json()["order"]["status"] == "closed"
    assert client.get("/api/tables").json()[1]["status"] == "available"
    listed = next(order for order in client.get("/api/orders").json() if order["id"] == oid)
    assert listed["table_id"] == 2
    assert listed["lines"][0]["menu_item_id"] == 1
    receipt = client.get("/api/receipts").json()[0]
    assert receipt["order_id"] == oid
    assert receipt["order_number"] == "ORD-0002"
    assert receipt["table_code"] == "T02"
    assert receipt["total"] == 18
    assert receipt["issued_at"] != "2026-01-01T00:00:00Z"

def test_served_order_cannot_be_paid_again_and_preserves_state(client):
    oid, _ = lifecycle(client)
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":1,"quantity":1}).status_code == 200
    assert client.post(f"/api/orders/{oid}/confirm", json={"customer_name":"Mika"}).status_code == 200
    paid = client.post(f"/api/orders/{oid}/pay", json={"amount":18,"method":"cash"})
    assert paid.status_code == 200
    ticket_id = paid.json()["ticket"]["id"]
    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket_id}/{action}").status_code == 200

    before = client.get(f"/api/orders/{oid}").json()
    assert before["order"]["status"] == "served"
    assert before["payment"]["status"] == "paid"

    rejected = client.post(f"/api/orders/{oid}/pay", json={"amount":18,"method":"cash"})

    assert rejected.status_code == 409
    after = client.get(f"/api/orders/{oid}").json()
    assert after["order"] == before["order"]
    assert after["payment"] == before["payment"]
    assert after["ticket"] == before["ticket"]

def test_invalid_actions_and_payment_rollback(client):
    oid, _ = lifecycle(client)
    assert client.post(f"/api/orders/{oid}/send").status_code == 409
    before = client.get(f"/api/orders/{oid}").json()
    assert client.post(f"/api/orders/{oid}/pay", json={"amount":1,"method":"cash"}).status_code == 409
    assert client.get(f"/api/orders/{oid}").json() == before
    assert client.get("/api/kitchen").json() == []
    assert client.post("/api/tables/2/open").status_code == 409
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":999,"quantity":1}).status_code == 404
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":1,"quantity":999}).status_code == 200

def test_open_order_cannot_send_to_kitchen_and_preserves_state(client):
    oid, _ = lifecycle(client)
    client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":1,"quantity":1})
    before = client.get(f"/api/orders/{oid}").json()

    rejected = client.post(f"/api/orders/{oid}/send")

    assert rejected.status_code == 409
    assert client.get(f"/api/orders/{oid}").json() == before
    assert client.get("/api/kitchen").json() == []

def test_guided_counter_order_waits_for_payment_before_kitchen(client):
    created = client.post("/api/counter/orders")
    assert created.status_code == 200
    order = created.json()["order"]
    oid = order["id"]
    assert order["order_channel"] == "counter"
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":1,"quantity":1}).status_code == 200

    confirmed = client.post(f"/api/orders/{oid}/confirm", json={"customer_name":"Mika"})
    assert confirmed.status_code == 200
    assert confirmed.json()["order"]["status"] == "awaiting_payment"
    assert confirmed.json()["order"]["customer_name"] == "Mika"
    assert client.get("/api/kitchen").json() == []
    queued = client.get("/api/payment-queue").json()
    assert len(queued) == 1 and queued[0]["order_number"] == order["order_number"]

    paid = client.post(f"/api/orders/{oid}/pay", json={"amount":18,"method":"cash"})
    assert paid.status_code == 200
    assert paid.json()["order"]["status"] == "paid"
    ticket = paid.json()["ticket"]
    assert ticket["status"] == "queued"

    repeated = client.post(f"/api/orders/{oid}/send")
    assert repeated.status_code == 200
    assert repeated.json()["ticket"] == ticket
    assert len(client.get("/api/kitchen").json()) == 1

    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket['id']}/{action}").status_code == 200
    closed = client.post(f"/api/orders/{oid}/close")
    assert closed.status_code == 200
    assert closed.json()["receipt"]["receipt_number"]

def test_table_order_creation_accepts_qr_channel_metadata(client):
    opened = client.post("/api/tables/3/open")
    assert opened.status_code == 200
    session_id = opened.json()["session"]["id"]
    created = client.post(f"/api/sessions/{session_id}/orders", json={"customer_name":"Lia","order_channel":"qr"})
    assert created.status_code == 200
    assert created.json()["order"]["customer_name"] == "Lia"
    assert created.json()["order"]["order_channel"] == "qr"

def test_ready_queue_keeps_served_ticket_while_active_kitchen_queue_excludes_it(client):
    oid, _ = lifecycle(client)
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":1,"quantity":1}).status_code == 200
    assert client.post(f"/api/orders/{oid}/confirm", json={"customer_name":"Mika"}).status_code == 200
    paid = client.post(f"/api/orders/{oid}/pay", json={"amount":18,"method":"cash"})
    assert paid.status_code == 200
    ticket = paid.json()["ticket"]["id"]
    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket}/{action}").status_code == 200

    active = client.get("/api/kitchen")
    ready = client.get("/api/kitchen?queue=ready")

    assert active.status_code == 200
    assert all(row["id"] != ticket for row in active.json())
    assert ready.status_code == 200
    assert [row["id"] for row in ready.json()] == [ticket]
    assert ready.json()[0]["status"] == "served"
    assert client.get("/api/kitchen?queue=invalid").status_code == 422

    assert client.post(f"/api/orders/{oid}/close").status_code == 200
    assert client.get("/api/kitchen?queue=ready").json() == []

def test_foreign_keys_and_illegal_kitchen_transition(client):
    oid, _ = lifecycle(client)
    client.post(f"/api/orders/{oid}/lines", json={"menu_item_id":3,"quantity":1})
    client.post(f"/api/orders/{oid}/confirm", json={"customer_name":"Mika"})
    ticket = client.post(f"/api/orders/{oid}/pay", json={"amount":5,"method":"cash"}).json()["ticket"]["id"]
    assert client.post(f"/api/kitchen/{ticket}/ready").status_code == 409
    with db.connect() as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO restaurant_order_lines(order_id,menu_item_id,item_name,quantity,unit_price,line_total) VALUES(999,999,'x',1,1,1)")
        assert c.execute("PRAGMA foreign_key_check").fetchone() is None
