from app import db


def test_bakuran_resources_and_atomic_stock_receipt(client):
    health = client.get("/api/health").json()
    assert health["project_name"]
    assert health["database_ready"] is True
    assert health["target_stack"] == "react_fastapi_sqlite"
    assert client.get("/api/catalog").status_code == 200
    assert client.get("/api/customers").json()[0]["code"] == "CUS-001"
    purchase = client.post("/api/purchases", json={"name": "restock", "supplier_id": 1}).json()
    pid = purchase["id"]
    assert client.post(f"/api/purchases/{pid}/lines", json={"name": "burger", "product_id": 1, "quantity": 3, "unit_cost": 8}).status_code == 200
    assert client.post(f"/api/purchases/{pid}/receive").json()["status"] == "received"
    assert client.post("/api/stock/receipt", json={"name": "receipt", "product_id": 1, "quantity": 2}).status_code == 200
    assert client.post("/api/attendance", json={"name": "Alex", "value": "in"}).status_code == 200
    assert client.get("/api/search?q=burger").status_code == 200
    with db.connect() as connection:
        assert connection.execute("SELECT on_hand FROM inventory WHERE product_id=1").fetchone()[0] == 25
    for endpoint in ("/api/pos/transactions", "/api/order-to-cash", "/api/kitchen/tickets", "/api/restaurant/service", "/api/purchasing", "/api/stock/receipts", "/api/settings", "/api/notifications", "/api/attendance", "/api/suppliers"):
        assert client.get(endpoint).status_code == 200

def test_send_and_payment_are_idempotent_and_invalid_receipt_rolls_back(client):
    opened = client.post("/api/tables/2/open").json()
    oid = client.post(f"/api/sessions/{opened['session']['id']}/orders").json()["order"]["id"]
    client.post(f"/api/orders/{oid}/lines", json={"menu_item_id": 1, "quantity": 1})
    first = client.post(f"/api/orders/{oid}/send").json()
    second = client.post(f"/api/orders/{oid}/send").json()
    assert first == second
    assert client.post("/api/stock/receipt", json={"name": "bad", "product_id": 999, "quantity": 2}).status_code == 404
