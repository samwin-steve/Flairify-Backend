import hashlib
import math
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import Principal, admin, bearer, create_demo_session, merchant, principal, quota, require_record
from .config import settings
from .models import (
    Box,
    ChatRequest,
    Conversation,
    GenerationRequest,
    ImportRequest,
    Message,
    OrderQuoteRequest,
    PhotoSource,
    PlaceOrderRequest,
    Product,
    ReferencePhoto,
    SavedLook,
    Store,
    UserProfile,
    WardrobeItem,
    now,
)
from .services import (
    avatars,
    garment_images,
    inventory,
    jobs,
    media,
    orders,
    photos,
    recommendations,
    sellers,
    try_on,
)
from .store import store


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
        "sample_try_on": c.allow_sample_try_on,
        "generation_provider": "Google Vertex AI",
        "garment_images": live and garment_images.available("signed-in"),
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
    return {**value, "admin": p.admin, "demo": p.demo, "seller": p.seller}


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
        "items": [garment_images.public(p.uid, item) for item in items],
        "confirmed_count": sum(w["confirmed"] for w in items),
        "duplicates": store().list("duplicates", p.uid),
    }


@app.put("/api/wardrobe/{key}")
def edit_garment(key: str, item: WardrobeItem, p: Principal = Depends(principal)):
    if item.confirmed and (item.category == "unknown" or item.name == "Describe this garment"):
        raise HTTPException(422, "Name and categorize the garment before confirming ownership")

    def update(old):
        value = item.model_dump(mode="json")
        value["id"] = key
        # Preserve concurrently generated media; all evidence/provenance is server-owned.
        for field in garment_images.FIELDS:
            value[field] = old.get(field) if old else None
        if old:
            for field in ("image", "source_photo_id", "box", "sample", "evidence", "created_at"):
                value[field] = old[field]
        else:
            value.update(source_photo_id=None, image="", evidence="manual", sample=False, box=None)
        return value

    value = store().mutate("wardrobe", p.uid, key, update)
    invalidate_looks(p.uid, key)
    return value


@app.post("/api/wardrobe/{key}/shop-image")
def create_garment_image(key: str, p: Principal = Depends(principal)):
    require_record("wardrobe", p.uid, key)
    try:
        return garment_images.request(p.uid, key)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


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
    # Remove the record first so an in-flight image cannot re-publish this garment.
    store().delete("wardrobe", p.uid, key)
    for job in store().list("jobs", p.uid):
        if job["kind"] == "garment_image" and job["payload"].get("item_id") == key:
            delete_job(job["id"], p)
    if item["image"].startswith("media:"):
        media.delete(p.uid, item["image"][6:])
    if item.get("generated_image"):
        media.delete(p.uid, item["generated_image"][6:])
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
    if kind == "portrait":
        old = store().get("references", p.uid, kind)
        if old:
            delete_photo(kind, p)
        ref = ReferencePhoto(id=kind, kind=kind, media_id=media_id)
        return store().put("references", p.uid, kind, ref.model_dump())
    source = PhotoSource(
        media_id=media_id, original_media_id=media.save_original(p.uid, raw), captured_at=captured
    )
    store().put("photos", p.uid, source.id, source.model_dump(mode="json"))
    if kind == "full_body":
        old = store().get("references", p.uid, kind)
        if old and not old.get("source_photo_id"):
            media.delete(p.uid, old["media_id"])
        ref = ReferencePhoto(id=kind, kind=kind, media_id=media_id, source_photo_id=source.id)
        store().put("references", p.uid, kind, ref.model_dump())
        auto_analyze(p, source.id)
        return ref.model_dump()
    return source.model_dump(mode="json")


def auto_analyze(p, photo_id):
    profile = store().get("profiles", p.uid, "me") or {}
    if settings().ai_ready and not p.demo and profile.get("consent", {}).get("ai_photo_processing"):
        quota(p.uid, "analysis", 20)
        return jobs.create(p.uid, "wardrobe", {"photo_ids": [photo_id]}, photo_id)
    return None


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
    store().put("photos", p.uid, key, row)
    auto_analyze(p, key)
    return row


