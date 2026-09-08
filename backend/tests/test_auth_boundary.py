import pytest

from app import auth


def enable_local_auth(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PROFILE", "local")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_BOOTSTRAP_USERNAME", "desk-admin")
    monkeypatch.setenv("AUTH_BOOTSTRAP_PASSWORD", "correct-horse-battery-staple")
    auth.initialize_auth()


def test_default_disabled_auth_allows_legacy_operator_mutations_with_explicit_dev_bypass(client, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PROFILE", "disabled")
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_LOCAL_DEV_BYPASS", "true")

    response = client.post("/api/counter/orders", json={})

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/counter/orders"),
        ("put", "/api/auth/users/1/roles"),
        ("patch", "/api/orders/1"),
        ("delete", "/api/orders/1/lines/1"),
    ],
)
def test_default_disabled_auth_rejects_every_operator_mutation_without_dev_bypass(client, monkeypatch, method, path):
    monkeypatch.setattr(auth, "AUTH_PROFILE", "disabled")
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_LOCAL_DEV_BYPASS", raising=False)

    response = client.request(method, path, json={})

    assert response.status_code == 401
    assert "AUTH_LOCAL_DEV_BYPASS" in response.json()["detail"]


def test_default_disabled_auth_keeps_health_and_auth_routes_public(client, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PROFILE", "disabled")
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_LOCAL_DEV_BYPASS", raising=False)

    health = client.get("/api/health")
    session = client.get("/api/auth/session")
    login = client.post(
        "/api/auth/login",
        json={"username": "desk-admin", "password": "correct-horse-battery-staple"},
    )
    logout = client.post("/api/auth/logout")

    assert health.status_code == 200
    assert session.status_code == 200
    assert session.json() == {"authenticated": False, "auth_enabled": False}
    assert login.status_code == 200
    assert login.json() == {"authenticated": False, "auth_enabled": False}
    assert logout.status_code == 200


def test_default_disabled_auth_keeps_customer_qr_endpoint_public(client, monkeypatch):
    opened = client.post("/api/tables/2/open")
    assert opened.status_code == 200
    token = opened.json()["session"]["qr_token"]
    monkeypatch.setattr(auth, "AUTH_PROFILE", "disabled")
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_LOCAL_DEV_BYPASS", raising=False)

    response = client.get(f"/api/customer/tables/{token}")
    order = client.post(
        f"/api/customer/tables/{token}/orders",
        headers={"Idempotency-Key": "public-boundary"},
        json={"customer_name": "Mika", "lines": [{"menu_item_id": 1, "quantity": 1}]},
    )

    assert response.status_code == 200
    assert response.json()["table"]["code"] == "T02"
    assert order.status_code == 200
    assert order.json()["order"]["status"] == "awaiting_payment"


def test_enabled_auth_login_does_not_require_csrf(client, monkeypatch):
    enable_local_auth(monkeypatch)

    response = client.post(
        "/api/auth/login",
        json={"username": "desk-admin", "password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert client.cookies.get("local_session")
    assert client.cookies.get("local_csrf")


def test_enabled_auth_rejects_operator_mutation_without_csrf(client, monkeypatch):
    enable_local_auth(monkeypatch)
    login = client.post(
        "/api/auth/login",
        json={"username": "desk-admin", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200

    response = client.post("/api/counter/orders", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed."


def test_enabled_auth_accepts_operator_mutation_with_login_csrf_pair(client, monkeypatch):
    enable_local_auth(monkeypatch)
    login = client.post(
        "/api/auth/login",
        json={"username": "desk-admin", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/counter/orders",
        headers={"X-CSRF-Token": client.cookies.get("local_csrf")},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["order"]["order_channel"] == "counter"
