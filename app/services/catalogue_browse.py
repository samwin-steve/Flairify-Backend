"""Small owner-scoped catalogue pages; no embeddings or full analysis in browse reads."""

import hashlib
import re

from fastapi import HTTPException

from ..models import Product
from ..store import store
from . import inventory, styling

FIELDS = tuple(key for key in Product.model_fields if key != "enrichment")


def matches(row, budget, category, department, available_only):
    return (
        row.get("active", True)
        and row.get("indexed")
        and row["price"] <= budget
        and (not category or row["category"] == category)
        and (not department or row.get("attributes", {}).get("department") in (department, "unisex"))
        and (not available_only or any(s["quantity"] > 0 for v in row["variants"] for s in v["stock"]))
        and not styling.quality_issue(row)
    )


def selected(owner, ids):
    keys = list(dict.fromkeys(ids.split(",")))
    if not 1 <= len(keys) <= 20 or not all(re.fullmatch(r"[\w-]{1,100}", key) for key in keys):
        raise HTTPException(422, "Choose between 1 and 20 valid product IDs")
    return [
        row
        for row in store().get_many("products", owner, keys, fields=FIELDS)
        if matches(row, 10000000, None, None, False)
    ]


def page(
    owner,
    *,
    q="",
    budget=1000000,
    category=None,
    department=None,
    available_only=True,
    page_size=24,
    cursor=None,
):
    db = store()
    if q.strip():
        if cursor and not re.fullmatch(r"search:[0-9]{1,3}", cursor):
            raise HTTPException(422, "Invalid search cursor")
        offset = int(cursor.split(":")[1]) if cursor else 0
        exact = []
        if db.cloud:
            from google.cloud.firestore_v1.base_query import FieldFilter

            request = (
                db.db.collection("flairify_products")
                .where(filter=FieldFilter("owner", "==", owner))
                .where(filter=FieldFilter("data.name", "==", q.strip()))
            )
            exact = [
                snap.to_dict()["data"]
                for snap in request.select(["data." + key for key in FIELDS]).limit(48).stream()
            ]
        rows = exact or inventory.search(owner, q, budget, category)
        literal = [
            row for row in rows if q.casefold() in (row["name"] + " " + row.get("description", "")).casefold()
        ]
        if literal:
            rows = literal
        rows = [row for row in rows if matches(row, budget, category, department, available_only)]
        end = offset + page_size
        return {
            "products": rows[offset:end],
            "next_cursor": f"search:{end}" if len(rows) > end else None,
            "page_size": page_size,
        }
    if cursor and not re.fullmatch(r"[0-9a-f]{64}", cursor):
        raise HTTPException(422, "Invalid catalogue cursor")
    if db.cloud:
        from google.cloud.firestore_v1.base_query import FieldFilter

        collection = db.db.collection("flairify_products")
        query = collection.where(filter=FieldFilter("owner", "==", owner)).where(
            filter=FieldFilter("data.active", "==", True)
        )
        if category:
            query = query.where(filter=FieldFilter("data.category", "==", category))
        if department:
            query = query.where(
                filter=FieldFilter("data.attributes.department", "in", list({department, "unisex"}))
            )
        query = query.order_by("__name__").select(["data." + key for key in FIELDS])

        def load(after, count):
            request = query.start_after({"__name__": collection.document(after)}) if after else query
            return [(snap.id, snap.to_dict()["data"]) for snap in request.limit(count).stream()]
    else:
        rows = db.list("products", owner, fields=FIELDS)
        batch = sorted(
            (hashlib.sha256(f"{owner}:{row['id']}".encode()).hexdigest(), row)
            for row in rows
            if row.get("active", True)
            and (not category or row["category"] == category)
            and (not department or row.get("attributes", {}).get("department") in (department, "unisex"))
        )

        def load(after, count):
            return [(key, row) for key, row in batch if not after or key > after][:count]

    visible, scanned, after, more = [], 0, cursor, True
    # Fill a page despite a few unavailable or rejected records. Bound sparse scans.
    while len(visible) < page_size and scanned < page_size * 4 and more:
        count = page_size - len(visible)
        chunk = load(after, count)
        scanned += len(chunk)
        more = len(chunk) == count
        if chunk:
            after = chunk[-1][0]
        visible.extend(row for _, row in chunk if matches(row, budget, category, department, available_only))
    return {"page_size": page_size, "products": visible, "next_cursor": after if more else None}
