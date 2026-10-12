import asyncio
from unittest.mock import patch

from app.auth import Principal
from app.models import ChatRequest, Conversation
from app.rag import embeddings
from app.services import recommendations
from app.store import store


def start(client, onboarded):
    identity, headers = onboarded
    response = client.post(
        "/api/chat",
        headers=headers,
        json={"message": "A smart outfit for the office under ₹5,000", "include_wardrobe": False},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["outfits"]) >= 2
    return identity, headers, data


def turn(client, h, data, text, **extra):
    response = client.post(
        "/api/chat",
        headers=h,
        json={
            "message": text,
            "conversation_id": data["conversation"]["id"],
            "include_wardrobe": False,
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_second_look_shoe_swap_preserves_exact_shirt_and_trousers(client, onboarded):
    _, h, a = start(client, onboarded)
    selected = a["outfits"][1]
    b = turn(client, h, a, "I like the second look. Keep the shirt and trousers, but swap the shoes")
    assert b["outfits"], b["text"]
    keep = {p["id"] for p in selected["products"] if p["category"] != "shoes"}
    old = {p["id"] for p in selected["products"] if p["category"] == "shoes"}
    for look in b["outfits"]:
        ids = {p["id"] for p in look["products"]}
        assert keep <= ids and not old & ids
        assert look["complete"] and look["total"] <= 5000
        assert look["occasion"] == selected["occasion"]
    assert len(b["conversation"]["messages"]) == 4


def test_explanation_does_not_search_and_next_variation_keeps_context(client, onboarded, monkeypatch):
    uid, h, a = start(client, onboarded)
    with patch.object(
        recommendations, "candidates", side_effect=AssertionError("Discussion must not search")
    ):
        b = turn(client, h, a, "Why does the second look work for the office?")
    assert not b["outfits"] and a["outfits"][1]["title"] in b["text"]
    assert b["intent"]["occasion"] == a["intent"]["occasion"]
    # Persisted conversation is the source, even in a fresh request context.
    saved = store().get("conversations", uid["user_id"], a["conversation"]["id"])
    assert len(saved["messages"]) == 4
    c = turn(client, h, b, "A different variation of the second look")
    assert c["outfits"] and c["intent"]["occasion"] == a["intent"]["occasion"]
    assert len(c["conversation"]["messages"]) == 6


def test_selected_look_and_single_colour_variation(client, onboarded):
    _, h, a = start(client, onboarded)
    chosen = a["outfits"][0]
    b = turn(client, h, a, "A different variation", reference_outfit_id=chosen["id"])
    assert b["outfits"]
    kept = {p["id"] for p in chosen["products"] if p["category"] not in ("top", "dress", "jacket")}
    assert all(kept <= {p["id"] for p in o["products"]} for o in b["outfits"])
    assert all(
        not (
            {p["id"] for p in chosen["products"] if p["category"] == "top"}
            & {p["id"] for p in o["products"] if p["category"] == "top"}
        )
        for o in b["outfits"]
    )
    unknown = client.post(
        "/api/chat",
        headers=h,
        json={
            "message": "Another variation",
            "conversation_id": a["conversation"]["id"],
            "reference_outfit_id": "someone-elses-look",
        },
    )
    assert unknown.status_code == 422


def test_kept_item_becoming_unavailable_is_not_silently_replaced(client, onboarded):
    identity, h, a = start(client, onboarded)
    chosen = a["outfits"][0]
    product = next(p for p in chosen["products"] if p["category"] == "bottom")
    for variant in product["variants"]:
        for stock in variant["stock"]:
            stock["quantity"] = 0
    store().put("products", identity["user_id"], product["id"], product)
    b = turn(client, h, a, "Change only the shoes", reference_outfit_id=chosen["id"])
    assert not b["outfits"]


def test_category_plan_only_searches_changed_slot(client, onboarded, monkeypatch):
    _, h, a = start(client, onboarded)
    original = recommendations.candidates
    seen = []

    def capture(*args, **kwargs):
        seen.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(recommendations, "candidates", capture)
    b = turn(client, h, a, "Different shoes for the first look")
    assert b["outfits"]
    assert seen[0]["categories"] == ("shoes",)
    assert "Complement these retained pieces" in seen[0]["category_queries"]["shoes"]
    assert seen[0]["deeper"] and seen[0]["exclude_ids"]


def test_query_cache_scopes_model_and_owner_and_expires(client, monkeypatch):
    embeddings._query_cache.clear()
    calls = []
    monkeypatch.setattr(embeddings, "embed", lambda text, **k: calls.append(text) or [1.0, 0.0])
    embeddings.cached_query("retailer", "blue shoes")
    embeddings.cached_query("retailer", "blue shoes")
    embeddings.cached_query("other", "blue shoes")
    assert len(calls) == 2
    monkeypatch.setattr(embeddings.time, "monotonic", lambda: 10**15)
    embeddings.cached_query("retailer", "blue shoes")
    assert len(calls) == 3
    embeddings._query_cache.clear()


def test_adk_discussion_tool_returns_grounded_old_looks_without_search(client, onboarded):
    from app.agents.tools import StylistTools

    identity, _, a = start(client, onboarded)
    conversation = Conversation.model_validate(a["conversation"])
    emitted = []

    async def emit(kind, value):
        emitted.append(kind)

    tools = StylistTools(
        Principal(identity["user_id"], demo=True),
        ChatRequest(message="Why the second one?"),
        conversation.intent,
        emit,
        conversation,
    )
    result = asyncio.run(tools.discuss_current_looks())
    assert result["looks"][0]["id"] == a["outfits"][1]["id"]
    assert tools.result["outfits"] == [] and "outfits" not in emitted


def test_colour_followup_preserves_context_and_changes_main_piece(client, onboarded):
    _, h, a = start(client, onboarded)
    chosen = a["outfits"][0]
    b = turn(client, h, a, "Blue instead, same style", reference_outfit_id=chosen["id"])
    assert b["outfits"] and b["intent"]["palette"] == ["blue"]
    kept = {p["id"] for p in chosen["products"] if p["category"] != "top"}
    for look in b["outfits"]:
        assert kept <= {p["id"] for p in look["products"]}
        assert any(
            "blue" in p["attributes"].get("colour", "").lower()
            for p in look["products"]
            if p["category"] == "top"
        )
        assert look["total"] <= 5000


def test_budget_parser_does_not_read_comma_in_trousers_as_rupees():
    assert (
        recommendations.parse_intent("Keep the trousers, change the shoes", {"budget": 5000}, 5000)["budget"]
        == 5000
    )
    assert recommendations.parse_intent("up to ₹3,000 please", {"budget": 5000}, 5000)["budget"] == 3000
