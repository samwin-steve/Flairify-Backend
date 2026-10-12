"""Bounded, owner-scoped conversational grounding and explicit look refinement."""

import re

from fastapi import HTTPException

from ..store import store
from . import styling

EDIT = re.compile(
    r"\b(another|different|variation|version|instead|swap|replace|change|keep|same|cheaper|relaxed|casual|formal|like|love|prefer)\b",
    re.IGNORECASE,
)
DISCUSS = re.compile(
    r"^(?:hi|hello|hey|thanks?|thank you)[!. ]*$|\b(why|explain|which (?:one|look)|what (?:did|was)|remind me|would .+ work|can i wear|how (?:do|should|can) i|tell me (?:about|more))\b",
    re.IGNORECASE,
)


def latest_looks(conversation):
    return next((m.outfits for m in reversed(conversation.messages) if m.outfits), [])


def all_looks(conversation):
    return {o["id"]: o for m in conversation.messages for o in m.outfits}


def focus(conversation, request, proposed=None):
    looks = all_looks(conversation)
    key = request.reference_outfit_id or proposed
    if key:
        if key not in looks:
            raise HTTPException(422, "Choose a look from this conversation to refine")
        return looks[key]
    recent = latest_looks(conversation)
    text = request.message.lower()
    ordinal = re.search(r"\b(first|second|third|1st|2nd|3rd)\b|(?:look|option)\s*#?([123])\b", text)
    if ordinal:
        number = {"first": 0, "second": 1, "third": 2, "1st": 0, "2nd": 1, "3rd": 2}.get(
            ordinal[1], int(ordinal[2] or 1) - 1
        )
        return recent[number] if number < len(recent) else None
    if EDIT.search(text) or DISCUSS.search(text):
        return looks.get(conversation.intent.get("focus_outfit_id")) or (recent[0] if recent else None)
    return None


def compact_look(look):
    return {
        "id": look["id"],
        "title": look["title"],
        "occasion": look["occasion"],
        "explanation": look["explanation"],
        "pieces": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "colour": p.get("colour") or p.get("attributes", {}).get("colour"),
                "owned": owned,
            }
            for owned, pieces in [(False, look["products"]), (True, look["owned"])]
            for p in pieces
        ],
    }


def context(conversation, request):
    selected = focus(conversation, request)
    return {
        "active_brief": {
            k: v for k, v in conversation.intent.items() if k not in ("shown_product_ids", "last_product_ids")
        },
        "latest_looks": [compact_look(o) for o in latest_looks(conversation)],
        "selected_look": compact_look(selected) if selected else None,
        # A bounded transcript gives older corrections context without embedding private chat in catalogue vectors.
        "earlier_customer_requests": [
            m.content[:500] for m in conversation.messages[:-12] if m.role == "user"
        ][-12:],
    }


def refinement(conversation, request, interpreted):
    selected = focus(conversation, request, (interpreted or {}).get("reference_outfit_id"))
    if not selected or not (
        request.reference_outfit_id or EDIT.search(request.message) or (interpreted or {}).get("refine")
    ):
        return None
    text = request.message.lower()
    if (
        re.search(r"\b(different options|more options|other options|something cheaper)\b", text)
        and not request.reference_outfit_id
        and not conversation.intent.get("focus_outfit_id")
        and not re.search(r"\b(keep|first|second|third|this|that)\b", text)
    ):
        return None
    # An explicit new occasion resets the look unless the customer explicitly asks to adapt it.
    if re.search(
        r"\b(now|instead|actually)\b.*\b(gym|wedding|beach|workout|interview)\b", text
    ) and not re.search(r"\b(this|that|same|keep)\b", text):
        return None
    categories = [c for c, pattern in styling.CATEGORY_WORDS.items() if re.search(pattern, text)]
    keep = set()
    for fragment in re.findall(
        r"\bkeep\b(.+?)(?=(?:and|but)\s+(?:swap|replace|change|try|show)|[,.]|$)", text
    ):
        keep.update(c for c, pattern in styling.CATEGORY_WORDS.items() if re.search(pattern, fragment))
    changed = [c for c in categories if c not in keep]
    if not changed:
        changed = [
            c
            for c in (interpreted or {}).get("change_categories", [])
            if c in styling.CATEGORY_WORDS and c not in keep
        ]
    if not changed:
        changed = [
            next(
                (
                    p["category"]
                    for p in selected["products"]
                    if p["category"] in ("top", "dress", "jacket") and p["category"] not in keep
                ),
                "shoes",
            )
        ]
    return {"look": selected, "change_categories": changed, "keep_categories": list(keep)}


def discussion(principal, request, conversation):
    """Refresh catalogue facts without generating a new rack of recommendations."""
    selected = focus(conversation, request)
    rows = [selected] if selected else latest_looks(conversation)
    facts = []
    for look in rows:
        item = compact_look(look)
        item["current_products"] = []
        for p in look["products"]:
            current = store().get("products", principal.catalog_owner, p["id"])
            item["current_products"].append(
                {k: current.get(k) for k in ("id", "name", "description", "attributes", "price", "active")}
                if current and current.get("indexed")
                else {"id": p["id"], "unavailable": True}
            )
        facts.append(item)
    if facts:
        text = f"For {facts[0]['title']}, {facts[0]['explanation']} Would you like to keep the main piece and change the shoes, or try another colour?"
    else:
        text = "I'm here to help you put a look together. What are you dressing for?"
    intent = dict(conversation.intent)
    if selected:
        intent["focus_outfit_id"] = selected["id"]
    return {
        "text": text,
        "outfits": [],
        "intent": intent,
        "method": "conversation",
        "discussed_looks": facts,
    }
