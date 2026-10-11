# Integration setup and evidence

Official API references were checked on 11 October 2026. Model availability varies by region, account and project. Environment variables have no guessed default model IDs. Provider adapters are implemented, but must pass a project-specific smoke test before being described as live.

## Local mode

Copy `.env.example` to `.env`; leave `APP_MODE=demo`, `STORE_BACKEND=sqlite`, and `ENABLE_PAID_AI=false`. Set a private `DEMO_ADMIN_KEY` if you need the protected demo inventory workspace. Run `uv sync --locked`, then `uv run uvicorn app.main:app --reload --port 8000`.

## Firebase Authentication

1. Register a web app in your Firebase project; enable Google and email/password sign-in.
2. Add the deployed frontend domain and localhost to authorized domains.
3. Set the frontend **server runtime** `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, and `FIREBASE_APP_ID`. These are public Firebase configuration identifiers, not service-account secrets.
4. Set backend `APP_MODE=production`, Firestore, bucket, project and service identity. Do not turn on production with local SQLite.
5. Grant the retailer administrator the `admin: true` custom claim from a trusted administrative environment. Never expose a claim-setting endpoint to the browser.
6. For local production testing use `gcloud auth application-default login` or Firebase Auth Emulator (`FIREBASE_AUTH_EMULATOR_HOST` on the backend plus an explicitly configured emulator client). The browser emulator connection is not enabled by default.

[Firebase token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens) and [custom claims](https://firebase.google.com/docs/auth/admin/custom-claims).

## Google Photos Picker

Enable the Picker API. Create an OAuth web client with the frontend JavaScript origins. Configure its consent screen and test users, and set `GOOGLE_PHOTOS_CLIENT_ID` on the backend. This client ID is public. The UI requests `https://www.googleapis.com/auth/photospicker.mediaitems.readonly` through Google Identity Services only when the customer chooses Photos.

The app creates a session, opens the returned picker URI, follows `pollInterval` / `timeoutIn`, lists all selected-media pages, and downloads authenticated media bytes. It checks the HTTPS Google content host, disallows redirects, bounds file sizes, and gets fresh base URLs on retry. Tokens remain in browser memory and transient request headers; they are not stored in Firestore or localStorage. Completed or cancelled sessions are deleted. Direct uploads remain available. Browser pop-up controls may require retry. No full-library search or face-group access is implemented.

