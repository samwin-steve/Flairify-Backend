# Catalogue enrichment verification — 14 October 2026

## Existing catalogue backfill

The two durable backfill jobs completed successfully against the deployed Google Cloud
services. All **200 existing products** have current schema-v1 metadata and regenerated,
normalized **768-dimensional Gemini Embedding 2** vectors. Comparing the original records
confirmed that all 200 seller records were unchanged apart from derived metadata and
index markers. Current prices and availability facets match the serving records.

Gemini `gemini-3.8-flash` analyzed 195 product photographs. Five products had no usable
permitted photograph and received text-only analysis. There are **4,708 validated tags**;
199 records are complete and one needs review: the original sunglasses listing
`sample-fashion-40009` is incorrectly categorized as a top. That mismatch was preserved
and flagged, not silently corrected. Existing quality checks exclude that item from
clothing recommendations.

Unsupported physical claims, unknown vocabulary, unverifiable quotes and conflicting
tags were rejected. Fabric, breathability, weight and stretch require seller evidence.
Confidence values are model estimates, not calibrated probabilities or measured accuracy.

Observed analysis latency was 13.64 seconds mean, 13.36 seconds median and 17.22 seconds
p95. These timings include individual analysis work, not total onboarding or queue time.
Successful stored analyses used 645,711 input tokens and 352,031 output tokens. Failed
preflight requests and retries are not included; these counts are not a billing estimate.

See [the collected audit](catalogue-enrichment-audit.json).

## Incremental update verification

A temporary signed-in owner uploaded a product photograph through the deployed API.
Creating the listing automatically produced image metadata and a searchable vector.
Changing only price and stock reused the exact analysis and vector while refreshing
current filters. Changing its description reran analysis and regenerated its embedding.
The listing then appeared in semantic search. The temporary account, product, media,
search entry and analysis cache were removed.

See [incremental results](catalogue-enrichment-incremental-results.json).

## Live streamed conversation checks

A temporary Firebase user called the deployed SSE endpoint with saved sizes, store and
budget. No provider responses were simulated. Google ADK, Vertex Gemini, Gemini Embedding
2 and Firestore produced the results below; current serving records validated product IDs,
prices, total cost, size and positive stock for every card.

| Request | Look totals (INR) | Text events | Complete response (seconds) |
| --- | --- | --- | --- |
| Independence Day office kurta and flats | 2,597 | 5 | 28.82 |
| Keep those clothes, change the flats | 2,397 / 2,697 / 2,897 | 5 | 18.26 |
| Evening wedding guest | 2,797 / 2,498 / 2,398 | 4 | 18.00 |
| Three-day Mumbai work trip with walking | 2,997 / 3,697 | 6 | 13.40 |

The second request preserved every non-shoe product ID and excluded the previous shoe.
No look exceeded INR 5,000, included an unconfirmed owned garment or serialized the full
metadata audit into its conversation card. All 102 temporary user records and the
Firebase account were removed. See [conversation results](catalogue-enrichment-chat-results.json).

Three before/after retrieval observations are included in the audit. They are not a
human-rated relevance benchmark. No numerical improvement in recommendation usefulness,
garment recognition, duplicate accuracy or graph-assisted uplift is claimed.

## Automated verification

194 backend tests passed in Cloud Build after adding import evidence validation, private draft media,
commercial-field publication checks and generated-metadata provenance. Frontend type checking passed. Earlier in this
change, 28 frontend logic tests, a production build and 10 desktop/mobile Playwright
journeys passed, including catalogue metadata, commerce and conversational refinement.
Metadata UI checks found no horizontal overflow at 393px and 1440px and no violations
in the tested Axe rules. Browser provider responses in the metadata UI test were
simulated; the incremental API and SSE checks above used real Google services.

## Deployment

Successful Cloud Builds `b20455e9-0417-47d3-b268-101cff0ca2ed` (backend source `9b1ee25`) and `7360e1a3-c2db-40eb-a988-52490a20c6c0` (frontend source `02e0d41`) deployed the import/privacy changes. Verified ready revisions receiving 100% traffic: `flairify-api-00031-lvl`, `flairify-worker-00062-9nn` and `flairify-web-00027-fr8`. The four live SSE checks ran the previously deployed enrichment/ranking code before the draft-only privacy change.

The final provenance/title validation patch (source `3cd1f26`) passed all **194 backend tests** in successful build `0869776f-de54-4ce5-b644-197bc4289d51`. API `flairify-api-00033-lf8` and worker `flairify-worker-00066-gcx` were verified at 100% traffic on that exact build image. Frontend remains `flairify-web-00027-fr8`.

The final caption-normalization build `dc80de48-3be1-4f0d-9a89-a3a9a2068d5c` (source `03ceee9`) passed **197 backend tests**. The previous image-query build `92cc783b-6812-44c5-8422-48d329565c45` (source `d2aff3a`) deployed successfully; the real customer/owner access and health checks were repeated on that release and passed.

Final deployment completed successfully. API `flairify-api-00035-l4x` and worker `flairify-worker-00070-rf5` receive 100% traffic on build `dc80de48-3be1-4f0d-9a89-a3a9a2068d5c` (source `03ceee9`). Both repositories were pushed and their worktrees were clean after saving this verification.
