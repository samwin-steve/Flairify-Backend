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
- `IMAGE_EDIT_MODEL=gemini-3.1-flash-image`, `IMAGE_EDIT_LOCATION=global`: Google-only 2D editing uses the selected customer photo and product image, plus an optional portrait for identity. Jacket layering preserves the visible source top as an evaluation target. The source photo remains unchanged. `ALLOW_SAMPLE_TRY_ON=true` permits only the bundled, allowlisted licensed catalogue photos as illustrative previews. Set it false for a retailer deployment. `MAX_DAILY_IMAGE_GENERATIONS=30` is the shared image quota; each account has a separate five-per-day generation limit.
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
