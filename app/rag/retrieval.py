from concurrent.futures import ThreadPoolExecutor

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
    categories=None,
    category_queries=None,
    exclude_ids=(),
    deeper=False,
):
    if not embeddings.enabled(owner):
        from ..services.inventory import attribute_search

        rows = attribute_search(owner, query, budget, category)
        rows = [
            r for r in rows if (not categories or r["category"] in categories) and r["id"] not in exclude_ids
        ]
        return rows, {
            "method": "demo-attribute-baseline",
            "semantic": False,
        }
    try:
        kinds = tuple(categories or ((category,) if category else repository.KINDS))
        plans = category_queries or {k: query for k in kinds}
        unique = list(dict.fromkeys(plans[k] for k in kinds))
        with ThreadPoolExecutor(max_workers=3) as pool:
            vectors = dict(zip(unique, pool.map(lambda q: embeddings.cached_query(owner, q), unique)))
        vector = vectors[unique[0]]
        rows = repository.nearest(
            owner,
            vector,
            budget=budget,
            department=department,
            store_id=store_id,
            clothing_size=clothing_size,
            shoe_size=shoe_size,
            categories=kinds,
            category_vectors={k: vectors[plans[k]] for k in kinds},
            exclude_ids=exclude_ids,
            limit=32 if deeper else 16,
        )
        return rows, {
            "method": "firestore-vector",
            "model": "gemini-embedding-2",
            "dimensions": len(vector),
            "candidates": len(rows),
            "category_queries": len(kinds),
            "query_version": "category-context-v3-enriched",
            "semantic": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # Do not silently turn a broken production index into an unbounded full scan.
        raise HTTPException(
            503, "Semantic catalogue search is temporarily unavailable. Please try again shortly."
        ) from exc
