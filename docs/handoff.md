# Marle project handoff — 2026-09-23

## Start here

Repository: `/Users/aarusharora/repo/clothing-aggregator` (`~/repo/clothing-aggregator`).
Branch: `main`. Base commit at handoff: `e862eb9`.

**The working implementation is in the uncommitted working tree.** It includes
new, modified and intentionally deleted files. No commit, push or deployment
was performed. Preserve these changes when continuing; do not reset the tree
or restore deleted demo code.

The user wanted an actual menswear search aggregator without an eBay account,
then agreed to a Jora-inspired approach: maintain a reviewed retailer registry,
collect products in the background, and search the stored catalogue. Their
last implementation request was: “make this a working implementation — delete
old code that is not used.” That work is implemented and verified locally.
The latest request is this handoff; no additional feature is currently assigned.

## Update — same day, second session

The user asked for a review and then “fix everything”. Changes since the
original handoff below (all uncommitted, like the rest):

- **Sources:** added Highs and Lows, Up There and General Pants Co. (multi-brand,
  overlapping brands). Culture Kings was removed: its robots rules block paging. 8 enabled,
  56,715 offers, 10,693 listings — see [live validation](live-validation.md).
- **De-duplication:** fixed false merges (model numbers were dropped, “S/S” was
  noise, colourways merged on first colour) and added the rule that one
  retailer's listings never merge. Added colourway-suffix, apostrophe and plural
  handling. 52 cross-retailer groups now merge; previously 0.
- **Search speed:** migration `0003_offer_filters` adds filter columns; SQL
  prefilters before payload decoding. Broad prompts went from ~3.5 s to ~0.2–0.5 s.
- **Categories:** garment-noun classifier (`classify_category`), new trackpants,
  singlet, underwear categories and more aliases; brand prefix removed first.
- **Brands:** prompts are matched against indexed brands (`Catalogue.recognise_brands`).
- **Offers:** $0–$1 and >90%-off placeholder variants skipped; `default_brand`
  for Industrie; internal “[MERGED …]” title tags stripped.
- **UI:** product cards list each other retailer's price with a link, and name
  the colourway when the title doesn't.
- Checks: 240 backend tests, 90 frontend tests, 36 browser tests (8 skips),
  lint/types/build, migration upgrade/downgrade on fresh SQLite.

## What works now (original handoff)

```text
Background: reviewed retailer registry → scheduled imports → SQL variant index
Search:     prompt → NLP filters → index query → grouping/ranking → UI via SSE
Purchase:   product card → retailer product page with the selected variant
```

The API is Python/FastAPI with SQLAlchemy; the frontend is Next.js/TypeScript.
Search makes no outbound retailer requests. A deterministic parser works
without credentials; Anthropic parsing remains optional. Live validation used
the deterministic parser, so it does not establish optional model-provider
configuration or availability.

Five sources use public Shopify men's collection JSON endpoints. Ordinary
Python/httpx HTTPS requests succeeded with the explicit user agent
`Marle/0.1 (menswear product index)`. No eBay account, provider API key, proxy
rotation or browser impersonation was used.

| Connected retailer | Collection | Imported variant offers |
| --- | --- | ---: |
| Assembly Label | `mens-shop-all` | 812 |
| Academy Brand | `mens` | 2,561 |
| Industrie | `all` | 9,873 |
| Universal Store | `mens` | 16,979 |
| Incu | `mens-clothing` | 7,210 |
| **Total** | | **37,435** |

These are individual size/colour offers, including unavailable records retained
in storage, not distinct garments. Search excludes known out-of-stock offers.
The ignored local database `apps/api/marle.sqlite3` still contains all 37,435
records; its count was checked again while writing this handoff. Freshness is
time-dependent, so stored counts do not guarantee the same future search results.
The database is local state and will not accompany a Git clone.

Ten retailer websites are reviewed in the codebase. THE ICONIC, UNIQLO, Country
Road, AS Colour and Cotton On remain unconfigured: they have no enabled product
adapter. “Website verified” and “working product import” are distinct statuses.

