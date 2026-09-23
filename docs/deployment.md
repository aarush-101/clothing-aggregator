# Deployment

## Local setup

Use `make install`, `make ingest`, `make api` and `make web` as described in the
[root README](../README.md). Blank database/Redis settings work locally: SQLite
persists at `apps/api/marle.sqlite3`, and the response/intent cache is in memory.
Back up the SQLite file if it contains inventory or saved items you need.

## PostgreSQL and Redis

Set `DATABASE_URL` to a PostgreSQL connection string and `REDIS_URL` to Redis.
Run `cd apps/api && .venv/bin/alembic upgrade head` before starting services.
Migration `0002` adds the catalogue, schedules and ingestion run tables without
removing existing account data. Use the same database in the API and worker.

`APP_ENV=production` requires database and Redis URLs and explicit CORS origins.
Set `CORS_ALLOW_ORIGINS` to the frontend origin. Set
`NEXT_PUBLIC_API_BASE_URL` at frontend **build time** to the API's public URL.

## Processes

API:

```bash
INGESTION_ENABLED=false uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker, from `apps/api` with the same environment:

```bash
python -m app.ingest
```

One-off population or explicit refresh:

```bash
python -m app.ingest --once
python -m app.ingest --once --retailer assemblylabel --force
```

The worker's schedule is stored in SQL. Leases prevent concurrent publication
for a source and recover after a worker exits. Scheduled retries honour stored
cooldowns. `--force` is an operator override of the due time, including cooldowns;
it still respects robots, request spacing and active leases.

For a small single-instance deployment, leave `INGESTION_ENABLED=true` and the
API hosts the background task itself. Do not rely on serverless request
lifetimes to keep an ingestion worker running. Keep the database on durable
storage; ephemeral filesystem deployments lose local SQLite inventory.

## Frontend and health

Run `npm run build` in `apps/web`, then serve the Next.js output. The existing
standalone Docker configuration and Vercel frontend deployment remain usable.
The API and worker require long-lived Python processes.

- `/health`: process liveness and configured source count.
- `/health/ready`: database/cache readiness and unexpired variant-offer count.
- `/api/retailers?include_health=true`: configured versus unconfigured retailers,
  last successful import, stored offer count and latest error.

A ready but empty catalogue can accept searches and reports collection pending.
Health is not a guarantee of full retailer coverage. Alert on missing recent
successful imports and empty inventory. Source access must be checked from the
actual deployment environment; local success does not prove production access.

Use one API instance or session affinity for SSE. Cross-instance live event
streaming is not implemented. Hosted PostgreSQL/load testing remains future
validation; see [limitations](limitations.md).
