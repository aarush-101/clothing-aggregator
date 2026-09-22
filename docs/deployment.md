# Deployment

The frontend is a standard Next.js app; the backend is a standard ASGI service.
Nothing is tied to a particular host.

| Piece | Recommended | Alternatives |
| --- | --- | --- |
| Frontend | Vercel | Netlify, Cloudflare Pages, the bundled Dockerfile |
| Backend | Railway | Render, Fly.io, the bundled Dockerfile anywhere |
| PostgreSQL | Neon | Supabase, RDS, any managed Postgres |
| Redis | Upstash | Any managed Redis with TLS |

---

## Before you deploy

`APP_ENV=production` makes configuration validation strict. The service refuses
to start if:

- `REDIS_URL` is missing — the in-process cache is not shared between instances
- `DATABASE_URL` is missing
- `CORS_ALLOW_ORIGINS` contains a wildcard

That is deliberate: these are the three mistakes that quietly break a
multi-instance deployment or open it up.

---

## 1. PostgreSQL (Neon or Supabase)

Create the database and copy the **pooled** connection string.

```bash
# Neon
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx-pooler.ap-southeast-2.aws.neon.tech/neondb

# Supabase (Connection Pooling / Transaction mode, port 6543)
DATABASE_URL=postgresql+asyncpg://postgres.xxx:pass@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres
```

`postgres://` and `postgresql://` prefixes are upgraded to `postgresql+asyncpg://`
automatically, so pasting the provider's string as-is works.

Run migrations once, from anywhere that can reach the database:

```bash
cd apps/api
DATABASE_URL="postgresql+asyncpg://…" .venv/bin/alembic upgrade head
```

Make this a release step in your host (see below) so it runs on every deploy.

> **Supabase note.** Only the database is used. Supabase Auth is not wired in —
> see [limitations.md](limitations.md) for the upgrade path from the anonymous
> device tokens shipped here.

---

## 2. Redis (Upstash)

Create a database in the same region as the API and use the TLS URL:

```bash
REDIS_URL=rediss://default:<password>@apn1-xxx.upstash.io:6379
```

Redis holds cached searches, the coalescing locks and rate-limit counters. All
keys carry TTLs (24 h maximum), so it stays small and needs no eviction policy
beyond the default.

---

## 3. Backend

### Railway

1. New project → Deploy from repo → root directory `apps/api`.
2. Railway detects the `Dockerfile`.
3. Variables: `APP_ENV=production`, `DATABASE_URL`, `REDIS_URL`,
   `CORS_ALLOW_ORIGINS=https://your-app.vercel.app`, `LOG_FORMAT=json`,
   `ANTHROPIC_API_KEY` (optional), plus any `AFFILIATE_FEEDS` /
   `AFFILIATE_TEMPLATES`.
4. Health check path `/health/ready`.
5. Pre-deploy command: `alembic upgrade head`.

### Render

`render.yaml`:

```yaml
services:
  - type: web
    name: clothing-aggregator-api
    env: docker
    dockerfilePath: ./apps/api/Dockerfile
    dockerContext: ./apps/api
    healthCheckPath: /health/ready
    preDeployCommand: alembic upgrade head
    envVars:
      - key: APP_ENV
        value: production
      - key: LOG_FORMAT
        value: json
      - key: DATABASE_URL
        sync: false
      - key: REDIS_URL
        sync: false
      - key: CORS_ALLOW_ORIGINS
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
```

### Fly.io

```bash
cd apps/api
fly launch --no-deploy --dockerfile Dockerfile
fly secrets set APP_ENV=production LOG_FORMAT=json \
  DATABASE_URL="postgresql+asyncpg://…" REDIS_URL="rediss://…" \
  CORS_ALLOW_ORIGINS="https://your-app.vercel.app"
fly deploy
```

In `fly.toml`:

```toml
[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false      # SSE connections must not be suspended

  [[http_service.checks]]
    path = "/health/ready"
    interval = "30s"
    timeout = "5s"

[deploy]
  release_command = "alembic upgrade head"
```

`auto_stop_machines = false` matters: a suspended machine drops in-flight
Server-Sent Events.

### Any Docker host

```bash
docker build -t aggregator-api apps/api
docker run -p 8000:8000 \
  -e APP_ENV=production -e LOG_FORMAT=json \
  -e DATABASE_URL=… -e REDIS_URL=… -e CORS_ALLOW_ORIGINS=… \
  aggregator-api
```

