import hashlib
import json
import math
import secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .config import settings
from .store import store
from .auth import Principal, principal, admin, create_demo_session, require_record, quota, bearer
from .models import (
    UserProfile,
    PhotoSource,
    ReferencePhoto,
    Box,
    WardrobeItem,
    ImportRequest,
    ChatRequest,
    Conversation,
    Message,
    GenerationRequest,
    SavedLook,
    Product,
    Store,
    now,
)
from .services import inventory, recommendations, jobs, media, photos, avatars


@asynccontextmanager
async def lifespan(app):
    settings()
    yield


app = FastAPI(
    title="Flairify API",
    version="0.1.0",
    description="Wardrobe-first shopping. Demo, real providers and experimental capabilities are explicitly separated.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Photos-Token"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "flairify-api"}


@app.get("/api/config")
def config(credentials=Depends(bearer)):
    c = settings()
    live = False
    if credentials:
        try:
            live = not principal(credentials).demo
        except HTTPException:
            pass
    return {
        "mode": c.app_mode,
        "analysis": "gemini" if c.ai_ready and live else "manual",
        "chat": "gemini" if c.ai_ready and live else "rules",
        "try_on": live and c.enable_paid_ai and bool(c.try_on_model or c.image_edit_model),
        "video": live and c.enable_paid_ai and bool(c.veo_model),
        "photos_client_id": c.google_photos_client_id,
        "avatar": avatars.capabilities(),
        "demo_admin": c.app_mode == "demo" and c.enable_demo_admin,
    }


@app.post("/api/auth/demo")
def demo():
    quota("public-demo", "new-session", 100)
    result = create_demo_session()
    inventory.seed_catalog(result["user_id"])
    store().put("profiles", result["user_id"], "me", UserProfile().model_dump())
    return result


class AdminUnlock(BaseModel):
    key: str = Field(max_length=200)


@app.post("/api/admin/unlock")
def unlock(data: AdminUnlock, p: Principal = Depends(principal), credentials=Depends(bearer)):
    cfg = settings()
    if not p.demo or not cfg.enable_demo_admin:
        raise HTTPException(403, "Use a Firebase account with an admin custom claim")
    expected = cfg.demo_admin_key
    if not expected or not secrets.compare_digest(data.key, expected):
        raise HTTPException(403, "Enter the configured demo administrator key")
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    session = store().get("sessions", "system", digest)
    session["admin"] = True
    store().put("sessions", "system", digest, session)
    return {"admin": True, "scope": "Only your isolated demo catalogue"}


@app.get("/api/profile")
def get_profile(p: Principal = Depends(principal)):
    if not p.demo and settings().seed_sample_catalog:
        inventory.seed_catalog(p.catalog_owner)
    value = store().get("profiles", p.uid, "me") or UserProfile().model_dump()
    return {**value, "admin": p.admin, "demo": p.demo}


@app.put("/api/profile")
def put_profile(profile: UserProfile, p: Principal = Depends(principal)):
    profile.onboarding_complete = bool(recommendations.get_confirmed_wardrobe(p.uid))
    if not profile.consent.remember_preferences:
        profile.styles = []
        profile.colours = []
        profile.clothing_size = ""
        profile.shoe_size = ""
        profile.fit = "Comfortable"
        profile.budget = 5000
    from .services.graph import clear

    clear(p.uid)
    return store().put("profiles", p.uid, "me", profile.model_dump())


@app.post("/api/wardrobe/sample")
def sample(p: Principal = Depends(principal)):
    if not p.demo:
        raise HTTPException(403, "Sample wardrobe is only available in demo mode")
    inventory.seed_wardrobe(p.uid)
    return {"items": store().list("wardrobe", p.uid)}


@app.get("/api/wardrobe")
def wardrobe(p: Principal = Depends(principal)):
    items = store().list("wardrobe", p.uid)
    return {
        "items": items,
        "confirmed_count": sum(w["confirmed"] for w in items),
        "duplicates": store().list("duplicates", p.uid),
    }


