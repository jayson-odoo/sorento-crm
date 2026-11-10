"""QUOTE-TERMS-SELECT: payment terms from the AutoCount-synced master, validity as number + unit.

One rule set for the terms template, the quotation copy and the cover preview:

- ``payment_term_id`` in a payload picks a term (this company's, active) and sets the printed
  ``payment_terms`` text to its label; an explicit null clears both.
- ``validity_value`` / ``validity_unit`` in a payload come as a pair (both set or both null) and
  set the printed ``validity`` text, e.g. ``2 WEEKS``.
- A payload that names none of them leaves the stored text alone, so a legacy free-text value
  keeps printing until someone picks (no silent loss, owner brief 10 Nov 2026).

The printed text lives on the row itself, so issue freeze, cover, PDF and sign link need nothing.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.payment_term import PaymentTerm
from app.services.error_handler import AppException

VALIDITY_UNITS = ("day", "week", "month", "year")
VALIDITY_MIN = 1
VALIDITY_MAX = 999

_VALIDITY_TEXT = re.compile(r"^\s*(\d{1,3})\s*(day|week|month|year)s?\s*$", re.IGNORECASE)


def format_validity(value: int, unit: str) -> str:
    """``2, week`` -> ``2 WEEKS``; singular when the number is 1."""
    word = unit.upper() if value == 1 else f"{unit.upper()}S"
    return f"{value} {word}"


def parse_validity(text: Optional[str]) -> Optional[Tuple[int, str]]:
    """Legacy free text that is exactly a number and a unit, else None (kept as text)."""
    match = _VALIDITY_TEXT.match(text or "")
    if not match:
        return None
    value = int(match.group(1))
    if not VALIDITY_MIN <= value <= VALIDITY_MAX:
        return None
    return value, match.group(2).lower()


def term_label(term: Any) -> str:
    description = (term.description or "").strip()
    return description or term.term_code


def _norm(value: Optional[str]) -> str:
    return " ".join((value or "").split()).lower()


def list_terms(db: Session, *, company_id: str) -> List[Dict[str, Any]]:
    """The select's options: this company's active terms, by label."""
    rows = (
        db.query(PaymentTerm)
        .filter(PaymentTerm.company_id == company_id, PaymentTerm.is_active.is_(True))
        .all()
    )
    out = [
        {
            "id": str(row.id),
            "code": row.term_code,
            "description": row.description,
            "label": term_label(row),
        }
        for row in rows
    ]
    return sorted(out, key=lambda row: row["label"].lower())


def project_customer_id(db: Session, project: Any) -> Optional[str]:
    """The project's customer, by the rule the project list uses
    (`project_service._effective_customer_id`): the one picked on the sales profile, else the
    linked lead's buyer."""
    from app.models.projects import ProjectLead, ProjectSalesProfile

    picked = (
        db.query(ProjectSalesProfile.customer_id)
        .filter(ProjectSalesProfile.project_id == project.id)
        .scalar()
    )
    if picked:
        return str(picked)
    if getattr(project, "lead_id", None):
        lead_customer = (
            db.query(ProjectLead.customer_id).filter(ProjectLead.id == project.lead_id).scalar()
        )
        return str(lead_customer) if lead_customer else None
    return None


def customer_term(db: Session, *, company_id: str, customer_id: Optional[str]) -> Optional[PaymentTerm]:
    """The active term named by the customer's AutoCount debtor terms (`Debtor.DisplayTerm`),
    matched by code ignoring case and spacing; None when the customer names none or none syncs.
    Owner Q3 (10 Nov 2026): this beats the terms template's default on a new quotation."""
    if not customer_id:
        return None
    from app.models.order import Customer

    code = (
        db.query(Customer.payment_terms_code)
        .filter(Customer.id == str(customer_id), Customer.company_id == company_id)
        .scalar()
    )
    if not (code or "").strip():
        return None
    wanted = _norm(code)
    for term in (
        db.query(PaymentTerm)
        .filter(PaymentTerm.company_id == company_id, PaymentTerm.is_active.is_(True))
        .order_by(PaymentTerm.created_at, PaymentTerm.id)
        .all()
    ):
        if _norm(term.term_code) == wanted:
            return term
    return None


