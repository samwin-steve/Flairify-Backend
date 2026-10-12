# Verification — 12 October 2026

## Latest release: saved preferences, optional wardrobe and occasion relevance

**97 backend tests, 21 frontend logic tests and 20 desktop/mobile Playwright journeys passed.** Production Next.js compilation and TypeScript checks passed. The new cases cover profile persistence without optional style-memory consent, no-photo onboarding, catalogue-only default, matching confirmed wardrobe items only, per-turn toggle overrides, saved department/store/size constraints, distinct main garments, different-options follow-ups, changing from an office celebration to a workout, unavailable stock, model rejection and unknown-ID validation. Browser journeys cover persisted Profile edits, no size/department selectors in chat, payloads using saved settings, explicit checkout confirmation, tested Axe WCAG A/AA rules and mobile overflow. These are functional regressions, not an accuracy benchmark.

The exact request “I have independece day at office can you suggest some chothes” was exercised with real Google ADK, Gemini Embedding 2, Firestore vector retrieval and Gemini whole-outfit assessment against the existing sample catalogue. Men's results used three different kurtas (rust, white and olive), neutral trousers and formal shoes, totaling **₹2,997, ₹2,397 and ₹2,797**. Women's results used two different green kurtas with neutral trousers and flats, totaling **₹2,897 and ₹3,097**. All used saved M/EU39 sizes and no owned clothes; neither response requested sizes again. Six actual text events were observed in each run. Total measured call times were **36.99s and 24.98s**; these are single observations, not latency guarantees. Product photographs were inspected as a contact sheet; metadata colours can differ from perceived colour in the photo, and no visual accuracy score is claimed.

These operator probes ran the changed local code against live Google services, before deployment. Temporary owner-scoped records were removed afterward. See [collected occasion results](live-occasion-results.json). The sample catalogue still contains 200 source records; 10 contradictory/children's records are excluded from adult shopping, leaving 190 visible records, 189 in stock. No source product or photo was deleted. The real wardrobe graph is retained for optional wardrobe-pairing requests; no graph uplift was measured in these catalogue-only probes.

Visual QA also caught an over-colourful deterministic outfit. The final rules favor neutral supporting garments and reject loud/checked office footwear. Distinct product names now identify each recommendation instead of repeated generic colour titles. No new image or video was generated in this release. Human-rated recommendation quality and coverage across arbitrary occasions remain unmeasured; the sample catalogue limits the available choices.

## Previous release: semantic retrieval, ADK, SSE and BigQuery Graph

The previous release suite had **88 passing backend tests, 17 passing frontend logic tests and 18 passing Playwright journey checks** across desktop Chromium and emulated Pixel 7. Production Next.js compilation and TypeScript checks passed. The two new streaming browser cases were rerun successfully after correcting the test fixture to retain consented sizes; the other sixteen had already passed. The final two budget regressions verify that neither an inflated agent interpretation nor an API budget can override a tighter customer ceiling. These are functional checks, not a human styling evaluation.

All **200 existing catalogue products** received real `gemini-embedding-2` embeddings through Vertex AI and were indexed in Firestore. The initial backfill took **224.48 seconds**. Two native Firestore indexes reached READY. A temporary signed-in owner then added a sample product through the deployed admin API: its asynchronous index job completed and semantic catalogue search returned it. A price edit reused the vector; a description/colour edit generated a replacement. The temporary listing and owner grant were removed afterward.

A real deployed browser request used Google ADK and bounded Firestore retrieval, returning three complete sample outfits at **₹2,298 each** against a ₹5,000 budget. The browser received **five text SSE events**, with visible word counts increasing through **2, 23, 40, 63 and 81**, and observed the word fade and typing cursor. No synthetic typing delay was used. Conversation restoration passed. Desktop and mobile Axe checks returned no violations for the tested rules; a 393-pixel mobile viewport had a 393-pixel document width. Reduced-motion mode disabled the animation. This establishes actual incremental rendering, not a latency guarantee.

The deployed property graph is `data-workshops.flairify.WardrobeGraph`. An operator check synchronized three distinct checked outfits and executed a real `GRAPH_TABLE` traversal: product coverage counts were **3, 2 and 1**; querying a different owner returned no evidence. The graph query processed **822 bytes** and the snapshot write processed **918 bytes**. These are processed bytes, not billed-cost estimates. The deployed Cloud Tasks worker also successfully synchronized checked outfit evidence. A new occasion with no prior matching outfits correctly returns an empty graph result. Human-rated recommendation relevance and graph-assisted ranking uplift have **not** been measured.

