# Image performance update — 18 October 2026

See [image delivery results](IMAGE_DELIVERY_RESULTS.md): both latest repositories were
pulled, 365 thumbnails prepared, the initial Inventory payload reduced by 95.63%,
and authenticated browser cache hits verified with zero transferred bytes. Backend
and frontend Cloud Builds succeeded; 235 backend tests, 48 frontend logic tests and
28 distinct targeted desktop/mobile browser cases passed across reruns.

# Latest catalogue update — 14 October 2026

See [catalogue enrichment verification](CATALOGUE_ENRICHMENT_RESULTS.md) for the completed 200-product backfill, live incremental indexing and four real streamed conversation checks. See [photo import and publication](PHOTO_CATALOGUE_IMPORT.md) for 365 newly published Drive products with configurable prices, all supported sizes, verified semantic retrieval and a saved payment-free order. All 213 backend tests passed.

# Verification — 13 October 2026

## Latest release: no daily voice-session cap and reliable return navigation

Removed both daily voice-session checks and their configuration fields. Previously exhausted records are ignored without resetting counters. The deployed authenticated request returned **429 before** and **200 after**, while the old shared counter remained **12** even after a real voice call. Authentication, exclusive chat leases, single-use tickets, per-connection duration, and separate search/generation limits remain enforced.

In-app menu navigation now preserves the voice call and updates the same history used by spoken back commands. Starting or switching chats still ends the old call. Completed, explicit page requests have a conservative fallback when the model only speaks an acknowledgement; named destinations override an imprecise model argument. Interim, interrupted, negative, quoted and compound requests cannot trigger the fallback.

**166 backend tests, 28 frontend logic tests, production compilation and 20 distinct desktop/mobile browser journeys passed.** The updated voice journey was rerun on both viewports after adding an explicit new-chat termination assertion. The local voice transport is a fixture; it separately covers previews, selection retention, reconnect, invalid destinations and duplicate events.

Both Cloud Builds succeeded and route 100% of traffic to web `flairify-web-00023-27t`, API `flairify-api-00027-7b4` and private worker `flairify-worker-00054-5x7`. Six Google-synthesized spoken requests passed through the real browser MediaStream, capture worklet, Google Live transcription and tools: open Fitting Room, back to styles, open closet, back to Stylist, back to Inventory after manual menu changes, and return to the original page. The call retained one connection throughout, returned 1,045,464 native audio bytes and saved 14 messages. End stopped the microphone. No image/video generation was requested. Mobile checks found no horizontal overflow. This does not measure physical phone microphones or arbitrary accents/noise.

The temporary Firebase account and three owner records were removed; zero owner records or QA media remain. Web/API returned 200 and private worker returned the expected unauthenticated 403. See [collected before/after and spoken navigation evidence](live-voice-return-results.json).

## Previous release: spoken garment selection, previews and mobile navigation

**132 backend tests, 25 frontend logic tests, TypeScript and production builds pass.** Across the full browser run and focused reruns, all **42 distinct desktop/mobile journeys** pass. The first run exposed two tests that still clicked the removed mobile bottom bar; both now use the hamburger menu. The final 20 voice/navigation/onboarding checks passed together, including desktop hamburger visibility, mobile viewport use, selected checkboxes, manual selection updates, reconnecting with the same chat, keeping voice during Fitting Room generation, showing the completed preview/Buy action, and no recovery after End. Local voice transport and image responses are explicit fixtures.

Backend tests exercise the exact Vishudh kurta / Cobblerz sandals names, combining them through the shared try-on service, deduplication after reloading a conversation, unknown/ambiguous/foreign names, slot conflicts, clear/remove, stock and reference-photo rechecks, safe retrieval timeouts and blocking generation after an invalid selection. Existing tests cover consent, image failures, owner isolation and cancellation. New modules pass focused Ruff checks; the repository-wide lint command still finds pre-existing issues outside the changed modules.

Both Cloud Builds succeeded: backend `8d2f8c4a-c669-4e87-9fe6-217c31e3ea2f` (source `52ff9ed`) and frontend `dd104cd1-238d-4bff-b2bd-085113b35624` (source `fdca938`). API `flairify-api-00024-66n`, private worker `flairify-worker-00048-btf`, and web `flairify-web-00020-qhc` were ready. Delayed duplicate builds, including an obsolete frontend commit, were cancelled; no model or application quota was increased.

### Real deployed check

