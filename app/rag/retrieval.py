from fastapi import HTTPException

from . import embeddings, repository


def candidates(
    owner,
    query,
    budget,
    *,
    department="all",
    store_id=None,
    clothing_size=None,
    shoe_size=None,
    category=None,
):
    if not embeddings.enabled(owner):
        from ..services.inventory import attribute_search

        return attribute_search(owner, query, budget, category), {
            "method": "demo-attribute-baseline",
            "semantic": False,
        }
    try:
        vector = embeddings.embed(query, query=True)
        rows = repository.nearest(
            owner,
            vector,
            budget=budget,
            department=department,
            store_id=store_id,
            clothing_size=clothing_size,
            shoe_size=shoe_size,
            categories=(category,) if category else repository.KINDS,
        )
        return rows, {
            "method": "firestore-vector",
            "model": "gemini-embedding-2",
            "dimensions": len(vector),
            "candidates": len(rows),
            "semantic": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # Do not silently turn a broken production index into an unbounded full scan.
        raise HTTPException(
            503, "Semantic catalogue search is temporarily unavailable. Please try again shortly."
        ) from exc
