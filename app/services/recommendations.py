import itertools
import re
from fastapi import HTTPException
from ..models import CompatibilityAssessment, Outfit, WardrobeItem
from ..store import store
from ..config import settings
from .inventory import search, available
from . import ai


def get_confirmed_wardrobe(owner):
    return [w for w in store().list("wardrobe", owner) if w["confirmed"]]


def parse_intent(message, previous, default_budget):
    text = message.lower()
    budget = previous.get("budget", default_budget)
    match = re.search(r"(?:₹\s*|rs\.?\s*|inr\s*|under\s+|budget\s+(?:of\s+)?)([\d,]+)", text)
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


def recommend(principal, request, previous):
    owner = principal.uid
    owned = get_confirmed_wardrobe(owner)
    if not owned:
        raise HTTPException(409, "Confirm at least one garment in your wardrobe before chatting")
    profile = store().get("profiles", owner, "me") or {}
    intent = parse_intent(
        request.message,
        previous,
        request.budget if request.budget is not None else profile.get("budget", 5000),
    )
    method = "rule-based"
    note = None
    if settings().ai_ready and not principal.demo:
        try:
            extracted = ai.interpret(request.message, previous)
            if extracted["budget"] is None:
                extracted["budget"] = intent["budget"]
            intent.update(extracted)
            method = "Gemini intent + validated outfit rules"
        except Exception:
            note = (
                "The AI stylist is temporarily unavailable. These are clearly labeled rule-based suggestions."
            )
    if request.budget is not None:
        intent["budget"] = request.budget
    size = request.clothing_size or profile.get("clothing_size", "")
    shoe_size = request.shoe_size or profile.get("shoe_size", "")
    if not size or not shoe_size:
        return {
            "text": "What clothing and shoe sizes should I check? Add them in Profile, or use the size fields here. I won’t guess your size.",
            "outfits": [],
            "intent": intent,
            "method": method,
        }
    catalogue = search(principal.catalog_owner, intent["query"], intent["budget"])
    eligible = []
    for product in catalogue:
        options = available(product, shoe_size if product["category"] == "shoes" else size, request.store_id)
        if options:
            stock = options[0]
            location = store().get("stores", principal.catalog_owner, stock["store_id"])
            if location:
                eligible.append({**product, "availability": stock, "store": location})
    jackets = [p for p in eligible if p["category"] == "jacket"]
    jackets.sort(
        key=lambda p: (
            0 if ("relaxed" in p["attributes"].get("styles", "")) == intent["relaxed"] else 1,
            p["price"],
        )
    )
    if intent["another_jacket"]:
        excluded = set(previous.get("last_product_ids", []))
        jackets = [p for p in jackets if p["id"] not in excluded]
    shoes = sorted([p for p in eligible if p["category"] == "shoes"], key=lambda p: p["price"])
    tops = [w for w in owned if w["category"] == "top"]
    if intent["keep_shirt"]:
        kept = [w for w in tops if w["id"] in previous.get("last_owned_ids", [])]
        if kept:
            tops = kept
    bottoms = [w for w in owned if w["category"] == "bottom"]
    owned_shoes = [w for w in owned if w["category"] == "shoes"]
    dresses = [w for w in owned if w["category"] == "dress"]
    owned_jackets = [w for w in owned if w["category"] == "jacket"]
    # Fill missing base pieces from size/stock-validated records; never imply ownership.
    bases = [(list(pair), []) for pair in itertools.product(tops[:4], bottoms[:4])]
    bases += [([d], []) for d in dresses[:4]]
    if not bases:
        top_choices = [(w, True) for w in tops[:4]] or [
            (p, False) for p in eligible if p["category"] == "top"
        ][:2]
        bottom_choices = [(w, True) for w in bottoms[:4]] or [
            (p, False) for p in eligible if p["category"] == "bottom"
        ][:2]
        for pair in itertools.product(top_choices, bottom_choices):
            bases.append(
                ([p for p, is_owned in pair if is_owned], [p for p, is_owned in pair if not is_owned])
            )
        if not tops and not bottoms:
            bases += [([], [p]) for p in eligible if p["category"] == "dress"][:2]
    # Explicit shopping requests can replace a base or add an accessory, using
    # the same current, size-filtered catalogue as the jacket flow.
    requested_category = None
    buying = re.search(r"\b(show|find|buy|new|need|want|looking for)\b", request.message.lower())
    if buying and not intent["keep_shirt"]:
        for category, pattern in [
            ("dress", r"\bdress(?:es)?\b"),
            ("bottom", r"\b(trousers|jeans|pants|skirt|bottoms?)\b"),
            ("top", r"\b(shirts?|tees?|tops?)\b"),
            ("bag", r"\b(bags?|tote|handbag)\b"),
            ("accessory", r"\b(accessor(?:y|ies)|scarf|belt)\b"),
        ]:
            if re.search(pattern, request.message.lower()):
                requested_category = category
                break
    requested = [p for p in eligible if p["category"] == requested_category][:3]
    if requested_category == "top":
        bases = [([bottom], [product]) for product in requested for bottom in bottoms[:3]]
    elif requested_category == "bottom":
        bases = [([top], [product]) for product in requested for top in tops[:3]]
    elif requested_category == "dress":
        bases = [([], [product]) for product in requested]
    elif requested_category in ("bag", "accessory"):
        bases = [(base, pieces + [product]) for base, pieces in bases[:3] for product in requested]
    explicit_jacket = (
        intent["jacket_coverage"]
        or intent["another_jacket"]
        or bool(re.search(r"\b(jacket|blazer)\b", request.message.lower()))
    )
    layers = (
        [None]
        if requested_category
        else (
            jackets[:8]
            if intent["jacket_coverage"]
            else ((jackets[:3] or [None]) if explicit_jacket or not owned_jackets else [None])
        )
    )
    outfits = []
    counts = {}
    for jacket in layers:
        for base, missing_pieces in bases[:8]:
            used_owned = base + owned_shoes[:1]
            if not jacket:
                used_owned += owned_jackets[:1]
            if not used_owned:
                # A confirmed accessory or existing jacket can still anchor the outfit.
                used_owned = [owned[0]]
            essentials = missing_pieces + (shoes[:1] if not owned_shoes else [])
            purchases = essentials + ([jacket] if jacket else [])
            total = sum(p["price"] for p in purchases)
            if total > intent["budget"]:
                if intent["jacket_coverage"]:
                    continue
                purchases = essentials
                total = sum(p["price"] for p in purchases)
                if owned_jackets and not any(w["category"] == "jacket" for w in used_owned):
                    used_owned += owned_jackets[:1]
            if total > intent["budget"]:
                continue
            score, reason, complete = assess_outfit_compatibility(used_owned, purchases, intent["occasion"])
            if not complete:
                continue
            signature = tuple(sorted(w["id"] for w in used_owned) + sorted(p["id"] for p in purchases))
            if any(o["_signature"] == signature for o in outfits):
                continue
            outfit = Outfit(
                title="A little polish, a lot of possibility"
                if jacket and jacket in purchases
                else "An easy everyday combination",
                occasion=intent["occasion"],
                owned=[WardrobeItem.model_validate(w) for w in used_owned],
                products=purchases,
                total=total,
                explanation=reason,
                complete=complete,
                sample=any(w.get("sample") for w in used_owned) or any(p["sample"] for p in purchases),
            )
            assessment = CompatibilityAssessment(
                garment_ids=[w["id"] for w in used_owned],
                product_ids=[p["id"] for p in purchases],
                outfit_id=outfit.id,
                occasion=intent["occasion"],
                score=score,
                reason=reason,
            )
            outfit.assessment = assessment
            result = outfit.model_dump(mode="json")
            result["_signature"] = signature
            outfits.append(result)
            if jacket and jacket in purchases and complete:
                counts[jacket["id"]] = counts.get(jacket["id"], 0) + 1
    outfits.sort(
        key=lambda o: (
            -counts.get(next((p["id"] for p in o["products"] if p["category"] == "jacket"), ""), 0)
            if intent["jacket_coverage"]
            else 0,
            -o["assessment"]["score"],
            o["total"],
        )
    )
    selected = outfits[:3]
    # Re-read serving stock immediately before returning, independent of search/index cache.
    valid = []
    for outfit in selected:
        current = []
        for product in outfit["products"]:
            latest = store().get("products", principal.catalog_owner, product["id"])
            checks = (
                available(latest, product["availability"]["size"], product["availability"]["store_id"])
                if latest
                else []
            )
            if not checks:
                break
            current.append({**latest, "availability": checks[0], "store": product["store"]})
        else:
            outfit["products"] = current
            outfit["total"] = sum(p["price"] for p in current)
            if outfit["total"] > intent["budget"]:
                continue
            outfit.pop("_signature", None)
            store().put("outfits", owner, outfit["id"], outfit)
            store().put("compatibility", owner, outfit["assessment"]["id"], outfit["assessment"])
            valid.append(outfit)
    if settings().ai_ready and not principal.demo and valid:
        try:
            from .stylist_tools import assess_with_tools

            valid = assess_with_tools(principal, valid)
        except Exception:
            note = "Whole-outfit AI assessment was unavailable; rule-based assessments are shown."
    from .graph import record_outfit

    for outfit in valid:
        record_outfit(owner, outfit)
        store().put("outfits", owner, outfit["id"], outfit)
        store().put("compatibility", owner, outfit["assessment"]["id"], outfit["assessment"])
    intent["last_product_ids"] = [p["id"] for o in valid[:1] for p in o["products"]]
    intent["last_owned_ids"] = [w["id"] for o in valid[:1] for w in o["owned"]]
    if not valid:
        text = "I couldn’t find an available combination within your budget and sizes. Your wardrobe is a good place to start; try another store or keep your current pieces."
    elif intent["jacket_coverage"]:
        best = next((p for p in valid[0]["products"] if p["category"] == "jacket"), None)
        text = (
            f"{best['name']} works in {counts.get(best['id'], 0)} distinct complete outfit candidates we checked. This is a rule-based shortlist, not a review of every possible outfit."
            if best
            else "No available jacket completes a checked outfit within the total budget."
        )
    else:
        text = f"Let’s make what you own work a little harder. I’ve started with your confirmed wardrobe and kept each combination within ₹{intent['budget']:,}. "
        text += (
            "For Mumbai, an easy layer and comfortable shoes can carry you from meetings to a walk."
            if "Mumbai" in intent["occasion"]
            else "Here are a few combinations to make your own."
        )
    if note:
        text = note + " " + text
    return {"text": text, "outfits": valid, "intent": intent, "method": method, "coverage": counts}
