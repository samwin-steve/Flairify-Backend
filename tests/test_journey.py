import io
import json
from PIL import Image
from app.store import store
from app.services import inventory


def image_bytes():
    out = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(out, "JPEG")
    return out.getvalue()


def test_onboarding_gate(client, session):
    _, h = session
    assert client.post("/api/chat", headers=h, json={"message": "Mumbai, ₹5,000"}).status_code == 409
    client.post("/api/wardrobe/sample", headers=h)
    assert client.post("/api/onboarding/complete", headers=h).status_code == 409


def test_budget_stock_and_grounding(client, onboarded):
    data, h = onboarded
    r = client.post(
        "/api/chat",
        headers=h,
        json={"message": "I’m going to Mumbai for work for three days. Walking a lot. Budget ₹5,000."},
    )
    assert r.status_code == 200, r.text
    outfits = r.json()["outfits"]
    assert outfits
    ids = {w["id"] for w in client.get("/api/wardrobe", headers=h).json()["items"] if w["confirmed"]}
    for outfit in outfits:
        assert outfit["total"] == sum(p["price"] for p in outfit["products"]) <= 5000
        assert set(w["id"] for w in outfit["owned"]) <= ids
        assert outfit["complete"] is True
        assert all(p["availability"]["quantity"] > 0 and p["id"] != "p-soldout" for p in outfit["products"])
        assert all(
            p["availability"]["size"] == ("39" if p["category"] == "shoes" else "M")
            for p in outfit["products"]
        )
        assert outfit["assessment"]["source"] == "rule"
        assert "together" in outfit["explanation"]


def test_followup_preserves_occasion_and_cheaper(client, onboarded):
    _, h = onboarded
    first = client.post("/api/chat", headers=h, json={"message": "Mumbai work trip under ₹5,000"}).json()
    second = client.post(
        "/api/chat",
        headers=h,
        json={"message": "Something cheaper", "conversation_id": first["conversation"]["id"]},
    ).json()
    assert second["intent"]["budget"] == 3750
    assert "Mumbai" in second["intent"]["occasion"]
    assert all(o["total"] <= 3750 for o in second["outfits"])


def test_another_jacket_excludes_previous(client, onboarded):
    _, h = onboarded
    a = client.post("/api/chat", headers=h, json={"message": "Mumbai under ₹5,000"}).json()
    previous = {p["id"] for p in a["outfits"][0]["products"] if p["category"] == "jacket"}
    b = client.post(
        "/api/chat",
        headers=h,
        json={"message": "Show another jacket", "conversation_id": a["conversation"]["id"]},
    ).json()
    assert all(
        p["id"] not in previous for o in b["outfits"] for p in o["products"] if p["category"] == "jacket"
    )


def test_user_isolation_and_media(client, onboarded):
    data, h = onboarded
    photo = client.post(
        "/api/photos", headers=h, files={"file": ("photo.jpg", image_bytes(), "image/jpeg")}
    ).json()
    other = client.post("/api/auth/demo").json()
    h2 = {"Authorization": "Bearer " + other["token"]}
    assert client.get("/api/wardrobe", headers=h2).json()["items"] == []
    assert client.get("/api/media/" + photo["media_id"], headers=h2).status_code == 404
    assert client.get("/api/media/" + photo["media_id"]).status_code == 401
    assert client.delete("/api/photos/" + photo["id"], headers=h2).status_code == 404
    assert client.get("/api/media/" + photo["media_id"], headers=h).status_code == 200
    assert (
        client.get("/api/wardrobe", headers={"Authorization": "Bearer " + data["user_id"]}).status_code == 401
    )


