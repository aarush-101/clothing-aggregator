# Clothing Aggregator API

FastAPI service for on-demand menswear search: natural-language query parsing,
concurrent retailer connectors, normalisation, de-duplication, deterministic
ranking, Redis caching and Server-Sent Event streaming.

Full documentation lives in the repository root:
[`README.md`](../../README.md) and [`docs/`](../../docs).

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/uvicorn app.main:app --reload --port 8000
```

Interactive docs at <http://localhost:8000/docs>.

Redis, PostgreSQL and an Anthropic API key are all optional — the service falls
back to an in-process cache, skips persistence, and parses queries
deterministically.

## Test and lint

```bash
.venv/bin/pytest                 # 256 tests, no external services required
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

## Migrations

```bash
DATABASE_URL="postgresql+asyncpg://…" .venv/bin/alembic upgrade head
```

## Layout

```
app/
  config.py            settings, validated at import
  logging_config.py    structured logging
  models/              SearchIntent, Product, SSE events, API bodies
  services/nlp/        sanitise → parser → anthropic | deterministic
  services/            search_engine, ranking, dedupe, cache, event_bus
  connectors/          base interface, registry, mock / feed / api / html
  db/                  SQLAlchemy models, session, repositories
  api/                 routers
  data/                seeded mock catalogue and sample feeds
alembic/               migrations
tests/                 pytest suite
```

Supports Python 3.9+; the Docker image uses 3.12.
