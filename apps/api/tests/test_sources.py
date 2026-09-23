"""Source parsing, pagination and access controls use deterministic HTTP fixtures."""

import copy
import gzip

import httpx
import pytest

from app.models.product import utcnow
from app.sources.registry import load_retailers
from app.sources.shopify import ShopifySource, SourceError, normalise_variants
from tests.catalogue_fixtures import raw_product, source


def test_registry_has_reviewed_sources_and_separate_enabled_coverage():
    retailers = load_retailers()
    assert len(retailers) == 10
    assert len([r for r in retailers if r.ingestion and r.ingestion.enabled]) == 5


def test_variant_price_size_colour_stock_and_url_stay_together():
    products = normalise_variants(raw_product(), source(), utcnow())
    assert len(products) == 4
    medium = next(p for p in products if p.product_id == "102")
    assert medium.price == 100
    assert medium.available_sizes == ["m"]
    assert medium.colours == ["black"]
    assert medium.product_url.endswith("?variant=102")
    assert medium.shipping_destination is None
    assert medium.shipping_cost is None
    unavailable = next(p for p in products if p.product_id == "103")
    assert unavailable.in_stock is False and unavailable.available_sizes == []


def test_missing_stock_is_unknown_and_non_menswear_is_excluded():
    raw = raw_product()
    del raw["variants"][0]["available"]
    assert normalise_variants(raw, source(), utcnow())[0].in_stock is None
    raw["tags"] = ["kids"]
    assert normalise_variants(raw, source(), utcnow()) == []


def test_department_vendor_is_not_presented_as_a_brand():
    raw = raw_product()
    raw["vendor"] = "Mens"
    assert all(p.brand is None for p in normalise_variants(raw, source(), utcnow()))


async def test_pagination_requires_empty_page_and_decodes_compressed_responses():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                content=gzip.compress(b"User-agent: *\nAllow: /"),
                headers={"content-encoding": "gzip"},
            )
        page = request.url.params.get("page")
        return httpx.Response(200, json={"products": [raw_product()] if page == "1" else []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        products = await ShopifySource(source(), client=client, request_delay=0).fetch()
    assert len(products) == 4
    assert len(calls) == 3
    assert calls[-1].endswith("page=2")


async def test_robots_wildcards_and_longest_match_prevent_collection_requests():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200, text="User-agent: *\nAllow: /\nDisallow: /collections/*/products.json"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError, match=r"robots\.txt"):
            await ShopifySource(source(), client=client, request_delay=0).fetch()
    assert calls == ["/robots.txt"]


@pytest.mark.parametrize("mode", ["truncated", "repeated", "malformed", "blocked", "redirect"])
async def test_unreliable_snapshots_fail_without_retry_storms(mode):
    retailer = source().model_copy(deep=True)
    retailer.ingestion.max_pages = 2
    calls = []

    def handler(request):
        calls.append(request.url)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if mode == "blocked":
            return httpx.Response(429, headers={"Retry-After": "7200"})
        if mode == "malformed":
            return httpx.Response(200, json={"oops": []})
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        raw = copy.deepcopy(raw_product())
        if mode == "truncated":
            raw["id"] = request.url.params["page"]
        return httpx.Response(200, json={"products": [raw]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError) as error:
            await ShopifySource(retailer, client=client, request_delay=0).fetch()
    if mode == "blocked":
        assert error.value.blocked and error.value.retry_after == 7200
        assert len(calls) == 2
    assert all(url.host == "assemblylabel.com" for url in calls)