The image runs as a non-root user and has a built-in health check.

---

## 4. Frontend (Vercel)

1. Import the repo; set **Root Directory** to `apps/web`.
2. Framework preset: Next.js. Build and install commands are detected.
3. Environment variable: `NEXT_PUBLIC_API_BASE_URL=https://your-api.up.railway.app`.
4. Deploy, then add that Vercel URL to the API's `CORS_ALLOW_ORIGINS`.

`NEXT_PUBLIC_*` values are inlined **at build time**, so changing the API URL
needs a redeploy, not just a restart. Preview deployments get their own origins;
either add them to `CORS_ALLOW_ORIGINS` or point previews at a staging API.

### Serving both from one origin

If you would rather avoid CORS entirely, proxy the API through Next:

```ts
// next.config.ts
async rewrites() {
  return [{ source: '/api/:path*', destination: `${process.env.API_ORIGIN}/api/:path*` }];
}
```

Then set `NEXT_PUBLIC_API_BASE_URL=""`. Verify your platform streams responses
without buffering before relying on this for SSE — Vercel's Node runtime does;
some edge proxies do not.

---

## Server-Sent Events in production

SSE is a long-lived HTTP response. Three things to check:

1. **No proxy buffering.** The API sends `X-Accel-Buffering: no` and
   `Cache-Control: no-cache, no-transform`. Nginx-style proxies honour the
   first; CDNs usually honour the second.
2. **Idle timeouts.** Comment frames go out every 15 seconds, which keeps most
   proxies from closing the connection. A search finishes well inside the
   default 25-second deadline anyway.
3. **Instance affinity.** The event broker is per-process. With more than one
   API instance, a reconnect can land on an instance that never ran the search.
   The endpoint falls back to replaying the cached snapshot, so the client still
   ends in the right state — but for a fully correct multi-instance stream, use
   sticky sessions or implement the broker over Redis pub/sub. See
   [limitations.md](limitations.md).

---

## Scaling notes

- **Stateless API.** Everything shared lives in Redis or PostgreSQL. Scale
  horizontally, subject to the SSE affinity note above.
- **Retailer requests are the cost centre.** `SEARCH_MAX_CONCURRENT_RETAILERS`
  bounds fan-out per search; the cache is what actually protects your partners'
  infrastructure. Do not shorten `CACHE_FRESH_SECONDS` without a reason.
- **Anthropic spend** scales with *unique* queries, not searches, because parsed
  intents are cached for 24 hours and the system prompt is cached per request.
- **Connection pools.** Use the pooled PostgreSQL string; each instance opens
  its own pool.

---

## Observability

Set `LOG_FORMAT=json`. Every line carries an `event` name plus context, and
requests and searches carry `request_id` / `search_id`.

Useful events: `search.completed`, `retailer.failed`, `retailer.completed`,
`intent.llm_failed`, `intent.llm_bypassed`, `cache.redis_unavailable`,
`http.rate_limited`, `click.recorded`.

Worth alerting on:

| Signal | Why |
| --- | --- |
| `retailer.failed` rate per connector | a partner is down or has changed their feed |
| `search.completed` with `status=partial` | degraded results |
| `intent.llm_failed` rate | Anthropic degradation; the fallback is carrying traffic |
| `/health/ready` non-200 | cache unavailable or no connectors registered |
| p95 of `search.completed.duration_ms` | the shopper-visible number |

`connector_health_records` accumulates one row per connector per search, which
is the raw material for a reliability dashboard. Add a retention job before it
grows large.

---

## Deployment checklist

- [ ] `APP_ENV=production`, `LOG_FORMAT=json`
- [ ] `DATABASE_URL` (pooled) and `REDIS_URL` (TLS) set
- [ ] `CORS_ALLOW_ORIGINS` lists exactly your frontend origins, no wildcard
- [ ] `alembic upgrade head` runs as a release step
- [ ] Health check points at `/health/ready`
- [ ] `NEXT_PUBLIC_API_BASE_URL` set at frontend build time
- [ ] `MOCK_INCLUDE_FLAKY_RETAILER=false`
- [ ] Mock connectors removed from `ENABLED_CONNECTORS` once real ones exist
- [ ] Rate limits reviewed for your traffic
- [ ] `ANTHROPIC_API_KEY` set (or a deliberate decision to run deterministic)