A temporary Firebase account used an existing licensed sample portrait and a controlled prior conversation containing the two actual current catalogue products. Three Google-synthesized spoken utterances went through the real browser capture worklet to Vertex Gemini Live. The agent selected both named products without generating, recovered from a forced WebSocket disconnect with selections retained, then queued one real Google Gemini image-editing preview. A repeated spoken generation request returned the same job. Native reply audio totalled 1,197,608 bytes. The image job succeeded with both selected product names, and the generated image and Buy action loaded after refresh. End stopped microphone tracks. The 393px mobile check had no horizontal overflow or bottom navigation, and its tested Axe rules had zero violations. Screenshots were visually inspected.

These checks establish one working selection-to-preview example and bounded connection recovery, not a human recommendation-relevance score or guaranteed likeness/fit. Physical phone microphones, noisy speech, arbitrary language/accent accuracy and all network interruptions remain unmeasured. See [collected live evidence](live-voice-actions-results.json). The temporary Firebase account, ten owner records and two media objects were removed; no owner records remained. Web/API health returned 200, and the private worker returned its expected unauthenticated 403.

## Previous release: voice availability after sign-in

Reproduced the reported unavailable error on the deployed frontend by delaying actual capability responses during Firebase restoration: the signed-in server reported voice enabled, but the client blocked Talk using guest/pending configuration without making a voice request. The frontend now waits for authentication, separates guest/account capability caches and uses the authenticated voice-ticket endpoint as authority. Demo Talk also opens sign-in correctly.

**25 frontend logic tests, 38 desktop/mobile browser journeys, TypeScript and the production build passed.** New cases cover slow initialization, stale false flags, actual server refusals and demo sign-in without microphone capture. Source `8f90a2e`, successful Cloud Build `cf8c8570-9b56-4276-b8e0-9451e83c6852`, serves all traffic as `flairify-web-00019-d4x`. The deployed delayed-capability retest connected through the real authenticated backend to Google and received 34,562 native audio bytes, transcript and turn events. End worked. Physical microphones were not retested; no backend code, model settings or quotas changed. See [voice connection evidence](live-voice-config-results.json).

## Previous release: account-entry preferences and new chats

**25 frontend logic tests, 34 desktop/mobile Playwright journeys, TypeScript and the production Next.js build passed.** Shopping preferences now gate account entry, including restored Firebase/demo sessions and legacy profiles missing a required size. Returning customers with complete settings skip setup. Photos remain optional, and preferences remain editable in Profile. The setup form has readable step-label contrast and mobile columns that stay within the viewport.

New chat is visible above the conversation on desktop/mobile, clears the draft and look selection, detaches a pending text or voice response, and persists a fresh state through refresh. Previous conversations remain available explicitly in history. Browser tests cover delayed history loading, stale completed responses, a late voice event, separate persisted conversations, legacy/incomplete setup, Profile readback, tested Axe rules and horizontal overflow. Text/voice late-event cases use clearly identified transport fixtures; normal demo conversation and preference tests use the real local APIs.

The first broader run exposed old Fitting Room fixtures that bypassed account setup; the fixtures now save sizes before entering the app. A later rerun exhausted the isolated local demo-account quota after repeated test runs; the final 34 checks passed on a fresh local SQLite dataset with paid AI disabled. Production quotas were not changed. The backend runtime is unchanged in this release; its 126 tests were verified in the preceding voice release and were not rerun for frontend-only behavior.

### Deployed verification

The normal main-push Cloud Build **`e87b627d-a659-4b53-866c-67e357071738`** succeeded and deployed frontend source **`c41bfa4`** as **`flairify-web-00018-sgf`**, serving all traffic. The build listing was initially delayed; a duplicate manually requested build was cancelled before starting. Backend revision `flairify-api-00023-f82` remains unchanged. Web/API health returned 200; the private worker returned its expected unauthenticated 403.

A temporary Firebase customer registered and completed setup on the deployed site. Incomplete-account refresh returned to preferences; completed-account refresh and later sign-in went straight into the app. Saved M/EU39/men/Bandra settings remained editable. Two real Gemini greetings persisted as separate conversations, with the original two messages unchanged. New chat cleared the draft and survived refresh; selecting an earlier conversation restored it after refresh. Mobile history navigation, desktop/mobile tested Axe rules and 393px/320px chat widths passed. The 393px setup form had no horizontal overflow. Screenshots were visually inspected, and the final browser recorded no JavaScript errors.

