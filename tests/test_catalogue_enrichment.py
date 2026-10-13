import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.catalogue import context, enrichment
from app.catalogue.schema import Analysis, Enrichment, ProviderAnalysis, Tag
from app.catalogue.taxonomy import VOCAB
from app.config import settings
from app.models import Product, now
from app.rag import embeddings, repository
from app.services import indexing, inventory, jobs, sellers
from app.store import store


def listing():
    p = copy.deepcopy(next(iter(inventory.fixture_products().values())))
    p.update(
        name="Ivory office shirt",
        category="top",
        description="Cotton shirt with long sleeves.",
        attributes={"colour": "Ivory", "department": "women", "fabric": "Cotton"},
        image="",
    )
    return p


def tag(field, value, source="styling_inference", **kw):
    return Tag(
        field=field,
        value=value,
        source=source,
        confidence=0.9,
        evidence="Simple cut and restrained styling",
        **kw,
    )


def analysis(tags=None, **kw):
    return Analysis(
        tags=tags or [tag("occasion", "office"), tag("outfit_template", "office_ready")],
        image_quality="adequate",
        image_matches_product=True,
        **kw,
    )


def metadata(p, tags=None):
    return Enrichment(
        status="complete",
        schema_version="1",
        taxonomy_version="1",
        prompt_version="1",
        model=settings().gemini_model,
        input_hash=enrichment.fingerprint(p),
        input_mode="text_only",
        assessed_at=now(),
        tags=tags or analysis().tags,
    ).model_dump()


def test_confidence_and_taxonomy_validation():
    with pytest.raises(ValidationError):
        Tag(field="fabric", value="cotton", confidence=float("nan"), source="visual", evidence="texture")
    with pytest.raises(ValidationError):
        Tag(field="random_field", value="cotton", confidence=0.9, source="visual", evidence="texture")
    p = listing()
    tags, issues, unknown = enrichment.validate(analysis([tag("occasion", "any_event")]), p, True)
    assert "occasion:unknown_taxonomy_value" in issues
    assert "occasion" in unknown
    assert [t.value for t in tags] == ["top"]


def test_performance_and_fabric_need_explicit_seller_evidence():
    p = listing()
    values = [
        tag("fabric", "cotton", "visual"),
        tag("stretch", "stretch"),
        tag("breathability", "breathable"),
    ]
    values.append(
        Tag(
            field="fabric",
            value="cotton",
            source="seller",
            source_field="attributes.fabric",
            evidence="Cotton",
            confidence=1,
        )
    )
    values.append(
        Tag(
            field="weight",
            value="lightweight",
            source="seller",
            source_field="description",
            evidence="Cotton shirt",
            confidence=1,
        )
    )
    tags, issues, unknown = enrichment.validate(analysis(values), p, True)
    assert [(t.field, t.value) for t in tags] == [("category", "top"), ("fabric", "cotton")]
    assert {"weight", "stretch", "breathability"} <= set(unknown)
    assert len(issues) == 4


@pytest.mark.parametrize(
    "description", ["Not cotton", "Cotton-like texture", "Feels like cotton", "Faux leather"]
)
def test_false_or_negative_material_claim_cannot_become_verified(description):
    p = listing()
    p["description"] = description
    t = Tag(
        field="fabric",
        value="leather" if "leather" in description else "cotton",
        source="seller",
        source_field="description",
        evidence=description,
        confidence=1,
    )
    tags, _, _ = enrichment.validate(analysis([t]), p, True)
    assert all(t.field != "fabric" for t in tags)


def test_no_image_or_mismatched_image_cannot_supply_visual_facts():
    p = listing()
    visual = tag("pattern", "striped", "visual")
    result = analysis([visual, tag("occasion", "office")])
    tags, _, _ = enrichment.validate(result, p, False)
    assert all(t.field != "pattern" for t in tags)
    result.image_matches_product = False
    tags, issues, _ = enrichment.validate(result, p, True)
    assert [t.field for t in tags] == ["category"]
    assert "image_product_mismatch" in issues


