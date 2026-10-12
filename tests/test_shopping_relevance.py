"""Occasion relevance and preference regressions using the actual sample catalogue."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.models import WardrobeItem
from app.services import styling
from app.store import store


def setup(client, session, department="men", store_id="bandra"):
    data, headers = session
    response = client.put(
        "/api/profile",
        headers=headers,
        json={
            "name": "QA",
            "clothing_size": "M",
            "shoe_size": "39",
            "department": department,
            "preferred_store_id": store_id,
            "budget": 5000,
            "consent": {"remember_preferences": False},
        },
    )
    assert response.status_code == 200
    assert client.post("/api/onboarding/complete", headers=headers).status_code == 200
    return data["user_id"], headers


@pytest.mark.parametrize("department", ["men", "women"])
def test_independence_day_office_is_relevant_diverse_and_catalogue_only(client, session, department):
    _, h = setup(client, session, department)
    r = client.post(
        "/api/chat",
        headers=h,
        json={"message": "I have independece day at office can you suggest some chothes"},
    ).json()
    assert r["outfits"], r
    anchors = []
    for outfit in r["outfits"]:
        assert outfit["owned"] == [] and outfit["complete"] and outfit["total"] <= 5000
        main = next(p for p in outfit["products"] if p["category"] in ("top", "dress"))
        anchors.append(main["id"])
        assert styling.colours(main) & {"white", "green", "orange"}
        for p in outfit["products"]:
            assert p["attributes"]["department"] in (department, "unisex")
            assert p["availability"]["store_id"] == "bandra"
            assert p["availability"]["size"] == ("39" if p["category"] == "shoes" else "M")
            assert p["category"] not in ("jacket", "accessory", "bag")
            if p["category"] in ("bottom", "shoes"):
                assert styling.colours(p) & styling.NEUTRALS
            assert not any(
                t in p["name"].lower() for t in ("kids", "sunglasses", "track pants", "shorts", "cropped")
            )
    assert len(anchors) >= 2 and len(anchors) == len(set(anchors))
    assert "Independence Day" in r["intent"]["occasion"]
    assert "What clothing" not in r["text"]


def test_profile_saved_without_optional_memory_and_checked_at_checkout(client, session):
    _, h = setup(client, session, "women", "lower-parel")
    p = client.get("/api/profile", headers=h).json()
    assert (p["clothing_size"], p["shoe_size"], p["department"], p["preferred_store_id"]) == (
        "M",
        "39",
        "women",
        "lower-parel",
    )
    assert p["styles"] == [] and p["include_wardrobe"] is False
    assert client.get("/api/wardrobe", headers=h).json()["items"] == []
    assert (
        client.put("/api/profile", headers=h, json={"preferred_store_id": "foreign-store"}).status_code == 422
    )


def test_wardrobe_toggle_never_forces_unsuitable_or_unconfirmed_pieces(client, session):
    uid, h = setup(client, session)
    for name, colour, confirmed in [
        ("Red football jersey", "Red", True),
        ("White office shirt", "White", False),
    ]:
        w = WardrobeItem(name=name, colour=colour, category="top", confirmed=confirmed)
        store().put("wardrobe", uid, w.id, w.model_dump(mode="json"))
    request = {"message": "Independence Day office clothes", "include_wardrobe": True}
    r = client.post("/api/chat", headers=h, json=request).json()
    assert r["outfits"] and all(not o["owned"] for o in r["outfits"])
    shirt = next(w for w in store().list("wardrobe", uid) if w["colour"] == "White")
    shirt["confirmed"] = True
    store().put("wardrobe", uid, shirt["id"], shirt)
    on = client.post("/api/chat", headers=h, json=request).json()
    assert any(o["owned"] for o in on["outfits"])
    assert all({w["id"] for w in o["owned"]} <= {shirt["id"]} for o in on["outfits"])
    off = client.post("/api/chat", headers=h, json={**request, "include_wardrobe": False}).json()
    assert all(not o["owned"] for o in off["outfits"])


def test_show_different_options_excludes_previous_hero_items(client, session):
    _, h = setup(client, session)
    a = client.post("/api/chat", headers=h, json={"message": "Office shirts"}).json()
    b = client.post(
        "/api/chat",
        headers=h,
        json={"message": "Show different options", "conversation_id": a["conversation"]["id"]},
    ).json()
    first = {p["id"] for o in a["outfits"] for p in o["products"]}
    second = {p["id"] for o in b["outfits"] for p in o["products"]}
    assert first and second and not first & second
    assert all(len(o["products"]) == 1 for o in a["outfits"] + b["outfits"])


def test_saved_size_stock_budget_and_department_are_hard_constraints(client, session):
    uid, h = setup(client, session)
    for p in store().list("products", uid):
        for v in p["variants"]:
            if v["size"] == "M":
                for stock in v["stock"]:
                    stock["quantity"] = 0
        store().put("products", uid, p["id"], p)
    r = client.post("/api/chat", headers=h, json={"message": "Independence Day office shirts"}).json()
    assert not r["outfits"] and "no matching top" in r["text"]


@pytest.mark.parametrize("message", ["Now I need a running outfit for the gym", "A workout outfit"])
def test_occasion_change_does_not_keep_previous_independence_palette(client, session, message):
    _, h = setup(client, session)
    a = client.post("/api/chat", headers=h, json={"message": "Independence Day at office"}).json()
    b = client.post(
        "/api/chat",
        headers=h,
        json={
            "message": message,
            "conversation_id": a["conversation"]["id"],
        },
    ).json()
    assert b["intent"]["palette"] == [] and b["intent"]["dress_code"] == "sports"
    assert b["outfits"] and "Independence" not in b["intent"]["occasion"]


def test_whole_outfit_model_rejects_candidates_and_cannot_invent_ids(client, monkeypatch):
    options = [{"key": "a", "owned": [], "products": [], "rank": 1, "accepted": True}]
    response = {
        "options": [
            {
                "option_id": "a",
                "suitable": False,
                "score": 0.1,
                "reason": "Sportswear does not suit an office celebration.",
            }
        ]
    }

    class Provider:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        @property
        def models(self):
            return self

        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps(response))

    monkeypatch.setattr(styling.ai, "client", lambda **kwargs: Provider())
    intent = {"query": "office", "occasion": "office", "dress_code": "office", "palette": []}
    assert styling.assess_shortlist(options, intent, True) == "gemini"
    assert not options[0]["accepted"]
    response["options"][0]["option_id"] = "invented"
    unchanged = deepcopy(options)
    assert styling.assess_shortlist(options, intent, True) == "rules-fallback"
    assert options == unchanged


@pytest.mark.parametrize(
    "message,occasion", [("Office shirts", "Work & everyday"), ("White shirts", "Everyday")]
)
def test_new_request_does_not_inherit_old_occasion(message, occasion):
    result = styling.brief(message, {"occasion": "Independence Day", "palette": ["orange"]}, None)
    assert result["occasion"] == occasion
    assert result["palette"] != ["orange"]