def test_upload_manual_review_and_deletion(client, session):
    _, h = session
    p = client.post(
        "/api/photos", headers=h, files={"file": ("photo.jpg", image_bytes(), "image/jpeg")}
    ).json()
    job = client.post("/api/wardrobe/import", headers=h, json={"photo_ids": [p["id"]]}).json()
    final = next(j for j in client.get("/api/jobs", headers=h).json()["jobs"] if j["id"] == job["id"])
    assert final["status"] == "succeeded"
    item = client.get("/api/wardrobe", headers=h).json()["items"][0]
    assert item["category"] == "unknown" and not item["confirmed"]
    item["confirmed"] = True
    assert client.put("/api/wardrobe/" + item["id"], headers=h, json=item).status_code == 422
    item.update(name="My shirt", category="top", colour="White")
    assert client.put("/api/wardrobe/" + item["id"], headers=h, json=item).status_code == 200
    assert client.post("/api/onboarding/complete", headers=h).status_code == 200
    original = p["original_media_id"]
    assert client.get("/api/media/" + original, headers=h).content == image_bytes()
    crop_id = item["image"][6:]
    assert client.delete("/api/photos/" + p["id"], headers=h).status_code == 200
    assert client.get("/api/wardrobe", headers=h).json()["items"] == []
    assert client.get("/api/media/" + crop_id, headers=h).status_code == 404
    assert client.get("/api/media/" + original, headers=h).status_code == 404
    assert client.get("/api/media/" + p["media_id"], headers=h).status_code == 404


