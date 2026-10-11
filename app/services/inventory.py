import csv
import hashlib
import io
import json
from pathlib import Path

from fastapi import HTTPException

from ..models import Product, Store, WardrobeItem
from ..store import store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def seed_catalog(owner):
    if store().get("meta", owner, "seeded"):
        return
    for name, kind, model in [("catalogue", "products", Product), ("stores", "stores", Store)]:
        for record in json.loads((FIXTURES / f"{name}.json").read_text()):
            item = model.model_validate(record).model_dump(mode="json")
            store().put(kind, owner, item["id"], item)
    store().put("meta", owner, "seeded", {"done": True})


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


def search(owner, q="", budget=1000000, category=None):
    words = q.lower().split()
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
        return sum(w in text for w in words)

    return sorted(records, key=lambda p: (-score(p), p["price"], p["id"]))[:60]


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
