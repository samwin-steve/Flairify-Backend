import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from app.auth import Principal
from app.models import ChatRequest, Product
from app.services import inventory, recommendations, try_on
from app.store import store

ALPHA_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"}


def test_catalogue_has_diverse_photographed_options_and_demo_sizes():
    products = list(inventory.fixture_products().values())
    assert len(products) == 200
    departments = Counter(p["attributes"]["department"] for p in products)
    assert departments == {"men": 90, "women": 91, "unisex": 19}
    credits = json.loads((inventory.FIXTURES / "catalogue-sources.json").read_text())
    assert len(credits) == 190
    assert len({c["source_id"] for c in credits}) == 190
    assert sum(c["dataset"] == "myntra" for c in credits) == 8
    for p in products:
        assert p["sample"] and p["indexed"]
        expected = (
            {str(i) for i in range(35, 49)}
            if p["category"] == "shoes"
            else ({"One size"} if p["category"] in ("bag", "accessory") else ALPHA_SIZES)
        )
        assert {v["size"] for v in p["variants"]} == expected
        for variant in p["variants"]:
            assert {s["store_id"] for s in variant["stock"]} == {"bandra", "lower-parel"}
            assert all(s["quantity"] == (0 if p["id"] == "p-soldout" else 12) for s in variant["stock"])
        if p["id"].startswith("sample-"):
            with Image.open(inventory.FIXTURES / "images" / Path(p["image"]).name) as image:
                image.verify()
            if p["category"] in try_on.CLOTHING:
                assert try_on.sample_asset(p)


def test_existing_catalogue_upgrades_without_overwriting_seller_edits(client):
    owner = "legacy-catalogue"
    legacy = json.loads((inventory.FIXTURES / "catalogue-legacy.json").read_text())
    for p in legacy:
        p = Product.model_validate(p).model_dump(mode="json")
        if p["id"] == "p-shirt":
            p["price"] = 321
            p["variants"][0]["stock"][0]["quantity"] = 0
        store().put("products", owner, p["id"], p)
    original = store().get("products", owner, "p-shirt")
    custom = {**deepcopy(original), "id": "retailer-original", "sample": False}
    store().put("products", owner, custom["id"], custom)
    store().put("meta", owner, "seeded", {"done": True})
    inventory.seed_catalog(owner)
    assert len(store().list("products", owner)) == 201
    assert store().get("products", owner, "p-shirt") == original
    assert store().get("products", owner, custom["id"]) == custom
    unmodified = next(p for p in legacy if p["id"] != "p-shirt" and p["category"] == "jacket")
    assert {v["size"] for v in store().get("products", owner, unmodified["id"])["variants"]} == ALPHA_SIZES
    # Later stock edits stay intact even when profiles/catalogue pages refresh.
    current = store().get("products", owner, "sample-fashion-15970")
    current["price"] = 123
    store().put("products", owner, current["id"], current)
    inventory.seed_catalog(owner)
    assert store().get("products", owner, current["id"])["price"] == 123


@pytest.mark.parametrize("department", ["men", "women"])
@pytest.mark.parametrize("size,shoe_size", [("XXS", "35"), ("XXL", "45"), ("4XL", "48")])
@pytest.mark.parametrize("anchor", ["top", "jacket"])
def test_single_garment_mumbai_trip_across_departments_and_sizes(
    client, session, department, size, shoe_size, anchor
):
    data, _ = session
    owner = data["user_id"]
    garment = json.loads((inventory.FIXTURES / "wardrobe.json").read_text())[0]
    garment.update(confirmed=True, category=anchor, name=f"My {anchor}")
    store().put("wardrobe", owner, garment["id"], garment)
    result = recommendations.recommend(
        Principal(owner, demo=True),
        ChatRequest(
            message="Mumbai for work for three days, walking a lot, under ₹5,000",
            department=department,
            clothing_size=size,
            shoe_size=shoe_size,
            store_id="lower-parel",
        ),
        {},
    )
    assert result["outfits"], result["text"]
    for outfit in result["outfits"]:
        assert outfit["complete"] and outfit["total"] == sum(p["price"] for p in outfit["products"]) <= 5000
        assert garment["id"] in {w["id"] for w in outfit["owned"]}
        for p in outfit["products"]:
            assert p["attributes"]["department"] in (department, "unisex")
            assert p["availability"]["size"] == (shoe_size if p["category"] == "shoes" else size)
            assert p["availability"]["store_id"] == "lower-parel"
            assert p["availability"]["quantity"] > 0


def test_requested_top_can_fill_missing_bottom_and_shoes(client, session):
    data, _ = session
    owner = data["user_id"]
    garment = json.loads((inventory.FIXTURES / "wardrobe.json").read_text())[0]
    garment.update(confirmed=True, category="jacket", name="My jacket")
    store().put("wardrobe", owner, garment["id"], garment)
    result = recommendations.recommend(
        Principal(owner, demo=True),
        ChatRequest(
            message="Find a new shirt under ₹5,000",
            clothing_size="4XL",
            shoe_size="48",
            department="men",
        ),
        {},
    )
    assert result["outfits"], result["text"]
    assert all(
        {p["category"] for p in o["products"]} == {"top", "bottom", "shoes"} for o in result["outfits"]
    )


def test_search_does_not_starve_categories_and_failure_is_specific(client, onboarded):
    data, headers = onboarded
    assert len(inventory.search(data["user_id"])) == 200
    assert {p["category"] for p in inventory.search(data["user_id"])} == {
        "top",
        "bottom",
        "jacket",
        "dress",
        "shoes",
        "bag",
        "accessory",
    }
    response = client.post(
        "/api/chat",
        headers=headers,
        json={
            "message": "Show a new jacket under ₹5,000",
            "clothing_size": "unavailable-size",
            "shoe_size": "39",
        },
    ).json()
    assert not response["outfits"]
    assert "no matching jacket" in response["text"]
    assert "unavailable-size" in response["text"]
