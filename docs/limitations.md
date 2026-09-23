# Current limitations

The initial implementation searches real, stored retailer inventory. Its
coverage and operational limits remain explicit.

- **50 Australian Shopify stores** (see the registry). Only public Shopify
  collection JSON is supported, so non-Shopify retailers (THE ICONIC, UNIQLO,
  Country Road, Rolla's, Wrangler) are not covered. Stores whose robots rules
  block paginated collection URLs (Culture Kings, Surf Dive 'n' Ski) are excluded. Marle does not use affiliate links or feeds.
  There is no automatic search across the whole internet.
- **Observed availability:** imports are periodic. Retailer checkout is the
  authority for current prices, stock and shipping. An AU storefront does not
  establish delivery to every destination. Shipping costs remain unknown.
- **Size and colour:** variants are kept separate, but size systems are not
  converted between brands. General searches list sizes at the displayed price;
  a different-priced size requires a size-specific search. Colour/material
  extraction relies on retailer options and text, not image recognition.
- **Snapshot scope:** coverage is the configured men's collection, not a claim
  to every item on a retailer's site. Pagination is not a transactional snapshot
  of the retailer: repeated IDs are detected, but inventory can change during an
  import. Long-term removal accuracy needs operational monitoring.
- **Access changes:** public endpoints and robots rules may change or become
  unavailable. Sources pause on failures/challenges and retain unexpired data.
  The successful local check is not evidence of unlimited or permanent access.
- **Ranking:** deterministic lexical matching and approximate currency
  conversion through static rates. No semantic/vector search or live FX.
- **De-duplication:** matches need the same brand, the same normalised title and
  the same colourway (or a shared image filename). There are no barcodes in the
  public Shopify data, so stores that name a product differently (“Levi's 568
  Loose Straight Jean The Midnight Blues Show” vs “568 Loose Straight Jeans”)
  are not merged. 696 of ~31,500 in-stock colourways currently merge.
  Marle does not use affiliate links or feeds, so matching relies on names.
- **Brand recognition** uses the brands present in the index. A brand whose
  name is also a garment/colour/material word is not recognised from a prompt.
- **Scale:** SQLite is for local/small deployments. PostgreSQL migration support
  exists; a hosted PostgreSQL deployment and high-concurrency load have not been
  benchmarked. SQL filters narrow candidates; relevance and grouping still run
  in Python, so very broad prompts take up to ~1.2 s locally. Keyword-only
  prompts scan `search_text` with `LIKE`; full-text indexing would help at scale.
- **Shopify rate limits** apply per client IP across all Shopify stores. One
  429/challenge pauses the whole import round. With 50 stores a full refresh
  takes roughly 20–30 minutes at the 2 s default spacing.
- **Streaming:** the event broker is in-process. Multi-instance deployments need
  session affinity; Redis does not yet carry live events between API instances.
- **Operations:** there is no admin UI, metrics dashboard, automated access
  review, or run-log retention job. Inspect `/api/retailers` and `ingestion_runs`.
- **Accounts:** anonymous device sessions, saved searches and favourites work.
  Email/password sign-in, checkout, payments and alerts are outside this change.

Tests use isolated offline fixtures. Live imports and the dated report are
separate checks. See [live-validation.md](live-validation.md).
