"""Publish explicitly selected photo drafts using an owner-approved commerce policy.

Dry-run by default. --write requires a backup path and queues durable index jobs.
Use runtime identity/ADC. No Drive credentials or photos are embedded in this script.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.catalogue.publication import PublicationPolicy, activate
from app.models import now
from app.services import jobs
from app.store import store


def publish_one(original, proposed):
    key = original["id"]
    digest = proposed["enrichment"]["input_hash"]
    store().put(
        "catalogue_analysis",
        "retailer",
        key + "-" + digest,
        {
            "status": "complete",
            "product_id": key,
            "record": proposed["enrichment"],
            "lease_until": 0,
            "reused_from_input_hash": original["enrichment"]["input_hash"],
            "reuse_reason": "commerce_activation_with_repeated_known_colour",
            "reused_at": now(),
        },
    )

    def compare(latest):
        if latest != original:
            raise ValueError("Listing changed since validation; refusing to replace seller edits")
        return proposed

    store().mutate("products", "retailer", key, compare)
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-ids", type=Path, required=True, help="JSON list of explicit imported IDs")
    parser.add_argument("--policy", type=Path, default=Path("config/photo-catalogue-pricing.json"))
    parser.add_argument("--requester", required=True)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    access = store().get("seller_access", "system", args.requester)
    if not access or access.get("role") != "owner":
        raise ValueError("A configured website owner must run this publication")
    policy = PublicationPolicy.model_validate_json(args.policy.read_text())
    ids = json.loads(args.product_ids.read_text())
    if (
        not isinstance(ids, list)
        or not ids
        or len(ids) != len(set(ids))
        or not all(isinstance(key, str) for key in ids)
    ):
        raise ValueError("Supply unique product IDs")
    available = {p["id"]: p for p in store().list("products", "retailer")}
    if not set(ids) <= available.keys():
        raise ValueError("Some requested products do not exist")
    stores = {s["id"] for s in store().list("stores", "retailer")}
    pairs = [(available[key], activate(available[key], policy, args.requester, stores)) for key in ids]
    pending = [(before, after) for before, after in pairs if after]
    print(
        json.dumps(
            {
                "selected": len(ids),
                "to_publish": len(pending),
                "already_published": len(ids) - len(pending),
                "policy": policy.model_dump(),
                "write": args.write,
            }
        ),
        flush=True,
    )
    if not args.write:
        return
    if not args.backup:
        raise ValueError("--backup is required for live publication")
    # Never replace the original checkpoint with already-published rows during a retry.
    if not args.backup.exists():
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        args.backup.write_text(json.dumps([available[key] for key in ids]))
        args.backup.chmod(0o600)
    else:
        backup = json.loads(args.backup.read_text())
        if {p["id"] for p in backup} != set(ids):
            raise ValueError("Backup belongs to a different publication")
    with ThreadPoolExecutor(max_workers=4) as pool:
        for count, _ in enumerate(pool.map(lambda pair: publish_one(*pair), pending), 1):
            if count % 50 == 0 or count == len(pending):
                print(json.dumps({"published": count, "total": len(pending)}), flush=True)
    # Identical policy + IDs produce identical job IDs. A rerun repairs an interrupted enqueue.
    import hashlib

    scope = hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()[:16]
    queued = []
    for offset in range(0, len(ids), 100):
        job = jobs.create(
            args.requester,
            "index",
            {"catalog_owner": "retailer", "product_ids": sorted(ids)[offset : offset + 100]},
            f"photo-publication:{policy.version}:{scope}:{offset}",
        )
        queued.append(job["id"])
    result = {"policy": policy.version, "product_count": len(ids), "job_ids": queued, "requested_at": now()}
    args.backup.with_suffix(".jobs.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
