import io
import json
from PIL import Image
import pytest
from app.main import app
from app.auth import Principal, principal
from app.store import store
from app.services import inventory, indexing


@pytest.fixture
def signed(client):
    who = [Principal("seller-a", seller=True, email="seller@example.invalid")]
    app.dependency_overrides[principal] = lambda: who[0]
    inventory.seed_catalog("retailer")
    yield client, who
    app.dependency_overrides.clear()


def create_product(c, name="Seller linen jacket"):
    shop = {"id": "seller-store", "name": "Seller studio", "address": "Mumbai", "sample": False}
    assert c.put("/api/admin/stores/seller-store", json=shop).status_code == 200
    out = io.BytesIO()
    Image.new("RGB", (200, 300), "pink").save(out, "JPEG")
    image = c.post("/api/admin/images", files={"file": ("jacket.jpg", out.getvalue(), "image/jpeg")}).json()[
        "image"
    ]
    assert c.get("/api/catalog/media/" + image[6:]).status_code == 200
    product = {
        "id": "seller-jacket",
        "sku": "SELLER-01",
        "name": name,
        "category": "jacket",
        "price": 1200,
        "image": image,
        "seller_id": "forged-owner",
        "ai_attributes": {"fabric": "invented"},
        "variants": [
            {
                "id": "seller-m",
                "size": "M",
                "colour": "Pink",
                "stock": [{"store_id": "seller-store", "quantity": 3}],
            }
        ],
    }
    r = c.post("/api/admin/products", json=product)
    assert r.status_code == 200, r.text
    return product


def test_seller_create_upload_index_ownership_and_mock_inbox(signed):
    c, who = signed
    product = create_product(c)
    item = next(p for p in c.get("/api/catalog").json()["products"] if p["id"] == product["id"])
    assert item["indexed"] and item["seller_id"] == "seller-a" and not item["sample"]
    assert item["ai_attributes"] == {}
    assert c.post("/api/admin/products", json=product).status_code == 409
    who[0] = Principal("seller-b", seller=True)
    assert c.get("/api/admin/catalog").json()["products"] == []
    assert c.put("/api/admin/products/" + product["id"], json=product).status_code == 403
    forged = {**product, "id": "forged-image"}
    forged["variants"][0]["stock"][0]["store_id"] = "b-store"
    c.put("/api/admin/stores/b-store", json={"id": "b-store", "name": "B", "address": "Mumbai"})
    assert c.post("/api/admin/products", json=forged).status_code == 403
    assert (
        c.put(
            "/api/admin/stores/seller-store", json={"id": "seller-store", "name": "Hijack", "address": "X"}
        ).status_code
        == 403
    )
    who[0] = Principal("customer")
    assert c.post("/api/admin/products", json=product).status_code == 403
    data = {
        "items": [
            {
                "product_id": "seller-jacket",
                "variant_id": "seller-m",
                "store_id": "seller-store",
                "quantity": 2,
            }
        ],
        "expected_total": 2400,
        "request_key": "test-seller-order",
        "acknowledge_mock": True,
    }
    order = c.post("/api/orders", json=data)
    assert order.status_code == 200, order.text
    who[0] = Principal("seller-a", seller=True)
    assert c.get("/api/admin/orders").json()["orders"][0]["total"] == 2400
    assert c.get("/api/orders").json()["orders"] == []
    who[0] = Principal("seller-b", seller=True)
    assert c.get("/api/admin/orders").json()["orders"] == []
    who[0] = Principal("site-owner", admin=True)
    assert c.get("/api/admin/orders").json()["orders"][0]["id"] == order.json()["id"]


