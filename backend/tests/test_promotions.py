from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import app


def promotion_payload(**overrides):
    payload = {
        "code": " save10 ",
        "name": "Save ten",
        "discount_type": "fixed",
        "value": "5.00",
        "starts_on": datetime.now(timezone.utc).date().isoformat(),
        "ends_on": (date.today() + timedelta(days=30)).isoformat(),
        "usage_limit": None,
        "active": True,
    }
    payload.update(overrides)
    return payload


def create_promotion(client, **overrides):
    response = client.post("/api/promotions", json=promotion_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def start_order(client, *, channel="counter", item_id=1, quantity=1):
    response = client.post("/api/counter/orders", json={"order_channel": channel})
    assert response.status_code == 200, response.text
    order_id = response.json()["order"]["id"]
    line = client.post(
        f"/api/orders/{order_id}/lines",
        json={"menu_item_id": item_id, "quantity": quantity},
    )
    assert line.status_code == 200, line.text
    return order_id


def configure_tax(client):
    response = client.post(
        "/api/tax/configuration",
        json={
            "name": "VAT",
            "rate": "10",
            "policy": "exclusive",
            "effective_from": "2020-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def apply_promotion(client, order_id, code, key=None):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post(
        f"/api/orders/{order_id}/promotions",
        headers=headers,
        json={"code": code},
    )


def csrf_headers(client):
    return {"X-CSRF-Token": client.cookies["local_csrf"]}


def role_client(test_client, username, role):
    with db.connect() as connection:
        cursor = connection.execute(
            "INSERT INTO auth_users(username,password_hash,created_at) VALUES (?,?,?)",
            (username, auth._password_hash("operator-password"), "2026-01-01T00:00:00Z"),
        )
        role_id = connection.execute("SELECT id FROM auth_roles WHERE name=?", (role,)).fetchone()[0]
        connection.execute(
            "INSERT INTO auth_user_roles(user_id,role_id) VALUES (?,?)",
            (cursor.lastrowid, role_id),
        )
    session, csrf = auth._new_session(cursor.lastrowid)
    test_client.cookies.set("local_session", session)
    test_client.cookies.set("local_csrf", csrf)
    test_client.headers.update({"X-CSRF-Token": csrf})
    return test_client


def test_promotions_normalize_codes_list_status_and_bound_values(client):
    created = create_promotion(client)

    assert created["code"] == "SAVE10"
    assert created["discount_type"] == "fixed"
    assert created["value"] == "5.00"
    assert created["usage_count"] == 0
    assert created["remaining_uses"] is None

    listed = client.get("/api/promotions")
    assert listed.status_code == 200
    assert listed.json()[0]["code"] == "SAVE10"
    assert listed.json()[0]["status"] == "active"

    duplicate = client.post("/api/promotions", json=promotion_payload(code=" save10 "))
    assert duplicate.status_code == 409

    invalid = [
        promotion_payload(value="-0.01"),
        promotion_payload(discount_type="percentage", value="100.01"),
        promotion_payload(value="1.001"),
        promotion_payload(code="   "),
        promotion_payload(starts_on="2030-01-02", ends_on="2030-01-01"),
        promotion_payload(usage_limit=-1),
    ]
    for payload in invalid:
        response = client.post("/api/promotions", json=payload)
        assert response.status_code == 422, response.text


def test_disabled_auth_without_local_bypass_reports_promotions_as_read_only(client, monkeypatch):
    monkeypatch.delenv("AUTH_LOCAL_DEV_BYPASS", raising=False)
    response = client.get("/api/promotions")
    assert response.status_code == 200
    assert response.json() == []


def test_editing_an_open_promoted_order_reprices_the_snapshot(client):
    create_promotion(client, value="5.00")
    order_id = start_order(client)
    applied = apply_promotion(client, order_id, "save10", key="open-edit-1")
    assert applied.status_code == 200
    updated = client.post(f"/api/orders/{order_id}/lines", json={"menu_item_id": 2, "quantity": 1})
    assert updated.status_code == 200
    body = updated.json()
    assert body["order"]["original_subtotal"] == "34.00"
    assert body["order"]["discount_amount"] == "5.00"
    assert body["order"]["discounted_subtotal"] == "29.00"


def test_fixed_promotion_recalculates_from_discounted_subtotal_and_preserves_tax_snapshot(client):
    tax = configure_tax(client)
    order_id = start_order(client)
    confirmed = client.post(
        f"/api/orders/{order_id}/confirm",
        json={"customer_name": "Mika"},
    )
    assert confirmed.status_code == 200, confirmed.text
    before = confirmed.json()
    assert before["order"]["tax_rule_id"] == tax["id"]
    assert before["order"]["tax_amount"] == "1.80"

    create_promotion(client, value="5.00")
    applied = apply_promotion(client, order_id, "save10", key="apply-fixed-1")

    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["order"]["status"] == "awaiting_payment"
    assert body["order"]["original_subtotal"] == "18.00"
    assert body["order"]["discount_amount"] == "5.00"
    assert body["order"]["discounted_subtotal"] == "13.00"
    assert body["order"]["taxable_subtotal"] == "13.00"
    assert body["order"]["tax_amount"] == "1.30"
    assert body["order"]["total"] == 14.30
    assert body["tax"]["rule_id"] == before["tax"]["rule_id"]
    assert body["tax"]["snapshot_at"] == before["tax"]["snapshot_at"]
    assert body["promotion"]["code"] == "SAVE10"
    assert body["promotion"]["discount_amount"] == "5.00"
    assert body["pricing"] == {
        "original_subtotal": "18.00",
        "discount_amount": "5.00",
        "discounted_subtotal": "13.00",
        "total": "14.30",
    }

    paid = client.post(
        f"/api/orders/{order_id}/pay",
        json={"amount": "14.30", "method": "cash"},
    )
    assert paid.status_code == 200, paid.text
    rejected = apply_promotion(client, order_id, "save10", key="apply-after-pay")
    assert rejected.status_code == 409


def test_promotion_before_confirmation_snapshots_discounted_tax_and_receipt(client):
    tax = configure_tax(client)
    create_promotion(client, code="EARLY", value="5")
    order_id = start_order(client)

    applied = apply_promotion(client, order_id, "early", key="early-apply")
    assert applied.status_code == 200, applied.text
    confirmed = client.post(
        f"/api/orders/{order_id}/confirm",
        json={"customer_name": "Mika"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["order"]["total"] == 14.30
    assert confirmed.json()["order"]["taxable_subtotal"] == "13.00"
    assert confirmed.json()["order"]["tax_amount"] == "1.30"
    assert confirmed.json()["tax"]["rule_id"] == tax["id"]

    paid = client.post(
        f"/api/orders/{order_id}/pay",
        json={"amount": "14.30", "method": "cash"},
    )
    assert paid.status_code == 200, paid.text
    ticket_id = paid.json()["ticket"]["id"]
    for action in ("start", "ready", "serve"):
        assert client.post(f"/api/kitchen/{ticket_id}/{action}").status_code == 200

    closed = client.post(f"/api/orders/{order_id}/close")
    assert closed.status_code == 200, closed.text
    receipt = closed.json()["receipt"]
    assert receipt["promotion_id"] == applied.json()["promotion"]["promotion_id"]
    assert receipt["promotion_code"] == "EARLY"
    assert receipt["promotion_discount_amount"] == "5.00"
    assert receipt["promotion_original_subtotal"] == "18.00"
    assert receipt["promotion_discounted_subtotal"] == "13.00"
    assert receipt["tax_rule_id"] == tax["id"]
    assert receipt["taxable_subtotal"] == "13.00"
    assert receipt["tax_amount"] == "1.30"


def test_percentage_promotion_replaces_and_remove_restores_original_taxed_total(client):
    configure_tax(client)
    order_id = start_order(client)
    assert client.post(
        f"/api/orders/{order_id}/confirm",
        json={"customer_name": "Mika"},
    ).status_code == 200
    create_promotion(client, code="half", discount_type="percentage", value="50")
    create_promotion(client, code="two-off", value="2")

    first = apply_promotion(client, order_id, "HALF", key="replace-1")
    assert first.status_code == 200, first.text
    assert first.json()["order"]["discounted_subtotal"] == "9.00"
    assert first.json()["order"]["total"] == 9.90
    first_applied_id = first.json()["promotion"]["id"]

    replaced = apply_promotion(client, order_id, "two-off", key="replace-2")
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["promotion"]["code"] == "TWO-OFF"
    assert replaced.json()["order"]["discount_amount"] == "2.00"
    assert replaced.json()["order"]["discounted_subtotal"] == "16.00"
    assert replaced.json()["order"]["total"] == 17.60
    with db.connect() as connection:
        assert connection.execute(
            "SELECT 1 FROM applied_promotions WHERE id=?", (first_applied_id,)
        ).fetchone() is None

    applied_id = replaced.json()["promotion"]["id"]
    removed = client.delete(f"/api/orders/{order_id}/promotions/{applied_id}", headers={"Idempotency-Key": "replace-remove"})
    assert removed.status_code == 200, removed.text
    assert removed.json()["promotion"] is None
    assert removed.json()["order"]["discount_amount"] == "0.00"
    assert removed.json()["order"]["discounted_subtotal"] == "18.00"
    assert removed.json()["order"]["taxable_subtotal"] == "18.00"
    assert removed.json()["order"]["tax_amount"] == "1.80"
    assert removed.json()["order"]["total"] == 19.80


def test_promotions_are_limited_to_manual_and_delivery_orders_before_payment(client):
    create_promotion(client, code="WELCOME", value="3")

    qr_table = client.post("/api/tables/2/open")
    assert qr_table.status_code == 200
    qr_order = client.post(
        f"/api/customer/tables/{qr_table.json()['qr_token']}/orders",
        headers={"Idempotency-Key": "qr-promotion"},
        json={"customer_name": "Mika", "lines": [{"menu_item_id": 1, "quantity": 1}]},
    )
    assert qr_order.status_code == 200
    qr_rejected = apply_promotion(client, qr_order.json()["order"]["id"], "WELCOME", key="qr-apply")
    assert qr_rejected.status_code == 409

    delivery_id = start_order(client, channel="delivery")
    assert client.post(
        f"/api/orders/{delivery_id}/delivery",
        json={"address": "12 Mabini Street, Cebu City", "contact": "09171234567"},
    ).status_code == 200
    assert client.post(
        f"/api/orders/{delivery_id}/confirm",
        json={"customer_name": "Delivery"},
    ).status_code == 200
    delivery_applied = apply_promotion(client, delivery_id, "welcome", key="delivery-apply")
    assert delivery_applied.status_code == 200
    assert delivery_applied.json()["order"]["order_channel"] == "delivery"


def test_date_active_and_lifecycle_guards_do_not_mutate_orders(client):
    create_promotion(client, code="FUTURE", starts_on=(date.today() + timedelta(days=1)).isoformat())
    create_promotion(client, code="EXPIRED", starts_on="2020-01-01", ends_on="2020-01-02")
    create_promotion(client, code="INACTIVE", active=False)
    order_id = start_order(client)

    for code in ("FUTURE", "EXPIRED", "INACTIVE"):
        response = apply_promotion(client, order_id, code, key=f"guard-{code}")
        assert response.status_code == 409, response.text
    assert client.get(f"/api/orders/{order_id}").json()["promotion"] is None

    create_promotion(client, code="VALID", value="1")
    assert apply_promotion(client, order_id, "VALID", key="valid-before-confirm").status_code == 200
    assert client.post(
        f"/api/orders/{order_id}/confirm", json={"customer_name": "Mika"}
    ).status_code == 200
    applied_id = client.get(f"/api/orders/{order_id}").json()["promotion"]["id"]
    assert client.delete(f"/api/orders/{order_id}/promotions/{applied_id}", headers={"Idempotency-Key": "valid-remove"}).status_code == 200
    assert client.post(
        f"/api/orders/{order_id}/pay",
        json={"amount": "18.00", "method": "cash"},
    ).status_code == 200
    assert client.delete(f"/api/orders/{order_id}/promotions/{applied_id}", headers={"Idempotency-Key": "paid-remove"}).status_code == 409


def test_usage_limits_are_atomic_and_apply_is_idempotent(client):
    create_promotion(client, code="ONCE", value="2", usage_limit=1)
    first_order = start_order(client)
    second_order = start_order(client)

    first = apply_promotion(client, first_order, "once", key="once-key")
    retry = apply_promotion(client, first_order, "ONCE", key="once-key")
    assert first.status_code == retry.status_code == 200
    assert retry.json() == first.json()

    unavailable = apply_promotion(client, second_order, "ONCE", key="second-once")
    assert unavailable.status_code == 409
    with db.connect() as connection:
        assert connection.execute("SELECT usage_count FROM promotions WHERE code='ONCE'").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM applied_promotions WHERE order_id=?", (second_order,)
        ).fetchone()[0] == 0


def test_apply_idempotency_conflict_and_audit_are_durable(client):
    create_promotion(client, code="AUDIT", value="1")
    create_promotion(client, code="OTHER", value="2")
    order_id = start_order(client)
    first = apply_promotion(client, order_id, "AUDIT", key="audit-key")
    assert first.status_code == 200
    conflict = apply_promotion(client, order_id, "OTHER", key="audit-key")
    assert conflict.status_code == 409
    applied_id = first.json()["promotion"]["id"]
    removed = client.delete(f"/api/orders/{order_id}/promotions/{applied_id}", headers={"Idempotency-Key": "audit-remove"})
    assert removed.status_code == 200

    events = client.get("/api/audit-events").json()
    event_types = [event["event_type"] for event in events]
    assert "promotion.created" in event_types
    assert "promotion.applied" in event_types
    assert "promotion.removed" in event_types
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM idempotency_keys WHERE key='audit-key'"
        ).fetchone()[0] == 1


def test_concurrent_limited_promotion_allows_only_one_order(client):
    create_promotion(client, code="RACE", value="1", usage_limit=1)
    first_order = start_order(client)
    second_order = start_order(client)

    def apply(order_id):
        with TestClient(app) as concurrent_client:
            return concurrent_client.post(
                f"/api/orders/{order_id}/promotions",
                headers={"Idempotency-Key": f"race-{order_id}"},
                json={"code": "RACE"},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(apply, (first_order, second_order)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    with db.connect() as connection:
        assert connection.execute("SELECT usage_count FROM promotions WHERE code='RACE'").fetchone()[0] == 1


@pytest.fixture
def auth_promotion_clients(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "promotions-auth.db")
    monkeypatch.setattr(auth, "auth_enabled", lambda: True)
    monkeypatch.setenv("AUTH_BOOTSTRAP_USERNAME", "bootstrap")
    monkeypatch.setenv("AUTH_BOOTSTRAP_PASSWORD", "bootstrap-password")
    db.initialize(reset=True)
    with TestClient(app) as test_client:
        yield test_client


def test_promotion_roles_allow_manager_creation_and_operator_application_but_not_viewer_mutation(
    auth_promotion_clients,
):
    manager = role_client(auth_promotion_clients, "promotion-manager", "manager")
    created = manager.post(
        "/api/promotions",
        headers=csrf_headers(manager),
        json=promotion_payload(code="ROLE", value="1"),
    )
    assert created.status_code == 201, created.text
    assert manager.post("/api/auth/logout", headers=csrf_headers(manager)).status_code == 200

    operator = role_client(auth_promotion_clients, "promotion-operator", "operator")
    order_id = start_order(operator)
    applied = operator.post(
        f"/api/orders/{order_id}/promotions",
        headers={**csrf_headers(operator), "Idempotency-Key": "operator-apply"},
        json={"code": "ROLE"},
    )
    assert applied.status_code == 200, applied.text
    denied_create = operator.post(
        "/api/promotions",
        headers=csrf_headers(operator),
        json=promotion_payload(code="NOPE"),
    )
    assert denied_create.status_code == 403
    assert operator.post("/api/auth/logout", headers=csrf_headers(operator)).status_code == 200

    viewer = role_client(auth_promotion_clients, "promotion-viewer", "viewer")
    assert viewer.get("/api/promotions").status_code == 200
    denied_apply = viewer.post(
        f"/api/orders/{order_id}/promotions",
        headers={**csrf_headers(viewer), "Idempotency-Key": "viewer-apply"},
        json={"code": "ROLE"},
    )
    assert denied_apply.status_code == 403


def test_promotion_remove_requires_idempotency_key_and_replays(client):
    create_promotion(client, code="REMOVE", value="1")
    order_id = start_order(client)
    applied = apply_promotion(client, order_id, "REMOVE", key="remove-apply")
    assert applied.status_code == 200
    applied_id = applied.json()["promotion"]["id"]

    missing = client.delete(f"/api/orders/{order_id}/promotions/{applied_id}")
    assert missing.status_code == 400

    removed = client.delete(
        f"/api/orders/{order_id}/promotions/{applied_id}",
        headers={"Idempotency-Key": "remove-key"},
    )
    assert removed.status_code == 200
    replay = client.delete(
        f"/api/orders/{order_id}/promotions/{applied_id}",
        headers={"Idempotency-Key": "remove-key"},
    )
    assert replay.status_code == 200
    assert replay.json() == removed.json()
