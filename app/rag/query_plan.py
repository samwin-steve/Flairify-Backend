"""Category-specific retrieval keeps supporting pieces aligned with the whole look."""

LABELS = {
    "top": "shirts tops kurtas",
    "bottom": "trousers chinos jeans skirts",
    "dress": "dresses one-piece outfits",
    "jacket": "jackets blazers outerwear",
    "shoes": "shoes footwear",
    "bag": "bags",
    "accessory": "accessories",
}


def build(intent, refinement=None):
    target = intent.get("requested_category")
    categories = (target,) if intent.get("single_item") and target else ("top", "bottom", "shoes", "dress")
    if target and target not in categories:
        categories += (target,)
    if refinement:
        categories = tuple(refinement["change_categories"])
    context = f"{intent['occasion']}. Dress code: {intent['dress_code']}. {intent['query']}"
    queries = {}
    for category in categories:
        palette = " ".join(intent.get("palette", []))
        if category in ("bottom", "shoes") and len(categories) > 1:
            palette = "neutral colours to complement the main garment"
        if refinement:
            retained = [
                p
                for p in refinement["look"]["products"] + refinement["look"]["owned"]
                if p["category"] not in categories
            ]
            anchor = "; ".join(p["name"] for p in retained)
            style = next((p for p in refinement["look"]["products"] if p["category"] == category), None)
            context_piece = f"Complement these retained pieces: {anchor}."
            if style:
                context_piece += f" Alternative to: {style['name']}."
        else:
            context_piece = ""
        queries[category] = f"{LABELS[category]} for {context}. {palette}. {context_piece}"[:2000]
    return categories, queries
