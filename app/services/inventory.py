import csv
import hashlib
import io
import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from ..models import Product, Store, WardrobeItem
from ..store import store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
CATALOG_VERSION = "2026-10-expanded-200-v1"


@lru_cache(maxsize=1)
def fixture_products():
    return {
        p["id"]: Product.model_validate(p).model_dump(mode="json")
        for p in json.loads((FIXTURES / "catalogue.json").read_text())
    }


def seed_catalog(owner):
    marker = store().get("meta", owner, "seeded")
    if marker and marker.get("version") == CATALOG_VERSION:
        return
    fixtures = fixture_products()
    existing = {p["id"]: p for p in store().list("products", owner)}
    store().create_missing("products", owner, [p for key, p in fixtures.items() if key not in existing])
    # Widen sizes only on untouched legacy fixtures. Preserve retailer/admin corrections.
    for raw in json.loads((FIXTURES / "catalogue-legacy.json").read_text()):
        old = Product.model_validate(raw).model_dump(mode="json")
        if old["id"] in existing and product_hash(existing[old["id"]]) == product_hash(old):

            def upgrade(current, expected=old):
                return (
                    fixtures[expected["id"]]
                    if current and product_hash(current) == product_hash(expected)
                    else current
                )

            store().mutate("products", owner, old["id"], upgrade)
    current_stores = {s["id"] for s in store().list("stores", owner)}
    store().create_missing(
        "stores",
        owner,
        [
            Store.model_validate(s).model_dump(mode="json")
            for s in json.loads((FIXTURES / "stores.json").read_text())
            if s["id"] not in current_stores
        ],
    )
    store().put("meta", owner, "seeded", {"done": True, "version": CATALOG_VERSION})


def seed_wardrobe(owner):
    for record in json.loads((FIXTURES / "wardrobe.json").read_text()):
        if not store().get("wardrobe", owner, record["id"]):
            item = WardrobeItem.model_validate(record).model_dump(mode="json")
            store().put("wardrobe", owner, item["id"], item)


def available(product, size, store_id=None):
    if not product or not product.get("active", True):
        return []
    choices = []
    for variant in product["variants"]:
        if size and variant["size"].casefold() != size.casefold() and variant["size"] != "One size":
            continue
        if not size and variant["size"] != "One size":
            continue
        for stock in variant["stock"]:
            if stock["quantity"] > 0 and (not store_id or stock["store_id"] == store_id):
                choices.append(
                    {
                        "variant_id": variant["id"],
                        "size": variant["size"],
                        "colour": variant["colour"],
                        **stock,
                    }
                )
    return choices


def attribute_search(owner, q="", budget=1000000, category=None, limit=None):
    stop_words = {
        "a",
        "an",
        "the",
        "i",
        "my",
        "me",
        "for",
        "to",
        "and",
        "with",
        "some",
        "new",
        "show",
        "find",
        "want",
        "need",
        "buy",
        "under",
        "budget",
        "please",
        "in",
        "of",
    }
    words = [w for w in re.findall(r"[a-z]+", q.lower()) if w not in stop_words]
    records = [
        p
        for p in store().list("products", owner)
        if p["indexed"]
        and p.get("active", True)
        and p["price"] <= budget
        and (not category or p["category"] == category)
    ]

    def score(p):
        text = " ".join([p["name"], p["description"], p["category"], json.dumps(p["attributes"])]).lower()
        name = p["name"].lower()
        return sum(3 * (w in name) + (w in text) for w in words)

    return sorted(records, key=lambda p: (-score(p), p["price"], p["id"]))[:limit]


def parse_import(raw, filename):
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "Catalogue imports must be under 2 MB")
    try:
        if filename.lower().endswith(".csv"):
            records = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            for r in records:
                for field in ("variants", "attributes", "delivery", "ai_attributes"):
                    if r.get(field):
                        r[field] = json.loads(r[field])
        else:
            records = json.loads(raw)
        if not isinstance(records, list) or not 1 <= len(records) <= 500:
            raise ValueError("Import between 1 and 500 products")
        validated = [Product.model_validate(r) for r in records]
        if len({p.id for p in validated}) != len(validated):
            raise ValueError("Duplicate product IDs in import")
        return validated
    except Exception as exc:
        raise HTTPException(422, f"Invalid catalogue: {str(exc)[:500]}")


def product_hash(p):
    data = {k: v for k, v in p.items() if k not in ("updated_at", "content_hash", "indexed", "ai_attributes")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def search(owner, q="", budget=1000000, category=None, limit=None):
    # Browsing an empty query retains the inventory screen contract. Recommendation
    # retrieval never uses this listing path.
    from .styling import quality_issue

    if not q.strip():
        rows = attribute_search(owner, q, budget, category)
    else:
        from ..rag.retrieval import candidates

        rows, _ = candidates(owner, q, budget, category=category)
    return [p for p in rows if not quality_issue(p)][:limit]
