"""Bounded relationship graph. Firestore is the current graph; BigQuery is an optional projection."""

import hashlib
from functools import partial
from ..models import now
from ..store import store
from ..config import settings


def edge(owner, source, target, kind, buffer=None, **attributes):
    key = hashlib.sha256(f"{source}:{target}:{kind}".encode()).hexdigest()[:32]
    row = {
        "id": key,
        "source_id": source,
        "target_id": target,
        "relationship": kind,
        "assessed_at": now(),
        **attributes,
    }
    if buffer is not None:
        buffer.append(("relationships", owner, key, row))
    else:
        store().put("relationships", owner, key, row)
    return row


def node(owner, key, kind, label, buffer=None):
    row = {"id": key, "kind": kind, "label": label}
    if buffer is not None:
        buffer.append(("nodes", owner, key, row))
    else:
        store().put("nodes", owner, key, row)


def record_outfit(owner, outfit):
    records = []
    write_node = partial(node, buffer=records)
    write_edge = partial(edge, buffer=records)
    write_node(owner, owner, "User", "Customer")
    write_node(owner, outfit["id"], "Outfit", outfit["title"])
    occasion_id = "occasion:" + outfit["occasion"]
    write_node(owner, occasion_id, "Occasion", outfit["occasion"])
    write_edge(owner, outfit["id"], occasion_id, "SUITS_OCCASION")
    a = outfit["assessment"]
    common = {
        "outfit_id": outfit["id"],
        "score": a["score"],
        "reason": a["reason"],
        "assessment_source": a["source"],
        "model_version": a["version"],
        "occasion": outfit["occasion"],
        "feedback": a.get("feedback"),
    }
    for garment in outfit["owned"]:
        write_node(owner, garment["id"], "WardrobeGarment", garment["name"])
        write_edge(owner, owner, garment["id"], "OWNS")
        write_edge(owner, outfit["id"], garment["id"], "OUTFIT_CONTAINS_OWNED", **common)
        if garment.get("source_photo_id"):
            write_node(owner, garment["source_photo_id"], "Photo", "Selected source photo")
            write_edge(owner, garment["id"], garment["source_photo_id"], "APPEARED_IN")
    for product in outfit["products"]:
        write_node(owner, product["id"], "RetailProduct", product["name"])
        write_edge(owner, outfit["id"], product["id"], "OUTFIT_CONTAINS_PRODUCT", **common)
        st = product["store"]
        write_node(owner, st["id"], "Store", st["name"])
        write_edge(
            owner,
            product["availability"]["variant_id"],
            st["id"],
            "AVAILABLE_AT",
            quantity=product["availability"]["quantity"],
        )
        for garment in outfit["owned"]:
            write_edge(owner, garment["id"], product["id"], "CANDIDATE_COMPLEMENT", **common)
    profile = store().get("profiles", owner, "me") or {}
    if profile.get("consent", {}).get("remember_preferences"):
        for style in profile.get("styles", []):
            write_node(owner, "style:" + style, "Style", style)
            write_edge(owner, owner, "style:" + style, "PREFERS_STYLE")

    store().put_many(records)


def clear(owner):
    for kind in ("nodes", "relationships"):
        for row in store().list(kind, owner):
            store().delete(kind, owner, row["id"])
    if settings().enable_bigquery:
        from ..rag.wardrobe_graph import schedule

        # A durable job rebuilds from currently retained outfits after deletion.
        # Version filtering immediately excludes stale graph evidence from retrieval.
        schedule(owner)
