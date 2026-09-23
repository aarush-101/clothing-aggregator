"""Prepare isolated offline inventory, then serve the real API for Playwright."""

import argparse
import asyncio
import os

import uvicorn
from sqlalchemy import delete

from app.config import get_settings
from app.db.session import build_database
from app.db.tables import CatalogueOffer, CatalogueSource, IngestionRun
from app.services.catalogue import Catalogue
from app.sources.registry import enabled_retailers
from tests.catalogue_fixtures import seed_catalogue


async def prepare():
    if os.environ.get("APP_ENV") != "test" or not os.environ.get("DATABASE_URL", "").endswith(
        "e2e.sqlite3"
    ):
        raise RuntimeError(
            "E2E seeding requires APP_ENV=test and the dedicated e2e.sqlite3 database"
        )
    settings = get_settings()
    database = build_database(settings)
    try:
        await database.create_all()
        async with database.session() as session:
            for table in (CatalogueOffer, CatalogueSource, IngestionRun):
                await session.execute(delete(table))
        await seed_catalogue(Catalogue(database, enabled_retailers(), settings))
    finally:
        await database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    asyncio.run(prepare())
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)
