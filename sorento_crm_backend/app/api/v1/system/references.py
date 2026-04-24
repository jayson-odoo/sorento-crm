"""Entity reference resolution endpoint.

Exposes the deterministic entity resolver as an HTTP API so the MCP layer (or any
external caller) can disambiguate codes mid-turn. The resolver itself lives in
`app.services.entity_resolver`.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.entity_resolver import resolve_references

router = APIRouter(prefix="/references")


@router.get("/resolve")
def resolve_reference(
    query: str = Query(..., description="Free-text query or a single code to resolve."),
    tokens: list[str] | None = Query(
        None,
        description=(
            "Optional pre-extracted tokens. If provided, the resolver skips regex extraction and "
            "looks up each token verbatim."
        ),
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Resolve free-text entity references (product codes, order numbers, shipment numbers, ...)
    to their canonical entity types.

    Returns, per token: the entity type (product, customer_order, customer, inbound_shipment,
    spo_allocation, grn, warehouse, supplier, promotion) and a minimal display payload. Tokens
    with no deterministic match are returned in `unresolved_tokens` so the caller can tell the
    user "no record found" instead of guessing.
    """
    input_tokens: list[str] | str
    if tokens:
        input_tokens = [t for t in tokens if t]
    else:
        input_tokens = query or ""
    result = resolve_references(db, input_tokens)
    return result.as_dict()