Earlier research reported widespread blocked requests. That historical result
does not describe the current five integrations: all five completed real imports
from this environment. See [live validation](live-validation.md) for evidence.

## Run and inspect

Python 3.9+ and Node 20+ are required. Dependencies are already installed in
this checkout; use `make install` for a fresh environment. Copy `.env.example`
to `.env` only if no existing configuration needs preserving.

From the repository root:

```bash
make ingest       # refresh due sources once; no need to force every run
make api          # http://localhost:8000
# In another terminal:
make web          # http://localhost:3000
```

Blank `DATABASE_URL` uses persistent SQLite at `apps/api/marle.sqlite3`.
Blank `REDIS_URL` uses an in-process intent/snapshot cache. Docker and provider
keys are unnecessary for the local implementation. API startup creates local
SQLite tables and runs ingestion in the background by default.

Useful reads:

- `GET /health/ready`: database/cache readiness and unexpired offer count.
- `GET /api/retailers?include_health=true`: configured coverage, import state,
  stored counts, last success and errors.
- `POST /api/search` with `{"query":"black linen shirt under $120"}`: returns
  the search ID, SSE URL and snapshot URL.
- `GET /api/search/{search_id}/events`: result stream.
- `GET /api/search/{search_id}`: snapshot, rechecked against current inventory.

For a separate ingestion process, set `INGESTION_ENABLED=false` on the API and
run `make worker`. A deliberate single-source refresh is available:

```bash
cd apps/api
.venv/bin/python -m app.ingest --once --retailer assemblylabel --force
```

`--force` overrides the scheduled due time, including cooldowns; it does not
steal an active lease or bypass robots checks. Normal runs honour cooldowns.
Temporary live-validation servers on ports 8181 and 3181 were stopped after
testing. Do not assume a service is running; check before starting another.

## Implementation map

Paths below are relative to the repository root.

| Area | Main files |
| --- | --- |
| Reviewed sites and enabled collection settings | `apps/api/app/data/retailers.json` |
| Registry validation and public JSON collection | `apps/api/app/sources/registry.py`, `shopify.py` |
| Stored inventory, atomic replacement, leases and queries | `apps/api/app/services/catalogue.py` |
| Scheduler and CLI | `apps/api/app/services/ingestion.py`, `apps/api/app/ingest.py` |
| Database tables and migration | `apps/api/app/db/tables.py`, `apps/api/alembic/versions/0002_product_index.py` |
| App startup and settings | `apps/api/app/deps.py`, `config.py`, `main.py` |
| Search, filtering, grouping and ranking | `apps/api/app/services/search_engine.py`, `filtering.py`, `dedupe.py`, `ranking.py` |
| HTTP/SSE and retailer health | `apps/api/app/api/routes_search.py`, `routes_retailers.py`, `routes_health.py` |
| UI state and source/product presentation | `apps/web/lib/use-search-stream.ts`, `apps/web/components/` |
| Offline source/index checks | `apps/api/tests/test_sources.py`, `test_catalogue.py`, `test_search_engine.py` |
| Browser fixtures and setup | `apps/api/tests/catalogue_fixtures.py`, `e2e_server.py`, `apps/web/playwright.config.ts` |

Key behaviour to preserve:

- Sources refresh every six hours by default. Robots checks use Protego.
  Requests are spaced at least one second apart and respect declared crawl
  delays/request rates. Blocked responses and access challenges pause a source.
- SQL leases and heartbeat/token checks prevent an expired worker from
  publishing over another worker. Complete snapshots replace source inventory
  atomically; incomplete pagination or parse failures preserve the last good
  inventory. Missing variants disappear after a successful complete refresh.
- Prices, sizes, colours, stock and purchase URLs stay attached to their source
  variant. Price bounds are strict. General results show available sizes at
  the displayed price, not sizes whose variants cost something different.
- Offers become stale after 12 hours and expire from search after 48 hours.
  Stale stock is shown as unconfirmed; known unavailable stock remains excluded.
  Shipping costs and delivery eligibility remain unknown unless supported by data.