def test_conflicting_values_and_generic_tag_stuffing_are_bounded():
    p = listing()
    tags, issues, _ = enrichment.validate(
        analysis(
            [tag("occasion", v) for v in sorted(VOCAB["occasion"])]
            + [tag("fit", "slim", "visual"), tag("fit", "oversized", "visual")]
        ),
        p,
        True,
    )
    assert len([t for t in tags if t.field == "occasion"]) == 3
    assert len([t for t in tags if t.field == "fit"]) == 1
    assert all(t.confidence <= 0.85 for t in tags if t.source == "styling_inference")
    assert "occasion:excess_or_conflicting_tags" in issues


def test_enrichment_is_incremental_and_never_changes_retailer_facts(client, monkeypatch):
    p = listing()
    original = copy.deepcopy(p)
    store().put("products", "retailer", p["id"], p)
    monkeypatch.setattr(enrichment, "enabled", lambda _: True)
    calls = []
    monkeypatch.setattr(enrichment, "analyze", lambda *a: (calls.append(a) or analysis(), {}))
    first, created = enrichment.ensure("retailer", p)
    assert created and len(calls) == 1
    assert {k: v for k, v in first.items() if k != "enrichment"} == {
        k: v for k, v in original.items() if k != "enrichment"
    }
    assert set(first["enrichment"]["unknown_fields"]) >= {"fabric", "stretch", "breathability"}
    assert enrichment.ensure("retailer", first)[1] is False
    first["price"] += 100
    first["variants"][0]["stock"][0]["quantity"] = 0
    store().put("products", "retailer", p["id"], first)
    assert enrichment.ensure("retailer", first)[1] is False
    first["description"] += " Embroidered collar."
    store().put("products", "retailer", p["id"], first)
    assert enrichment.ensure("retailer", first)[1] is True
    assert len(calls) == 2
    monkeypatch.setattr(enrichment, "SCHEMA_VERSION", "2")
    latest = store().get("products", "retailer", p["id"])
    assert not enrichment.current(latest)
    assert enrichment.ensure("retailer", latest)[0]["enrichment"]["schema_version"] == "2"


def test_duplicate_analysis_reuses_cache_and_seller_edit_during_analysis_is_not_overwritten(
    client, monkeypatch
):
    p = listing()
    store().put("products", "retailer", p["id"], p)
    monkeypatch.setattr(enrichment, "enabled", lambda _: True)

    def provider(*args):
        latest = {**p, "name": "New seller title"}
        store().put("products", "retailer", p["id"], latest)
        return analysis(), {}

    monkeypatch.setattr(enrichment, "analyze", provider)
    with pytest.raises(enrichment.RetryableEnrichmentError):
        enrichment.ensure("retailer", p)
    assert store().get("products", "retailer", p["id"])["name"] == "New seller title"
    store().put("products", "retailer", p["id"], p)
    monkeypatch.setattr(enrichment, "analyze", lambda *a: pytest.fail("cached analysis should be reused"))
    assert enrichment.ensure("retailer", p)[0]["enrichment"]["status"] == "complete"


def test_provider_failure_is_recorded_not_fabricated(client, monkeypatch):
    p = listing()
    store().put("products", "retailer", p["id"], p)
    monkeypatch.setattr(enrichment, "enabled", lambda _: True)
    monkeypatch.setattr(
        enrichment, "analyze", lambda *a: (_ for _ in ()).throw(RuntimeError("private provider payload"))
    )
    with pytest.raises(enrichment.RetryableEnrichmentError):
        enrichment.ensure("retailer", p)
    failed = store().get("products", "retailer", p["id"])
    assert failed["enrichment"]["status"] == "failed" and failed["enrichment"]["tags"] == []
    assert "private" not in failed["enrichment"]["error"]
    assert not enrichment.current(failed)


def test_metadata_is_searchable_but_pairing_items_are_not_the_product(client):
    p = listing()
    p["attributes"]["source_dataset"] = "https://irrelevant-source.example.com"
    p["enrichment"] = metadata(
        p, [tag("occasion", "office"), tag("matching_garment", "jeans"), tag("footwear", "heels")]
    )
    text = embeddings.document(p)
    assert "office" in text and "heels" in text and "irrelevant-source" not in text
    from app.services.styling import suitable

    assert suitable(p, {"avoid_types": ["heels", "jeans"]})
    changed = copy.deepcopy(p)
    changed["description"] = "Changed listing"
    assert enrichment.search_metadata(changed) == {}


