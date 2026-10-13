"""Resolve spoken garment choices only against this conversation's retrieved looks."""

import hashlib
import json
import re

from fastapi import HTTPException

from ..models import GenerationRequest
from ..store import store
from . import generations, inventory, try_on


def normalize(name):
    return " ".join(re.findall(r"\w+", name.casefold()))


def candidates(conversation, pending=()):
    rows = {(p["kind"], p["id"]): p for p in conversation.voice_selection}
    for look in [o for m in conversation.messages for o in m.outfits] + list(pending):
        for kind, pieces in [("product", look["products"]), ("wardrobe", look["owned"])]:
            for p in pieces:
                rows[(kind, p["id"])] = {**p, "kind": kind}
    return list(rows.values())


def choose(principal, conversation, profile, names, pending=(), replace=False, remove=False, store_id=None):
    if (
        not isinstance(names, list)
        or len(names) > 20
        or any(not isinstance(n, str) or not n.strip() or len(n) > 250 for n in names)
    ):
        raise HTTPException(422, "Choose up to 20 named pieces from this chat.")
    rows = candidates(conversation, pending)
    resolved = []
    # Resolve the complete request before changing anything; never silently drop an unknown piece.
    for name in names:
        key = normalize(name)
        matches = [p for p in rows if key == normalize(p["name"]) or name == p["kind"] + ":" + p["id"]]
        if not matches:
            matches = [p for p in rows if set(key.split()) <= set(normalize(p["name"]).split())]
        if len(matches) != 1:
            choices = ", ".join(p["name"] for p in matches[:4])
            raise HTTPException(
                422,
                f"Which piece did you mean by {name}? "
                + (
                    "Choose one of: " + choices
                    if choices
                    else "Choose a garment from the recommendations in this chat."
                ),
            )
        resolved.append(matches[0])
    chosen = [] if replace else list(conversation.voice_selection)
    adjustments = []
    for row in resolved:
        kind, key = row["kind"], row["id"]
        if remove:
            chosen = [p for p in chosen if (p["kind"], p["id"]) != (kind, key)]
            continue
        current = store().get(
            "products" if kind == "product" else "wardrobe",
            principal.catalog_owner if kind == "product" else principal.uid,
            key,
        )
        if not current:
            raise HTTPException(409, "A chosen piece is no longer available. Pick another recommendation.")
        variant = None
        if kind == "product":
            size = profile.get("shoe_size" if current["category"] == "shoes" else "clothing_size")
            stock = inventory.available(current, size, store_id or profile.get("preferred_store_id"))
            if not stock or not try_on.supports(current):
                raise HTTPException(
                    409,
                    f"{current['name']} is unavailable in your saved size/store or lacks a supported photo. Choose another piece.",
                )
            variant = stock[0]["variant_id"]
        elif not current.get("confirmed") or not current["image"].startswith("media:"):
            raise HTTPException(409, "Confirm the owned garment and add its photo in My Wardrobe first.")
        if current["category"] not in try_on.EDITABLE:
            raise HTTPException(409, "This garment category cannot be previewed yet.")
        piece = {
            "kind": kind,
            "id": key,
            "variant_id": variant,
            "name": current["name"],
            "category": current["category"],
            "available": True,
        }
        for previous in chosen:
            if try_on.conflicts(previous["category"], piece["category"]) and (
                previous["kind"],
                previous["id"],
            ) != (kind, key):
                adjustments.append(
                    f"{piece['name']} replaces {previous['name']} so there is one piece per clothing slot."
                )
        chosen = [p for p in chosen if not try_on.conflicts(p["category"], piece["category"])] + [piece]
    conversation.voice_selection = chosen
    conversation.voice_preview_job_id = None
    persist(principal, conversation)
    return {"pieces": chosen, "adjustments": adjustments, "generated": False}


def persist(principal, conversation):
    store().put("conversations", principal.uid, conversation.id, conversation.model_dump(mode="json"))


def preview(principal, conversation, profile, store_id=None):
    if not conversation.voice_selection:
        raise HTTPException(422, "Choose at least one recommended garment to try on first.")
    # Stable across model retries, disconnects and repeated 'see it on me'. Explicit
    # regeneration is available in Fitting Room; a reconnect never starts another paid job.
    selected = [{k: p[k] for k in ("kind", "id", "variant_id")} for p in conversation.voice_selection]
    digest = hashlib.sha256(
        json.dumps(sorted(selected, key=lambda p: (p["kind"], p["id"])), sort_keys=True).encode()
    ).hexdigest()[:24]
    request_key = "voice-" + conversation.id + "-" + digest
    job_id = hashlib.sha256(f"try_on:{request_key}".encode()).hexdigest()[:32]
    existing = store().get("jobs", principal.uid, job_id)
    if existing:
        from .jobs import public

        job = public(existing)
    else:
        # Recheck current sizes, store stock and evidence immediately before enqueue.
        choose(
            principal,
            conversation,
            profile,
            [p["kind"] + ":" + p["id"] for p in selected],
            replace=True,
            store_id=store_id,
        )
        selected = [{k: p[k] for k in ("kind", "id", "variant_id")} for p in conversation.voice_selection]
        job = generations.submit(
            "try_on", GenerationRequest(selections=selected, request_key=request_key), principal
        )
    conversation.voice_preview_job_id = job["id"]
    persist(principal, conversation)
    return job
