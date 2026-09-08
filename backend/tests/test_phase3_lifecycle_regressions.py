from concurrent.futures import ThreadPoolExecutor

from app import db


def create_order(client, *, item_id=1, quantity=1):
    opened = client.post("/api/tables/2/open")
    assert opened.status_code == 200
    session_id = opened.json()["session"]["id"]
    created = client.post(f"/api/sessions/{session_id}/orders")
    assert created.status_code == 200
    order_id = created.json()["order"]["id"]
    assert client.post(
        f"/api/orders/{order_id}/lines",
        json={"menu_item_id": item_id, "quantity": quantity},
    ).status_code == 200
    return order_id


def confirm_and_pay(client, order_id, amount=18):
    assert client.post(
        f"/api/orders/{order_id}/confirm", json={"customer_name": "Mika"}
    ).status_code == 200
    response = client.post(
        f"/api/orders/{order_id}/pay",
        json={"amount": amount, "method": "cash"},
    )
    assert response.status_code == 200
    return response.json()


def test_ready_ticket_is_in_pickup_queue_before_it_is_served(client):
    order_id = create_order(client)
    paid = confirm_and_pay(client, order_id)
    ticket_id = paid["ticket"]["id"]

    assert client.post(f"/api/kitchen/{ticket_id}/start").status_code == 200
    assert client.post(f"/api/kitchen/{ticket_id}/ready").status_code == 200

    ready_queue = client.get("/api/kitchen?queue=ready")
    active_queue = client.get("/api/kitchen")
    assert ready_queue.status_code == 200
    assert [ticket["id"] for ticket in ready_queue.json()] == [ticket_id]
    assert ready_queue.json()[0]["status"] == "ready"
    assert [ticket["id"] for ticket in active_queue.json()] == [ticket_id]


def test_invalid_payment_and_release_preserve_order_payment_and_ticket_state(client):
    order_id = create_order(client)
    before = client.get(f"/api/orders/{order_id}").json()

    assert client.post(f"/api/orders/{order_id}/send").status_code == 409
    assert client.post(
        f"/api/orders/{order_id}/pay",
        json={"amount": 1, "method": "cash"},
    ).status_code == 409
    assert client.get(f"/api/orders/{order_id}").json() == before

    paid = confirm_and_pay(client, order_id)
    paid_before = client.get(f"/api/orders/{order_id}").json()
    assert client.post(f"/api/orders/{order_id}/send").status_code == 200
    assert client.post(f"/api/orders/{order_id}/send").status_code == 200
    assert client.get(f"/api/orders/{order_id}").json() == paid_before
    assert paid["ticket"]["id"] == paid_before["ticket"]["id"]


def test_concurrent_payment_and_release_are_idempotent_in_isolated_db(client):
    order_id = create_order(client)
    assert client.post(
        f"/api/orders/{order_id}/confirm", json={"customer_name": "Mika"}
    ).status_code == 200

    def pay():
        return client.post(
            f"/api/orders/{order_id}/pay",
            json={"amount": 18, "method": "cash"},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        payment_statuses = list(pool.map(lambda _: pay(), range(8)))

    assert payment_statuses == [200] * 8
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM payments WHERE order_id=?", (order_id,)
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM kitchen_tickets WHERE order_id=?", (order_id,)
        ).fetchone()[0] == 1

    def release():
        return client.post(f"/api/orders/{order_id}/send").status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        release_statuses = list(pool.map(lambda _: release(), range(8)))

    assert release_statuses == [200] * 8
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM payments WHERE order_id=?", (order_id,)
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM kitchen_tickets WHERE order_id=?", (order_id,)
        ).fetchone()[0] == 1


def test_valid_lifecycle_closes_with_exactly_one_receipt(client):
    order_id = create_order(client)
    paid = confirm_and_pay(client, order_id)
    ticket_id = paid["ticket"]["id"]
    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket_id}/{action}").status_code == 200

    assert client.post(f"/api/orders/{order_id}/close").status_code == 200
    repeated = client.post(f"/api/orders/{order_id}/close")
    assert repeated.status_code == 200
    assert repeated.json()["order"]["status"] == "closed"

    with db.connect() as connection:
        assert connection.execute(
            "SELECT status FROM restaurant_orders WHERE id=?", (order_id,)
        ).fetchone()[0] == "closed"
        assert connection.execute(
            "SELECT COUNT(*) FROM receipts WHERE order_id=?", (order_id,)
        ).fetchone()[0] == 1


def test_invalid_kitchen_transitions_conflict_without_mutation(client):
    order_id = create_order(client)
    paid = confirm_and_pay(client, order_id)
    ticket_id = paid["ticket"]["id"]

    before = client.get(f"/api/orders/{order_id}").json()["ticket"]
    assert client.post(f"/api/kitchen/{ticket_id}/ready").status_code == 409
    assert client.post(f"/api/kitchen/{ticket_id}/serve").status_code == 409
    after = client.get(f"/api/orders/{order_id}").json()["ticket"]
    assert after == before
    assert after["status"] == "queued"