def test_bad_upload_and_group_selection(client, session):
    _, h = session
    assert (
        client.post(
            "/api/photos", headers=h, files={"file": ("x.jpg", b"not image", "image/jpeg")}
        ).status_code
        == 422
    )
    p = client.post("/api/photos", headers=h, files={"file": ("x.jpg", image_bytes(), "image/jpeg")}).json()
    assert (
        client.patch(
            "/api/photos/" + p["id"],
            headers=h,
            json={"group_photo": True, "person_box": {"x": 0, "y": 0, "width": 1, "height": 1}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/photos/" + p["id"],
            headers=h,
            json={"group_photo": True, "person_box": {"x": 0.2, "y": 0.1, "width": 0.4, "height": 0.8}},
        ).status_code
        == 200
    )


def test_honest_generation_and_dedup(client, onboarded):
    _, h = onboarded
    outfit = client.post("/api/chat", headers=h, json={"message": "Mumbai under ₹5,000"}).json()["outfits"][0]
    payload = {
        "outfit_id": outfit["id"],
        "product_id": outfit["products"][0]["id"],
        "request_key": "same-request-key",
    }
    j = client.post("/api/generate/try_on", headers=h, json=payload).json()
    other = client.post("/api/generate/try_on", headers=h, json=payload).json()
    assert j["id"] == other["id"]
    final = next(x for x in client.get("/api/jobs", headers=h).json()["jobs"] if x["id"] == j["id"])
    assert final["status"] == "failed" and final["result"] is None
    assert "not connected" in final["error"]
    assert (
        client.post(
            "/api/generate/video", headers=h, json={"source_job_id": j["id"], "request_key": "video-test-key"}
        ).status_code
        == 409
    )


def test_admin_import_and_stock(client, onboarded):
    data, h = onboarded
    assert client.get("/api/admin/catalog", headers=h).status_code == 403
    assert client.post("/api/admin/unlock", headers=h, json={"key": "wrong"}).status_code == 403
    assert client.post("/api/admin/unlock", headers=h, json={"key": "test-admin-key"}).status_code == 200
    original = client.get("/api/admin/catalog", headers=h).json()["products"][0]
    product = {
        **original,
        "id": "new-arrival",
        "sku": "NEW-1",
        "name": "New arrival jacket",
        "indexed": False,
    }
    r = client.post(
        "/api/admin/import",
        headers=h,
        files={"file": ("catalogue.json", json.dumps([product]).encode(), "application/json")},
    )
    assert r.status_code == 200, r.text
    assert any(
        p["id"] == "new-arrival"
        for p in client.get("/api/catalog?q=new+arrival", headers=h).json()["products"]
    )
    for v in product["variants"]:
        for stock in v["stock"]:
            stock["quantity"] = 0
    assert client.put("/api/admin/products/new-arrival", headers=h, json=product).status_code == 200
    assert inventory.available(store().get("products", data["user_id"], "new-arrival"), "M") == []


def test_remote_image_import_rejected(client, onboarded):
    _, h = onboarded
    client.post("/api/admin/unlock", headers=h, json={"key": "test-admin-key"})
    p = client.get("/api/admin/catalog", headers=h).json()["products"][0]
    p["image"] = "http://169.254.169.254/computeMetadata/v1/"
    assert client.put("/api/admin/products/" + p["id"], headers=h, json=p).status_code == 422


def test_consent_and_saved_invalidation(client, onboarded):
    _, h = onboarded
    outfit = client.post("/api/chat", headers=h, json={"message": "Mumbai under ₹5,000"}).json()["outfits"][0]
    assert client.post("/api/saved/" + outfit["id"], headers=h).status_code == 200
    assert len(client.get("/api/saved", headers=h).json()["looks"]) == 1
    client.delete("/api/wardrobe/" + outfit["owned"][0]["id"], headers=h)
    assert client.get("/api/saved", headers=h).json()["looks"] == []
    profile = client.get("/api/profile", headers=h).json()
    profile.pop("admin")
    profile.pop("demo")
    profile["consent"]["remember_preferences"] = False
    client.put("/api/profile", headers=h, json=profile)
    result = client.get("/api/profile", headers=h).json()
    assert result["styles"] == [] and result["clothing_size"] == "" and result["shoe_size"] == ""


def test_size_not_inferred(client, onboarded):
    data, h = onboarded
    profile = store().get("profiles", data["user_id"], "me")
    profile.update(clothing_size="", shoe_size="")
    store().put("profiles", data["user_id"], "me", profile)
    result = client.post("/api/chat", headers=h, json={"message": "Find an outfit"}).json()
    assert not result["outfits"] and "sizes" in result["text"]


def test_nearby_distance_and_invalid_coords(client, session):
    _, h = session
    result = client.get("/api/stores?lat=19.0596&lon=72.8295", headers=h).json()["stores"]
    assert result[0]["id"] == "bandra" and result[0]["distance_km"] == 0
    assert "straight-line" in result[0]["distance_label"]
    assert client.get("/api/stores?lat=95&lon=200", headers=h).status_code == 422


def test_keep_my_shirt_preserves_previous_top(client, onboarded):
    _, h = onboarded
    first = client.post("/api/chat", headers=h, json={"message": "Mumbai under ₹5,000"}).json()
    top = next(w["id"] for w in first["outfits"][0]["owned"] if w["category"] == "top")
    next_turn = client.post(
        "/api/chat",
        headers=h,
        json={
            "message": "Keep my shirt, show another jacket",
            "conversation_id": first["conversation"]["id"],
        },
    ).json()
    assert next_turn["outfits"]
    assert all(top in {w["id"] for w in outfit["owned"]} for outfit in next_turn["outfits"])


def test_single_owned_top_fills_base_before_optional_layer(client, onboarded):
    data, headers = onboarded
    owner = data["user_id"]
    items = store().list("wardrobe", owner)
    top = next(w for w in items if w["category"] == "top")
    for item in items:
        if item["id"] != top["id"]:
            store().delete("wardrobe", owner, item["id"])
    result = client.post("/api/chat", headers=headers, json={"message": "Mumbai work under ₹5,000"}).json()
    assert result["outfits"]
    for outfit in result["outfits"]:
        assert outfit["complete"] and outfit["total"] <= 5000
        assert {w["id"] for w in outfit["owned"]} == {top["id"]}
        assert {"bottom", "shoes"} <= {p["category"] for p in outfit["products"]}
    for product in store().list("products", owner):
        if product["category"] == "bottom":
            for variant in product["variants"]:
                for stock in variant["stock"]:
                    stock["quantity"] = 0
            store().put("products", owner, product["id"], product)
    unavailable = client.post(
        "/api/chat", headers=headers, json={"message": "Mumbai work under ₹5,000"}
    ).json()
    assert unavailable["outfits"] == []


def test_existing_jacket_is_reused_without_upselling(client, onboarded):
    from app.models import WardrobeItem

    data, headers = onboarded
    jacket = WardrobeItem(name="My existing jacket", category="jacket", colour="Navy", confirmed=True)
    store().put("wardrobe", data["user_id"], jacket.id, jacket.model_dump(mode="json"))
    result = client.post("/api/chat", headers=headers, json={"message": "Mumbai work under ₹5,000"}).json()
    assert result["outfits"]
    for outfit in result["outfits"]:
        assert jacket.id in {w["id"] for w in outfit["owned"]}
        assert all(p["category"] != "jacket" for p in outfit["products"])
