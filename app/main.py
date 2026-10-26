"""Простой CRUD-сервис с in-memory хранилищем.

Ручки:
    POST /items         -- создать запись (201)
    GET  /items/{id}    -- получить запись (404, если нет)
    PUT  /items/{id}    -- обновить запись (404, если нет)
    GET  /health        -- служебная, 200 когда сервис готов
"""

import itertools
import os
import threading

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from metrics import setup_metrics
# Пригодятся на этапе метрик: будут лейблами pod / datacenter.
POD_ID = os.getenv("POD_ID", "unknown")
DATACENTER = os.getenv("DATACENTER", "unknown")


class ItemIn(BaseModel):
    """Тело запроса для создания/обновления."""

    name: str
    description: str | None = None


class Item(ItemIn):
    """То, что возвращаем клиенту: тело + id."""

    id: int


class InMemoryStorage:
    """Хранилище на словаре.

    Lock нужен потому, что FastAPI выполняет обычные (def, не async def)
    обработчики в пуле потоков -- несколько запросов могут одновременно
    читать/писать словарь и счетчик id.
    """

    def __init__(self) -> None:
        self._items: dict[int, Item] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def create(self, data: ItemIn) -> Item:
        with self._lock:
            item = Item(id=next(self._ids), **data.model_dump())
            self._items[item.id] = item
            return item

    def get(self, item_id: int) -> Item | None:
        with self._lock:
            return self._items.get(item_id)

    def update(self, item_id: int, data: ItemIn) -> Item | None:
        with self._lock:
            if item_id not in self._items:
                return None
            item = Item(id=item_id, **data.model_dump())
            self._items[item_id] = item
            return item


app = FastAPI(title="items-service")
setup_metrics(app)
storage = InMemoryStorage()


@app.post("/items", status_code=status.HTTP_201_CREATED, response_model=Item)
def create_item(data: ItemIn) -> Item:
    return storage.create(data)


@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    item = storage.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.put("/items/{item_id}", response_model=Item)
def update_item(item_id: int, data: ItemIn) -> Item:
    item = storage.update(item_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "pod": POD_ID, "datacenter": DATACENTER}
