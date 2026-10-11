"""Read-only ADK tools bound to a verified principal, never a model-supplied user ID."""

import asyncio

from ..models import ChatRequest
from ..services import recommendations
from ..services.inventory import available
from ..store import store


class StylistTools:
    def __init__(self, principal, request: ChatRequest, previous, emit):
        self.principal, self.request, self.previous, self.emit = principal, request, previous, emit
        self.result = None
        self._candidate_lock = asyncio.Lock()

    async def get_confirmed_wardrobe(self) -> dict:
        """Read the current customer's confirmed owned garments."""
        rows = await asyncio.to_thread(recommendations.get_confirmed_wardrobe, self.principal.uid)
        return {
            "garments": [{k: r.get(k) for k in ("id", "name", "category", "colour", "pattern")} for r in rows]
        }

    async def find_outfit_candidates(
        self,
        query: str,
        occasion: str,
        budget: int | None = None,
        relaxed: bool = False,
        cheaper: bool = False,
        another_jacket: bool = False,
        keep_shirt: bool = False,
        jacket_coverage: bool = False,
    ) -> dict:
        """Retrieve semantic catalogue matches, then validate complete outfits against owned clothes, sizes, stock and total budget."""
        async with self._candidate_lock:
            if self.result is None:
                await self.emit("status", {"message": "Finding pieces that work with your wardrobe…"})
                intent = {
                    "query": query[:2000],
                    "occasion": occasion[:150],
                    "budget": budget,
                    "relaxed": relaxed,
                    "cheaper": cheaper,
                    "another_jacket": another_jacket,
                    "keep_shirt": keep_shirt,
                    "jacket_coverage": jacket_coverage,
                }
                self.result = await asyncio.to_thread(
                    recommendations.recommend,
                    self.principal,
                    self.request,
                    self.previous,
                    interpreted=intent,
                )
                await self.emit(
                    "outfits",
                    {
                        "outfits": self.result["outfits"],
                        "retrieval": self.result.get("retrieval"),
                        "method": self.result["method"],
                    },
                )
                await self.emit("status", {"message": "Putting the looks together…"})
        return {
            "graph_evidence": self.result.get("graph", {}),
            "summary": self.result["text"],
            "outfits": [
                {
                    "id": o["id"],
                    "occasion": o["occasion"],
                    "owned": [
                        {k: g.get(k) for k in ("id", "name", "category", "colour")} for g in o["owned"]
                    ],
                    "products": [
                        {k: p.get(k) for k in ("id", "name", "category", "attributes")} for p in o["products"]
                    ],
                    "explanation": o["explanation"],
                    "complete": o["complete"],
                }
                for o in self.result["outfits"]
            ],
        }

    async def get_product_details(self, product_id: str) -> dict:
        """Read a product from this turn's validated shortlist only."""
        products = {p["id"]: p for o in (self.result or {}).get("outfits", []) for p in o["products"]}
        product = products.get(product_id)
        if not product:
            return {"error": "Product is not in the validated shortlist"}
        latest = await asyncio.to_thread(store().get, "products", self.principal.catalog_owner, product_id)
        return (
            {k: latest.get(k) for k in ("id", "name", "category", "attributes", "price")}
            if latest
            else {"error": "Product unavailable"}
        )

    async def check_variant_availability(self, product_id: str) -> dict:
        """Recheck only the selected size and store for a shortlisted product."""
        products = {p["id"]: p for o in (self.result or {}).get("outfits", []) for p in o["products"]}
        product = products.get(product_id)
        if not product:
            return {"error": "Product is not in the validated shortlist"}
        current = await asyncio.to_thread(store().get, "products", self.principal.catalog_owner, product_id)
        return {
            "availability": available(
                current, product["availability"]["size"], product["availability"]["store_id"]
            )
        }