def test_contextual_tags_improve_relevant_ranking_without_tag_count_advantage(client):
    office, casual = listing(), listing()
    office["enrichment"] = metadata(
        office, [tag("occasion", "office"), tag("outfit_template", "office_ready")]
    )
    casual["enrichment"] = metadata(
        casual, [tag("occasion", "casual_outing"), tag("outfit_template", "weekend_casual")]
    )
    intent = {"query": "something for office meetings", "occasion": "office", "dress_code": "office"}
    assert context.relevance(office, intent) > context.relevance(casual, intent) + 3
    assert context.relevance(listing(), intent) == 0
    assert "office ready" in context.query_context(intent)


def test_enriched_text_changes_vector_and_stock_only_reuses_it(client, monkeypatch):
    p = listing()
    store().put("products", "retailer", p["id"], p)
    monkeypatch.setattr(embeddings, "enabled", lambda _: True)
    monkeypatch.setattr(embeddings, "embed", lambda _: [1.0, 0.0])
    assert indexing.index_products("retailer", [p["id"]])["embeddings_generated"] == 1
    latest = store().get("products", "retailer", p["id"])
    latest["enrichment"] = metadata(latest)
    store().put("products", "retailer", p["id"], latest)
    assert indexing.index_products("retailer", [p["id"]])["embeddings_generated"] == 1
    latest = store().get("products", "retailer", p["id"])
    latest["price"] += 1
    store().put("products", "retailer", p["id"], latest)
    assert indexing.index_products("retailer", [p["id"]])["embeddings_reused"] == 1
    assert repository.read("retailer", p["id"])["price"] == latest["price"]


def test_job_retries_bad_product_then_continues_and_reports_partial_failure(client, monkeypatch):
    calls = []

    def fake(owner, ids):
        calls.extend(ids)
        return {
            "indexed": int("good" in ids),
            "enriched": 0,
            "enrichment_reused": 0,
            "embeddings_generated": 0,
            "embeddings_reused": 0,
            "errors": [{"product_id": "bad", "error": "Failed"}] if "bad" in ids else [],
            "method": "test",
        }

    monkeypatch.setattr(indexing, "index_products", fake)
    job = jobs.create(
        "operator", "index", {"catalog_owner": "retailer", "product_ids": ["bad", "good"]}, "unique"
    )
    result = store().get("jobs", "operator", job["id"])
    assert calls == ["bad", "good", "bad", "bad"]
    assert result["status"] == "failed" and result["result"]["processed"] == 2
    assert result["result"]["indexed"] == 1 and len(result["result"]["errors"]) == 1


def test_seller_cannot_inject_generated_metadata(client):
    p = listing()
    p.update(image="/images/blazer.jpg", enrichment=metadata(p))
    seller = SimpleNamespace(uid="seller", catalog_owner="retailer", demo=False, admin=False)
    for stock in p["variants"][0]["stock"]:
        store().put("stores", "retailer", stock["store_id"], {"id": stock["store_id"], "seller_id": "seller"})
    prepared = sellers.prepare_product(seller, Product.model_validate(p))
    assert prepared.enrichment is None


def test_provider_uses_actual_photo_and_structured_google_schema(client, monkeypatch):
    provider = MagicMock()
    provider.__enter__.return_value = provider
    provider.models.generate_content.return_value = SimpleNamespace(
        text=analysis().model_dump_json(), usage_metadata=None
    )
    monkeypatch.setattr(enrichment.ai, "client", lambda **kw: provider)
    result, _ = enrichment.analyze(listing(), b"photo-bytes")
    sent = provider.models.generate_content.call_args.kwargs
    assert sent["contents"][0].inline_data.data == b"photo-bytes"
    assert sent["config"].response_schema is ProviderAnalysis
    assert result.tags
