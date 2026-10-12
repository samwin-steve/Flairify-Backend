import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth import Principal
from app.models import ChatRequest
from app.rag import embeddings, repository, retrieval
from app.services import indexing, inventory, recommendations
from app.store import store


def test_embedding_cache_ignores_stock_but_refreshes_semantic_fields(client, monkeypatch):
    product = copy.deepcopy(next(iter(inventory.fixture_products().values())))
    owner = "retailer"
    store().put("products", owner, product["id"], product)
    monkeypatch.setattr(embeddings, "enabled", lambda _: True)
    calls = []
    monkeypatch.setattr(embeddings, "embed", lambda text: calls.append(text) or [1.0, 0.0])
    assert indexing.index_products(owner, [product["id"]])["embeddings_generated"] == 1
    assert indexing.index_products(owner, [product["id"]])["indexed"] == 0
    current = store().get("products", owner, product["id"])
    current["price"] += 1
    current["variants"][0]["stock"][0]["quantity"] = 0
    current["indexed"] = False
    store().put("products", owner, product["id"], current)
    assert indexing.index_products(owner, [product["id"]])["embeddings_reused"] == 1
    current["attributes"]["styles"] = "evening celebration"
    store().put("products", owner, product["id"], current)
    assert indexing.index_products(owner, [product["id"]])["embeddings_generated"] == 1
    assert len(calls) == 2
    assert "evening celebration" in calls[-1]


def test_embedding_2_uses_prompt_instructions_not_legacy_task_type(client, monkeypatch):
    captured = []
    provider = MagicMock()
    provider.__enter__.return_value = provider
    provider.models.embed_content.side_effect = lambda **kw: (
        captured.append(kw) or SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] * 768)])
    )
    monkeypatch.setattr(embeddings.genai, "Client", lambda **_: provider)
    vector = embeddings.embed("light layers for meetings", query=True)
    assert len(vector) == 768
    assert abs(sum(v * v for v in vector) - 1) < 1e-8
    assert captured[0]["model"] == "gemini-embedding-2"
    assert captured[0]["config"].task_type is None
    assert captured[0]["contents"].startswith("task: search result | query:")


def test_firestore_search_is_bounded_and_scoped(client, monkeypatch):
    query = MagicMock()
    query.where.return_value = query
    query.find_nearest.return_value.stream.return_value = []
    query.order_by.return_value.limit.return_value.stream.return_value = []
    db = SimpleNamespace(cloud=True, db=MagicMock())
    db.db.collection.return_value = query
    monkeypatch.setattr(repository, "store", lambda: db)
    assert (
        repository.nearest(
            "retailer",
            [1.0] * 768,
            budget=5000,
            department="women",
            store_id="bandra",
            clothing_size="M",
            categories=("jacket",),
        )
        == []
    )
    filters = [c.kwargs["filter"] for c in query.where.call_args_list]
    assert {(f.field_path, f.op_string) for f in filters} == {
        ("owner", "=="),
        ("space", "=="),
        ("active", "=="),
        ("facets", "array_contains"),
        ("price", "<="),
    }
    assert next(f.value for f in filters if f.field_path == "owner") == "retailer"
    assert next(f.value for f in filters if f.field_path == "facets") == repository.facet(
        "jacket", "women", "bandra", "M"
    )
    assert query.find_nearest.call_args.kwargs["limit"] == 16
    query.order_by.return_value.limit.assert_called_once_with(2)


def test_live_retrieval_failure_never_scans_catalogue(client, monkeypatch):
    monkeypatch.setattr(embeddings, "enabled", lambda _: True)
    monkeypatch.setattr(embeddings, "embed", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(inventory, "attribute_search", lambda *a, **k: pytest.fail("Unexpected full scan"))
    with pytest.raises(HTTPException) as exc:
        retrieval.candidates("retailer", "work trip", 5000)
    assert exc.value.status_code == 503


@pytest.mark.parametrize("api_budget,expected", [(5000, 3000), (2000, 2000)])
def test_agent_and_api_cannot_raise_message_budget(client, onboarded, api_budget, expected):
    data, _ = onboarded
    result = recommendations.recommend(
        Principal(data["user_id"], demo=True),
        ChatRequest(message="Mumbai work under ₹3,000", budget=api_budget),
        {},
        interpreted={"budget": 999999, "query": "work trip"},
    )
    assert result["intent"]["budget"] == expected
    assert all(o["total"] <= expected for o in result["outfits"])


def test_scoped_facets_do_not_claim_soldout_size(client):
    p = copy.deepcopy(next(iter(inventory.fixture_products().values())))
    p["attributes"]["department"] = "unisex"
    p["category"] = "jacket"
    p["variants"] = [
        {"id": "m", "size": "M", "colour": "blue", "stock": [{"store_id": "bandra", "quantity": 1}]},
        {"id": "s", "size": "S", "colour": "blue", "stock": [{"store_id": "bandra", "quantity": 0}]},
    ]
    keys = repository.facets(p)
    assert repository.facet("jacket", "women", "bandra", "M") in keys
    assert repository.facet("jacket", "men", "bandra", "M") in keys
    assert repository.facet("jacket", "women", "bandra", "S") not in keys


def test_semantic_shortlist_keeps_budget_stock_and_ownership(client, onboarded, monkeypatch):
    data, _ = onboarded
    owner = data["user_id"]
    records = inventory.attribute_search(owner)
    original_list = store().list
    monkeypatch.setattr(
        store(),
        "list",
        lambda kind, uid: (
            pytest.fail("Full catalogue scan") if kind == "products" else original_list(kind, uid)
        ),
    )
    monkeypatch.setattr(recommendations, "candidates", lambda *a, **kw: (records, {"method": "test-vector"}))
    result = recommendations.recommend(
        Principal(owner, demo=True),
        ChatRequest(message="Mumbai work under ₹5,000", clothing_size="M", shoe_size="39"),
        {},
        interpreted={"budget": 999999, "query": "walking work layers"},
    )
    assert result["outfits"]
    for look in result["outfits"]:
        assert look["total"] <= 5000 and look["complete"]
        assert all(store().get("wardrobe", owner, w["id"])["confirmed"] for w in look["owned"])
        assert all(p["availability"]["quantity"] > 0 for p in look["products"])


def test_adk_tools_never_accept_another_users_identifier(client, onboarded):
    from app.agents.tools import StylistTools

    data, _ = onboarded

    async def emit(*args):
        pass

    tools = StylistTools(Principal(data["user_id"], demo=True), ChatRequest(message="work"), {}, emit)
    assert asyncio.run(tools.get_product_details("not-retrieved")) == {
        "error": "Product is not in the validated shortlist"
    }
    assert all(r["id"] for r in asyncio.run(tools.get_confirmed_wardrobe())["garments"])
