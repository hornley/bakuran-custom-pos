import hashlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from app import auth, db


def open_qr_table(client, table_id=2):
    opened = client.post(f"/api/tables/{table_id}/open")
    assert opened.status_code == 200
    return opened, opened.json()["qr_token"]


def submit(client, token, key="customer-order-1", lines=None, name="Mika"):
    return client.post(
        f"/api/customer/tables/{token}/orders",
        headers={"Idempotency-Key": key},
        json={"customer_name": name, "lines": lines or [{"menu_item_id": 1, "quantity": 1}]},
    )


def test_open_table_issues_session_scoped_token_and_customer_can_load_menu(client):
    opened, token = open_qr_table(client)

    public = client.get(f"/api/customer/tables/{token}")

    assert public.status_code == 200
    body = public.json()
    assert body["table"]["code"] == "T02"
    assert body["session"]["id"] == opened.json()["session"]["id"]
    assert token not in public.text
    assert "qr_token_hash" not in public.text
    assert {item["name"] for item in body["menu"]} == {
        "House Burger",
        "Garden Pasta",
        "Lemonade",
        "House Coffee",
    }


def test_open_table_stores_only_a_hash_and_table_listing_does_not_repeat_the_token(client):
    opened, token = open_qr_table(client)

    assert "qr_token_hash" not in str(opened.json())
    with db.connect() as connection:
        stored = connection.execute(
            "SELECT qr_token_hash, qr_token_issued_at FROM table_sessions WHERE id=?",
            (opened.json()["session"]["id"],),
        ).fetchone()
        assert stored["qr_token_hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert stored["qr_token_hash"] != token
        assert stored["qr_token_issued_at"]

    listed = client.get("/api/tables").json()
    assert "qr_token" not in str(listed)
    assert "qr_token_hash" not in str(listed)


def test_public_customer_api_does_not_bypass_operator_auth(client, monkeypatch):
    _, token = open_qr_table(client)
    monkeypatch.setattr(auth, "AUTH_PROFILE", "local")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setattr(auth, "record_event", lambda *args, **kwargs: None)

    assert client.get(f"/api/customer/tables/{token}").status_code == 200
    assert client.get("/api/tables").status_code == 401


def test_customer_api_allows_the_default_local_frontend_origin(client):
    _, token = open_qr_table(client)

    response = client.options(
        f"/api/customer/tables/{token}/orders",
        headers={
            "Origin": "http://127.0.0.1:5200",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5200"


def test_customer_menu_endpoint_returns_only_active_items_and_categories(client):
    _, token = open_qr_table(client)
    with db.connect() as connection:
        connection.execute("UPDATE menu_items SET active=0 WHERE id=4")
        connection.execute("UPDATE menu_categories SET active=0 WHERE id=2")

    response = client.get(f"/api/customer/tables/{token}/menu")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["House Burger", "Garden Pasta"]


def test_customer_order_snapshots_configured_tax_and_payment_uses_inclusive_total(client):
    configured = client.post(
        "/api/tax/configuration",
        json={
            "name": "VAT",
            "rate": "10",
            "policy": "exclusive",
            "effective_from": "2020-01-01",
        },
    )
    assert configured.status_code == 201
    _, token = open_qr_table(client)

    created = submit(client, token, key="qr-tax")

    assert created.status_code == 200
    order = client.get(f"/api/orders/{created.json()['order']['id']}").json()["order"]
    assert order["status"] == "awaiting_payment"
    assert order["tax_policy"] == "exclusive"
    assert order["tax_rate"] == "10"
    assert Decimal(str(order["taxable_subtotal"])) == Decimal("18.00")
    assert Decimal(str(order["tax_amount"])) == Decimal("1.80")
    assert Decimal(str(order["total"])) == Decimal("19.80")
    assert order["tax_rule_id"] == configured.json()["id"]
    assert order["tax_snapshot_at"]

    assert client.post(f"/api/orders/{order['id']}/pay", json={"amount": "18.00", "method": "cash"}).status_code == 409
    paid = client.post(f"/api/orders/{order['id']}/pay", json={"amount": "19.80", "method": "cash"})
    assert paid.status_code == 200
    assert Decimal(str(paid.json()["payment"]["amount"])) == Decimal("19.80")


def test_qr_payment_snapshots_legacy_awaiting_order_before_validation(client):
    _, token = open_qr_table(client)
    created = submit(client, token, key="legacy-qr-tax")
    order_id = created.json()["order"]["id"]
    with db.connect() as connection:
        connection.execute(
            "UPDATE restaurant_orders SET tax_rule_id=NULL, tax_name='', tax_rate='0.00', tax_policy='none', taxable_subtotal='0.00', tax_amount='0.00', tax_snapshot_at=NULL, tax_effective_from=NULL, tax_effective_to=NULL WHERE id=?",
            (order_id,),
        )
    configured = client.post(
        "/api/tax/configuration",
        json={
            "name": "VAT",
            "rate": "10",
            "policy": "exclusive",
            "effective_from": "2020-01-01",
        },
    )
    assert configured.status_code == 201

    assert client.post(f"/api/orders/{order_id}/pay", json={"amount": "18.00", "method": "cash"}).status_code == 409
    paid = client.post(f"/api/orders/{order_id}/pay", json={"amount": "19.80", "method": "cash"})
    assert paid.status_code == 200
    with db.connect() as connection:
        order = connection.execute(
            "SELECT tax_rule_id, tax_policy, tax_rate, taxable_subtotal, tax_amount, total, tax_snapshot_at, status FROM restaurant_orders WHERE id=?",
            (order_id,),
        ).fetchone()
    assert order["tax_rule_id"] == configured.json()["id"]
    assert order["tax_policy"] == "exclusive"
    assert order["tax_rate"] == "10"
    assert Decimal(str(order["taxable_subtotal"])) == Decimal("18.00")
    assert Decimal(str(order["tax_amount"])) == Decimal("1.80")
    assert Decimal(str(order["total"])) == Decimal("19.80")
    assert order["tax_snapshot_at"]
    assert order["status"] == "paid"


def test_customer_order_is_awaiting_payment_and_idempotent(client):
    _, token = open_qr_table(client)

    first = submit(client, token)
    retry = submit(client, token)

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert first.json()["order"]["status"] == "awaiting_payment"
    assert first.json()["order"]["order_channel"] == "qr"
    assert first.json()["order"]["order_number"]
    assert first.json()["lines"][0]["line_total"] == 18
    assert client.get("/api/payment-queue").json()[0]["order_number"] == first.json()["order"]["order_number"]
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restaurant_orders WHERE order_channel='qr'").fetchone()[0] == 1
    assert "client_idempotency_key" not in first.text
    assert "idempotency_fingerprint" not in first.text


def test_customer_order_allows_only_one_active_qr_order_per_session(client):
    _, token = open_qr_table(client)

    assert submit(client, token, key="first-order").status_code == 200
    duplicate = submit(client, token, key="second-order")

    assert duplicate.status_code == 409
    assert "active order" in duplicate.json()["detail"]
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM restaurant_orders WHERE session_id=2 AND order_channel='qr'"
        ).fetchone()[0] == 1


def test_customer_token_cannot_read_another_session_or_closed_session(client):
    _, token = open_qr_table(client, 2)
    other, other_token = open_qr_table(client, 3)
    order = submit(client, token).json()["order"]

    assert client.get(f"/api/customer/tables/not-a-token").status_code == 404
    assert client.get(f"/api/customer/tables/{other_token}/orders/{order['id']}").status_code == 404

    with db.connect() as connection:
        connection.execute("UPDATE table_sessions SET status='closed', closed_at='2026-09-08T00:00:00Z' WHERE id=?", (other.json()["session"]["id"],))
    assert client.get(f"/api/customer/tables/{other_token}").status_code == 404


def test_closed_token_cannot_be_reused_after_a_new_session_opens(client):
    _, old_token = open_qr_table(client, 2)
    assert client.post("/api/tables/2/close").status_code == 200
    _, new_token = open_qr_table(client, 2)

    assert client.get(f"/api/customer/tables/{old_token}").status_code == 404
    assert client.get(f"/api/customer/tables/{new_token}").status_code == 200


def test_customer_rejects_missing_or_invalid_basket_without_creating_order(client):
    _, token = open_qr_table(client)

    assert client.post(f"/api/customer/tables/{token}/orders", headers={"Idempotency-Key": "empty"}, json={"customer_name": "Mika", "lines": []}).status_code == 422
    assert submit(client, token, key="unknown", lines=[{"menu_item_id": 999, "quantity": 1}]).status_code == 404
    assert submit(client, token, key="inactive", lines=[{"menu_item_id": 1, "quantity": 1}], name=" ").status_code == 422
    assert submit(client, token, key="bad-qty", lines=[{"menu_item_id": 1, "quantity": 0}]).status_code == 422
    assert submit(client, token, key="too-many", lines=[{"menu_item_id": 1, "quantity": 21}]).status_code == 422
    with db.connect() as connection:
        connection.execute("UPDATE menu_items SET active=0 WHERE id=1")
    assert submit(client, token, key="inactive-item").status_code == 404
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restaurant_orders WHERE order_channel='qr'").fetchone()[0] == 0


def test_customer_rejects_blank_or_oversized_idempotency_keys(client):
    _, token = open_qr_table(client)

    missing = client.post(
        f"/api/customer/tables/{token}/orders",
        json={"customer_name": "Mika", "lines": [{"menu_item_id": 1, "quantity": 1}]},
    )
    blank = submit(client, token, key="")
    oversized = submit(client, token, key="k" * 129)

    assert missing.status_code == 400
    assert blank.status_code == 400
    assert oversized.status_code == 400
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restaurant_orders WHERE order_channel='qr'").fetchone()[0] == 0


def test_customer_rejects_duplicate_menu_lines(client):
    _, token = open_qr_table(client)

    response = submit(
        client,
        token,
        key="duplicate-lines",
        lines=[
            {"menu_item_id": 1, "quantity": 1},
            {"menu_item_id": 1, "quantity": 1},
        ],
    )

    assert response.status_code == 422
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restaurant_orders WHERE order_channel='qr'").fetchone()[0] == 0


def test_customer_rejects_extra_fields_and_control_characters(client):
    _, token = open_qr_table(client)

    extra_field = client.post(
        f"/api/customer/tables/{token}/orders",
        headers={"Idempotency-Key": "extra-field"},
        json={"customer_name": "Mika", "lines": [{"menu_item_id": 1, "quantity": 1, "price": 0}]},
    )
    control_name = submit(client, token, key="control-name", name="Mika\nLia")

    assert extra_field.status_code == 422
    assert control_name.status_code == 422
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restaurant_orders WHERE order_channel='qr'").fetchone()[0] == 0


def test_customer_order_rolls_back_if_a_line_write_fails(client):
    _, token = open_qr_table(client)
    with db.connect() as connection:
        connection.execute(
            "CREATE TRIGGER fail_customer_line BEFORE INSERT ON restaurant_order_lines "
            "WHEN NEW.menu_item_id=3 BEGIN SELECT RAISE(ABORT, 'test line failure'); END"
        )

    response = submit(
        client,
        token,
        key="line-rollback",
        lines=[{"menu_item_id": 1, "quantity": 1}, {"menu_item_id": 3, "quantity": 1}],
    )

    assert response.status_code == 409
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restaurant_orders WHERE order_channel='qr'").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM restaurant_order_lines WHERE order_id=2").fetchone()[0] == 0


def test_customer_order_uses_current_server_price_when_menu_changed_after_load(client):
    _, token = open_qr_table(client)
    menu = client.get(f"/api/customer/tables/{token}/menu")
    assert menu.status_code == 200

    with db.connect() as connection:
        connection.execute("UPDATE menu_items SET price=21.5 WHERE id=1")

    response = submit(client, token, key="price-revalidation")

    assert response.status_code == 200
    assert response.json()["lines"][0]["unit_price"] == 21.5
    assert response.json()["lines"][0]["line_total"] == 21.5
    assert response.json()["order"]["total"] == 21.5


def test_customer_rejects_reusing_idempotency_key_for_different_basket(client):
    _, token = open_qr_table(client)

    assert submit(client, token, key="same-key").status_code == 200
    conflict = submit(client, token, key="same-key", lines=[{"menu_item_id": 2, "quantity": 1}])

    assert conflict.status_code == 409
    assert "different order" in conflict.json()["detail"]


def test_idempotency_key_is_trimmed_and_payload_conflicts_include_customer_name(client):
    _, token = open_qr_table(client)

    first = submit(client, token, key="  same-key  ", name="Mika")
    retry = submit(client, token, key="same-key", name="Mika")
    conflict = submit(client, token, key="same-key", name="Lia")

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert conflict.status_code == 409


def test_same_idempotency_key_is_scoped_to_the_table_session(client):
    _, first_token = open_qr_table(client, 2)
    _, second_token = open_qr_table(client, 3)

    first = submit(client, first_token, key="session-scoped")
    second = submit(client, second_token, key="session-scoped")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["order"]["id"] != first.json()["order"]["id"]


def test_concurrent_same_key_creates_one_order_and_returns_same_payload(client):
    _, token = open_qr_table(client)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: submit(client, token, key="race-safe"), range(2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM restaurant_orders WHERE session_id=2 AND order_channel='qr'"
        ).fetchone()[0] == 1


def test_customer_order_detail_requires_matching_token(client):
    _, token = open_qr_table(client, 2)
    _, other_token = open_qr_table(client, 3)
    created = submit(client, token)
    order_id = created.json()["order"]["id"]

    detail = client.get(f"/api/customer/tables/{token}/orders/{order_id}")

    assert detail.status_code == 200
    assert detail.json()["order"]["id"] == order_id
    assert client.get(f"/api/customer/tables/{other_token}/orders/{order_id}").status_code == 404
