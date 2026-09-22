"""Optional account features.

Search works without an account. These endpoints add saved searches and
favourites on top, using a lightweight device token rather than a password, so
the first implementation stays simple. The schema already carries ``email`` and
``password_hash`` for a later upgrade to full authentication.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.repository import AccountRepository
from app.deps import AppContext, get_accounts, get_context, require_user
from app.models.api import AnonymousSessionResponse, FavouriteRequest, SaveSearchRequest
from app.services.nlp.sanitise import QueryValidationError, normalise_query

router = APIRouter(prefix="/api", tags=["account"])


def _require_persistence(accounts: AccountRepository) -> None:
    if not accounts.available:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Accounts require a database. Set DATABASE_URL to enable them.",
        )


@router.post(
    "/auth/session",
    response_model=AnonymousSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an anonymous account token",
)
async def create_session(
    accounts: AccountRepository = Depends(get_accounts),
) -> AnonymousSessionResponse:
    _require_persistence(accounts)
    created = await accounts.create_anonymous_user()
    if created is None:  # pragma: no cover - guarded above
        raise HTTPException(status_code=500, detail="Could not create a session")
    return AnonymousSessionResponse(**created)


@router.get("/account/saved-searches", summary="List saved searches")
async def list_saved_searches(
    user=Depends(require_user), accounts: AccountRepository = Depends(get_accounts)
) -> List[dict]:
    return await accounts.list_saved_searches(user.id)


@router.post(
    "/account/saved-searches",
    status_code=status.HTTP_201_CREATED,
    summary="Save a search",
)
async def create_saved_search(
    payload: SaveSearchRequest,
    user=Depends(require_user),
    accounts: AccountRepository = Depends(get_accounts),
    context: AppContext = Depends(get_context),
) -> dict:
    try:
        query = normalise_query(
            payload.query,
            max_length=context.settings.search_max_query_length,
            min_length=context.settings.search_min_query_length,
        )
    except QueryValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    outcome = await context.parser.parse(query)
    saved = await accounts.save_search(
        user_id=user.id,
        query=query,
        intent=outcome.intent.model_dump(mode="json"),
        fingerprint=outcome.intent.fingerprint(),
        label=payload.label,
    )
    if saved is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Could not save the search")
    return saved


@router.delete(
    "/account/saved-searches/{saved_search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved search",
)
async def delete_saved_search(
    saved_search_id: str,
    user=Depends(require_user),
    accounts: AccountRepository = Depends(get_accounts),
) -> None:
    removed = await accounts.delete_saved_search(user.id, saved_search_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.get("/account/favourites", summary="List favourites")
async def list_favourites(
    user=Depends(require_user), accounts: AccountRepository = Depends(get_accounts)
) -> List[dict]:
    return await accounts.list_favourites(user.id)


@router.post("/account/favourites", status_code=status.HTTP_201_CREATED, summary="Add a favourite")
async def add_favourite(
    payload: FavouriteRequest,
    user=Depends(require_user),
    accounts: AccountRepository = Depends(get_accounts),
) -> dict:
    added = await accounts.add_favourite(user.id, payload.product, payload.group_id)
    if added is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Could not save the favourite")
    return added


@router.delete(
    "/account/favourites/{retailer}/{product_id:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a favourite",
)
async def remove_favourite(
    retailer: str,
    product_id: str,
    user=Depends(require_user),
    accounts: AccountRepository = Depends(get_accounts),
) -> None:
    removed = await accounts.remove_favourite(user.id, retailer, product_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
