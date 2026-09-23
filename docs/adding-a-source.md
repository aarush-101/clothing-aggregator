# Adding a retailer source

The running app imports configured sources into SQL. Do not add a new
search-time connector: searches read the index.

0. Prefer retailers that stock the same brands as existing sources. A
   single-brand store adds products but never duplicates to merge. Compare
   page-1 `vendor` values with the brands already indexed.
1. Add or review the retailer in
   [`retailers.json`](../apps/api/app/data/retailers.json). Record its official
   menswear page and website-review evidence.
2. Check its men's collection and robots rules from the deployment environment.
   For the existing Shopify adapter, verify the collection's public product
   JSON, variant fields, pagination, currency and purchase links.
3. Add an `ingestion` object, initially disabled:

```json
{
  "enabled": false,
  "method": "shopify_json",
  "collection": "mens",
  "currency": "AUD",
  "refresh_seconds": 21600,
  "max_pages": 30
}
```

   Optional ingestion settings:
   - `"default_brand": "Label"` for an own-label store whose vendor field is a
     department ("Mens") or empty.
   - `"vendor_brands": {"Levi AUS/NZ Production": "Levi's"}` when a brand
     store uses internal vendor names. Without it, the brand displays oddly
     and never matches the same label at other retailers, so nothing merges.
   - `"garments_only": true` for a catch-all collection that also contains
     homewares or books; unclassifiable products are skipped.

   Check that robots.txt allows the exact `?limit=250&page=1` URL: rules such
   as `Disallow: /*?*` or `Disallow: /*limit=*` block pagination.

   **Probe gently.** Shopify rate-limits a client IP across *all* stores it
   hosts. A burst of ~1 request/second across many stores triggered a 429
   “Verifying your connection” on every Shopify store, including enabled
   sources, for about 10–15 minutes. Leave several seconds between probe
   requests, one store at a time.

4. Enable it for a controlled import and run
   `python -m app.ingest --once --retailer RETAILER_KEY --force`. Record a dated
   access report before describing access as validated. The CLI exits nonzero
   if selected sources fail. Inspect `/api/retailers` and verify real searches.
5. Commit the registry and report. If access fails, keep its state honest and
   disable scheduled ingestion if the failure needs manual investigation.

Only one enabled source per host is supported, so workers cannot accidentally
ignore a site's request budget. The adapter rejects redirects outside the
configured HTTPS host and honours robots patterns, crawl delay, Retry-After,
response-size and page limits. It does not solve challenges or rotate proxies.

For a different API/feed format, implement a new ingestion adapter in
`app/sources/` and validate its configuration. It must emit normalised variant
offers, distinguish unknown stock/shipping, and return a complete snapshot only
when it has actually traversed the source scope. Partial feeds must not be fed
to the current complete-snapshot publisher. Add offline tests for malformed
records, pagination, variant correctness, failures and removal behaviour.

No generic HTML or feed adapter is bundled. Marle links directly to retailers
and does not use affiliate links.
Credentials belong in environment/secrets storage, never the registry.
