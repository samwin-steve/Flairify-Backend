"""Persisted mock orders: no payment, shipment, reservation or stock decrement."""

import hashlib
import json
from collections import defaultdict

from fastapi import HTTPException

from ..models import now
from ..store import store


def preview_context(p, key):
    from ..auth import require_record

    if not key:
        raise HTTPException(422, "Choose a completed preview first")
    job = require_record("jobs", p.uid, key)
    if (
        job["kind"] != "try_on"
        or job["status"] != "succeeded"
        or not (job.get("result") or {}).get("media_id")
    ):
        raise HTTPException(409, "Wait for your style preview to finish before buying this look")
    payload, result = job.get("payload", {}), job.get("result") or {}
    outfit_id = payload.get("outfit_id")
    if outfit_id:
        outfit = store().get("outfits", p.uid, outfit_id)
        if not outfit:
            raise HTTPException(
                409, "This recommendation is no longer available. Choose a fresh look or browse Inventory."
            )
        pieces = outfit["products"]
    else:
        pieces = [piece for piece in result.get("pieces", []) if piece["kind"] == "product"]
        if not pieces:
            pieces = [piece for piece in payload.get("selections", []) if piece["kind"] == "product"]
        legacy_id = result.get("product_id") or payload.get("product_id")
        if not pieces and legacy_id:
            pieces = [{"id": legacy_id, "name": result.get("product_name", "Selected item")}]
    return list({piece["id"]: piece for piece in pieces}.values()), outfit_id


def preview_products(p, key):
    pieces, _ = preview_context(p, key)
    products, unavailable = [], []
    for piece in pieces:
        product = store().get("products", p.catalog_owner, piece["id"])
        if (
            not product
            or not product.get("active", True)
            or not product.get("indexed")
            or not any(stock["quantity"] > 0 for v in product["variants"] for stock in v["stock"])
        ):
            unavailable.append({"id": piece["id"], "name": piece.get("name", "Selected item")})
            continue
        # Preserve the recommended variant for checkout; stock and prices are rechecked there.
        if piece.get("availability"):
            product = {**product, "availability": piece["availability"]}
        products.append(product)
    return {"products": products, "unavailable": unavailable, "preview_job_id": key}


def quote(p, request):
    allowed = None
    if request.source == "fitting_room":
        if request.outfit_id:
            raise HTTPException(422, "Use the preview reference for a Fitting Room order")
        pieces, _ = preview_context(p, request.preview_job_id)
        allowed = {piece["id"] for piece in pieces}
    elif request.preview_job_id:
        raise HTTPException(422, "A preview reference requires a Fitting Room order")
    elif request.source == "stylist":
        outfit = store().get("outfits", p.uid, request.outfit_id) if request.outfit_id else None
        if not outfit:
            raise HTTPException(409, "This look is no longer available. Choose the clothes from Inventory.")
        allowed = {item["id"] for item in outfit["products"]}
    elif request.outfit_id:
        raise HTTPException(422, "An outfit reference requires a stylist order")
    combined = defaultdict(int)
    for item in request.items:
        combined[(item.product_id, item.variant_id, item.store_id)] += item.quantity
    if any(q > 10 for q in combined.values()):
        raise HTTPException(422, "Choose no more than 10 of one size at a store")
    lines = []
    for (product_id, variant_id, store_id), quantity in sorted(combined.items()):
        product = store().get("products", p.catalog_owner, product_id)
        if not product or not product.get("active", True) or not product.get("indexed"):
            raise HTTPException(409, "A selected product is no longer available. Refresh Inventory.")
        if allowed is not None and product_id not in allowed:
            raise HTTPException(422, "Only new products from this look can be ordered")
        variant = next((v for v in product["variants"] if v["id"] == variant_id), None)
        stock = next((s for s in (variant or {}).get("stock", []) if s["store_id"] == store_id), None)
        location = store().get("stores", p.catalog_owner, store_id)
        if not variant or not stock or not location or stock["quantity"] < quantity:
            raise HTTPException(
                409, "The chosen size or quantity is unavailable at this store. Review your selection."
            )
        lines.append(
            {
                "product_id": product_id,
                "sku": product["sku"],
                "name": product["name"],
                "image": product["image"],
                "variant_id": variant_id,
                "size": variant["size"],
                "colour": variant["colour"],
                "store_id": store_id,
                "store_name": location["name"],
                "quantity": quantity,
                "unit_price": product["price"],
                "line_total": product["price"] * quantity,
                "sample": product.get("sample", False),
                "seller_id": product.get("seller_id"),
            }
        )
    return {
        "items": lines,
        "total": sum(i["line_total"] for i in lines),
        "currency": "INR",
        "mock": True,
        "payment_status": "not_required",
        "fulfillment_status": "not_scheduled",
        "notice": "Your order has been saved.",
    }


def public(order):
    return {k: v for k, v in order.items() if k != "request_fingerprint"}


def project(p, order):
    # Replayable projections: a retried request repairs an interrupted write with the same IDs.
    common = {k: order[k] for k in ("id", "created_at", "status", "source", "mock", "currency", "notice")}
    store().put(
        "order_inbox",
        p.catalog_owner,
        order["id"],
        {**common, "items": order["items"], "total": order["total"]},
    )
    sellers = {line["seller_id"] for line in order["items"] if line.get("seller_id")}
    for seller in sellers:
        lines = [line for line in order["items"] if line.get("seller_id") == seller]
        store().put(
            "seller_orders",
            seller,
            order["id"],
            {**common, "items": lines, "total": sum(i["line_total"] for i in lines)},
        )


def place(p, request):
    # Keep pre-existing checkout fingerprints stable for in-flight retries.
    excluded = {"request_key"} | ({"preview_job_id"} if request.preview_job_id is None else set())
    fingerprint = hashlib.sha256(
        json.dumps(request.model_dump(exclude=excluded), sort_keys=True).encode()
    ).hexdigest()
    key = "MO-" + hashlib.sha256(f"{p.uid}:{request.request_key}".encode()).hexdigest()[:20].upper()
    existing = store().get("orders", p.uid, key)
    if existing:
        if existing["request_fingerprint"] != fingerprint:
            raise HTTPException(409, "This checkout key was already used for a different selection")
        project(p, existing)
        return public(existing)
    from ..auth import quota

    quota(p.uid, "mock-orders", 100)
    value = quote(p, request)
    if value["total"] != request.expected_total:
        raise HTTPException(409, "The price changed. Review the updated total before placing your order.")
    value.update(
        id=key,
        status="mock_placed",
        source=request.source,
        outfit_id=request.outfit_id,
        preview_job_id=request.preview_job_id,
        created_at=now(),
        request_fingerprint=fingerprint,
    )

    def save(old):
        if old and old["request_fingerprint"] != fingerprint:
            raise HTTPException(409, "This checkout key was already used for a different selection")
        return old or value

    result = store().mutate("orders", p.uid, key, save)
    project(p, result)
    return public(result)
