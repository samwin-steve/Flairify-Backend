import hashlib
from ..models import WardrobeItem, DuplicateCandidate
from ..store import store
from ..config import settings
from . import media, ai


def extract(owner, photo_ids, progress):
    ai_ready = settings().ai_ready and not owner.startswith("demo-")
    if ai_ready:
        profile = store().get("profiles", owner, "me") or {}
        if not profile.get("consent", {}).get("ai_photo_processing"):
            raise ValueError("Photo processing consent was withdrawn. Enable it before retrying.")
    results = []
    for photo_id in photo_ids:
        photo = store().get("photos", owner, photo_id)
        if not photo:
            raise ValueError("A selected photo was deleted")
        progress("Finding clothes" if ai_ready else "Preparing photo for manual review")
        raw, _ = media.read(owner, photo["media_id"])
        selected = media.crop(raw, photo["person_box"], max_size=1600)
        cache_key = hashlib.sha256(selected + settings().gemini_model.encode()).hexdigest()
        cached = store().get("analysis", owner, cache_key)
        if cached:
            detections = cached["items"]
        elif ai_ready:
            from ..auth import quota

            quota("live-ai", "wardrobe-analysis", 30)
            detections = [d.model_dump() for d in ai.detect(selected)]
            store().put(
                "analysis", owner, cache_key, {"id": cache_key, "items": detections, "photo_id": photo_id}
            )
        else:
            detections = [
                {
                    "name": "Describe this garment",
                    "category": "unknown",
                    "colour": "Unknown",
                    "pattern": "Unknown",
                    "visible_details": "Add garment details and confirm ownership.",
                    "box": {"x": 0, "y": 0, "width": 1, "height": 1},
                    "uncertainty": ["Manual review required; no automated garment detection has run."],
                }
            ]
        progress("Creating garment thumbnails")
        for idx, d in enumerate(detections):
            item_id = hashlib.sha256(f"{photo_id}:{idx}".encode()).hexdigest()[:32]
            if store().get("wardrobe", owner, item_id):
                results.append(item_id)
                continue
            thumbnail = media.save(owner, media.crop(selected, d["box"], max_size=1200), source_id=photo_id)
            item = WardrobeItem(
                id=item_id,
                name=d["name"],
                category=d["category"],
                colour=d["colour"],
                pattern=d["pattern"],
                details=d["visible_details"],
                box=d["box"],
                source_photo_id=photo_id,
                image="media:" + thumbnail,
                uncertainty=d["uncertainty"]
                + ["Thumbnail is a rectangular evidence crop, not a segmented garment."],
                evidence="original_crop",
            )
            store().put("wardrobe", owner, item.id, item.model_dump(mode="json"))
            results.append(item.id)
    progress("Checking possible duplicates")
    items = store().list("wardrobe", owner)
    # Exact evidence hashes are safe candidates; never merge without a decision.
    for i, a in enumerate(items):
        if not a["image"].startswith("media:"):
            continue
        ma = store().get("media", owner, a["image"][6:])
        for b in items[i + 1 :]:
            if not b["image"].startswith("media:"):
                continue
            mb = store().get("media", owner, b["image"][6:])
            if ma and mb and ma["sha256"] == mb["sha256"]:
                group_id = hashlib.sha256(":".join(sorted([a["id"], b["id"]])).encode()).hexdigest()[:32]
                if not store().get("duplicates", owner, group_id):
                    group = DuplicateCandidate(
                        id=group_id,
                        item_ids=[a["id"], b["id"]],
                        score=1,
                        reason="The visible evidence crops are identical. Confirm whether these are the same garment.",
                        method="exact-image-hash",
                    )
                    store().put("duplicates", owner, group_id, group.model_dump())
    # Each garment gets a bounded worker job; slow image generation never blocks ownership review.
    from . import garment_images

    if garment_images.available(owner):
        progress("Queuing shop-style garment images")
        for item_id in results:
            garment_images.request(owner, item_id)
    return {
        "item_ids": results,
        "analysis": "gemini" if ai_ready else "manual",
        "segmentation": "not_enabled",
    }
