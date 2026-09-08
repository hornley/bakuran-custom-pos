import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import app


def _new_delivery_order(client, *, with_metadata=False):
    created = client.post("/api/counter/orders", json={"order_channel": "delivery"})
    assert created.status_code == 200, created.text
    order = created.json()["order"]
    oid = order["id"]
    if with_metadata:
        metadata = client.post(
            f"/api/orders/{oid}/delivery",
            json={
                "address": "12 Mabini Street, Cebu City",
                "contact": "09171234567",
                "contact_name": "Mika",
            },
        )
        assert metadata.status_code == 200, metadata.text
    assert client.post(f"/api/orders/{oid}/lines", json={"menu_item_id": 1, "quantity": 1}).status_code == 200
    return oid


def _pay_delivery(client, *, with_metadata=True):
    oid = _new_delivery_order(client, with_metadata=with_metadata)
    confirmed = client.post(f"/api/orders/{oid}/confirm", json={"customer_name": "Mika"})
    assert confirmed.status_code == 200, confirmed.text
    paid = client.post(f"/api/orders/{oid}/pay", json={"amount": 18, "method": "cash"})
    assert paid.status_code == 200, paid.text
    payload = paid.json()
    return oid, payload["delivery"]["id"]


def test_delivery_address_and_contact_are_validated_and_payment_is_cash_only(client):
    oid = _new_delivery_order(client)

    missing = client.post(f"/api/orders/{oid}/delivery", json={"address": "", "contact": ""})
    assert missing.status_code == 422
    assert client.get(f"/api/orders/{oid}").json()["delivery"] is None

    partial = client.post(f"/api/orders/{oid}/delivery", json={"address": "12 Mabini Street"})
    assert partial.status_code == 422

    saved = client.post(
        f"/api/orders/{oid}/delivery",
        json={"address": "12 Mabini Street, Cebu City", "contact": "09171234567"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["delivery"]["address"] == "12 Mabini Street, Cebu City"
    assert saved.json()["delivery"]["contact"] == "09171234567"

    confirmed = client.post(f"/api/orders/{oid}/confirm", json={"customer_name": "Mika"})
    assert confirmed.status_code == 200
    card = client.post(f"/api/orders/{oid}/pay", json={"amount": 18, "method": "test_card"})
    assert card.status_code == 409
    assert client.get(f"/api/orders/{oid}").json()["order"]["status"] == "awaiting_payment"

    cash = client.post(f"/api/orders/{oid}/pay", json={"amount": 18, "method": "cash"})
    assert cash.status_code == 200
    assert cash.json()["order"]["order_channel"] == "delivery"
    assert cash.json()["delivery"]["status"] == "pending"
    assert cash.json()["ticket"]["status"] == "queued"


def test_delivery_metadata_is_isolated_and_invalid_updates_do_not_mutate(client):
    first = _new_delivery_order(client, with_metadata=True)
    second = _new_delivery_order(client)
    before = client.get(f"/api/orders/{first}").json()

    invalid = client.post(
        f"/api/orders/{first}/delivery",
        json={"address": "12 Mabini Street", "contact": "not-a-phone", "contact_name": "Changed"},
    )
    assert invalid.status_code == 422
    assert client.get(f"/api/orders/{first}").json() == before
    assert client.get(f"/api/orders/{second}").json()["delivery"] is None

    saved = client.post(
        f"/api/orders/{first}/delivery",
        json={"address": "99 Rizal Avenue, Cebu City", "contact": "+639171234567", "contact_name": "Nina"},
    )
    assert saved.status_code == 200
    assert saved.json()["delivery"]["order_id"] == first
    assert client.get(f"/api/orders/{second}").json()["delivery"] is None


def test_delivery_confirmation_and_assignment_require_payment_and_metadata(client):
    missing_oid = _new_delivery_order(client)
    assert client.post(f"/api/orders/{missing_oid}/confirm", json={"customer_name": "Mika"}).status_code == 422
    assert client.get(f"/api/orders/{missing_oid}").json()["order"]["status"] == "open"

    oid = _new_delivery_order(client, with_metadata=True)
    assert client.post(f"/api/orders/{oid}/confirm", json={"customer_name": "Mika"}).status_code == 200
    delivery_id = client.get(f"/api/orders/{oid}").json()["delivery"]["id"]

    before = client.get(f"/api/delivery/{delivery_id}").json()
    assert before["delivery"]["status"] == "pending"
    assert client.get("/api/delivery").json() == []
    not_paid = client.post(f"/api/delivery/{delivery_id}/assign", json={"driver_id": 1})
    assert not_paid.status_code == 409
    assert client.get(f"/api/delivery/{delivery_id}").json() == before


def test_delivery_transitions_are_guarded_and_idempotent(client):
    oid, delivery_id = _pay_delivery(client)
    assert [row["id"] for row in client.get("/api/delivery").json()] == [delivery_id]

    before_invalid = client.get(f"/api/delivery/{delivery_id}").json()
    direct_departure = client.post(f"/api/delivery/{delivery_id}/out-for-delivery", json={})
    assert direct_departure.status_code == 409
    direct_delivery = client.post(f"/api/delivery/{delivery_id}/delivered", json={})
    assert direct_delivery.status_code == 409
    assert client.get(f"/api/delivery/{delivery_id}").json() == before_invalid

    drivers = client.get("/api/delivery/drivers").json()
    assert len(drivers) >= 2
    first_driver, second_driver = drivers[:2]

    assigned = client.post(
        f"/api/delivery/{delivery_id}/assign",
        json={"driver_id": first_driver["id"]},
        headers={"Idempotency-Key": "assign-once"},
    )
    assert assigned.status_code == 200, assigned.text
    repeated_assign = client.post(
        f"/api/delivery/{delivery_id}/assign",
        json={"driver_id": first_driver["id"]},
        headers={"Idempotency-Key": "assign-once"},
    )
    assert repeated_assign.status_code == 200
    assert repeated_assign.json() == assigned.json()
    assert len(client.get(f"/api/delivery/{delivery_id}").json()["delivery"]["assignments"]) == 1
    conflicting_key = client.post(
        f"/api/delivery/{delivery_id}/assign",
        json={"driver_id": second_driver["id"]},
        headers={"Idempotency-Key": "assign-once"},
    )
    assert conflicting_key.status_code == 409
    assert len(client.get(f"/api/delivery/{delivery_id}").json()["delivery"]["assignments"]) == 1

    reassigned = client.post(f"/api/delivery/{delivery_id}/assign", json={"driver_id": second_driver["id"]})
    assert reassigned.status_code == 200, reassigned.text
    history = reassigned.json()["delivery"]["assignments"]
    assert len(history) == 2
    assert sum(assignment["status"] == "active" for assignment in history) == 1
    assert reassigned.json()["delivery"]["driver_id"] == second_driver["id"]

    departed = client.post(
        f"/api/delivery/{delivery_id}/callback",
        json={"status": "out_for_delivery", "callback_id": "driver-event-1"},
    )
    assert departed.status_code == 200, departed.text
    duplicate_departure = client.post(
        f"/api/delivery/{delivery_id}/callback",
        json={"status": "out_for_delivery", "callback_id": "driver-event-1"},
    )
    assert duplicate_departure.status_code == 200
    assert duplicate_departure.json() == departed.json()

    delivered = client.post(
        f"/api/delivery/{delivery_id}/callback",
        json={"status": "delivered", "callback_id": "driver-event-2"},
    )
    assert delivered.status_code == 200, delivered.text
    duplicate_delivered = client.post(
        f"/api/delivery/{delivery_id}/callback",
        json={"status": "delivered", "callback_id": "driver-event-2"},
    )
    assert duplicate_delivered.status_code == 200
    assert duplicate_delivered.json() == delivered.json()
    assert delivered.json()["delivery"]["status"] == "delivered"
    assert client.post(f"/api/delivery/{delivery_id}/assign", json={"driver_id": first_driver["id"]}).status_code == 409
    assert client.get(f"/api/orders/{oid}").json()["delivery"]["status"] == "delivered"


def test_paid_delivery_actions_remain_available_after_kitchen_served(client):
    oid, delivery_id = _pay_delivery(client)
    ticket_id = client.get(f"/api/orders/{oid}").json()["ticket"]["id"]

    assert client.post(f"/api/kitchen/{ticket_id}/start").status_code == 200
    assert client.post(f"/api/kitchen/{ticket_id}/ready").status_code == 200
    assert client.post(f"/api/kitchen/{ticket_id}/serve").status_code == 200
    assert client.get(f"/api/orders/{oid}").json()["order"]["status"] == "served"

    assigned = client.post(f"/api/delivery/{delivery_id}/assign", json={"driver_id": 1})
    assert assigned.status_code == 200, assigned.text
    departed = client.post(f"/api/delivery/{delivery_id}/out-for-delivery", json={})
    assert departed.status_code == 200, departed.text
    delivered = client.post(f"/api/delivery/{delivery_id}/delivered", json={})
    assert delivered.status_code == 200, delivered.text


def test_delivery_failure_and_cancel_paths_are_guarded(client):
    _, failed_id = _pay_delivery(client)
    assert client.post(f"/api/delivery/{failed_id}/assign", json={"driver_id": 1}).status_code == 200
    failed = client.post(f"/api/delivery/{failed_id}/failed", json={"reason": "Customer unavailable"})
    assert failed.status_code == 200, failed.text
    assert failed.json()["delivery"]["status"] == "failed"
    assert failed.json()["delivery"]["assignments"][0]["status"] == "failed"
    assert client.post(f"/api/delivery/{failed_id}/delivered", json={}).status_code == 409
    repeated = client.post(
        f"/api/delivery/{failed_id}/failed",
        json={"reason": "Customer unavailable"},
        headers={"Idempotency-Key": "failure-once"},
    )
    assert repeated.status_code == 409

    _, cancelled_id = _pay_delivery(client)
    cancelled = client.post(f"/api/delivery/{cancelled_id}/cancel", json={"reason": "Customer cancelled"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["delivery"]["status"] == "cancelled"
    assert cancelled.json()["delivery"]["assignments"] == []
    assert client.post(f"/api/delivery/{cancelled_id}/assign", json={"driver_id": 1}).status_code == 409


def test_delivery_failure_and_cancel_require_reason_and_preserve_state(client):
    _, delivery_id = _pay_delivery(client)
    before = client.get(f"/api/delivery/{delivery_id}").json()
    assert client.post(f"/api/delivery/{delivery_id}/failed", json={}).status_code == 422
    assert client.post(f"/api/delivery/{delivery_id}/cancel", json={"reason": "   "}).status_code == 422
    assert client.get(f"/api/delivery/{delivery_id}").json() == before


@pytest.mark.parametrize(
    ("action", "event_type"),
    [("failed", "delivery.failed"), ("cancel", "delivery.cancelled")],
)
def test_delivery_reason_is_not_written_to_audit_detail(client, action, event_type):
    _, delivery_id = _pay_delivery(client)
    reason = "Leave at 44 Sensitive Road; call 09171234567"

    result = client.post(f"/api/delivery/{delivery_id}/{action}", json={"reason": reason})
    assert result.status_code == 200, result.text

    events = client.get("/api/audit-events").json()
    event = next(event for event in events if event["event_type"] == event_type)
    assert event["path"] == f"/api/delivery/{delivery_id}/{action}"
    assert event["detail"] == f"delivery_id={delivery_id}"
    assert reason not in event["detail"]


def test_delivery_audit_events_cover_creation_assignment_reassignment_and_callback(client):
    _, delivery_id = _pay_delivery(client)
    assert client.post(f"/api/delivery/{delivery_id}/assign", json={"driver_id": 1}).status_code == 200
    assert client.post(f"/api/delivery/{delivery_id}/assign", json={"driver_id": 2}).status_code == 200
    assert client.post(f"/api/delivery/{delivery_id}/out-for-delivery", json={}).status_code == 200
    assert client.post(f"/api/delivery/{delivery_id}/delivered", json={}).status_code == 200

    events = client.get("/api/audit-events").json()
    event_types = [event["event_type"] for event in events if event["event_type"].startswith("delivery.")]
    assert "delivery.created" in event_types
    assert "delivery.assigned" in event_types
    assert "delivery.reassigned" in event_types
    assert "delivery.out_for_delivery" in event_types
    assert "delivery.delivered" in event_types
    assert all(event["created_at"] for event in events)
    assert sum(event["event_type"] == "delivery.out_for_delivery" for event in events) == 1
    assert sum(event["event_type"] == "delivery.delivered" for event in events) == 1


def test_delivery_mutation_is_denied_to_viewer_when_optional_auth_is_enabled(client, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PROFILE", "local")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_BOOTSTRAP_USERNAME", "admin")
    monkeypatch.setenv("AUTH_BOOTSTRAP_PASSWORD", "admin-password")
    with TestClient(app) as authenticated_client:
        admin_login = authenticated_client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        assert admin_login.status_code == 200, admin_login.text
        admin_csrf = authenticated_client.cookies.get("local_csrf")
        created_user = authenticated_client.post(
            "/api/auth/users",
            json={"username": "viewer", "password": "viewer-password", "roles": ["viewer"]},
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert created_user.status_code == 200, created_user.text
        viewer = TestClient(app)
        try:
            login = viewer.post("/api/auth/login", json={"username": "viewer", "password": "viewer-password"})
            assert login.status_code == 200, login.text
            denied = viewer.post(
                "/api/delivery/1/assign",
                json={"driver_id": 1},
                headers={"X-CSRF-Token": viewer.cookies.get("local_csrf")},
            )
            assert denied.status_code == 403
        finally:
            viewer.close()

    with db.connect() as connection:
        assert connection.execute(
            "SELECT 1 FROM audit_events WHERE event_type='auth.denied' AND path='/api/delivery/1/assign'"
        ).fetchone()
