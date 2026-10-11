"""Seller ownership is assigned by the server, never by a product payload."""

from fastapi import HTTPException

from ..models import now
from ..store import store


def can_manage(p, row):
    return p.admin or row.get("seller_id") == p.uid


def prepare_product(p, product):
    old = store().get("products", p.catalog_owner, product.id)
    if old and not can_manage(p, old):
        raise HTTPException(403, "You can edit only your own products")
    product.seller_id = old.get("seller_id") if old else p.uid
    product.sample = (
        bool(old and old.get("sample")) or product.sample or p.demo or product.image.startswith("/images/")
    )
    product.ai_attributes = (old or {}).get("ai_attributes", {})
    product.indexed = False
    product.content_hash = ""
    product.updated_at = now()
    if not product.variants or not product.image:
        raise HTTPException(422, "Add a product photo and at least one size with stock information")
    known = {s["id"] for s in store().list("stores", p.catalog_owner) if can_manage(p, s)}
    if any(not v.stock for v in product.variants) or any(
        s.store_id not in known for v in product.variants for s in v.stock
    ):
        raise HTTPException(422, "Every size needs stock at one of your stores")
    if product.image.startswith("media:"):
        record = store().get("media", p.catalog_owner, product.image[6:])
        if not record:
            raise HTTPException(422, "Upload the product photo again")
        if (
            not p.admin
            and record.get("uploader_id") != p.uid
            and (not old or old.get("image") != product.image)
        ):
            raise HTTPException(403, "Use a product image you uploaded")
    return product


def manage_store(p, data):
    old = store().get("stores", p.catalog_owner, data.id)
    if old and not can_manage(p, old):
        raise HTTPException(403, "You can edit only your own stores")
    data.seller_id = old.get("seller_id") if old else p.uid
    data.sample = data.sample or p.demo

    def update(current):
        if current and not can_manage(p, current):
            raise HTTPException(403, "You can edit only your own stores")
        return data.model_dump()

    return store().mutate("stores", p.catalog_owner, data.id, update)
