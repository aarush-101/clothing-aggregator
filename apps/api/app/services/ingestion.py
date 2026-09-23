"""Scheduled ingestion independent of shopper requests."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from app.logging_config import get_logger
from app.services.catalogue import Catalogue
from app.sources.shopify import ShopifySource, SourceError

log = get_logger(__name__)


class IngestionWorker:
    def __init__(self, catalogue: Catalogue):
        self.catalogue = catalogue
        self._task: Optional[asyncio.Task] = None
        # Set when the platform rate-limits us; no source is tried until then.
        self.paused_until = 0.0

    async def refresh(self, key: str, *, force: bool = False) -> bool:
        token = await self.catalogue.claim(key, force=force)
        if token is None:
            return False
        try:
            source = ShopifySource(
                self.catalogue.retailers[key],
                request_delay=self.catalogue.settings.ingestion_request_interval_seconds,
            )
            products = await source.fetch(lambda: self.catalogue.heartbeat(key, token))
            published = await self.catalogue.publish(key, token, products)
            log.info(
                "ingestion.completed", retailer=key, variants=len(products), published=published
            )
            return published
        except asyncio.CancelledError:
            await self.catalogue.fail(key, token, "Worker stopped; refresh will resume", 60)
            raise
        except Exception as exc:
            error = (
                str(exc)
                if isinstance(exc, SourceError)
                else f"{type(exc).__name__}: source refresh failed"
            )
            await self.catalogue.fail(
                key,
                token,
                error,
                exc.retry_after if isinstance(exc, SourceError) else 3600,
                exc.blocked if isinstance(exc, SourceError) else False,
            )
            log.warning("ingestion.failed", retailer=key, error=error)
            if isinstance(exc, SourceError) and exc.rate_limited:
                self.paused_until = time.time() + exc.retry_after
                log.warning("ingestion.paused_all_sources", seconds=exc.retry_after)
            return False

    async def tick(self, *, force: bool = False, retailer: Optional[str] = None) -> None:
        keys = [retailer] if retailer else list(self.catalogue.retailers)
        for key in keys:
            if time.time() < self.paused_until:
                log.info("ingestion.round_stopped", reason="rate limited", skipped=key)
                return
            await self.refresh(key, force=force)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("ingestion.worker_error")
            await asyncio.sleep(self.catalogue.settings.ingestion_poll_seconds)

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