The first registration check used an overly short five-second assertion while the profile was still loading; verification resumed with the same account and a 30-second wait. One live chat request timed out and correctly restored its draft with an error; one retry succeeded. Successful greeting calls took 7.881s and 4.970s in this run, excluding the failed request; these are individual observations, not latency guarantees. A contrast scan during the message entrance animation was repeated after opacity reached 1, without another model call. No images, videos, voice sessions or purchases were generated in this release check. See [collected deployed checks](live-entry-deployed-results.json).

The temporary Firebase account and its eight owner-scoped records were deleted after verification. No owner records or QA media remained. No real customer settings or production quotas were changed.

## Previous release: native Gemini Live voice stylist

**126 backend tests, 25 frontend logic tests and 28 desktop/mobile Playwright journeys passed**, along with TypeScript and the production Next.js build. New tests cover single-use voice tickets, Firebase/demo gating, cross-user conversation denial, exact WebSocket origins, shared chat leases, malformed PCM, quota bounds, saved interrupted turns, roleless native audio events, tool acknowledgement/result assembly, readable transcripts, resampling and playback cancellation. Browser voice tests use a clearly simulated provider stream with real browser capture, and verify permission denial, mute/end, history, reduced motion and accessibility. The initial wider browser run lacked the local admin fixture key; it was rerun with the required isolated setup. The final 28 all passed. A mobile preference shortcut hidden by the first layout was restored before the successful final run.

A separate **deployed signed-in Chromium session** used Google-generated spoken WAV utterances through an actual MediaStream, the application's AudioWorklet, the Cloud Run WebSocket and **Vertex AI `gemini-3.8-live` in `us-central1` through Google ADK**. Neither the API nor WebSocket was mocked. This verifies synthesized audio input and real native spoken output, not human microphone acoustics. The browser observed **2,203,690 received audio bytes, 290 output chunks, 4,167 captured input frames and 293 playback starts** (including three test-input sources). Connection readiness took **6.283 seconds** in this one run.

The voice request for a subtle Independence Day office outfit under ₹5,000 returned three looks totaling **₹2,897, ₹3,097 and ₹3,097**. The next spoken request, “I like the second look. Keep the top and trousers, but change the shoes,” retained the exact olive kurta and grey trousers in all three variants and replaced the old shoe product, with totals **₹3,297, ₹2,797 and ₹2,697**. Asking why the stylist liked the look returned an explanation with **no new outfit cards**. All shopping preferences came from the saved profile. Measured input-to-persisted-turn times were **32.340s, 30.134s and 13.239s**, including playback of the input utterance and tool work; these are individual observations, not conversational latency percentiles. A short spoken acknowledgement can arrive before the final cards.

Mute stopped outgoing PCM frames. End stopped all microphone tracks. All seven messages (greeting plus three exchanges) restored after refresh. Desktop and 393px mobile Axe scans returned zero violations for the tested WCAG A/AA rules, reduced motion disabled the orb animation, and the mobile document width matched its viewport. A separate local 320px layout check retained all composer controls without overflow. Screenshots were visually inspected and no browser errors were recorded. See [collected deployed voice results](live-voice-deployed-results.json).

The live conversation was verified on frontend source `0af6615` / revision `flairify-web-00017-qgf` (successful build `1c4cd67a-4751-4d66-95e1-27cb88c5c3fd`) and backend source `9ddd57a` / API `flairify-api-00022-8r2`, worker `flairify-worker-00044-4bq` (successful build `d5911dd7-07fe-44d5-950a-c02a61fe7e64`). The final transcript-only patch `d083e38` adds missing sentence spaces seen in native tool-boundary transcripts; its regression preserves initials and decimal prices. Successful Cloud Build `48efa241-9976-4eb6-bf06-8dcf860c5f65` independently passed all 126 tests and deployed API `flairify-api-00023-f82` and worker `flairify-worker-00046-hsj`. The paid three-turn journey was not repeated for this formatting-only patch. Final health and same-origin microphone policy checks passed. Web/API health returned 200; unauthenticated worker access returned the expected 403.

The temporary Firebase account and **74 owner-scoped records** were removed; zero owner records or media remained. Raw voice audio was not persisted by Flairify. The local test utterances are temporary QA assets, not committed customer recordings. No image/video generation, purchase or real-user setting was changed during voice verification. Physical phone microphones, noise/accent accuracy, human-rated styling usefulness, native interruption in a real speaking turn and billed voice cost remain unmeasured. Interruption handling is covered by simulated transport and backend tests. See [voice setup and boundaries](VOICE_STYLIST.md).

