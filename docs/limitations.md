# Limitations and next steps

An account of what the current prototype does not do. The accepted direction
now includes a persistent product index and background ingestion; see
[product-index.md](product-index.md). Those capabilities are not implemented.

---

## Data

### The bundled retailers are fictional

The four mock retailers, the flaky fifth, and the sample feed are invented, on
the reserved `.example` TLD, with invented brands. This is deliberate: shipping
fabricated products attributed to real shops would be dishonest, and the
`.example` domain guarantees no real site is ever contacted.

The consequence is that **"View at retailer" links for mock products do not
resolve.** The click is still tracked and the affiliate template still expands —
only the destination is fictional.

*Next:* validate a real source and ingest it into the planned product index.
Keep mocks in explicit demo/test mode; live indexed search must never silently
fall back to fictional inventory.

### No real retailer relationships

Nothing here has credentials for Awin, Impact, CJ or Rakuten. Those require
approved publisher accounts and per-advertiser approval. The generic feed
connector provides field mapping, but each source still needs validation and
an ingestion adapter with pagination and completeness tracking.

### Unknown stock and shipping are not modelled accurately

`Product.in_stock` defaults to `True`, and `total_price` treats a missing shipping
cost as zero. Those defaults cannot support reliable indexed offers when source
data is incomplete or stale.

*Next:* explicit unknown availability and shipping, variant-specific prices and
verification timestamps across storage, ranking, filters and UI.

### Currency conversion uses static rates

`services/currency.py` carries indicative rates so cross-currency price filters
work offline. They drift.

*Next:* a cached live FX source (ECB daily, or a commercial feed), refreshed
hourly, with the rate and its timestamp shown wherever a converted price is
displayed.

---

## Search quality

### Ranking is keyword-based, not semantic

Scoring is deterministic token overlap plus structured attribute matching. It is
fast, explainable and testable, and it cannot silently regress — but it will
miss "something to wear to my brother's wedding in Noosa in January" unless the
parser turns that into attributes first.

*Next:* embed product titles and descriptions once per retrieval, embed the
intent, and add a semantic-similarity dimension to `RankingWeights` with a
modest weight. The architecture already supports this — add a dimension, give it
a weight, and the existing tests will tell you what moved. Keep the
deterministic dimensions: an aggregator that cannot explain its ordering is hard
to debug and hard to trust.

### De-duplication is heuristic

