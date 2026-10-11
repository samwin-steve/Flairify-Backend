"""Download free licensed sample imagery; each source page confirms its license."""

import html, json, re
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import httpx

root = Path(__file__).resolve().parents[2]
items = {
    "shirt": (
        "https://unsplash.com/photos/white-dress-shirt-hanging-on-clothes-hanger-e8sbQNYEwX8",
        "Fallon Michael",
    ),
    "blazer": (
        "https://unsplash.com/photos/a-woman-poses-in-a-large-beige-blazer-hnAWDdHSgSI",
        "Alina Matveycheva",
    ),
    "sneakers": (
        "https://unsplash.com/photos/a-pair-of-white-sneakers-on-a-white-background-8GzbKs74yq4",
        "Maria Fernanda Pissioli",
    ),
    "tote": ("https://unsplash.com/photos/white-tote-bag-lihCTIOP28U", "Rahul Bhogal"),
    "hero": (
        "https://unsplash.com/photos/woman-in-white-blazer-standing-beside-beige-concrete-wall-ByT3r80omGs",
        "Guillaume Bolduc",
    ),
}
items.update(
    {
        "jeans": (
            "https://unsplash.com/photos/blue-denim-jeans-on-black-surface-3oejsU5OQVk",
            "Eduardo Pastor",
        ),
        "tee": ("https://unsplash.com/photos/white-crew-neck-t-shirt-acn5ERAeSb4", "Haryo Setyadi"),
        "jacket": (
            "https://unsplash.com/photos/woman-wearing-green-jacket-standing-near-the-wall-s0CrFb7LoBM",
            "Yunming Wang",
        ),
        "loafers": ("https://unsplash.com/photos/pair-of-brown-leather-shoes-r6yad26A_qc", "rupixen"),
        "shirt": (
            "https://unsplash.com/photos/white-dress-shirt-hanged-on-black-clothes-hanger-R0LzhF574gU",
            "See source photo page",
        ),
    }
)
manifest = []
with httpx.Client(timeout=45, follow_redirects=True) as client:
    for name, (page, author) in items.items():
        res = client.get(page)
        res.raise_for_status()
        match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', res.text)
        if not match:
            match = re.search(r'<meta[^>]*content="([^"]+)"[^>]*property="og:image"', res.text)
        if not match:
            raise RuntimeError("No source image for " + name)
        url = html.unescape(match.group(1))
        parsed = urlparse(url)
        if parsed.hostname != "images.unsplash.com":
            raise RuntimeError("Unexpected image host")
        url = urlunparse(
            parsed._replace(
                query=urlencode(
                    {"auto": "format", "fit": "crop", "w": 1200 if name == "hero" else 720, "q": 85}
                )
            )
        )
        photo = client.get(url)
        photo.raise_for_status()
        (root / "frontend/public/images" / f"{name}.jpg").write_bytes(photo.content)
        manifest.append(
            {
                "file": f"images/{name}.jpg",
                "source": page,
                "author": author,
                "image_url": url,
                "license": "Unsplash License",
                "license_url": "https://unsplash.com/license",
                "purpose": "Sample / editorial only; no retailer affiliation or verified product identity",
            }
        )
        print(name, len(photo.content))
    trousers_url = "https://images.pexels.com/photos/33055598/pexels-photo-33055598/free-photo-of-casual-black-pants-on-white-background.jpeg?auto=compress&dpr=1&h=750&w=1260"
    photo = client.get(trousers_url)
    photo.raise_for_status()
    (root / "frontend/public/images/trousers.jpg").write_bytes(photo.content)
    manifest.append(
        {
            "file": "images/trousers.jpg",
            "source": "https://www.pexels.com/photo/casual-black-pants-on-white-background-33055598/",
            "author": "Youssef Mahmoud",
            "image_url": trousers_url,
            "license": "Pexels License",
            "license_url": "https://www.pexels.com/license/",
            "purpose": "Illustrative sample. No retailer affiliation or verified product identity.",
        }
    )
(root / "frontend/public/image-credits.json").write_text(json.dumps(manifest, indent=2))
