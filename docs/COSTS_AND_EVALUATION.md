# Cost controls and evaluation

## Controls shipped

Cloud Run minimum instances 0, maximum instances 2 per service; worker concurrency 1 and Cloud Tasks concurrency 2 / dispatch rate 1 per second. Customer generation is on demand, capped at five new jobs per day and three attempts per job. Public demo account creation is globally capped at 100/day, uploads at 300/day plus per-user limits, and expensive AI is disabled in public demo mode. Analysis copies are at most 1600 px, thumbnails 600 px. Uploads are limited to 10 MB and 30 million decoded pixels. Catalogue hashes avoid unchanged reindex/embedding work. Candidates and query scans are bounded. No GPU, paid external API or minimum-instance capacity was created.

Limits reduce risk; they do not make a billing spending cap. Billing alerts require a chosen billing account and monetary threshold. Optional Terraform budget resources are provided but default to disabled so a threshold is not invented for the shared project. Review shared-project spend separately.

## Estimate worksheet

No paid-model generation cost was measured in the demo. Fill in current regional pricing before publishing numeric estimates:

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
| Latency | Actual timing with mode, model, region and workload | Local synthetic evaluation script records observed elapsed times |
| Unit cost | Provider token/output counts plus Cloud Billing data | Not collected; symbolic worksheet above |

Run `uv run python scripts/evaluate_demo.py` for a repeatable synthetic attribute/graph comparison. The output explicitly distinguishes validation correctness from fashion relevance and records actual timings. A shared top recommendation or tie is not an improvement.
