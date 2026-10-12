# Saved shopping preferences and occasion relevance

## Customer flow

Onboarding saves department, clothing size, EU shoe size, preferred store and budget. Profile can change them. These explicitly saved account settings are separate from optional style/colour memory. Existing accounts with missing sizes are directed to Profile once; chat does not ask size questions. Photos are optional for catalogue shopping. A reference photo and consent are still required for real previews.

**Pair with my wardrobe** defaults off. The per-turn switch overrides the saved Profile default. When off, retrieval does not read owned garments or query wardrobe graph evidence. When on, only confirmed, occasion-appropriate garments compete with catalogue choices; at most two owned pieces can appear in a recommendation. Unsuitable owned pieces are not forced into looks. Unconfirmed extractions never count as ownership.

Checkout prefers the returned recommended variant, otherwise the saved available size/store. It does not silently change a saved size that is unavailable. The customer must review and confirm the mock order; no payment or fulfillment occurs.

## Ranking pipeline

1. Google ADK interprets occasion, dress code, palette and desired garment types using the saved shopping context. A deterministic brief handles important demo cases, typo variants and follow-up continuity.
2. Gemini Embedding 2 / Firestore retrieves bounded category shortlists. Preserve the returned cosine similarity instead of discarding it. Apply current department, size, store, total-budget and stock filters.
3. Exclude obvious contradictory and children's records from adult shopping. Ten source fixtures are currently excluded; records and images remain available for owner correction. This is a limited validation rule, not a comprehensive visual catalogue audit.
4. Construct compatible silhouettes from shortlisted pieces. A request for shirts yields shirts without compulsory jackets, shoes or accessories. Complete outfits use top/bottom/shoes or dress/shoes; layers are added when requested. Office-celebration rules favor a restrained colour accent, neutral supporting pieces and suitable footwear.
5. Rank at most twelve distinct main-garment combinations. A configured Vertex Gemini model returns schema-validated whole-outfit suitability, score and rationale. It can reject options but cannot invent IDs, variants, prices or stock. Reject malformed/unknown-ID responses. Provider/schema failure is recorded as `rules-fallback`, never a successful Gemini assessment.
6. Select up to three different main garments and penalize repeated supporting products and recently shown items. “Different options” excludes prior main garments. Return fewer options when appropriate. Re-read serving inventory and validate the final total/combination before saving.
7. When wardrobe pairing is enabled, prior owner-scoped BigQuery Graph whole-outfit evidence contributes a small bounded score. No graph evidence is claimed for catalogue-only recommendations. Graph coverage is not a replacement for present stock checks or whole-outfit assessment.

The existing ADK/SSE path streams actual model text to the browser; this change does not simulate typing or expose chain of thought. Costs remain bounded by candidate limits, provider timeouts and existing daily quotas.

Implementation: `app/services/styling.py`, `app/services/recommendations.py`, `app/rag/repository.py`, `app/agents/`, `app/prompts/stylist.py`. Official contracts checked: [Firestore vector distances](https://firebase.google.com/docs/firestore/vector-search) and [Vertex structured output](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/generativeaionvertexai-gemini-controlled-generation-response-schema-2).

## Boundaries

Recommendations are hypotheses, not expert styling or fit guarantees. Colour and silhouette checks depend on supplied catalogue facts; photographs may contain additional details. Anonymous demos use deterministic rules. Signed-in requests use Google models when enabled, subject to quota/capacity. The sample catalogue has limited office/ethnic variety; unrelated substitutes should not conceal gaps. Generic heuristics are strongest for covered office/celebration cases and do not establish accuracy across all occasions. Human-rated relevance, model quality uplift and graph ranking uplift have not been measured. See `VERIFICATION.md` for actual collected tests.
