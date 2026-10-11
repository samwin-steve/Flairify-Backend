# Flairify — a little more you

**Promise:** Share your wardrobe once. Find pieces that work with your life—and see the look on you.

## Retail problem

Product-led shopping often ignores what a customer already owns. A recommendation can look appealing alone yet duplicate existing clothes, exceed the total outfit budget, or fail to suit everyday plans. Retailers also need recommendations tied to actual size and store-level stock.

## Customer value

Flairify builds a confirmed digital wardrobe before the first personalized conversation. Customers describe a trip, occasion or budget; the app combines owned garments with available catalogue products, explains whole-outfit choices, and keeps ownership, new spend and availability visible. The customer corrects every wardrobe inference and controls photos, preferences and generated media. There is no urgency language or forced upselling.

## Differentiation

- Wardrobe confirmation is a real application gate, not a marketing promise.
- Budgets apply to the combined cost of new pieces, with backend size and stock checks.
- Compatibility relationships carry provenance and uncertainty; graph coverage means distinct assessed outfit combinations, not every theoretical pair.
- Product and wardrobe data ground the experience. Rule-based demo, configured providers and experimental 3D have distinct labels.
- On-demand previews and motion jobs have persistent state and truthful error handling. A failed provider request never becomes a fake success.

## Google Cloud usage

Next.js and FastAPI deploy independently to Cloud Run from two GitHub repositories through Cloud Build push triggers. A private Cloud Run worker receives OIDC-authenticated Cloud Tasks. A dedicated Firestore database and private Cloud Storage bucket retain application and media state. Gen AI SDK adapters target Vertex Gemini, Google virtual try-on and Veo. BigQuery schemas and bounded SQL support catalogue embedding projections and relationship analysis. Firebase Authentication verifies production identities; Google Photos Picker requires separate user authorization. Artifact Registry stores images. Runtime identities avoid downloaded service-account keys.

## Prototype scope

Working deterministic journey: onboarding, sample/direct-upload review, confirmed wardrobe persistence, grounded budget/stock recommendations, follow-ups, saved looks, protected inventory editing/import, durable job states and sample 3D viewing. Signed-in Firebase accounts can additionally use live Gemini photo extraction, intent interpretation and tool-assisted whole-outfit assessment, verified with a licensed public sample photo. Deployed catalogue data remains clearly synthetic. Separate Google Photos OAuth setup, verified retailer feeds, live image/video provider validation, semantic/graph evaluation and personal-avatar reconstruction have documented limitations. No uncollected accuracy or business-lift figures are claimed.