An additional live follow-up encountered Vertex AI `429 RESOURCE_EXHAUSTED`. It returned an SSE error rather than a fabricated answer. The final patch gives wrapped Google capacity errors a clear busy/retry message and safely distinguishes timeouts; tests confirm no private provider payload is exposed, no failed conversation is saved as successful, and the same request key can be retried. This probe did not collect a completed graph-assisted follow-up answer. No quota was reset or raised.

The online graph query uses Garment ← Wears ← Outfit → Adds → Product, with owner constraints and the current wardrobe fingerprint. An initial longer Customer-to-Product traversal encountered a BigQuery internal error. The deployed shorter query was verified; SDK automatic query-job resubmission is disabled so provider failures remain bounded. Graph unavailability leaves semantic recommendations usable with an explicit missing-evidence status.

| Service | Runtime source | Successful Cloud Build | Ready revision |
| --- | --- | --- | --- |
| Frontend | `2b54056` | `976cc324-8141-4368-b703-8bc4abeb4b69` | `flairify-web-00013-mvq` |
| API | `589faca` | `60eaf52b-fc29-43c2-b592-ea2b009e8d84` | `flairify-api-00018-9mj` |
| Worker | `589faca` | same backend build | `flairify-worker-00036-sll` |

Final Cloud Build completed successfully, including all 88 backend tests on Python 3.13. Live web/API health checks returned 200, while unauthenticated worker access returned 403. The temporary QA owner grant, listing, Firebase account, owner records and graph rows were removed. Cleanup verified no remaining QA records/media and the shared catalogue back at 200 products.

See [collected semantic and streaming results](live-semantic-results.json). Earlier sections below retain historical observations from previous releases. No image/video generation was performed for this release, and the existing shared image-generation allowance was not increased.

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

70 backend tests pass, including ten new cases (one parametrized) for ordered multi-piece selections, owned/new slot conflicts, duplicate bottoms and shoes, dress/separate conflicts, actual Google request image counts with a mocked SDK, current stock/variant checks, foreign/unconfirmed/missing-photo items, limits, idempotency, original-evidence changes, related media deletion, legacy profile defaults, queued background snapshots, regeneration using current settings, and honest VTO capability limits. Frontend selection logic adds nine cases (13 Vitest tests total); production compilation and TypeScript checks pass. Mocked tests validate request behavior, not visual preservation quality.


Sixteen Playwright journey checks passed across desktop and Pixel 7, including direct selection, automatic conflict replacement, keyboard toggling, zero-selection gating, a single request with all chosen IDs, absence of the old dialog, resumable job display, and background settings retained after refresh. The dedicated browser generation response is stubbed; it is not reported as a real generated image. Axe scans of the new selection interface found zero violations for the tested rules; both viewports had no horizontal overflow. A separate local browser check verified that missing-photo errors remain inline, retries reuse the request key, and “Manage reference photos” opens the Reference photos tab.

Live image verification for the new multi-piece/background behavior is currently limited by the already-exhausted shared allowance (30 attempts on 11 October 2026). The limit was not reset or increased. A new regression test confirms a 429 before queuing when the allowance is exhausted and a clear error if the limit is reached while a job waits. Real generated multi-piece preservation and both background modes therefore remain unmeasured in this update.


The deployed signed-in check used a fresh temporary Firebase account and the licensed `hero.jpg` reference. Google extraction produced two draft garments; confirming them enabled a recommendation from the sample catalogue. Selecting multiple pieces submitted their IDs directly with no dialog, then received the expected daily-allowance 429 before any try-on job was created. Both checked and unchecked background settings persisted through reload. The final Profile scan exposed an existing low-contrast image placeholder and a 14-pixel mobile overflow; the frontend correction darkens placeholder text and allows the Profile form columns to shrink. Focused desktop/mobile tests now also cover Profile overflow and an unavailable-photo placeholder.

Final deployed verification passed after both Cloud Builds completed successfully: private source/reference photos loaded, checked/unchecked background preferences persisted, desktop and mobile Profile scans each returned zero tested Axe violations, the 393-pixel viewport had a 393-pixel document width, and deleting the reference removed associated wardrobe records/media. See [live multi-preview results](live-multi-preview-results.json). No new multi-piece image was generated or rated because the existing image allowance was exhausted.

The temporary Firebase account was deleted after verification; its nine remaining owner-scoped records were removed and no residual media remained. Frontend revision `flairify-web-00012-2bm`, API `flairify-api-00015-rsk`, worker `flairify-worker-00030-gj4` were ready. The existing shared image counter was left unchanged.
