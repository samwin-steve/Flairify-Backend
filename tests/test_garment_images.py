from types import SimpleNamespace

from app.auth import Principal, principal
from app.main import app
from app.services import ai, garment_images, jobs, media, wardrobe
from app.store import store
from tests.test_try_on import picture
from tests.test_try_on import signed as signed  # noqa: PLC0414 - export the shared pytest fixture


def upload(c):
    return c.post(
        "/api/photos", data={"kind": "full_body"}, files={"file": ("me.jpg", picture(), "image/jpeg")}
    ).json()


def test_automatic_shop_image_keeps_evidence_and_server_owned_provenance(signed):
    c, owner, calls = signed
    photo = upload(c)
    item = c.get("/api/wardrobe").json()["items"][0]
    assert item["shop_image_status"] == "succeeded"
    assert item["generated_image"] != item["image"]
    assert item["evidence"] == "original_crop" and not item["confirmed"]
    assert item["brand"] is None and item["material"] is None and item["size"] is None
    assert calls[0]["config"].image_config.image_size == "1K"
    assert calls[0]["contents"][0].inline_data.data == media.read(owner, item["image"][6:])[0]
    # Repeat extraction and repeat requests reuse completed work, without a second model call.
    wardrobe.extract(owner, [photo["source_photo_id"]], lambda stage: None)
    assert c.post(f"/api/wardrobe/{item['id']}/shop-image").json()["status"] == "succeeded"
    assert len(calls) == 1
    edited = {
        **item,
        "name": "My corrected shirt",
        "confirmed": True,
        "generated_image": "media:forged",
        "generated_image_model": "forged",
        "image": "media:another-user",
        "shop_image_job_id": "forged",
    }
    saved = c.put(f"/api/wardrobe/{item['id']}", json=edited).json()
    assert saved["name"] == "My corrected shirt" and saved["confirmed"]
    for field in ("generated_image", "generated_image_model", "image", "shop_image_job_id"):
        assert saved[field] == item[field]
    assert c.get("/api/media/" + item["generated_image"][6:]).status_code == 200
    app.dependency_overrides[principal] = lambda: Principal("different-user")
    assert c.get("/api/media/" + item["generated_image"][6:]).status_code == 404
    assert c.post(f"/api/wardrobe/{item['id']}/shop-image").status_code == 404
    app.dependency_overrides[principal] = lambda: Principal(owner)
    c.delete("/api/photos/full_body")
    for field in ("generated_image", "image"):
        assert c.get("/api/media/" + item[field][6:]).status_code == 404


def test_image_failure_does_not_block_review_and_retry_is_real(signed, monkeypatch):
    c, _owner, _calls = signed
    provider = ai.client

    class NoImage:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @property
        def models(self):
            return self

        def generate_content(self, **kwargs):
            return SimpleNamespace(parts=[])

    monkeypatch.setattr(ai, "client", lambda **kwargs: NoImage())
    upload(c)
    item = c.get("/api/wardrobe").json()["items"][0]
    assert item["generated_image"] is None and item["shop_image_status"] == "failed"
    assert "no garment image" in item["shop_image_error"]
    assert c.get("/api/media/" + item["image"][6:]).status_code == 200
    assert c.put(f"/api/wardrobe/{item['id']}", json={**item, "confirmed": True}).status_code == 200
    profile = c.get("/api/profile").json()
    for key in ("admin", "demo", "seller"):
        profile.pop(key, None)
    c.put("/api/profile", json={**profile, "clothing_size": "M", "shoe_size": "39"})
    assert c.post("/api/onboarding/complete").status_code == 200
    monkeypatch.setattr(ai, "client", provider)
    assert c.post(f"/api/jobs/{item['shop_image_job_id']}/retry").status_code == 200
    updated = c.get("/api/wardrobe").json()["items"][0]
    assert updated["generated_image"] and updated["confirmed"]


def test_cancelled_image_cannot_reappear_after_model_returns(signed, monkeypatch):
    c, owner, _calls = signed
    monkeypatch.setattr(jobs, "enqueue", lambda *args, **kwargs: None)
    photo = upload(c)
    wardrobe.extract(owner, [photo["source_photo_id"]], lambda stage: None)
    item = store().list("wardrobe", owner)[0]
    original = garment_images.generate

    def generate_then_cancel(*args):
        result = original(*args)
        assert c.delete(f"/api/jobs/{item['shop_image_job_id']}").status_code == 200
        return result

    monkeypatch.setattr(garment_images, "generate", generate_then_cancel)
    jobs.process(owner, item["shop_image_job_id"])
    current = c.get("/api/wardrobe").json()["items"][0]
    assert current["generated_image"] is None and current["shop_image_status"] == "cancelled"
    assert len(store().list("media", owner)) == 3  # original, processing photo, crop


def test_consent_rechecked_when_queued(signed, monkeypatch):
    c, owner, calls = signed
    monkeypatch.setattr(jobs, "enqueue", lambda *args, **kwargs: None)
    photo = upload(c)
    wardrobe.extract(owner, [photo["source_photo_id"]], lambda stage: None)
    item = store().list("wardrobe", owner)[0]
    profile = store().get("profiles", owner, "me")
    profile["consent"]["ai_photo_processing"] = False
    store().put("profiles", owner, "me", profile)
    jobs.process(owner, item["shop_image_job_id"])
    assert calls == []
    assert c.post(f"/api/wardrobe/{item['id']}/shop-image").status_code == 409
    assert c.get("/api/wardrobe").json()["items"][0]["shop_image_status"] == "failed"


def test_original_only_deletes_generated_media_but_preserves_crop(signed):
    c, _owner, _ = signed
    upload(c)
    item = c.get("/api/wardrobe").json()["items"][0]
    assert c.delete(f"/api/jobs/{item['shop_image_job_id']}").status_code == 200
    assert c.get("/api/media/" + item["generated_image"][6:]).status_code == 404
    assert c.get("/api/media/" + item["image"][6:]).status_code == 200
    assert c.get("/api/wardrobe").json()["items"][0]["generated_image"] is None