def test_seller_access_requires_owner_approval(signed):
    c, who = signed
    who[0] = Principal("requester", email="verified-token@example.invalid")
    assert c.post("/api/seller-access/request").json()["status"] == "pending"
    assert c.get("/api/admin/seller-requests").status_code == 403
    assert c.post("/api/admin/seller-requests/requester/approve").status_code == 403
    who[0] = Principal("owner", admin=True)
    assert (
        c.get("/api/admin/seller-requests").json()["requests"][0]["email"] == "verified-token@example.invalid"
    )
    assert c.post("/api/admin/seller-requests/requester/approve").status_code == 200
    assert store().get("seller_access", "system", "requester")["role"] == "seller"
    assert c.post("/api/admin/seller-requests/requester/revoke").status_code == 200
    assert store().get("seller_access", "system", "requester")["role"] == "revoked"


def test_archive_hides_product_from_search_and_checkout(signed):
    c, _ = signed
    product = create_product(c)
    product["active"] = False
    assert c.put("/api/admin/products/" + product["id"], json=product).status_code == 200
    assert all(p["id"] != product["id"] for p in c.get("/api/catalog").json()["products"])
    data = {
        "items": [
            {"product_id": product["id"], "variant_id": "seller-m", "store_id": "seller-store", "quantity": 1}
        ]
    }
    assert c.post("/api/orders/quote", json=data).status_code == 409


def test_indexing_does_not_overwrite_concurrent_stock_edit(signed, monkeypatch):
    c, _ = signed
    create_product(c)
    original = store().put

    def interleave(kind, owner, key, value):
        if kind == "search":
            current = store().get("products", owner, key)
            current["variants"][0]["stock"][0]["quantity"] = 0
            current["indexed"] = False
            original("products", owner, key, current)
        return original(kind, owner, key, value)

    current = store().get("products", "retailer", "seller-jacket")
    current["indexed"] = False
    original("products", "retailer", "seller-jacket", current)
    monkeypatch.setattr(store(), "put", interleave)
    indexing.index_products("retailer", ["seller-jacket"])
    current = store().get("products", "retailer", "seller-jacket")
    assert current["variants"][0]["stock"][0]["quantity"] == 0 and not current["indexed"]


def test_indexed_new_product_is_eligible_for_recommendations(signed):
    from app.models import UserProfile

    c, who = signed
    create_product(c)
    # Use a catalogue containing this seller listing to make the eligibility assertion deterministic.
    for p in store().list("products", "retailer"):
        if p["id"] != "seller-jacket" and p["category"] != "shoes":
            store().delete("products", "retailer", p["id"])
    who[0] = Principal("customer")
    inventory.seed_wardrobe("customer")
    for w in store().list("wardrobe", "customer"):
        w["confirmed"] = True
        store().put("wardrobe", "customer", w["id"], w)
    profile = UserProfile(clothing_size="M", shoe_size="39", onboarding_complete=True).model_dump()
    store().put("profiles", "customer", "me", profile)
    response = c.post("/api/chat", json={"message": "A jacket for Mumbai work under ₹5,000"})
    assert response.status_code == 200, response.text
    assert any(p["id"] == "seller-jacket" for look in response.json()["outfits"] for p in look["products"])


def test_seller_shirt_can_replace_owned_top_when_requested(signed):
    from app.models import UserProfile

    c, who = signed
    product = create_product(c, "Seller white shirt")
    product["category"] = "top"
    assert c.put("/api/admin/products/" + product["id"], json=product).status_code == 200
    who[0] = Principal("customer")
    inventory.seed_wardrobe("customer")
    for w in store().list("wardrobe", "customer"):
        w["confirmed"] = True
        store().put("wardrobe", "customer", w["id"], w)
    store().put(
        "profiles",
        "customer",
        "me",
        UserProfile(clothing_size="M", shoe_size="39", onboarding_complete=True).model_dump(),
    )
    result = c.post("/api/chat", json={"message": "Find a new white shirt under ₹5,000"}).json()
    matched = [o for o in result["outfits"] if any(p["id"] == "seller-jacket" for p in o["products"])]
    assert matched and all(o["total"] <= 5000 and o["complete"] for o in matched)
    assert all(all(w["category"] != "top" for w in o["owned"]) for o in matched)
