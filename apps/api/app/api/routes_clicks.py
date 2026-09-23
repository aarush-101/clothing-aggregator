"""Outbound click analytics.

The browser navigates straight to the retailer's product page; this endpoint
only records the click. It never redirects to a URL it has not validated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.db.repository import AccountRepository, fingerprint_client
from app.deps import AppContext, get_accounts, get_context, get_optional_user
from app.logging_config import get_logger
from app.models.api import ClickRequest, ClickResponse
from app.services.ratelimit import client_identifier

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["clicks"])


@router.post("/clicks", response_model=ClickResponse, summary="Record an outbound click")
async def record_click(
    payload: ClickRequest,
    request: Request,
    context: AppContext = Depends(get_context),
    accounts: AccountRepository = Depends(get_accounts),
    user=Depends(get_optional_user),
) -> ClickResponse:
    log.info(
        "click.recorded",
        retailer=payload.retailer,
        product_id=payload.product_id,
        search_id=payload.search_id,
    )

    click_id = None
    if accounts.available:
        try:
            click_id = await accounts.record_click(
                {
                    "search_id": payload.search_id,
                    "user_id": getattr(user, "id", None),
                    "retailer": payload.retailer,
                    "product_id": payload.product_id,
                    "destination_url": payload.destination_url,
                    "price": payload.price,
                    "currency": (payload.currency or "AUD").upper(),
                    "position": payload.position,
                    "client_fingerprint": fingerprint_client(
                        client_identifier(request), request.headers.get("user-agent")
                    ),
                }
            )
        except Exception as exc:
            # Analytics must never block a shopper from reaching the retailer.
            log.warning("click.persist_failed", error=str(exc))

    return ClickResponse(
        recorded=click_id is not None,
        click_id=click_id,
        destination_url=payload.destination_url,
    )
