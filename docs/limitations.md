# Current limitations

The initial implementation searches real, stored retailer inventory. Its
coverage and operational limits remain explicit.

- **Eight sources:** Assembly Label, Academy Brand, Industrie, Universal Store,
  Incu, Highs and Lows, Up There and General Pants Co. THE ICONIC, UNIQLO, Country Road, AS Colour and Cotton On
  have no adapter (they are not Shopify stores; affiliate product feeds are the
  realistic route). There is no automatic search across the whole internet.
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
  are not merged. Only 52 of ~9,400 in-stock colourways currently merge.
  Barcode (GTIN) data from affiliate feeds would be the reliable fix.
- **Brand recognition** uses the brands present in the index. A brand whose
  name is also a garment/colour/material word is not recognised from a prompt.
- **Scale:** SQLite is for local/small deployments. PostgreSQL migration support
  exists; a hosted PostgreSQL deployment and high-concurrency load have not been
  benchmarked. SQL filters narrow candidates; relevance and grouping still run
  in Python, so very broad prompts (“jeans”) take up to ~0.8 s locally.
- **Streaming:** the event broker is in-process. Multi-instance deployments need
  session affinity; Redis does not yet carry live events between API instances.
- **Operations:** there is no admin UI, metrics dashboard, automated access
  review, or run-log retention job. Inspect `/api/retailers` and `ingestion_runs`.
- **Accounts:** anonymous device sessions, saved searches and favourites work.
  Email/password sign-in, checkout, payments and alerts are outside this change.

Tests use isolated offline fixtures. Live imports and the dated report are
separate checks. See [live-validation.md](live-validation.md).
