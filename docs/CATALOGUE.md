# Expanded sample catalogue

## Contents and provenance

200 products: 90 men’s, 91 women’s, 19 unisex. 199 have simulated availability; the existing sold-out jacket remains unavailable for verification. All sample clothing has XXS, XS, S, M, L, XL, XXL, 3XL and 4XL; shoes have EU 35–48; accessories/bags have one size. Both sample stores carry these variants. Prices, sizes, stock quantities, store positions and delivery eligibility are explicitly sample data. No live Myntra integration or manufacturer sizing claim is made.

- **8 women’s products** use the `img` references in Hitesh Suthar’s [Myntra Fashion Product Dataset](https://www.kaggle.com/datasets/hiteshsuthar101/myntra-fashion-product-dataset), publisher-declared [ODC PDDL 1.0](https://opendatacommons.org/licenses/pddl/1-0/). The CSV’s unnamed index repeats across categories and archive image numbers do not reliably identify products. We therefore download the exact original HTTPS image URL supplied in each selected row, restricted to `assets.myntassets.com`, rather than guessing a filename.
- **182 men’s, women’s and unisex products** use Param Aggarwal’s [Fashion Product Images Dataset](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset), publisher-declared MIT. Metadata comes from its [small dataset sibling](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small); photos come from the full-resolution original files. The low-resolution thumbnails are not used.
- **10 existing sample records** remain, with their original Unsplash/Pexels photos or original garment illustrations. Their existing attribution is retained.

`fixtures/catalogue-sources.json` records each new photograph’s source ID, original dataset/file or image reference, department, category and declared license. `fixtures/image-credits.json` and the frontend’s `public/image-credits.json` include all media credits. The declarations are the dataset publishers’ stated terms, not independent verification of all underlying retailer image rights or trademark permissions. No retailer endorsement is implied. Review image rights again before repurposing this hackathon sample catalogue for a commercial retailer launch.

Photos are validated with Pillow, orientation-corrected, resized to at most 900×1100 and stored locally in both repositories. The app does not depend on third-party hotlinks. No product-image generation is involved. The eight requested CSV photos are three tops, three dresses and two trousers; bundled multi-piece sets and children’s products were excluded.

## Rebuild and migration

Run `PYTHONPATH=. .venv/bin/python scripts/expand_catalogue.py` from the backend, with the frontend checked out beside it. Public selected-file downloads require network access but no Kaggle credentials. Metadata is cached under ignored `.data/catalogue-source`. The full multi-GB archives are never downloaded. Selection, prices and sizes are deterministic; validation timestamps are regenerated. Existing downloaded images are reused.

A version marker upgrades existing anonymous and shared demo catalogues on profile/catalogue access. Missing fixtures are created in batches without overwriting concurrent seller records. Untouched legacy fixtures receive wider sample sizes; modified legacy prices, stock or attributes are preserved. Subsequent reads do not restore intentionally edited/deleted stock. Real seller listings never acquire artificial variants.

## Matching fixes

Search no longer discards whole product categories behind a global 60-result cutoff. Recommendation candidates are bounded independently by category and include low-price alternatives. A confirmed shirt can be completed with a new bottom and shoes; a confirmed jacket can anchor a new base. Requests for new shirts/bottoms can also fill the opposite missing piece from stock. Arbitrary owned garments are no longer inserted as duplicate base layers. Explicit jacket requests are not silently dropped to meet budget.

Departments are customer-selected, never inferred from a face or body. Women’s/men’s selections include unisex records. Sizes are editable in the stylist and shared with onboarding. Store information is read once per recommendation rather than once per product. Current size/stock/price checks still run immediately before returning a result; failure explains missing categories or a combined-cost mismatch. Rankings remain a bounded rule-based shortlist with optional Gemini assessment, not measured fashion-quality guarantees.

## License notice for the MIT-declared dataset

Attribution: Param Aggarwal, Fashion Product Images Dataset. The dataset page declares MIT but supplies no separate copyright year in the retrieved metadata; no year is invented here.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
