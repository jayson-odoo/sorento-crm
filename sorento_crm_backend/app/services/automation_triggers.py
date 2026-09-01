"""Trigger registry for automations.

A trigger turns an automation row into a list of {context} payloads, one per
match. The first concrete trigger watches promotion expiry: ``X days before
promotion end``; ``days_before_certificate_expiry`` is its certificate twin.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import company_scope
from app.models.certificate import (
    CERTIFICATE_STATUS_ACTIVE,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.marketing import Promotion


@dataclass(frozen=True)
class TriggerSpec:
    type: str
    label: str
    description: str
    config_schema: dict[str, Any]
    # Rule-engine fact sources this trigger exposes. Empty = no rule filtering
    # (conditions_json is ignored). days_before_promotion_end -> ("promotion",).
    fact_sources: tuple[str, ...] = ()
    # True when several matches from one run can be folded into a single email
    # per recipient, i.e. the automation's group_matches flag means anything.
    # Grouping is actually implemented by automation_service._EXPIRY_BATCH_SPECS,
    # so this flag MUST be True for exactly the keys in that dict and nothing
    # else - test_automation_trigger_catalog.py asserts the two cannot drift.
    # The FE reads it to decide whether to render the "Combine into one email"
    # switch, instead of hardcoding a trigger type.
    supports_grouping: bool = False


@dataclass(frozen=True)
class TriggerMatch:
    context: dict[str, Any]
    source_kind: str
    source_id: str
    # ORM objects keyed by fact-source name (e.g. {"promotion": <Promotion>}),
    # fed to rule_engine.resolve_facts for conditions_json filtering. None when
    # the trigger exposes no fact sources.
    fact_sources: Optional[dict] = None


TriggerFn = Callable[[Session, dict[str, Any], str], Iterable[TriggerMatch]]

_REGISTRY: dict[str, tuple[TriggerSpec, TriggerFn]] = {}


def register(spec: TriggerSpec, fn: TriggerFn) -> None:
    _REGISTRY[spec.type] = (spec, fn)


def list_specs() -> list[TriggerSpec]:
    return [s for s, _ in _REGISTRY.values()]


def fire(
    db: Session,
    trigger_type: str,
    config: dict[str, Any],
    timezone: str,
) -> list[TriggerMatch]:
    pair = _REGISTRY.get(trigger_type)
    if not pair:
        raise ValueError(f"Unknown trigger type: {trigger_type}")
    _, fn = pair
    return list(fn(db, config or {}, timezone))


def _today_in_tz(timezone: str) -> date:
    try:
        from datetime import datetime as _dt

        return _dt.now(ZoneInfo(timezone)).date()
    except Exception:
        return date.today()


def _build_promotion_link(promotion_id: str) -> str:
    base = (settings.frontend_base_url or "").rstrip("/")
    if not base:
        return f"/marketing-management/promotions/{promotion_id}"
    return f"{base}/marketing-management/promotions/{promotion_id}"


def _build_certificate_link(certificate_id: str) -> str:
    """Internal, in-system deep link to one certificate.

    Reminder recipients are staff, so they get the CRM detail page and never a
    public ``/view?token=`` link (REM-4). The deep-link-after-login layout
    carries them back here once they sign in.
    """
    base = (settings.frontend_base_url or "").rstrip("/")
    path = f"/master-data-management/certificates/{certificate_id}"
    return f"{base}{path}" if base else path


def _build_complaint_link(complaint_id: str) -> str:
    base = (settings.frontend_base_url or "").rstrip("/")
    if not base:
        return f"/complaint-management/complaints/{complaint_id}"
    return f"{base}/complaint-management/complaints/{complaint_id}"


def _build_purchase_request_link(request_id: str, request_type: str | None = None) -> str:
    base = (settings.frontend_base_url or "").rstrip("/")
    if (request_type or "").strip() == "sponsorship_form":
        path = f"/procurement-management/sponsorship-forms/{request_id}"
    else:
        path = f"/procurement-management/purchase-requests/{request_id}"
    return f"{base}{path}" if base else path


def _trigger_days_before_promotion_end(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    days_before = int(config.get("days_before", 7) or 7)
    today = _today_in_tz(timezone)
    target_end = today + timedelta(days=days_before)

    rows = (
        db.query(Promotion)
        .filter(Promotion.end_date == target_end, Promotion.is_active.is_(True))
        .all()
    )
    for promo in rows:
        end_date = getattr(promo, "end_date")
        start_date = getattr(promo, "start_date")
        days_until_end = (end_date - today).days if end_date else None
        ctx = {
            "promotion": {
                "id": str(getattr(promo, "id")),
                "code": "",
                "name": str(getattr(promo, "description", "") or ""),
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "link": _build_promotion_link(str(getattr(promo, "id"))),
                "days_until_end": days_until_end,
                "created_by": getattr(promo, "created_by", None),
            },
            "today": today.isoformat(),
        }
        yield TriggerMatch(
            context=ctx,
            source_kind="promotion",
            source_id=str(getattr(promo, "id")),
            # The ORM object itself feeds rule_engine.resolve_facts so the
            # automation's conditions_json can filter on access levels / name / dates.
            fact_sources={"promotion": promo},
        )


register(
    TriggerSpec(
        type="days_before_promotion_end",
        label="Days before promotion end",
        description="Fires for every active promotion whose end_date is exactly X days from today (in the automation's timezone).",
        config_schema={
            "type": "object",
            "properties": {
                "days_before": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 7,
                    "title": "Days before promotion ends",
                }
            },
            "required": ["days_before"],
        },
        fact_sources=("promotion",),
        supports_grouping=True,
    ),
    _trigger_days_before_promotion_end,
)


def _trigger_days_before_certificate_expiry(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Certificates whose CURRENT revision expires exactly ``days_before`` days
    from today, in the automation's timezone.

    Exact-date semantics, identical to ``_trigger_days_before_promotion_end``:
    three automation rows (90 / 30 / 7) produce three independent reminders with
    no new code, and there is deliberately NO catch-up window - a scheduler
    outage on the match day loses that window's email (REM-7), which the
    validity-scoped list filter mitigates instead.

    Three exclusions fall out of the query rather than needing branches: an
    archived certificate fails the status filter; a NULL ``valid_until`` never
    equals a date, so an unknown expiry stays inert rather than reading as "no
    expiry"; and the join is on ``current_revision_id`` (re-checking
    ``is_current``), so a superseded revision's window never fires a reminder.
    """
    days_before = int(config.get("days_before", 30) or 30)
    today = _today_in_tz(timezone)
    target_expiry = today + timedelta(days=days_before)

    # A scheduler session never ran the company resolver, so its scope is UNSET -
    # fail-closed, which would return zero certificates. This sweep is a system
    # job that must see every company; the context manager restores whatever
    # scope the caller had.
    with company_scope(db, None):
        rows: list[Any] = (
            db.query(Certificate, CertificateRevision)
            .join(
                CertificateRevision,
                CertificateRevision.id == Certificate.current_revision_id,
            )
            .filter(
                Certificate.status == CERTIFICATE_STATUS_ACTIVE,
                CertificateRevision.is_current.is_(True),
                CertificateRevision.valid_until == target_expiry,
            )
            .order_by(Certificate.scheme, Certificate.certificate_number)
            .all()
        )
        coverage: dict[str, int] = {}
        if rows:
            coverage = {
                str(certificate_id): int(total)
                for certificate_id, total in db.query(
                    CertificateProduct.certificate_id,
                    func.count(CertificateProduct.id),
                )
                .filter(
                    CertificateProduct.certificate_id.in_(
                        [str(cert.id) for cert, _ in rows]
                    )
                )
                .group_by(CertificateProduct.certificate_id)
                .all()
            }

    for cert, revision in rows:
        valid_until = revision.valid_until
        ctx = {
            "certificate": {
                "id": str(cert.id),
                "scheme": cert.scheme,
                "certificate_number": cert.certificate_number,
                "certifying_body": cert.certifying_body or "",
                "issuer": cert.issuer or "",
                "title": cert.title or "",
                "status": cert.status,
                "revision_no": revision.revision_no,
                "valid_from": (
                    revision.valid_from.isoformat() if revision.valid_from else None
                ),
                "valid_until": valid_until.isoformat() if valid_until else None,
                "days_until_expiry": (valid_until - today).days if valid_until else None,
                "covered_product_count": coverage.get(str(cert.id), 0),
                "link": _build_certificate_link(str(cert.id)),
                "created_by": cert.created_by,
            },
            "today": today.isoformat(),
        }
        yield TriggerMatch(
            context=ctx,
            source_kind="certificate",
            source_id=str(cert.id),
            # The ORM row feeds rule_engine.resolve_facts, so conditions_json can
            # scope the automation to a scheme, a certifying body or a company.
            fact_sources={"certificate": cert},
        )