## Previous release: conversational stylist and targeted variations

**115 backend tests, 21 frontend logic tests and 24 desktop/mobile Playwright journeys passed**, with TypeScript and a production Next.js build. Browser verification covers automatic chat restoration, discussion without duplicate recommendations, explicit look selection, preserving a selected look's shirt/trousers while replacing only shoes, menu keyboard behavior, new-chat reset, reduced-motion support and the existing shopping/generation journeys. Mobile/desktop screenshots were inspected; tested Axe rules and overflow checks passed for the new conversation journey. The preference journey's selector was updated to wait for the new response because restored historical cards are now present.

A three-turn operator probe ran the changed code against actual Vertex AI Gemini, Google ADK, Gemini Embedding 2 and Firestore. Independence Day office recommendations returned three different main garments at ₹2,797, ₹2,697 and ₹3,697, searching four categories and reading 51 candidates. “I like the second look. Keep the shirt and trousers, but swap the shoes” preserved the exact green shirt and grey trousers, returned two different replacement shoes at totals ₹2,897 and ₹2,597, and searched only shoes (23 candidates). A subsequent explanation returned no new outfit cards and performed no semantic retrieval. Each turn delivered four real text events. Observed complete service-call times were 42.936s, 28.279s and 13.195s, including local-to-cloud persistence overhead; these are single observations, not service-level guarantees or a controlled latency comparison. All 67 temporary owner records were removed. No image/video generation was requested. See [collected real-service results](live-dialogue-results.json).

The first operator attempt failed before a model call because the test harness replaced the Gen AI Client type before ADK schema construction. The harness was corrected to supply Google credentials without replacing the type, then the full three-turn check passed. This was a harness problem, not a fabricated successful model response.

These checks establish conversation continuity, slot preservation, bounded retrieval and current budget/stock enforcement. Broad recommendation relevance, user satisfaction and graph-assisted uplift remain unmeasured. BigQuery Graph remains available for optional wardrobe pairing; this catalogue-only probe did not query it.

### Deployed conversation verification — 13 October 2026

Both main-push Cloud Builds passed and deployed: frontend `446fcff7-d836-414f-80fe-9e0601b37f06` (source `308df7d`) and backend `89e499db-af82-41fe-a01e-5a74d0a2ef7b` (source `2c00fd4`). Ready revisions are `flairify-web-00016-mj7`, `flairify-api-00021-rz4` and private `flairify-worker-00042-mx7`. Web/API returned 200; unauthenticated worker access returned the expected 403. Cloud Build independently passed the backend and frontend tests.

A fresh Firebase account completed onboarding in the deployed browser with saved men/M/EU39/Bandra preferences, then received three Independence Day office looks totaling ₹2,797, ₹2,597 and ₹3,097. The browser test initially could not retrieve a terminal SSE body from Chromium after the application had closed its completed stream; the answer was already displayed and persisted successfully. Verification resumed with the same account and saved conversation, without repeating the first model request. That first turn's streaming count and duration were not recovered and are intentionally null in the collected evidence.

Selecting the second look and asking to keep its top/trousers while changing shoes preserved the exact rust kurta and black trousers. Two different replacement shoes produced totals of ₹2,897 and ₹2,697. Only one category was searched, retrieving 23 candidates. The next explanatory question returned no new outfit cards and no semantic retrieval. The two follow-ups took 13.361s and 7.442s in this one browser run; six and four real text events were observed, with visible word counts progressing through 2–79 and 13–67 respectively. These are individual observations, not a latency guarantee or styling-quality score.

Full six-message history restored after refresh. Desktop and 393px mobile scans reported zero violations for the tested Axe WCAG A/AA rules, no mobile horizontal overflow and no browser errors. The refined wardrobe menu and reduced-motion preference worked. Deployed screenshots were visually inspected. See [collected deployed conversation results](live-dialogue-deployed-results.json). No image or video generation was requested; the retailer catalogue remains explicitly labeled sample data. The temporary Firebase account and 67 owner-scoped records were removed, with zero remaining owner records or uploaded media.

## Previous release: generated preview and Fitting Room checkout

**106 backend tests, 21 frontend logic tests and 22 desktop/mobile Playwright journeys passed.** TypeScript and production Next.js compilation passed. Completed preview cards display only the generated image; the original photo is neither rendered nor fetched by the preview card. Reference management remains available separately. Buy opens checkout for all available new products from the original recommendation, even when fewer were selected for generation; owned items are excluded.

