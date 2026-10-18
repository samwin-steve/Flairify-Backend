from copy import deepcopy

from app.services import catalogue_browse, inventory
from app.store import store


def test_pagination_preserves_catalogue_without_duplicate_or_missing_products(client, session):
    _, headers = session
    expected = {p["id"] for p in client.get("/api/catalog", headers=headers).json()["products"]}
    ids = []
    cursor = None
    for _ in range(30):
        params = {"page_size": 24, "available_only": False}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/api/catalog", headers=headers, params=params)
        assert response.status_code == 200
        data = response.json()
        assert len(data["products"]) <= 24 and data["page_size"] == 24
        assert all("enrichment" not in p for p in data["products"])
        ids.extend(p["id"] for p in data["products"])
        cursor = data["next_cursor"]
        if not cursor:
            break
    assert len(ids) == len(set(ids))
    assert set(ids) == expected


def test_filters_cursor_validation_and_empty_catalogue(client, session):
    _, headers = session
    params = {"page_size": 12, "category": "shoes", "department": "men"}
    response = client.get("/api/catalog", headers=headers, params=params).json()
    assert response["products"]
    assert all(
        p["category"] == "shoes" and p["attributes"]["department"] in {"men", "unisex"}
        for p in response["products"]
    )
    assert client.get("/api/catalog?page_size=1000", headers=headers).status_code == 422
    assert client.get("/api/catalog?page_size=24&cursor=bad", headers=headers).status_code == 422
    assert client.get("/api/catalog?page_size=24&category=absent", headers=headers).json()["products"] == []


def test_checkout_reads_only_scoped_products_and_keeps_latest_stock(client, session):
    account, headers = session
    rows = client.get("/api/catalog", headers=headers).json()["products"]
    keys = [p["id"] for p in rows[:2]]
    selected = client.get("/api/catalog", headers=headers, params={"ids": ",".join(keys)}).json()["products"]
    assert {p["id"] for p in selected} == set(keys)
    product = store().get("products", account["user_id"], keys[0])
    product["price"] = 1234
    product["variants"][0]["stock"][0]["quantity"] = 0
    store().put("products", account["user_id"], keys[0], product)
    current = client.get("/api/catalog", headers=headers, params={"ids": keys[0]}).json()["products"][0]
    assert current["price"] == 1234 and current["variants"][0]["stock"][0]["quantity"] == 0
    assert client.get("/api/catalog?ids=../../private", headers=headers).status_code == 422
    assert (
        client.get(
            "/api/catalog", headers=headers, params={"ids": ",".join(str(i) for i in range(21))}
        ).status_code
        == 422
    )
    other = client.post("/api/auth/demo").json()["user_id"]
    private = product.copy()
    private["id"] = "other-only"
    store().put("products", other, private["id"], private)
    assert catalogue_browse.selected(account["user_id"], "other-only") == []


def test_availability_filter_and_projection_preserve_full_stored_data(client, session):
    account, _ = session
    owner = account["user_id"] + "-projection"
    product = next(iter(inventory.fixture_products().values())).copy()
    product.update(active=True, indexed=True)
    product["variants"] = [
        {"id": "zero", "size": "M", "colour": "Blue", "stock": [{"store_id": "bandra", "quantity": 0}]}
    ]
    product["enrichment"] = {"status": "complete", "tags": [{"field": "occasion", "value": "office"}]}
    store().put("products", owner, product["id"], product)
    assert catalogue_browse.page(owner, available_only=True)["products"] == []
    assert len(catalogue_browse.page(owner, available_only=False)["products"]) == 1
    assert store().get("products", owner, product["id"])["enrichment"] == product["enrichment"]
    assert (
        "enrichment"
        not in store().get_many("products", owner, [product["id"]], fields=catalogue_browse.FIELDS)[0]
    )


def test_literal_listing_search_does_not_fill_page_with_unrelated_candidates(client, session):
    account, headers = session
    product = deepcopy(next(iter(inventory.fixture_products().values())))
    product.update(
        id="unique-listing", name="Unique QA white shirt", category="top", active=True, indexed=True
    )
    store().put("products", account["user_id"], product["id"], product)
    result = client.get(
        "/api/catalog", headers=headers, params={"page_size": 24, "q": product["name"]}
    ).json()
    assert [row["id"] for row in result["products"]] == [product["id"]]
    assert result["next_cursor"] is None
    for variant in product["variants"]:
        for stock in variant["stock"]:
            stock["quantity"] = 0
    store().put("products", account["user_id"], product["id"], product)
    result = client.get(
        "/api/catalog", headers=headers, params={"page_size": 24, "q": product["name"]}
    ).json()
    assert result["products"] == []