@app.put("/api/wardrobe/{key}")
def edit_garment(key: str, item: WardrobeItem, p: Principal = Depends(principal)):
    old = store().get("wardrobe", p.uid, key)
    if item.confirmed and (item.category == "unknown" or item.name == "Describe this garment"):
        raise HTTPException(422, "Name and categorize the garment before confirming ownership")
    if old:
        # Evidence fields are server-owned and cannot be reassigned to another photo.
        for field in ("image", "source_photo_id", "box", "sample", "evidence", "created_at"):
            setattr(
                item, field, Box.model_validate(old[field]) if field == "box" and old[field] else old[field]
            )
    else:
        item.source_photo_id = None
        item.image = ""
        item.evidence = "manual"
        item.sample = False
    item.id = key
    value = store().put("wardrobe", p.uid, key, item.model_dump(mode="json"))
    invalidate_looks(p.uid, key)
    return value


def invalidate_looks(owner, item_id=None):
    from .services.graph import clear

    clear(owner)
    for kind in ("outfits", "saved", "compatibility"):
        for row in store().list(kind, owner):
            store().delete(kind, owner, row["id"])
    # Historical prose may mention a deleted garment, but stale recommendation cards are removed.
    for c in store().list("conversations", owner):
        for m in c["messages"]:
            m["outfits"] = []
        store().put("conversations", owner, c["id"], c)


@app.delete("/api/wardrobe/{key}")
def delete_garment(key: str, p: Principal = Depends(principal)):
    item = require_record("wardrobe", p.uid, key)
    if item["image"].startswith("media:"):
        media.delete(p.uid, item["image"][6:])
    store().delete("wardrobe", p.uid, key)
    invalidate_looks(p.uid, key)
    for d in store().list("duplicates", p.uid):
        if key in d["item_ids"]:
            store().delete("duplicates", p.uid, d["id"])
    return {"deleted": True}


class DuplicateDecision(BaseModel):
    action: str = Field(pattern="^(merge|separate)$")
    keep_id: str | None = None


@app.post("/api/duplicates/{key}")
def duplicate_decision(key: str, data: DuplicateDecision, p: Principal = Depends(principal)):
    row = require_record("duplicates", p.uid, key)
    if data.action == "merge":
        if data.keep_id not in row["item_ids"]:
            raise HTTPException(422, "Choose the garment to keep")
        for item_id in row["item_ids"]:
            if item_id != data.keep_id and store().get("wardrobe", p.uid, item_id):
                delete_garment(item_id, p)
    row["status"] = "merged" if data.action == "merge" else "separate"
    store().put("duplicates", p.uid, key, row)
    return row


@app.post("/api/photos")
async def upload(
    file: UploadFile = File(...), kind: str = Form("wardrobe"), p: Principal = Depends(principal)
):
    if kind not in ("wardrobe", "portrait", "full_body"):
        raise HTTPException(422, "Unknown photo type")
    if (
        len(store().list("photos", p.uid)) + len(store().list("references", p.uid))
        >= settings().max_photos_per_user
    ):
        raise HTTPException(429, "Photo limit reached. Delete photos before adding more.")
    quota(p.uid, "upload", 60)
    if p.demo:
        quota("public-demo", "upload", 300)
    raw = await file.read(settings().max_upload_mb * 1024 * 1024 + 1)
    normalized, captured = media.normalize(raw)
    media_id = media.save(p.uid, normalized)
    if kind != "wardrobe":
        ref = ReferencePhoto(id=kind, kind=kind, media_id=media_id)
        old = store().get("references", p.uid, kind)
        if old:
            media.delete(p.uid, old["media_id"])
        return store().put("references", p.uid, kind, ref.model_dump())
    source = PhotoSource(
        media_id=media_id, original_media_id=media.save_original(p.uid, raw), captured_at=captured
    )
    return store().put("photos", p.uid, source.id, source.model_dump())


@app.get("/api/photos")
def list_photos(p: Principal = Depends(principal)):
    return {"photos": store().list("photos", p.uid), "references": store().list("references", p.uid)}


class Selection(BaseModel):
    person_box: Box
    group_photo: bool = False


@app.patch("/api/photos/{key}")
def select_person(key: str, data: Selection, p: Principal = Depends(principal)):
    row = require_record("photos", p.uid, key)
    if data.group_photo and data.person_box.width * data.person_box.height > 0.95:
        raise HTTPException(422, "Select the person in this group photo before processing")
    row.update(data.model_dump())
    return store().put("photos", p.uid, key, row)


