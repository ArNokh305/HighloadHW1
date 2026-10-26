# ---------- /health ----------

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- POST /items ----------

def test_create_returns_201_and_item(client):
    r = client.post("/items", json={"name": "apple", "description": "red"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "apple"
    assert body["description"] == "red"
    assert isinstance(body["id"], int)


def test_create_assigns_unique_ids(client):
    ids = {client.post("/items", json={"name": f"n{i}"}).json()["id"] for i in range(5)}
    assert len(ids) == 5


def test_create_without_required_field_is_422(client):
    r = client.post("/items", json={"description": "no name"})
    assert r.status_code == 422


# ---------- GET /items/{id} ----------

def test_get_existing_item(client):
    created = client.post("/items", json={"name": "apple"}).json()
    r = client.get(f"/items/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_missing_item_is_404(client):
    assert client.get("/items/999").status_code == 404


def test_get_with_non_integer_id_is_422(client):
    assert client.get("/items/abc").status_code == 422


# ---------- PUT /items/{id} ----------

def test_update_existing_item(client):
    item_id = client.post("/items", json={"name": "old"}).json()["id"]

    r = client.put(f"/items/{item_id}", json={"name": "new", "description": "d"})
    assert r.status_code == 200
    assert r.json() == {"id": item_id, "name": "new", "description": "d"}

    # Изменение действительно сохранилось.
    assert client.get(f"/items/{item_id}").json()["name"] == "new"


def test_update_missing_item_is_404(client):
    assert client.put("/items/999", json={"name": "x"}).status_code == 404


def test_update_with_invalid_body_is_422(client):
    item_id = client.post("/items", json={"name": "x"}).json()["id"]
    assert client.put(f"/items/{item_id}", json={}).status_code == 422

