# Retailer website registry

The maintained list lives in
[`apps/api/app/data/retailers.json`](../apps/api/app/data/retailers.json).
It gives source research and future ingestion a shared list of retailers,
official menswear URLs and dated evidence.

The initial ten entries were reviewed on **2026-09-23**: THE ICONIC, UNIQLO
Australia, Country Road, Assembly Label, AS Colour Australia, Universal Store,
Industrie, Incu, Academy Brand and Cotton On Australia. Each entry links to the
official page used for its review.

## What verified means

`website_verification.status = verified` means a review found an official
retailer website with a menswear section. The initial reviews used web browsing,
which may return cached page content. They were not live access benchmarks
from Marle's backend.

`data_access.status` is tracked separately. All initial entries are
`not_validated`: none has a working Marle product integration established by
this review. Website verification does not verify individual products, current
prices, stock, sizes, delivery destinations or suitability for automated
collection. `storefront_market = AU` identifies the reviewed storefront's
market; it does not assert that every item ships to Australia.

## Entry fields

| Field | Meaning |
| --- | --- |
| `key` | Stable, unique retailer/storefront identifier. Reuse an existing identifier when it represents the same storefront. |
| `name` | Retailer's display name. |
| `website_url` | Official storefront home URL, including its regional path where applicable. |
| `menswear_url` | Official men's clothing collection or department URL. |
| `storefront_market` | Two-letter storefront market code, or `null` if unknown. This is not a shipping allowlist. |
| `website_verification.status` | `unverified`, `verified`, `needs_review` or `inactive`. |
| `website_verification.reviewed_on` | Date of the latest website review (`YYYY-MM-DD`), or `null` before review. |
| `website_verification.method` | How the website was reviewed; initially `official_page_review_via_web`. Use `null` before review. |
| `website_verification.evidence_url` | Official page supporting the website review, or `null` before review. |
| `website_verification.notes` | What the reviewer observed and any limits on the evidence. |
| `data_access.status` | `not_validated`, `validated`, `blocked`, `unavailable` or `needs_review`. |
| `data_access.method` | Validated or attempted method: `feed`, `api`, `html`, `shopify_json` or `search_provider`; otherwise `null`. |
| `data_access.last_checked_on` | Date of the last product-access check, or `null` if none has been recorded here. |
| `data_access.evidence_url` | URL or repository-relative path to a dated access report, or `null`. Repository paths are relative to the repository root. |

`schema_version` describes the JSON format, not the freshness of its entries.
Dates belong to individual reviews. Never put credentials or signed feed URLs
in this file.

## Maintaining the list

1. Check for an existing key and storefront before adding an entry. Different
   regional storefronts may share a domain, so preserve their regional paths.
2. Visit the official website and follow its men's department link. Record the
   final URL, review date, method and a short observation. Keep candidates
   `unverified` until that review is complete.
3. Validate product access separately in the intended deployment environment.
   Record the endpoint or provider, client, date, responses, representative
   products, usable fields, pagination/completeness and any observed limits in
   a report. Link that report before setting data access to `validated`.
   A successful homepage request is insufficient.
4. Recheck a website before integrating it and aim to review listed websites
   quarterly. Mark uncertain or outdated entries `needs_review`; record
   confirmed closed storefronts as `inactive` so their identifiers and history
   remain traceable. Product access needs its own checks whenever an adapter
   fails or changes. No automated review scheduler exists yet.
5. Validate JSON syntax, unique keys, URLs and evidence when editing the file.
   Commit the registry and related access reports together. Git retains the
   history of previous observations.

## Relationship to the running app

This is a checked-in source registry, not an enabled connector list. Adding an
entry does not start crawling it or add products to search results. The
prototype still returns demo data by default, and `GET /api/retailers` still
describes configured runtime connectors.

The planned [product index](product-index.md) can use this registry to seed
retailer identities, while source configuration and access checks determine
which ingestion adapters can run. The existing
[`shopify_stores.json`](../apps/api/app/data/shopify_stores.json) remains a
separate historical research/configuration file for the optional Shopify
connector. Its 93 candidates have not been promoted into this verified list.