New checks cover authenticated preview access, unfinished jobs, unrelated product injection, standalone/legacy previews, missing recommendations, unavailable stock, changed prices, idempotent order placement and refresh persistence. The browser tests use real local order APIs and explicitly labeled completed-preview media fixtures. No new Google image or video was generated for this interface/order change, and no generation-quality improvement is claimed. Tested Axe WCAG A/AA rules reported zero violations; desktop and Pixel 7 layouts had no horizontal overflow. Screenshots were inspected.

Shopping actions now read Buy and Order placed. Orders still persist without payment or fulfillment; internal legacy API fields remain compatible. Both main-push Cloud Builds succeeded: frontend `ed518007-e38f-4a94-961a-147868143e25` (source `05aaba9`) and backend `7e28ea8c-5b79-45aa-a7a1-522df12d1d11` (source `c2c0a33`). Ready revisions are `flairify-web-00015-q2g`, `flairify-api-00020-l5r` and private `flairify-worker-00040-k5q`. Web/API returned 200 and unauthenticated worker access returned 403. Cloud Build independently passed all 106 backend tests and 21 frontend logic tests.

A fresh private demo session exercised the deployed UI using an explicitly labeled completed-preview fixture. Both desktop and Pixel 7 emulation loaded the preview image without requesting its source comparison image; Buy offered all three recommended new products even though only one was marked selected for the preview. Checkout saved a three-item order totaling ₹2,097 through the real Firestore-backed order API. The order restored after refreshing on both layouts. No visible mock labels or browser errors were found; tested Axe rules returned zero violations. Document widths matched their 1440px and 412px viewports. Screenshots were inspected. Temporary session records and private media were removed afterward. See [collected deployed results](live-fitting-shopping-results.json); this verifies layout/order behavior, not a new model generation.

## Previous release: saved preferences, optional wardrobe and occasion relevance

**99 backend tests, 21 frontend logic tests and 20 desktop/mobile Playwright journeys passed.** Production Next.js compilation and TypeScript checks passed. The new cases cover profile persistence without optional style-memory consent, no-photo onboarding, catalogue-only default, matching confirmed wardrobe items only, per-turn toggle overrides, saved department/store/size constraints, distinct main garments, different-options follow-ups, changing from an office celebration to a workout, unavailable stock, model rejection and unknown-ID validation. Browser journeys cover persisted Profile edits, no size/department selectors in chat, payloads using saved settings, explicit checkout confirmation, tested Axe WCAG A/AA rules and mobile overflow. These are functional regressions, not an accuracy benchmark.

The exact request “I have independece day at office can you suggest some chothes” was exercised with real Google ADK, Gemini Embedding 2, Firestore vector retrieval and Gemini whole-outfit assessment against the existing sample catalogue. Men's results used three different kurtas (rust, white and olive), neutral trousers and formal shoes, totaling **₹2,997, ₹2,397 and ₹2,797**. Women's results used two different green kurtas with neutral trousers and flats, totaling **₹2,897 and ₹3,097**. All used saved M/EU39 sizes and no owned clothes; neither response requested sizes again. Six actual text events were observed in each run. Total measured call times were **36.99s and 24.98s**; these are single observations, not latency guarantees. Product photographs were inspected as a contact sheet; metadata colours can differ from perceived colour in the photo, and no visual accuracy score is claimed.

These operator probes ran the changed local code against live Google services, before deployment. Temporary owner-scoped records were removed afterward. See [collected occasion results](live-occasion-results.json). The sample catalogue still contains 200 source records; 10 contradictory/children's records are excluded from adult shopping, leaving 190 visible records, 189 in stock. No source product or photo was deleted. The real wardrobe graph is retained for optional wardrobe-pairing requests; no graph uplift was measured in these catalogue-only probes.

Visual QA also caught an over-colourful deterministic outfit. The final rules favor neutral supporting garments and reject loud/checked office footwear. Distinct product names now identify each recommendation instead of repeated generic colour titles. No new image or video was generated in this release. Human-rated recommendation quality and coverage across arbitrary occasions remain unmeasured; the sample catalogue limits the available choices.

### Deployed verification

Both GitHub main-push Cloud Builds completed successfully. The backend build passed all 99 tests on Python 3.13. Ready revisions: frontend **flairify-web-00014-hdq** (source `7185105`, build `af389d05-6590-4163-b406-f7d395b33134`), API **flairify-api-00019-k8b**, worker **flairify-worker-00038-7wr** (source `5f8a362`, backend build `ecc75b4f-d77e-423e-b049-047c50de7e91`). The superseded backend build was cancelled before deployment. Web/API returned HTTP 200; unauthenticated worker access returned the expected 403.

