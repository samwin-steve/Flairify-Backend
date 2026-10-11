import io
from types import SimpleNamespace
import pytest
from PIL import Image
from app.main import app
from app.auth import Principal, principal
from app.config import settings
from app.store import store
from app.models import UserProfile, Box
from app.services import ai, inventory, try_on


def picture():
    out = io.BytesIO()
    Image.new("RGB", (100, 160), "white").save(out, "JPEG")
    return out.getvalue()


@pytest.fixture
def signed(client, monkeypatch):
    monkeypatch.setenv("ENABLE_PAID_AI", "true")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("IMAGE_EDIT_MODEL", "gemini-3.1-flash-image")
    monkeypatch.setenv("ALLOW_SAMPLE_TRY_ON", "true")
    settings.cache_clear()
    owner = "signed-in-test-user"
    app.dependency_overrides[principal] = lambda: Principal(owner)
    inventory.seed_catalog("retailer")
    profile = UserProfile(consent={"remember_preferences": False, "ai_photo_processing": True})
    store().put("profiles", owner, "me", profile.model_dump())
    monkeypatch.setattr(
        ai,
        "detect",
        lambda raw: [
            ai.Detection(
                name="Visible white shirt",
                category="top",
                colour="white",
                pattern="solid",
                visible_details="buttons",
                box=Box(),
                uncertainty=[],
            )
        ],
    )
    calls = []

    class Provider:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @property
        def models(self):
            return self

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                parts=[SimpleNamespace(inline_data=SimpleNamespace(data=picture(), mime_type="image/jpeg"))]
            )

    monkeypatch.setattr(ai, "client", lambda **kwargs: Provider())
    yield client, owner, calls
    app.dependency_overrides.clear()


def test_full_body_upload_detects_garments_and_reuses_photo_for_preview(signed):
    c, owner, calls = signed
    ref = c.post(
        "/api/photos", data={"kind": "full_body"}, files={"file": ("me.jpg", picture(), "image/jpeg")}
    ).json()
    assert ref["source_photo_id"]
    wardrobe = c.get("/api/wardrobe").json()["items"]
    assert (
        len(wardrobe) == 1 and wardrobe[0]["name"] == "Visible white shirt" and not wardrobe[0]["confirmed"]
    )
    result = c.post(
        "/api/generate/try_on", json={"product_id": "p-shirt", "request_key": "image-generation-1"}
    ).json()
    job = next(j for j in c.get("/api/jobs").json()["jobs"] if j["id"] == result["id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["reference_media_id"] == ref["media_id"]
    assert job["result"]["provider"] == "google-gemini-image-edit"
    assert job["result"]["sample_product"] is True
    assert c.get("/api/media/" + job["result"]["media_id"]).status_code == 200
    assert len(calls) == 2 and all(c["model"] == "gemini-3.1-flash-image" for c in calls)
    # Opening wardrobe review does not repeat the already successful auto-analysis.
    before = len(c.get("/api/jobs").json()["jobs"])
    c.post("/api/wardrobe/import", json={"photo_ids": [ref["source_photo_id"]]})
    assert len(c.get("/api/jobs").json()["jobs"]) == before
    regen = c.post("/api/jobs/" + job["id"] + "/regenerate")
    assert regen.status_code == 200 and regen.json()["id"] != job["id"]
    assert c.delete("/api/photos/full_body").status_code == 200
    assert not c.get("/api/photos").json()["photos"]
    assert not c.get("/api/photos").json()["references"]
    assert c.get("/api/media/" + job["result"]["media_id"]).status_code == 404


def test_wardrobe_upload_becomes_reference_and_selection_starts_analysis(signed):
    c, owner, calls = signed
    photo = c.post("/api/photos", files={"file": ("me.jpg", picture(), "image/jpeg")}).json()
    assert c.get("/api/wardrobe").json()["items"] == []
    c.patch("/api/photos/" + photo["id"], json={"person_box": {"x": 0, "y": 0, "width": 1, "height": 1}})
    assert len(c.get("/api/wardrobe").json()["items"]) == 1
    r = c.post(
        "/api/generate/try_on",
        json={
            "product_id": "p-blazer",
            "reference_id": "photo:" + photo["id"],
            "request_key": "wardrobe-as-reference",
        },
    )
    assert r.status_code == 200
    job = next(j for j in c.get("/api/jobs").json()["jobs"] if j["id"] == r.json()["id"])
    assert job["status"] == "succeeded" and job["result"]["reference_media_id"] == photo["media_id"]
    assert any("Layer the selected jacket" in p for p in calls[-1]["contents"] if isinstance(p, str))


def test_try_on_validates_current_stock_and_reference_owner(signed):
    c, owner, calls = signed
    photo = c.post("/api/photos", files={"file": ("me.jpg", picture(), "image/jpeg")}).json()
    assert (
        c.post(
            "/api/generate/try_on",
            json={
                "product_id": "p-soldout",
                "reference_id": "photo:" + photo["id"],
                "request_key": "soldout-test",
            },
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/generate/try_on",
            json={
                "product_id": "p-shirt",
                "reference_id": "photo:some-other-users-photo",
                "request_key": "cross-user-test",
            },
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/generate/try_on",
            json={"product_id": "p-shirt", "variant_id": "wrong-variant", "request_key": "bad-size-test"},
        ).status_code
        == 409
    )
    assert calls == []


def test_consent_required_for_automatic_analysis_and_generation(signed):
    c, owner, calls = signed
    profile = store().get("profiles", owner, "me")
    profile["consent"]["ai_photo_processing"] = False
    store().put("profiles", owner, "me", profile)
    c.post("/api/photos", data={"kind": "full_body"}, files={"file": ("me.jpg", picture(), "image/jpeg")})
    assert c.get("/api/wardrobe").json()["items"] == []
    assert (
        c.post(
            "/api/generate/try_on", json={"product_id": "p-shirt", "request_key": "no-consent-test"}
        ).status_code
        == 409
    )
    assert calls == []


def test_catalogue_preview_support_is_an_allowlist(signed):
    c, _, _ = signed
    products = c.get("/api/catalog").json()["products"]
    assert next(p for p in products if p["id"] == "p-shirt")["try_on_supported"]
    assert not next(p for p in products if p["id"] == "p-dress")["try_on_supported"]
    forged = {**next(p for p in products if p["id"] == "p-shirt"), "image": "/images/../../etc/passwd"}
    assert try_on.sample_asset(forged) is None
