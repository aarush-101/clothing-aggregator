# Architecture

Audience: engineers working on this codebase.

## Accepted direction and current implementation

As of **2026-09-23**, Marle's target architecture includes a persistent product
index and scheduled ingestion. The original restrictions against a preloaded
catalogue and background crawling are superseded.

Collection will run independently of shopper searches: workers ingest feeds,
APIs and accessible product pages, update product/variant offers and expire
stale data. Search will retrieve candidates from the index and reuse the
existing parsing, ranking and presentation pipeline. Targeted discovery and
refresh jobs may be requested by a search without blocking initial results.

**This is a design decision, not implemented functionality.** The code still
uses the connector-based request lifecycle documented below. No product index,
ingestion worker or scheduler exists yet. See
[product-index.md](product-index.md) for the target data model, source failure
handling, freshness/removal rules and delivery acceptance checks.

## The shape of the problem

A menswear search engine that aggregates many retailers has three hard parts:

1. **Understanding the request.** "Relaxed black linen shirt under $120 that
   ships to Sydney" is six constraints in one sentence.
2. **Keeping product data fresh across slow, unreliable sources** while
   keeping shopper searches responsive.
3. **Making heterogeneous inventory comparable** — the same shirt listed by
   three retailers under three names at three prices.

The current prototype fetches retailer data because a person searches and
retains results in a cache for at most 24 hours. This describes today's
implementation, not a constraint on the target architecture.

---

## Current request lifecycle

```
POST /api/search
  ├─ rate limit (per IP, per minute)
  ├─ validate + normalise the query
  ├─ create search_id, register an event stream
  └─ return 202 immediately                     ◄── the browser never waits here

background task
  ├─ emit search_started
  ├─ resolve intent
  │    ├─ intent cache hit?  → reuse (parser identity is cached too)
  │    ├─ injection heuristics fire? → deterministic parser, LLM skipped
  │    ├─ Anthropic available? → structured output → Pydantic validation
  │    └─ anything failed?   → deterministic parser
  ├─ emit intent_parsed
  ├─ fingerprint = sha256(normalised intent)
  ├─ results cache
  │    ├─ fresh (<30m)  → emit products, complete. No retailer contacted.
  │    ├─ stale (<24h)  → emit products now, then refresh below
  │    └─ miss          → continue
  ├─ acquire Redis lock on the fingerprint
  │    └─ already held? → wait for the in-flight search, reuse its result
  ├─ fan out to the relevant connectors
  │    ├─ bounded concurrency (semaphore)
  │    ├─ per-retailer timeout, retries with exponential backoff + jitter
  │    ├─ overall deadline; stragglers are cancelled and marked failed
  │    └─ after each response: filter → group → rank → emit products_added
  ├─ emit ranking_completed (authoritative ordering)
  ├─ cache the result, persist analytics
  └─ emit search_completed, close the stream

GET /api/search/{id}/events   ◄── SSE, resumable via Last-Event-ID
GET /api/search/{id}          ◄── snapshot, for reconnects and no-JS clients
```

---

## Current module map

### `apps/api/app`

| Module | Responsibility |
| --- | --- |
| `config.py` | Settings, validated by Pydantic at import. Fails fast on bad config. |
| `logging_config.py` | Structured logging; JSON in production, contextvars for request/search ids. |
| `models/intent.py` | `SearchIntent` — the structured query, plus its cache fingerprint. |
| `models/product.py` | `Product`, `ProductGroup`, `RetailerStatus`, `SearchResult`; all sanitisation. |
| `models/events.py` | SSE event types and payload builders. |
| `services/nlp/` | `sanitise` → `parser` → (`anthropic_parser` \| `fallback_parser`), over `lexicon`. |
| `services/search_engine.py` | Orchestration: cache, lock, fan-out, streaming, completion. |
| `services/dedupe.py` | Cross-retailer duplicate detection and grouping. |
| `services/ranking.py` | Weighted scoring, match reasons, hard filters, sorting. |
| `services/cache.py` | Redis (or in-process) cache with the freshness policy. |
| `services/event_bus.py` | Per-search event log with replay and fan-out. |
| `services/affiliate.py` | Affiliate deep links and click sub-ids. |
| `services/currency.py` | Cross-currency comparison for price filters. |
| `connectors/` | `base` (the interface), `registry`, and mock, feed, API, HTML and Shopify implementations. |
| `db/` | SQLAlchemy models, session, repositories. No product table. |
| `api/` | FastAPI routers. |

### `apps/web`

| Module | Responsibility |
| --- | --- |
| `lib/use-search-stream.ts` | Creates the search, consumes SSE, reduces events into state. |
| `lib/filters.ts` | Client-side faceting, filtering, sorting. |
| `lib/intent-chips.ts` | Turns a `SearchIntent` into the chips shown to the shopper. |
| `components/search-results-view.tsx` | The results page composition. |
| `components/product-card.tsx` | One garment, its cheapest offer, its match reasons. |
| `components/account-provider.tsx` | Optional anonymous account, favourites, saved searches. |

