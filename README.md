# Marle — menswear search aggregator

Marle turns a clothing prompt into filters, searches a persistent product
catalogue, merges the same garment sold by different retailers into one card
with each retailer's price, and links shoppers to the original retailers. It
collects real menswear from **Assembly Label, Academy Brand, Industrie,
Universal Store, Incu, Highs and Lows, Up There and General Pants Co.**, without
an eBay account or shopping API key.

**Status: working initial implementation with limited retailer coverage.**
Thirteen websites are reviewed in the registry; eight have enabled, tested
imports. The rest are listed but unconfigured. This does not search every
retailer on the internet or guarantee current stock and delivery at checkout.

A live import on 2026-09-23 stored **56,715 size/colour offers** (35,497 in
stock) for **10,693 distinct listings** across the eight sources. The multi-brand
stores were chosen because they stock the same brands (Carhartt WIP, Norse
Projects, Gramicci, Levi's, Dickies, Nike…), so the same garment can appear at
several retailers and be merged. See the
[live validation report](docs/live-validation.md) for evidence and limits.

## Run locally

Requirements: Python 3.9+, Node 20+. Docker and API keys are optional.

```bash
make install
cp .env.example .env
make ingest       # first real import; subsequent runs refresh due sources
make api          # http://localhost:8000
# In another terminal:
make web          # http://localhost:3000
```

Try **“black linen shirt under $120”**, **“linen shirt size M under $150”**,
**“carhartt jacket”** or **“norse projects”**. Results have real product images, prices and retailer
links. Empty searches show an empty state; there is no fictional fallback.

With `DATABASE_URL` blank, the app creates a persistent SQLite database at
`apps/api/marle.sqlite3`. Restarting the API preserves inventory, favourites and
saved searches. With `REDIS_URL` blank, parsed intents and search snapshots use
an in-process cache. PostgreSQL and Redis can be configured for deployment.

The API starts a background ingestion task by default. If the database is
empty, the first collection happens in the background and search explains that
inventory is pending. `make ingest` lets you populate it before opening the UI.

## How it works

```text
Background: retailer registry → scheduled collection → variant index in SQL
Search:     prompt → NLP filters → index query → grouping/ranking → results
Purchase:   result card → original retailer's product/variant page
```

- Sources refresh every six hours by default, independently of searches.
- Imports check robots.txt, identify as Marle, space requests, respect
  Retry-After and pause on access challenges.
- A complete collection replaces that retailer's inventory atomically. Failed,
  truncated or malformed collections preserve the last good snapshot.
- Each stored variant keeps its own price, colour, size and availability.
  A size-specific search uses that variant's price and purchase link.
- Offers need refreshing after 12 hours and expire from search after 48 hours.
  Unknown shipping costs and destinations remain unknown. Stale stock is not
  displayed as confirmed availability.
- Search reads SQL without outbound retailer requests. It works during source
  outages while unexpired inventory remains. Snapshots and reconnects recheck
  the index so removed or expired offers cannot reappear from a response cache.
- Filter columns (category, price, size, stock, brand, search text) let SQL
  narrow offers before ranking; typical searches take 5–750 ms locally.
- Brand names in a prompt are recognised from the indexed brands, in any case
  (“levis 501 jeans”, “no nike”), and filter results.
- The same garment from different retailers is merged using brand, a
  normalised title and the full colourway. Two listings from one retailer are
  never merged. Each card links to every retailer's price for that garment.
- The deterministic prompt parser works without credentials. Anthropic parsing
  remains optional. Ranking is deterministic and exposed at `/api/ranking`.

## Manage sources

Edit [retailers.json](apps/api/app/data/retailers.json). Website verification,
product-access evidence and enabled ingestion are separate fields. Runtime
coverage, errors and last successful imports are visible at `/api/retailers`.
See [the registry guide](docs/retailer-registry.md) and
[adding a source](docs/adding-a-source.md).

```bash
make ingest          # refresh due sources once
make worker          # standalone scheduler; set INGESTION_ENABLED=false on API
cd apps/api
.venv/bin/python -m app.ingest --once --retailer assemblylabel --force
```

`--force` is an operator command to ignore the scheduled due time; it never
steals an active worker lease. Normal scheduled runs respect cooldowns.

The replaced mock retailers, sample feeds, fake-store API, unused HTML/feed
connector templates and historical 93-store configuration have been removed.
Offline fixtures live under `tests/` and are never loaded by the application.

## Verification

```bash
make test         # backend + frontend unit/integration tests; offline
make lint         # Python lint/format + frontend lint/types
make build        # production frontend build
make test-e2e     # browser tests against an isolated SQLite fixture catalogue
```

The browser suite builds and serves the frontend independently of an existing
`next dev` process. Live retailer imports are explicit integration checks and
are not run by CI.

## Documentation

| Document | Contents |
| --- | --- |
| [Project handoff](docs/handoff.md) | Current implementation, validation, local state and how to continue |
| [Architecture](docs/architecture.md) | Components, storage, search and refresh behaviour |
| [Product index](docs/product-index.md) | Implemented index design and remaining expansion work |
| [API reference](docs/api.md) | Search/SSE, source health and accounts |
| [Retailer registry](docs/retailer-registry.md) | Website and access verification |
| [Adding a source](docs/adding-a-source.md) | Integrating a reviewed retailer |
| [Live validation](docs/live-validation.md) | Observed import/search results |
| [Access research](docs/real-retailer-data.md) | Historical findings and current source choices |
| [Affiliate links](docs/affiliate-networks.md) | Optional link attribution |
| [Deployment](docs/deployment.md) | Local SQLite, PostgreSQL, workers and hosting |
| [Limitations](docs/limitations.md) | Coverage, freshness and operational limits |