@app.delete("/api/photos/{key}")
def delete_photo(key: str, p: Principal = Depends(principal)):
    row = store().get("photos", p.uid, key)
    kind = "photos"
    if not row:
        row = require_record("references", p.uid, key)
        kind = "references"
        if row.get("source_photo_id") and store().get("photos", p.uid, row["source_photo_id"]):
            return delete_photo(row["source_photo_id"], p)
    aliases = {key, "photo:" + key}
    for ref in store().list("references", p.uid):
        if ref.get("source_photo_id") == key:
            aliases.add(ref["id"])
            store().delete("references", p.uid, ref["id"])
    for job in store().list("jobs", p.uid):
        if (
            key in job["payload"].get("photo_ids", [])
            or job["payload"].get("reference_id") in aliases
            or job["payload"].get("source_photo_id") == key
        ):
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
    uploaded = store().get("media", p.catalog_owner, key) or {}
    own_upload = (p.admin or p.seller) and uploaded.get("uploader_id") == p.uid
    listed = any(v["image"] == "media:" + key for v in store().list("products", p.catalog_owner))
    if not own_upload and not listed:
        history = store().list("orders", p.uid)
        if p.admin:
            history += store().list("order_inbox", p.catalog_owner)
        elif p.seller:
            history += store().list("seller_orders", p.uid)
        if not any(line.get("image") == "media:" + key for order in history for line in order["items"]):
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
    already = [
        j for j in store().list("jobs", p.uid) if j["kind"] == "wardrobe" and j["status"] != "cancelled"
    ]
    covered = {key for j in already for key in j["payload"].get("photo_ids", [])}
    missing = [key for key in data.photo_ids if key not in covered]
    if not missing:
        return jobs.public(
            next(
                j
                for j in reversed(already)
                if any(key in data.photo_ids for key in j["payload"].get("photo_ids", []))
            )
        )
    return jobs.create(p.uid, "wardrobe", {"photo_ids": missing}, ":".join(sorted(missing)))


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
    if not p.demo and settings().seed_sample_catalog:
        inventory.seed_catalog(p.catalog_owner)
    return {
        "products": [
            {**product, "try_on_supported": try_on.supports(product)}
            for product in inventory.search(p.catalog_owner, q, budget, category)
        ]
    }


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
    payload = {**data.model_dump(), "catalog_owner": p.catalog_owner}
    if kind == "try_on" and not p.demo:
        try:
            payload, _, _ = try_on.prepare(p.uid, payload)
        except (try_on.CapabilityUnavailable, ValueError) as exc:
            raise HTTPException(409, str(exc))
    quota(p.uid, "generation", settings().max_daily_generations)
    if kind == "video":
        source = require_record("jobs", p.uid, data.source_job_id)
        if (
            source["kind"] != "try_on"
            or source["status"] != "succeeded"
            or not source.get("result", {}).get("accepted")
        ):
            raise HTTPException(409, "Accept a successful try-on preview first")
    return jobs.create(p.uid, kind, payload, data.request_key)


@app.post("/api/jobs/{key}/accept")
def accept(key: str, p: Principal = Depends(principal)):
    row = require_record("jobs", p.uid, key)
    if row["status"] != "succeeded" or row["kind"] not in ("try_on", "video"):
        raise HTTPException(409, "Only successful generated media can be accepted")
    row["result"]["accepted"] = True
    store().put("jobs", p.uid, key, row)
    return jobs.public(row)


