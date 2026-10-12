import itertools
import re

from ..config import settings
from ..models import CompatibilityAssessment, Outfit, WardrobeItem
from ..rag import query_plan, wardrobe_graph
from ..rag.retrieval import candidates
from ..store import store
from . import conversation_context, styling
from .inventory import available


def get_confirmed_wardrobe(owner):
    return [w for w in store().list("wardrobe", owner) if w["confirmed"]]


def parse_intent(message, previous, default_budget):
    text = message.lower()
    budget = previous.get("budget", default_budget)
    match = re.search(
        r"(?:₹\s*|\brs\.?\s*|\binr\s*|\bunder\s+|\bup to\s+|\bbudget\s+(?:of\s+)?)(\d[\d,]*)", text
    )
    if match:
        budget = min(1000000, int(match.group(1).replace(",", "")))
    cheaper = "cheaper" in text or "less expensive" in text
    if cheaper and not match:
        budget = max(0, int(budget * 0.75))
    return {
        "budget": budget,
        "occasion": "Mumbai · work trip"
        if "mumbai" in text
        else ("Work & everyday" if "work" in text else previous.get("occasion", "Everyday")),
        "query": message,
        "relaxed": "relaxed" in text or previous.get("relaxed", False),
        "cheaper": cheaper,
        "another_jacket": "another jacket" in text or "another blazer" in text,
        "keep_shirt": "keep my shirt" in text,
        "jacket_coverage": "most" in text and ("jacket" in text or "blazer" in text),
    }


def assess_outfit_compatibility(owned, products, occasion):
    cats = {w["category"] for w in owned} | {p["category"] for p in products}
    complete = ("dress" in cats or {"top", "bottom"} <= cats) and "shoes" in cats
    colours = {w["colour"].lower() for w in owned}
    score = (
        0.62
        + (0.18 if complete else 0)
        + (0.07 if "jacket" in cats else 0)
        + (0.05 if len(colours) <= 3 else 0)
    )
    owned_names = ", ".join(w["name"] for w in owned)
    new_names = ", ".join(p["name"] for p in products)
    reason = f"Build around {owned_names}. "
    if new_names:
        reason += f"Add {new_names}. "
    reason += "The base, layer and shoes were considered together for " + occasion.lower() + ". "
    reason += (
        "Try the shoes for comfort; your chosen size is not a fit guarantee."
        if "shoes" in cats
        else "Add your own comfortable shoes to complete this combination."
    )
    return min(score, 1), reason, complete


