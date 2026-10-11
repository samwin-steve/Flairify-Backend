from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def uid():
    return uuid4().hex


def now():
    return datetime.now(UTC).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentSettings(Model):
    remember_preferences: bool = False
    ai_photo_processing: bool = False


class UserProfile(Model):
    name: str = Field(default="Friend", max_length=80)
    styles: list[str] = Field(default_factory=list, max_length=10)
    colours: list[str] = Field(default_factory=list, max_length=10)
    clothing_size: str = Field(default="", max_length=20)
    shoe_size: str = Field(default="", max_length=20)
    fit: str = Field(default="Comfortable", max_length=40)
    budget: int = Field(default=5000, ge=0, le=1000000)
    consent: ConsentSettings = Field(default_factory=ConsentSettings)
    onboarding_complete: bool = False


class Box(Model):
    x: float = Field(default=0, ge=0, lt=1)
    y: float = Field(default=0, ge=0, lt=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(default=1, gt=0, le=1)

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.width > 1.001 or self.y + self.height > 1.001:
            raise ValueError("Selection must be inside the photo")
        return self


class PhotoSource(Model):
    id: str = Field(default_factory=uid)
    media_id: str
    original_media_id: str | None = None
    source: Literal["upload", "google_photos", "sample"] = "upload"
    captured_at: str | None = None
    person_box: Box = Field(default_factory=Box)
    group_photo: bool = False
    created_at: str = Field(default_factory=now)


class ReferencePhoto(Model):
    id: str
    kind: Literal["portrait", "full_body"]
    media_id: str
    source_photo_id: str | None = None
    created_at: str = Field(default_factory=now)


Category = Literal["top", "bottom", "dress", "jacket", "shoes", "bag", "accessory", "unknown"]


class WardrobeItem(Model):
    id: str = Field(default_factory=uid)
    name: str = Field(max_length=100)
    category: Category = "unknown"
    colour: str = Field(default="Unknown", max_length=50)
    pattern: str = Field(default="Unknown", max_length=80)
    details: str = Field(default="", max_length=500)
    brand: str | None = None
    material: str | None = None
    size: str | None = None
    image: str = ""
    source_photo_id: str | None = None
    box: Box | None = None
    uncertainty: list[str] = Field(default_factory=list)
    confirmed: bool = False
    sample: bool = False
    evidence: Literal["original_crop", "manual", "sample", "generated_cleanup"] = "manual"
    created_at: str = Field(default_factory=now)


class DuplicateCandidate(Model):
    id: str = Field(default_factory=uid)
    item_ids: list[str]
    score: float = Field(ge=0, le=1)
    reason: str
    method: str
    status: Literal["pending", "merged", "separate"] = "pending"


class StockRecord(Model):
    store_id: str
    quantity: int = Field(ge=0, le=1000000)
    aisle: str | None = None
    rack: str | None = None


class ProductVariant(Model):
    id: str = Field(max_length=100, pattern=r"^[\w-]+$")
    size: str = Field(max_length=20)
    colour: str = Field(max_length=60)
    stock: list[StockRecord] = Field(default_factory=list, max_length=100)


class Product(Model):
    id: str = Field(pattern=r"^[\w-]+$", max_length=100)
    sku: str = Field(max_length=100)
    name: str = Field(min_length=1, max_length=150)
    brand: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    category: Category
    price: int = Field(ge=0, le=10000000, description="Integer INR rupees")
    currency: Literal["INR"] = "INR"
    image: str = ""
    variants: list[ProductVariant] = Field(default_factory=list, max_length=50)
    attributes: dict[str, str] = Field(default_factory=dict)
    ai_attributes: dict[str, str] = Field(default_factory=dict)
    product_url: str | None = None
    delivery: list[str] = Field(default_factory=list, max_length=10)
    sample: bool = False
    indexed: bool = False
    updated_at: str = Field(default_factory=now)
    content_hash: str = ""
    seller_id: str | None = None
    active: bool = True

    @model_validator(mode="after")
    def unique_variants(self):
        if len({v.id for v in self.variants}) != len(self.variants):
            raise ValueError("Variant IDs must be unique")
        if any(len({s.store_id for s in v.stock}) != len(v.stock) for v in self.variants):
            raise ValueError("Each variant can have only one stock record per store")
        return self

    @field_validator("image")
    @classmethod
    def local_images(cls, v):
        if v and not (v.startswith("/images/") or v.startswith("media:")):
            raise ValueError("Upload product images first; arbitrary remote image URLs are not accepted")
        if ".." in v:
            raise ValueError("Invalid image path")
        return v

    @field_validator("product_url")
    @classmethod
    def safe_link(cls, v):
        if v and not v.startswith("https://"):
            raise ValueError("Product URL must use https")
        return v


class Store(Model):
    id: str = Field(pattern=r"^[\w-]+$", max_length=100)
    name: str = Field(max_length=150)
    address: str = Field(max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sample: bool = False
    seller_id: str | None = None


class CompatibilityAssessment(Model):
    id: str = Field(default_factory=uid)
    garment_ids: list[str]
    product_ids: list[str]
    outfit_id: str
    occasion: str
    score: float = Field(ge=0, le=1)
    reason: str
    source: Literal["rule", "gemini", "user"] = "rule"
    version: str = "capsule-rules-v1"
    assessed_at: str = Field(default_factory=now)
    feedback: Literal["useful", "not_useful"] | None = None


class Outfit(Model):
    id: str = Field(default_factory=uid)
    title: str
    occasion: str
    owned: list[WardrobeItem]
    products: list[dict]
    total: int
    explanation: str
    complete: bool
    sample: bool
    assessment: CompatibilityAssessment | None = None


class Message(Model):
    id: str = Field(default_factory=uid)
    role: Literal["user", "assistant"]
    content: str
    created_at: str = Field(default_factory=now)
    outfits: list[dict] = Field(default_factory=list)


class Conversation(Model):
    id: str = Field(default_factory=uid)
    title: str = "A little outfit inspiration"
    messages: list[Message] = Field(default_factory=list)
    intent: dict = Field(default_factory=dict)
    updated_at: str = Field(default_factory=now)


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class GenerationJob(Model):
    id: str = Field(default_factory=uid)
    kind: Literal["wardrobe", "index", "try_on", "video", "avatar"]
    status: JobStatus = JobStatus.queued
    stage: str = "Queued"
    payload: dict = Field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    attempts: int = 0
    operation: str | None = None
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    lease_until: float = 0


class SavedLook(Model):
    id: str
    outfit: dict
    created_at: str = Field(default_factory=now)


class ChatRequest(Model):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    store_id: str | None = None
    clothing_size: str | None = None
    shoe_size: str | None = None
    budget: int | None = Field(default=None, ge=0, le=1000000)


class ImportRequest(Model):
    photo_ids: list[str] = Field(min_length=1, max_length=12)


class GenerationRequest(Model):
    outfit_id: str | None = None
    reference_id: str | None = None
    product_id: str | None = None
    variant_id: str | None = None
    source_job_id: str | None = None
    duration: Literal[4, 6, 8] = 4
    layering: bool = True
    accepted_preview: bool = False
    request_key: str = Field(min_length=8, max_length=100)


class OrderLineRequest(Model):
    product_id: str = Field(min_length=1, max_length=100)
    variant_id: str = Field(min_length=1, max_length=100)
    store_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=10, strict=True)


class OrderQuoteRequest(Model):
    items: list[OrderLineRequest] = Field(min_length=1, max_length=20)
    source: Literal["inventory", "stylist"] = "inventory"
    outfit_id: str | None = None


class PlaceOrderRequest(OrderQuoteRequest):
    request_key: str = Field(min_length=8, max_length=100)
    expected_total: int = Field(ge=0, le=2000000000, strict=True)
    acknowledge_mock: Literal[True]
