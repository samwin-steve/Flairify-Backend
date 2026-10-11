# Verification — 11 October 2026

## Automated checks collected

- Backend: 39 Pytest cases pass. Tests cover the confirmed-wardrobe gate, budget/size/current stock, owner isolation, media deletion, direct upload validation, consent, follow-up continuity, admin imports/indexing, unavailable generation, job deduplication, Firebase token verification, Photos Picker contract mocks and AI output validation. Regression cases also cover automatically extracting a full-body upload, reusing wardrobe photos for previews, available variants, consent, Google image requests, source deletion and regeneration.
- New backend cases cover seller ownership, access approval/revocation, protected product photos, indexing, requested seller products in complete outfits, mock-order persistence/idempotency, combined quantities, price/stock rechecks, customer/seller isolation, and historical order photos after a listing update.
- Frontend: four Vitest logic tests, TypeScript checks and a Next.js production build pass. Cloud Build runs these checks before deploying.
- Playwright: twelve journeys pass locally using desktop Chromium and emulated Pixel 7 viewports. They include direct mock checkout before wardrobe onboarding, seller photo/listing/stock editing, automatic discovery, order inbox/history and checkout from a stylist look. Existing checks cover sample onboarding before first chat, the Mumbai budget, saving, sign-in-required generation and inventory search, direct upload/manual review, wardrobe persistence, loaded sample GLB, no horizontal overflow, keyboard focus and Axe WCAG A/AA checks on the landing and stylist screens.
- Browser emulation is not physical-device AR validation. Automated accessibility checks are not a full accessibility audit.
- A credential-pattern scan of tracked source files found no private keys, GitHub tokens or embedded Google API keys. This is a limited scan, not a security certification.

## Deployed infrastructure checks

Both GitHub repositories have successful main-push Cloud Build deployments. The web, API and private worker use separate runtime identities. Public web/API health requests succeed; unauthenticated access to the worker is rejected (403). Cloud Tasks dispatches authorized jobs. A second user receives 404 for another user's private media; deleted media returns 404. Firebase email/password registration and verified API access were exercised using temporary QA accounts. Google sign-in is configured, but its interactive account-selection flow was not tested here.

Private Storage, the dedicated Firestore database, deny-all browser rules, indexing exclusions, BigQuery schema and the Cloud Tasks queue are deployed in `data-workshops`. No GPU or billing-alert threshold was provisioned.

## Live Vertex AI smoke test

A signed-in Firebase QA account uploaded one licensed public editorial photo through the deployed API. The authenticated Cloud Tasks worker completed Gemini garment extraction and created private evidence crops in **10.67 seconds**, including upload and polling. It returned two detections, which were confirmed for this controlled test. This is not a detection accuracy benchmark.

A subsequent Mumbai request used Gemini intent interpretation and tool-assisted whole-outfit assessment. It returned one complete combination with **₹1,890 of sample new products**, within the ₹5,000 total budget and available sample variants, in **7.41 seconds**. Both latencies are single observations, not percentiles or service-level promises. Cross-user media access and access after deletion both returned 404. The temporary Firebase test account and its owner-scoped records/media were removed after verification.

See [live-integration-results.json](live-integration-results.json) for the collected result. Separately, a deployed browser check confirmed that all four wardrobe/product photos in a recommendation card loaded successfully. Downloaded source pages and licenses are recorded in the frontend image credits.

## Live browser upload and image-generation check

A fresh Firebase account completed the deployed browser journey using the licensed public `hero.jpg` fixture and the sample catalogue shirt. With consent, the full-body upload automatically queued Gemini extraction and produced **two draft garments in 8.84 seconds**. Ownership review remained required. Inventory showed **nine in-stock sample items** from ten records. The uploaded photo was visible and selected in the try-on dialog without a second upload.

The private worker used **`gemini-3.1-flash-image` on Vertex AI in `global`** to produce a real 2D preview in **14.52 seconds**, measured from the generation click to a successful job poll. The downloaded PNG was **1,390,426 bytes**. Both source and generated images loaded. Refresh persistence, download, mobile overflow checks, try-on dialog Axe checks, cross-user media denial (404), preview deletion (404), and source/garment deletion passed. These are single-fixture functional observations, not preservation or detection-quality benchmarks. The generated photo was visually reviewed as a style visualization; exact identity, garment reproduction and fit are not guaranteed.

A subsequent fresh-account browser check on frontend build `aeb0c60f-2e8b-48e4-83cd-39e4b661756a` confirmed that first sign-in opens wardrobe setup automatically. The test accounts and their remaining owner-scoped records/media were removed. See [live-image-results.json](live-image-results.json). An earlier direct Vertex probe also returned a real image; only the deployed browser timings above describe the end-to-end journey.

## Capability and quality boundaries

Google Gemini image editing has a successful deployed output. Google VTO and Veo have not been verified with live outputs. Photos Picker uses contract mocks and still needs a separate OAuth client. Retail catalogue facts are synthetic. The 3D form is an original CC0 sample. See [limitations](LIMITATIONS.md) for remaining engineering work.

[evaluation-results.json](evaluation-results.json) contains the observed synthetic attribute and coverage-ranking comparison. Both return valid complete combinations; no human usefulness lift was measured. Detection precision/recall, duplicate-grouping error rates, likeness, video consistency and billed per-onboarding cost remain uncollected.

## Live seller and mock-order checks

Temporary signed-in Firebase accounts exercised owner approval and revocation, seller-only product upload, private image retrieval, Cloud Tasks indexing, catalogue discovery, authoritative quoting, idempotent mock placement, private customer order history, and the seller inbox. Stock remained unchanged after placement; an unavailable quantity was rejected after a stock update. Customer order access by another account returned 404. The initial-owner bootstrap script was also exercised against a temporary account. All temporary accounts, roles, listings, product media, and tracked order/projection records were removed afterward. No payment system or paid AI generation was invoked by these commerce checks.

Four critical browser journeys were repeated successfully on the deployed release: direct mock purchase and the wardrobe/stylist purchase journey, each on desktop Chromium and emulated Pixel 7. The remote order-history test now waits for app initialization before choosing desktop versus mobile navigation. All four passed in the final live run.

Release evidence:

| Service | Runtime source | Successful Cloud Build | Ready revision |
| --- | --- | --- | --- |
| Frontend | `c9ffc3c` | `9857967f-c6a2-476d-a325-c2912aa181e2` | `flairify-web-00008-x7j` |
| API | `b1a4c54` | `3e0ee7d9-6e77-45ca-ab6c-e016ba475b55` | `flairify-api-00010-lpk` |
| Worker | `b1a4c54` | same backend build | `flairify-worker-00020-5mm` |

Later frontend changes only add the browser-test initialization wait; they do not change runtime source. Both repository main-push triggers remain enabled. The intended real owner's sign-in email was not supplied during this verification, so no real account was granted owner access by assumption.
