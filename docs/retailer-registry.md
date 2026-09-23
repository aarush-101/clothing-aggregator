# Retailer website registry

The maintained list lives in
[`apps/api/app/data/retailers.json`](../apps/api/app/data/retailers.json).
It gives source research and running ingestion a shared list of retailers,
official menswear URLs and dated evidence.

The registry holds **50 Australian Shopify stores**, all reviewed and enabled
on **2026-09-23**: 19 multi-brand retailers and 31 brand or label stores. Stores
without a working import (non-Shopify sites, robots-blocked pagination) were
removed rather than kept as placeholders. Each entry links to the official page
used for its review.

## What verified means

`website_verification.status = verified` means a review found an official
retailer website with a menswear section. The initial reviews used web browsing,
which may return cached page content. They were not live access benchmarks
from Marle's backend.

Stores were chosen for brand overlap, so the same garment appears at more than
one store and can be merged.

`data_access.status` is tracked separately; every entry currently has a
validated public collection import, with evidence in
[the live report](live-validation.md). Culture Kings and Surf Dive 'n' Ski were
checked but not added because their robots rules disallow paginated collection
requests.

Website verification alone does not establish product access or current stock.
`storefront_market = AU` describes the storefront, not shipping eligibility.
Runtime health and last successful imports are stored in SQL and reported by
`GET /api/retailers`; a historical successful check is not a health monitor.

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

`app/sources/registry.py` validates and loads this file at startup. An optional
`ingestion` object selects the method, men's collection, currency, refresh
interval and page budget, plus an optional `default_brand` for own-label
stores whose Shopify vendor is a department name. Only
`ingestion.enabled = true` entries run.
Adding a website without this configuration does not start collection.

There is one registry: the old 93-store Shopify candidate configuration has
been removed. `/api/retailers` lists all reviewed entries alongside their
configured/collected status. See [adding a source](adding-a-source.md) for the
configuration and validation workflow.
