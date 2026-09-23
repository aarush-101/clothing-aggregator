# Clothing Aggregator API

FastAPI prototype for menswear search: natural-language query parsing,
concurrent retailer connectors, normalisation, de-duplication, deterministic
ranking, Redis caching and Server-Sent Event streaming.

The default sources contain fictional products. A persistent product index and
scheduled ingestion are the accepted next architecture, but neither is
implemented yet. See the [product-index plan](../../docs/product-index.md).

Full documentation lives in the repository root:
[`README.md`](../../README.md) and [`docs/`](../../docs).

## Run it

Run these **from this directory** (`apps/api`) — `pyproject.toml` lives here, not
at the repository root.

```bash
cd apps/api

python3 -m venv .venv

# Required: the pip bundled with some Python builds (macOS system Python ships
# 21.2.4) predates PEP 660, and `pip install -e .` fails on a pyproject-only
# project with "File setup.py or setup.cfg not found".
.venv/bin/pip install --upgrade pip

.venv/bin/pip install -e ".[dev]"

.venv/bin/uvicorn app.main:app --reload --port 8000
```

Or, from the repository root, `make install-api` does all of the above.

Interactive docs at <http://localhost:8000/docs>.

In the current development/demo mode, Redis, PostgreSQL and an Anthropic API key
are all optional — the service falls back to an in-process cache, skips
persistence, and parses queries deterministically.

The planned live indexed mode will require PostgreSQL and an ingestion worker.

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
