import json

from ..config import settings
from ..store import store
from . import ai
from .inventory import product_hash


def index_products(owner, ids):
    changed = 0
    for key in ids:
        product = store().get("products", owner, key)
        if not product:
            continue
        digest = product_hash(product)
        if product.get("content_hash") == digest and product.get("indexed"):
            continue
        description = " ".join(
            [product["name"], product["description"], product["category"], json.dumps(product["attributes"])]
        )
        embedding = None
        if settings().enable_paid_ai and settings().embedding_model:
            embedding = ai.embed(description)
        store().put(
            "search",
            owner,
            key,
            {"id": key, "description": description, "embedding": embedding, "hash": digest},
        )
        if settings().enable_bigquery:
            from google.cloud import bigquery

            cfg = settings()
            client = bigquery.Client(project=cfg.google_cloud_project)
            sql = f"""MERGE `{cfg.google_cloud_project}.{cfg.bigquery_dataset}.products` t
            USING (SELECT @owner owner,@id id,@description description,@embedding embedding,@hash content_hash) s
            ON t.owner=s.owner AND t.id=s.id WHEN MATCHED THEN UPDATE SET description=s.description,embedding=s.embedding,content_hash=s.content_hash
            WHEN NOT MATCHED THEN INSERT(owner,id,description,embedding,content_hash) VALUES(s.owner,s.id,s.description,s.embedding,s.content_hash)"""
            params = [
                bigquery.ScalarQueryParameter("owner", "STRING", owner),
                bigquery.ScalarQueryParameter("id", "STRING", key),
                bigquery.ScalarQueryParameter("description", "STRING", description),
                bigquery.ArrayQueryParameter("embedding", "FLOAT64", embedding or []),
                bigquery.ScalarQueryParameter("hash", "STRING", digest),
            ]
            client.query(
                sql,
                job_config=bigquery.QueryJobConfig(query_parameters=params, maximum_bytes_billed=100_000_000),
            ).result()

        def publish(current):
            if current and product_hash(current) == digest:
                return {**current, "indexed": True, "content_hash": digest}
            return current

        current = store().mutate("products", owner, key, publish)
        if current and current.get("content_hash") == digest:
            changed += 1
    return {
        "indexed": changed,
        "requested": len(ids),
        "method": "vertex-embedding"
        if settings().embedding_model and settings().enable_paid_ai
        else "attribute-text",
        "visual_attributes": "Not extracted automatically in this version",
    }
