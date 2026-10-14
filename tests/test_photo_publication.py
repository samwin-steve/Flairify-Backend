import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.catalogue import enrichment
from app.catalogue.publication import PublicationPolicy, activate
from app.catalogue.schema import Enrichment
from app.config import settings
from app.models import Product, now
from app.services import inventory
from app.store import store
from scripts.publish_photo_catalogue import publish_one


@pytest.fixture
def policy():
    return PublicationPolicy.model_validate_json(Path("config/photo-catalogue-pricing.json").read_text())


def draft(category="top"):
    item = Product(
        id="drive-photo",
        sku="PHOTO",
        name="Blue shirt",
        category=category,
        price=0,
        active=False,
        image="media:photo",
        seller_id="owner",
        attributes={
            "catalogue_status": "draft",
            "source_drive_file_id": "drive-source",
            "colour": "Blue",
            "description_source": "gemini_visual",
        },
    ).model_dump(mode="json")
    item["enrichment"] = Enrichment(
        status="complete",
        schema_version="1",
        taxonomy_version="1",
        prompt_version="1",
        model=settings().gemini_model,
        input_hash=enrichment.fingerprint(item),
        input_mode="image_and_text",
        assessed_at=now(),
        image_hash="photo-hash",
    ).model_dump(mode="json")
    return item


@pytest.mark.parametrize("category", ["top", "bottom", "dress", "jacket", "shoes", "bag"])
def test_publication_sizes_stock_prices_and_metadata_reuse(category, policy):
    original = draft(category)
    frozen = copy.deepcopy(original)
    result = activate(original, policy, "owner", policy.store_ids)
    assert original == frozen
    assert result["active"] and not result["indexed"]
    assert result["price"] == policy.prices[category]
    expected = (
        ["One size"]
        if category == "bag"
        else policy.shoe_sizes
        if category == "shoes"
        else policy.clothing_sizes
    )
    assert [v["size"] for v in result["variants"]] == expected
    for size in expected:
        for sid in policy.store_ids:
            assert inventory.available(result, size, sid)[0]["quantity"] == 20
    assert enrichment.current(result)
    assert {k: v for k, v in result["enrichment"].items() if k != "input_hash"} == {
        k: v for k, v in original["enrichment"].items() if k != "input_hash"
    }
    assert result["ai_attributes"]["metadata_reused_from"] == original["enrichment"]["input_hash"]
    # Subsequent semantic edits must still invalidate metadata normally.
    result["variants"][0]["colour"] = "Red"
    assert not enrichment.current(result)


@pytest.mark.parametrize("change", ["seller", "price", "image", "name", "status", "stale", "active"])
def test_changed_or_unreviewed_drafts_are_not_overwritten(change, policy):
    original = draft()
    if change == "seller":
        original["seller_id"] = "another"
    elif change == "status":
        original["enrichment"]["status"] = "needs_review"
    elif change == "stale":
        original["enrichment"]["input_hash"] = "stale"
    else:
        original[change] = {"price": 1, "image": "media:another", "name": "Another shirt", "active": True}[
            change
        ]
    with pytest.raises(ValueError):
        activate(original, policy, "owner", policy.store_ids)


def test_retry_preserves_seller_price_and_stock_edits(policy):
    result = activate(draft(), policy, "owner", policy.store_ids)
    result["price"] = 1700
    result["variants"][0]["stock"][0]["quantity"] = 4
    assert activate(result, policy, "owner", policy.store_ids) is None


def test_concurrent_edit_not_lost_and_reuse_cache_audited(client, policy):
    original = draft()
    result = activate(original, policy, "owner", policy.store_ids)
    store().put("products", "retailer", original["id"], original)
    publish_one(original, result)
    cached = store().get(
        "catalogue_analysis", "retailer", original["id"] + "-" + result["enrichment"]["input_hash"]
    )
    assert cached["reused_from_input_hash"] == original["enrichment"]["input_hash"]
    assert cached["record"]["assessed_at"] == original["enrichment"]["assessed_at"]
    with pytest.raises(ValueError, match="changed"):
        publish_one(original, result)
    assert store().get("products", "retailer", original["id"]) == result


def test_invalid_policy_or_unknown_store_rejected(policy):
    raw = policy.model_dump()
    raw["prices"]["top"] = 0
    with pytest.raises(ValidationError):
        PublicationPolicy.model_validate(raw)
    with pytest.raises(ValueError, match="store"):
        activate(draft(), policy, "owner", [])
