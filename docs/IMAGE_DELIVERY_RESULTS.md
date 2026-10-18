# Image delivery verification — 18 October 2026

The latest source was pulled before changes: backend `005342e`, frontend `d5b7285`.
The release preserves those shopping-preference, preview, analytics and interface changes.

## Collected live measurements

| Measurement | Before | After |
| --- | ---: | ---: |
| Initial Inventory JSON | 1,902,059 bytes / 555 products | 83,061 bytes / 24 products |
| Initial request duration, one run each | 11.117 seconds | 3.584 seconds |
| Same 12 product photographs | 809,073 bytes | 174,856 bytes |
| Median image request, same 12 | 0.863 seconds | 0.546 seconds |
| Four-concurrent image batch | 3.006 seconds | 2.078 seconds |
| Repeated image in a real Chromium browser | Previously no-store | 1.5 ms / zero transferred bytes |

The initial JSON shrank **95.63%**; the same 12 photographs shrank **78.39%**.
These are collected functional checks, not a controlled latency benchmark or an
instant-first-visit guarantee. Network conditions, warm/cold instances and SDK
initialization affect timing. Repeated browser loading was measured directly:
first 433.2 ms / 13,830 transferred bytes; second 1.5 ms / zero transferred bytes,
with both reads returning the same 13,530-byte WebP image.

All **365 active uploaded catalogue images** were prepared as 384px WebP without
errors: 26,407,072 source bytes versus 4,273,444 thumbnail bytes (**83.82% less**).
This used Pillow and the existing private Storage bucket, without AI model calls.
The original files were preserved. New product indexing prepares thumbnails too.
The welcome image optimizer returned a valid 640px WebP of 33,704 bytes.

## Functional and privacy checks

- Real deployed first/next pages returned distinct product IDs; category/department
  filtering remained correct. A selected-ID checkout read fetched 12 products in
  45,812 bytes / 0.660 seconds rather than reading the entire catalogue.
- Actual authenticated image responses carried private five-minute caching,
  Authorization variance and ETags through the Next.js proxy. Conditional
  revalidation returned 304. The original JPEG remained downloadable.
- A real browser cache hit transferred no bytes. The same URL without Authorization
  returned 401, including after its authenticated variant was cached.
- Temporary Firebase test accounts were removed; no profile, generation or order
  was created in production by these checks.
- Unit tests cover private media ownership, original-byte preservation, derivative
  reuse, bounded memory/widths, deletion during transformation, deletion of warm
  images, archive rechecks before 304, owner-scoped reads, cursor validation, missing/duplicate products,
  stock changes, exact-name searches, queue limits and cancelled requests.
- **235 backend tests**, **48 frontend logic tests**, TypeScript checking and the
  production build passed. Cloud Build independently passed the tests/builds.
- **28 distinct targeted desktop/mobile browser cases passed across reruns**:
  account entry/new chats, direct checkout, seller upload/indexing/stock/order flow,
  filters/pagination, recommendation cards, preview selection, image retries,
  cache reuse and deletion. Viewport screenshots were inspected; the image journey
  had no horizontal overflow. These use local fixtures/emulation, not physical
  phone or mobile-network measurements.

Two old image-cache tests used a fixed number of microtasks and also failed in the
preceding frontend Cloud Build. They now wait for the observable completed download.
Commerce selectors/count assertions were updated for the pulled interface and
paginated loading. During implementation a seller search exposed a genuine edge
case: availability filtering could replace an exact sold-out listing with unrelated
results. Exact-name retrieval now precedes availability filtering; its regression
and seller journey pass. The final test suite passes without those failures.

## Deployed release

Backend commit `dc697eb`, Cloud Build `84f71e5e-d237-48c5-90e8-4ba4b9157f6d`: SUCCESS.
API `flairify-api-00038-wt7`, private worker `flairify-worker-00076-4tl`, both verified
on that build image with 100% traffic. Superseded build
`2962973c-c0b8-4a91-8932-6e8711c4feba` for our earlier commit was cancelled before
its replacement to avoid a redundant rollout.

Frontend commit `1a95d56`, Cloud Build `70a14541-4022-422d-9986-6b31d20f6680`: SUCCESS.
Web revision `flairify-web-00031-7qp` was verified on that build image with 100% traffic.
No Redis, CDN, GPU or additional cloud services were created. Existing scale-to-zero
and concurrency limits remain in place.

Evidence: [before](image-delivery-before.json), [after](image-delivery-after.json),
[thumbnail preparation](image-thumbnail-preparation.json), [design](IMAGE_DELIVERY.md).
