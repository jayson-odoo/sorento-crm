"""Entity reference resolution endpoint.

Exposes the deterministic entity resolver as an HTTP API so the MCP layer (or any
external caller) can disambiguate codes mid-turn. The resolver itself lives in
`app.services.entity_resolver`.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.access import ContactAccessType
from app.models.marketing import Promotion
from app.services.entity_resolver import (
    resolve_references,
    resolve_references_intersection,
)

router = APIRouter(prefix="/references")


_ALLOWED_MATCH_MODES = {"or", "and"}


def _apply_promotion_access_levels_filter(
    db: Session,
    result: dict[str, Any],
    access_level_names: list[str] | None,
) -> dict[str, Any]:
    """Drop promotion matches whose `access_levels` JSONB does not intersect the
    caller-supplied access-level NAMES.

    Names are translated to canonical `contact_access_types.code` values (case-
    insensitive name match) before intersection, because `Promotion.access_levels`
    stores codes. Non-promotion matches are untouched. Empty / missing
    `access_level_names` is a no-op.
    """
    if not access_level_names:
        return result
    names_lower = {n.strip().lower() for n in access_level_names if n and n.strip()}
    if not names_lower:
        return result

    code_rows = (
        db.query(ContactAccessType.code)
        .filter(func.lower(ContactAccessType.name).in_(names_lower))
        .all()
    )
    allowed_codes: set[str] = {r[0] for r in code_rows}

    def _collect_promo_ids() -> set[str]:
        ids: set[str] = set()
        for tr in result.get("resolutions", []) or []:
            for m in tr.get("matches", []) or []:
                if m.get("entity_type") == "promotion" and m.get("uuid"):
                    ids.add(str(m["uuid"]))
        for m in result.get("intersection", []) or []:
            if m.get("entity_type") == "promotion" and m.get("uuid"):
                ids.add(str(m["uuid"]))
        return ids

    promo_ids = _collect_promo_ids()
    keep_ids: set[str] = set()
    if promo_ids and allowed_codes:
        rows = (
            db.query(Promotion.id, Promotion.access_levels)
            .filter(Promotion.id.in_(list(promo_ids)))
            .all()
        )
        for pid, levels in rows:
            if isinstance(levels, list) and allowed_codes.intersection(levels):
                keep_ids.add(str(pid))

    def _keep(m: dict[str, Any]) -> bool:
        if m.get("entity_type") != "promotion":
            return True
        return str(m.get("uuid") or "") in keep_ids

    if "resolutions" in result:
        for tr in result["resolutions"]:
            tr["matches"] = [m for m in tr.get("matches", []) if _keep(m)]
            tr["resolved"] = bool(tr["matches"]) and not tr.get("ambiguous", False)
        result["unresolved_tokens"] = [
            tr["token"] for tr in result["resolutions"] if not tr["matches"]
        ]

    if "intersection" in result:
        result["intersection"] = [m for m in result["intersection"] if _keep(m)]
        by_type: dict[str, list[dict[str, Any]]] = {}
        for m in result["intersection"]:
            by_type.setdefault(m["entity_type"], []).append(m)
        result["by_entity_type"] = by_type
        result["empty"] = not result["intersection"]
        if result["empty"]:
            result["unresolved_tokens"] = list(result.get("tokens", []))

    return result


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
            "Restrict resolution to these entity types. Two modes:\n"
            "  • Set filter (default) — len != len(tokens): the list is treated as a "
            "whitelist; every surviving probe runs against every token.\n"
            "  • Positional pairing — len == len(tokens): tokens[i] is resolved ONLY "
            "against allowed_entity_types[i]. Use this when the caller already knows "
            "which token names which entity (e.g. tokens=['Fira Ventures','DO'] "
            "paired with ['customer','delivery_order'] — 'DO' is searched only as a "
            "delivery_order and never as a customer)."
        ),
    )
    access_levels: list[str] | None = Field(
        default=None,
        description=(
            "Promotion-only post-filter. Array of contact-access-type NAMES (e.g. "
            "['Dealer','End User']) — translated to codes via contact_access_types.name "
            "and intersected with Promotion.access_levels (JSONB). A promotion match "
            "survives only when at least one of its stored access codes is in the "
            "translated set. Non-promotion matches are untouched. Empty / null → no-op."
        ),
    )


def _resolve_input(
    db: Session,
    query: str,
    tokens: list[str] | None,
    match_mode: str = "or",
    allowed_entity_types: list[str] | None = None,
    access_levels: list[str] | None = None,
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
        result = resolve_references_intersection(
            db,
            prepared_tokens,
            allowed_entity_types=allowed_entity_types,
        ).as_dict()
    else:
        result = resolve_references(
            db,
            input_for_or,
            allowed_entity_types=allowed_entity_types,
        ).as_dict()
    return _apply_promotion_access_levels_filter(db, result, access_levels)


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
        description=(
            "Entity-type whitelist. If its length equals `tokens`, pairs are positional "
            "(token[i] resolved only against allowed_entity_types[i]); otherwise it acts "
            "as a global set filter applied to every token."
        ),
    ),
    access_levels: list[str] | None = Query(
        None,
        description=(
            "Promotion-only post-filter. Array of contact-access-type NAMES (translated "
            "to codes via contact_access_types.name and intersected with "
            "Promotion.access_levels). Promotion matches survive only on intersection; "
            "non-promotion matches untouched. Empty / omitted → no-op."
        ),
    ),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Resolve free-text entity references (product codes, order numbers, shipment numbers, ...)
    to their canonical entity types.

    OR mode (default): per-token, returns canonical UUIDs + display payload + ambiguity signals.
    AND mode: cross-token intersection across each entity's concatenated searchable columns.
    """
    return _resolve_input(
        db,
        query,
        tokens,
        match_mode=match_mode,
        allowed_entity_types=allowed_entity_types,
        access_levels=access_levels,
    )


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
        access_levels=payload.access_levels,
    )
