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

## Deployed access checks

A temporary signed-in customer could not retrieve a draft image (404) or its protected metadata (403), and no draft appeared in the customer catalogue. After receiving a temporary owner role, the same QA account retrieved the real image bytes and current image-analysis metadata through the deployed API. The temporary account and grant were removed. Web/API health returned 200 and the private worker returned the expected unauthenticated 403. See [collected access results](photo-import-access-results.json).

## Image serving at catalogue scale

Product image authorization uses bounded document-existence queries for the matching image and viewer access, instead of reading the entire catalogue per thumbnail. These equality filters use Firestore index merging ([Google documentation](https://firebase.google.com/docs/firestore/query-data/index-overview)). The live customer, site-owner and listing-owner query paths were checked against the project. Private order-history access remains available for purchased items that are later archived.

## Completed import

All 15 folders were scanned and all 367 images were downloaded and byte-length checked. **365 private draft listings** have current Gemini image metadata, **8,871 validated tags**, and **730 verified stored source/crop image objects**. Two ambiguous layered outfits were held for human review and did not create products. All 200 pre-existing seller records remain unchanged, bringing the stored catalogue to 565 records (200 existing active entries plus 365 private drafts). None of the new drafts is published or included in customer search/checkout. Direct unauthenticated Cloud Storage access returned 403.

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
