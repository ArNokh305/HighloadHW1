import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def fresh_storage(monkeypatch):
    storage = main.InMemoryStorage()
    monkeypatch.setattr(main, "storage", storage)
    return storage


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c
