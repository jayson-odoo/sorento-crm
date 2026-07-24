"""Trigger registry for automations.

A trigger turns an automation row into a list of {context} payloads, one per
match. The first concrete trigger watches promotion expiry: ``X days before
promotion end``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models.marketing import Promotion


@dataclass(frozen=True)
class TriggerSpec:
    type: str
    label: str
    description: str
    config_schema: dict[str, Any]
    # Rule-engine fact sources this trigger exposes. Empty = no rule filtering
    # (conditions_json is ignored). days_before_promotion_end → ("promotion",).
    fact_sources: tuple[str, ...] = ()


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
    ),
    _trigger_days_before_promotion_end,
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
