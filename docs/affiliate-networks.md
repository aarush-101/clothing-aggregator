# Affiliate network integrations

How to wire the major networks into the generic feed connector. None of this
requires new code — a network integration is a feed configuration plus a
deep-link template.

> This document describes **how to integrate once you have access**. It does not
> imply any of these relationships exist. Each network requires an approved
> publisher account and per-advertiser approval.

---

## The general shape

Every network works the same way:

1. Apply as a publisher; get approved per advertiser (retailer).
2. Fetch that advertiser's product feed (JSON, XML or CSV over HTTPS).
3. Build outbound links through the network's redirect domain, with your
   publisher id and a click reference you choose.
4. Reconcile the click reference against your own click events.

Map (1)–(2) onto `AFFILIATE_FEEDS`, and (3) onto `AFFILIATE_TEMPLATES`.

```bash
AFFILIATE_TEMPLATES='{"<retailer key>": "<network template with {url} and {subid}>"}'
```

`{url}` → the URL-encoded destination. `{subid}` → our deterministic id,
`ca-<retailer>-<hash>`, which is stable per product so it survives caching.

---

## Awin

**Feed** — Create-a-Feed produces a downloadable URL per advertiser; XML and CSV.

```json
{
  "key": "awin_northbound",
  "display_name": "Northbound",
  "url": "https://productdata.awin.com/datafeed/download/apikey/<KEY>/language/en/fid/<FEED_ID>/format/xml/",
  "format": "xml",
  "items_path": "product",
  "currency": "AUD",
  "ships_to": ["AU"],
  "field_map": {
    "product_id": "aw_product_id",
    "title": "product_name",
    "brand": "brand_name",
    "description": "description",
    "product_url": "aw_deep_link",
    "image_url": "aw_image_url",
    "category": "merchant_category",
    "price": "search_price",
    "original_price": "rrp_price",
    "currency": "currency",
    "colours": "colour",
    "in_stock": "in_stock"
  }
}
```

**Links** — `aw_deep_link` is already tracked; append your click reference.

```
https://www.awin1.com/cread.php?awinmid=<MID>&awinaffid=<AFFID>&clickref={subid}&ued={url}
```

Reporting joins on `clickref`.

---

## Impact

**Feed** — the Catalog API (`/Catalogs/{CatalogId}/Items`) returns JSON.

```json
{
  "key": "impact_harbour",
  "display_name": "Harbour",
  "url": "https://api.impact.com/Mediapartners/<ACCOUNT_SID>/Catalogs/<CATALOG_ID>/Items?PageSize=500",
  "format": "json",
  "items_path": "Items",
  "headers": { "Authorization": "Basic <base64 sid:token>", "Accept": "application/json" },
  "field_map": {
    "product_id": "CatalogItemId",
    "title": "Name",
    "brand": "Manufacturer",
    "product_url": "Url",
    "image_url": "ImageUrl",
    "category": "Category",
    "price": "CurrentPrice",
    "original_price": "OriginalPrice",
    "currency": "Currency",
    "in_stock": "InStock"
  }
}
```

**Links** — tracking link plus `subId1`:

```
https://<TRACKING_DOMAIN>/c/<ACCOUNT>/<CAMPAIGN>/<AD>?subId1={subid}&u={url}
```

---

## CJ (Commission Junction)

**Feed** — the REST Product Feed (or the GraphQL product search) returns JSON.

```json
{
  "key": "cj_meridian",
  "display_name": "Meridian",
  "url": "https://ads.api.cj.com/query",
  "format": "json",
  "items_path": "data.products.resultList",
  "headers": { "Authorization": "Bearer <PERSONAL_ACCESS_TOKEN>" },
  "field_map": {
    "product_id": "id",
    "title": "title",
    "brand": "brand",
    "product_url": "link",
    "image_url": "imageLink",
    "price": "price.amount",
    "currency": "price.currency",
    "in_stock": "availability"
  }
}
```

Note the dotted paths into nested objects — no code required.

**Links** — CJ links carry `sid`:

```
https://www.anrdoezrs.net/links/<PID>/type/dlg/sid/{subid}/{url}
```

CJ expects the destination **not** URL-encoded in the path form; if you use that
shape, drop `{url}`'s encoding by templating the raw link instead.

---

## Rakuten Advertising

**Feed** — delivered by FTP/SFTP as gzipped CSV/XML per advertiser. The generic
connector reads HTTP(S) and local files, so mirror the drop into object storage
(or a local path) on receipt and point `url` at that.

```json
{
  "key": "rakuten_ridgeline",
  "display_name": "Ridgeline",
  "url": "https://storage.example.com/feeds/rakuten/ridgeline-latest.xml",
  "format": "xml",
  "items_path": "product",
  "field_map": {
    "product_id": "sku",
    "title": "productname",
    "brand": "manufacturer",
    "product_url": "linkurl",
    "image_url": "imageurl",
    "price": "price",
    "original_price": "retailprice",
    "currency": "currency"
  }
}
```

**Links**

```
https://click.linksynergy.com/deeplink?id=<ID>&mid=<MID>&u1={subid}&murl={url}
```

Mirroring the SFTP drop is the only piece of infrastructure this network needs
beyond configuration; it is a scheduled copy of a file you are entitled to, not
a crawl of a retailer.

---

## Direct retailer integrations

Some retailers will give you a feed or an API directly. These are the best
sources: no intermediary, fresher data, negotiated rate limits.

- **Feed** — configure it like any other feed connector.
- **API** — write a small `RetailerConnector` subclass
  ([adding-a-connector.md](adding-a-connector.md#2-api-connector-a-subclass)).
- **Shopify storefronts** — many menswear brands expose `/products.json` or the
  Storefront GraphQL API. Use it **only** with the retailer's agreement; it is
  public but it is still their infrastructure.

Record each relationship in `retailer_configs`: `connector_type`, `enabled`,
`permission_granted`, `affiliate_network`, `affiliate_template`. That table is
the audit trail for how the data is allowed to be used.

---

## Click attribution

1. Each product's `affiliate_url` is built at normalisation time from the
   template, carrying `{subid}`.
2. The shopper's browser navigates straight there — fast, and the network sees a
   normal referral.
3. In parallel the frontend fires `POST /api/clicks`, which writes an
   `affiliate_click_events` row with the retailer, product, sub-id, price,
   position and the originating `search_id`.
4. Reconcile the network's reporting against that table on the sub-id.

Sub-ids are deterministic per `(retailer, product_id)` so a cached result set
keeps working; per-search context lives on the click event, not in the URL.

Client fingerprints stored with clicks are one-way hashes of IP and
user-agent — enough to spot abuse, not enough to identify a person.

---

## Operational notes

- **Feed size.** `max_items` bounds what a single search reads. For large feeds,
  prefer a searchable endpoint (`query_param`) or pre-filter upstream.
- **Freshness.** Feeds are typically rebuilt daily. Our 30-minute freshness
  window is about our own request volume, not the retailer's update cadence, so
  it stays correct either way.
- **Currency.** Set `currency` per feed. Cross-currency comparison uses static
  approximate rates — see [limitations.md](limitations.md).
- **Compliance.** Outbound links carry `rel="nofollow sponsored"`. If you
  operate in a market that requires affiliate disclosure, add it to the results
  page before launch.
