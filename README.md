# Flairify backend

[Open the deployed Flairify app](https://flairify-web-7kxckvikva-uc.a.run.app) · [API documentation](https://flairify-api-7kxckvikva-uc.a.run.app/docs)
Personalized retail shopping API with optional wardrobe pairing and asynchronous worker. Paid integration adapters target Google Cloud only. This repository is intended for a public hackathon submission; it contains no credentials.

## Run locally

Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/) are supported. The lockfile pins the complete environment.

```sh
cp .env.example .env
uv sync --locked
# Optional: set your own DEMO_ADMIN_KEY in .env for the protected demo inventory UI.
uv run uvicorn app.main:app --reload --port 8000
```

Open [API docs](http://localhost:8000/docs). Run the [frontend repository](https://github.com/samwin-steve/Flairify-Frontend) on port 3000 with `BACKEND_URL=http://127.0.0.1:8000`.

Demo mode needs no credentials. Save your shopping department, clothing/shoe sizes, preferred store and budget, then start shopping without photos. These settings persist independently of optional style-memory consent and can be changed in Profile. Wardrobe pairing defaults off; turn it on in chat to consider suitable confirmed pieces. Uploaded photos require manual review when Gemini is not configured. Review and correct unknown details before confirming ownership.

## Tests

```sh
uv run pytest -q
uv run python scripts/evaluate_demo.py
```

Tests verify shopping-preference setup, optional confirmed-wardrobe use, isolation, media access/deletion, budget/stock/size validation, follow-up context, import/indexing, safe image sources, consent, generation failures/idempotency and Photos Picker contracts. Provider mocks are not live integration results.

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

The sample catalogue contains **200 options** (90 men’s, 91 women’s, 19 unisex): 48 tops, 43 bottoms, 25 jackets, 16 dresses, 42 shoes, 15 bags and 11 accessories. Ten contradictory or children’s listings are excluded from adult shopping results without deleting the source records. This leaves 190 shopper-visible records, 189 in simulated stock; one deliberately sold-out fixture exercises unavailable-item handling. Sample clothing offers XXS–4XL, shoes EU 35–48, and bags/accessories one size, at two sample stores. These variants are demonstration data, not manufacturer size availability. Seller-supplied stock and sizes remain unchanged.

190 new archive photographs include eight image references from the requested Myntra fashion CSV and 182 from Param Aggarwal’s fashion image dataset. Provenance and publisher-declared licenses are recorded in `fixtures/catalogue-sources.json`, `fixtures/image-credits.json`, and [catalogue documentation](docs/CATALOGUE.md). Photographed clothing, footwear, bags and accessories support illustrative Google Gemini previews; items without supported original photographs stay disabled. No sample listing is a current retailer offer.

With photo-processing consent, a full-body upload automatically queues Gemini garment extraction and becomes a usable private preview reference. Wardrobe uploads start extraction after explicit person selection. Detections remain drafts until ownership is confirmed. Each detected garment also queues a private Gemini shop-style image, with the original evidence crop retained, AI labeling, retry and an original-only option. Image failure does not block wardrobe review. Try-on can start directly from Inventory using a reference or existing wardrobe photo; completed previews show source and generated images, and support download, regeneration and deletion.

## Seller Studio and mock orders

Owners and approved sellers can add clothes with a product photo, SKU, INR price, sizes, store quantities, and optional aisle/rack. Each save queues indexing; successfully indexed active products appear in Inventory and are eligible for size-, stock-, and budget-checked recommendations. Sellers manage only their own products and stores. Owners manage the shared catalogue and approve seller requests. Existing Firebase `admin` and `seller` claims remain supported.

A signed-in customer opens **Seller Studio → Request seller access**. An owner reviews requests in Seller Studio. Bootstrap the first owner from a trusted operator terminal after that person has signed in to Flairify:

```bash
.venv/bin/python scripts/grant_seller_access.py --project data-workshops --email OWNER_EMAIL --role owner
```

The operator needs Identity Platform account-read and Firestore write permissions and an active `gcloud auth login`. No identity-admin permission is added to the running app. Roles live in the server-only `flairify_seller_access` collection; browser Firestore access remains denied. App-managed revocations take effect on the next request. Firebase custom claims are managed separately; a preexisting custom claim must be removed separately to revoke its grant. Never bootstrap an account based only on a name or client-supplied UID.

Customers can choose **Inventory → Mock buy** without wardrobe onboarding, or **Mock buy new pieces** on a stylist recommendation. Checkout requires explicit mock acknowledgment, selected sizes/stores/quantities, and a server-validated total. Orders are persisted privately and reappear in **My Orders**. Seller Studio shows only the seller's item lines; the owner sees the catalogue-wide mock inbox. No payment, shipment, reservation, stock decrement, or wardrobe-ownership confirmation occurs.

The backend rechecks serving inventory at quote and placement, rejects changed totals, unavailable sizes and excessive quantities, and merges repeated product/variant/store cart lines. A stable request key prevents duplicate placement; replay returns the original price snapshot. Order persistence is atomic per customer/order key. Inbox projections are separate idempotent writes and are repaired on retry; there is no cross-document transaction or background repair sweep. These are mock records, not a production fulfillment system. Anonymous demo history lasts only while its isolated session is valid; sign in for account-based history.

API additions: `GET/POST /api/orders`, `POST /api/orders/quote`, `GET /api/orders/{id}`, `GET /api/admin/orders`, `POST /api/admin/products`, `GET /api/seller-access`, `POST /api/seller-access/request`, `GET /api/admin/seller-requests`, and owner-only approval/revocation actions. The protected image upload accepts validated files rather than fetching arbitrary URLs. Index publication checks the product hash to avoid overwriting stock edited during indexing.


Select one or more pieces using the initially empty checkboxes on a stylist look, then click **See it on me** to generate directly. Conflicting slots resolve to the latest selection. Set **Keep my generated outfits in the same background** during onboarding or in Profile; unchecked requests a plain white background. See [integration details](docs/INTEGRATIONS.md#direct-multi-piece-previews-and-backgrounds) for selection validation, deletion and provider limits.

## Semantic catalogue RAG and streamed ADK stylist

See [SEMANTIC_RAG.md](docs/SEMANTIC_RAG.md) for the Gemini Embedding 2 / Firestore implementation, Google ADK modules, SSE contract, indexes, migration and explicit demo limitations.

## Occasion-aware recommendations

Saved shopping settings replace the repeated chat selectors. Catalogue-only recommendations work without photos; the chat switch opts into suitable confirmed wardrobe pieces. Ranking retains semantic similarity, interprets the occasion, assesses complete shortlisted outfits with Gemini and diversifies the main garment. Checkout preselects saved/recommended variants but still requires review and confirmation. See [recommendation quality and limits](docs/RECOMMENDATION_QUALITY.md).
