"""Google-only, cached image analysis with evidence checks and compare-before-publish."""

import hashlib
import io
import json
import re
import time

from google.genai import types
from PIL import Image

from ..auth import quota
from ..config import settings
from ..models import now
from ..prompts.catalogue import SYSTEM
from ..services import ai, media
from ..store import store
from .schema import Analysis, Enrichment, ProviderAnalysis, Tag
from .taxonomy import (
    FACT_ATTRIBUTES,
    INFERRED,
    PHYSICAL,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
    VOCAB,
)

MIN_CONFIDENCE = 0.65
ALIASES = {
    "t_shirt": ("t-shirt", "tshirt", "tee"),
    "v_neck": ("v-neck",),
    "three_quarter": ("3/4", "three-quarter"),
    "multicolour": (
        "multi",
        "multicolor",
    ),
    "grey": ("gray",),
    "ivory": ("off white", "off-white"),
    "orange": ("saffron",),
    "non_stretch": ("non-stretch", "no stretch"),
    "stretch": ("stretchy", "stretchable"),
    "lightweight": ("light weight", "light-weight"),
    "heavyweight": ("heavy weight",),
    "breathable": ("breathability",),
    "low_breathability": ("not breathable", "non-breathable"),
}


class RetryableEnrichmentError(Exception):
    pass


def enabled(owner):
    cfg = settings()
    return owner == "retailer" and cfg.ai_ready and cfg.enable_catalogue_enrichment


def seller_facts(product):
    description = product.get("description", "")
    # Keep the actual listing unchanged; remove known fixture provenance from search/AI input.
    description = re.sub(
        r"(?i)\b(?:sample catalogue|sample inventory|sample product|demo stock).*", "", description
    )
    description = re.sub(
        r"(?i)Archived dataset photograph.*|Demonstration price, sizes and stock.*|Illustrative licensed photograph.*",
        "",
        description,
    )
    description = description.replace("Synthetic catalogue item.", "").strip()
    return {
        **{k: product.get(k, "") for k in ("name", "category")},
        "brand": "" if product.get("brand") == "Sample catalogue" else product.get("brand", ""),
        "description": description,
        "attributes": {k: v for k, v in product.get("attributes", {}).items() if k in FACT_ATTRIBUTES},
        "variant_colours": sorted({v["colour"] for v in product.get("variants", [])}),
    }


