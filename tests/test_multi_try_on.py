from copy import deepcopy

import pytest
from test_try_on import picture

from app.config import settings
from app.models import WardrobeItem
from app.services import jobs, media, try_on
from app.store import store

pytest_plugins = ["test_try_on"]


def reference(owner):
    key = media.save(owner, picture())
    store().put("references", owner, "full_body", {"id": "full_body", "media_id": key})
    return key


def product(category, index=0):
    return [
        p
        for p in store().list("products", "retailer")
        if p["category"] == category
        and try_on.supports(p)
        and any(s["quantity"] for v in p["variants"] for s in v["stock"])
    ][index]


def selection(p):
    return {"kind": "product", "id": p["id"]}


def owned(owner, category="top"):
    item = WardrobeItem(
        name="My confirmed shirt",
        category=category,
        confirmed=True,
        image="media:" + media.save(owner, picture()),
    ).model_dump(mode="json")
    store().put("wardrobe", owner, item["id"], item)
    return {"kind": "wardrobe", "id": item["id"]}


def job(c, response):
    assert response.status_code == 200, response.text
    return next(j for j in c.get("/api/jobs").json()["jobs"] if j["id"] == response.json()["id"])


def test_multi_garment_google_inputs_stock_variants_and_background(signed):
    c, owner, calls = signed
    reference(owner)
    chosen = [
        owned(owner),
        selection(product("jacket")),
        selection(product("bottom")),
        selection(product("shoes")),
    ]
    request = {"selections": chosen, "request_key": "multi-garment-request"}
    result = job(c, c.post("/api/generate/try_on", json=request))
    assert result["status"] == "succeeded", result
    assert {p["category"] for p in result["result"]["pieces"]} == {"top", "jacket", "bottom", "shoes"}
    assert not result["result"]["keep_background"]
    assert all(p["variant_id"] for p in result["result"]["pieces"] if p["kind"] == "product")
    contents = calls[0]["contents"]
    assert len([p for p in contents if not isinstance(p, str)]) == 5
    assert "plain white studio background" in contents[0]
    assert any("Layer the selected jacket" in p for p in contents if isinstance(p, str))
    assert c.post("/api/generate/try_on", json=request).json()["id"] == result["id"]
    assert len(calls) == 1  # duplicate click does not charge or generate again
    # Deleting selected owned evidence removes associated preview media.
    assert c.delete("/api/wardrobe/" + chosen[0]["id"]).status_code == 200
    assert c.get("/api/media/" + result["result"]["media_id"]).status_code == 404


def test_last_selected_wins_for_bottoms_shoes_and_owned_new_conflicts(signed):
    c, owner, _ = signed
    reference(owner)
    b1, b2 = product("bottom", 0), product("bottom", 1)
    s1, s2 = product("shoes", 0), product("shoes", 1)
    chosen = [
        owned(owner, "bottom"),
        selection(b1),
        selection(s1),
        selection(b2),
        selection(s2),
        selection(s2),
    ]
    r = job(
        c, c.post("/api/generate/try_on", json={"selections": chosen, "request_key": "conflicting-pieces"})
    )
    assert r["status"] == "succeeded"
    assert [p["id"] for p in r["result"]["pieces"]] == [b2["id"], s2["id"]]
    assert len(r["result"]["selection_adjustments"]) == 3


@pytest.mark.parametrize("dress_last", [True, False])
def test_dress_replaces_separates_and_separates_replace_dress(signed, dress_last):
    _, owner, _ = signed
    reference(owner)
    top, bottom, dress, jacket = [selection(product(cat)) for cat in ["top", "bottom", "dress", "jacket"]]
    chosen = [top, bottom, jacket, dress] if dress_last else [dress, jacket, top, bottom]
    _, pieces, _ = try_on.prepare(owner, {"catalog_owner": "retailer", "selections": chosen})
    assert {p["category"] for p in pieces} == (
        {"dress", "jacket"} if dress_last else {"top", "bottom", "jacket"}
    )


def test_profile_defaults_snapshot_and_regenerate_use_latest_setting(signed, monkeypatch):
    c, owner, calls = signed
    reference(owner)
    # Pre-migration profiles have the same unchecked default as new accounts.
    profile = store().get("profiles", owner, "me")
    profile.pop("keep_background", None)
    store().put("profiles", owner, "me", profile)
    assert c.get("/api/profile").json()["keep_background"] is False
    monkeypatch.setattr(jobs, "enqueue", lambda *args: None)
    r = c.post(
        "/api/generate/try_on",
        json={"selections": [selection(product("top"))], "request_key": "snapshot-white-bg"},
    )
    profile["keep_background"] = True
    assert c.put("/api/profile", json=profile).json()["keep_background"] is True
    # Rendering preference persists independently of permission to remember style/size.
    assert not c.get("/api/profile").json()["consent"]["remember_preferences"]
    jobs.process(owner, r.json()["id"])
    assert "plain white studio background" in calls[-1]["contents"][0]
    regen = c.post("/api/jobs/" + r.json()["id"] + "/regenerate")
    jobs.process(owner, regen.json()["id"])
    assert "Preserve the same background" in calls[-1]["contents"][0]
    assert job(c, regen)["result"]["keep_background"] is True


