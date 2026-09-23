# Live source validation — 2026-09-23

## Third import: 50 stores

Two research passes found Australian Shopify stores that overlap our brands:
14 multi-brand retailers and 28 brand-direct or label stores. Each passed the
same checks (canonical HTTPS root, `/meta.json` AUD, Protego allowing the exact
`?limit=250&page=1` URL, page-1 JSON with variant price/availability, an empty
final page within 60 pages, same-host product page). THE ICONIC, UNIQLO,
Country Road, AS Colour and Cotton On were removed from the registry: they are
not Shopify stores and Marle does not use affiliate feeds.

**Platform-wide rate limit.** Both research passes triggered HTTP 429
“Verifying your connection” from *every* Shopify store (including enabled
sources) after bursts of roughly one request per second across many hosts. It
cleared after 10–15 minutes. The importer now shares one request clock across
all sources (2 s default) and stops the round on any 429/challenge. The full
50-store import then ran with the API's background worker and completed with
no 429s.

| Retailer | Type | Collection | Offers | In stock | Listings |
| --- | --- | --- | ---: | ---: | ---: |
| Academy Brand | Brand / label store | `mens` | 2,561 | 2,058 | 419 |
| Afends | Brand / label store | `all-mens-clothing` | 1,755 | 1,462 | 329 |
| Assembly Label | Brand / label store | `mens-shop-all` | 812 | 642 | 136 |
| Barney Cools | Brand / label store | `shop-all` | 391 | 271 | 71 |
| Budgy Smuggler | Brand / label store | `mens-swimwear-1` | 1,320 | 1,059 | 183 |
| Carhartt WIP Australia | Brand / label store | `men` | 4,238 | 3,382 | 653 |
| Commas | Brand / label store | `all` | 1,201 | 354 | 216 |
| Deus Ex Machina Australia | Brand / label store | `mens` | 4,915 | 2,704 | 860 |
| Dickies Australia | Brand / label store | `mens-clothing` | 1,532 | 1,064 | 209 |
| Former Merchandise Australia | Brand / label store | `shop-all` | 1,022 | 776 | 211 |
| Gramicci Australia | Brand / label store | `mens` | 1,632 | 975 | 400 |
| Industrie | Brand / label store | `all` | 9,879 | 7,105 | 1,635 |
| Jac + Jack | Brand / label store | `mens-view-all` | 300 | 224 | 50 |
| Kiss Chacey | Brand / label store | `all` | 8,722 | 1,952 | 1,453 |
| Ksubi Australia | Brand / label store | `mens` | 2,529 | 1,907 | 316 |
| Levi's Australia | Brand / label store | `men` | 3,991 | 2,387 | 322 |
| M.J. Bale | Brand / label store | `all` | 13,052 | 10,736 | 2,175 |
| Mr Simple | Brand / label store | `all` | 1,366 | 871 | 217 |
| Nena & Pasadena | Brand / label store | `all` | 10,541 | 2,659 | 1,724 |
| Nique | Brand / label store | `mens` | 285 | 201 | 55 |
| P. Johnson | Brand / label store | `shop-all-mens` | 1,060 | 935 | 300 |
| Rusty Australia | Brand / label store | `mens` | 2,004 | 965 | 187 |
| Saturdays NYC Australia | Brand / label store | `all` | 1,214 | 1,020 | 361 |
| Status Anxiety | Brand / label store | `mens` | 21 | 21 | 21 |
| Stussy Australia | Brand / label store | `all` | 2,584 | 1,811 | 772 |
| Thrills | Brand / label store | `mens-all` | 2,690 | 1,664 | 401 |
| Uncut | Brand / label store | `all` | 565 | 360 | 89 |
| WNDRR | Brand / label store | `all` | 2,580 | 1,960 | 390 |
| Worship Supplies | Brand / label store | `mens` | 881 | 540 | 126 |
| XLarge Australia | Brand / label store | `full-collection` | 2,327 | 1,188 | 330 |
| Zanerobe | Brand / label store | `all` | 15,001 | 1,025 | 2,551 |
| 50-50 Skate Shop | Multi-brand | `clothing` | 3,948 | 1,640 | 1,253 |
| Beachin Surf | Multi-brand | `mens` | 4,713 | 1,333 | 439 |
| Bodhi Surf | Multi-brand | `mens-surfwear-australia` | 2,166 | 1,323 | 437 |
| General Pants Co. | Multi-brand | `mens-clothing` | 10,709 | 6,139 | 1,904 |
| HAVN | Multi-brand | `mens` | 3,613 | 2,230 | 875 |
| Highs and Lows | Multi-brand | `mens-clothing` | 1,655 | 978 | 403 |
| Incu | Multi-brand | `mens-clothing` | 7,207 | 5,109 | 1,688 |
| Locality Store | Multi-brand | `apparel` | 4,063 | 725 | 1,227 |
| Maplestore | Multi-brand | `mens-clothing` | 4,395 | 2,803 | 875 |
| Natural Necessity Surf Shop | Multi-brand | `mens-clothing` | 1,768 | 389 | 115 |
| Ozmosis | Multi-brand | `mens-clothing` | 2,432 | 1,825 | 453 |
| Providence Clothing Co | Multi-brand | `clothing` | 3,707 | 1,561 | 587 |
| Skate Connection | Multi-brand | `apparel` | 2,689 | 1,553 | 676 |
| Street Machine Skateboarding | Multi-brand | `apparel` | 746 | 288 | 128 |
| Supply Store | Multi-brand | `frontpage` | 7,654 | 4,443 | 2,041 |
| SurfStitch | Multi-brand | `mens-clothing` | 16,747 | 15,569 | 3,299 |
| Universal Store | Multi-brand | `mens` | 16,958 | 10,667 | 2,811 |
| Up There | Multi-brand | `clothing` | 6,934 | 2,799 | 1,697 |
| Vast Outdoors | Multi-brand | `mens-clothing` | 1,768 | 1,467 | 346 |
| **Total (50)** | | | **206,843** | **117,119** | **38,416** |

Status Anxiety's collection is mostly items tagged for women or unclassified
accessories, so few offers remain after filtering.

**Matching.** Across 31,469 in-stock colourways, 696 groups merge offers from
more than one store (previously 52). A random sample of 15 were all the same
garment, e.g. Carhartt WIP “Brandon Pant” at HAVN, Incu, Carhartt WIP AU and
Supply Store (AUD 240–259.95); Thrills “Visions Jacob Pant - Black” at Thrills
and Universal Store; Rusty “Flip Daddy Reversible Webbing Belt” at Rusty and
Bodhi Surf. Brand stores' internal vendor names (“Levi AUS/NZ Production”,
“Grammici Shopify”) are mapped per source with `vendor_brands`.

**Speed** (in-process, parse excluded; SQL query + grouping/ranking):

| Prompt | Groups | Query | Rank |
| --- | ---: | ---: | ---: |
| black linen shirt under $120 | 12 | 56 ms | 2 ms |
| carhartt jacket | 85 | 35 ms | 16 ms |
| norse projects | 208 | 54 ms | 33 ms |
| swim shorts | 926 | 247 ms | 136 ms |
| hoodie | 1,856 | 473 ms | 270 ms |
| summer wedding outfit | 1,256 | 955 ms | 224 ms |


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
refused it, as designed, and it was removed from the registry.

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