def _unprocessable(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


def resolve(db: Session, *, company_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """The column writes the structured keys in ``payload`` imply, validated.

    Returns only the keys to set: a subset of ``payment_term_id``, ``payment_terms``,
    ``validity_value``, ``validity_unit``, ``validity``. Raw ``payment_terms`` / ``validity`` text in
    the payload is not looked at here; the caller writes that first and this wins over it.
    """
    out: Dict[str, Any] = {}
    if "payment_term_id" in payload:
        term_id = payload.get("payment_term_id")
        if term_id:
            # A malformed id is the same refusal as an unknown one, never a 500 from Postgres.
            try:
                term_id = str(uuid.UUID(str(term_id)))
            except ValueError:
                raise _unprocessable(
                    "That payment term is not one of this company's AutoCount terms. Pick one from the list.",
                    "payment_term_unknown",
                )
            term = (
                db.query(PaymentTerm)
                .filter(
                    PaymentTerm.id == str(term_id),
                    PaymentTerm.company_id == company_id,
                    PaymentTerm.is_active.is_(True),
                )
                .first()
            )
            if term is None:
                raise _unprocessable(
                    "That payment term is not one of this company's AutoCount terms. Pick one from the list.",
                    "payment_term_unknown",
                )
            out["payment_term_id"] = str(term.id)
            out["payment_terms"] = term_label(term)
        else:
            out["payment_term_id"] = None
            out["payment_terms"] = None

    if "validity_value" in payload or "validity_unit" in payload:
        value = payload.get("validity_value")
        unit = payload.get("validity_unit")
        if value is None and unit is None:
            out.update(validity_value=None, validity_unit=None, validity=None)
        else:
            if value is None or unit is None:
                raise _unprocessable(
                    "Validity needs both a number and a unit, e.g. 2 weeks.", "validity_incomplete"
                )
            if unit not in VALIDITY_UNITS:
                raise _unprocessable(
                    "Validity is in days, weeks, months or years.", "validity_unit_unknown"
                )
            if isinstance(value, bool) or not isinstance(value, int) or not (
                VALIDITY_MIN <= value <= VALIDITY_MAX
            ):
                raise _unprocessable(
                    f"Validity is a whole number from {VALIDITY_MIN} to {VALIDITY_MAX}.",
                    "validity_value_range",
                )
            out.update(validity_value=value, validity_unit=unit, validity=format_validity(value, unit))
    return out


def apply(db: Session, *, company_id: str, target: Any, payload: Dict[str, Any]) -> None:
    """``resolve`` written onto a row (or namespace)."""
    for field, value in resolve(db, company_id=company_id, payload=payload).items():
        setattr(target, field, value)


def active_term_id(db: Session, *, company_id: str, term_id: Optional[str]) -> Optional[str]:
    """``term_id`` when it is still an active term of this company, else None. A default handed
    to a new quotation must be one ``resolve`` accepts, or the create is refused."""
    if not term_id:
        return None
    found = (
        db.query(PaymentTerm.id)
        .filter(
            PaymentTerm.id == str(term_id),
            PaymentTerm.company_id == company_id,
            PaymentTerm.is_active.is_(True),
        )
        .scalar()
    )
    return str(found) if found else None


def link_legacy_terms(db: Session, *, company_id: str) -> int:
    """Link templates and quotations whose legacy text equals an ACTIVE term's code or description.

    Case and spacing ignored, this company only, never one already linked, never a quotation that
    is with a manager or approved, and the printed text is left as it is. Runs after a non-dry
    ``payment_terms`` push. Returns the rows linked.
    """
    from app.models.projects import ProjectQuotationDocument, QuotationTemplate
    from app.services import project_quotation_approval_service as approvals

    by_text: Dict[str, str] = {}
    terms = (
        db.query(PaymentTerm)
        .filter(PaymentTerm.company_id == company_id, PaymentTerm.is_active.is_(True))
        .order_by(PaymentTerm.term_code)
        .all()
    )
    # A code never loses to another term's description.
    for term in terms:
        by_text.setdefault(_norm(term.term_code), str(term.id))
    for term in terms:
        if (term.description or "").strip():
            by_text.setdefault(_norm(term.description), str(term.id))
    if not by_text:
        return 0

    linked = 0
    for model in (QuotationTemplate, ProjectQuotationDocument):
        rows = (
            db.query(model)
            .filter(
                model.company_id == company_id,
                model.payment_term_id.is_(None),
                func.coalesce(func.trim(model.payment_terms), "") != "",
            )
            .all()
        )
        for row in rows:
            term_id = by_text.get(_norm(row.payment_terms))
            if term_id and model is ProjectQuotationDocument and (
                approvals.current_key(db, row) in approvals.LOCKED_KEYS
            ):
                continue
            if term_id:
                row.payment_term_id = term_id
                linked += 1
    db.flush()
    return linked
