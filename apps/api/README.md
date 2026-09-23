# Marle API

FastAPI service for prompt parsing, indexed menswear search, ranking, SSE,
accounts, favourites and click tracking. A scheduled worker collects enabled
retailers into a persistent SQL variant catalogue.

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m app.ingest --once
.venv/bin/uvicorn app.main:app --reload --port 8000
```

No credentials are needed for the five initial product sources or the
fallback query parser. Blank `DATABASE_URL` uses `marle.sqlite3` in this
directory, automatically creating tables. PostgreSQL deployments must run
`.venv/bin/alembic upgrade head` before starting the API or worker.

`INGESTION_ENABLED=true` starts the worker within the API process for local
use. For a dedicated worker, disable it on the API and run
`.venv/bin/python -m app.ingest`. Source schedules and leases live in SQL.

| Directory | Purpose |
| --- | --- |
| `app/sources/` | Registry validation and public Shopify collection adapter |
| `app/services/catalogue.py` | Variant storage, worker leases, publication and indexed queries |
| `app/services/ingestion.py` | Scheduled imports and failure handling |
| `app/services/search_engine.py` | Prompt parsing, ranking and search events |
| `app/db/` | SQLAlchemy tables and application repositories |
| `app/data/retailers.json` | Reviewed retailers and ingestion configuration |
| `tests/` | Offline source, persistence, lifecycle and HTTP tests |

Run `.venv/bin/pytest`, `.venv/bin/ruff check .` and
`.venv/bin/ruff format --check .`. See [the root README](../../README.md).
