"""Synthetic correctness comparison; no invented human relevance or model quality metrics."""

import json, time, tempfile, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as folder:
    os.environ.update(
        DATA_DIR=folder,
        APP_MODE="demo",
        STORE_BACKEND="sqlite",
        ENABLE_PAID_AI="false",
        MEDIA_BUCKET="",
        WORKER_URL="",
    )
    from app.config import settings

    settings.cache_clear()
    from app.store import store
    from app.services import inventory, recommendations
    from app.models import UserProfile, ChatRequest
    from app.auth import Principal

    owner = "evaluation-only"
    p = Principal(owner, demo=True)
    inventory.seed_catalog(owner)
    inventory.seed_wardrobe(owner)
    for item in store().list("wardrobe", owner):
        item["confirmed"] = True
        store().put("wardrobe", owner, item["id"], item)
    profile = UserProfile(clothing_size="M", shoe_size="39")
    store().put("profiles", owner, "me", profile.model_dump())
    rows = []
    for method, query in [
        ("attribute", "Mumbai work trip under ₹5,000"),
        ("coverage", "Which jacket under ₹5,000 works with the most distinct outfits?"),
    ]:
        started = time.perf_counter()
        result = recommendations.recommend(p, ChatRequest(message=query), {})
        elapsed = (time.perf_counter() - started) * 1000
        outfits = result["outfits"]
        owned = {w["id"] for w in store().list("wardrobe", owner)}
        rows.append(
            {
                "method": method,
                "query": query,
                "outfits": len(outfits),
                "latency_ms": round(elapsed, 2),
                "budget_valid": all(o["total"] <= 5000 for o in outfits),
                "stock_valid": all(p["availability"]["quantity"] > 0 for o in outfits for p in o["products"]),
                "ownership_valid": all(w["id"] in owned for o in outfits for w in o["owned"]),
                "complete_outfits": sum(o["complete"] for o in outfits),
                "top_products": [p["id"] for p in outfits[0]["products"]] if outfits else [],
                "coverage": result.get("coverage", {}),
                "human_relevance": None,
                "human_explanation_rating": None,
            }
        )
    report = {
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": "local synthetic fixtures; no AI calls",
        "results": rows,
        "finding": "Coverage ranking provides counts of assessed combinations. No human usefulness or explanation improvement has been established.",
    }
    out = Path(__file__).resolve().parents[1] / "docs/evaluation-results.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
