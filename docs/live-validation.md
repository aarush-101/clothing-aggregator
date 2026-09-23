# Live source validation — 2026-09-23

## Second import: eight sources, cross-retailer matching

Later the same day, four multi-brand Shopify stores were checked for brand
overlap with the existing sources (robots.txt, `/meta.json` AUD, page-1
collection JSON, a later empty page, same-host product URL). Three were enabled.
The schema moved to migration `0003` (filter columns), which rebuilt the offers
table, and all sources were re-imported with `python -m app.ingest --once --force`.

| Retailer | Collection | Stored variant offers | In stock | Listings |
| --- | --- | ---: | ---: | ---: |
| Assembly Label | `mens-shop-all` | 812 | 642 | 136 |
| Academy Brand | `mens` | 2,561 | 2,058 | 419 |
| Industrie | `all` | 9,879 | 7,105 | 1,635 |
| Universal Store | `mens` | 16,958 | 10,667 | 2,811 |
| Incu | `mens-clothing` | 7,207 | 5,109 | 1,688 |
| Highs and Lows | `mens-clothing` | 1,655 | 978 | 403 |
| Up There | `clothing` | 6,934 | 2,799 | 1,697 |
| General Pants Co. | `mens-clothing` | 10,709 | 6,139 | 1,904 |
| **Total** | | **56,715** | **35,497** | **10,693** |

Culture Kings passed the manual page-1 check but its robots.txt contains
`Disallow: /*?*`, which forbids every paginated `?page=` request. The importer
refused it, as designed; it is recorded as `blocked` and not enabled.

Across all in-stock colourways (9,444 cards before grouping), **52 groups merge
offers from more than one retailer**. A random sample of 15 merged groups were
all the same garment, e.g. Carhartt WIP “OG Active Jacket” (Incu, AUD 550) with
“OG Active Jacket - Black Rinsed” (Highs and Lows, AUD 550), and Norse Projects
“Teno Cotton Hemp Military Rib Zip Cardigan” (Up There AUD 380, Incu AUD 415).
Overlap is still limited: many shared brands (Levi's, Dickies) are listed under
different product names or wash names by different stores and are not merged.

Index query times measured in-process against this database (parse excluded):

| Prompt | Results | Query |
| --- | ---: | ---: |
| black linen shirt under $120 | 1 | 30 ms |
| something black under $50 | 441 | 220 ms (was ~3.4 s) |
| summer wedding outfit | 542 | 456 ms (was ~4.0 s) |
| nike t-shirt | 34 | 36 ms |
| carhartt jacket | 14 groups, 1 cross-retailer | 15 ms |
| jeans | 663 groups | 743 ms |

A browser session against the running app confirmed merged cards list the other
retailer's price with a working product link, with no page errors.

## First import: five sources

Environment: local macOS checkout, Python/httpx backend, SQLite persistence,
ordinary HTTPS with `User-Agent: Marle/0.1 (menswear product index)`. No eBay
account, provider API key, proxy rotation or browser impersonation was used.
This is a dated observation, not a guarantee of future access or stock.

## Import

Executed `python -m app.ingest --once --force`. Every source completed its
pagination with a final empty products page and published its snapshot.

| Retailer | Collection endpoint | Stored variant offers |
| --- | --- | ---: |
| Assembly Label | [mens-shop-all](https://assemblylabel.com/collections/mens-shop-all/products.json) | 812 |
| Academy Brand | [mens](https://academybrand.com/collections/mens/products.json) | 2,561 |
| Industrie | [all](https://www.industrie.com.au/collections/all/products.json) | 9,873 |
| Universal Store | [mens](https://www.universalstore.com/collections/mens/products.json) | 16,979 |
| Incu | [mens-clothing](https://www.incu.com/collections/mens-clothing/products.json) | 7,210 |
| **Total** | | **37,435** |

Counts include individual size/colour variants and unavailable offers retained
for source fidelity. They are not distinct-garment counts. Explicit non-menswear
and gift-card records are excluded. All five sources returned HTTP 200 on the
collection probes. Robots checks allowed these URLs; `/meta.json` confirmed AUD
on each domain. The import uses a one-second minimum request gap, increased by
any declared crawl delay/request rate, and at most 30 pages per source.

The first integration attempt exposed a local HTTP decoding bug: a decompressed
body was being wrapped with its old content-encoding header. That bug was fixed
and the complete import above then succeeded. Those failed runs did not publish
inventory. The database retains the run history.

## Search through the HTTP API

Started a separate API process with ingestion and Anthropic parsing disabled,
reading the stored database. `/health/ready` reported 37,435 unexpired variant
offers. `POST /api/search`, the SSE stream and the snapshot endpoint completed:

| Prompt | Returned groups | Example observed offer |
| --- | ---: | --- |
| black linen shirt under $120 | 1 | Industrie St Martins Short Sleeve Linen Shirt — AUD 89.95 |
| linen shirt size M under $150 | 81 | Academy Brand Hopper SS Shirt — AUD 20.00, size M |
| navy shorts size 32 | 15 | Academy Brand Stripe Riviera Linen Short — AUD 54.00, size 32 |

Each complete request/SSE/snapshot sequence took roughly 1–1.5 seconds locally.
These timings include re-reading the snapshot and are not a load benchmark.
Prices are source observations from this date. Product links retain the selected
variant ID; shipping charges/destinations remain unknown.

Offline integration tests separately check persistence through a new database
connection, request-free search, variant selection, worker lease exclusion,
expiry, source failure preservation, reconciliation and snapshot invalidation.
The migration chain was applied successfully to a fresh SQLite database.
The frontend production build, types, lint and format checks passed. Offline
browser tests passed on desktop/mobile (36 passed; 8 layout-specific skips).
A separate browser check against the real imported database verified the
Industrie shirt's image, AUD 89.95 price, retailer URL and all five source rows.
The mobile navy-shorts search returned 15 cards with no horizontal overflow or
browser script errors. One sampled product URL from each source returned HTTP
200 on its configured retailer host.

A follow-up Industrie import removed a department label ("Mens") from the brand
field. Missing brand evidence stays unknown. The source adapter was retested
after that correction.

## Limits

Only these five sources were ingested, from this local environment. THE ICONIC,
UNIQLO, Country Road, AS Colour and Cotton On remain website-reviewed entries
without a product adapter. Hosted deployment access, long-term reliability,
shipping eligibility and checkout inventory were not established by this run.