def test_empty_bounded_and_ambiguous_selections_rejected_before_google(signed):
    c, owner, calls = signed
    reference(owner)
    for extra in [{}, {"selections": [selection(product("top"))], "product_id": "p-shirt"}]:
        r = c.post("/api/generate/try_on", json={**extra, "request_key": "invalid-selection"})
        assert r.status_code == 409
    r = c.post(
        "/api/generate/try_on",
        json={"selections": [selection(product("top"))] * 21, "request_key": "too-many-selections"},
    )
    assert r.status_code == 422
    assert calls == []


def test_foreign_unconfirmed_and_missing_original_wardrobe_not_usable(signed):
    c, owner, calls = signed
    reference(owner)
    foreign = owned("someone-else")
    own = owned(owner)
    item = store().get("wardrobe", owner, own["id"])
    item["confirmed"] = False
    store().put("wardrobe", owner, item["id"], item)
    for chosen in [foreign, own]:
        r = c.post("/api/generate/try_on", json={"selections": [chosen], "request_key": "invalid-ownership"})
        assert r.status_code == 409
    item.update(confirmed=True, image="", generated_image="media:generated-only")
    store().put("wardrobe", owner, item["id"], item)
    assert (
        c.post(
            "/api/generate/try_on", json={"selections": [own], "request_key": "no-original-photo"}
        ).status_code
        == 409
    )
    assert calls == []


def test_whole_selection_rechecks_outfit_membership_stock_and_image_changes(signed, monkeypatch):
    c, owner, calls = signed
    reference(owner)
    top, bottom = product("top"), product("bottom")
    chosen = [selection(top), selection(bottom)]
    store().put("outfits", owner, "look", {"id": "look", "products": [top], "owned": []})
    assert (
        c.post(
            "/api/generate/try_on",
            json={"outfit_id": "look", "selections": chosen, "request_key": "wrong-outfit-piece"},
        ).status_code
        == 409
    )
    monkeypatch.setattr(jobs, "enqueue", lambda *args: None)
    r = c.post("/api/generate/try_on", json={"selections": chosen, "request_key": "stock-recheck-queue"})
    for v in bottom["variants"]:
        for s in v["stock"]:
            s["quantity"] = 0
    store().put("products", "retailer", bottom["id"], bottom)
    jobs.process(owner, r.json()["id"])
    assert job(c, r)["status"] == "failed"
    assert calls == []
    prepared, _, _ = try_on.prepare(owner, {"catalog_owner": "retailer", "selections": [selection(top)]})
    top["image"] = "media:" + media.save("retailer", picture())
    store().put("products", "retailer", top["id"], top)
    with pytest.raises(ValueError, match="photo changed"):
        try_on.prepare(owner, prepared)


def test_vto_cannot_silently_ignore_multiple_pieces_or_white_background(signed, monkeypatch):
    _, owner, _ = signed
    reference(owner)
    p = deepcopy(product("top"))
    p.update(sample=False, image="media:" + media.save("retailer", picture()))
    store().put("products", "retailer", p["id"], p)
    monkeypatch.setenv("IMAGE_EDIT_MODEL", "")
    monkeypatch.setenv("TRY_ON_MODEL", "test-vto")
    settings.cache_clear()
    payload = {"catalog_owner": "retailer", "selections": [selection(p)]}
    with pytest.raises(try_on.CapabilityUnavailable, match="background settings require"):
        try_on.prepare(owner, payload)
    prepared, _, _ = try_on.prepare(owner, {**payload, "keep_background": True})
    assert prepared["keep_background"] is True
    with pytest.raises(try_on.CapabilityUnavailable):
        try_on.prepare(
            owner, {**payload, "keep_background": True, "selections": [selection(p), owned(owner, "jacket")]}
        )


def test_daily_image_limit_fails_before_queue_and_is_clear_if_reached_while_waiting(signed, monkeypatch):
    from app.auth import quota

    c, owner, calls = signed
    reference(owner)
    monkeypatch.setenv("MAX_DAILY_IMAGE_GENERATIONS", "1")
    settings.cache_clear()
    monkeypatch.setattr(jobs, "enqueue", lambda *args: None)
    r = c.post("/api/generate/try_on", json={"product_id": "p-shirt", "request_key": "before-limit-used"})
    assert r.status_code == 200
    # Another request reserves the last image while this job waits; the queued job stays truthful.
    quota("live-ai", "image-generation", 1)
    jobs.process(owner, r.json()["id"])
    result = job(c, r)
    assert result["status"] == "failed" and "daily Google image allowance" in result["error"]
    assert calls == []
    new = c.post("/api/generate/try_on", json={"product_id": "p-shirt", "request_key": "after-limit-used"})
    assert new.status_code == 429 and "05:30 India time" in new.json()["detail"]
    assert len(c.get("/api/jobs").json()["jobs"]) == 1
