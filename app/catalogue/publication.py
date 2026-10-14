"""Activate reviewed photo imports with explicit, configurable commerce settings."""

from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Product, now
from . import enrichment


class PublicationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=80)
    currency: str = "INR"
    prices: dict[str, int]
    clothing_sizes: list[str]
    shoe_sizes: list[str]
    store_ids: list[str]
    quantity_per_variant_per_store: int = Field(ge=1, le=1000000)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.currency != "INR" or set(self.prices) != {"top", "bottom", "dress", "jacket", "shoes", "bag"}:
            raise ValueError("Configure INR prices for all six imported categories")
        if any(price <= 0 or price > 10000000 for price in self.prices.values()):
            raise ValueError("Prices must be positive integer INR amounts")
        for values in (self.clothing_sizes, self.shoe_sizes, self.store_ids):
            if not values or len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise ValueError("Sizes and stores must be nonempty and unique")
        return self


def activate(product, policy, requester, known_stores):
    """Return a validated copy. Retries never overwrite a previously published listing.

    Analysis is reused only for this first activation: the photo and all semantic
    fields remain identical, and variant colour repeats the already analysed colour.
    The caller records both fingerprints and the reuse reason in the cache audit.
    """
    attributes = product.get("attributes", {})
    if not attributes.get("source_drive_file_id") or product.get("seller_id") != requester:
        raise ValueError("Only this owner's imported photo listings may be activated")
    if attributes.get("publication_policy"):
        return None
    if (
        product.get("active", True)
        or product.get("variants")
        or product.get("price") != 0
        or attributes.get("catalogue_status") != "draft"
    ):
        raise ValueError("Listing has seller changes; publish it individually in Seller Studio")
    if not enrichment.current(product) or product["enrichment"]["status"] != "complete":
        raise ValueError("Current, successful metadata review is required before publication")
    if not set(policy.store_ids) <= set(known_stores):
        raise ValueError("Policy refers to an unavailable store")
    colour = attributes.get("colour", "").strip()
    if not colour:
        raise ValueError("The imported garment needs a reviewed colour")
    category = product["category"]
    sizes = (
        ["One size"]
        if category == "bag"
        else policy.shoe_sizes
        if category == "shoes"
        else policy.clothing_sizes
    )
    updated = deepcopy(product)
    updated.update(
        price=policy.prices[category],
        currency=policy.currency,
        active=True,
        indexed=False,
        content_hash="",
        updated_at=now(),
        variants=[
            {
                "id": f"{product['id']}-size-{index}",
                "size": size,
                "colour": colour,
                "stock": [
                    {"store_id": sid, "quantity": policy.quantity_per_variant_per_store}
                    for sid in policy.store_ids
                ],
            }
            for index, size in enumerate(sizes)
        ],
    )
    updated["attributes"].pop("catalogue_status", None)
    updated["attributes"].update(
        publication_policy=policy.version,
        commercial_details="owner_configured_payment_free",
        price_source="Owner-configured catalogue price",
        availability_source="Owner-configured sizes and stock for payment-free orders",
    )
    old_facts, new_facts = enrichment.seller_facts(product), enrichment.seller_facts(updated)
    old_facts.pop("variant_colours")
    repeated_colours = new_facts.pop("variant_colours")
    if old_facts != new_facts or repeated_colours != [colour] or updated["image"] != product["image"]:
        raise ValueError("Semantic changes require fresh analysis")
    digest = enrichment.fingerprint(updated)
    updated["enrichment"]["input_hash"] = digest
    updated["ai_attributes"].update(
        metadata_provenance="visual-v1:" + digest,
        metadata_reused_from=product["enrichment"]["input_hash"],
        metadata_reuse_reason="First publication; only price, sizes, stock and repeated known colour changed",
    )
    # Assessment time, confidence, image evidence, usage and tags remain unchanged.
    return Product.model_validate(updated).model_dump(mode="json")
