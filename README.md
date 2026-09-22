# Marle — on-demand menswear search

A natural-language search engine for menswear. You describe what you want in a
sentence; it interprets the request, queries several retailers concurrently,
normalises and de-duplicates what comes back, ranks it, and streams the results
into the page as each retailer responds.

> **It is not a marketplace.** There is no product catalogue in this repository
> and no crawler on a timer. Retailers are contacted *only* when a user submits
> a search, and results live in Redis for at most 24 hours.

```
“Find me a relaxed black linen shirt under $120 that ships to Sydney”
        │
        ├─ parse ──────────► SearchIntent {colours:[black], materials:[linen],
        │                                   fits:[relaxed], max: 120, ships_to: AU}
        ├─ select connectors ► the ones that ship to AU and stock menswear
        ├─ fan out ─────────► 6 retailers, concurrently, 8s timeout each
        ├─ normalise ───────► one Product shape, untrusted text sanitised
        ├─ de-duplicate ────► one card per garment, cheapest offer first
        ├─ rank ────────────► deterministic weighted score + match reasons
        └─ stream ──────────► SSE: results appear as retailers answer
```

---

## Contents

| Path | What lives there |
| --- | --- |
| `apps/api` | FastAPI service: parsing, connectors, ranking, caching, SSE |
| `apps/web` | Next.js App Router frontend |
| `docs/` | Architecture, API reference, connector guide, deployment, limitations |
| `docker-compose.yml` | Local PostgreSQL and Redis |
| `.env.example` | Every environment variable, annotated |

---

## Quick start

Requirements: **Python 3.9+**, **Node 20+**. Docker is optional — the stack runs
without Redis or PostgreSQL, and no Anthropic API key is needed.

```bash
git clone <this repo> && cd clothing-aggregator
cp .env.example .env

# 1. Dependencies (creates apps/api/.venv and installs npm packages)
make install

# 2. Optional: PostgreSQL + Redis
docker compose up -d
make migrate

# 3. Run both halves (two terminals)
make api     # http://localhost:8000  (docs at /docs)
make web     # http://localhost:3000
```

Open <http://localhost:3000> and search for
*“Find me a relaxed black linen shirt under $120 that ships to Sydney”*.

### Running without Docker

`docker compose up -d` is optional. With `REDIS_URL` and `DATABASE_URL` unset:

- caching falls back to an in-process store (single instance only)
- accounts, favourites and analytics are skipped
- **search, streaming, ranking and de-duplication all work exactly the same**

The API logs which mode it started in.

### Without an Anthropic API key

Query parsing falls back to a deterministic parser that handles colours,
materials, fits, categories, sizes, prices, currencies, brands, exclusions,
destinations and sort hints. Every example query in this README works without a
key. Set `ANTHROPIC_API_KEY` to enable the better parser; nothing else changes.

---

## Commands

```bash
make help          # list everything

make install       # install API + web dependencies
make up / down     # start / stop PostgreSQL and Redis
make migrate       # alembic upgrade head

make api           # uvicorn with reload on :8000
make web           # next dev on :3000

make test          # backend (pytest) + frontend (vitest)
make test-e2e      # Playwright, boots both servers itself
make lint          # ruff + eslint + tsc
make format        # ruff format + prettier
make build         # next build
make verify        # lint + test + build (what CI runs)
```

Per-app equivalents:

```bash
cd apps/api && .venv/bin/pytest            # 256 backend tests
cd apps/web && npm run test                # 88 frontend unit tests
cd apps/web && npm run test:e2e            # 44 end-to-end tests (desktop + mobile)
```

---

## What a search actually does

`POST /api/search` returns a `search_id` immediately and runs the job in the
background. The browser subscribes to
`GET /api/search/{id}/events` and receives, in order:

| Event | Meaning |
| --- | --- |
| `search_started` | job accepted; the candidate retailer list |
| `intent_parsed` | the structured `SearchIntent`, and which parser produced it |
| `retailer_started` | one connector began |
| `retailer_completed` | it returned *n* relevant products |
| `retailer_failed` | it timed out or errored — the search continues |
| `products_added` | newly grouped, ranked products (merge by `group_id`) |
| `ranking_completed` | the authoritative ordered result set |
| `search_completed` | final status, warnings, cache state, last-updated time |

