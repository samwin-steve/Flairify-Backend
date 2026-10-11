"""Build a reproducible, explicitly synthetic 200-product catalogue from licensed dataset samples.

Downloads selected files only (not the multi-GB archives). Run from this repository with
.venv/bin/python scripts/expand_catalogue.py; no Kaggle credentials are required for these public files.
"""

import csv
import io
import json
import re
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".data/catalogue-source"
FRONT = ROOT.parent / "frontend/public"
CLOTHING_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]
SHOE_SIZES = [str(i) for i in range(35, 49)]
DATASETS = {
    "fashion": ("paramaggarwal/fashion-product-images-dataset", "MIT"),
    "myntra": ("hiteshsuthar101/myntra-fashion-product-dataset", "ODC PDDL 1.0"),
}


def download(dataset, filename, maximum=25_000_000):
    url = f"https://www.kaggle.com/api/v1/datasets/download/{dataset}/{quote(filename, safe='')}"
    with httpx.Client(timeout=75, follow_redirects=True) as client, client.stream("GET", url) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > maximum:
                raise ValueError("Dataset file exceeds download limit")
    raw = bytes(body)
    if raw.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            matches = [f for f in archive.infolist() if not f.is_dir()]
            if len(matches) != 1 or matches[0].file_size > maximum:
                raise ValueError("Unexpected dataset archive contents")
            raw = archive.read(matches[0])
    return raw


def rows(dataset, filename):
    cache = CACHE / filename.replace("/", "_")
    if not cache.exists():
        cache.write_bytes(download(dataset, filename))
    return [r for r in csv.DictReader(io.StringIO(cache.read_text(encoding="utf-8-sig"))) if None not in r]


