"""Provision the BigQuery property graph with operator ADC, then grant runtime dataset roles.
Run: python -m scripts.configure_graph (project and dataset come from .env).
The API/worker also need roles/bigquery.jobUser on the project (see bootstrap_gcp.sh).
"""

from pathlib import Path
from google.cloud import bigquery
from app.config import settings
from app.rag.wardrobe_graph import client, prefix

if __name__ == "__main__":
    cfg = settings()
    sql = (Path(__file__).resolve().parents[1] / "infra/wardrobe-graph.sql").read_text()
    sql = sql.replace("data-workshops.flairify", prefix()).replace(
        "location='us-central1'", f"location='{cfg.google_cloud_location}'"
    )
    provider = client()
    job = provider.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000))
    job.result()
    dataset = provider.get_dataset(prefix())
    entries = list(dataset.access_entries)
    for name, role in (("flairify-api", "READER"), ("flairify-worker", "WRITER")):
        entry = bigquery.AccessEntry(
            role, "userByEmail", f"{name}@{cfg.google_cloud_project}.iam.gserviceaccount.com"
        )
        if entry not in entries:
            entries.append(entry)
    dataset.access_entries = entries
    provider.update_dataset(dataset, ["access_entries"])
    print("Created WardrobeGraph and configured dataset-scoped runtime access")