@app.post("/api/jobs/{key}/regenerate")
def regenerate(key: str, p: Principal = Depends(principal)):
    row = require_record("jobs", p.uid, key)
    if row["kind"] != "try_on" or row["status"] != "succeeded":
        raise HTTPException(409, "Choose a completed style preview to regenerate")
    payload = {k: v for k, v in row["payload"].items() if k in GenerationRequest.model_fields}
    payload["request_key"] = secrets.token_hex(16)
    return generate("try_on", GenerationRequest.model_validate(payload), p)


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
    # Cancel before deleting files so the worker cannot publish an in-flight result.
    store().mutate(
        "jobs",
        p.uid,
        key,
        lambda current: {**current, "status": "cancelled", "stage": "Deleted", "result": None},
    )
    if row["kind"] == "garment_image":

        def clear(current):
            if not current or current.get("shop_image_job_id") != key:
                raise InterruptedError("Garment removed or changed")
            if current.get("generated_image"):
                removed.append(current["generated_image"][6:])
            return {
                **current,
                "generated_image": None,
                "generated_image_model": None,
                "generated_image_version": None,
            }

        removed = []
        try:
            store().mutate("wardrobe", p.uid, row["payload"]["item_id"], clear)
        except InterruptedError:
            pass
        for media_id in set(removed):
            media.delete(p.uid, media_id)
        invalidate_looks(p.uid)
    if row.get("result") and row["result"].get("media_id"):
        media.delete(p.uid, row["result"]["media_id"])
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


@app.get("/api/seller-access")
def seller_access(p: Principal = Depends(principal)):
    return {
        "approved": p.admin or p.seller,
        "request": store().get("seller_requests", p.catalog_owner, p.uid),
    }


@app.post("/api/seller-access/request")
def request_seller(p: Principal = Depends(principal)):
    if p.demo:
        raise HTTPException(403, "Sign in with Google or email to request seller access")
    if p.admin or p.seller:
        return {"status": "approved"}
    quota(p.uid, "seller-access", 5)

    def update(old):
        if old and old.get("status") == "pending":
            return old
        return {"id": p.uid, "email": p.email, "status": "pending", "created_at": now()}

    return store().mutate("seller_requests", p.catalog_owner, p.uid, update)


@app.get("/api/admin/seller-requests")
def seller_requests(p: Principal = Depends(admin)):
    return {"requests": store().list("seller_requests", p.catalog_owner)}


@app.post("/api/admin/seller-requests/{key}/{decision}")
def approve_seller(key: str, decision: str, p: Principal = Depends(admin)):
    if p.demo or decision not in ("approve", "revoke"):
        raise HTTPException(403, "Only the account owner can approve or revoke signed-in sellers")
    row = require_record("seller_requests", p.catalog_owner, key)

    def update(old):
        if old and old.get("role") == "owner":
            raise HTTPException(409, "Owner access is managed outside the seller workspace")
        return {
            "id": key,
            "role": "seller" if decision == "approve" else "revoked",
            "updated_at": now(),
            "approved_by": p.uid,
        }

    store().mutate("seller_access", "system", key, update)
    row.update(status="approved" if decision == "approve" else "revoked", updated_at=now())
    return store().put("seller_requests", p.catalog_owner, key, row)


@app.get("/api/admin/catalog")
def admin_catalog(p: Principal = Depends(merchant)):
    return {
        "products": [r for r in store().list("products", p.catalog_owner) if sellers.can_manage(p, r)],
        "stores": store().list("stores", p.catalog_owner),
        "editable_store_ids": [
            r["id"] for r in store().list("stores", p.catalog_owner) if sellers.can_manage(p, r)
        ],
    }


@app.post("/api/admin/import")
async def import_catalog(file: UploadFile = File(...), p: Principal = Depends(merchant)):
    quota(p.uid, "catalog-import", 20)
    records = inventory.parse_import(await file.read(2 * 1024 * 1024 + 1), file.filename or "catalogue.json")
    records = [sellers.prepare_product(p, product) for product in records]
    keys = []
    for product in records:
        old = store().get("products", p.catalog_owner, product.id)
        if old and inventory.product_hash(old) == inventory.product_hash(product.model_dump()):
            continue

        def publish(current, value=product):
            if current and not sellers.can_manage(p, current):
                raise HTTPException(403, "You can edit only your own products")
            return value.model_dump()

        store().mutate("products", p.catalog_owner, product.id, publish)
        keys.append(product.id)
    return jobs.create(
        p.uid, "index", {"catalog_owner": p.catalog_owner, "product_ids": keys}, secrets.token_hex(16)
    )


