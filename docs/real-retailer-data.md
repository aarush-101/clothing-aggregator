# Product sources and access research

Audience: whoever decides which data sources this product ships with.

## Summary

As of **2026-09-23**, the accepted direction is a persistent menswear product
index populated by background ingestion, with searches reading indexed data.
Sources can include retailer/affiliate feeds, supported APIs and accessible
product pages. Shopping/web-search services supplement discovery. See
[product-index.md](product-index.md) for the architecture and delivery plan.

**No live source is configured by default, and the index and ingestion workers
are not implemented.** The earlier eBay-first recommendation is retired; this
project does not depend on an eBay account or integration. Source credentials
and commercial arrangements depend on the chosen access method, not on a
universal account requirement for aggregation.

---

## Historical Shopify access findings

The previous research, recorded on 2026-09-22, reported probes of Shopify's
public `/products.json` endpoint with the following results. These measurements
have not been independently rerun as part of the architecture revision.

| Result | Count |
| --- | --- |
| Domains tested | 213 |
| Serve a public `products.json` | **93** (verified, currency/country read from each store's `/meta.json`) |
| Accept our server-side HTTP client | **0 of 93** |

The report recorded `HTTP 429` with `cf-mitigated: challenge` from the Python
client, while a different client could retrieve data. This establishes a
failure of that endpoint/client/deployment combination; it does not establish
that every product page, supported API or feed is inaccessible.

Recheck representative sources in the intended deployment environment and
record the endpoint, client, status, access method and date. Do not treat
changes in client behaviour as a guarantee of durable access. The 93-store list
remains a research artefact, not validated live coverage. The Shopify connector
is retained with offline tests and remains disabled by default.

---

## Source options to validate

| Source | Intended role | Work still required |
| --- | --- | --- |
| Retailer or affiliate JSON/XML feed | Scheduled product/offer ingestion | Obtain access where required; validate field mapping, full-snapshot scope, pagination, variants and update/deletion semantics |
| Supported retailer API | Structured inventory and targeted verification | Confirm merchant access, coverage and limits; implement an adapter |
| Accessible product pages | Discover or enrich product information | Validate access and structured data per retailer; current HTML connector requires configured permission |
| Shopping/web-search API | Discover products and retailers beyond existing integrations | Benchmark a provider, initially Serper; validate purchase links, costs and storage conditions; keep unverified details explicit |

No listed route has been proven end to end in Marle's planned indexed mode.
Authentication does not guarantee complete inventory or freedom from access
limits. Search-result absence is not a product deletion signal. A current price
also does not establish availability in the requested size or destination.

---

## Recommended sequence

1. Benchmark a representative retailer sample serving Australia. Record usable
   product fields, freshness, working links, access failures and request cost.
2. Select a validated source and implement persistent, idempotent ingestion.
3. Query the index through the existing search experience, with unknown stock
   and shipping represented explicitly and freshness visible.
4. Add scheduled refreshes, complete-snapshot reconciliation, expiry and source
   cooldowns. Verify that failed imports do not delete prior inventory.
5. Expand source coverage and discovery using measured gaps. Keep fictional
   products restricted to explicit demo/test mode.

## What is already built and waiting

| Piece | State |
| --- | --- |
| Generic JSON/XML feed connector | Implemented with offline tests; mapping and snapshot handling need source-specific validation. |
| Shopify connector | Implemented with offline tests; disabled by default. |
| Store discovery list (93 stores, currency + country) | Historical research in `app/data/shopify_stores.json`; not current access validation. |
| Per-store caching and cold-fetch budget | Implemented for the current search-driven Shopify connector. |
| Department filtering | Implemented; live-data quality remains unmeasured. |
| Cross-currency comparison | Implemented with static rates; live rates remain outstanding. |
| Affiliate click tracking and sub-ids | Implemented; actual retailer integration remains to be validated. |
| Persistent product/offer index | Not implemented. |
| Ingestion worker and scheduler | Not implemented. |
| Indexed search and freshness-aware UI | Not implemented. |

The existing pipeline provides reusable pieces, but a persistent aggregator
requires new storage, ingestion and search behaviour. It is not a config-only
change.
