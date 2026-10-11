"""Bounded relationship graph. Firestore is the current graph; BigQuery is an optional projection."""

import hashlib
from ..models import now
from ..store import store
from ..config import settings


def edge(owner, source, target, kind, **attributes):
    key = hashlib.sha256(f"{source}:{target}:{kind}".encode()).hexdigest()[:32]
    row = {
        "id": key,
        "source_id": source,
        "target_id": target,
        "relationship": kind,
        "assessed_at": now(),
        **attributes,
    }
    store().put("relationships", owner, key, row)
    return row


def node(owner, key, kind, label):
    store().put("nodes", owner, key, {"id": key, "kind": kind, "label": label})


def record_outfit(owner, outfit):
    node(owner, owner, "User", "Customer")
    node(owner, outfit["id"], "Outfit", outfit["title"])
    occasion_id = "occasion:" + outfit["occasion"]
    node(owner, occasion_id, "Occasion", outfit["occasion"])
    edge(owner, outfit["id"], occasion_id, "SUITS_OCCASION")
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
        node(owner, garment["id"], "WardrobeGarment", garment["name"])
        edge(owner, owner, garment["id"], "OWNS")
        edge(owner, outfit["id"], garment["id"], "OUTFIT_CONTAINS_OWNED", **common)
        if garment.get("source_photo_id"):
            node(owner, garment["source_photo_id"], "Photo", "Selected source photo")
            edge(owner, garment["id"], garment["source_photo_id"], "APPEARED_IN")
    for product in outfit["products"]:
        node(owner, product["id"], "RetailProduct", product["name"])
        edge(owner, outfit["id"], product["id"], "OUTFIT_CONTAINS_PRODUCT", **common)
        st = product["store"]
        node(owner, st["id"], "Store", st["name"])
        edge(
            owner,
            product["availability"]["variant_id"],
            st["id"],
            "AVAILABLE_AT",
            quantity=product["availability"]["quantity"],
        )
        for garment in outfit["owned"]:
            edge(owner, garment["id"], product["id"], "CANDIDATE_COMPLEMENT", **common)
    profile = store().get("profiles", owner, "me") or {}
    if profile.get("consent", {}).get("remember_preferences"):
        for style in profile.get("styles", []):
            node(owner, "style:" + style, "Style", style)
            edge(owner, owner, "style:" + style, "PREFERS_STYLE")


def clear(owner):
    for kind in ("nodes", "relationships"):
        for row in store().list(kind, owner):
            store().delete(kind, owner, row["id"])
    if settings().enable_bigquery:
        from google.cloud import bigquery

        c = settings()
        client = bigquery.Client(project=c.google_cloud_project)
        params = [bigquery.ScalarQueryParameter("owner", "STRING", owner)]
        for table in ("nodes", "relationships"):
            client.query(
                f"DELETE FROM `{c.google_cloud_project}.{c.bigquery_dataset}.{table}` WHERE owner=@owner",
                job_config=bigquery.QueryJobConfig(query_parameters=params, maximum_bytes_billed=100_000_000),
            ).result()