- Snapshot reads and completed-stream reconnects re-query inventory, preventing
  deleted or expired products from returning through a cached result. Broker
  snapshots provide a fallback if the cache is unavailable. Failed searches
  remain readable and appear as errors in the UI.
- UI source coverage stays visible after search completes. The destination chip
  says “Destination: Sydney”; it does not claim confirmed shipping to Sydney.

Removed runtime code includes the old connector framework, mock retailers,
fake-store API, unused HTML/feed templates, sample feeds, mock inventory and
historical 93-store configuration. Offline synthetic data exists only under
tests. The tracked `apps/web/tsconfig.tsbuildinfo` was deleted and build info is
ignored. Historical database migrations were preserved; old account data was
not destructively removed.

## Verification completed

Final checks before this documentation-only handoff:

- Backend: **228 tests passed**; Ruff lint and format checks passed.
- Frontend: **88 unit tests passed**; TypeScript, ESLint and formatting passed.
- Browser suite: **36 passed, 8 layout-specific skips**, desktop and mobile.
- Frontend production build passed.
- Alembic `0001_initial → 0002_product_index` applied to a fresh SQLite database.
- A complete real import succeeded for all five sources. Each source's robots
  rules were checked; `/meta.json` confirmed AUD during live validation.
- Real API searches and a separate browser session used the imported inventory,
  verifying images, prices, product links, source coverage and mobile layout.
  One sampled product URL per retailer returned HTTP 200.

Observed real searches on 2026-09-23:

| Prompt | Groups returned | Example |
| --- | ---: | --- |
| black linen shirt under $120 | 1 | Industrie St Martins Short Sleeve Linen Shirt, AUD 89.95 |
| linen shirt size M under $150 | 81 | Academy Brand Hopper SS Shirt, AUD 20.00, size M |
| navy shorts size 32 | 15 | Academy Brand Stripe Riviera Linen Short, AUD 54.00, size 32 |

These counts and prices are dated observations. A gzip double-decoding bug found
during the initial import was fixed before the successful run. Failed attempts
remain in `ingestion_runs`. A later Industrie refresh removed the placeholder
vendor “Mens” from the brand field and retained the same variant count.

To repeat checks after changes:

```bash
make test
make lint
make build
make test-e2e
```

The browser suite uses an isolated `apps/api/e2e.sqlite3`, disables live
ingestion, and builds/serves the frontend against fixture inventory. It does
not validate live retailer access. Override `E2E_WEB_PORT`/`E2E_API_PORT` if
needed; final validation used 3133/8133. Its build sets the API URL at build time,
so rebuild with the intended URL before serving a production frontend.

## Remaining limits and sensible follow-up work

This is a working initial implementation, not complete internet-wide coverage.
No guarantee of permanent unblocked access is possible. Imports preserve useful
unexpired data during source outages; they do not circumvent access challenges.

Potential next work, if requested:

1. Add more retailers through the registry and an appropriate adapter, recording
   actual product-access evidence. Follow [adding a source](adding-a-source.md).
2. Validate source access from the deployment host, PostgreSQL migrations/runtime
   and concurrent load. Local success is not a production-access guarantee.
3. Add import monitoring, alerts, run-log retention and an operator UI.
4. Improve lexical relevance, cross-retailer deduplication and size normalization.

Other limits: currency conversion uses existing static rates; there is no live
FX or vector search. Shipping eligibility is not verified. The live event broker
is in-process, so multiple API instances need session affinity; Redis does not
transport live SSE events. Email/password sign-in, checkout, payments and alerts
were not implemented by this change.

Before frontend code edits, read `apps/web/AGENTS.md` and the relevant bundled
Next.js guide under `apps/web/node_modules/next/dist/docs/`. No sub-agents were
used for this implementation. Keep the README honest about coverage and avoid
reintroducing fictional products as a fallback.

Further context: [README](../README.md), [architecture](architecture.md),
[product index](product-index.md), [retailer registry](retailer-registry.md),
[live validation](live-validation.md), [limitations](limitations.md),
[deployment](deployment.md), [API reference](api.md).
