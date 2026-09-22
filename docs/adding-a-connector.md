# Adding a retailer connector

Every product source implements one interface and returns one `Product` shape.
Nothing downstream — ranking, de-duplication, caching, the UI — needs to know
where a garment came from.

## Choose the right kind

| Situation | Use | Code needed |
| --- | --- | --- |
| The retailer (or its affiliate network) publishes a JSON or XML product feed | **Generic feed connector** | none — configuration only |
| The retailer has a real search API | **API connector** | a subclass, ~80 lines |
| You need realistic data for development or tests | **Mock connector** | add to the seeded catalogue |
| The retailer has **given you written permission** to read their pages | **HTML connector** | configuration + a permission record |
| None of the above | Stop. See [Sourcing policy](#sourcing-policy). |

Prefer, in order: official retailer APIs → affiliate feeds → authorised product
feeds. Everything else needs a conversation with the retailer first.

---

## 1. Feed connector (no code)

Most affiliate networks publish a feed. Point the generic connector at it and
map the field names.

```bash
AFFILIATE_FEEDS='[
  {
    "key": "harbour_lane",
    "display_name": "Harbour Lane",
    "url": "https://feeds.example.com/harbour-lane/products.xml",
    "format": "xml",
    "currency": "AUD",
    "ships_to": ["AU", "NZ"],
    "items_path": "products/product",
    "field_map": {
      "product_id": "id",
      "title": "name",
      "brand": "brand",
      "product_url": "link",
      "image_url": "image",
      "price": "price",
      "original_price": "rrp",
      "currency": "price@currency",
      "colours": "colour",
      "materials": "material",
      "available_sizes": "sizes",
      "in_stock": "availability"
    },
    "defaults": { "shipping_destination": "AU" },
    "headers": { "Authorization": "Bearer ${FEED_TOKEN}" },
    "query_param": null,
    "timeout_seconds": 8,
    "max_items": 250
  }
]'
ENABLED_CONNECTORS=mock:*,harbour_lane
```

### Configuration reference

| Key | Required | Meaning |
| --- | --- | --- |
| `key` | ✓ | lowercase slug; the machine identifier |
| `display_name` | ✓ | shown to shoppers |
| `url` | ✓ | `https://…`, or a path relative to `apps/api/app/` for local files |
| `format` | | `json` (default) or `xml` |
| `enabled` | | default `true` |
| `currency` | | ISO 4217, default `AUD` |
| `ships_to` | | ISO 3166 alpha-2 list; empty means worldwide |
| `items_path` | | dotted path (JSON) or element path (XML) to the product records |
| `field_map` | | our field → their field; merged over the defaults |
| `defaults` | | static values merged into every product |
| `headers` | | sent with the request (API keys, etc.) |
| `query_param` | | if the feed is searchable, the parameter to put keywords in |
| `timeout_seconds` | | default 8 |
| `max_items` | | default 250 |

### Path syntax

**JSON** — dotted, with numeric list indices: `pricing.amount`, `images.0.src`.
**XML** — element paths, with `@` for attributes: `price`, `price@currency`,
`offers/offer/price`.

A feed the connector cannot parse fails that connector only; the search
continues with everything else. Rows that fail validation are discarded and
counted, not raised. `apps/api/app/data/sample_feed.{xml,json}` are worked
examples, including a deliberately malformed row.

### Verify it

```bash
cd apps/api
.venv/bin/python -c "
import asyncio
from app.config import get_settings
from app.connectors.registry import ConnectorRegistry
from app.services.nlp.fallback_parser import parse_query

registry = ConnectorRegistry(get_settings())
connector = registry.get('harbour_lane')
print(asyncio.run(connector.health_check()))
products = asyncio.run(connector.search(parse_query('black linen shirt')))
print(len(products), products[:2])
"
```

Then check `GET /api/retailers?include_health=true`.

---

## 2. API connector (a subclass)

Use `apps/api/app/connectors/example_public.py` as the template.

```python
class HarbourLaneConnector(RetailerConnector):
    key = "harbour_lane"
    display_name = "Harbour Lane"
    ships_to = ["AU", "NZ"]
    currency = "AUD"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._client: Optional[httpx.AsyncClient] = None

    def supports(self, intent: SearchIntent) -> bool:
        # The base implementation checks shipping, gender and exclusions.
        # Narrow further if the retailer only stocks some categories.
        if not super().supports(intent):
            return False
        return not intent.product_categories or bool(
            set(intent.product_categories) & {"shirt", "trousers", "knitwear"}
        )

    async def search(self, intent: SearchIntent) -> List[Product]:
        client = self._ensure_client()
        try:
            response = await client.get(
                "https://api.harbourlane.example/v1/search",
                params={"q": " ".join(intent.all_keywords()[:6]), "limit": 60},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"request failed: {exc}") from exc

        products = [self.normalise(record) for record in payload.get("results", [])]
        return [p for p in products if p is not None and passes_coarse_filter(p, intent)]

    def normalise(self, raw_product: Any) -> Optional[Product]:
        if not isinstance(raw_product, dict) or not raw_product.get("sku"):
            return None
        # build_product never raises: a bad record returns None.
        return self.build_product(
            product_id=str(raw_product["sku"]),
            title=raw_product.get("name"),
            brand=raw_product.get("brand"),
            product_url=raw_product.get("url"),
            image_url=raw_product.get("image"),
            category=raw_product.get("category"),
            colours=raw_product.get("colours"),
            materials=raw_product.get("fabrics"),
            available_sizes=raw_product.get("sizes"),
            price=raw_product.get("price"),
            original_price=raw_product.get("was_price"),
            in_stock=raw_product.get("available", True),
            shipping_destination="AU",
            shipping_cost=raw_product.get("shipping"),
            source_updated_at=raw_product.get("updated_at"),
        )

    async def health_check(self) -> ConnectorHealth:
        ...

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
```

Register it in `ConnectorRegistry._build`, behind a settings flag:

```python
if self._settings.enable_harbour_lane:
    self._connectors["harbour_lane"] = HarbourLaneConnector(self._settings)
```

### Rules

1. **`normalise` returns `None`, never raises.** Always go through
   `build_product`, which discards unusable records and logs them.
2. **Raise `ConnectorError` for upstream failures.** The engine turns it into a
   `retailer_failed` event and a partial result; anything else is logged as an
   unexpected error.
3. **Never `sleep`, retry or back off inside `search`.** The engine owns
   timeouts, retries and concurrency.
4. **Reuse one `httpx.AsyncClient`** and close it in `aclose`.
5. **Set `ships_to` and `currency` honestly.** They drive connector selection
   and cross-currency price comparison.
6. **Only return products you can link to.** `product_url` must be a plain
   `http(s)` URL to the retailer's own page.

### Test it

Add cases to `apps/api/tests/test_connectors.py`:

```python
def test_harbour_lane_normalises_a_record(settings):
    connector = HarbourLaneConnector(settings)
    product = connector.normalise({"sku": "HL-1", "name": "Linen Shirt",
                                   "url": "https://harbourlane.example/p/1",
                                   "price": 119})
    assert product is not None and product.retailer == "harbour_lane"

def test_harbour_lane_discards_records_without_a_sku(settings):
    assert HarbourLaneConnector(settings).normalise({"name": "No sku"}) is None
```

Use `respx` to stub HTTP rather than hitting the network in tests.

---

## 3. Affiliate links

Add a deep-link template. `{url}` is replaced with the URL-encoded destination
and `{subid}` with our deterministic click id.

```bash
AFFILIATE_TEMPLATES='{
  "harbour_lane": "https://www.awin1.com/cread.php?awinmid=1234&awinaffid=999&clickref={subid}&ued={url}"
}'
```

Without a template the shopper still goes to the retailer's own product page.
We never fabricate an affiliate link and never rewrite a URL into something the
retailer did not publish. Sub-ids are stable per `(retailer, product_id)` so
they stay valid across cached results; the search id is recorded on the click
event instead.

Network-specific formats: [affiliate-networks.md](affiliate-networks.md).

---

## 4. HTML connectors — policy

`html_connector.py` exists for one situation: **a retailer has given you written
permission** to read their public product pages before a feed is available.

It refuses to run unless *both* `ENABLE_HTML_CONNECTORS=true` **and** that
connector's `permission_granted=True`. It also:

- reads and obeys `robots.txt`, with no override
- treats an unreachable `robots.txt` as "do not crawl"
- sends an honest, identifiable User-Agent with a contact URL
- rate-limits itself to one request per second per retailer
- stops immediately on `401`, `403` or `429`
- reads **schema.org Product JSON-LD** — the structured data retailers publish
  for exactly this purpose — rather than scraping rendered markup

It does **not**, and must not be extended to, defeat or work around bot
protection, CAPTCHAs, rate limits, paywalls or login walls. If a retailer blocks
us, that is the answer.

Record the permission in the `retailer_configs` table (`permission_granted`,
`affiliate_network`, `config`) so it is auditable.

---

## Sourcing policy

In order of preference:

1. **Official retailer APIs** — documented, supported, rate-limited by
   agreement.
2. **Affiliate network feeds** — Awin, Impact, CJ, Rakuten. Access is granted
   per-advertiser and carries commercial terms.
3. **Authorised product feeds** — a retailer hosting a feed for you directly.
4. **Permission-gated JSON-LD reads** — only with written permission, under the
   constraints above.

Unrestricted scraping and anti-bot evasion are out of scope for this project.
They create legal and ethical exposure, they break constantly, and they are not
how a business built on retailer relationships should behave.

---

## Checklist

- [ ] `key` and `display_name` set; `ships_to` and `currency` accurate
- [ ] `normalise` returns `None` for unusable records and never raises
- [ ] Upstream failures raise `ConnectorError`
- [ ] No sleeping, retrying or backing off inside `search`
- [ ] One reusable HTTP client, closed in `aclose`
- [ ] `health_check` is cheap and does not fan out
- [ ] Unit tests for `normalise` (good record, bad record) and `supports`
- [ ] Affiliate template configured, or a deliberate decision not to
- [ ] Appears in `GET /api/retailers?include_health=true`
