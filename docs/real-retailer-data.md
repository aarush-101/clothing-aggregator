# Getting real retailer data in

Audience: whoever decides which data sources this product ships with.

## Summary

The Shopify public-JSON route is built and tested, but **it does not work
server-side**. Every verified storefront blocks our client at the CDN. The
routes that do work all need a credential or a relationship — none of them
need much code, because the connector layer is already built.

**Fastest path to real menswear inventory: the eBay Browse API** (free
developer account, sanctioned, large clothing catalogue). Best *brand*
coverage: an affiliate network.

---

## What I tried, and the measurement

I probed 213 menswear domains for Shopify's public `/products.json`.

| Result | Count |
| --- | --- |
| Domains tested | 213 |
| Serve a public `products.json` | **93** (verified, currency/country read from each store's `/meta.json`) |
| Accept our server-side HTTP client | **0 of 93** |

Every one of the 93 returned `HTTP 429` with the header
`cf-mitigated: challenge` — Cloudflare issuing a bot challenge on the stores'
behalf. A handful of large retailers (MR PORTER, SSENSE, Rhone, Country Road)
returned `403` before that, which is the same message stated more plainly.

Getting past a Cloudflare challenge requires TLS-fingerprint spoofing, a
headless browser, or proxy rotation. All three are anti-bot evasion. This
project does not do that — it is prohibited by the brief, it is the kind of
thing that ends retailer relationships before they start, and it breaks
constantly. **The 93-store list is a research artefact, not a data source.**

The connector and the store list are kept (`app/connectors/shopify.py`,
`app/data/shopify_stores.json`), disabled by default, because they become
immediately useful via route B below.

---

## Routes that work

### A. eBay Browse API — recommended first move

Free developer account, OAuth client-credentials, designed for exactly this.
Large menswear inventory with real images, prices, conditions and buyable
links, and an affiliate programme (EPN) for monetisation.

- **Cost:** free tier
- **Approval:** self-serve developer account
- **Effort:** ~1 day — a `RetailerConnector` subclass plus token caching
- **Coverage:** very broad, but marketplace inventory (mixed new/used, many
  sellers) rather than curated brand.new stock
- **Caveat:** not verified here, because it needs credentials. The endpoint is
  `GET /buy/browse/v1/item_summary/search?q=...&category_ids=...`.

### B. Shopify Storefront API — the sanctioned version of what I built

The same 93 stores are reachable **with a merchant-issued Storefront API
access token**. That is Shopify's supported interface; it is not challenged,
because it is authenticated and intended for third-party clients.

- **Cost:** free
- **Approval:** per-merchant — each brand issues you a token
- **Effort:** ~half a day to extend `ShopifyConnector` to the GraphQL
  Storefront endpoint; the normalisation, department filtering, colour/size
  extraction and caching are already written and tested
- **Coverage:** exactly the brands you sign, from the 93 already identified
- **Why it is realistic:** DTC brands want to be in a shopping engine that
  sends them traffic. This is a business-development task, not an engineering
  one.

### C. Affiliate networks — best brand coverage

Awin, Impact, CJ, Rakuten. This is how ASOS, Uniqlo, COS, THE ICONIC and the
other names a shopper actually types become reachable.

- **Cost:** free to join; they take a cut of commission
- **Approval:** publisher account, then per-advertiser approval (days to weeks)
- **Effort:** **zero code.** The generic feed connector is built. A feed is a
  `.env` entry — see [affiliate-networks.md](affiliate-networks.md)
- **Coverage:** the best available

### D. Commercial product-data APIs

Paid aggregators that resell retailer catalogues or Google Shopping results.
Fast to integrate and broad, but recurring cost, and you inherit whatever
compliance posture the vendor has — diligence them before depending on one.

### E. Direct retailer partnerships

A retailer hands you a feed or an API. Best data quality and the only route
that scales into a real business, but it is a commercial conversation.

---

## Recommended sequence

1. **eBay Browse API** — real inventory in the product within a day, no
   gatekeeper. Proves the pipeline end to end against live data.
2. **Apply to one affiliate network** in parallel (Awin for UK/EU, Impact or
   Rakuten for AU/US). Approval takes time, so start the clock early.
3. **Approach 10–15 DTC brands** from `shopify_stores.json` for Storefront API
   tokens. Lead with traffic, not with a data request.
4. **Turn the mock connectors off** in production once two real sources are
   live; keep them for tests, where they are genuinely valuable.

## What is already built and waiting

| Piece | State |
| --- | --- |
| Generic JSON/XML feed connector | Done, tested. Config-only for any affiliate feed. |
| Shopify connector | Done, 18 tests. Needs the Storefront API swap for route B. |
| Store discovery list (93 stores, currency + country) | Done, in `app/data/shopify_stores.json`. |
| Per-store catalogue caching | Done, so repeat searches cost retailers nothing. |
| Cold-fetch budget | Done, so a first search never fans out to 93 stores at once. |
| Department filtering (mens/womens/kids/gift cards) | Done, tested. |
| Cross-currency price comparison | Done — USD/GBP/EUR/AUD/NZD/DKK/SEK/NOK/CHF/CAD/SGD/JPY. |
| Affiliate click tracking and sub-ids | Done. |

Adding a source is a connector and a config entry. The expensive part of this
product — parsing, ranking, de-duplication, caching, streaming — is finished
and does not change per source.