def fingerprint(product):
    # Uploaded images are immutable IDs. Bundled image replacements must use a new path.
    payload = {
        "facts": seller_facts(product),
        "image": product.get("image", ""),
        "schema": SCHEMA_VERSION,
        "taxonomy": TAXONOMY_VERSION,
        "prompt": PROMPT_VERSION,
        "model": settings().gemini_model,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def current(product):
    record = product.get("enrichment") or {}
    return record.get("input_hash") == fingerprint(product) and record.get("status") in {
        "complete",
        "needs_review",
    }


def search_tags(product):
    if not current(product):
        return []
    return [t for t in product["enrichment"]["tags"] if t["confidence"] >= MIN_CONFIDENCE]


def search_metadata(product):
    groups = {}
    for tag in search_tags(product):
        groups.setdefault(tag["field"], []).append(tag["value"])
    return {field: sorted(set(values)) for field, values in sorted(groups.items())}


def photograph(owner, product):
    image = product.get("image", "")
    if image.startswith("media:"):
        raw, mime = media.read(owner, image[6:])
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("Product photo format is unsupported")
    else:
        from ..services.try_on import sample_asset

        path = sample_asset(product)
        if not path:
            return None  # No invented image understanding for illustrated/absent assets.
        raw = path.read_bytes()
    normalized, _ = media.normalize(raw)
    with Image.open(io.BytesIO(normalized)) as source:
        source.thumbnail((900, 900))
        output = io.BytesIO()
        source.save(output, "JPEG", quality=85)
    return output.getvalue()


def contains_value(text, value):
    names = (value.replace("_", " "), *ALIASES.get(value, ()))
    return any(re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", text.casefold()) for name in names)


def seller_evidence(tag, facts):
    fields = {k: str(v) for k, v in facts.items() if k != "attributes"}
    fields.update({"attributes." + k: str(v) for k, v in facts["attributes"].items()})
    supplied = fields.get(tag.source_field, "")
    quote = tag.evidence.strip().casefold()
    if not quote or quote not in supplied.casefold() or not contains_value(quote, tag.value):
        return False
    # Explicit negative claims cannot become positive performance/fabric claims.
    if tag.field in PHYSICAL:
        if re.search(r"\b(?:not|no|non|without|free of|faux|imitation)\b", quote):
            return tag.value in {"non_stretch", "low_breathability"}
        if "look" in quote or "like" in quote or "feel" in quote:
            return False
    return True


def validate(analysis, product, has_image):
    facts = seller_facts(product)
    accepted, issues = {}, []
    usable = (
        has_image and analysis.image_quality in {"adequate", "limited"} and analysis.image_matches_product
    )
    if has_image and not analysis.image_matches_product:
        issues.append("image_product_mismatch")
    if has_image and analysis.image_quality == "unusable":
        issues.append("image_unusable")
    for tag in analysis.tags:
        # Imported photo descriptions are generated observations, not retailer testimony.
        # A quoted title may help identify the item but cannot establish composition.
        if (
            product.get("attributes", {}).get("description_source") == "gemini_visual"
            and tag.source == "seller"
            and seller_evidence(tag, facts)
        ):
            tag = tag.model_copy(
                update={
                    "source": "styling_inference" if tag.field in INFERRED else "visual",
                    "source_field": "",
                    "evidence": ("Image-derived listing: " + tag.evidence)[:220],
                }
            )
        issue = None
        if tag.value not in VOCAB[tag.field]:
            issue = "unknown_taxonomy_value"
        elif tag.field in PHYSICAL and tag.source != "seller":
            issue = "physical_claim_without_seller_evidence"
        elif tag.source == "seller" and not seller_evidence(tag, facts):
            issue = "unverified_seller_evidence"
        elif tag.source != "seller" and has_image and not usable:
            issue = "image_cannot_support_tag"
        elif tag.source == "visual" and (not usable or tag.field in INFERRED):
            issue = "unsupported_visual_claim"
        elif tag.source == "styling_inference" and tag.field not in INFERRED:
            issue = "unsupported_fact_inference"
        elif tag.field == "category" and tag.value != product["category"]:
            issue = "category_conflict"
        if issue:
            issues.append(f"{tag.field}:{issue}")
            continue
        # Model certainty is not a measured probability. Keep inferred certainty bounded.
        cap = 0.85 if tag.source == "styling_inference" else 0.9 if tag.source == "visual" else 1.0
        checked = tag.model_copy(update={"confidence": min(tag.confidence, cap)})
        existing = accepted.get((tag.field, tag.value))
        if not existing or existing.confidence < checked.confidence:
            accepted[tag.field, tag.value] = checked
    # Retailer categories stay authoritative; a photo-import category is a visual hypothesis.
    derived = product.get("attributes", {}).get("description_source") == "gemini_visual"
    if product["category"] in VOCAB["category"] and (not derived or usable):
        accepted["category", product["category"]] = Tag(
            field="category",
            value=product["category"],
            confidence=0.8 if derived else 1,
            source="visual" if derived else "seller",
            evidence="Primary garment category identified from the supplied photograph"
            if derived
            else product["category"],
            source_field="" if derived else "category",
        )
    # Resolve contradictory single-value traits and bound generic occasion/style tagging.
    limits = {
        "category": 1,
        "fit": 1,
        "silhouette": 2,
        "neckline": 1,
        "sleeve_length": 1,
        "primary_colour": 1,
        "occasion": 3,
        "outfit_template": 3,
        "style": 3,
        "weather": 2,
    }
    for field, limit in limits.items():
        group = sorted(
            [t for t in accepted.values() if t.field == field],
            key=lambda t: (t.source != "seller", -t.confidence, t.value),
        )
        for extra in group[limit:]:
            accepted.pop((field, extra.value))
            issues.append(f"{field}:excess_or_conflicting_tags")
    tags = sorted(accepted.values(), key=lambda t: (t.field, t.value))
    known = {t.field for t in tags if t.confidence >= MIN_CONFIDENCE}
    return tags, sorted(set(issues)), sorted(set(VOCAB) - known)


def analyze(product, image):
    quota("live-ai", "catalogue-enrichment", settings().max_daily_catalogue_enrichments)
    parts = [
        json.dumps(
            {
                "seller_facts": seller_facts(product),
                "vocabulary": {k: sorted(v) for k, v in VOCAB.items()},
                "photo_attached": bool(image),
            }
        )
    ]
    if image:
        parts.insert(0, types.Part.from_bytes(data=image, mime_type="image/jpeg"))
    with ai.client(gemini=True, timeout=50000) as provider:
        response = provider.models.generate_content(
            model=settings().gemini_model,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                response_schema=ProviderAnalysis,
                max_output_tokens=6500,
                thinking_config=ai.thinking(),
                temperature=0.2,
            ),
        )
    result = Analysis.model_validate_json(response.text)
    usage = response.usage_metadata
    return result, {
        key: int(getattr(usage, key, 0) or 0)
        for key in ("prompt_token_count", "candidates_token_count", "thoughts_token_count")
    }


def publish(owner, product, record):
    def merge(latest):
        if not latest or fingerprint(latest) != record["input_hash"]:
            raise RetryableEnrichmentError("Listing changed while its photo was being analyzed")
        return {**latest, "enrichment": record}

    return store().mutate("products", owner, product["id"], merge)


def ensure(owner, product, *, include_inactive=False):
    """Return current product and whether a new provider analysis was performed."""
    if not enabled(owner) or (not product.get("active", True) and not include_inactive):
        return product, False
    if current(product):
        return product, False
    digest = fingerprint(product)
    cache_id = product["id"] + "-" + digest
    started = time.monotonic()

    def claim(old):
        if old and old.get("status") == "complete":
            return old
        if old and old.get("lease_until", 0) > time.time():
            raise RetryableEnrichmentError("This listing is already being analyzed")
        return {"status": "running", "lease_until": time.time() + 100, "product_id": product["id"]}

    cached = store().mutate("catalogue_analysis", owner, cache_id, claim)
    if cached["status"] == "complete":
        return publish(owner, product, cached["record"]), False
    base = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": settings().gemini_model,
        "input_hash": digest,
        "input_mode": "text_only",
        "assessed_at": now(),
    }
    try:
        image = photograph(owner, product)
        base.update(
            input_mode="image_and_text" if image else "text_only",
            image_hash=hashlib.sha256(image).hexdigest() if image else "",
        )
        analysis, usage = analyze(product, image)
        tags, issues, unknown = validate(analysis, product, bool(image))
        needs_review = bool({"image_product_mismatch", "image_unusable"} & set(issues))
        record = Enrichment(
            **base,
            status="needs_review" if needs_review else "complete",
            tags=tags,
            unknown_fields=unknown,
            validation_issues=issues,
            uncertainties=analysis.uncertainties,
            image_quality=analysis.image_quality,
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=usage,
        ).model_dump(mode="json")
        # Cache validated output before publishing: a concurrent stock edit never costs another AI call.
        store().put(
            "catalogue_analysis",
            owner,
            cache_id,
            {
                "status": "complete",
                "product_id": product["id"],
                "record": record,
                "lease_until": 0,
            },
        )
        return publish(owner, product, record), True
    except RetryableEnrichmentError:
        raise
    except Exception as exc:
        # No raw model responses, seller text or credentials in job errors or logs.
        message = "Product analysis could not finish. Retry enrichment; existing seller facts are unchanged."
        record = Enrichment(**base, status="failed", error=message, unknown_fields=sorted(VOCAB)).model_dump(
            mode="json"
        )
        store().put(
            "catalogue_analysis",
            owner,
            cache_id,
            {
                "status": "failed",
                "lease_until": 0,
                "product_id": product["id"],
                "error_type": type(exc).__name__,
            },
        )
        publish(owner, product, record)
        raise RetryableEnrichmentError(message) from exc