@app.post("/api/admin/products")
def add_product(product: Product, p: Principal = Depends(merchant)):
    quota(p.uid, "catalog-write", 100)
    product = sellers.prepare_product(p, product)

    def create(old):
        if old:
            raise HTTPException(409, "This product ID already exists. Edit the existing listing instead.")
        return product.model_dump()

    store().mutate("products", p.catalog_owner, product.id, create)
    return jobs.create(
        p.uid, "index", {"catalog_owner": p.catalog_owner, "product_ids": [product.id]}, secrets.token_hex(16)
    )


@app.put("/api/admin/products/{key}")
def edit_product(key: str, product: Product, p: Principal = Depends(merchant)):
    if key != product.id:
        raise HTTPException(422, "Product ID must match the listing being edited")
    quota(p.uid, "catalog-write", 100)
    product = sellers.prepare_product(p, product)

    def update(old):
        if old and not sellers.can_manage(p, old):
            raise HTTPException(403, "You can edit only your own products")
        return product.model_dump()

    store().mutate("products", p.catalog_owner, key, update)
    return jobs.create(
        p.uid, "index", {"catalog_owner": p.catalog_owner, "product_ids": [key]}, secrets.token_hex(16)
    )


@app.post("/api/admin/reindex")
def reindex(p: Principal = Depends(merchant)):
    quota(p.uid, "catalog-reindex", 10)
    return jobs.create(
        p.uid,
        "index",
        {
            "catalog_owner": p.catalog_owner,
            "product_ids": [
                r["id"] for r in store().list("products", p.catalog_owner) if sellers.can_manage(p, r)
            ],
        },
        secrets.token_hex(16),
    )


@app.put("/api/admin/stores/{key}")
def edit_store(key: str, data: Store, p: Principal = Depends(merchant)):
    if key != data.id:
        raise HTTPException(422, "Store ID must match")
    quota(p.uid, "store-write", 50)
    return sellers.manage_store(p, data)


@app.post("/api/admin/images")
async def upload_product_image(file: UploadFile = File(...), p: Principal = Depends(merchant)):
    quota(p.uid, "product-images", 50)
    raw, _ = media.normalize(await file.read(settings().max_upload_mb * 1024 * 1024 + 1))
    key = media.save(p.catalog_owner, raw)
    record = require_record("media", p.catalog_owner, key)
    record["uploader_id"] = p.uid
    store().put("media", p.catalog_owner, key, record)
    return {"image": "media:" + key}


@app.get("/api/admin/sample-import")
def sample_import(p: Principal = Depends(merchant)):
    return Response(
        (inventory.FIXTURES / "catalogue.json").read_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="flairify-sample-catalogue.json"'},
    )


@app.post("/api/orders/quote")
def order_quote(data: OrderQuoteRequest, p: Principal = Depends(principal)):
    return orders.quote(p, data)


@app.post("/api/orders")
def place_order(data: PlaceOrderRequest, p: Principal = Depends(principal)):
    return orders.place(p, data)


@app.get("/api/orders")
def order_history(p: Principal = Depends(principal)):
    return {
        "orders": sorted(
            [orders.public(r) for r in store().list("orders", p.uid)],
            key=lambda r: r["created_at"],
            reverse=True,
        )
    }


@app.get("/api/orders/{key}")
def order_detail(key: str, p: Principal = Depends(principal)):
    return orders.public(require_record("orders", p.uid, key))


@app.get("/api/admin/orders")
def seller_orders(p: Principal = Depends(merchant)):
    rows = store().list("order_inbox", p.catalog_owner) if p.admin else store().list("seller_orders", p.uid)
    return {"orders": sorted(rows, key=lambda r: r["created_at"], reverse=True)}


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