Brand + normalised title + colour, model identifiers and image filenames catch
the common cases. They will miss retailer-specific renaming ("Kessler Relaxed
Linen Shirt" vs "Relaxed Shirt in Black Linen by Kessler") and they can
over-merge two genuinely different garments that share a stock photo.

*Next:* add perceptual image hashing and a title-similarity threshold, and
measure precision and recall against a hand-labelled set before tuning.

### Size handling is simplified

Sizes are normalised to comparable tokens (`m`, `xl`, `32`) but there is no
conversion between systems (EU 50 vs UK 40 vs M) and no per-brand sizing.

*Next:* a brand-aware size table, and a "fits like" signal derived from returns
or reviews where a retailer exposes it.

### Occasion queries are shallow

"Smart casual outfit for a summer wedding" returns individually relevant
garments, not a coordinated outfit. There is no outfit-building logic.

*Next:* a composition layer that picks one item per slot (top / bottom / shoe)
under a total budget, with colour and formality coherence rules.

---

## Architecture

### The SSE broker is per-process

`event_bus.py` holds streams in memory. With more than one API instance, a
browser reconnect can land on an instance that never ran that search. The
endpoint degrades gracefully — it replays the cached snapshot instead of
404ing — but progress events are lost for that reconnect.

*Next:* implement the same interface over Redis pub/sub (publish on the search's
channel, subscribe in the SSE handler, replay from the persisted event list), or
run sticky sessions. The interface is already narrow enough to swap.

### Cache invalidation is time-based only

Results expire; there is no way to say "this retailer's prices changed, drop
their entries". Fine at this scale, wrong once you have price alerts.

*Next:* per-retailer cache tags so a feed refresh can invalidate just that
retailer's contribution.

### Analytics write on the request path

`search_analytics` and `connector_health_records` are written inline at the end
of a search. Failures are caught and logged, so they never break a search, but
they add latency and the tables grow unbounded.

*Next:* push to a queue, and add a retention policy (or roll up
`connector_health_records` hourly).

### No product index or scheduled ingestion yet

The current search engine starts tasks in response to user searches. There is
no independent ingestion worker, scheduler or persistent product table. The
former on-demand-only restriction has been retired; these are now missing
capabilities rather than deliberate exclusions.

*Next:* persistent listings and variant offers, idempotent ingestion, indexed
candidate retrieval, then scheduled refresh/expiry jobs. Follow
[product-index.md](product-index.md) for leases, snapshot completeness and
source budgets. Price/restock alerts can build on that infrastructure later.

---

## Accounts

### Authentication is a device token, not a login

`POST /api/auth/session` mints an anonymous account and returns a bearer token
stored in `localStorage`. Favourites and saved searches genuinely work, and
search never requires an account. But there is no email, no password, no session
expiry, and no way to move an account to another device.

The `users` table already carries `email` and `password_hash`.

*Next:* either add email/password with proper hashing and verification, or
delegate to Supabase Auth / Auth0 and map the subject onto `users.id`. Add token
rotation and expiry at the same time.

### No account deletion or data export

There is no self-service way to delete an account or export its data. Required
before any real launch under GDPR or the Australian Privacy Act.

---

## Frontend

### No virtualisation

Every result group renders. `SEARCH_MAX_RESULTS` caps this at 120 groups, which
is comfortable, but removing that cap without virtualising the grid would not
be.

### Images are unoptimised

Plain `<img>` with lazy loading and a graceful failure panel, not `next/image`.
Retailer imagery comes from arbitrary hosts that cannot be allow-listed in
advance, and the optimiser would need network access at request time.

*Next:* once the real retailer set is known, add their hosts to
`images.remotePatterns` and switch to `next/image` for the measurable LCP win.

### Refinement is client-side only

Filters and sorting operate on the result set already returned. Fast and
instant, but you cannot filter to something no retailer returned for the
original query.

*Next:* in indexed mode, re-query the index when a filter needs products outside
the returned page. Local filtering remains useful within an already loaded set.

### No design-system webfont

System font stacks, so the build works offline and there is no flash of unstyled
text. A licensed display face would sharpen the editorial feel.

*Next:* `next/font/local` with a self-hosted subset.

---

## Testing and tooling

- **No visual regression tests.** Playwright covers behaviour and layout
  overflow, not appearance.
- **No load testing.** Concurrency limits and timeouts are reasoned, not
  measured. Measure before choosing production values.
- **No contract tests against real feeds.** Connector tests use fixtures. Once a
  real feed is connected, add a recorded-response test so a schema change fails
  in CI instead of in production.
- **Accessibility is tested structurally, not audited.** Roles, labels, focus
  order, keyboard operation and live regions are covered by tests; there has
  been no screen-reader pass or automated axe run.

*Next:* add `@axe-core/playwright` to the e2e suite, and do one manual pass with
VoiceOver before launch.

---

## Operational

- **No admin UI.** `retailer_configs` exists but nothing reads it at runtime yet;
  connector configuration comes from environment variables at boot.
  *Next:* load overrides from the table on startup and expose a small admin API.
- **No per-retailer circuit breaker.** A retailer that is down is retried on
  every search. `connector_health_records` has the data to drive one.
  *Next:* trip a breaker after N consecutive failures and skip that connector
  for a cooling-off period.
- **`X-Forwarded-For` is trusted.** Correct behind a single managed proxy, wrong
  if the API is exposed directly. Strip the header at the edge.
- **No affiliate disclosure UI.** Outbound links carry
  `rel="nofollow sponsored"`, but there is no visible disclosure. Add one before
  launch in any market that requires it.

---

## Recommended order of work

1. Validate representative live menswear sources serving Australia.
2. Add persistent listings/offers and import a validated source idempotently.
3. Search the index, with explicit unknown values and visible freshness.
4. Add scheduled ingestion, leases, source cooldowns, expiry and cache invalidation.
5. Expand discovery through additional sources and evaluate a search provider.
6. Complete launch requirements such as live FX, account privacy controls and
   multi-instance event delivery; benchmark search quality and source reliability.
7. Consider semantic ranking and outfit composition after measuring the core
   search experience.
