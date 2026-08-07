"""Spec Registry API — the vocabulary both the CRM ranker and the n8n parser read.

One vocabulary, two consumers, so this endpoint is the thing that stops them drifting:
if the parser emits `wall_mounted` while the ranker looks for `wall_hung`, every query
quietly scores worse and nothing logs an error.

Writes exist, and they are shaped by that guarantee rather than around it:

  * a `seed` row is repaired on every deploy, so editing its vocabulary would be undone.
    Staff extend it instead — `user_synonyms` is merged in at read time, additive only,
    so a word added here can never remove one the parser depends on.
  * a `user` row has no seed to drift from and is left alone entirely.
  * calibration (`rank_weight`, `is_active`, the match window) has always been
    human-owned on both.

So: add words and tune weights freely; renaming a shipped VALUE is deliberately not
offered, because that is the one edit that breaks the two consumers apart.
"""
import hashlib
import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.product_spec import ProductSpecRegistry
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.product_spec_registry import (
    active_registry,
    default_match_window,
    merged_synonyms,
)

router = APIRouter()


def _serialise(row) -> dict:
    return {
        "spec_key": row.spec_key,
        "label": row.label,
        "data_type": row.data_type,
        "unit": row.unit,
        "allowed_values": row.allowed_values or [],
        # Merged view: consumers see one vocabulary, not the seed/user split.
        "synonyms": merged_synonyms(row),
        "applies_to_classes": row.applies_to_classes or [],
        "applies_when": row.applies_when or {},
        "rank_weight": float(row.rank_weight) if row.rank_weight is not None else None,
        "measured_coverage": row.measured_coverage,
        # Editing surface: which fields the UI may offer, and what it must not touch.
        "source": row.source or "seed",
        "user_synonyms": row.user_synonyms or {},
        "match_tolerance": float(row.match_tolerance) if row.match_tolerance is not None else 0.0,
        "match_decay": float(row.match_decay) if row.match_decay is not None else 0.0,
        "is_active": bool(row.is_active),
    }


@router.get("")
@router.get("/")
async def get_spec_registry(
    request: Request,
    response: Response,
    current_user: dict = Depends(
        # Reuses the product-master read permission rather than minting a new one:
        # a new permission needs a grant sweep across provisioned roles, and this is
        # product vocabulary that anyone who may read products may read.
        require_permission_with_api_key("master_data.products.view")
    ),
    db: Session = Depends(get_db),
):
    """The active spec vocabulary, with an ETag so the parser can skip re-reading it."""
    try:
        rows = active_registry(db)
        keys = [_serialise(row) for row in rows]
        stamps = [r.updated_at or r.created_at for r in rows]
        updated_at = max(stamps).isoformat() if stamps else None

        payload = {"keys": keys, "updated_at": updated_at}

        # Hash the payload itself rather than the max timestamp: an admin edit that
        # lands in the same second still changes the body, and a stale prompt is
        # worse than a re-read.
        etag = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        etag_header = f'"{etag}"'

        if request.headers.get("if-none-match") == etag_header:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag_header})

        response.headers["ETag"] = etag_header
        response.headers["Cache-Control"] = "private, max-age=60"
        return payload
    except Exception as e:
        raise handle_internal_error(str(e))


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
_EDITABLE_DATA_TYPES = {"enum", "numeric", "boolean"}


class SpecKeyUpdate(BaseModel):
    """What a human may change on an existing key.

    Deliberately narrow. `spec_key`, `data_type` and `unit` are absent because changing
    them on a key that already has derived values against it would silently invalidate
    every stored spec — that is a migration, not an edit.
    """

    label: Optional[str] = Field(default=None, min_length=1, max_length=150)
    rank_weight: Optional[float] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None
    match_tolerance: Optional[float] = Field(default=None, ge=0)
    match_decay: Optional[float] = Field(default=None, ge=0)
    # value -> [extra customer phrasings]. Merged with the seed's, never replacing it.
    user_synonyms: Optional[dict[str, list[str]]] = None
    # Only honoured on a `user` row; a seed row's closed list is the parser's contract.
    allowed_values: Optional[list[str]] = None


class SpecKeyCreate(BaseModel):
    """A brand-new key, owned by whoever created it and never seed-repaired."""

    spec_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=150)
    data_type: str
    unit: Optional[str] = Field(default=None, max_length=16)
    allowed_values: list[str] = Field(default_factory=list)
    user_synonyms: dict[str, list[str]] = Field(default_factory=dict)
    applies_when: dict[str, list[str]] = Field(default_factory=dict)
    rank_weight: float = Field(default=1.0, ge=0, le=100)
    is_active: bool = True