---

## Natural-language parsing

Two parsers behind one interface (`IntentParser`).

**Anthropic** (`anthropic_parser.py`). One Messages API call with
`output_config.format` set to a hand-written JSON schema that mirrors
`SearchIntent` exactly — a test asserts the two cannot drift apart. `effort` is
`low` because this is short extraction on a latency-sensitive path, and the
static system prompt is cached, so every search after the first reads it from
cache. The reply is parsed and validated with Pydantic before it is trusted.

**Deterministic** (`fallback_parser.py`). Regex and lexicon based. It handles
categories, colours, materials, fits, styles, occasions, seasons, sizes, price
expressions (`under $120`, `between $80 and $150`, `around $200`, `$1.5k`),
currencies, destinations, brand preferences and exclusions, gender and sort
hints. It is pure, synchronous and exhaustively unit-tested.

The deterministic parser is **not** a stub. It runs when there is no API key,
when the LLM call fails or times out, when the model returns something empty,
and whenever the query trips the injection heuristics. It also backfills prices
and sizes the model omitted, because those are stated explicitly in the sentence
and the regexes are reliable.

### Prompt injection

The search box feeds an LLM, so it is an injection surface. Four layers:

1. **Validation** — length, word count, control characters.
2. **Detection** — heuristics for instruction-shaped text ("ignore previous
   instructions", role reassignment, fake conversation turns, tag injection,
   exfiltration). A match means the LLM is **skipped entirely**, and the UI says
   so with a "Keyword parsing" chip.
3. **Neutralisation** — prompt-structural characters (`<>{}[]\`|`, zero-width and
   bidi characters) are stripped before the text is embedded in a delimited
   section, so it cannot close the tag and speak as the system.
4. **Output validation** — the reply becomes a strict Pydantic model. Even a
   fully hijacked response can only produce search filters.

Instruction words are also in the stopword list, so an injection attempt never
becomes a search keyword.

---

## Connectors

The interface below is for the current search-driven connectors. Background
ingestion needs adapters that also report pagination, source scope and snapshot
completeness. A filtered `search(intent)` response cannot establish whether a
retailer removed an item. See [product-index.md](product-index.md).

```python
class RetailerConnector(ABC):
    key: str
    display_name: str
    ships_to: list[str]
    currency: str
    requires_permission: bool

    def supports(self, intent) -> bool
    async def search(self, intent) -> list[Product]
    def normalise(self, raw_product) -> Product | None
    async def health_check(self) -> ConnectorHealth
    async def aclose(self) -> None
```

`normalise` returns `None` rather than raising, and `build_product` swallows
validation errors for a single record. One malformed row in a 5,000-row feed
must not fail the connector, and one failing connector must not fail the search.

Which connectors exist is configuration (`ENABLED_CONNECTORS`), not code. See
[adding-a-connector.md](adding-a-connector.md).

### Failure handling

- Per-retailer timeout (`SEARCH_RETAILER_TIMEOUT_SECONDS`, default 8s)
- Bounded retries with exponential backoff and jitter; permission errors are
  never retried because retrying cannot help
- Bounded concurrency (`SEARCH_MAX_CONCURRENT_RETAILERS`, default 6)
- Overall deadline (`SEARCH_TOTAL_TIMEOUT_SECONDS`, default 25s); stragglers are
  cancelled and reported as failed
- Any failure produces `status: "partial"`, a non-blocking notice in the UI, and
  the successful retailers' results are shown regardless

---

## De-duplication

The same garment is routinely listed by several retailers. `dedupe.py` derives
identity keys per offer and unions offers that share any of them:

| Key | Built from |
| --- | --- |
| `brand_title` | normalised brand + title stripped of brand, colour and noise tokens + primary canonical colour |
| `model` | a SKU-like token extracted from the title or product id |
| `image` | the filename portion of the image URL |

Union-find groups the offers. Within a group, offers are ordered **in-stock
first, then cheapest including shipping**, and the first becomes the card's
primary offer. `lowest_total_price` deliberately ignores out-of-stock offers —
quoting a price nobody can buy is worse than quoting none.

Colour is part of the identity key, so different colourways stay separate. When
a later retailer's response merges into an existing group, the whole accumulated
set is re-grouped and re-ranked, which keeps streamed results identical to what
a single batch run would have produced.

---

## Ranking

`score_product(product, intent)` returns `(score, reasons)`.

Each dimension yields a sub-score in `[0, 1]`. **Only dimensions the shopper
mentioned are applicable**; the score is the weighted mean over applicable
dimensions, so unmentioned attributes neither help nor hurt. Weights are in
`RankingWeights` and published at `GET /api/ranking`.

Hard filters run *before* scoring: excluded brands, and prices outside the
stated range (with a 10% tolerance above the maximum, because "under $120" is
usually approximate). Currency mismatches are converted first; if a rate is
unknown the price constraint is skipped rather than applied wrongly.

