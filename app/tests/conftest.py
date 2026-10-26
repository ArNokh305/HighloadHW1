import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def fresh_storage(monkeypatch):
    """Каждому тесту -- пустое хранилище.

    storage -- глобальный объект модуля, и без сброса тесты влияли бы
    друг на друга (например, id зависели бы от порядка запуска).
    Обработчики ищут `storage` в модуле в момент вызова, поэтому
    подмена атрибута модуля работает.
    """
    storage = main.InMemoryStorage()
    monkeypatch.setattr(main, "storage", storage)
    return storage


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c
