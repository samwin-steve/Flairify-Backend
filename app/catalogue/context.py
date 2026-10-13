"""Bounded contextual reranking of retrieved items; absent tags are not negative facts."""

import json
import re

from .enrichment import search_metadata, search_tags

CONTEXTS = {
    r"wedding|reception|sangeet": {"occasion": "wedding", "outfit_template": "wedding_guest"},
    r"office|work\b|meeting|conference|interview": {"occasion": "office", "outfit_template": "office_ready"},
    r"party|cocktail|nightclub": {"occasion": "party"},
    r"travel|vacation|holiday|trip": {"occasion": "travel", "outfit_template": "vacation_capsule"},
    r"festival|festive|diwali|eid|independence|republic day": {
        "occasion": "festival",
        "outfit_template": "festive_celebration",
    },
    r"date|romantic|dinner": {"occasion": "date_night", "outfit_template": "date_night"},
    r"weekend|casual|brunch": {"occasion": "casual_outing", "outfit_template": "weekend_casual"},
    r"gym|workout|running|athleisure": {"occasion": "workout", "outfit_template": "athleisure"},
    r"hot|summer|warm|humid": {"weather": "warm_weather"},
    r"winter|cold": {"weather": "cold_weather"},
}


def targets(intent):
    text = " ".join(str(intent.get(k, "")) for k in ("query", "occasion", "dress_code")).lower()
    result = set()
    for pattern, fields in CONTEXTS.items():
        if re.search(pattern, text):
            result.update(fields.items())
    for style in (
        "minimalist",
        "formal",
        "streetwear",
        "vintage",
        "bohemian",
        "contemporary",
        "smart_casual",
        "sporty",
        "ethnic",
    ):
        if re.search(r"\b" + style.replace("_", " ") + r"\b", text):
            result.add(("style", style))
    return result


def query_context(intent):
    return "; ".join(f"{field}: {value.replace('_', ' ')}" for field, value in sorted(targets(intent)))


def relevance(product, intent):
    wanted = targets(intent)
    tags = search_tags(product)
    if not tags or not wanted:
        return 0.0
    matches = {(t["field"], t["value"]): t["confidence"] for t in tags}
    # At most one boost per dimension: broadly tagged products cannot win by tag stuffing.
    score = sum(
        max((matches.get((field, value), 0) for f, value in wanted if f == field), default=0) * weight
        for field, weight in (("occasion", 2.4), ("outfit_template", 1.2), ("style", 1.0), ("weather", 0.6))
    )
    wanted_occasions = {v for f, v in wanted if f == "occasion"}
    actual = {t["value"] for t in tags if t["field"] == "occasion"}
    # A known casual-only main garment is less convincing for a wedding or office.
    if (
        product["category"] in {"top", "dress", "jacket"}
        and wanted_occasions
        and actual
        and not wanted_occasions & actual
    ):
        score -= 1.5
    return score


def pairing_bonus(pieces):
    """Small tie-breaker for grounded complement hypotheses; whole-outfit checks still run."""
    metadata = [search_metadata(p) for p in pieces]
    hits = 0
    for i, source in enumerate(metadata):
        suggested = set(
            source.get("matching_garment", []) + source.get("footwear", []) + source.get("accessory", [])
        )
        for j, other in enumerate(metadata):
            if i != j and suggested & set(other.get("subcategory", [])):
                hits += 1
    return min(0.6, hits * 0.15)


def assessment_context(product):
    if "enrichment" not in product:
        return product.get("styling_context", {})
    # Compact source/field/value groups avoid repeating the audit record in every
    # outfit, conversation message and Gemini tool response.
    groups = {}
    for tag in search_tags(product):
        if tag["field"] != "category":
            groups.setdefault(tag["source"], {}).setdefault(tag["field"], {})[tag["value"]] = tag[
                "confidence"
            ]
    return groups


def appearance_words(product):
    # Suggested pairing garments must not be confused with the product itself.
    groups = search_metadata(product)
    return json.dumps(
        {
            k: v
            for k, v in groups.items()
            if k
            in {
                "subcategory",
                "fit",
                "silhouette",
                "neckline",
                "sleeve_length",
                "pattern",
                "primary_colour",
                "secondary_colour",
                "print",
                "design_detail",
            }
        }
    ).replace("_", " ")
