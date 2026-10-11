# Verification — 11 October 2026

## Automated checks collected

- Backend: 60 Pytest cases pass. Tests cover the confirmed-wardrobe gate, budget/size/current stock, owner isolation, media deletion, direct upload validation, consent, follow-up continuity, admin imports/indexing, unavailable generation, job deduplication, Firebase token verification, Photos Picker contract mocks and AI output validation. Regression cases also cover automatically extracting a full-body upload, reusing wardrobe photos for previews, available variants, consent, Google image requests, source deletion and regeneration.
- New backend cases cover seller ownership, access approval/revocation, protected product photos, indexing, requested seller products in complete outfits, mock-order persistence/idempotency, combined quantities, price/stock rechecks, customer/seller isolation, and historical order photos after a listing update.
- Frontend: four Vitest logic tests, TypeScript checks and a Next.js production build pass. Cloud Build runs these checks before deploying.
- Playwright: fourteen journeys pass locally using desktop Chromium and emulated Pixel 7 viewports. They include direct mock checkout before wardrobe onboarding, seller photo/listing/stock editing, automatic discovery, order inbox/history and checkout from a stylist look. Existing checks cover sample onboarding before first chat, the Mumbai budget, saving, sign-in-required generation and inventory search, direct upload/manual review, wardrobe persistence, loaded sample GLB, no horizontal overflow, keyboard focus and Axe WCAG A/AA checks on the landing and stylist screens.
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

## Shop-style garment images

On 11 October 2026, a fresh signed-in QA upload of the licensed public `hero.jpg` fixture created two draft garment crops and two real **Gemini 3.1 Flash Image** shop-style images through the deployed Cloud Tasks worker. Both image jobs succeeded. Stored job timestamps record **5.935 seconds** for extraction and **10.126 / 11.965 seconds** from each image job's creation to completion, including queue time. These are single-fixture observations, not latency percentiles or quality measurements.

The deployed review dialog loaded both the generated illustration and original crop. Desktop and 393px mobile screenshots were visually inspected; mobile had no horizontal overflow. The desktop review dialog had no Axe WCAG A/AA violations. Refresh persistence, cross-user image denial (404), deleting only the generated image while retaining the crop, and deleting the source with all garment media passed. The browser check resumed using the same temporary account after fixing test-runner setup and a navigation selector; no extra image generation was needed.

The five new backend tests cover private image provenance, unchanged original evidence and attributes, idempotent reuse, preserving user edits, failed image generation without blocking ownership review, retry, consent at execution, cancellation during generation, and deletion. Existing try-on tests now also account for the automatic garment-image request. TypeScript, four Vitest tests and the production frontend build passed. Both Cloud Build pipelines passed their checks and deployed successfully.

| Service | Runtime source | Cloud Build | Ready revision |
| --- | --- | --- | --- |
| Frontend | `f7519b2` | `c889f902-682c-49ba-82c8-10a66d046cd6` | `flairify-web-00009-x4h` |
| API | `34c4f36` | `e7464102-dd90-4309-9944-13e8d647c617` | `flairify-api-00012-jmd` |
| Worker | `34c4f36` | same backend build | `flairify-worker-00024-rqt` |

The temporary Firebase QA account, test demo session and owner-scoped records were removed after verification; no residual QA media remained.

See [collected live checks](live-garment-image-results.json). Generated images can complete hidden garment details incorrectly; they do not replace original evidence. No numerical garment-preservation quality or billed-cost result is claimed.

## Expanded catalogue checks

200 validated sample products, 190 additional local archive photos (8 exact image references from the requested Myntra CSV), department counts 90 men / 91 women / 19 unisex. All sample clothing variants cover XXS–4XL and shoes EU 35–48. Asset tests verify photo integrity, manifest identity, supported clothing preview inputs and two-store size coverage. Migration tests preserve retailer edits while upgrading untouched legacy fixtures.

Twelve parameterized Mumbai checks cover men/women, XXS+EU35 / XXL+EU45 / 4XL+EU48, and a wardrobe containing only a shirt or only a jacket. Every scenario returned complete outfits with current stock and combined totals at or below ₹5,000. Additional checks cover a requested new shirt with a missing bottom, category retrieval beyond 60 results, unavailable sizes and explicit error explanations. These are synthetic correctness results; no human relevance score is claimed. The local comparison in `evaluation-results.json` was recollected for this catalogue.

The deployed shared catalogue migrated from 10 to 200 without changing seller-edited records. Four anonymous live API scenarios each returned three complete ₹2,997 outfits from a single confirmed shirt. A separate temporary Firebase account exercised real Gemini intent and tool-based whole-outfit assessment against the expanded catalogue: three valid ₹2,997 outfits, all assessments sourced from Gemini, in 13.21 seconds. Its account and 48 owner-scoped records were deleted after verification. See `live-catalogue-results.json`; these checks establish response validity, not human-rated styling quality.

Live frontend verification: all 190 added photo files return the exact bytes of the validated local copies. Desktop Chromium and Pixel 7 emulation both passed catalogue filtering, photo loading, refresh, editable 4XL/EU48 sizes and complete ₹2,997 recommendations. Inventory Axe scans reported zero WCAG A/AA violations; neither viewport overflowed horizontally. Both Cloud Build triggers succeeded; the frontend serves revision `flairify-web-00010-vz8`. Physical mobile devices were not tested.

## Direct multi-piece previews and background settings — 11 October 2026

69 backend tests pass, including nine new cases (one parametrized) for ordered multi-piece selections, owned/new slot conflicts, duplicate bottoms and shoes, dress/separate conflicts, actual Google request image counts with a mocked SDK, current stock/variant checks, foreign/unconfirmed/missing-photo items, limits, idempotency, original-evidence changes, related media deletion, legacy profile defaults, queued background snapshots, regeneration using current settings, and honest VTO capability limits. Frontend selection logic adds nine cases (13 Vitest tests total); production compilation and TypeScript checks pass. Mocked tests validate request behavior, not visual preservation quality.
