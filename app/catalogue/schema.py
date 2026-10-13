from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TagField = Literal[
    "category",
    "subcategory",
    "fabric",
    "fit",
    "silhouette",
    "neckline",
    "sleeve_length",
    "pattern",
    "primary_colour",
    "secondary_colour",
    "shade",
    "print",
    "design_detail",
    "occasion",
    "weather",
    "breathability",
    "weight",
    "stretch",
    "layering",
    "style",
    "outfit_template",
    "matching_garment",
    "complementary_colour",
    "footwear",
    "accessory",
    "mix_and_match",
]


class Tag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: TagField
    value: str = Field(min_length=1, max_length=50)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    source: Literal["seller", "visual", "styling_inference"]
    evidence: str = Field(min_length=1, max_length=220)
    source_field: str = Field(default="", max_length=80)


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[Tag] = Field(max_length=70)
    image_quality: Literal["adequate", "limited", "unusable", "not_provided"]
    image_matches_product: bool
    uncertainties: list[str] = Field(default_factory=list, max_length=12)


class ProviderTag(BaseModel):
    """Compact provider schema; the stricter Tag model validates the returned values."""

    field: str
    value: str
    confidence: float
    source: Literal["seller", "visual", "styling_inference"]
    evidence: str
    source_field: str


class ProviderAnalysis(BaseModel):
    # Repeating the full enum and string/array bounds inside an array exceeds the
    # Vertex structured-output complexity budget. Enforce those limits locally.
    tags: list[ProviderTag]
    image_quality: Literal["adequate", "limited", "unusable", "not_provided"]
    image_matches_product: bool
    uncertainties: list[str]


class Enrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["complete", "needs_review", "failed", "unavailable"]
    schema_version: str
    taxonomy_version: str
    prompt_version: str
    model: str
    input_hash: str
    image_hash: str = ""
    input_mode: Literal["image_and_text", "text_only"]
    tags: list[Tag] = Field(default_factory=list, max_length=80)
    unknown_fields: list[str] = Field(default_factory=list)
    validation_issues: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    image_quality: str = "not_provided"
    assessed_at: str
    error: str | None = None
    latency_ms: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
