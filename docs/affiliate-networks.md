# Optional affiliate links

Current ingestion reads public retailer collections and uses direct product
links by default. No affiliate partnership or account is required for the five
initial sources, and no affiliate feed adapter is currently implemented.

The existing click-attribution code remains available. If you have an approved
retailer/network relationship, set an HTTPS deep-link template by retailer key:

```bash
AFFILIATE_TEMPLATES='{"assemblylabel":"https://your-approved-network.example/link?url={url}&ref={subid}"}'
```

This is a format example, not a working network link. `{url}` becomes the
URL-encoded retailer product/variant URL; `{subid}` becomes a stable click
reference. Clicks are recorded through `/api/clicks` when SQL is available.

Validate the actual network's requirements and redirects before enabling a
template. Network product feeds require a new ingestion adapter with pagination,
variant and deletion semantics; the old unused generic connector was removed.
See [adding a source](adding-a-source.md).
