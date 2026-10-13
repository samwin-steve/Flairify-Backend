"""Voice navigation is limited to app screens, never URLs or account actions."""

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
