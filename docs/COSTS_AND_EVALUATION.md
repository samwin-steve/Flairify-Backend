# Cost controls and evaluation

## Controls shipped

Cloud Run minimum instances 0, maximum instances 2 per service; worker concurrency 1 and Cloud Tasks concurrency 2 / dispatch rate 1 per second. Customer generation is on demand, capped at five new jobs per day and three attempts per job. Public demo account creation is globally capped at 100/day, uploads at 300/day plus per-user limits, and anonymous sessions cannot call paid models; signed-in live analysis is globally capped at 30 photos/day and 50 chat requests/day. Gemini image editing has a separate shared 30-image/day quota. Analysis copies are at most 1600 px, thumbnails 600 px. Uploads are limited to 10 MB and 30 million decoded pixels. Catalogue hashes avoid unchanged reindex/embedding work. Candidates and query scans are bounded. No GPU, paid external API or minimum-instance capacity was created.

Limits reduce risk; they do not make a billing spending cap. Billing alerts require a chosen billing account and monetary threshold. Optional Terraform budget resources are provided but default to disabled so a threshold is not invented for the shared project. Review shared-project spend separately.

## Estimate worksheet

No billed per-user unit cost has been measured. The illustrative estimate below uses published prices and explicit assumptions; collect provider usage and billing data before treating it as a measured cost:

- Onboarding = selected photos × (Gemini input-image + output-token cost) + CPU processing seconds + Storage bytes/month + Firestore operations.
- Indexing = changed products × (visual analysis + embedding tokens) + BigQuery scan bytes + write operations.
- Try-on = requested output images × selected model's image price + worker time + storage.
- Motion = accepted previews × requested seconds × selected Veo output price + polling/storage.
- Use actual billed currency/conversion, model, region, output resolution, duration and measured token counts. Keep original inputs as assumptions, not results.

Primary pricing sources: [Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/pricing), [Cloud Run](https://cloud.google.com/run/pricing), [Firestore](https://cloud.google.com/firestore/pricing), [Storage](https://cloud.google.com/storage/pricing), [BigQuery](https://cloud.google.com/bigquery/pricing), [Cloud Tasks](https://cloud.google.com/tasks/pricing).

## Evaluation plan and current limits

| Dimension | Required evidence | Current prototype evidence |
| --- | --- | --- |
| Garment detection | Hand-labeled consented photo set; per-category precision/recall and box IoU | Not collected; manual demo is not detection |
| Duplicates | Labeled same/different garment pairs; false merge and missed duplicate rates | Exact-hash candidates only; no similarity claims |
| Recommendations | Blinded user ratings for usefulness and explanations, baseline vs graph-assisted | Synthetic checks only; no human usefulness lift claimed |
| Budget, stock and ownership | Exact server assertions against fixtures and changed stock | Automated tests cover totals, variants, unavailable items and owner IDs |
| Preview preservation | Consenting users rate likeness, visible garment details and proportions | Not collected; customer acceptance required |
| Video consistency | Frame-by-frame face/garment/proportion review and rejection rate | Not collected |
| Latency | Actual timing with mode, model, region and workload | Local synthetic timings plus one deployed upload/analysis observation (10.67s) and one signed-in chat (7.41s), plus a live browser upload/extraction (8.84s) and 2D preview (14.52s); see VERIFICATION.md |
| Unit cost | Provider token/output counts plus Cloud Billing data | Not collected; symbolic worksheet above |

Run `uv run python scripts/evaluate_demo.py` for a repeatable synthetic attribute/graph comparison. The output explicitly distinguishes validation correctness from fashion relevance and records actual timings. A shared top recommendation or tie is not an improvement.

## Illustrative model-cost estimate (not a measured bill)

Pricing checked 11 October 2026 in the [official pricing table](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing). Using conservative standard global Gemini 3.8 Flash rates of $1.50/M input and $7.50/M output tokens (excluding temporary credits), **three photos**, each assumed to use 2,000 input and 1,000 total output/reasoning tokens, cost approximately **$0.0315 for model analysis**. These token counts are assumptions, not measurements. The current promotional effective rates would halve that component through December 2026, subject to eligibility.

One virtual-try-on output is listed at **$0.06**. One Gemini 3.1 Flash Image 1K output is approximately **$0.067**, plus image/text inputs and any text output. These are alternative routes, not a promise that both are called. Gemini 3.1 Flash Image was exercised in global with a 1K output; Google VTO still needs project-specific validation. Veo cost depends on selected output/audio/SKU; confirm its billing unit before converting a four-second clip into a numeric estimate.

At request-based Cloud Run list rates, 30 assumed active worker seconds at 1 vCPU / 1 GiB add about **$0.000795** before free-tier effects. Thus this three-photo onboarding scenario is roughly **$0.0323 plus Firestore, storage, API/frontend processing and egress**. Actual latency/tokens, retries, image dimensions, INR billing SKUs, taxes and regional pricing change the result; this is not a spending cap or an INR exchange-rate quote. [Cloud Run rates](https://cloud.google.com/run/pricing).