Full payloads: [`docs/api.md`](docs/api.md).

### Caching

Results are keyed by a stable hash of the **normalised intent**, not the raw
sentence — so “relaxed black linen shirt under $120” and “black linen shirt,
relaxed, under $120” share one cache entry.

| Age | Behaviour |
| --- | --- |
| < 30 min | served immediately; no retailer is contacted |
| 30 min – 24 h | served immediately **and** refreshed, because a user asked |
| > 24 h / absent | a live search runs |

A Redis lock stops two identical searches from hitting retailers at the same
time; the second waits for the first and reuses its result. Every response
carries a visible last-updated time and a cached/refreshed label.

---

## Retailer connectors

Four kinds ship in the box:

| Connector | Status | Purpose |
| --- | --- | --- |
| **Mock retailers** (4 + 1 flaky) | on by default | A seeded catalogue of 44 garments / 78 offers across fictional retailers. Makes the whole pipeline demonstrable offline, including cross-retailer duplicates and a deliberate outage. |
| **Generic feed** (JSON/XML) | on (bundled sample) | Declarative field mapping for affiliate feeds — Awin, Impact, CJ, Rakuten, Shopify collections. No code per network. |
| **Example public API** | off by default | A template for a real API integration against a credential-free public API. |
| **HTML / JSON-LD** | off, permission-gated | Reads schema.org product data from a retailer's own pages, only with written permission. Obeys robots.txt, rate-limits itself, never evades bot protection. |

The mock data uses invented brands and retailers on the reserved `.example` TLD.
Nothing here impersonates a real shop, and "View at retailer" links for mock
products intentionally do not resolve.

Adding your own: [`docs/adding-a-connector.md`](docs/adding-a-connector.md).
Affiliate network specifics: [`docs/affiliate-networks.md`](docs/affiliate-networks.md).

---

## Ranking

Deterministic and inspectable — `GET /api/ranking` returns the live weights.

| Dimension | Weight |
| --- | --- |
| Keyword relevance | 0.25 |
| Price fit | 0.13 |
| Category match | 0.12 |
| Colour match | 0.09 |
| Size availability | 0.08 |
| Material match | 0.07 |
| Shipping availability | 0.07 |
| Stock status | 0.07 |
| Fit match | 0.06 |
| Brand preference | 0.06 |

Only the dimensions a shopper actually mentioned are scored; the rest are
dropped and their weight redistributed, so “black linen shirt” is not penalised
for saying nothing about brand or size. Each result carries plain-English
reasons such as *“Matches your requested shirt, black colour, linen material and
relaxed fit.”*

No LLM is involved in ranking. See
[`docs/architecture.md`](docs/architecture.md#ranking) for the scoring detail
and [`docs/limitations.md`](docs/limitations.md) for where embeddings would help.

---

## Accounts

Search never requires an account. Optionally, a device can claim an anonymous
account (`POST /api/auth/session`) to save searches and favourites. The `users`
table already carries `email` and `password_hash` for a later upgrade to full
authentication — see [`docs/limitations.md`](docs/limitations.md).

---

## Security

- Query length, word count and character validation before anything else
- Prompt-injection detection; a query that looks like an instruction to the
  model is parsed deterministically instead and never reaches the LLM
- The model's reply is validated against a strict Pydantic model, so a hijacked
  response can only ever produce search filters
- All retailer text is stripped of markup; all URLs must be plain `http(s)`
- Per-IP rate limiting on searches and on requests generally
- Environment validation at startup; production refuses to boot without Redis,
  PostgreSQL, or with wildcard CORS
- Secrets are never logged; click tracking stores hashed client fingerprints

---

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Request lifecycle, module map, ranking and de-duplication internals, design decisions |
| [API reference](docs/api.md) | Every endpoint, every SSE payload, error shapes |
| [Adding a connector](docs/adding-a-connector.md) | Step-by-step, plus the HTML-connector policy |
| [Affiliate networks](docs/affiliate-networks.md) | Awin, Impact, CJ, Rakuten and direct integrations |
| [Deployment](docs/deployment.md) | Vercel, Railway/Render/Fly, Neon/Supabase, Upstash |
| [Limitations](docs/limitations.md) | Known gaps and recommended next steps |
