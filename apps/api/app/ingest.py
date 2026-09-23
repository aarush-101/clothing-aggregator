"""Run once with `python -m app.ingest --once`, or run a dedicated worker."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.db.session import build_database
from app.logging_config import configure_logging
from app.services.catalogue import Catalogue
from app.services.ingestion import IngestionWorker
from app.sources.registry import enabled_retailers


async def run(args) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    database = build_database(settings)
    try:
        if database.url.startswith("sqlite"):
            await database.create_all()
        catalogue = Catalogue(database, enabled_retailers(), settings)
        await catalogue.initialise()
        if args.retailer and args.retailer not in catalogue.retailers:
            raise ValueError(f"Unknown or disabled source: {args.retailer}")
        worker = IngestionWorker(catalogue)
        if args.once:
            await worker.tick(force=args.force, retailer=args.retailer)
            states = await catalogue.source_states()
            print(
                json.dumps(
                    {
                        key: {
                            "state": row.state,
                            "variant_offers": row.offer_count,
                            "last_success": row.last_success,
                            "error": row.error,
                        }
                        for key, row in states.items()
                    },
                    indent=2,
                )
            )
            checked = [states[args.retailer]] if args.retailer else states.values()
            return 1 if any(s.state in {"failed", "blocked", "pending"} for s in checked) else 0
        await worker.run()
        return 0
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Refresh due sources and exit")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh even when not due (never overrides an active lease)",
    )
    parser.add_argument("--retailer", help="Refresh one enabled retailer with --once")
    args = parser.parse_args()
    if (args.force or args.retailer) and not args.once:
        parser.error("--force and --retailer require --once")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
