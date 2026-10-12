"""Completed previews resolve only the authenticated customer's purchasable products."""

import pytest

from app.models import GenerationJob
from app.store import store


def preview(client, onboarded):
    identity, h = onboarded
    look = client.post(
        "/api/chat", headers=h, json={"message": "Mumbai work trip under ₹5,000", "include_wardrobe": False}
    ).json()["outfits"][0]
    job = GenerationJob(
        kind="try_on",
        status="succeeded",
        payload={"outfit_id": look["id"]},
        result={
            "media_id": "test-generated-fixture",
            "pieces": [{"kind": "product", "id": look["products"][0]["id"]}],
        },
    ).model_dump(mode="json")
    store().put("jobs", identity["user_id"], job["id"], job)
    data = {
        "source": "fitting_room",
        "preview_job_id": job["id"],
        "items": [
            {
                "product_id": p["id"],
                "variant_id": p["availability"]["variant_id"],
                "store_id": p["availability"]["store_id"],
                "quantity": 1,
            }
            for p in look["products"]
        ],
    }
    return identity["user_id"], h, job, look, data


def test_preview_buys_all_recommended_new_items_and_saves_order(client, onboarded):
    _, h, job, look, data = preview(client, onboarded)
    shopping = client.get(f"/api/jobs/{job['id']}/shopping", headers=h).json()
    assert {p["id"] for p in shopping["products"]} == {p["id"] for p in look["products"]}
    assert len(shopping["products"]) > len(job["result"]["pieces"])
    quote = client.post("/api/orders/quote", headers=h, json=data).json()
    body = {
        **data,
        "request_key": "preview-order-test",
        "expected_total": quote["total"],
        "acknowledge_mock": True,
    }
    order = client.post("/api/orders", headers=h, json=body)
    assert order.status_code == 200, order.text
    assert order.json()["source"] == "fitting_room" and order.json()["preview_job_id"] == job["id"]
    assert order.json()["total"] == look["total"]
    assert order.json()["payment_status"] == "not_required"
    assert client.post("/api/orders", headers=h, json=body).json()["id"] == order.json()["id"]
    assert len(client.get("/api/orders", headers=h).json()["orders"]) == 1
    other = client.post("/api/auth/demo").json()
    foreign = {"Authorization": "Bearer " + other["token"]}
    assert client.get(f"/api/jobs/{job['id']}/shopping", headers=foreign).status_code == 404
    assert client.post("/api/orders/quote", headers=foreign, json=data).status_code == 404


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_unfinished_preview_cannot_be_shopped(client, onboarded, status):
    uid, h, job, _, data = preview(client, onboarded)
    job["status"] = status
    store().put("jobs", uid, job["id"], job)
    assert client.get(f"/api/jobs/{job['id']}/shopping", headers=h).status_code == 409
    assert client.post("/api/orders/quote", headers=h, json=data).status_code == 409


def test_preview_reports_unavailable_and_rechecks_stock_and_price(client, onboarded):
    uid, h, job, look, data = preview(client, onboarded)
    p = look["products"][0]
    previous = client.post("/api/orders/quote", headers=h, json=data).json()["total"]
    p["price"] += 100
    store().put("products", uid, p["id"], p)
    body = {
        **data,
        "request_key": "changed-preview-total",
        "expected_total": previous,
        "acknowledge_mock": True,
    }
    assert client.post("/api/orders", headers=h, json=body).status_code == 409
    for variant in p["variants"]:
        for stock in variant["stock"]:
            stock["quantity"] = 0
    store().put("products", uid, p["id"], p)
    shopping = client.get(f"/api/jobs/{job['id']}/shopping", headers=h).json()
    assert shopping["unavailable"] == [{"id": p["id"], "name": p["name"]}]
    assert p["id"] not in [p["id"] for p in shopping["products"]]
    assert client.post("/api/orders/quote", headers=h, json=data).status_code == 409
    store().delete("outfits", uid, look["id"])
    assert client.get(f"/api/jobs/{job['id']}/shopping", headers=h).status_code == 409


def test_standalone_and_legacy_previews_exclude_owned_pieces(client, onboarded):
    uid, h, job, look, data = preview(client, onboarded)
    job["payload"] = {}
    job["result"]["pieces"].append({"kind": "wardrobe", "id": "owned-shirt"})
    store().put("jobs", uid, job["id"], job)
    shopping = client.get(f"/api/jobs/{job['id']}/shopping", headers=h).json()
    assert [p["id"] for p in shopping["products"]] == [look["products"][0]["id"]]
    # Other catalogue products cannot be attached by changing the client cart.
    assert client.post("/api/orders/quote", headers=h, json=data).status_code == 422
    job["result"].pop("pieces")
    job["result"]["product_id"] = look["products"][0]["id"]
    store().put("jobs", uid, job["id"], job)
    assert len(client.get(f"/api/jobs/{job['id']}/shopping", headers=h).json()["products"]) == 1
    assert (
        client.post("/api/orders/quote", headers=h, json={**data, "source": "inventory"}).status_code == 422
    )
