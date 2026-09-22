# API reference

Base URL in development: `http://localhost:8000`.
Interactive docs: `/docs` (Swagger) and `/redoc`. Schema: `/openapi.json`.

All responses are JSON unless stated. Errors share one shape:

```json
{ "error": "invalid_request", "detail": "Search query is required." }
```

`error` is one of `bad_request`, `unauthorized`, `forbidden`, `not_found`,
`invalid_request`, `rate_limited`, `not_implemented`, `unavailable`,
`internal_error`. Validation failures add a `fields` array. Internal errors
never leak details — the cause is in the structured log, correlated by the
`X-Request-ID` response header.

---

## Search

### `POST /api/search`

Creates a search job and returns immediately. The job runs in the background;
subscribe to the event stream to watch it.

**Request**

```json
{ "query": "Find me a relaxed black linen shirt under $120 that ships to Sydney" }
```

| Field | Rules |
| --- | --- |
| `query` | required, 2–400 characters (`SEARCH_MAX_QUERY_LENGTH`), max 80 words |

No other fields are accepted (`extra: forbid`).

**Response `202 Accepted`**

```json
{
  "search_id": "0f3c…",
  "query": "Find me a relaxed black linen shirt under $120 that ships to Sydney",
  "status": "accepted",
  "events_url": "/api/search/0f3c…/events",
  "snapshot_url": "/api/search/0f3c…"
}
```

**Headers** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-Request-ID`.

**Errors** `422` invalid query · `429` rate limited (with `Retry-After`).

---

### `GET /api/search/{search_id}/events`

Server-Sent Events. `Content-Type: text/event-stream`.

Each frame carries an `id:` (a monotonic sequence number), an `event:` name and
a JSON `data:` payload. Send `Last-Event-ID` on reconnect to replay only what
you missed. Comment frames (`: keep-alive`) arrive every 15 seconds while idle.

Every payload includes `sequence`, `type`, `search_id` and `timestamp`.

```
id: 4
event: products_added
data: {"sequence":4,"type":"products_added","search_id":"0f3c…", …}
```

#### `search_started`

```json
{ "query": "…", "cache_state": "miss", "retailers": [RetailerStatus, …] }
```

#### `intent_parsed`

```json
{
  "intent": SearchIntent,
  "parser": "anthropic" | "deterministic" | "cache",
  "duration_ms": 412,
  "retailers": [RetailerStatus, …]
}
```

`retailers` is repeated here because connectors that cannot serve the parsed
intent are now marked `skipped`.

#### `retailer_started` / `retailer_completed` / `retailer_failed`

```json
{ "retailer": RetailerStatus, "error": "timed out after 8s" }
```

`error` is present only on `retailer_failed`.

#### `products_added`

```json
{
  "groups": [ProductGroup, …],
  "total_products": 12,
  "source": "live" | "cache",
  "results_updated_at": "2026-09-22T05:12:04+00:00"
}
```

`groups` contains only the groups that changed. **Merge by `group_id`** — a
retailer answering late adds an offer to an existing group rather than creating
a new card.

#### `ranking_completed`

```json
{ "groups": [ProductGroup, …], "total_products": 12, "group_count": 5 }
```

The authoritative, fully ordered result set. Replace your list with it.

#### `search_completed`

```json
{
  "status": "completed" | "partial" | "failed",
  "cache_state": "miss" | "fresh" | "stale" | "refreshed" | "coalesced",
  "total_products": 12,
  "group_count": 5,
  "retailers": [RetailerStatus, …],
  "warnings": ["Atlas Trading Co. could not be searched (HTTP 503)."],
  "results_updated_at": "2026-09-22T05:12:04+00:00",
  "duration_ms": 1840
}
```

`partial` means at least one retailer failed; the results from the rest are
still complete and usable. The stream closes after this event.

**Errors** `404` if the search id is unknown and no snapshot survives.

---

### `GET /api/search/{search_id}`

The current state of a search, as a `SearchResult`. Use it for reconnects,
polling clients, or anything that cannot hold an SSE connection.

```json
{
  "search_id": "0f3c…",
  "query": "…",
  "intent": SearchIntent,
  "groups": [ProductGroup, …],
  "retailers": [RetailerStatus, …],
  "status": "completed",
  "cache_state": "miss",
  "total_products": 12,
  "started_at": "…",
  "completed_at": "…",
  "results_updated_at": "…",
  "warnings": []
}
```

---

### `GET /api/ranking`

The live ranking weights and the rules that govern them. Ranking is
deterministic, so this fully explains ordering.

```json
{
  "weights": { "keyword_relevance": 0.25, "price_fit": 0.13, … },
  "notes": ["Only the dimensions present in your query are scored; …"]
}
```

---

## Retailers

### `GET /api/retailers?include_health=false`

```json
[
  {
    "key": "northbound",
    "name": "Northbound Supply",
    "type": "mock" | "feed" | "api" | "html",
    "ships_to": ["AU", "NZ"],
    "currency": "AUD",
    "requires_permission": false,
    "healthy": true,
    "message": "seeded catalogue",
    "latency_ms": 350
  }
]
```

`include_health=true` probes each connector (5s timeout each); health fields are
`null` otherwise.

---

## Click tracking

### `POST /api/clicks`

Records an outbound click for affiliate attribution. The browser navigates
straight to the retailer; this is a side-channel and must never block.

```json
{
  "retailer": "northbound",
  "product_id": "northbound-ksl-lns-01",
  "destination_url": "https://northbound-supply.example/products/…",
  "search_id": "0f3c…",
  "price": 119.0,
  "currency": "AUD",
  "position": 1
}
```

`destination_url` must be a plain `http(s)` URL; anything else is rejected with
`422`. Returns `{ "recorded": true, "click_id": "…", "destination_url": "…" }`.
`recorded` is `false` when no database is configured — the click is still
logged.

---

## Accounts (optional)

Search never requires authentication. These endpoints need `DATABASE_URL`; they
return `501` otherwise.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/auth/session` | Creates an anonymous account, returns a bearer token (`201`) |
| `GET /api/account/saved-searches` | List saved searches |
| `POST /api/account/saved-searches` | Save a search — parses the query and stores the intent (`201`) |
| `DELETE /api/account/saved-searches/{id}` | Remove one (`204`) |
| `GET /api/account/favourites` | List favourites |
| `POST /api/account/favourites` | Save a product snapshot (`201`) |
| `DELETE /api/account/favourites/{retailer}/{product_id}` | Remove one (`204`) |