def variants(key, category, colour, quantity=12):
    sizes = (
        SHOE_SIZES
        if category == "shoes"
        else (["One size"] if category in ("bag", "accessory") else CLOTHING_SIZES)
    )
    return [
        {
            "id": f"{key}-{size.lower().replace(' ', '-')}",
            "size": size,
            "colour": colour,
            "stock": [
                {
                    "store_id": store,
                    "quantity": quantity,
                    "aisle": {
                        "top": "A",
                        "bottom": "B",
                        "jacket": "C",
                        "dress": "D",
                        "shoes": "E",
                        "bag": "F",
                        "accessory": "G",
                    }[category],
                    "rack": "Sample rack 1",
                }
                for store in ("bandra", "lower-parel")
            ],
        }
        for size in sizes
    ]


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    legacy = ROOT / "fixtures/catalogue-legacy.json"
    if not legacy.exists():
        legacy.write_bytes((ROOT / "fixtures/catalogue.json").read_bytes())
    records = json.loads(legacy.read_text())
    for p in records:
        colour = p["variants"][0]["colour"]
        p["variants"] = variants(p["id"], p["category"], colour, 0 if p["id"] == "p-soldout" else 12)
        p["attributes"]["department"] = "women" if p["category"] == "dress" else "unisex"
        p["attributes"]["availability_source"] = "Simulated sizes and stock; not retailer availability"
    source_rows = rows("paramaggarwal/fashion-product-images-small", "styles.csv")
    categories = {
        "top": ["Shirts", "Tshirts", "Tops", "Kurtas", "Tunics"],
        "bottom": ["Trousers", "Jeans", "Track Pants", "Skirts", "Shorts", "Leggings"],
        "jacket": ["Jackets", "Blazers", "Rain Jacket"],
        "dress": ["Dresses"],
        "shoes": ["Casual Shoes", "Formal Shoes", "Sports Shoes", "Flats", "Sandals"],
        "bag": ["Backpacks", "Handbags", "Messenger Bag", "Laptop Bag"],
        "accessory": ["Belts", "Scarves", "Caps"],
    }
    quotas = {
        "Men": {"top": 24, "bottom": 22, "jacket": 12, "shoes": 20, "bag": 6, "accessory": 6},
        "Women": {"top": 20, "bottom": 18, "jacket": 10, "dress": 12, "shoes": 16, "bag": 4, "accessory": 2},
        "Unisex": {"shoes": 4, "bag": 4, "accessory": 2},
    }
    selected = []
    for department, groups in quotas.items():
        for category, count in groups.items():
            pools = [
                [
                    r
                    for r in source_rows
                    if r["gender"] == department
                    and r["articleType"] == article
                    and r["productDisplayName"]
                    and r["baseColour"]
                ]
                for article in categories[category]
            ]
            # Round-robin article types avoids 20 near-identical shirts or shoes.
            candidates = []
            while any(pools) and len(candidates) < count:
                for pool in pools:
                    if pool and len(candidates) < count:
                        candidates.append(pool.pop(0))
            if len(candidates) != count:
                raise ValueError(f"Insufficient source options for {department} {category}")
            for r in candidates:
                selected.append(
                    {
                        "dataset": "fashion",
                        "source_id": r["id"],
                        "source_file": f"fashion-dataset/fashion-dataset/images/{r['id']}.jpg",
                        "name": r["productDisplayName"],
                        "colour": r["baseColour"],
                        "brand": "",
                        "department": department.lower(),
                        "category": category,
                        "styles": r["usage"].lower(),
                        "article_type": r["articleType"],
                    }
                )
    myntra = rows(DATASETS["myntra"][0], "Fashion Dataset.csv")
    used = set()
    for category, pattern, count in [
        ("top", r"\b(shirt|top|t-shirt)$", 3),
        ("dress", r"\bdress$", 3),
        ("bottom", r"\btrousers\b", 2),
    ]:
        eligible = [
            r
            for r in myntra
            if re.search(pattern, r["name"], re.IGNORECASE)
            and not re.search(r"\b(set|with|pack|girls|two-piece|co-ord)\b|&", r["name"], re.IGNORECASE)
            and r["p_id"] not in used
            and r["colour"]
        ]
        for r in eligible[:count]:
            used.add(r["p_id"])
            selected.append(
                {
                    "dataset": "myntra",
                    "source_id": str(int(float(r["p_id"]))),
                    "source_url": r["img"].replace("http://", "https://"),
                    "source_file": "Fashion Dataset.csv: img column",
                    "name": r["name"],
                    "colour": r["colour"],
                    "brand": r["brand"],
                    "department": "women",
                    "category": category,
                    "styles": "everyday",
                    "article_type": category,
                }
            )
    assert len(selected) == 190
    for folder in (ROOT / "fixtures/images", FRONT / "images"):
        folder.mkdir(parents=True, exist_ok=True)
    credits = []

    def asset(row):
        dataset, licence = DATASETS[row["dataset"]]
        name = f"catalog-{row['dataset']}-{row['source_id']}.jpg"
        local = ROOT / "fixtures/images" / name
        if not local.exists():
            if row.get("source_url"):
                # The archive image numbering is not a reliable product ID mapping.
                # Use each CSV row's explicit original image reference instead.
                url = row["source_url"]
                if urlparse(url).scheme != "https" or urlparse(url).hostname != "assets.myntassets.com":
                    raise ValueError("Unexpected dataset image host")
                response = httpx.get(url, timeout=60, follow_redirects=False)
                response.raise_for_status()
                raw = response.content
                if len(raw) > 5_000_000:
                    raise ValueError("Image exceeds download limit")
            else:
                raw = download(dataset, row["source_file"], maximum=5_000_000)
            with Image.open(io.BytesIO(raw)) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                if min(image.size) < 200:
                    raise ValueError("Source image too small for a useful product preview")
                image.thumbnail((900, 1100))
                image.save(local, "JPEG", quality=88, optimize=True)
        (FRONT / "images" / name).write_bytes(local.read_bytes())
        return {
            **row,
            "file": "images/" + name,
            "source": f"https://www.kaggle.com/datasets/{dataset}",
            "author": "Hitesh Suthar (dataset publisher)"
            if row["dataset"] == "myntra"
            else "Param Aggarwal (dataset publisher)",
            "license": licence,
            "license_url": "https://opendatacommons.org/licenses/pddl/1-0/"
            if row["dataset"] == "myntra"
            else "https://opensource.org/license/mit",
            "purpose": "Archived dataset photograph. Prices, sizes and stock are simulated; no current retailer affiliation.",
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, credit in enumerate(pool.map(asset, selected), 1):
            credits.append(credit)
            if i % 20 == 0:
                print(f"Downloaded and validated {i}/190 catalogue images", flush=True)
    prices = {
        "top": 499,
        "bottom": 699,
        "jacket": 1399,
        "dress": 999,
        "shoes": 899,
        "bag": 599,
        "accessory": 299,
    }
    for i, row in enumerate(credits):
        key = f"sample-{row['dataset']}-{row['source_id']}"
        category = row["category"]
        records.append(
            {
                "id": key,
                "sku": key.upper(),
                "name": row["name"][:150],
                "brand": row["brand"],
                "category": category,
                "price": prices[category] + (i % 7) * 100,
                "currency": "INR",
                "image": "/" + row["file"],
                "sample": True,
                "indexed": True,
                "description": f"{row['colour']} {row['article_type']}. Archived dataset photograph for {row['department']} styling. Demonstration price, sizes and stock; not a live retailer offer.",
                "attributes": {
                    "department": row["department"],
                    "colour": row["colour"],
                    "styles": row["styles"],
                    "source_dataset": row["source"],
                    "source_id": row["source_id"],
                    "availability_source": "Simulated sizes and stock; not retailer availability",
                },
                "variants": variants(key, category, row["colour"]),
                "delivery": [],
            }
        )
    from app.models import Product

    records = [Product.model_validate(p).model_dump(mode="json") for p in records]
    (ROOT / "fixtures/catalogue.json").write_text(json.dumps(records, indent=2) + "\n")
    (ROOT / "fixtures/catalogue-sources.json").write_text(json.dumps(credits, indent=2) + "\n")
    for path in (ROOT / "fixtures/image-credits.json", FRONT / "image-credits.json"):
        existing = json.loads(path.read_text()) if path.exists() else []
        existing = [c for c in existing if not c["file"].startswith("images/catalog-")]
        path.write_text(json.dumps(existing + credits, indent=2) + "\n")
    print(
        json.dumps(
            {
                "products": len(records),
                "departments": dict(Counter(p["attributes"]["department"] for p in records)),
                "categories": dict(Counter(p["category"] for p in records)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