@app.delete("/api/photos/{key}")
def delete_photo(key: str, p: Principal = Depends(principal)):
    row = store().get("photos", p.uid, key)
    kind = "photos"
    if not row:
        row = require_record("references", p.uid, key)
        kind = "references"
    for job in store().list("jobs", p.uid):
        if key in job["payload"].get("photo_ids", []) or job["payload"].get("reference_id") == key:
            delete_job(job["id"], p)
    for item in store().list("wardrobe", p.uid):
        if item.get("source_photo_id") == key:
            delete_garment(item["id"], p)
    for a in store().list("analysis", p.uid):
        if a.get("photo_id") == key and a.get("id"):
            store().delete("analysis", p.uid, a["id"])
    media.delete(p.uid, row["media_id"])
    if row.get("original_media_id"):
        media.delete(p.uid, row["original_media_id"])
    store().delete(kind, p.uid, key)
    for m in store().list("media", p.uid):
        if m.get("source_id") == key:
            media.delete(p.uid, m["id"])
    return {"deleted": True}


@app.get("/api/media/{key}")
def get_media(key: str, p: Principal = Depends(principal)):
    raw, mime = media.read(p.uid, key)
    return Response(
        raw,
        media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/catalog/media/{key}")
def product_media(key: str, p: Principal = Depends(principal)):
    if not any(v["image"] == "media:" + key for v in store().list("products", p.catalog_owner)):
        raise HTTPException(404, "Product image not found")
    raw, mime = media.read(p.catalog_owner, key)
    return Response(raw, media_type=mime, headers={"Cache-Control": "private, no-store"})


@app.post("/api/wardrobe/import")
def start_import(data: ImportRequest, p: Principal = Depends(principal)):
    quota(p.uid, "analysis", 20)
    profile = store().get("profiles", p.uid, "me") or {}
    if settings().ai_ready and not p.demo and not profile.get("consent", {}).get("ai_photo_processing"):
        raise HTTPException(409, "Enable photo processing consent in Profile first")
    for key in data.photo_ids:
        require_record("photos", p.uid, key)
    return jobs.create(p.uid, "wardrobe", data.model_dump(), ":".join(sorted(data.photo_ids)))


@app.post("/api/onboarding/complete")
def complete(p: Principal = Depends(principal)):
    if not recommendations.get_confirmed_wardrobe(p.uid):
        raise HTTPException(409, "Confirm at least one garment first")
    if any(
        j["kind"] == "wardrobe" and j["status"] in ("queued", "running") for j in store().list("jobs", p.uid)
    ):
        raise HTTPException(409, "Wait for wardrobe processing to finish")
    profile = store().get("profiles", p.uid, "me") or UserProfile().model_dump()
    profile["onboarding_complete"] = True
    store().put("profiles", p.uid, "me", profile)
    return {"ready": True, "confirmed_count": len(recommendations.get_confirmed_wardrobe(p.uid))}


@app.get("/api/catalog")
def catalog(
    q: str = "", category: str | None = None, budget: int = 1000000, p: Principal = Depends(principal)
):
    return {"products": inventory.search(p.catalog_owner, q, budget, category)}


@app.get("/api/stores")
def stores(lat: float | None = None, lon: float | None = None, p: Principal = Depends(principal)):
    rows = store().list("stores", p.catalog_owner)
    if lat is not None and lon is not None:
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise HTTPException(422, "Invalid coordinates")
        for r in rows:
            if r["latitude"] is not None and r["longitude"] is not None:
                a, b = math.radians(lat), math.radians(r["latitude"])
                dlat = b - a
                dlon = math.radians(r["longitude"] - lon)
                hav = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
                r["distance_km"] = round(6371 * 2 * math.asin(math.sqrt(min(1, hav))), 1)
                r["distance_label"] = "Approximate straight-line distance" + (
                    " to a sample location" if r["sample"] else ""
                )
        rows.sort(key=lambda r: r.get("distance_km", float("inf")))
    return {"stores": rows}


@app.get("/api/conversations")
def conversations(p: Principal = Depends(principal)):
    return {
        "conversations": sorted(
            store().list("conversations", p.uid), key=lambda c: c["updated_at"], reverse=True
        )
    }


@app.post("/api/chat")
def chat(data: ChatRequest, p: Principal = Depends(principal)):
    profile = store().get("profiles", p.uid, "me") or {}
    if not profile.get("onboarding_complete"):
        raise HTTPException(409, "Complete your wardrobe review before your first chat")
    quota(p.uid, "chat", 50)
    if not p.demo and settings().ai_ready:
        quota("live-ai", "chat", 50)
    if data.conversation_id:
        convo = Conversation.model_validate(require_record("conversations", p.uid, data.conversation_id))
    else:
        convo = Conversation(title=data.message[:60])
    if len(convo.messages) > 100:
        raise HTTPException(409, "Start a new conversation to continue")
    result = recommendations.recommend(p, data, convo.intent)
    convo.messages += [
        Message(role="user", content=data.message),
        Message(role="assistant", content=result["text"], outfits=result["outfits"]),
    ]
    convo.intent = result["intent"]
    convo.updated_at = now()
    store().put("conversations", p.uid, convo.id, convo.model_dump(mode="json"))
    return {**result, "conversation": convo.model_dump(mode="json")}


@app.get("/api/saved")
def saved(p: Principal = Depends(principal)):
    return {"looks": store().list("saved", p.uid)}


@app.post("/api/saved/{key}")
def save_look(key: str, p: Principal = Depends(principal)):
    outfit = require_record("outfits", p.uid, key)
    look = SavedLook(id=key, outfit=outfit).model_dump(mode="json")
    return store().put("saved", p.uid, key, look)


@app.delete("/api/saved/{key}")
def unsave(key: str, p: Principal = Depends(principal)):
    store().delete("saved", p.uid, key)
    return {"deleted": True}


@app.get("/api/jobs")
def list_jobs(p: Principal = Depends(principal)):
    rows = store().list("jobs", p.uid)
    for j in rows:
        if (
            j["status"] in ("queued", "running")
            and j.get("lease_until", 0) < time.time()
            and not settings().worker_url
        ):
            jobs.enqueue(p.uid, j["id"])
    return {"jobs": [jobs.public(j) for j in sorted(rows, key=lambda j: j["created_at"], reverse=True)]}


@app.post("/api/generate/{kind}")
def generate(kind: str, data: GenerationRequest, p: Principal = Depends(principal)):
    if kind not in ("try_on", "video", "avatar"):
        raise HTTPException(404, "Unknown generation type")
    # Check idempotency before charging the quota.
    key = hashlib.sha256(f"{kind}:{data.request_key}".encode()).hexdigest()[:32]
    existing = store().get("jobs", p.uid, key)
    if existing:
        return jobs.public(existing)
    quota(p.uid, "generation", settings().max_daily_generations)
    if kind == "try_on":
        require_record("outfits", p.uid, data.outfit_id)
    if kind == "video":
        source = require_record("jobs", p.uid, data.source_job_id)
        if (
            source["kind"] != "try_on"
            or source["status"] != "succeeded"
            or not source.get("result", {}).get("accepted")
        ):
            raise HTTPException(409, "Accept a successful try-on preview first")
    payload = {**data.model_dump(), "catalog_owner": p.catalog_owner}
    return jobs.create(p.uid, kind, payload, data.request_key)


@app.post("/api/jobs/{key}/accept")
def accept(key: str, p: Principal = Depends(principal)):
    row = require_record("jobs", p.uid, key)
    if row["status"] != "succeeded" or row["kind"] not in ("try_on", "video"):
        raise HTTPException(409, "Only successful generated media can be accepted")
    row["result"]["accepted"] = True
    store().put("jobs", p.uid, key, row)
    return jobs.public(row)


@app.post("/api/jobs/{key}/retry")
def retry(key: str, p: Principal = Depends(principal)):
    row = require_record("jobs", p.uid, key)
    if row["status"] != "failed" or row["attempts"] >= 3:
        raise HTTPException(409, "This job cannot be retried; maximum three attempts")
    quota(p.uid, "generation-retries", 5)
    jobs.update(p.uid, key, status="queued", error=None, lease_until=0)
    jobs.enqueue(p.uid, key)
    return {"queued": True}


@app.delete("/api/jobs/{key}")
def delete_job(key: str, p: Principal = Depends(principal)):
    row = require_record("jobs", p.uid, key)
    if row.get("result") and row["result"].get("media_id"):
        media.delete(p.uid, row["result"]["media_id"])
    row.update(status="cancelled", stage="Deleted", result=None)
    store().put("jobs", p.uid, key, row)
    for child in store().list("jobs", p.uid):
        if child["payload"].get("source_job_id") == key and child["status"] != "cancelled":
            delete_job(child["id"], p)
    return {"deleted": True}


@app.post("/api/photos-picker")
def picker_create(p: Principal = Depends(principal), x_photos_token: str = Header("")):
    quota(p.uid, "picker", 20)
    return photos.create(p.uid, x_photos_token)


@app.get("/api/photos-picker/{key}")
def picker_get(key: str, p: Principal = Depends(principal), x_photos_token: str = Header("")):
    return photos.poll(p.uid, key, x_photos_token)


@app.post("/api/photos-picker/{key}/import")
def picker_import(key: str, p: Principal = Depends(principal), x_photos_token: str = Header("")):
    if len(store().list("photos", p.uid)) > settings().max_photos_per_user - 12:
        raise HTTPException(429, "Make room for selected photos by deleting old photos")
    return photos.import_selected(p.uid, key, x_photos_token)


@app.delete("/api/photos-picker/{key}")
def picker_delete(key: str, p: Principal = Depends(principal), x_photos_token: str = Header("")):
    photos.delete(p.uid, key, x_photos_token)
    return {"deleted": True}


@app.get("/api/admin/catalog")
def admin_catalog(p: Principal = Depends(admin)):
    return {
        "products": store().list("products", p.catalog_owner),
        "stores": store().list("stores", p.catalog_owner),
    }


@app.post("/api/admin/import")
async def import_catalog(file: UploadFile = File(...), p: Principal = Depends(admin)):
    records = inventory.parse_import(await file.read(2 * 1024 * 1024 + 1), file.filename or "catalogue.json")
    keys = []
    for product in records:
        product.sample = p.demo
        product.indexed = False
        product.updated_at = now()
        validate_product(product, p)
    for product in records:
        old = store().get("products", p.catalog_owner, product.id)
        if old and inventory.product_hash(old) == inventory.product_hash(product.model_dump()):
            continue
        store().put("products", p.catalog_owner, product.id, product.model_dump())
        keys.append(product.id)
    return jobs.create(
        p.uid, "index", {"catalog_owner": p.catalog_owner, "product_ids": keys}, secrets.token_hex(16)
    )


def validate_product(product, p):
    known = {s["id"] for s in store().list("stores", p.catalog_owner)}
    if any(s.store_id not in known for v in product.variants for s in v.stock):
        raise HTTPException(422, "Every stock record must reference a known store")
    if product.image.startswith("media:"):
        require_record("media", p.catalog_owner, product.image[6:])


@app.put("/api/admin/products/{key}")
def edit_product(key: str, product: Product, p: Principal = Depends(admin)):
    product.id = key
    product.sample = p.demo
    product.indexed = False
    product.updated_at = now()
    validate_product(product, p)
    store().put("products", p.catalog_owner, key, product.model_dump())
    return jobs.create(
        p.uid, "index", {"catalog_owner": p.catalog_owner, "product_ids": [key]}, secrets.token_hex(16)
    )


@app.post("/api/admin/reindex")
def reindex(p: Principal = Depends(admin)):
    return jobs.create(
        p.uid,
        "index",
        {
            "catalog_owner": p.catalog_owner,
            "product_ids": [r["id"] for r in store().list("products", p.catalog_owner)],
        },
        secrets.token_hex(16),
    )


@app.put("/api/admin/stores/{key}")
def edit_store(key: str, data: Store, p: Principal = Depends(admin)):
    data.id = key
    data.sample = p.demo
    return store().put("stores", p.catalog_owner, key, data.model_dump())


@app.post("/api/admin/images")
async def upload_product_image(file: UploadFile = File(...), p: Principal = Depends(admin)):
    raw, _ = media.normalize(await file.read(settings().max_upload_mb * 1024 * 1024 + 1))
    return {"image": "media:" + media.save(p.catalog_owner, raw)}


@app.get("/api/admin/sample-import")
def sample_import(p: Principal = Depends(admin)):
    return Response(
        (inventory.FIXTURES / "catalogue.json").read_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="flairify-sample-catalogue.json"'},
    )


@app.get("/api/compatibility")
def compatibility(p: Principal = Depends(principal)):
    return {
        "assessments": store().list("compatibility", p.uid),
        "nodes": store().list("nodes", p.uid),
        "relationships": store().list("relationships", p.uid),
        "method": "Scored hypotheses for shortlisted whole outfits; not universal pair compatibility",
    }


class Feedback(BaseModel):
    value: str = Field(pattern="^(useful|not_useful)$")


@app.post("/api/compatibility/{key}/feedback")
def feedback(key: str, data: Feedback, p: Principal = Depends(principal)):
    row = require_record("compatibility", p.uid, key)
    row["feedback"] = data.value
    store().put("compatibility", p.uid, key, row)
    return row
