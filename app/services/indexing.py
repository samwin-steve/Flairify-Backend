"""Changed-only indexing; resumable jobs safely reuse completed product embeddings."""

from ..rag import embeddings, repository
from ..store import store
from .inventory import product_hash


def index_products(owner, ids):
    changed = generated = reused = 0
    for key in ids:
        product = store().get("products", owner, key)
        if not product:
            continue
        digest = product_hash(product)
        text = embeddings.document(product)
        content_digest = embeddings.digest(text)
        live = embeddings.enabled(owner)
        if (
            not product.get("active", True)
            and product.get("indexed")
            and product.get("content_hash") == digest
        ):
            continue
        existing = repository.read(owner, key)
        if (
            product.get("content_hash") == digest
            and product.get("indexed")
            and existing
            and existing.get("hash") == content_digest
            and bool(existing.get("embedding")) == live
        ):
            continue
        vector = None
        if live and product.get("active", True):
            if existing and existing.get("hash") == content_digest and existing.get("embedding"):
                vector = existing["embedding"]
                reused += 1
            else:
                vector = embeddings.embed(text)
                generated += 1
        row = {"description": text, "embedding": vector, "hash": content_digest}
        if live:
            published = repository.publish(owner, product, row, digest)
        else:
            # Demo projections carry no invented vectors and use the attribute baseline.
            store().put("search", owner, key, {"id": key, **row})
            published = repository.publish(owner, product, row, digest) if not store().cloud else False
            if store().cloud:

                def mark(current, expected=digest):
                    return (
                        {**current, "indexed": True, "content_hash": expected}
                        if current and product_hash(current) == expected
                        else current
                    )

                current = store().mutate("products", owner, key, mark)
                published = bool(current and current.get("content_hash") == digest)
        changed += int(published)
    return {
        "indexed": changed,
        "requested": len(ids),
        "embeddings_generated": generated,
        "embeddings_reused": reused,
        "method": "gemini-embedding-2 / Firestore"
        if embeddings.enabled(owner)
        else "demo-attribute-baseline",
    }
