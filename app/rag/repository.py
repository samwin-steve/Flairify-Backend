"""Server-only vector projection. Every query is catalogue-owner and model-space scoped."""

import json
from concurrent.futures import ThreadPoolExecutor

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from ..models import now
from ..store import store
from .embeddings import space

KINDS = ("top", "bottom", "dress", "jacket", "shoes", "bag", "accessory")


def facet(category, department="all", store_id=None, size=None):
    return json.dumps(
        [category, department, store_id or "*", (size or "*").casefold()], separators=(",", ":")
    )


def facets(product):
    department = product.get("attributes", {}).get("department", "").lower()
    departments = {"all", department} - {""}
    if department == "unisex":
        departments.update(("women", "men"))
    keys = set()
    for variant in product["variants"]:
        for stock in variant["stock"]:
            if stock["quantity"] <= 0:
                continue
            for dep in departments:
                for location in (None, stock["store_id"]):
                    for size in (None, variant["size"]):
                        keys.add(facet(product["category"], dep, location, size))
    return sorted(keys)


def read(owner, key):
    db = store()
    if not db.cloud:
        return db.get("vectors", owner, key)
    snap = db.ref("vectors", owner, key).get()
    if not snap.exists:
        return None
    row = snap.to_dict()
    row["embedding"] = list(row["embedding"]) if row.get("embedding") else None
    return row


def publish(owner, product, row, product_digest):
    """Compare the serving record and publish vector + indexed marker atomically."""
    from ..services.inventory import product_hash

    db = store()
    row = {
        **row,
        "owner": owner,
        "id": product["id"],
        "space": space(),
        "updated_at": now(),
        "price": product["price"],
        "facets": facets(product),
        "active": product.get("active", True),
    }

    def marked(current):
        return {**current, "indexed": True, "content_hash": product_digest}

    if db.cloud:
        product_ref = db.ref("products", owner, product["id"])
        vector_ref = db.ref("vectors", owner, product["id"])

        @firestore.transactional
        def write(tx):
            snap = product_ref.get(transaction=tx)
            current = snap.to_dict()["data"] if snap.exists else None
            if not current or product_hash(current) != product_digest:
                return False
            if row["active"]:
                tx.set(vector_ref, {**row, "embedding": Vector(row["embedding"])})
            else:
                tx.delete(vector_ref)
            tx.set(product_ref, {"owner": owner, "id": product["id"], "data": marked(current)})
            return True

        return write(db.db.transaction())
    with db.lock:
        current = db.get("products", owner, product["id"])
        if not current or product_hash(current) != product_digest:
            return False
        db.put("vectors", owner, product["id"], row)
        db.put("products", owner, product["id"], marked(current))
        return True


def nearest(
    owner,
    vector,
    *,
    budget,
    department="all",
    store_id=None,
    clothing_size=None,
    shoe_size=None,
    categories=KINDS,
    limit=8,
):
    db = store()
    if not db.cloud:
        raise RuntimeError("Online semantic search requires Firestore")

    def category_candidates(category):
        size = shoe_size if category == "shoes" else clothing_size
        if category in ("bag", "accessory"):
            size = "One size" if clothing_size else None
        query = (
            db.db.collection("flairify_vectors")
            .where(filter=FieldFilter("owner", "==", owner))
            .where(filter=FieldFilter("space", "==", space()))
            .where(filter=FieldFilter("active", "==", True))
            .where(
                filter=FieldFilter("facets", "array_contains", facet(category, department, store_id, size))
            )
            .where(filter=FieldFilter("price", "<=", budget))
        )
        semantic = query.find_nearest(
            vector_field="embedding",
            query_vector=Vector(vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
            distance_result_field="distance",
        ).stream()
        rows = [d.to_dict() for d in semantic]
        # Two affordable alternatives per category prevent high-priced semantic hits
        # from crowding out combinations that satisfy the total outfit budget.
        rows += [d.to_dict() for d in query.order_by("price").limit(2).stream()]
        return rows

    with ThreadPoolExecutor(max_workers=4) as pool:
        groups = list(pool.map(category_candidates, categories))
    ids = list(dict.fromkeys(row["id"] for group in groups for row in group))
    # Bounded point reads only; never load the catalogue to perform online ranking.
    refs = [db.ref("products", owner, key) for key in ids]
    latest = {s.to_dict()["id"]: s.to_dict()["data"] for s in db.db.get_all(refs)} if refs else {}
    return [
        latest[key]
        for key in ids
        if key in latest
        and latest[key].get("indexed")
        and latest[key].get("active", True)
        and latest[key]["price"] <= budget
    ]
