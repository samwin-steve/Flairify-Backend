"""Gemini Embedding 2 only. Document/query instructions follow Google's retrieval format."""

import hashlib
import json
import math

from google import genai
from google.genai import types

from ..auth import quota
from ..config import settings

TEXT_VERSION = "retail-v1"


def space():
    c = settings()
    return f"{c.embedding_model}:{c.embedding_dimensions}:{TEXT_VERSION}"


def enabled(owner):
    c = settings()
    # Anonymous demo catalogues never consume paid AI; their fallback is explicitly labeled.
    return c.enable_paid_ai and owner == "retailer" and c.store_backend == "firestore"


def document(product):
    facts = {k: product.get(k, "") for k in ("name", "brand", "description", "category", "attributes")}
    facts["colours"] = sorted({v["colour"] for v in product["variants"]})
    # Price and stock are structured filters, not semantic identity. Their edits reuse the vector.
    text = f"title: {product['name']} | text: " + json.dumps(facts, sort_keys=True, ensure_ascii=False)
    # Bound provider input even when seller-supplied attribute maps are verbose.
    return text.encode("utf-8")[:8000].decode("utf-8", errors="ignore")


def digest(text):
    return hashlib.sha256((space() + "\n" + text).encode()).hexdigest()


def embed(text, *, query=False):
    c = settings()
    if c.embedding_model != "gemini-embedding-2":
        raise ValueError("Flairify requires Gemini Embedding 2")
    quota("live-ai", "embedding", c.max_daily_embeddings)
    prompt = f"task: search result | query: {text}" if query else text
    with genai.Client(
        vertexai=True,
        project=c.google_cloud_project,
        location=c.embedding_location,
        http_options=types.HttpOptions(timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)),
    ) as client:
        response = client.models.embed_content(
            model=c.embedding_model,
            contents=prompt,
            # Embedding 2 does NOT accept the legacy task_type parameter.
            config=types.EmbedContentConfig(output_dimensionality=c.embedding_dimensions),
        )
    values = response.embeddings[0].values
    if len(values) != c.embedding_dimensions or not all(math.isfinite(x) for x in values):
        raise ValueError("Invalid embedding returned by Vertex AI")
    norm = math.sqrt(sum(x * x for x in values))
    if not norm:
        raise ValueError("Empty embedding returned by Vertex AI")
    return [x / norm for x in values]
