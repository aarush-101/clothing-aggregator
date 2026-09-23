# Product sources and access research

## Current result — 2026-09-23

Normal Python `httpx` requests successfully read public men's collection JSON
from Assembly Label, Academy Brand, Industrie, Universal Store and Incu.
Their robots rules allowed those collection URLs, and their `/meta.json`
responses identified AUD currency. These sources are now enabled in Marle's
persistent ingestion path. See [the live validation report](live-validation.md).

The adapter uses its own Marle user agent and ordinary HTTP requests. It checks
robots.txt, rate-limits collection requests, honours Retry-After, rejects
cross-host redirects and pauses on access challenges. Searches run against
stored products, so an outage need not stop all search results.

## Historical finding

Earlier research on 2026-09-22 reported Python requests receiving Cloudflare
challenges across 93 Shopify candidates. That was an observation of that
client/environment/request combination. It was not proof that all product
access was impossible, and the new successful requests supersede that broad
conclusion. The complete 93-domain benchmark has not been repeated.

The unused candidate list and old search-time Shopify connector have been
removed. The maintained [retailer registry](retailer-registry.md) now records
website evidence separately from product-access evidence and runtime ingestion.

## Additional routes

Retailer product feeds, supported APIs and shopping/web-search discovery are
possible future source adapters (affiliate links are deliberately not used). They are not implemented by adding a registry
entry alone. Validate access, coverage, variants, pagination, storage and
update/removal semantics before enabling a new source.

Marle has no dependency on eBay. The current 50 sources do not require an
account or API key. Access requirements for future sources depend on their
chosen method. No method establishes universal coverage or permanent access.
