from fastapi.testclient import TestClient

from app import db
from app.main import app


def csrf_headers(client):
    return {"X-CSRF-Token": client.cookies["local_csrf"]}


def test_tax_configuration_requires_manager_or_admin_when_local_auth_is_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "auth.db")
    monkeypatch.setenv("AUTH_PROFILE", "local")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_BOOTSTRAP_USERNAME", "admin")
    monkeypatch.setenv("AUTH_BOOTSTRAP_PASSWORD", "admin-password")
    db.initialize(reset=True)

    with TestClient(app) as client:
        admin_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin-password"},
        )
        assert admin_login.status_code == 200
        assert client.post(
            "/api/tax/configuration",
            json={
                "name": "VAT",
                "rate": "10",
                "policy": "exclusive",
                "effective_from": "2020-01-01",
            },
            headers=csrf_headers(client),
        ).status_code == 201

        created = client.post(
            "/api/auth/users",
            json={"username": "operator", "password": "operator-password", "roles": ["operator"]},
            headers=csrf_headers(client),
        )
        assert created.status_code == 200
        assert client.post("/api/auth/logout", headers=csrf_headers(client)).status_code == 200
        operator_login = client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "operator-password"},
        )
        assert operator_login.status_code == 200
        denied = client.post(
            "/api/tax/configuration",
            json={
                "name": "Reduced VAT",
                "rate": "5",
                "policy": "exclusive",
                "effective_from": "2030-01-01",
            },
            headers=csrf_headers(client),
        )
        assert denied.status_code == 403
