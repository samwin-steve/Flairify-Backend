"""Prepare private catalogue thumbnails without generating images or changing products.

Run with ADC/runtime identity. Dry-run by default; --write stores immutable WebP
variants in the existing private bucket. Original media and catalogue facts stay intact.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from app.services import image_delivery
from app.store import store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    ids = sorted(
        {
            p["image"][6:]
            for p in store().list("products", "retailer")
            if p.get("active", True) and p.get("image", "").startswith("media:")
        }
    )
    print(json.dumps({"catalogue_images": len(ids), "width": 384, "write": args.write}), flush=True)
    if not args.write:
        return

    def warm(key):
        record = store().get("media", "retailer", key)
        if not record or record.get("deleting"):
            return {"error": "Source is missing"}
        try:
            raw = image_delivery.thumbnail("retailer", record, 384)
            return {"original_bytes": record["size"], "thumbnail_bytes": len(raw)}
        except Exception as exc:  # noqa: BLE001 - isolate failures without logging image content
            return {"error": type(exc).__name__}

    result = {"images": len(ids), "completed": 0, "original_bytes": 0, "thumbnail_bytes": 0, "errors": []}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, value in enumerate(pool.map(warm, ids), 1):
            if value.get("error"):
                result["errors"].append({"media_id": ids[index - 1], "error": value["error"]})
            else:
                result["completed"] += 1
                for field in ("original_bytes", "thumbnail_bytes"):
                    result[field] += value[field]
            if index % 50 == 0:
                print(
                    json.dumps({"processed": index, "total": len(ids), "errors": len(result["errors"])}),
                    flush=True,
                )
    result["bytes_reduction_percent"] = (
        round(100 * (1 - result["thumbnail_bytes"] / result["original_bytes"]), 2)
        if result["original_bytes"]
        else 0
    )
    print(json.dumps(result), flush=True)
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
