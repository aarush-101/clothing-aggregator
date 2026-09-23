# Product index and background ingestion

Decision date: **2026-09-23**. Status: **accepted direction; not implemented**.

Marle will maintain a searchable menswear index and refresh it independently of
shopper searches. This supersedes the original restrictions against a stored
catalogue and scheduled crawling. The running prototype still uses connectors
on demand and returns demo data by default.

## Product scope

A shopper describes what they want, receives relevant products from multiple
retailers, and follows a link to the retailer to buy. Keeping a product index
does not require Marle to handle checkout, payments or fulfilment. There is no
dependency on an eBay account or eBay inventory.

Begin with a representative set of menswear retailers serving Australia. Grow
coverage through retailer integrations, accessible product pages and external
search discovery. Treat worldwide coverage as an expansion goal, not a launch
claim. Measure which retailers and product categories are actually covered.

## Why change the constraint?

Jora documents both website crawling and XML/JSON feed ingestion. It stores job
identifiers in a database, refreshes feeds every 2–24 hours and removes expired
listings. That supports separating collection from search; it does not imply
that every source is accessible or that collection never fails.
See [Jora's integration guide](https://support.jora.com/hc/en-us/articles/13919677306383-Get-your-jobs-published-on-Jora-with-an-XML-feed).

The proposed Marle design is inspired by that pattern. Its refresh schedules
must reflect product volatility and each source's limits, rather than copying
Jora's job-feed intervals.

| Concern | Current prototype | Accepted target |
| --- | --- | --- |
| Collection | A search triggers connector requests | Scheduled ingestion and targeted refresh jobs |
| Product storage | Temporary cached results | Persistent product and offer records |
| Search | Fan out to sources, then rank | Query the index, then rank |
| Source outage | Can fail a retailer during a search | Delays ingestion; freshness rules govern existing offers |
| Discovery | Configured connectors | Integrations plus a queue of discovered product URLs |
| Redis TTL | Product results disappear within 24 hours | Search-response cache lifetime, separate from product retention |

## Collection and search

**Collection:** source schedule or discovery → durable job → source adapter →
validation and normalisation → product/offer upserts → index update.

**Search:** prompt → existing intent parser → indexed candidates → filtering,
de-duplication and ranking → result cards linking to retailers.

Searches may enqueue deduplicated refreshes for stale products or discovery for
poorly covered queries. The initial response must not wait for those jobs. An
empty index returns an honest empty state; it must not silently use mock data.

Reuse the parser, normalisation helpers, ranking, UI and SSE transport where
possible. Evolve the event contract to report index results and optional
refreshes; cached/indexed results must not imply that every retailer was
contacted during that search.

## Initial storage and worker design

Use the existing PostgreSQL stack for persistent records, indexed filtering and
initial text search. Keep Redis for short-lived caches and coordination. A
separate search service can be considered after measured volume and relevance
justify it. Live indexed search requires a database; the offline demo can keep
its current optional-database setup.

Proposed records, not existing migrations:

| Record | Required information |
| --- | --- |
| Source | Access method/configuration, seller coverage, refresh interval, request budget, next due time and health |
| Listing | Stable source item ID, original retailer URL, title, brand, category, material, images and provenance |
| Variant offer | Retailer, listing/variant identity, colour, size, price/currency, availability and destination-specific shipping evidence |
| Observation | When the source was read, when it says the data changed, which fields it supports and when those fields were verified |
| Ingestion run/job | Source, scope, cursor, run status, counts, completeness, lease, attempts and next retry |
| Index revision | Version advanced on published changes, used to invalidate search-result caches |

Keep the data provider separate from the selling retailer. A shopping-search API
can return offers from many sellers. Preserve source identities even when
cross-retailer de-duplication groups listings into one garment. A cheap variant
must not supply the displayed price for a different requested size or colour.

Run ingestion in a worker process separate from the web API. Start with durable
PostgreSQL jobs and expiring leases so restarts and multiple workers do not
lose or duplicate work. Upserts must be idempotent, and expired workers must not
commit over a newer run. A scheduler creates due jobs with per-source limits;
user refresh requests share the same queue and budgets.

Support complete snapshots, incremental feeds and targeted product fetches as
distinct run types. Existing `RetailerConnector.search(intent)` filters and
caps results, so its output is not proof of a complete retailer inventory.
Reuse its parsing helpers through ingestion adapters that report pagination,
scope and completeness explicitly.

## Freshness and removal

- Store `last_seen_at` separately from field verification times. Reading a
  search provider's result does not establish current retailer stock.
- Configure refresh, stale-display and expiry thresholds per source/data type.
  Product descriptions can generally be refreshed less often than offer data;
  actual intervals must be chosen from source limits and measured changes.
- Represent availability as in stock, out of stock or unknown. Unknown sizes,
  materials and shipping remain unknown. Missing shipping cost is not free
  shipping, and an Australian search location does not prove delivery to AU.
- Show when price and availability were last observed. Stale offers must not
  be described as verified in stock. Expired offers leave active search;
  retain only the records needed for saved links and diagnostics under a
  separate retention policy.
- Remove absent offers only after a successful, complete authoritative
  snapshot for the relevant source/scope, or an explicit deletion signal.
  A failed, truncated or partially parsed run must not erase prior inventory.
  Absence from a search-result page never proves a product was removed.
- Commit published updates and the index revision together. Version response
  caches by index revision and cap their lifetime at the earliest included
  offer expiry, so cached results cannot resurrect removed or expired offers.
  Recompute freshness labels when reading cached results.

## Source reliability

Choose access per source: retailer or affiliate feeds, supported APIs, or
accessible product pages under the project's sourcing policy. Shopping/web
search APIs supplement discovery and identify coverage gaps; they are not the
only path to inventory. Do not assume a provider permits indefinite storage:
record and enforce source-specific storage and refresh conditions.

Use per-domain concurrency limits, bounded retries for transient failures,
`Retry-After` handling, and cooldowns. Access challenges pause the source and
surface an operational issue rather than creating repeated request storms.
Refresh healthy sources while failed sources recover. Persistent storage makes
search less dependent on individual fetches; it does not remove access limits.

The current HTML connector remains permission-gated. This decision adds no new
access mechanism or credentials. Validate discovered URLs and redirects before
fetching them so discovery cannot reach private/internal network addresses.

## Delivery order and acceptance checks

1. **Validate sources.** Benchmark a representative retailer sample and real
   menswear prompts. Record usable fields, coverage, access failures, latency,
   update limits and cost. Recheck the historical Shopify findings in the
   intended deployment environment before generalising them.
2. **Persist and ingest.** Add migrations, ingestion adapters and a manual
   import command for a validated source. Re-importing the same data must not
   duplicate offers; restarting the API must preserve searchable inventory.
3. **Search the index.** Add indexed candidate retrieval and explicit unknown
   values across models, ranking, filters and UI. An uncached search must return
   ingested products even with source network access unavailable.
4. **Schedule and expire.** Add the worker/scheduler, leases, budgets, cooldowns,
   expiry and cache invalidation. Verify failed/partial imports preserve prior
   data, complete removals take effect, and expired cached offers stay hidden.
5. **Expand discovery.** Evaluate a shopping/web-search provider, initially
   Serper, and add targeted product checks. Measure relevance and retailer
   coverage on a fixed prompt set before expanding scope.

Automated tests stay offline using fixtures. Live source checks are explicit
integration exercises, with measured coverage and freshness recorded before
calling the service ready for shoppers. Source credentials, migrations,
workers and indexed search are all still outstanding.
