import itertools
import os
import threading
import random

from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel

from metrics import setup_metrics, POD_ID, DATACENTER


class ItemIn(BaseModel):
    name: str
    description: str | None = None


class Item(ItemIn):
    id: int


class InMemoryStorage:
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

FAIL_RATE = float(os.getenv("FAIL_RATE", 0.0))

def inject_failure_dependency():
    if random.random() < FAIL_RATE:
        raise HTTPException(
            status_code=500,
            detail="Dependency-based error injection triggered."
        )


@app.post("/items", status_code=status.HTTP_201_CREATED, response_model=Item,dependencies=[Depends(inject_failure_dependency)])
def create_item(data: ItemIn) -> Item:
    return storage.create(data)


@app.get("/items/{item_id}", response_model=Item,dependencies=[Depends(inject_failure_dependency)])
def get_item(item_id: int) -> Item:
    item = storage.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.put("/items/{item_id}", response_model=Item,dependencies=[Depends(inject_failure_dependency)])
def update_item(item_id: int, data: ItemIn) -> Item:
    item = storage.update(item_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "pod": POD_ID, "datacenter": DATACENTER}