[Sessions](https://developers.google.com/photos/picker/guides/sessions), [media pagination and authenticated base URLs](https://developers.google.com/photos/picker/guides/media-items).

## Vertex AI

Runtime identities use Application Default Credentials. Grant only `roles/aiplatform.user` to API/worker when turning paid features on. Configure `ENABLE_PAID_AI=true` only with authenticated production accounts and quotas; anonymous public demos keep paid generation off.

- `GEMINI_MODEL`: structured photo extraction, intent and bounded read-only tool-assisted outfit assessment.
- `EMBEDDING_MODEL`: searchable catalogue description embeddings (768 dimensions). Existing content hashes avoid unchanged calls.
- `TRY_ON_MODEL`: the official model catalogue documents `virtual-try-on-001`; the adapter uses `models.recontext_image`, one person and one verified product image. It intentionally accepts only a conservative clothing category subset. No arbitrary layering claim.
- `IMAGE_EDIT_MODEL=gemini-3.1-flash-image`, `IMAGE_EDIT_LOCATION=global`: Google-only 2D editing uses the customer reference plus selected owned and catalogue garment images, and an optional portrait for identity. Each source is labeled by clothing slot. Multi-piece layering, footwear, background and identity preservation are evaluation targets, not guarantees. The source photo remains unchanged. `ALLOW_SAMPLE_TRY_ON=true` permits only the bundled, allowlisted licensed catalogue photos as illustrative previews. Set it false for a retailer deployment. `MAX_DAILY_IMAGE_GENERATIONS=30` is the shared image quota; each account has a separate five-per-day generation limit.
- `VEO_MODEL`: official documentation currently demonstrates `veo-3.1-generate-001`. Adapter uses the Gen AI SDK's `GenerateVideosSource`, private Cloud Storage output and resumable operations. Four, six or eight seconds are allowed by the UI/schema, and must match the selected model's supported durations.

`GEMINI_LOCATION` overrides the Gemini text/analysis endpoint independently of regional Cloud Tasks and image/video providers. `IMAGE_EDIT_LOCATION` configures Gemini image editing separately. VTO/video use `GOOGLE_CLOUD_LOCATION`; split workers if their region requirements differ. Never route to paid endpoints outside GCP.

[Google Gen AI SDK](https://github.com/googleapis/python-genai), [Gemini 3.8 Flash](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash), [Google virtual try-on](https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-virtual-try-on-images), [image generation](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/image-generation), [image-to-video](https://cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-an-image).

## Inventory and BigQuery

Import CSV or JSON through the protected workspace. Variant lists, stock and attributes in CSV cells use JSON. Upload images through the admin image endpoint; unrestricted URL fetching is intentionally rejected. Every stock record must name an existing store. Sample fixtures span ten products and two explicitly synthetic Mumbai locations.

Run `bq query --use_legacy_sql=false --location=us-central1 < infra/bigquery.sql`. Set `ENABLE_BIGQUERY=true`, dataset and embedding model after granting dataset-scoped write access and project query-job access. The index worker uses parameterized MERGE and a maximum scanned-byte limit. Ordinary text/attribute search works without BigQuery. Current semantic search SQL is provided for integration validation; the online demo uses the deterministic attribute baseline.

[BigQuery Graph requirements](https://cloud.google.com/bigquery/docs/graph-overview), [vector search](https://cloud.google.com/bigquery/docs/vector-search).

## Project verification, 11 October 2026

A minimal real `gemini-3.8-flash` request succeeded in `global` using GCP credentials: 18 input tokens and 5 output tokens. This proves connectivity, not garment quality. Firebase web app `Flairify` was registered, existing Google/email providers reused, and only Flairify domains appended to authorized origins. `ALLOW_FIREBASE_IN_DEMO=true` permits verified Firebase accounts alongside anonymous sample sessions. Anonymous sessions never use paid analysis or generation. The retailer catalogue remains clearly labeled sample data via `SEED_SAMPLE_CATALOG=true`.

The project trigger enables Gemini text/analysis for signed-in users, with global daily quotas of 30 analyzed photos and 50 chat requests; each chat has a bounded tool loop. The image trigger is configured for `gemini-3.1-flash-image` in `global`, including explicitly labeled sample clothing. Video remains unavailable until separately configured and verified. Google Photos still requires a separate OAuth Picker client. No credentials or private Google Photos permissions are inferred from Firebase sign-in.


A full signed-in upload → Cloud Tasks → worker → Gemini → wardrobe review → chat smoke test also succeeded after deployment. Gemini extraction returned two candidate garments from a licensed public fixture; after confirmation, Gemini intent/tool assessment returned a complete ₹1,890 sample outfit within the ₹5,000 request. This proves the integration path, not extraction accuracy or recommendation quality. See [verification](VERIFICATION.md) and [collected results](live-integration-results.json).

## Upload and 2D preview flow

After signed-in photo-processing consent, uploading `kind=full_body` saves a private reference and linked wardrobe source, then automatically queues extraction. Uploading `kind=wardrobe` preserves explicit person selection; saving that selection starts extraction. Review/import reuses an existing analysis job. Confirm ownership before the first personalized conversation.

`POST /api/generate/try_on` accepts a current product ID, available variant, and reference ID (`full_body`, `portrait`, or `photo:<source-id>`); an outfit is optional. Missing references, unavailable stock and missing consent fail before paid generation. The worker reads owner-authorized media, runs Google image editing, stores the private result and exposes saved job status. Deleting a linked source also deletes its reference, detections and dependent previews. The API does not fetch arbitrary external images.

[Official Gemini image editing](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-edit-images) · [Gemini 3.1 Flash Image](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image).

The deployed signed-in browser journey has now verified automatic garment extraction and a successful `gemini-3.1-flash-image` preview, including visible private reference imagery, download, refresh, cross-user isolation and deletion. See [live image verification](live-image-results.json). One sample output does not establish likeness or exact garment/fit accuracy.

## Shop-style wardrobe images

With signed-in photo-processing consent, each extracted garment now queues a separate `garment_image` job using the configured `IMAGE_EDIT_MODEL` and `IMAGE_EDIT_LOCATION`. The worker sends the original garment crop to Gemini on Vertex AI, requesting a 1K studio flat lay. `ENABLE_GARMENT_IMAGES=true` controls the feature. `MAX_DAILY_GARMENT_IMAGES=12` limits each user; `MAX_DAILY_IMAGE_GENERATIONS=30` is shared with try-on. Quotas count attempts, not just successful outputs. Disable the feature to retain extraction/crops without automatic image-generation spend. These are request limits, not billing caps.

Original crops remain in `image` and preserve detection/duplicate evidence. Generated illustrations are separate `generated_image` media, with model/version metadata, never a source of confirmed attributes. Model reconstruction of occluded areas can be wrong. The UI labels generated imagery and shows the original in garment review. Generation failure does not prevent confirming ownership or using the stylist. Anonymous sample mode does not fake this capability.

`POST /api/wardrobe/{id}/shop-image` provides an idempotent request for an existing evidence crop; failed jobs use the existing bounded retry endpoint. Success is reused across extraction retries. `Keep original only` cancels/deletes the generated image; deleting the garment/source removes both media and cancels related work. The worker rechecks consent and source ownership, and cancelled/deleted garments cannot receive an in-flight result. Each separate job fits the worker timeout and queue concurrency limits.

API contract verified against [Google's Gemini image-editing documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-edit-images). No outside model provider, segmentation model or GPU is used.


## Direct multi-piece previews and backgrounds

Recommendation checkboxes start empty. One selected piece enables “See it on me”; clicking queues the preview immediately, using the current full-body reference (otherwise latest selected outfit photo, then portrait). Inventory also generates directly. Missing sign-in, processing consent, supported imagery or reference photos produces an inline error with setup links, never a fabricated result.

Selection order is significant: the latest piece replaces another in the same category; a dress replaces top and bottom, while selecting either separate replaces a dress. Jackets can layer over a top or dress. The API repeats this rule with authoritative categories across owned and new pieces. It allows at most one top, bottom, jacket, shoe pair, bag and accessory (or a dress instead of the separates). The request accepts at most 20 raw selections; resolution limits actual images to six pieces plus a reference and optional portrait. Private original crops are required for confirmed owned garments; generated shop-style cleanups are not treated as original evidence. Selected catalogue variants must still be in stock at enqueue and execution. Jobs pin selection image IDs and reject changed/deleted evidence. Deleting selected owned garments also cancels/deletes dependent previews and videos.

`UserProfile.keep_background` defaults to `false`, including profiles created before this field existed. It is an explicit rendering setting saved independently of consent to remember style preferences. The checkbox appears in the initial style-basics form and Profile. False requests a plain white background; true requests the source background. Jobs snapshot the setting when queued, so retry is stable. Regenerate is a new request and uses the current saved preference. The source photo is unchanged.

Multi-piece previews, footwear/accessories and white backgrounds use Gemini image editing only. The Google virtual-try-on fallback remains limited to one non-sample clothing product with source background; unsupported requests fail before the paid call. No additional provider was introduced. The configured `gemini-3.1-flash-image` supports up to 14 input images per the [official model reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image); the implementation stays below that limit. See [Google's image-editing API documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-edit-images). Model and region remain environment-configured. These capabilities do not guarantee exact likeness, layering, physical fit, background fidelity or unseen details.
