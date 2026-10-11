"""Generate original CC0 demo garment illustrations and synthetic retail facts."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
assets = root / "frontend/public/images"
assets.mkdir(parents=True, exist_ok=True)
shapes = {
    "top": '<path d="M105 64 61 88 28 169 67 187 91 137 85 280 235 280 229 137 253 187 292 169 259 88 215 64 190 87 130 87Z"/><path d="m130 65 30 30 30-30-7-13h-46z" fill="#fcfbf7"/><path d="M160 96v181M92 135l5-34M228 135l-5-34" class="seam"/><path d="m109 72 21 37 30-14 30 14 20-37" class="seam"/><g fill="#a99583"><circle cx="165" cy="124" r="2"/><circle cx="165" cy="154" r="2"/><circle cx="165" cy="184" r="2"/><circle cx="165" cy="214" r="2"/><circle cx="165" cy="244" r="2"/></g>',
    "bottom": '<path d="M92 53h136l17 238h-68l-17-158-17 158H75Z"/><path d="M93 71h134M160 71v59M111 73l-17 36M209 73l17 36M88 276h55M178 276h56" class="seam"/>',
    "jacket": '<path d="m102 59-43 35-34 174 40 12 35-136-13 154h146l-13-154 35 136 40-12-34-174-43-35-26 15h-64Z"/><path d="m124 54 36 83-37 57-14-77 16-14-16-13ZM196 54l-36 83 37 57 14-77-16-14 16-13Z" fill="#bca78f"/><path d="M160 137v157M102 230h36M182 230h36M60 110l12 41M260 110l-12 41" class="seam"/><circle cx="170" cy="232" r="4" fill="#745e49"/>',
    "shoes": '<path d="M44 119q30 25 71-2l28 21q7 44 43 47l71 15q34 13 15 41H50q-21-39-6-122Z"/><path d="M42 228h233l-4 20H48z" fill="#faf8f1"/><path d="m114 135 34 11m-26 1 33 11m-24 1 34 11m-122 49h227" class="seam"/><path d="m63 151 22 9 34-7" fill="none" stroke="#ad947c" stroke-width="9"/>',
    "bag": '<rect x="68" y="121" width="184" height="169" rx="14"/><path d="M113 142V87c0-66 94-66 94 0v55" fill="none" stroke="currentColor" stroke-width="15"/><path d="M87 141v127h146V141M92 189h134" class="seam"/>',
    "dress": '<path d="m124 52-22 49 28 62-52 132h164l-52-132 28-62-22-49-36 28Z"/><path d="M130 163h60M145 172l-29 99M175 172l29 99" class="seam"/>',
    "accessory": '<path d="M83 53h67l13 187 39-10 35 57-89 14-36-47Z"/><path d="m86 71 66 36m-61 1 64 36m-59 1 61 36m-55 1 58 36" class="seam"/>',
}
items = [
    ("shirt", "top", "#f9f6ed"),
    ("trousers", "bottom", "#49443f"),
    ("jeans", "bottom", "#8da3b1"),
    ("tee", "top", "#d1b5a4"),
    ("blazer", "jacket", "#cdbb9f"),
    ("jacket", "jacket", "#959f8b"),
    ("sneakers", "shoes", "#e5e0d4"),
    ("loafers", "shoes", "#7e604c"),
    ("tote", "bag", "#926e52"),
    ("dress", "dress", "#b65a70"),
    ("scarf", "accessory", "#dca1a7"),
]
for name, cat, color in items:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 340"><defs><filter id="s"><feDropShadow dx="0" dy="9" stdDeviation="7" flood-color="#50372a" flood-opacity=".13"/></filter><linearGradient id="f" x1="0" x2="1" y2="1"><stop stop-color="{color}"/><stop offset="1" stop-color="{color}" stop-opacity=".83"/></linearGradient></defs><style>.seam{{fill:none;stroke:#665549;stroke-opacity:.28;stroke-width:1.5}}</style><ellipse cx="160" cy="308" rx="95" ry="9" fill="#b8a797" opacity=".12"/><g fill="url(#f)" color="{color}" stroke="#655449" stroke-opacity=".17" stroke-width="1.2" filter="url(#s)">{shapes[cat]}</g></svg>'
    (assets / f"{name}.svg").write_text(svg)
fixtures = root / "backend/fixtures"
stores = [
    dict(
        id="bandra",
        name="Flairify Studio · Bandra",
        address="Sample store · Linking Road, Mumbai",
        latitude=19.0596,
        longitude=72.8295,
        sample=True,
    ),
    dict(
        id="lower-parel",
        name="Flairify Studio · Lower Parel",
        address="Sample store · Senapati Bapat Marg, Mumbai",
        latitude=18.9943,
        longitude=72.8252,
        sample=True,
    ),
]
products = []
for i, (id, name, cat, price, color, styles) in enumerate(
    [
        ("p-blazer", "The everyday linen blazer", "jacket", 2490, "Oat", "work minimal tailored"),
        ("p-jacket", "The relaxed overshirt", "jacket", 1790, "Sage", "relaxed casual travel"),
        ("p-sneakers", "Everyday walking sneakers", "shoes", 1890, "Cream", "walking comfort travel"),
        ("p-loafers", "Soft step loafers", "shoes", 2290, "Cocoa", "work classic"),
        ("p-tote", "The carry-everywhere tote", "bag", 1290, "Tan", "work travel"),
        ("p-shirt", "A fresh white shirt", "top", 1490, "White", "work minimal"),
        ("p-trousers", "Easy tailored trousers", "bottom", 1990, "Charcoal", "work tailored"),
        ("p-dress", "The weekend midi dress", "dress", 2690, "Rose", "relaxed weekend"),
        ("p-scarf", "A little colour scarf", "accessory", 690, "Blush", "classic colourful"),
        ("p-soldout", "Limited sample jacket (unavailable)", "jacket", 990, "Oat", "work"),
    ]
):
    image = id.removeprefix("p-") if id != "p-soldout" else "blazer"
    sizes = (
        ["37", "38", "39", "40", "41", "42", "43"]
        if cat == "shoes"
        else (["One size"] if cat in ["bag", "accessory"] else ["XS", "S", "M", "L", "XL"])
    )
    variants = [
        dict(
            id=f"{id}-{s.replace(' ', '-')}",
            size=s,
            colour=color,
            stock=[
                dict(
                    store_id=st["id"],
                    quantity=0 if id == "p-soldout" else (3 if j == 0 else 2),
                    aisle=f"{'B' if cat == 'shoes' else 'A'}{i + 1}",
                    rack="02",
                )
                for j, st in enumerate(stores)
            ],
        )
        for s in sizes
    ]
    products.append(
        dict(
            id=id,
            sku=f"FL-{100 + i}",
            name=name,
            brand="Flairify sample label",
            description=f"Synthetic catalogue item. {styles}. Product image is an original illustration.",
            category=cat,
            price=price,
            image=f"/images/{image}.svg",
            variants=variants,
            attributes={"styles": styles, "colour": color},
            delivery=["Home delivery eligible; timing confirmed by retailer"] if i % 2 == 0 else [],
            sample=True,
            indexed=True,
            updated_at="2026-10-11T00:00:00+00:00",
        )
    )
wardrobe = [
    dict(id="w-shirt", name="My white shirt", category="top", colour="White", image="/images/shirt.svg"),
    dict(
        id="w-trousers",
        name="Tailored charcoal trousers",
        category="bottom",
        colour="Charcoal",
        image="/images/trousers.svg",
    ),
    dict(
        id="w-jeans",
        name="Straight-leg blue jeans",
        category="bottom",
        colour="Blue",
        image="/images/jeans.svg",
    ),
    dict(id="w-tee", name="A favourite neutral tee", category="top", colour="Sand", image="/images/tee.svg"),
]
for w in wardrobe:
    w.update(
        sample=True,
        evidence="sample",
        confirmed=False,
        uncertainty=["Sample garment, not inferred from your photos"],
    )
for name, data in [("catalogue", products), ("stores", stores), ("wardrobe", wardrobe)]:
    (fixtures / f"{name}.json").write_text(json.dumps(data, indent=2))