def recommend(principal, request, previous, *, interpreted=None, conversation=None):
    owner = principal.uid
    profile = store().get("profiles", owner, "me") or {}
    include_owned = (
        request.include_wardrobe
        if request.include_wardrobe is not None
        else profile.get("include_wardrobe", False)
    )
    owned = get_confirmed_wardrobe(owner) if include_owned else []
    intent = parse_intent(
        request.message,
        previous,
        request.budget if request.budget is not None else profile.get("budget", 5000),
    )
    ceiling = intent["budget"]
    intent.update({k: v for k, v in (interpreted or {}).items() if v is not None})
    intent["budget"] = max(
        0,
        min(
            ceiling, intent.get("budget", ceiling), request.budget if request.budget is not None else ceiling
        ),
    )
    refinement = conversation_context.refinement(conversation, request, interpreted) if conversation else None
    interpretation = {**(interpreted or {}), "refine": bool(refinement)}
    intent.update(styling.brief(request.message, previous, interpretation))
    if refinement:
        intent["occasion"] = refinement["look"]["occasion"]
        intent["requested_category"] = refinement["change_categories"][0]
        intent["single_item"] = not refinement["look"]["complete"]
        intent["different"] = True
        if re.search(
            r"\b(white|green|orange|blue|black|red|pink|purple|beige|navy)\b", request.message, re.IGNORECASE
        ):
            intent["palette_category"] = refinement["change_categories"][0]
        if intent.get("required_type") and not re.search(
            styling.CATEGORY_WORDS[intent["requested_category"]], intent["required_type"]
        ):
            intent["required_type"] = None
        intent["reference_outfit_id"] = refinement["look"]["id"]
    intent["include_wardrobe"] = include_owned
    size = request.clothing_size or profile.get("clothing_size", "")
    shoe_size = request.shoe_size or profile.get("shoe_size", "")
    department = request.department or profile.get("department", "all")
    store_id = request.store_id or profile.get("preferred_store_id") or None
    if re.search(r"\bwomen(?:['’]?s)?\b", request.message.lower()):
        department = "women"
    elif re.search(r"\bmen(?:['’]?s)?\b", request.message.lower()):
        department = "men"
    intent["department"] = department
    if not size or not shoe_size:
        return {
            "text": "Your shopping sizes are not saved yet. Update them once in Profile; future recommendations will use them automatically.",
            "outfits": [],
            "intent": intent,
            "method": "profile-setup-required",
        }
    locations = {s["id"]: s for s in store().list("stores", principal.catalog_owner)}
    if store_id and store_id not in locations:
        return {
            "text": "Your saved store is no longer available. Update your store preference in Profile.",
            "outfits": [],
            "intent": intent,
            "method": "profile-setup-required",
        }
    # Carry the interpreted occasion into retrieval, including the actual palette and garment types.
    query = " ".join(
        [
            intent["query"],
            intent["occasion"],
            intent["dress_code"],
            " ".join(intent["palette"]),
            " ".join(intent["preferred_types"]),
        ]
    )
    recent = set(previous.get("shown_product_ids", previous.get("last_product_ids", [])))
    excluded = (
        {p["id"] for p in refinement["look"]["products"] if p["category"] in refinement["change_categories"]}
        if refinement
        else set()
    )
    categories, category_queries = query_plan.build(intent, refinement)
    catalogue, retrieval = candidates(
        principal.catalog_owner,
        query,
        intent["budget"],
        department=department,
        store_id=store_id,
        clothing_size=size,
        shoe_size=shoe_size,
        categories=categories,
        category_queries=category_queries,
        exclude_ids=excluded,
        deeper=bool(refinement or intent["different"]),
    )
    target = intent.get("requested_category")
    # Retained products bypass vector ranking but never current size/stock checks.
    if refinement:
        retrieved_ids = {p["id"] for p in catalogue}
        for original in refinement["look"]["products"]:
            if (
                original["id"] not in retrieved_ids
                and original["category"] not in refinement["change_categories"]
            ):
                current = store().get("products", principal.catalog_owner, original["id"])
                if current and current.get("indexed"):
                    catalogue.append(current)
    eligible = []
    for product in catalogue:
        if not product.get("active", True) or not styling.suitable(product, intent):
            continue
        if department != "all" and product.get("attributes", {}).get("department", "").lower() not in (
            department,
            "unisex",
        ):
            continue
        required_size = (
            "One size"
            if product["category"] in ("accessory", "bag")
            else shoe_size
            if product["category"] == "shoes"
            else size
        )
        stock = next(
            (s for s in available(product, required_size, store_id) if s["store_id"] in locations), None
        )
        if stock:
            eligible.append({**product, "availability": stock, "store": locations[stock["store_id"]]})
    graph = (
        wardrobe_graph.coverage(owner, owned, [p["id"] for p in eligible], intent["occasion"])
        if owned and not principal.demo
        else {"status": "not_requested" if not include_owned else "demo", "counts": {}}
    )
    suitable_owned = [w for w in owned if styling.suitable(w, intent)]
    if intent.get("palette"):
        suitable_owned = [
            w for w in suitable_owned if styling.colours(w) & (styling.NEUTRALS | set(intent["palette"]))
        ]
    if intent.get("keep_shirt") and include_owned:
        kept = [
            w
            for w in suitable_owned
            if w["category"] == "top" and w["id"] in previous.get("last_owned_ids", [])
        ]
        if kept:
            suitable_owned = [w for w in suitable_owned if w["category"] != "top"] + kept

    def rank(piece, is_owned=False):
        value = styling.relevance(piece, intent, piece.get("_semantic_score", 0))
        return value + (1.25 if is_owned else 0) + min(0.3, 0.05 * graph["counts"].get(piece["id"], 0))

    def choices(category, new_only=False):
        if refinement and category not in refinement["change_categories"]:
            original = next(
                (
                    p
                    for p in refinement["look"]["products"] + refinement["look"]["owned"]
                    if p["category"] == category
                ),
                None,
            )
            if original:
                kept = [(p, False) for p in eligible if p["id"] == original["id"]]
                kept += [(w, True) for w in suitable_owned if w["id"] == original["id"]]
                return kept
        new = [(p, False) for p in eligible if p["category"] == category]
        if intent["different"] and category == (target or "top"):
            unseen = [(p, o) for p, o in new if p["id"] not in recent]
            # Never repeat the item being replaced. Reuse older supporting choices only
            # when the bounded catalogue has no unseen alternative.
            new = unseen or ([(p, o) for p, o in new if p["id"] not in excluded] if refinement else [])
        rows = new + ([] if new_only else [(w, True) for w in suitable_owned if w["category"] == category])
        if intent.get("keep_shirt") and include_owned and category == "top":
            kept = [r for r in rows if r[1] and r[0]["id"] in previous.get("last_owned_ids", [])]
            if kept:
                return kept[:1]
        return sorted(rows, key=lambda r: (-rank(*r), r[0]["id"]))[:8]

    combinations = []
    if refinement:
        slots = list(
            dict.fromkeys(
                [p["category"] for p in refinement["look"]["products"] + refinement["look"]["owned"]]
                + refinement["change_categories"]
            )
        )
        # A bounded beam prevents multi-slot edits from expanding exponentially.
        combinations = [[]]
        for category in slots:
            expanded = [
                rows + [piece]
                for rows in combinations
                for piece in choices(category, category in refinement["change_categories"])
            ]
            expanded = [
                rows
                for rows in expanded
                if sum(p["price"] for p, owned in rows if not owned) <= intent["budget"]
            ]
            expanded.sort(key=lambda rows: -sum(rank(p, owned) for p, owned in rows))
            counts = {}
            combinations = []
            for rows in expanded:
                anchor = next((p["id"] for p, _ in rows if p["category"] == target), None)
                if anchor is not None and counts.get(anchor, 0) >= 12:
                    continue
                combinations.append(rows)
                counts[anchor] = counts.get(anchor, 0) + 1
                if len(combinations) >= 96:
                    break
    elif intent["single_item"] and target:
        combinations = [[p] for p in choices(target, True)]
    else:
        # Optional layers are added only when requested. No compulsory jacket or accessory.
        for top, bottom, shoe in itertools.product(
            choices("top", target == "top"),
            choices("bottom", target == "bottom"),
            choices("shoes", target == "shoes"),
        ):
            combinations.append([top, bottom, shoe])
        if target not in ("top", "bottom") and not intent.get("keep_shirt"):
            combinations += [
                [dress, shoe]
                for dress, shoe in itertools.product(choices("dress", target == "dress"), choices("shoes"))
            ]
        if target in ("jacket", "bag", "accessory"):
            combinations = [base + [piece] for base in combinations for piece in choices(target, True)]
    options = []
    for combination in combinations:
        used_owned = [p for p, is_owned in combination if is_owned]
        purchases = [p for p, is_owned in combination if not is_owned]
        if not purchases or len(used_owned) > 2 or not styling.compatible(used_owned + purchases, intent):
            continue
        total = sum(p["price"] for p in purchases)
        if total > intent["budget"]:
            continue
        primary = (
            next((p for p in purchases if p["category"] == target), None)
            or next((p for p in purchases if p["category"] in ("top", "dress")), None)
            or purchases[0]
        )
        key = ":".join(sorted(("o" if o else "p") + p["id"] for p, o in combination))
        rating = sum(rank(p, o) for p, o in combination) / len(combination)
        # A changed request must not inherit price-first ranking. Relevance leads; price is a tie break.
        options.append(
            {
                "key": key,
                "anchor": primary["id"],
                "ids": [p["id"] for p in purchases],
                "rank": rating,
                "owned": used_owned,
                "products": purchases,
                "total": total,
                "accepted": True,
            }
        )
    shortlist = styling.diverse(options, 12, recent)
    assessment_method = styling.assess_shortlist(
        shortlist, intent, settings().ai_ready and not principal.demo
    )
    selected = styling.diverse([o for o in shortlist if o["accepted"]], 3, recent)
    valid = []
    for option in selected:
        current = []
        for product in option["products"]:
            latest = store().get("products", principal.catalog_owner, product["id"])
            checks = (
                available(latest, product["availability"]["size"], product["availability"]["store_id"])
                if latest
                and latest.get("active", True)
                and latest.get("indexed")
                and styling.suitable(latest, intent)
                else []
            )
            if not checks:
                break
            current.append({**latest, "availability": checks[0], "store": product["store"]})
        else:
            total = sum(p["price"] for p in current)
            if total > intent["budget"] or not styling.compatible(option["owned"] + current, intent):
                continue
            score, _default_reason, complete = assess_outfit_compatibility(
                option["owned"], current, intent["occasion"]
            )
            primary = next((p for p in current if p["id"] == option["anchor"]), current[0])
            colour = primary.get("attributes", {}).get("colour", "")
            context = f"{colour} {primary['category']}".strip().capitalize()
            reason = option.get(
                "reason"
            ) or f"{context} leads this option for {intent['occasion'].lower()}. " + (
                "The pieces are considered together for the occasion. "
                if complete
                else "A focused selection, without extra purchases. "
            ) + (
                "Pairs with " + ", ".join(w["name"] for w in option["owned"]) + "."
                if option["owned"]
                else "All shown pieces are from the catalogue."
            )
            outfit = Outfit(
                title=primary["name"],
                occasion=intent["occasion"],
                owned=[WardrobeItem.model_validate(w) for w in option["owned"]],
                products=current,
                total=total,
                explanation=reason,
                complete=complete,
                sample=any(p.get("sample") for p in current + option["owned"]),
            )
            outfit.assessment = CompatibilityAssessment(
                garment_ids=[w["id"] for w in option["owned"]],
                product_ids=[p["id"] for p in current],
                outfit_id=outfit.id,
                occasion=intent["occasion"],
                score=option.get("model_score", score),
                reason=reason,
                source="gemini" if assessment_method == "gemini" else "rule",
                version=settings().gemini_model if assessment_method == "gemini" else "occasion-diversity-v2",
            )
            data = outfit.model_dump(mode="json")
            data["wardrobe_version"] = wardrobe_graph.version(owned)
            data["graph_evidence"] = {
                **graph,
                "counts": {p["id"]: graph["counts"][p["id"]] for p in current if p["id"] in graph["counts"]},
            }
            store().put("outfits", owner, outfit.id, data)
            store().put("compatibility", owner, outfit.assessment.id, data["assessment"])
            from .graph import record_outfit

            record_outfit(owner, data)
            valid.append(data)
    if valid and owned and not principal.demo:
        wardrobe_graph.schedule(owner)
    intent["last_outfit_ids"] = [o["id"] for o in valid] or previous.get("last_outfit_ids", [])
    intent["focus_outfit_id"] = (
        valid[0]["id"] if refinement and valid else previous.get("focus_outfit_id") if refinement else None
    )
    intent["last_product_ids"] = [p["id"] for o in valid for p in o["products"]] or previous.get(
        "last_product_ids", []
    )
    intent["shown_product_ids"] = list(
        dict.fromkeys(previous.get("shown_product_ids", []) + intent["last_product_ids"])
    )[-100:]
    intent["last_owned_ids"] = [w["id"] for o in valid for w in o["owned"]] or previous.get(
        "last_owned_ids", []
    )
    if valid:
        if refinement:
            changed = ", ".join(refinement["change_categories"])
            text = (
                f"I've kept the rest of your look and found {len(valid)} {'alternative' if len(valid) == 1 else 'alternatives'} for the {changed}. "
                + valid[0]["explanation"]
            )
        else:
            text = (
                f"Here are {len(valid)} different directions for {intent['occasion'].lower()}. "
                + valid[0]["explanation"]
            )
    else:
        context = f"clothing {size} and EU {shoe_size}"
        text = f"I found no matching {target or 'complete combination'} suitable for {intent['occasion'].lower()} in {context} within ₹{intent['budget']:,}. "
        text += "I won't substitute unrelated pieces. You can review your saved filters in Profile or browse Inventory."
    return {
        "text": text,
        "outfits": valid,
        "intent": intent,
        "method": "Google ADK / occasion-aware outfits" if interpreted else "Rule-based demo",
        "retrieval": retrieval,
        "graph": graph,
        "assessment_method": assessment_method,
    }
