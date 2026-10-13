# Catalogue metadata enrichment

Product imports and every Seller Studio create/edit enqueue the existing private Cloud Tasks index job. The worker analyzes the listing and its product photograph with the configured Vertex AI `GEMINI_MODEL`, validates structured output, saves a versioned enrichment record, then embeds the enriched search document with **Gemini Embedding 2**. Firestore stores both authoritative products and vector projections. No external model or image-fetch service is used.

## Evidence and schema

Seller fields are never rewritten by enrichment. `Product.enrichment` is server-owned; seller-submitted enrichment is discarded. The record contains `status`, schema/taxonomy/prompt versions, model, input hash, image hash, input mode, assessment time, measured latency, provider token usage, accepted tags, unknown fields, validation issues and uncertainty notes. Validated historical outputs are cached in owner-scoped `flairify_catalogue_analysis` records.

Each tag has a machine-readable `field` and `value`, confidence from 0 to 1, source (`seller`, `visual`, `styling_inference`), evidence and optional seller source field. The controlled vocabulary is in `app/catalogue/taxonomy.py`; typed schemas are in `app/catalogue/schema.py`. It covers product construction, visual attributes, occasion, weather, comfort properties, aesthetics, outfit templates and styling complements. Multiple tags are allowed where useful. Single-value construction fields and broad occasion/style groups have explicit limits.

- Fabric, stretch, breathability and weight require an explicit seller statement with a matching quote and value. A visible texture does not establish composition or performance. Negated, imitation and "looks like" material statements cannot become verified material tags.
- Image observations require an available, usable product photograph. Other clothing worn by a model is not part of the listing. Product/image conflicts are flagged for review and image-based tags are excluded.
- Non-photographic or absent bundled assets receive text-only analysis, clearly recorded as such. Uploaded image fetch/validation failures are reported and retried; they are not replaced with fabricated photo analysis.
- Styling and weather suitability are hypotheses. They do not guarantee exact fit, comfort or complete-outfit compatibility. Confidence is a model estimate, **not a calibrated accuracy measurement**.
- Tags below 0.65 remain available to the seller for review but are omitted from search. Unsupported fields remain explicitly unknown. A missing tag does not assert that a property is false.
- The provider receives a compact structured schema to stay within Vertex's schema-complexity limits. Its output then passes the stricter Pydantic schema and taxonomy/evidence validators before publication.

Seller Studio offers **Styling details**, source evidence and confidence, unknown fields, validation notes, per-listing retry after failure, and **Refresh search details** for bulk processing. Detailed metadata is fetched on demand through an owner/seller-authorized endpoint instead of adding it to every inventory card response.

## Search and recommendation behavior

Search documents contain relevant seller fashion facts and high-confidence metadata. Dataset IDs, source URLs, stock-provenance strings and known fixture boilerplate are excluded from embedding input; the original records retain them. Price, size, department and stock remain independent structured filters, rechecked against current product records.

Category-specific queries include contextual occasion/template cues. Bounded reranking rewards relevant occasion, template, style and weather tags; tag count cannot inflate the score. Pairing hypotheses provide a small tie-breaker, followed by whole-outfit rule checks and Gemini assessment with the validated metadata. Suggested matching garments are not treated as garments included in the product. The same retrieval services serve typed and voice conversations.

Existing vectors stay available during backfill. The embedding model/dimensions/space remain compatible; a new document content hash forces replacement when metadata changes. Publishing checks both the seller facts and current metadata to prevent an outdated vector overwriting a newer listing. Online retrieval still uses bounded vector queries and point reads, never a full catalogue scan.

## Incremental processing and recovery

The fingerprint covers semantic seller facts, immutable image ID/path, model and metadata versions. Price, size and stock-only edits reuse AI metadata and embeddings while updating live filters. Changed text, appearance attributes or photos cause new analysis. Duplicate requests share a leased, versioned cache. Concurrent seller edits are detected before publication. Bundled asset replacements must use a new filename; uploaded images already have immutable IDs.

The worker handles two listings concurrently, checkpoints completed listings, retries only failed listings up to three attempts, and continues past individual failures. A partly failed job reports exact failed product IDs instead of claiming full success. Cancelled jobs stop scheduling further batches; an already running analysis can finish caching safe product metadata. Cloud Run remains at two maximum instances, so at most four catalogue analyses run across the worker fleet. Photos are resized to at most 900px. Provider calls time out at 50 seconds, embedding calls at 20 seconds; job leases last 180 seconds.

`ENABLE_CATALOGUE_ENRICHMENT=true` and `ENABLE_PAID_AI=true` activate the pipeline for the shared retailer catalogue. `MAX_DAILY_CATALOGUE_ENRICHMENTS=600` and `MAX_DAILY_EMBEDDINGS=1500` bound provider calls. Anonymous local/guest fixtures do not consume paid AI or pretend analysis was performed. Failed analysis is visible and retryable; no successful metadata is fabricated.

## Bulk backfill and future migrations

Use the existing Cloud Run worker configuration with ADC/runtime identity (no downloaded service-account key):

```sh
# Read-only inventory/version report by default.
python -m scripts.enrich_catalogue
# Queue bounded jobs under a configured site owner so they appear in Seller Studio activity.
python -m scripts.enrich_catalogue --enqueue --requester OWNER_FIREBASE_UID --batch-size 100
# Selected listing repair.
python -m scripts.enrich_catalogue --enqueue --requester OWNER_FIREBASE_UID --product-id PRODUCT_ID
```

The script prints a run ID and job IDs. If enqueueing returns an uncertain result, repeat with the same `--run-id` to recover idempotent jobs. Re-running a completed backfill under a new run ID reuses unchanged metadata/vectors. The protected `/api/admin/reindex` action provides the same enrichment-and-index flow for each seller's authorized products. `/api/admin/products/{id}/reindex` retries one authorized listing.

For future changes, update the relevant schema, taxonomy or prompt version constant, keep readers compatible with stored prior versions, run validation tests, deploy the worker/API, then backfill. Old evidence remains in the versioned cache, original seller facts remain intact, and stale tags are excluded from reranking until refreshed. A future change in embedding model/dimensions requires a separate vector-space/index migration, not just a metadata version bump.

## Verification boundaries

Automated tests cover evidence validation, confidence/taxonomy bounds, contradictory tags, no-image handling, unchanged reuse, schema invalidation, concurrent edits, failed provider responses, seller authorization, vector refresh, stock-only reuse, contextual ranking and partial-job recovery. Live backfill and search observations are recorded separately in `CATALOGUE_ENRICHMENT_RESULTS.md` once collected. No relevance accuracy, comfort accuracy or calibrated confidence is claimed without a labeled evaluation.

Official references: [Vertex structured output](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output), [image understanding](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/image-understanding), [Google Gen AI structured-output example](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/generativeaionvertexai-gemini-controlled-generation-response-schema-2).
