# Importing an image-only clothing collection

The Drive collection supplied on 14 October 2026 contains 367 photographs in 15 folders.
The connected Drive API was used to list every direct folder and download the original
image bytes. All 367 downloaded byte lengths matched the observed Drive metadata.
Source JSON manifests provide Pinterest image/pin links for some collections, but no
seller prices, stock, verified materials or sizes. Source files and sharing were not edited.

## Preparation and provenance

`app.catalogue.image_import.prepare` uses the configured Vertex Gemini model to identify
one clearly visible primary garment per photograph. Dedicated shoe/bag/dress folders
constrain the selected category. Full outfits are not presented as one priced bundle.
The output includes a validated bounding box, visible description, confidence and
uncertainties. Unclear detections and invalid boxes are held for review. Titles and
descriptions are checked for unsupported material/performance claims. These crops are
original evidence, not generated reconstructions or segmentation masks.

Preparation writes a resumable local record under `prepared/<stable-product-id>.json`
and the evidence crop at the matching `.jpg` path. IDs derive from the Drive file ID,
not a potentially renamed filename. Records preserve the observed file metadata,
source pixel hash, model/version and structured `PhotoListing` output. The download
manifest is a JSON list containing `id`, `title`, `folder`, `url` and MIME metadata.
No bearer download links or customer images are committed to either public repository.

The importer checks image limits and exact decoded-image hashes before writing. It
never automatically merges products based on similar colour or category. Different
photographs of a potentially identical garment can remain distinct drafts; this import
does not establish real SKU identity or measure duplicate-grouping accuracy.

## Importing drafts

Run with a configured runtime identity or ADC; never commit account keys:

```sh
python -m scripts.import_photo_catalogue \
  --directory /path/to/staging \
  --manifest /path/to/drive-files.json \
  --requester OWNER_UID
```

The default checks and reports the files without writing. Add `--write` to import the
prepared records. The script verifies the requester is a configured site owner, limits
concurrent work to four items and saves checkpoints. Retrying reuses uploaded media,
existing listings and current analysis. Existing seller edits are never replaced.
Failed items are isolated in `import-result.json`; rerun after repairing the failure.

Media are copied to private Cloud Storage and retain original Drive source references.
Only owners and the listing's seller can access unpublished product photos. Original
Drive photographs remain unchanged. The stored source reference is normalized for
processing; the Drive file is the original-quality source.

Imported items start with `active=false`, `catalogue_status=draft`, no variants and no
established price. The internal numeric zero is a required-schema placeholder; Seller
Studio displays **Set price**. They do not enter customer search, recommendations or
checkout. Gemini enrichment can run on these private drafts. Confirmed price/size/stock
details must be entered before activation. Publishing through Seller Studio invokes the
normal enrichment/embedding pipeline; subsequent semantic changes are reanalyzed.

The images are user-supplied references from the named Drive collection. Their presence
in Drive does not establish retailer affiliation, current availability or a new asset
license. Brand names are not inferred from board titles, logos or watermarks. No claim
is made that these are live retailer feeds.

## Initial draft access checks

A temporary signed-in customer could not retrieve a draft image (404) or its protected metadata (403), and no draft appeared in the customer catalogue. After receiving a temporary owner role, the same QA account retrieved the real image bytes and current image-analysis metadata through the deployed API. The temporary account and grant were removed. Web/API health returned 200 and the private worker returned the expected unauthenticated 403. See [collected access results](photo-import-access-results.json).

## Image serving at catalogue scale

