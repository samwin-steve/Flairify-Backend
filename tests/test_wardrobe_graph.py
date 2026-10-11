from copy import deepcopy
from types import SimpleNamespace

from app.auth import Principal
from app.config import settings
from app.models import ChatRequest
from app.rag import wardrobe_graph
from app.services import jobs, recommendations
from app.store import store


def test_graph_snapshot_deduplicates_whole_outfits_and_rejects_stale_wardrobe(client, onboarded):
    data, _ = onboarded
    owner = data["user_id"]
    response = recommendations.recommend(Principal(owner, demo=True), ChatRequest(message="work"), {})
    original = response["outfits"][0]
    duplicate = deepcopy(original)
    duplicate["id"] = "repeated-look"
    store().put("outfits", owner, duplicate["id"], duplicate)
    version, rows = wardrobe_graph.snapshot(owner)
    assert len(rows) == len(response["outfits"])
    assert all(r["wardrobe_version"] == version and r["complete"] for r in rows)
    changed = original["owned"][0]
    changed["colour"] = "changed"
    store().put("wardrobe", owner, changed["id"], changed)
    assert wardrobe_graph.snapshot(owner)[1] == []


def test_graph_query_is_parameterized_scoped_and_bounded(client, monkeypatch):
    settings().enable_bigquery = True
    captured = {}

    class Client:
        def query(self, sql, job_config):
            captured.update(sql=sql, config=job_config)
            return SimpleNamespace(
                result=lambda timeout: [SimpleNamespace(product_id="jacket-a", distinct_outfits=2)],
                total_bytes_processed=240,
            )

    monkeypatch.setattr(wardrobe_graph, "client", lambda: Client())
    result = wardrobe_graph.coverage("customer-a", [], ["jacket-a"], "Work")
    assert result["counts"] == {"jacket-a": 2}
    assert "GRAPH_TABLE" in captured["sql"] and "Customer" in captured["sql"] and "Wears" in captured["sql"]
    assert "customer-a" not in captured["sql"]
    assert captured["config"].maximum_bytes_billed == 100_000_000
    params = {p.name: p.value for p in captured["config"].query_parameters if hasattr(p, "value")}
    assert params["owner"] == "customer-a" and params["occasion"] == "work"


def test_graph_unavailable_does_not_claim_evidence(client, monkeypatch):
    settings().enable_bigquery = True
    monkeypatch.setattr(wardrobe_graph, "client", lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))
    assert wardrobe_graph.coverage("a", [], ["p"], "Work")["status"] == "unavailable"


def test_index_job_checkpoints_every_five_records(client, session, monkeypatch):
    from app.services import indexing

    data, _ = session
    chunks = []

    def index(owner, ids):
        chunks.append(ids)
        return {
            "indexed": len(ids),
            "embeddings_generated": len(ids),
            "embeddings_reused": 0,
            "requested": len(ids),
        }

    monkeypatch.setattr(indexing, "index_products", index)
    record = jobs.create(
        data["user_id"],
        "index",
        {"catalog_owner": "retailer", "product_ids": [str(i) for i in range(12)]},
        "checkpoint-test",
    )
    saved = store().get("jobs", data["user_id"], record["id"])
    assert list(map(len, chunks)) == [5, 5, 2]
    assert saved["status"] == "succeeded" and saved["result"]["indexed"] == 12