A fresh account registered through the deployed browser, saved men/M/EU39/Bandra without optional style-memory consent, skipped photos and sent the exact typo-containing Independence Day request. Real Firestore retrieval returned 54 bounded candidates; real Gemini assessment produced three different kurta-based looks totaling **₹2,797, ₹3,097 and ₹2,797**, all catalogue-only with the saved size/store. The initial browser run passed its incremental text-rendering assertion before an Axe helper setup error. Visual checks resumed against the saved response with an explicit browser context; no additional model request was spent on that retry. A second timing-sensitive test assertion was corrected to wait for save completion and React state restoration; direct API readback had already confirmed the setting was saved.

The final deployed browser checks passed: Profile settings persisted, the wardrobe default survived refresh, the chat toggle could be turned off, the conversation restored, and checkout preselected M while requiring explicit review. Tested desktop/mobile Axe rules returned zero violations; the 393px mobile viewport had a 393px document width. Browser screenshots were inspected. The temporary Firebase account, 14 owner-scoped records and zero residual media were removed, with no remaining owner-scoped records. See [deployed results](live-occasion-deployed-results.json); the cleanup count in that file is authoritative.

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

## Customer interface cleanup — 13 October 2026

Frontend source `6bb611d` and backend source `1ca066d` remove presentation badges and redundant explanations across the shopping interface. Inventory provenance remains internal and documented; no retailer connection, stock, payment or generated-media capability was added by removing labels. Completed previews use current UI copy even when older result metadata contains obsolete sample labels.

Validation: 132 backend tests, 25 frontend logic tests, production compilation and 42 distinct desktop/mobile journeys passed (41 in the full run; the desktop fitting-room refresh test passed after fixing a test-helper readiness race, with both fitting-room variants rerun). Live Chromium checks covered Stylist, Inventory, My Wardrobe, Saved Looks, Fitting Room, My Orders, Profile and the Seller Studio access screen at 1440px and Pixel 7 widths. No demo/sample/mock badges, horizontal overflow or browser errors were observed; tested Axe WCAG A/AA rules reported zero violations on Stylist, Inventory and Profile. No paid model calls were made. Both temporary guest accounts and their 410 records including sessions were removed after setup validation and the live check. See [collected live interface results](live-interface-copy-results.json).

Cloud Build `2c263675-77e7-434a-b2fb-f937f079db87` and `14e3d0ac-6985-48f3-8d00-9a5ec8f89126` succeeded. Verified revisions were `flairify-web-00021-vv9`, `flairify-api-00025-5xg` and `flairify-worker-00050-z7f`.

## Voice navigation — 13 October 2026

Frontend source `292819d` and backend source `33b90f4` add an allowlisted ADK navigation tool, local back/origin history and duplicate-event protection. Opening another page retains the voice call, selected garments and active conversation. The automatic preview transition uses the same history. Navigation never grants permissions or itself purchases, changes preferences or generates media.

Validation: 145 backend tests (including 13 navigation cases), 28 frontend logic tests, production compilation and 20 targeted desktop/mobile browser journeys passed. The browser checks exercise preview-to-Stylist return, all customer page destinations, current selection retention, duplicate/invalid navigation events and the same active connection across screen changes. The broader 42-journey copy release was verified immediately before this change.

Real deployed Gemini Live verification accepted seven natural-language navigation requests: open Fitting Room, back to styles, open my closet, take me back, open the shop, go to Profile, and return where we started. Every destination matched and each screen appeared. The test used text input over the authenticated Live WebSocket, a silent simulated microphone, real Google tool calls and 1,246,590 native audio bytes. It used one connection, saved 16 messages, created zero image jobs and stopped microphone tracks on End. This verifies live natural-language routing and audio output; physical-device speech recognition was not newly tested. See [collected real-service results](live-voice-navigation-results.json).

Cloud Build `e992e9f8-fd2b-4117-90f0-fac8f44f4e3e` and `50666844-9ce3-4104-a7e0-fe234e5f350c` succeeded. All traffic was verified on `flairify-web-00022-mt2`, `flairify-api-00026-hw6` and `flairify-worker-00052-clt`.

The temporary Firebase test account and four owner-scoped records were removed afterward; zero QA owner records or media remained. Shared daily quotas were retained.
