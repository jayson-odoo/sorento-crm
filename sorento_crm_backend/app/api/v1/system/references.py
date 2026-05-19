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
from app.services.entity_resolver import (
    resolve_references,
    resolve_references_intersection,
)

router = APIRouter(prefix="/references")


_ALLOWED_MATCH_MODES = {"or", "and"}


class ResolveReferenceRequest(BaseModel):
    """POST body for /references/resolve."""

    query: str = Field(default="", description="Free-text query or a single code to resolve.")
    tokens: list[str] | None = Field(
        default=None,
        description="Optional pre-extracted tokens. If provided, resolver skips regex extraction.",
    )
    match_mode: str = Field(
        default="or",
        description=(
            "'or' (default): each token resolves independently — per-token candidate lists, "
            "ambiguity surfaced per token. 'and': cross-token intersection — returns ONLY rows "
            "whose concatenated searchable columns contain EVERY token. Use 'and' for compound "
            "filters like 'cabana filter tap promotion'. Code-only entity types (SPO / GRN / "
            "inbound shipment) are skipped in 'and' mode."
        ),
    )
    allowed_entity_types: list[str] | None = Field(
        default=None,
        description=(
            "Restrict resolution to these entity types. Useful when caller knows it can only "
            "consume e.g. promotion + attachment hits."
        ),
    )


def _resolve_input(
    db: Session,
    query: str,
    tokens: list[str] | None,
    match_mode: str = "or",
    allowed_entity_types: list[str] | None = None,
):
    mode = (match_mode or "or").strip().lower()
    if mode not in _ALLOWED_MATCH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"match_mode must be one of {sorted(_ALLOWED_MATCH_MODES)}",
        )

    if tokens:
        filtered = [t for t in tokens if t]
        if not filtered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tokens provided but empty after filtering",
            )
        prepared_tokens: list[str] = filtered
        input_for_or: list[str] | str = filtered
    else:
        if not (query or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="query is required when tokens is not provided",
            )
        # AND-mode needs explicit tokens; fall back to query splitting when caller
        # passed only a single phrase. Pure-string queries split on whitespace are
        # often wrong (multi-word entities collapse), so AND-mode REQUIRES tokens.
        if mode == "and":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="match_mode='and' requires `tokens` (one phrase per token), not a free-text query",
            )
        prepared_tokens = []
        input_for_or = query

    if mode == "and":
        return resolve_references_intersection(
            db,
            prepared_tokens,
            allowed_entity_types=allowed_entity_types,
        ).as_dict()
    return resolve_references(
        db,
        input_for_or,
        allowed_entity_types=allowed_entity_types,
    ).as_dict()


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
    match_mode: str = Query(
        "or",
        description=(
            "'or' (default) returns per-token candidates. 'and' returns cross-token intersection "
            "— rows matching every token. AND-mode requires `tokens` (cannot use `query`)."
        ),
    ),
    allowed_entity_types: list[str] | None = Query(
        None,
        description="Optional whitelist of entity types to consider.",
    ),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Resolve free-text entity references (product codes, order numbers, shipment numbers, ...)
    to their canonical entity types.

    OR mode (default): per-token, returns canonical UUIDs + display payload + ambiguity signals.
    AND mode: cross-token intersection across each entity's concatenated searchable columns.
    """
    return _resolve_input(db, query, tokens, match_mode=match_mode, allowed_entity_types=allowed_entity_types)


@router.post("/resolve")
def resolve_reference_post(
    payload: ResolveReferenceRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """POST variant for external callers that send JSON body (e.g. n8n HTTP node)."""
    return _resolve_input(
        db,
        payload.query,
        payload.tokens,
        match_mode=payload.match_mode,
        allowed_entity_types=payload.allowed_entity_types,
    )
