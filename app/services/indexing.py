"""Enrich before embedding; retries reuse validated metadata and unchanged vectors."""

import logging
from concurrent.futures import ThreadPoolExecutor

from ..catalogue import enrichment
from ..rag import embeddings, repository
from ..store import store
from .inventory import product_hash


def index_product(owner, key):
    counts = {
        "indexed": 0,
        "enriched": 0,
        "enrichment_reused": 0,
        "embeddings_generated": 0,
        "embeddings_reused": 0,
    }
    product = store().get("products", owner, key)
    if not product:
        return counts
    if product.get("active", True) and product.get("image", "").startswith("media:"):
        from . import image_delivery

        image_delivery.warm_product(owner, product)
    product, analyzed = enrichment.ensure(owner, product)
    counts["enriched"] = int(analyzed)
    counts["enrichment_reused"] = int(not analyzed and enrichment.current(product))
    digest = product_hash(product)
    text = embeddings.document(product)
    content_digest = embeddings.digest(text)
    live = embeddings.enabled(owner)
    if not product.get("active", True) and product.get("indexed") and product.get("content_hash") == digest:
        return counts
    existing = repository.read(owner, key)
    if (
        product.get("content_hash") == digest
        and product.get("indexed")
        and existing
        and existing.get("hash") == content_digest
        and bool(existing.get("embedding")) == live
    ):
        return counts
    vector = None
    if live and product.get("active", True):
        if existing and existing.get("hash") == content_digest and existing.get("embedding"):
            vector = existing["embedding"]
            counts["embeddings_reused"] = 1
        else:
            vector = embeddings.embed(text)
            counts["embeddings_generated"] = 1
    row = {"description": text, "embedding": vector, "hash": content_digest}
    if live or not store().cloud:
        published = repository.publish(owner, product, row, digest)
    else:

        def mark(current):
            return (
                {**current, "indexed": True, "content_hash": digest}
                if current and product_hash(current) == digest
                else current
            )

        current = store().mutate("products", owner, key, mark)
        published = bool(current and current.get("content_hash") == digest)
    if not live:
        store().put("search", owner, key, {"id": key, **row})
    if not published:
        raise enrichment.RetryableEnrichmentError(
            "Listing changed before its search record could be published"
        )
    counts["indexed"] = 1
    return counts


def index_products(owner, ids):
    totals = {
        "indexed": 0,
        "enriched": 0,
        "enrichment_reused": 0,
        "embeddings_generated": 0,
        "embeddings_reused": 0,
    }
    errors = []

    def run(key):
        try:
            return index_product(owner, key), None
        except Exception as exc:  # noqa: BLE001 - isolate failed products and report a safe retryable error
            logging.getLogger(__name__).warning(
                "Catalogue indexing failed: product=%s exception=%s", key, type(exc).__name__
            )
            return {}, {
                "product_id": key,
                "error": "Analysis or search indexing could not finish. Retry this listing.",
            }

    # Two I/O-bound calls per worker; Cloud Run remains capped at two instances.
    with ThreadPoolExecutor(max_workers=2) as pool:
        for counts, error in pool.map(run, ids):
            if error:
                errors.append(error)
            for field in totals:
                totals[field] += counts.get(field, 0)
    return {
        **totals,
        "requested": len(ids),
        "errors": errors,
        "method": "gemini-embedding-2 / Firestore"
        if embeddings.enabled(owner)
        else "demo-attribute-baseline",
    }
