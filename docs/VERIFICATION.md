# Verification — 11 October 2026

## Automated checks collected

- Backend: 27 Pytest cases pass. Tests cover the confirmed-wardrobe gate, budget/size/current stock, owner isolation, media deletion, direct upload validation, consent, follow-up continuity, admin imports/indexing, unavailable generation, job deduplication, Firebase token verification, Photos Picker contract mocks and AI output validation. Regression cases also cover automatically extracting a full-body upload, reusing wardrobe photos for previews, available variants, consent, Google image requests, source deletion and regeneration.
- Frontend: four Vitest logic tests, TypeScript checks and a Next.js production build pass. Cloud Build runs these checks before deploying.
- Playwright: eight journeys pass against the deployed app, using desktop Chromium and emulated Pixel 7 viewports. They cover sample onboarding before first chat, the Mumbai budget, saving, sign-in-required generation and inventory search, direct upload/manual review, wardrobe persistence, loaded sample GLB, no horizontal overflow, keyboard focus and Axe WCAG A/AA checks on the landing and stylist screens.
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

The test account and its remaining owner-scoped records/media were removed. See [live-image-results.json](live-image-results.json). An earlier direct Vertex probe also returned a real image; only the deployed browser timings above describe the end-to-end journey.

## Capability and quality boundaries

Google Gemini image editing has a successful deployed output. Google VTO and Veo have not been verified with live outputs. Photos Picker uses contract mocks and still needs a separate OAuth client. Retail catalogue facts are synthetic. The 3D form is an original CC0 sample. See [limitations](LIMITATIONS.md) for remaining engineering work.

[evaluation-results.json](evaluation-results.json) contains the observed synthetic attribute and coverage-ranking comparison. Both return valid complete combinations; no human usefulness lift was measured. Detection precision/recall, duplicate-grouping error rates, likeness, video consistency and billed per-onboarding cost remain uncollected.
