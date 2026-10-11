# Flairify backend

[Open the deployed Flairify app](https://flairify-web-7kxckvikva-uc.a.run.app) · [API documentation](https://flairify-api-7kxckvikva-uc.a.run.app/docs)
Wardrobe-first personalized retail shopping API and asynchronous worker. Paid integration adapters target Google Cloud only. This repository is intended for a public hackathon submission; it contains no credentials.

## Run locally

Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/) are supported. The lockfile pins the complete environment.

```sh
cp .env.example .env
uv sync --locked
# Optional: set your own DEMO_ADMIN_KEY in .env for the protected demo inventory UI.
uv run uvicorn app.main:app --reload --port 8000
```

Open [API docs](http://localhost:8000/docs). Run the [frontend repository](https://github.com/samwin-steve/Flairify-Frontend) on port 3000 with `BACKEND_URL=http://127.0.0.1:8000`.

Demo mode needs no credentials. Start a session in the frontend, choose clothing/shoe sizes, optionally upload reference photos, then use sample wardrobe or direct uploads. Confirm at least one garment. Uploaded photos require manual review when Gemini is not configured. Review and correct any unknown category before confirming. For a repeatable sample, confirm all four pieces and request a Mumbai work trip within ₹5,000.

## Tests

```sh
uv run pytest -q
uv run python scripts/evaluate_demo.py
```

Tests verify wardrobe gating, isolation, media access/deletion, budget/stock/size validation, follow-up context, import/indexing, safe image sources, consent, generation failures/idempotency and Photos Picker contracts. Provider mocks are not live integration results.

## Deploy

Project: `data-workshops`, region: `us-central1`. Separate Cloud Run services: `flairify-api`, `flairify-worker`, frontend `flairify-web`.

```sh
scripts/bootstrap_gcp.sh
# First build (requires Flairify build source bucket access; see docs/DEPLOYMENT.md)
gcloud builds submit --config cloudbuild.yaml --project data-workshops --region us-central1 \
  --service-account projects/data-workshops/serviceAccounts/flairify-build@data-workshops.iam.gserviceaccount.com \
  --gcs-source-staging-dir gs://data-workshops-flairify-build/source
```

Both repositories have `cloudbuild.yaml`. `main` push triggers build, test and deploy their own service. Backend builds deploy the API and private worker together. Anonymous demo sessions keep paid AI off and public admin unlocking disabled. The deployed trigger enables bounded Gemini analysis, conversation and 2D image editing for verified Firebase accounts, alongside labeled sample catalogue facts. Production mode requires Firebase configuration, runtime IAM and approved model access.

- [Architecture and data flow](docs/ARCHITECTURE.md)
- [Integration configuration](docs/INTEGRATIONS.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [Limitations and experimental boundaries](docs/LIMITATIONS.md)
- [3D/AR license evaluation](docs/AVATAR_RESEARCH.md)
- [Tests and deployment verification](docs/VERIFICATION.md)
- [Costs and evaluation](docs/COSTS_AND_EVALUATION.md)
- [Three-minute demo](docs/DEMO_SCRIPT.md)
- [Submission explanation](docs/SUBMISSION.md)

All retailer fixtures are synthetic. Inventory offers ten sample products, nine currently in sample stock. Four photographed clothing items support illustrative 2D previews through Gemini image editing; unsupported accessories/illustrations are disabled. Downloaded photographs are licensed and credited in `fixtures/image-credits.json` and the frontend's `public/image-credits.json`. These are not verified retailer products. Google virtual try-on remains a separate adapter for verified retailer imagery.

With photo-processing consent, a full-body upload automatically queues Gemini garment extraction and becomes a usable private preview reference. Wardrobe uploads start extraction after explicit person selection. Detections remain drafts until ownership is confirmed. Try-on can start directly from Inventory using a reference or existing wardrobe photo; completed previews show source and generated images, and support download, regeneration and deletion.