Group ordering follows the shopper's `sort_preference`:

| Preference | Ordering |
| --- | --- |
| `relevance` | score desc, then cheapest |
| `price_low_to_high` | cheapest **total** (item + shipping) |
| `biggest_discount` | largest markdown across the group's offers |
| `newest` | most recent `source_updated_at` |

"Lowest price" sorts on total cost including shipping, which is the number a
shopper actually pays; each card shows the shipping component explicitly.

Match reasons are assembled from the dimensions that matched with explicit
intent, producing sentences like *"Matches your requested shirt, black colour,
linen material and relaxed fit."* plus short notes for budget, size, discount,
stock and multi-retailer availability.

---

## Caching

This section describes the current caches. The target product index has its own
freshness and retention rules. Future response caches must account for index
revisions and offer expiry, not just the intent fingerprint and elapsed TTL.

Two caches, both content-addressed:

| Key | Value | TTL |
| --- | --- | --- |
| `ca:intent:v1:{sha256(query)}` | the parsed intent, the parser that produced it, and its warnings | 24 h |
| `ca:results:v1:{intent fingerprint}` | groups + retailer statuses | 24 h (fresh for 30 min) |

The results fingerprint is computed over the **normalised** intent with the raw
sentence excluded and all lists sorted, so differently worded equivalent queries
share one entry.

Caching the parser identity matters: without it, a deterministic parse would
look like an AI parse on the second search and the UI would stop telling the
truth. A regression test covers this.

A `SET NX PX` lock on the fingerprint coalesces concurrent identical searches.
The loser polls for the winner's result rather than duplicating the fan-out.

`REDIS_URL` is optional in development — an in-process backend with the same
interface takes over. Production refuses to start without Redis, because the
in-process cache is not shared between instances.

---

## Streaming

`event_bus.py` keeps an ordered, replayable event log per search. A subscriber
registers its queue *before* the backlog snapshot is taken, so no event can slip
through the gap; duplicates are filtered by sequence number.

The SSE endpoint sends `id:` on every frame, so a browser reconnect carries
`Last-Event-ID` and replays only what it missed. Comment frames every 15s stop
proxies closing an idle connection. If the in-process stream has expired, the
endpoint replays a correct minimal sequence from the persisted snapshot instead
of 404ing.

**Scope:** the broker is per-process. Multi-instance deployments need sticky
sessions or a Redis pub/sub implementation of the same interface — see
[limitations.md](limitations.md).

---

## Database

PostgreSQL currently stores application state only: `users`, `saved_searches`,
`favourites`, `retailer_configs`, `affiliate_click_events`, `search_analytics`,
`connector_health_records`.

**There is no product table yet.** Persistent listings, variant offers, source
observations and ingestion jobs are planned in [product-index.md](product-index.md).
Redis will remain a cache rather than the authoritative product store.

The database is optional for the current development/demo mode. With
`DATABASE_URL` unset, accounts and analytics are skipped and demo search is
unaffected. The target live indexed mode will require PostgreSQL. A `GUID` type
decorator maps to native `UUID` on PostgreSQL and `CHAR(36)` elsewhere so the
existing test suite runs on SQLite with no database server.

---

## Frontend

The results page is one client component driven by `useSearchStream`, a reducer
over SSE events. `products_added` merges by `group_id`; `ranking_completed`
replaces the list with the authoritative ordering.

Filtering and sorting are **client-side** over the already-ranked result set, so
refinement is instant and never re-queries retailers. Filtering by retailer
rebuilds each group from its surviving offers, which keeps the headline price
honest.

Deliberate choices:

- **System font stacks**, not `next/font/google` — the build works offline and
  there is no flash of unstyled text.
- **Plain `<img>`**, not `next/image` — retailer imagery comes from arbitrary
  hosts that cannot be allow-listed in advance, and the optimiser would need
  network access at request time. Failures degrade to a neutral panel.
- **Render-time state adjustment** instead of `setState` in effects, per React's
  guidance, which the React 19 lint rules enforce.
- The filter panel renders twice (desktop sidebar, mobile sheet) and takes an
  `idPrefix` so form-control ids stay unique. An e2e test asserts there are no
  duplicate ids.

---

## Testing

| Layer | Tool | Count | Covers |
| --- | --- | --- | --- |
| Backend | pytest | 256 | parsing, sanitisation, intent hashing, caching, normalisation, ranking, de-duplication, connectors, the search lifecycle, the HTTP API including SSE |
| Frontend | Vitest | 88 | formatting, intent chips, faceting/filtering/sorting, stream merging, components |
| End to end | Playwright | 44 | the real stack, desktop and mobile: home page minimalism, progressive streaming, partial failure, refinement, caching, accessibility |

Everything runs with no Docker, no Redis, no PostgreSQL and no API keys.
