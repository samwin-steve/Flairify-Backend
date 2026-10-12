# Semantic retrieval, Google ADK and streaming

## Decision

Firestore provides online catalogue RAG. It already holds Flairify's current catalogue and user state, supports native vector queries and avoids a second serving system or always-on vector infrastructure. Gemini Embedding 2 produces normalized 768-dimensional document and query embeddings through **Vertex AI**, using runtime Google service identities.

BigQuery **WardrobeGraph** supplies a second, bounded retrieval signal: which semantically shortlisted products occur in distinct, previously checked whole outfits using the current confirmed wardrobe and occasion. A real property graph connects Customer → Owns → Garment ← Wears ← Outfit → Adds → Product. The online query uses the shorter Garment ← Wears ← Outfit → Adds → Product traversal with the owner bound on every node; the current wardrobe fingerprint establishes ownership validity. Firestore remains authoritative for stock, size and price. Graph counts influence tie-breaking and “most outfits” ranking; they never bypass full outfit validation. No relevance uplift is claimed without a labeled evaluation.

The graph is populated by asynchronous `graph_sync` Cloud Tasks after checked outfits are saved. It stores IDs, wardrobe fingerprints, occasion and assessment provenance; no portraits, garment names or conversation text. Stable outfit signatures ensure repeated recommendations count once. Owner keys occur on all nodes and edges; queries bind the verified owner and current wardrobe fingerprint. Wardrobe edits immediately exclude stale evidence and queue projection cleanup. An empty snapshot deletes that customer's graph rows, even if the generation/query allowance is exhausted.

## Modules and flow

- `app/rag/embeddings.py`: document/query formatting, Google model invocation, model/version/dimension hash, normalization and daily quota.
- `app/rag/repository.py`: atomic vector publication and owner-scoped Firestore KNN queries.
- `app/rag/retrieval.py`: retrieval boundary; honest local/demo attribute baseline.
- `app/rag/query_plan.py`: category-specific queries grounded in the occasion and retained garments.
- `app/services/conversation_context.py`: own-conversation look references, ordinal resolution, grounded discussion and replacement slots.
- `app/rag/wardrobe_graph.py`: parameterized BigQuery Graph traversal, coverage evidence and idempotent owner snapshot synchronization. One compact table holds complete looks; BigQuery views expose typed graph nodes and edges, so each update requires one atomic MERGE rather than many separate writes.
- `app/agents/stylist.py`: Google ADK `LlmAgent`, `Runner`, Gemini and streamed partial events.
- `app/agents/tools.py`: read-only tools bound to the verified customer: confirmed wardrobe, semantic outfit candidates, retrieved product details and current variant availability.
- `app/prompts/stylist.py`: versioned instructions separate from untrusted product/customer text.
- `app/services/recommendations.py`: whole-outfit construction and authoritative budget, ownership, size, department and stock validation.
- `app/services/chat.py`: durable conversations, request deduplication, per-customer turn lock, error handling and streaming lifecycle.
- `app/utils/events.py`: SSE framing.

ADK interprets the current message and role-based conversation history, then chooses discussion or `find_outfit_candidates`. Category-specific semantic queries include the occasion and retained garment context. An outfit searches four relevant categories by default; a shoe replacement searches shoes only. Retrieval uses up to 16 vector hits per category, or 32 for variations, plus two affordable alternatives. A bounded 128-entry, 10-minute in-process cache reuses query vectors by catalogue owner, model space and text hash. Product facts are never cached by this mechanism. Serving records are reread before constructing and validating combinations. ADK explains the checked results. Product cards always come from backend records, never model-generated JSON. The agent has no purchase, generation, arbitrary URL, SQL, shell or preference-write tool.

The ADK session is isolated to one execution. The application conversation and active intent in owner-scoped Firestore are durable; the last 12 messages are replayed as ADK user/model events, with compact latest/selected look records, the active brief and up to 12 earlier customer requests as grounding. Transient ADK tool events are not a second persistent conversation store. Long-term preferences still require consent. The existing non-streaming `/api/chat` route runs the same ADK flow.