Product image authorization uses bounded document-existence queries for the matching image and viewer access, instead of reading the entire catalogue per thumbnail. These equality filters use Firestore index merging ([Google documentation](https://firebase.google.com/docs/firestore/query-data/index-overview)). The live customer, site-owner and listing-owner query paths were checked against the project. Private order-history access remains available for purchased items that are later archived.

## Initial staging audit

At the initial staging audit, all 15 folders had been scanned and all 367 images downloaded and byte-length checked. **365 private draft listings** have current Gemini image metadata, **8,871 validated tags**, and **730 verified stored source/crop image objects**. Two ambiguous layered outfits were held for human review and did not create products. All 200 pre-existing seller records remain unchanged, bringing the stored catalogue to 565 records (200 existing active entries plus 365 private drafts). At that audit, none of the new drafts was published or included in customer search/checkout. See the owner-authorized publication below for the subsequent activation. Direct unauthenticated Cloud Storage access returned 403.

| Category | New drafts |
| --- | ---: |
| Bag | 50 |
| Bottom | 53 |
| Dress | 51 |
| Jacket | 90 |
| Shoes | 58 |
| Top | 63 |

There are no failed or stale draft enrichment records at audit time. Physical metadata tags remain unknown because the image collection supplied no material/performance specifications. Photo-derived observations are labelled visual; suitability and pairing tags remain styling hypotheses. One transient analysis failure succeeded on retry. A sheet of 24 garment crops was visually inspected; no detection accuracy, calibrated confidence or duplicate-recall score is claimed. See [the final data audit](photo-import-audit.json).

The full access/health check was repeated successfully after deploying the bounded image lookup. Temporary QA identities were removed after each run.

## Owner-configured publication

After reviewing the missing commercial fields, the owner explicitly selected configurable
catalogue prices and all sizes for the existing payment-free shopping flow. The defaults
in [`config/photo-catalogue-pricing.json`](../config/photo-catalogue-pricing.json) are:

| Category | Price (INR) | Sizes |
| --- | ---: | --- |
| Top | 999 | XXS through 4XL |
| Bottom | 1,299 | XXS through 4XL |
| Dress | 2,499 | XXS through 4XL |
| Jacket | 2,299 | XXS through 4XL |
| Shoes | 1,799 | 35 through 48 |
| Bag | 1,499 | One size |

Each variant is configured with quantity 20 at the existing Bandra and Lower Parel stores.
These are owner-configured commerce settings, not availability, size ranges or prices
recovered from photographs or a retailer feed. No aisle, delivery promise or material is
invented. Payment-free orders retain the existing behavior: saved order, no payment,
shipment or stock reservation. Individual prices and stock can be changed in Seller Studio.
The configuration file supplies defaults for future batches; it does not overwrite existing
seller changes when rerun.

Publish an explicit JSON list of imported product IDs using the approved policy:

```sh
python -m scripts.publish_photo_catalogue \
  --product-ids /private/imported-product-ids.json \
  --requester OWNER_UID
# Review the dry-run counts and policy, then apply with a private backup:
python -m scripts.publish_photo_catalogue \
  --product-ids /private/imported-product-ids.json \
  --requester OWNER_UID \
  --backup /private/before-publication.json --write
```

The operator must have Google Cloud data access and identify a configured website owner.
The script only activates that owner's untouched, successfully analysed photo drafts.
Existing price or stock edits, or semantic changes without current analysis, stop
validation rather than being replaced. A compare-before-write transaction rejects concurrent edits. Original records
are saved outside the repository before publication; published records are skipped on retry.

The original image analysis is reused because adding prices, sizes and stock does not
change visual evidence. Variant colour repeats the exact colour already analysed in the
listing. A guarded semantic comparison verifies that all remaining facts and the image
are unchanged. Cache audit records preserve the previous fingerprint and reuse reason;
assessment dates, evidence, confidence and usage remain unchanged. Later changes to
colour, title, description or image still invalidate analysis normally.

Publication clears the draft state and queues deterministic, resumable index jobs in
batches of 100. Jobs generate Gemini Embedding 2 vectors and current price/stock facets
using the normal worker. No AI quota counters or concurrency limits are increased.

## Published result — 14 October 2026

All **365 imported products are active and indexed**, with **3,175 variants**, all configured
sizes, and stock at both existing stores. The catalogue contains 565 records and 565
current Gemini Embedding 2 vectors. Customer browsing returns 555 products: all 365
new listings plus 190 existing listings passing the pre-existing quality filters.
The 200 original commercial records were not changed. Two ambiguous source photos
remain excluded. See [publication audit](photo-publication-audit.json).

Four Cloud Tasks indexing jobs succeeded without errors. They generated 365 normalized
768-dimensional embeddings and reused all 365 image analyses, preserving 8,871 tags
with their evidence, confidence and assessment dates. The audit checked every new
product hash, vector hash, model space, metadata hash, price, size, stock and search facet.
No additional image-analysis calls were made during publication.

A temporary signed-in customer verified the deployed behavior:

- Inventory returned all 365 new products; an imported photo was served successfully.
- Semantic search found the requested imported evening gown and 16 new products among
  18 results. This is a functional retrieval check, not a relevance benchmark.
- A dress-and-shoes order totaling **₹4,298** was saved without payment and appeared
  in the seller order projection. Repeating the same request reused the existing order.
- The streamed stylist returned three evening wedding-guest outfits, each **₹4,298**,
  using five distinct newly imported products. Every product ID, size, store, current
  price and stock was checked. The response used Firestore vector search, Gemini
  Embedding 2 and Gemini outfit assessment, with six text events in 23.02 seconds.
- Direct unauthenticated Cloud Storage access remained 403; customer access to protected
  admin metadata remained 403. Web/API health returned 200; the private worker returned 403.

The temporary account, saved test order and seller projections were removed afterward.
No stock was changed. See [live checks](photo-publication-live-results.json).

**213 backend tests passed locally and in Cloud Build.** All changed Python files passed
Ruff. A repository-wide Ruff scan still reports 118 findings in unchanged files; those
were not included in this catalogue change. No frontend source changes were needed.

Cloud Build `01d4e96d-2975-4ed6-b7ff-eb38629e4de0` succeeded for backend commit
`8ae0815`. The API revision `flairify-api-00036-9pk` and private worker revision
`flairify-worker-00072-22g` were verified on that image with 100% traffic.