Authenticate with `Authorization: Bearer <token>`. Only the SHA-256 hash of the
token is stored. Saving the same search twice is idempotent.

---

## Health

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness. Always `200` while the process is up. |
| `GET /health/ready` | Readiness. `503` when the cache is unavailable or no connectors are registered. PostgreSQL being down does **not** make the service unready — search does not depend on it. |

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "development",
  "checks": {
    "cache": "ok",
    "database": "ok" | "unavailable" | "not configured",
    "connectors": 5,
    "active_searches": 0,
    "query_parser": "anthropic" | "deterministic"
  }
}
```

Both health paths are exempt from rate limiting.

---

## Object reference

### `SearchIntent`

| Field | Type | Notes |
| --- | --- | --- |
| `original_query` | string | the sentence as submitted |
| `product_categories` | string[] | canonical: `shirt`, `overshirt`, `trousers`, … |
| `occasion` | string \| null | `wedding`, `work`, `holiday`, … |
| `styles` | string[] | `minimal`, `smart casual`, `workwear`, … |
| `colours` | string[] | canonical: `ecru` → `cream` |
| `materials` | string[] | canonical: `lyocell` → `tencel` |
| `fits` | string[] | `relaxed`, `oversized`, `wide-leg`, … |
| `brands` | string[] | brands to buy **from** |
| `excluded_brands` | string[] | hard exclusion |
| `size` | string \| null | normalised: `m`, `xl`, `32` |
| `minimum_price` / `maximum_price` | number \| null | in `currency` |
| `currency` | string | ISO 4217, default `AUD` |
| `destination_country` | string | ISO 3166 alpha-2, default `AU` |
| `destination_postcode` | string \| null | |
| `destination_city` | string \| null | default `Sydney` |
| `gender` | `men` \| `women` \| `unisex` | default `men` |
| `sort_preference` | `relevance` \| `price_low_to_high` \| `biggest_discount` \| `newest` | |
| `additional_keywords` | string[] | leftover descriptive terms |

"Similar to X" puts X's aesthetic in `styles`, not in `brands` — filtering to X
would exclude exactly the cheaper alternatives being asked for.

### `Product`

`product_id`, `title`, `description`, `brand`, `retailer`, `retailer_name`,
`product_url`, `affiliate_url`, `image_url`, `category`, `colours[]`,
`materials[]`, `available_sizes[]`, `price`, `original_price`, `currency`,
`in_stock`, `shipping_destination`, `shipping_cost`, `source_updated_at`,
`retrieved_at`, `match_score` (0–1), `match_reasons[]`, plus computed
`discount_percent` and `total_price` (price + shipping).

Money is serialised as a JSON number rounded to 2dp. All text is stripped of
markup; all URLs are guaranteed plain `http(s)`.

### `ProductGroup`

One garment, every offer found for it.

| Field | Notes |
| --- | --- |
| `group_id` | stable across searches |
| `primary` | the offer to show: in-stock first, then cheapest incl. shipping |
| `offers` | all offers, same ordering |
| `match_score`, `match_reasons` | the best-scoring offer's |
| `offer_count`, `retailers` | |
| `lowest_total_price` | cheapest **purchasable** total; ignores out-of-stock offers |

### `RetailerStatus`

`key`, `name`, `state` (`pending` \| `running` \| `completed` \| `failed` \|
`skipped`), `product_count`, `duration_ms`, `error`, `attempts`.

---

## Rate limits

| Bucket | Default | Env |
| --- | --- | --- |
| Searches | 20/min per IP | `RATE_LIMIT_SEARCHES_PER_MINUTE` |
| All requests | 120/min per IP | `RATE_LIMIT_REQUESTS_PER_MINUTE` |

Fixed windows. The limiter **fails open** — if the cache is unavailable the site
keeps working. Client identity comes from `X-Forwarded-For` (trusted; strip it
at the edge if you deploy without a proxy), else the socket address.

## CORS

Only the origins in `CORS_ALLOW_ORIGINS` may call the API. Credentials are not
allowed; authentication uses a bearer token, not cookies. Wildcards are rejected
in production.