## Indexing

Seller add, edit and import already enqueue Cloud Tasks. Each index task processes at most five products and checkpoints before requeuing, keeping requests within the worker timeout. Only changed semantic text calls the embedding model. Text includes name, brand, description, category, retailer attributes (colour, styles, department and supplied details) and variant colours. Stock, price and size are structured filters; their edits refresh filters and reuse the vector. AI suggestions are not promoted into retailer facts.

`flairify_vectors` stores catalogue owner, product ID, semantic hash, model space, timestamp, price, active flag, eligibility facets and a native Firestore Vector. Publication transactionally checks that the product has not changed during embedding and writes the indexed flag with its matching projection. Concurrent stale jobs cannot publish over a newer edit. Edited products are temporarily unindexed until their new projection is ready. Inactive products have their projection removed.

Each category returns at most eight nearest candidates plus two affordable alternatives. Filtering happens before KNN: owner, model space, category, department, supplied store, size, positive projected stock and individual price ceiling. At most 70 product point reads feed outfit construction; no full catalogue scan occurs for online recommendations. Prices, availability and the combined purchase cost are checked again on serving records. This is a bounded shortlist, not exhaustive enumeration of every possible wardrobe combination. Empty-query inventory browsing and admin/migration listing still list products; they are separate from recommendation retrieval.

No embeddings are fabricated without credentials. Anonymous demo catalogues retain an explicitly identified deterministic attribute baseline and never consume paid AI. A live embedding/index failure returns a clear unavailable error rather than silently scanning the catalogue.

## Setup and migration

1. Enable Vertex AI, Firestore and the existing Cloud Tasks/Run services. API and worker identities need existing `roles/aiplatform.user` and `roles/datastore.user` permissions. No new outside service is required. BigQuery API access uses project `roles/bigquery.jobUser` for API/worker plus dataset reader (API) and writer (worker) grants.
2. Set `EMBEDDING_MODEL=gemini-embedding-2`, `EMBEDDING_LOCATION=global`, `EMBEDDING_DIMENSIONS=768`, `MAX_DAILY_EMBEDDINGS=1500`, and `ENABLE_PAID_AI=true`. Gemini chat uses `GEMINI_MODEL` and `GEMINI_LOCATION` separately.
3. Apply `infra/firestore.indexes.json` with Firebase, import/apply Terraform's two index resources, or run `python scripts/configure_vector_indexes.py` with the operator's gcloud login. Wait for both indexes to be READY. Do not create duplicates through several mechanisms.
4. With application default credentials and the configured named database, run `python -m scripts.backfill_embeddings`, or use Seller Studio's reindex action. This one-off migration intentionally scans the catalogue. Re-running skips unchanged vectors. No stock/retailer edits are replaced.
5. Run `python -m scripts.configure_graph` with operator ADC to create the actual property graph and dataset grants from `infra/wardrobe-graph.sql`. Grant the API/worker project `roles/bigquery.jobUser` (or use bootstrap with `ENABLE_BIGQUERY=true`). Set `ENABLE_BIGQUERY=true`, `BIGQUERY_DATASET=flairify`, `MAX_DAILY_GRAPH_QUERIES=300`. No reserved slots or GPU are created. Queries have a 100 MB billing limit and a 15-second job timeout; background graph writes have a 60-second job timeout. Runtime query failures omit graph evidence explicitly and keep semantic search usable. First-time users have no historical graph evidence until their first checked outfits have synchronized.
6. Deploy API/worker and frontend with the repository Cloud Build triggers. Cloud Build sets the embedding model, dimensions and region explicitly. The old `flairify_search` projection is no longer queried; it may be removed in a separate migration after any rollback window.

Changing dimensions or document schema requires a new model space, matching indexes and backfill before switching traffic. The model does **not** support legacy `task_type`; document and query task instructions are included in the input text instead. A failed provider call consumes an attempted-call quota unit, so retries cannot bypass the daily guard. Billing alerts are not spending caps.

