"""BigQuery Graph: evidence from distinct checked whole outfits, never live inventory."""

import hashlib
import json
import re
from datetime import UTC, datetime

from google.cloud import bigquery

from ..auth import quota
from ..config import settings
from ..store import store


def prefix():
    c = settings()
    if not re.fullmatch(r"[a-z][a-z0-9-]+", c.google_cloud_project) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", c.bigquery_dataset
    ):
        raise ValueError("Invalid BigQuery resource configuration")
    return f"{c.google_cloud_project}.{c.bigquery_dataset}"


def client():
    return bigquery.Client(project=settings().google_cloud_project, location=settings().google_cloud_location)


def version(owned):
    fields = ("id", "name", "category", "colour", "pattern", "details", "source_photo_id")
    evidence = sorted([{k: w.get(k) for k in fields} for w in owned], key=lambda x: x["id"])
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


def query_config(parameters, purpose):
    return bigquery.QueryJobConfig(
        query_parameters=parameters,
        maximum_bytes_billed=100_000_000,
        job_timeout_ms=60000 if purpose == "graph-sync" else 15000,
        labels={"app": "flairify", "purpose": purpose},
    )


def coverage(owner, owned, product_ids, occasion):
    if not settings().enable_bigquery:
        return {"status": "disabled", "counts": {}}
    parameters = [
        bigquery.ScalarQueryParameter("owner", "STRING", owner),
        bigquery.ScalarQueryParameter("revision", "STRING", version(owned)),
        bigquery.ScalarQueryParameter("occasion", "STRING", occasion.casefold()),
        bigquery.ArrayQueryParameter("product_ids", "STRING", product_ids[:70]),
    ]
    sql = f"""SELECT product_id, COUNT(DISTINCT outfit_id) AS distinct_outfits
      FROM GRAPH_TABLE (`{prefix()}.WardrobeGraph`
        MATCH (g:Garment)<-[:Wears]-(o:Outfit)-[:Adds]->(p:Product)
        WHERE g.owner=@owner AND o.owner=@owner AND p.owner=@owner
          AND o.wardrobe_version=@revision AND o.occasion=@occasion AND o.complete AND o.score>=0.7
        RETURN p.id AS product_id, o.id AS outfit_id
      ) WHERE product_id IN UNNEST(@product_ids)
      GROUP BY product_id ORDER BY distinct_outfits DESC, product_id LIMIT 70"""
    try:
        quota("live-ai", "graph-query", settings().max_daily_graph_queries)
        job = client().query(
            sql,
            job_config=query_config(parameters, "outfit-coverage"),
            job_retry=None,
            retry=None,
            timeout=10,
        )
        counts = {
            r.product_id: r.distinct_outfits for r in job.result(timeout=18, retry=None, job_retry=None)
        }
        return {
            "status": "ready",
            "source": "BigQuery Graph",
            "counts": counts,
            "bytes_processed": job.total_bytes_processed,
        }
    except Exception:  # noqa: BLE001 - optional remote provider boundary
        # Graph evidence improves ranking only when available. Semantic search and
        # full outfit validation remain usable; surface the absence honestly.
        return {"status": "unavailable", "source": "BigQuery Graph", "counts": {}}


def snapshot(owner):
    owned = [w for w in store().list("wardrobe", owner) if w["confirmed"]]
    revision = version(owned)
    owned_ids = {w["id"] for w in owned}
    outfits = sorted(store().list("outfits", owner), key=lambda o: o.get("created_at", ""), reverse=True)[:60]
    unique = {}
    for outfit in outfits:
        if not outfit.get("complete") or outfit.get("wardrobe_version") != revision:
            continue
        garments = sorted({w["id"] for w in outfit["owned"]})
        if not garments or not set(garments) <= owned_ids:
            continue
        products = sorted({p["id"] for p in outfit["products"]})
        occasion = outfit["occasion"].casefold()
        # Repeated recommendations of the same combination count once.
        key = hashlib.sha256(json.dumps([revision, occasion, garments, products]).encode()).hexdigest()
        assessment = outfit["assessment"]
        unique[key] = {
            "id": key,
            "wardrobe_version": revision,
            "occasion": occasion,
            "complete": True,
            "score": assessment["score"],
            "assessment_source": assessment["source"],
            "model_version": assessment["version"],
            "assessed_at": assessment.get("assessed_at") or datetime.now(UTC).isoformat(),
            "garments": garments,
            "products": products,
        }
    return revision, list(unique.values())


def sync(owner):
    """Idempotent owner snapshot in one MERGE. No names, photos or chat text enter BigQuery."""
    if owner.startswith("demo-"):
        return {"source": "demo", "outfits": 0}
    revision, rows = snapshot(owner)
    base = prefix()
    sql = f"""MERGE `{base}.graph_looks` t
    USING (
      SELECT @owner owner,JSON_VALUE(j,'$.id') id,JSON_VALUE(j,'$.wardrobe_version') wardrobe_version,
        JSON_VALUE(j,'$.occasion') occasion,TRUE complete,CAST(JSON_VALUE(j,'$.score') AS FLOAT64) score,
        JSON_VALUE(j,'$.assessment_source') assessment_source,JSON_VALUE(j,'$.model_version') model_version,
        TIMESTAMP(JSON_VALUE(j,'$.assessed_at')) assessed_at,
        JSON_VALUE_ARRAY(j,'$.garments') garment_ids,JSON_VALUE_ARRAY(j,'$.products') product_ids
      FROM UNNEST(JSON_QUERY_ARRAY(@rows)) j
    ) s ON t.owner=@owner AND t.owner=s.owner AND t.id=s.id
    WHEN MATCHED THEN UPDATE SET wardrobe_version=s.wardrobe_version,occasion=s.occasion,
      complete=s.complete,score=s.score,assessment_source=s.assessment_source,model_version=s.model_version,
      assessed_at=s.assessed_at,garment_ids=s.garment_ids,product_ids=s.product_ids
    WHEN NOT MATCHED THEN INSERT ROW
    WHEN NOT MATCHED BY SOURCE AND t.owner=@owner THEN DELETE
    """
    if rows:  # Required deletion must not be blocked by the recommendation quota.
        quota("live-ai", "graph-query", settings().max_daily_graph_queries)
    params = [
        bigquery.ScalarQueryParameter("owner", "STRING", owner),
        bigquery.ScalarQueryParameter("rows", "STRING", json.dumps(rows)),
    ]
    job = client().query(
        sql, job_config=query_config(params, "graph-sync"), job_retry=None, retry=None, timeout=10
    )
    job.result(timeout=65, retry=None, job_retry=None)
    store().put(
        "graph_status",
        owner,
        "current",
        {"revision": revision, "outfits": len(rows), "synced_at": datetime.now(UTC).isoformat()},
    )
    return {"outfits": len(rows), "source": "BigQuery Graph", "bytes_processed": job.total_bytes_processed}


def schedule(owner):
    if not settings().enable_bigquery or owner.startswith("demo-"):
        return
    if not store().get("graph_status", owner, "current") and not store().list("outfits", owner):
        return
    from ..services import jobs

    # A job reads current records at execution, never an old garment snapshot.
    jobs.create(owner, "graph_sync", {}, "graph-" + owner + "-" + datetime.now(UTC).isoformat())
