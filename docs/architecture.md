# Architecture

Marle separates collection from search. The source registry and SQL catalogue
are now part of the running application, not a proposed design.

## Collection

`app/sources/registry.py` loads the checked-in retailer file. Only entries with
an enabled ingestion configuration supply the worker. Five reviewed men's
collections currently use the public Shopify JSON adapter.

The worker periodically claims due sources using an atomic SQL update. A
five-minute lease token prevents duplicate workers; each page renews the lease.
Source due times and unfinished leases survive process restarts. A crashed
worker's lease can be reclaimed; its old token cannot publish over a new run.

The adapter fetches robots.txt, honours its matching rules and crawl delays,
and pages through the configured men's collection with a one-second minimum
request interval. Requests use the Marle user agent. Cross-host or non-HTTPS
redirects are rejected. Responses have a size limit and request timeout.
403/429 responses and access challenges pause the source with a cooldown;
Retry-After can lengthen it. There is no proxy rotation or challenge solving.

An empty final page establishes completion. Repeated IDs, malformed records,
invalid JSON and page-budget exhaustion fail the snapshot. Only a complete
snapshot is published: acquire the current lease row, replace that source's
variant offers, mark its run completed, then commit everything together.
Readers see the previous or new inventory, never a half-published collection.
A failed collection leaves offers untouched until their normal expiry.

## Storage

| Table | Purpose |
| --- | --- |
| `catalogue_sources` | Due time, lease token/expiry, health, last attempt/success and offer count |
| `catalogue_offers` | Source + variant ID primary key, category/expiry index and normalised product payload |
| `ingestion_runs` | Start/end times, state, offer count and error for each attempt |
| Existing account tables | Users, saved searches, favourites, clicks and search analytics |

SQLite is the local default and persists at `apps/api/marle.sqlite3`.
PostgreSQL uses the same SQLAlchemy models and migration `0002`.
Existing migration history is retained; old unused configuration/health tables
are not destructively dropped from existing installations.

## Search

The API accepts a prompt and starts a short asynchronous search job. The
optional Anthropic parser or deterministic parser produces `SearchIntent`.
An indexed SQL query narrows enabled, unexpired offers by category. Existing
relevance/ranking helpers apply the other constraints and group results.

Size-specific searches require a matching available variant. Colour, price,
stock and the product URL stay attached to that variant. Without a size,
the lowest eligible variant is displayed; listed sizes are only those offered
at that price. Unknown shipping is retained rather than inferred from an AU
storefront.

The frontend receives the existing SSE lifecycle with `source: "index"` and
`cache_state: "index"`. Retailer progress describes index coverage, not live
network requests. Product cards show observed times and stale/unknown stock.

Product results are not cached by query. Parsed intents, query snapshots and
rate counters use Redis or the local cache. Reading a completed snapshot or
reconnecting to a completed stream re-queries current inventory, so old search
IDs do not restore expired or removed products. Live SSE streams are
in-process; a scaled deployment still needs session affinity.

## Freshness

Each offer records its observation time independently of any source update
time. Defaults: scheduled refresh every six hours, stale after 12 hours,
expired after 48 hours. Stale offers lose confirmed in-stock/size claims.
Known unavailable variants stay excluded. Expired offers are filtered in SQL.
The last checked time displayed to shoppers comes from the observation, not
from when they submitted their search.

## Operations

Local startup creates SQLite tables and starts ingestion in the API process.
Production can run `python -m app.ingest` separately with
`INGESTION_ENABLED=false` on the API. `/api/retailers` exposes reviewed coverage
and refresh state; `/health/ready` checks database/cache and reports inventory
count. An empty catalogue is surfaced explicitly rather than seeded with demos.

See [deployment](deployment.md), [source onboarding](adding-a-source.md) and
[limitations](limitations.md) for practical constraints.