## Streaming contract

Authenticated `POST /api/chat/stream` accepts `ChatRequest` plus optional `request_id`. Events are `start`, `status`, `outfits`, `text` (delta), `done` (full persisted result), and `error`. Comments keep connections alive. Real text deltas are forwarded from ADK/Gemini; the deterministic demo emits one block and never simulates model typing. Unchecked pre-retrieval model text and hidden thought parts are suppressed.

The UI reveals newly received words with a subtle fade and a typing cursor; reduced-motion settings disable animation. Next.js passes the response body through without buffering, with `no-transform` and request cancellation. The browser decodes fragmented UTF-8/SSE, handles provider errors or truncated connections, removes incomplete messages on failure and retains the message and request ID for retry. A repeated completed request returns the saved result without another model call. New conversations/history switching are disabled while a turn is running. Sign-out aborts the stream. Conversations reload normally after completion.

A per-user lease prevents concurrent turns from overwriting history. The stream has a 105-second deadline; disconnects cancel the ADK run. A terminated instance's stale lease expires in 150 seconds. Automatic network retry is deliberately avoided. Partial responses are not presented as completed answers. Cached results are cleared of recommendation cards when wardrobe records are changed/deleted.

Wrapped Vertex AI capacity errors (429) display a clear busy/retry message; deadline failures have a separate timeout message. Error classification walks typed exception causes without exposing provider payloads. Failed turns release their lease and keep the request key available for customer-initiated retry; no successful result is invented.

## Official references

- [Gemini Embedding 2 model](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/embedding-2)
- [Embedding 2 retrieval instruction formats and dimensions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/embeddings/get-multimodal-embeddings)
- [Firestore vector search and composite indexes](https://firebase.google.com/docs/firestore/vector-search)
- [BigQuery Graph creation](https://docs.cloud.google.com/bigquery/docs/graph-create)
- [BigQuery Graph query syntax](https://docs.cloud.google.com/bigquery/docs/graph-query-overview)
- [ADK run configuration and SSE streaming](https://google.github.io/adk-docs/runtime/runconfig/)

Measured deployment results are recorded separately in `VERIFICATION.md`; semantic relevance uplift and graph ranking uplift require a labeled evaluation set and are not claimed.

A live test of the longer Customer-to-Product traversal hit BigQuery internal error 80038528. The shorter two-edge traversal avoids that path. BigQuery SDK automatic job resubmission is explicitly disabled to keep error handling and cost bounds effective.

## Conversation refinement

`ChatRequest.reference_outfit_id` is optional and must belong to the authenticated customer's current conversation. **Refine this look** sends it explicitly; the service also resolves first/second/third look references. Replacing shoes locks the rest of that look, rereads their current availability and excludes the old shoe product. General variations change the main piece; broad different-options requests can build fresh outfits. A missing retained size or item returns no replacement rather than secretly swapping the garment. Multi-slot edits use a beam capped at 96 partial combinations. Whole-outfit Gemini assessment and final budget/stock checks remain mandatory in the live recommendation path (with the existing explicit assessment fallback).

`discuss_current_looks` supports explanations and comparisons using retrieved product facts, without generating more cards or querying embeddings. The latest look remains available after discussion-only messages. The browser restores the last selected conversation after refresh and can open all previous chats; New conversation starts independently. Only the selected conversation ID is stored in localStorage. Messages remain in owner-scoped Firestore. Signing in clears the previous session's visible history and query cache before loading the authenticated customer's history.

The new moving pink/lilac background, response word animation and message transitions respect reduced-motion preferences. Completed outfit cards appear after the streamed reply, so they do not displace the text while it arrives. The wardrobe mode is a keyboard-accessible composer menu. No voice control is displayed without a functioning recording feature.

ADK session event contracts were checked against [Google's session documentation](https://adk.dev/sessions/session/). Gemini Embedding 2 keeps the documented [asymmetric query/document instructions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/embeddings/get-multimodal-embeddings); no embedding-model migration or reindex is required for this query-side change.
