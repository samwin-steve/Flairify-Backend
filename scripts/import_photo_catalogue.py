"""Import locally staged Drive photographs as private, unpublished catalogue drafts.

The manifest contains observed Drive metadata (id, title, folder, url); images are
downloaded through the authenticated Drive connector before this operator script.
Usage: python -m scripts.import_photo_catalogue --directory /path/to/staging
       --manifest /path/to/files.json --requester OWNER_UID --write
Never downloads arbitrary URLs, guesses commercial fields, or replaces existing listings.
"""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from app.catalogue import enrichment
from app.catalogue.image_import import PhotoListing, product_id, visual_only
from app.models import Product
from app.services import media
from app.store import store


def image_path(root, row):
    path = (root / "images" / row["folder"] / row["title"]).resolve()
    if not path.is_relative_to((root / "images").resolve()):
        raise ValueError("Image path must stay inside the staging directory")
    return path


def unique_images(root, rows):
    seen, unique, duplicates = {}, [], []
    for row in sorted(rows, key=lambda r: (r["folder"], r["title"])):
        path = image_path(root, row)
        raw = path.read_bytes()
        media.normalize(raw)  # Validate format, byte and pixel limits before decoding below.
        with Image.open(path) as image:
            image = image.convert("RGB")
            digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        if digest in seen:
            duplicates.append({"file_id": row["id"], "same_as": seen[digest]})
        else:
            seen[digest] = row["id"]
            unique.append(row)
    return unique, duplicates


def import_one(root, row, requester):
    key = product_id(row["id"])
    prepared = root / "prepared" / (key + ".json")
    if not prepared.exists():
        return {"id": key, "status": "awaiting_analysis"}
    record = json.loads(prepared.read_text())
    if record["file"]["id"] != row["id"]:
        raise ValueError("Prepared photo identity does not match the manifest")
    listing = visual_only(PhotoListing.model_validate(record["listing"]))
    if not listing.usable:
        return {"id": key, "status": "needs_review"}
    old = store().get("products", "retailer", key)
    if old and old.get("attributes", {}).get("source_drive_file_id") != row["id"]:
        raise ValueError("Product identity collision")
    if not old:
        # Durable media checkpoint makes retries reuse already uploaded originals/crops.
        checkpoint = store().get("catalogue_imports", "retailer", key) or {"id": key}
        for kind, raw in (
            ("original", image_path(root, row).read_bytes()),
            ("crop", (root / "prepared" / (key + ".jpg")).read_bytes()),
        ):
            if kind not in checkpoint:
                normalized, _ = media.normalize(raw)
                mid = media.save("retailer", normalized, source_id="drive:" + row["id"])
                uploaded = store().get("media", "retailer", mid)
                uploaded["uploader_id"] = requester
                store().put("media", "retailer", mid, uploaded)
                checkpoint[kind] = mid
                store().put("catalogue_imports", "retailer", key, checkpoint)
        folder = row["folder"]
        department = (
            "women"
            if folder.startswith("womens-") or folder.endswith("-woman") or folder == "evening-dresses"
            else "men"
            if folder.startswith("mens-") or folder.endswith("-man")
            else "unisex"
        )
        product = Product(
            id=key,
            sku="DRIVE-" + key[6:].upper(),
            name=listing.name,
            description=listing.description,
            category=listing.category,
            price=0,
            image="media:" + checkpoint["crop"],
            active=False,
            seller_id=requester,
            attributes={
                "catalogue_status": "draft",
                "source_drive_file_id": row["id"],
                "source_collection": folder,
                "source_file_name": row["title"],
                "source_url": row["url"],
                "source_photo_id": checkpoint["original"],
                "source_pixel_sha256": record["sha256_pixels"],
                "description_source": "gemini_visual",
                "department": department,
                "colour": listing.colour,
                "pattern": listing.pattern,
                "commercial_details": "price_sizes_stock_pending",
            },
            ai_attributes={
                "extraction_model": record["model"],
                "evidence": "original_crop",
                "uncertainty": " ".join(listing.uncertainty),
            },
        ).model_dump(mode="json")
        old = store().mutate("products", "retailer", key, lambda existing: existing or product)
    # Private drafts receive metadata now; publishing later triggers normal indexing.
    current, analyzed = enrichment.ensure("retailer", old, include_inactive=True)
    return {"id": key, "status": current["enrichment"]["status"], "analyzed": analyzed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--requester", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    access = store().get("seller_access", "system", args.requester)
    if not access or access.get("role") != "owner":
        parser.error("requester must be an authorized site owner")
    rows, duplicates = unique_images(args.directory, json.loads(args.manifest.read_text()))
    print(
        json.dumps({"unique_images": len(rows), "duplicates": len(duplicates), "write": args.write}),
        flush=True,
    )
    if not args.write:
        return
    report = {"duplicates": duplicates, "products": [], "errors": []}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(import_one, args.directory, row, args.requester): row for row in rows}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                report["products"].append(future.result())
            except Exception as exc:  # noqa: BLE001 - isolate a failed listing and allow resumable import
                report["errors"].append({"file_id": futures[future]["id"], "error_type": type(exc).__name__})
            if n % 10 == 0 or n == len(rows):
                from collections import Counter

                print(
                    json.dumps(
                        {
                            "processed": n,
                            "of": len(rows),
                            "states": dict(Counter(r["status"] for r in report["products"])),
                            "errors": len(report["errors"]),
                        }
                    ),
                    flush=True,
                )
                (args.directory / "import-result.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
