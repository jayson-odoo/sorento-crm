"""Entity reference resolution endpoint.

Exposes the deterministic entity resolver as an HTTP API so the MCP layer (or any
external caller) can disambiguate codes mid-turn. The resolver itself lives in
`app.services.entity_resolver`.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.entity_resolver import resolve_references

router = APIRouter(prefix="/references")


class ResolveReferenceRequest(BaseModel):
    """POST body for /references/resolve."""

    query: str = Field(default="", description="Free-text query or a single code to resolve.")
    tokens: list[str] | None = Field(
        default=None,
        description="Optional pre-extracted tokens. If provided, resolver skips regex extraction.",
    )


def _resolve_input(db: Session, query: str, tokens: list[str] | None):
    input_tokens: list[str] | str
    if tokens:
        filtered = [t for t in tokens if t]
        if not filtered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tokens provided but empty after filtering",
            )
        input_tokens = filtered
    else:
        if not (query or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="query is required when tokens is not provided",
            )
        input_tokens = query
    return resolve_references(db, input_tokens).as_dict()


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
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Resolve free-text entity references (product codes, order numbers, shipment numbers, ...)
    to their canonical entity types.

    Returns, per token: the entity type (product, customer_order, customer, inbound_shipment,
    spo_allocation, grn, warehouse, supplier, promotion) and a minimal display payload. Tokens
    with no deterministic match are returned in `unresolved_tokens` so the caller can tell the
    user "no record found" instead of guessing.
    """
    return _resolve_input(db, query, tokens)


@router.post("/resolve")
def resolve_reference_post(
    payload: ResolveReferenceRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """POST variant for external callers that send JSON body (e.g. n8n HTTP node)."""
    return _resolve_input(db, payload.query, payload.tokens)