def _reject(message: str, code: str):
    from app.services.error_handler import AppException

    return AppException(status_code=400, message=message, code=code)


def _validate_reachable(data_type: str, allowed_values, synonyms) -> None:
    """An allowed value nobody can say is a value that can never be searched for.

    There is already a test asserting this invariant across the seeded registry; the UI
    must not be able to introduce a violation the seed forbids.
    """
    if data_type != "enum":
        return
    words = {v: list(w) for v, w in (synonyms or {}).items()}
    unreachable = [v for v in (allowed_values or []) if not words.get(v)]
    if unreachable:
        raise _reject(
            "These values have no words a customer could say, so nothing would ever "
            f"match them: {', '.join(unreachable)}. Add at least one synonym each.",
            "spec_registry_unreachable_value",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_spec_key(
    payload: SpecKeyCreate,
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.add")),
    db: Session = Depends(get_db),
):
    """Register a new spec key. It is `user`-owned, so no deploy will overwrite it.

    A new key changes what a customer PHRASE can resolve to immediately, but no product
    carries it until a derivation rule exists and the catalog is re-derived. The UI says
    so; this endpoint does not pretend otherwise.
    """
    try:
        if payload.data_type not in _EDITABLE_DATA_TYPES:
            raise _reject(
                f"data_type must be one of {sorted(_EDITABLE_DATA_TYPES)}.",
                "spec_registry_bad_type",
            )
        if db.query(ProductSpecRegistry).filter_by(spec_key=payload.spec_key).first():
            raise _reject(
                f"A spec key named '{payload.spec_key}' already exists.",
                "spec_registry_duplicate",
            )
        _validate_reachable(payload.data_type, payload.allowed_values, payload.user_synonyms)

        tolerance, decay = default_match_window(payload.unit)
        row = ProductSpecRegistry(
            spec_key=payload.spec_key,
            label=payload.label,
            data_type=payload.data_type,
            unit=payload.unit,
            allowed_values=payload.allowed_values,
            synonyms={},
            user_synonyms=payload.user_synonyms,
            applies_to_classes=[],
            applies_when=payload.applies_when,
            rank_weight=payload.rank_weight,
            is_active=payload.is_active,
            match_tolerance=tolerance,
            match_decay=decay,
            source="user",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialise(row)
    except Exception as e:
        if type(e).__name__ == "AppException":
            raise
        raise handle_internal_error(str(e))


@router.patch("/{spec_key}")
async def update_spec_key(
    spec_key: str,
    payload: SpecKeyUpdate = Body(...),
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.edit")),
    db: Session = Depends(get_db),
):
    """Edit calibration and extend vocabulary. Seed-owned vocabulary stays seed-owned."""
    try:
        row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
        if row is None:
            raise handle_not_found("Spec key", spec_key)

        fields = payload.model_dump(exclude_unset=True)

        if "allowed_values" in fields:
            if (row.source or "seed") == "seed":
                raise _reject(
                    "This key's values ship with the product and are kept in step with "
                    "the chatbot parser, so they cannot be edited here. Add customer "
                    "wording instead, or create your own key.",
                    "spec_registry_seed_values_immutable",
                )
            row.allowed_values = fields["allowed_values"]

        if "user_synonyms" in fields:
            row.user_synonyms = {
                value: [w.strip() for w in words if w and w.strip()]
                for value, words in (fields["user_synonyms"] or {}).items()
            }

        for field in ("label", "rank_weight", "is_active", "match_tolerance", "match_decay"):
            if field in fields and fields[field] is not None:
                setattr(row, field, fields[field])

        _validate_reachable(row.data_type, row.allowed_values, merged_synonyms(row))

        db.commit()
        db.refresh(row)
        return _serialise(row)
    except Exception as e:
        if type(e).__name__ in {"AppException", "HTTPException"}:
            raise
        raise handle_internal_error(str(e))


@router.delete("/{spec_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spec_key(
    spec_key: str,
    current_user: dict = Depends(
        require_permission_with_api_key("master_data.spec_registry.delete")
    ),
    db: Session = Depends(get_db),
):
    """Delete a user-created key. Seeded keys are deactivated, never deleted.

    A seeded key would simply reappear on the next deploy, so offering "delete" for one
    would be a button that silently does nothing.
    """
    try:
        row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
        if row is None:
            raise handle_not_found("Spec key", spec_key)
        if (row.source or "seed") == "seed":
            raise _reject(
                "This key ships with the product and would come back on the next "
                "deploy. Switch it off instead.",
                "spec_registry_seed_undeletable",
            )
        db.delete(row)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        if type(e).__name__ in {"AppException", "HTTPException"}:
            raise
        raise handle_internal_error(str(e))
