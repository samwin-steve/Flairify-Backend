"""Backfill versioned catalogue metadata using configured Google runtime identity / ADC.

Dry-run by default. Enqueue two bounded jobs with --enqueue --requester OWNER_UID.
Re-running is safe: unchanged analysis and embeddings are reused. Never download a key.
"""

import argparse
import json
from uuid import uuid4

from app.catalogue.enrichment import current, enabled
from app.config import settings
from app.services import jobs
from app.store import store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enqueue", action="store_true")
    parser.add_argument("--requester", help="Verified site owner UID whose activity list receives the jobs")
    parser.add_argument("--product-id", action="append", default=[])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--run-id", default=None, help="Reuse after an uncertain enqueue outcome to avoid duplicate jobs"
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500:
        parser.error("batch-size must be between 1 and 500")
    if not store().cloud:
        parser.error("Configure Firestore before backfilling the shared catalogue")
    products = store().list("products", "retailer")
    if args.product_id:
        wanted = set(args.product_id)
        products = [p for p in products if p["id"] in wanted]
        if {p["id"] for p in products} != wanted:
            parser.error("One or more requested product IDs were not found")
    ids = sorted(p["id"] for p in products)
    run_id = args.run_id or uuid4().hex
    print(
        json.dumps(
            {
                "run_id": run_id,
                "products": len(ids),
                "metadata_current": sum(current(p) for p in products),
                "metadata_pending": sum(not current(p) for p in products),
                "enqueue": args.enqueue,
            }
        ),
        flush=True,
    )
    if not args.enqueue:
        return
    if not enabled("retailer") or not settings().worker_url:
        parser.error("Enable paid catalogue enrichment and configure the private Cloud Tasks worker")
    access = store().get("seller_access", "system", args.requester) if args.requester else None
    if not access or access.get("role") != "owner":
        parser.error("requester must be a configured site owner UID")
    for offset in range(0, len(ids), args.batch_size):
        job = jobs.create(
            args.requester,
            "index",
            {"catalog_owner": "retailer", "product_ids": ids[offset : offset + args.batch_size]},
            f"catalogue-enrichment:{run_id}:{offset}",
        )
        print(
            json.dumps(
                {
                    "job_id": job["id"],
                    "status": job["status"],
                    "products": len(ids[offset : offset + args.batch_size]),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
