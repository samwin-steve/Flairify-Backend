import copy
from app.store import store


def selection(client, h):
    product = next(
        p
        for p in client.get("/api/catalog", headers=h).json()["products"]
        if any(s["quantity"] for v in p["variants"] for s in v["stock"])
    )
    variant = next(v for v in product["variants"] if any(s["quantity"] for s in v["stock"]))
    stock = next(s for s in variant["stock"] if s["quantity"])
    return product, {
        "items": [
            {
                "product_id": product["id"],
                "variant_id": variant["id"],
                "store_id": stock["store_id"],
                "quantity": 1,
            }
        ]
    }


def checkout(client, h, data, key="test-checkout-123"):
    quote = client.post("/api/orders/quote", headers=h, json=data)
    assert quote.status_code == 200, quote.text
    return {**data, "expected_total": quote.json()["total"], "request_key": key, "acknowledge_mock": True}


def test_direct_order_without_wardrobe_is_persisted_and_idempotent(client, session):
    identity, h = session
    product, data = selection(client, h)
    body = checkout(client, h, data)
    first = client.post("/api/orders", headers=h, json=body)
    assert first.status_code == 200, first.text
    order = first.json()
    assert order["status"] == "mock_placed" and order["total"] == product["price"]
    assert order["payment_status"] == "not_required" and order["fulfillment_status"] == "not_scheduled"
    assert "request_fingerprint" not in order
    assert client.post("/api/orders", headers=h, json=body).json() == order
    assert client.get("/api/orders", headers=h).json()["orders"] == [order]
    assert client.get("/api/orders/" + order["id"], headers=h).json() == order
    assert store().get("products", identity["user_id"], product["id"])["variants"] == product["variants"]
    assert client.get("/api/wardrobe", headers=h).json()["items"] == []
    other = client.post("/api/auth/demo").json()
    h2 = {"Authorization": "Bearer " + other["token"]}
    assert client.get("/api/orders/" + order["id"], headers=h2).status_code == 404
    assert client.get("/api/orders", headers=h2).json()["orders"] == []
    body["items"][0]["quantity"] = 2
    assert client.post("/api/orders", headers=h, json=body).status_code == 409


def test_checkout_rechecks_price_stock_and_requires_mock_acknowledgment(client, session):
    identity, h = session
    product, data = selection(client, h)
    body = checkout(client, h, data)
    assert client.post("/api/orders", headers=h, json={**body, "acknowledge_mock": False}).status_code == 422
    assert client.post("/api/orders", headers=h, json={**body, "expected_total": 0}).status_code == 409
    assert client.post("/api/orders/quote", headers=h, json={**data, "price": 1}).status_code == 422
    product["price"] += 100
    store().put("products", identity["user_id"], product["id"], product)
    assert client.post("/api/orders", headers=h, json=body).status_code == 409
    for v in product["variants"]:
        for s in v["stock"]:
            s["quantity"] = 0
    store().put("products", identity["user_id"], product["id"], product)
    assert client.post("/api/orders", headers=h, json=body).status_code == 409
    assert client.get("/api/orders", headers=h).json()["orders"] == []


def test_duplicate_cart_lines_cannot_bypass_stock(client, session):
    identity, h = session
    product, data = selection(client, h)
    for v in product["variants"]:
        for s in v["stock"]:
            s["quantity"] = 1
    store().put("products", identity["user_id"], product["id"], product)
    data["items"] *= 2
    assert client.post("/api/orders/quote", headers=h, json=data).status_code == 409
    for quantity in [0, -1, 11, True, 1.5, "2"]:
        bad = copy.deepcopy(data)
        bad["items"][0]["quantity"] = quantity
        assert client.post("/api/orders/quote", headers=h, json=bad).status_code == 422


def test_stylist_orders_only_new_pieces_and_requires_owned_look(client, onboarded):
    _, h = onboarded
    look = client.post("/api/chat", headers=h, json={"message": "Mumbai for work under ₹5,000"}).json()[
        "outfits"
    ][0]
    data = {
        "source": "stylist",
        "outfit_id": look["id"],
        "items": [
            {
                "product_id": p["id"],
                "variant_id": p["availability"]["variant_id"],
                "store_id": p["availability"]["store_id"],
                "quantity": 1,
            }
            for p in look["products"]
        ],
    }
    result = client.post("/api/orders", headers=h, json=checkout(client, h, data)).json()
    assert result["source"] == "stylist" and result["total"] == look["total"] <= 5000
    assert {i["product_id"] for i in result["items"]} == {p["id"] for p in look["products"]}
    data["outfit_id"] = "someone-elses-look"
    assert client.post("/api/orders/quote", headers=h, json=data).status_code == 409
