"""Voice navigation is limited to app screens, never URLs or account actions."""

import re

DESTINATIONS = {
    "stylist": "Stylist",
    "wardrobe": "My Wardrobe",
    "inventory": "Inventory",
    "saved": "Saved Looks",
    "fitting": "Fitting Room",
    "orders": "My Orders",
    "profile": "Profile",
    "admin": "Seller Studio",
    "back": "previous page",
    "origin": "page where this voice conversation started",
}

ALIASES = {
    "style": "stylist",
    "styles": "stylist",
    "chat": "stylist",
    "the chat": "stylist",
    "my wardrobe": "wardrobe",
    "closet": "wardrobe",
    "my closet": "wardrobe",
    "shop": "inventory",
    "catalogue": "inventory",
    "catalog": "inventory",
    "saved looks": "saved",
    "saved outfits": "saved",
    "fitting room": "fitting",
    "my previews": "fitting",
    "my orders": "orders",
    "settings": "profile",
    "seller studio": "admin",
    "previous": "back",
    "previous page": "back",
    "original page": "origin",
}


def destination(value):
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().lower().split())
    normalized = ALIASES.get(normalized, normalized)
    return normalized if normalized in DESTINATIONS else None


def spoken_destination(text):
    """Conservative fallback for a complete, explicit navigation utterance.

    Gemini handles general language. This only recognizes standalone page commands,
    never catalogue text, partial transcripts, quoted instructions or mixed actions.
    """
    if not isinstance(text, str):
        return None
    text = " ".join(text.lower().strip().split()).rstrip(".!?")
    text = re.sub(r"^(?:okay|ok|hey|yes)[, ]+", "", text)
    text = re.sub(r"^(?:(?:can|could|would|will) you |please )+", "", text)
    text = re.sub(r",? (?:please|thanks|thank you)$", "", text)
    if re.fullmatch(r"(?:take|bring|send) me (?:back )?(?:to )?where we (?:started|began)", text):
        return "origin"
    if re.fullmatch(
        r"(?:go|come|take me|bring me|send me)(?: back)(?: to (?:the )?(?:previous page|where i was|where we were))?",
        text,
    ):
        return "back"
    match = re.fullmatch(
        r"(?:take me (?:back )?to|bring me (?:back )?to|send me (?:back )?to|"
        r"go (?:back )?to|back to|return to|open|show(?: me)?|navigate to|switch to) "
        r"(?:the )?(.+?)(?: page| screen| tab)?",
        text,
    )
    return destination(match[1]) if match else None
