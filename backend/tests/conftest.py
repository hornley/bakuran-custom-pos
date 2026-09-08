import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture(autouse=True)
def trusted_local_operator_bypass(monkeypatch):
    # Existing operator-flow tests model the explicitly opted-in local-dev path.
    monkeypatch.setenv("AUTH_LOCAL_DEV_BYPASS", "true")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "app.db")
    db.initialize(reset=True)
    with TestClient(app) as test_client:
        yield test_client
