"""The one company an /external ingest or read call works inside (group A1).

Everything this surface touches is partitioned per company: the masters carry a
NOT NULL ``company_id`` (migration 305) and their business codes are unique only
WITHIN a company, so "warehouse BRW" names two different rows. Without an anchor
the ingest raw-INSERTed no company at all and adopted by code across all of
them, which on the live schema is a failed write at best and the wrong company's
record overwritten at worst.

**Stated, never guessed.** The GRN path can infer its company from something
already in the payload - a warehouse code, a container number - and
``pin_scope_to_companies`` falls back to the incumbent when it finds nothing.
An ingest payload carries codes and nothing else, so there is nothing to infer
from, and the same fallback would file a Mocha push under Sorento while adopting
Sorento's rows on the way. That mistake is invisible until somebody reads a
wrong stock figure weeks later; a 422 is one field for the ESB to fix.

The resolved id is also pushed onto the session scope, so the ORM filter and the
auto-stamp agree with the raw SQL the ingest service issues. The two must not be
able to disagree about which company a request is in.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.base import set_company_scope
from app.services.error_handler import AppException

# The columns a company may be named by, in precedence order. Sorento's own code
# first: it is unique and it is what an operator debugging a failed sync reads
# off the Companies screen. `autocount_ref` is the ESB's vocabulary for the same
# company and is nullable, so it is a second chance, not the primary key.
#
# Interpolated into SQL below, and safe to be: the values come from this tuple,
# never from a payload. Every payload value is a bound parameter.
_MATCH_COLUMNS = ("code", "autocount_ref")


def _company_id_for_code(db: Session, code: str) -> Optional[str]:
    """The active company ``code`` names, or None.

    Case-insensitive on both columns. The ESB knows a company by whatever
    AutoCount calls it and an operator types the Sorento code; neither side
    controls the other's casing, and a sync must not fail on it.

    An inactive company is not a candidate. A caller that may not write there
    gains nothing from being told the difference between "no such company" and
    "that one is closed", and both are the same fix: send a live code.
    """
    for column in _MATCH_COLUMNS:
        row = db.execute(
            text(
                f"SELECT id FROM companies "
                f"WHERE lower({column}) = lower(:v) AND is_active = true LIMIT 1"
            ),
            {"v": code},
        ).first()
        if row is not None:
            return str(row[0])
    return None


def _binding_code(db: Session, integration_id: Optional[str]) -> Optional[str]:
    """``config_json.company_code`` for the calling integration, if it has one.

    An ESB dedicated to one AutoCount company configures it once here instead of
    repeating it in every request body. Absent - the common case today - is not
    an error on its own; it just leaves the body to say.
    """
    if not integration_id:
        return None
    value = db.execute(
        text("SELECT config_json ->> 'company_code' FROM integrations WHERE id = :id"),
        {"id": str(integration_id)},
    ).scalar()
    return value.strip() if isinstance(value, str) and value.strip() else None


def _resolved(db: Session, code: Optional[str]) -> Optional[str]:
    if code is None:
        return None
    company_id = _company_id_for_code(db, code)
    if company_id is None:
        raise AppException(
            status_code=422,
            message=(
                f"Unknown company '{code}'. Expected the code or the AutoCount "
                "reference of an active company."
            ),
            code="UNKNOWN_COMPANY",
        )
    return company_id


def resolve_company_anchor(db: Session, payload: dict, principal: dict) -> str:
    """The company id this request writes, adopts and reads inside.

    Body first, then the integration's binding. Both present and disagreeing is
    refused rather than ranked: either half could be the mistake, and only the
    caller knows which, so picking one would make a misconfigured integration
    look like a working one until the rows are read back.
    """
    body_code = payload.get("companyCode") if isinstance(payload, dict) else None
    body_code = body_code.strip() if isinstance(body_code, str) and body_code.strip() else None
    binding_code = _binding_code(db, principal.get("integration_id"))

    body_company_id = _resolved(db, body_code)
    binding_company_id = _resolved(db, binding_code)

    if body_company_id and binding_company_id and body_company_id != binding_company_id:
        raise AppException(
            status_code=422,
            message=(
                f"companyCode '{body_code}' names a different company from this "
                f"integration's binding '{binding_code}'. One request writes into "
                "one company."
            ),
            code="COMPANY_ANCHOR_AMBIGUOUS",
        )

    company_id = body_company_id or binding_company_id
    if company_id is None:
        raise AppException(
            status_code=422,
            message=(
                "No company anchor. Send a top-level 'companyCode', or bind this "
                "integration to a company (config_json.company_code)."
            ),
            code="COMPANY_ANCHOR_REQUIRED",
        )

    # So the ORM filter and auto-stamp cannot disagree with the service's raw SQL.
    set_company_scope(db, frozenset({company_id}))
    return company_id
