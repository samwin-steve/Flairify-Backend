"""One-off bounded embedding migration using ADC/runtime identity, never a downloaded key.
Run from the backend root: python -m scripts.backfill_embeddings
Configuration matches .env.example. Existing matching vectors incur no embedding call.
"""

import json
from app.config import settings
from app.rag.embeddings import enabled
from app.services.indexing import index_products
from app.store import store

if __name__ == "__main__":
    if not enabled("retailer"):
        raise SystemExit("Configure Firestore and ENABLE_PAID_AI=true before a real backfill")
    products = store().list("products", "retailer")  # Intentional one-off migration; never the search path.
    for offset in range(0, len(products), 5):
        ids = [p["id"] for p in products[offset : offset + 5]]
        result = index_products("retailer", ids)
        print(
            json.dumps({"processed": min(offset + 5, len(products)), "total": len(products), **result}),
            flush=True,
        )
