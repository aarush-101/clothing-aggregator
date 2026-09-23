# Product index and background ingestion

Decision date: **2026-09-23**. Status: **initial implementation running**.

The Jora-inspired change is implemented: persistent product storage and
background collection are independent of shopper searches. The original
on-demand-only prototype has been replaced.

Jora's documented model combines crawling and feed imports. That inspired
this separation; Marle uses retailer-specific collection methods and product
freshness rules. See [Jora's integration guide](https://support.jora.com/hc/en-us/articles/13919677306383-Get-your-jobs-published-on-Jora-with-an-XML-feed).

## Implemented

- The reviewed retailer registry controls enabled ingestion.
- Five men's collections import into a persistent SQL variant index.
- SQLite provides a working local default; PostgreSQL has a migration.
- Source schedules, worker leases, recovery and run records survive restarts.
- Complete snapshots publish atomically and remove absent offers in scope.
- Failed, malformed, repeated or truncated snapshots preserve prior inventory.
- Per-variant prices, colours, sizes, availability and direct links stay together.
- Search reads the index without retailer network access.
- Stale stock loses confirmation; expired offers leave active search.
- Search snapshots/reconnects re-query the index, avoiding stale response-cache
  resurrection. No product-response cache or index-revision table is needed in
  this first implementation.

The worker uses each source row as a durable, deduplicated scheduled job.
Separate arbitrary discovery jobs and incremental feed adapters are not yet
implemented. The local default hosts the worker in the API process; production
can run it separately with the same database lease protocol.

## Expansion work

- Validate the other reviewed retailers and implement their source adapters.
- Add web/shopping-search discovery beyond the registry.
- Add retailer feeds or supported APIs when access is available.
- Measure relevance, long-term access reliability and refresh costs.
- Add shipping/size-system evidence and better material extraction.
- Add full-text/vector candidate retrieval if measured catalogue size warrants
  it. Current SQL category filtering plus application ranking suits the initial
  catalogue; it has not been load-tested at internet scale.

See [architecture](architecture.md) for current behaviour and
[live validation](live-validation.md) for the measured import.
