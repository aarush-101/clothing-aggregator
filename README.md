# Marle — menswear search aggregator

Marle turns a clothing prompt into filters, searches a persistent product
catalogue, merges the same garment sold by different retailers into one card
with each retailer's price, and links shoppers straight to the original retailers (no affiliate links). It
collects real menswear from **50 Australian Shopify stores**: 19 multi-brand
retailers (Universal Store, Incu, General Pants, SurfStitch, Maplestore, Up
There, Supply Store…) and 31 brand or label stores (Carhartt WIP, Stüssy,
Levi's, Thrills, Deus, Industrie, M.J. Bale…), without any account or API key.

**Status: working initial implementation with limited retailer coverage.**
Every store in the registry has a tested, enabled import. This does not search
every retailer on the internet or guarantee current stock and delivery at
checkout.

A live import on 2026-09-23 stored **206,843 size/colour offers** (117,119 in
stock) for **38,416 distinct listings**. Stores were chosen for overlapping
brands, so the same garment appears at several places (a brand's own store and
its stockists) and is merged: **696 products** currently show prices from more
than one store. See the
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
  narrow offers before ranking; most searches take under 150 ms locally and the
  broadest (“hoodie”, “summer wedding outfit”) about 0.7–1.2 s.
- Brand names in a prompt are recognised from the indexed brands, in any case
  (“levis 501 jeans”, “no nike”), and filter results.
- The same garment from different retailers is merged using brand, a
  normalised title and the full colourway. Two listings from one retailer are
  never merged. Each card links to every retailer's price for that garment.
- The deterministic prompt parser works without credentials. Anthropic parsing
  remains optional. Ranking is deterministic and exposed at `/api/ranking`.
  See [How search understanding works](#how-search-understanding-works) below.

## How search understanding works

A shopper types a sentence; Marle turns it into a structured `SearchIntent`
(filters), queries the catalogue with it, then ranks what comes back. By
default this is **rule-based NLP: pattern matching plus curated vocabularies**,
with no model call, no API key and no per-query cost. An LLM parser can be
switched on, but it is optional and the rules always act as its fallback.

```text
prompt ─► sanitise ─► rule-based parser ─► brand recognition ─► SearchIntent
                            │  (optional: Claude, with rule-based fallback)
SearchIntent ─► SQL prefilter ─► exact filters ─► group & merge ─► rank ─► results
```

### 1. Sanitise ([`sanitise.py`](apps/api/app/services/nlp/sanitise.py))

The query is Unicode-normalised, stripped of control and markup characters
(`< > { } [ ]`, zero-width/bidi characters) and length-checked. Queries that
look like prompt injection (“ignore previous instructions”, “you are now…”,
fake `system:` turns) are flagged and never sent to an LLM.

### 2. Rule-based parser ([`fallback_parser.py`](apps/api/app/services/nlp/fallback_parser.py))

The parser reads the sentence in a fixed order and **removes each recognised
span before the next step**, so “$120” can never be mistaken for a size and a
word is never counted twice.

| Step | Recognises | Examples |
| --- | --- | --- |
| Price | upper/lower bounds and ranges | “under $120”, “over 80”, “between $50 and $90”, “$80–120”, “around $100” (±20%) |
| Size | letter and waist sizes | “size M”, “in medium”, “32 waist”, “W32” → `m`, `32` |
| Garment | category, via synonyms | “joggers” → `trackpants`, “jumper” → `knitwear`, “tee” → `t-shirt` |
| Attributes | colour, material, fit, style, occasion, season | “charcoal” → grey, “relaxed” → fit, “wedding” → occasion |
| Brands | preferred, excluded, “similar to” | “by Nike”, “not from Billabong” (excluded), “like Carhartt” (a style hint, not a filter) |
| Context | currency, destination, gender, sort order | “USD”, “ships to Melbourne”, “women's”, “cheap” / “on sale” / “new in” |
| Keywords | whatever meaningful words remain | “summer”, “501”, “oversized” |

Real parser output:

| Prompt | Parsed intent |
| --- | --- |
| relaxed black linen shirt size M under $120 for a summer wedding | category `shirt`, colour `black`, material `linen`, fit `relaxed`, size `m`, max `120`, occasion `wedding`, keyword `summer` |
| grey joggers between $50 and $90 | category `trackpants`, colour `grey`, min `50`, max `90` |
| swim shorts not from Billabong | category `swimwear`, excluded brand `billabong` |

Defaults: men's, AUD, destination Sydney, sorted by relevance.

**Vocabularies** live in [`lexicon.py`](apps/api/app/services/nlp/lexicon.py):
each canonical term maps to its synonyms. Garment categories are compiled into
one regular expression that tries the **longest phrase first**, so “swim
shorts” is swimwear rather than shorts and “polo shirt” is a polo rather than a
shirt. Broad categories include narrower ones (trousers → chinos, trackpants).

The **same classifier labels products at import**. For titles it takes the
*last* garment noun, because English titles end with the item itself: “Linen
Shirt **Jacket**” is an overshirt, “Short Sleeve **Shirt**” a shirt. The brand
prefix is removed first, so “Tommy Jeans CC Holder” is an accessory, not jeans.
Query and catalogue therefore share one vocabulary.

### 3. Brand recognition from the catalogue ([`catalogue.py`](apps/api/app/services/catalogue.py))

Rules alone only catch capitalised brands after “by/from”. After parsing,
`Catalogue.recognise_brands` matches the prompt against the **~640 brands
actually in the index**, normalised so “levis”, “LEVIS” and “Levi's” are equal,
and “stussy” matches “Stüssy”. It also accepts distinctive short forms
(“carhartt” → Carhartt WIP, “north face” → The North Face). A preceding “no”,
“not”, “without” or “not from” turns a match into an exclusion. Brands whose
names are also garment, colour or material words are never matched, so a label
called “Linen” cannot hijack linen searches.

### 4. Optional LLM parser ([`anthropic_parser.py`](apps/api/app/services/nlp/anthropic_parser.py))

With `ANTHROPIC_API_KEY` set, Claude is asked for a JSON object matching a
strict `SearchIntent` schema. Safeguards:

- The rule-based parse always runs first. Any failure, timeout, empty answer or
  flagged prompt falls back to it.
- Price and size are backfilled from the rules if the model omits them; they
  are stated literally in the text, so the regex is authoritative.
- The reply is validated into a typed model, so even a hijacked response can
  only produce search filters.

The LLM path has not been validated against live data. Before enabling it, map
its categories onto the lexicon's canonical names (today they are only
lowercased, so “t-shirts” would match nothing) and set `ANTHROPIC_MODEL` to a
current model ID.

### 5. From intent to results

1. **SQL prefilter.** Indexed columns narrow offers by category, price, size,
   stock and brand; colours, materials and keywords use `LIKE` on a stored
   lowercase search text. SQL returns a superset, and only those rows are decoded.
2. **Exact filters** in Python apply the precise rules (a colour must be the
   product's own colour, not a word in its description).
3. **Grouping.** Sizes of one product in one colour become one card; the
   displayed price is the cheapest in-stock size, with the sizes at that price.
4. **Merging.** The same garment at different stores (same brand, normalised
   title and colourway) becomes one card listing every store's price.
5. **Ranking.** A transparent weighted score, published at `GET /api/ranking`:

| Signal | Weight |
| --- | ---: |
| Keyword relevance | 0.25 |
| Price fit | 0.13 |
| Category | 0.12 |
| Colour | 0.09 |
| Size availability | 0.08 |
| Material, shipping, stock status | 0.07 each |
| Fit, brand preference | 0.06 each |

### Limits of the NLP

- **No semantic understanding:** vague requests (“something for a date night”)
  rely on the occasion and keyword lists, not on meaning. There are no embeddings.
- **No typo tolerance:** “hoddie” does not match hoodie.
- **Vocabulary-bound:** a garment or colour missing from the lexicon falls back
  to keyword matching. Extend `lexicon.py` to teach it new terms.
- **Capitalisation:** the rule-based brand patterns need capitals (“by Nike”);
  lowercase brands are caught by catalogue recognition instead.

Tests: [`test_fallback_parser.py`](apps/api/tests/test_fallback_parser.py),
[`test_catalogue.py`](apps/api/tests/test_catalogue.py) and
[`test_ranking.py`](apps/api/tests/test_ranking.py).

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
| [Deployment](docs/deployment.md) | Local SQLite, PostgreSQL, workers and hosting |
| [Limitations](docs/limitations.md) | Coverage, freshness and operational limits |