register(
    TriggerSpec(
        type="days_before_certificate_expiry",
        label="Days before certificate expiry",
        description=(
            "Fires for every active certificate whose current revision expires exactly "
            "X days from today (in the automation's timezone). Archived certificates, "
            "certificates with no expiry date and superseded revisions never match."
        ),
        config_schema={
            "type": "object",
            "properties": {
                "days_before": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 30,
                    "title": "Days before the certificate expires",
                }
            },
            "required": ["days_before"],
        },
        fact_sources=("certificate",),
        supports_grouping=True,
    ),
    _trigger_days_before_certificate_expiry,
)


def fact_sources_for(trigger_type: str) -> tuple[str, ...]:
    """Fact sources a trigger exposes for rule filtering (empty if unknown)."""
    pair = _REGISTRY.get(trigger_type)
    return pair[0].fact_sources if pair else ()


def _trigger_complaint_approved(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Event-driven trigger; pull-mode evaluation yields nothing.

    Matches are produced via :meth:`AutomationService.dispatch_event` from the
    complaint approval code path, so scheduled ``evaluate_due`` runs deliberately
    return no matches here.
    """
    return []


register(
    TriggerSpec(
        type="complaint_approved",
        label="Complaint approved",
        description="Fires when a complaint transitions to 'approved' (event-driven, dispatched from the approval flow).",
        config_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    _trigger_complaint_approved,
)


def _trigger_complaint_settled_on_site(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Event-driven trigger; pull-mode evaluation yields nothing.

    Matches come from :meth:`AutomationService.dispatch_event`, fired by the skip
    engine's complaint adapter. Deliberately separate from ``complaint_approved``:
    a settled complaint is a different business outcome and its context carries
    ``status='settled_on_site'``, so reusing the approval trigger would hand every
    subscribed automation a status that is not true.
    """
    return []


register(
    TriggerSpec(
        type="complaint_settled_on_site",
        label="Complaint settled on site",
        description=(
            "Fires when a complaint is closed as settled on site - the technician fixed "
            "the issue during the visit, so no replacement is arranged and customer "
            "service is never assigned (event-driven, dispatched from the skip flow)."
        ),
        config_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    _trigger_complaint_settled_on_site,
)


def _trigger_complaint_technical_response_updated(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Event-driven trigger; pull-mode evaluation yields nothing.

    Matches are produced via :meth:`AutomationService.dispatch_event` from the
    complaint update-and-reply code path (when the technical-team response is
    sent to the customer), so scheduled ``evaluate_due`` runs return nothing.
    """
    return []


register(
    TriggerSpec(
        type="complaint_technical_response_updated",
        label="Complaint technical response sent",
        description="Fires when a complaint's technical-team response is sent to the customer via Update & Reply (event-driven, dispatched from the reply flow).",
        config_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    _trigger_complaint_technical_response_updated,
)


def _trigger_purchase_request_approved(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Event-driven; pull-mode evaluation yields nothing.

    Matches are produced via :meth:`AutomationService.dispatch_event` from the
    purchase request approval code path.
    """
    return []


register(
    TriggerSpec(
        type="purchase_request_approved",
        label="Purchase request approved",
        description="Fires when a purchase request is approved (event-driven, dispatched from the approval flow).",
        config_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    _trigger_purchase_request_approved,
)


def _build_order_inquiry_link(so_number: Optional[str]) -> str:
    """The Order Inquiries worklist, narrowed to the sales order the row belongs to.

    There is no per-row detail page (`documentation/plans/scm/PLAN-scm-oi-handshake.md`) -
    the worklist's own search IS the way in, exactly as `orderInquiryRowHref` reaches it
    from every other screen. A row with no SO number (a claim-only or free-standing row)
    gets the unfiltered list rather than a broken query string.
    """
    base = (settings.frontend_base_url or "").rstrip("/")
    path = "/project-sales/order-inquiries"
    if so_number:
        from urllib.parse import quote

        path = f"{path}?query={quote(so_number)}"
    return f"{base}{path}" if base else path


def _trigger_order_inquiry_changed_with_links(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Event-driven; pull-mode evaluation yields nothing.

    Matches are produced via :meth:`AutomationService.dispatch_event` from
    ``ProjectOrderInquiryService._settle_row_in_place`` (`PLAN-scm-reorder-oi-feedback-
    1sep.md` S1, G6) - the moment a row CS has amended settles, is auto-acknowledged, AND
    already carries a link. A linkless amendment fires nothing: purchasing has arranged
    nothing yet, so there is nothing for this trigger to warn them a change moved.
    """
    return []


register(
    TriggerSpec(
        type="order_inquiry_changed_with_links",
        label="Order inquiry changed with links",
        description=(
            "Fires when CS amends an order inquiry row that already has a purchase order "
            "or SPO linked to it (event-driven, dispatched when the row settles). A row "
            "with no links yet fires nothing."
        ),
        config_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    _trigger_order_inquiry_changed_with_links,
)


def _trigger_sponsorship_form_approved(
    db: Session,
    config: dict[str, Any],
    timezone: str,
) -> Iterable[TriggerMatch]:
    """Event-driven; pull-mode evaluation yields nothing.

    Matches are produced via :meth:`AutomationService.dispatch_event` from the
    sponsorship form approval code path (shares the purchase_requests table).
    """
    return []


register(
    TriggerSpec(
        type="sponsorship_form_approved",
        label="Sponsorship form approved",
        description="Fires when a sponsorship form is approved (event-driven, dispatched from the approval flow).",
        config_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    _trigger_sponsorship_form_approved,
)
