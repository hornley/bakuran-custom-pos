import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "app.db")
    db.initialize(reset=True)
    with TestClient(app) as test_client:
        yield test_client
