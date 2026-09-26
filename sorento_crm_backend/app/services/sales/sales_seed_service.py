"""Seeds the Sales module's configurable defaults (plan 3.4, 3.7; slice S2).

Same shape as `app.services.project_seed_service`: additive and idempotent. It never
updates or deletes a row an admin has since changed - a renamed "Won" or a deactivated
stage survives every restart (the "wholesale guard": skipped once ANY default-scope row
for the entity exists).
"""
from __future__ import annotations

import uuid
from typing import Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption, LookupSet
from app.models.numbering import DocumentNumberingRule
from app.models.status import Status, StatusTransition

SALES_OPPORTUNITY_ENTITY = "sales_opportunity"
LOST_REASON_SET_KEY = "sales_opportunity_lost_reasons"

OPPORTUNITY_NUMBERING = {
    "doc_type": "sales_opportunity",
    "prefix_template": "OPP-",
    "number_digits": 6,
    "start_value": 1,
}

# The default funnel (plan 3.4; owner ruling 26 Sep, G5): New -> Qualified -> Proposal ->
# Negotiation -> Won/Lost. Proposal starts INACTIVE ("not so applicable for retail
# trading, but configurable") - an admin turns it on in System > Status Graphs with no
# code change (S2-2).
#
# (key, label, win_probability, is_initial, is_terminal, is_active)
DEFAULT_OPPORTUNITY_STATUSES = (
    ("new", "New", 10, True, False, True),
    ("qualified", "Qualified", 25, False, False, True),
    ("proposal", "Proposal", 50, False, False, False),
    ("negotiation", "Negotiation", 75, False, False, True),
    ("won", "Won", 100, False, True, True),
    ("lost", "Lost", 0, False, True, True),
)

_LIVE = ("new", "qualified", "proposal", "negotiation")

# Every live stage to the next live stage, back one step, and every live stage to Won
# and to Lost (section 16). Deliberately not a fully-connected graph, the same reasoning
# the project funnel gives: an illegal move being rejected is the point of a configurable
# graph, not a bug in it.
DEFAULT_OPPORTUNITY_EDGES = (
    ("new", "qualified", "Qualify"),
    ("qualified", "proposal", "Send proposal"),
    ("proposal", "negotiation", "Negotiate"),
    ("qualified", "negotiation", "Negotiate"),
    ("qualified", "new", "Back to New"),
    ("proposal", "qualified", "Back to Qualified"),
    ("negotiation", "proposal", "Back to Proposal"),
    ("negotiation", "qualified", "Back to Qualified"),
)

DEFAULT_LOST_REASONS = (
    ("price", "Price"),
    ("competitor", "Went to competitor"),
    ("project_cancelled", "Project cancelled"),
    ("no_response", "No response"),
    ("other", "Other"),
)


def _uid() -> str:
    return str(uuid.uuid4())


def seed_opportunity_numbering_rule(db: Session) -> bool:
    """``OPP-000001`` upward. Also inserted by migration `sales_0003_opportunities`;
    both check "when absent", so running either first is safe."""
    existing = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == OPPORTUNITY_NUMBERING["doc_type"])
        .first()
    )
    if existing:
        return False
    db.add(
        DocumentNumberingRule(
            id=_uid(),
            doc_type=OPPORTUNITY_NUMBERING["doc_type"],
            enabled=True,
            prefix_template=OPPORTUNITY_NUMBERING["prefix_template"],
            number_digits=OPPORTUNITY_NUMBERING["number_digits"],
            next_value=OPPORTUNITY_NUMBERING["start_value"],
            start_value=OPPORTUNITY_NUMBERING["start_value"],
            reset_policy="none",
        )
    )
    db.flush()
    return True


def seed_default_opportunity_graph(db: Session) -> int:
    """The graph for ``sales_opportunity`` (S2-1). No scoped variants: one funnel per
    install, same as the project lead funnel."""
    already = (
        db.query(func.count(Status.id))
        .filter(Status.entity_type == SALES_OPPORTUNITY_ENTITY, Status.scope_id.is_(None))
        .scalar()
    )
    if already:
        return 0

    by_key: Dict[str, Status] = {}
    for index, (key, label, probability, initial, terminal, active) in enumerate(
        DEFAULT_OPPORTUNITY_STATUSES
    ):
        row = Status(
            id=_uid(),
            entity_type=SALES_OPPORTUNITY_ENTITY,
            scope_id=None,
            key=key,
            label=label,
            sort_order=index,
            is_initial=initial,
            is_terminal=terminal,
            is_default=initial,
            is_active=active,
            win_probability=probability,
        )
        db.add(row)
        by_key[key] = row
    db.flush()

    for from_key, to_key, label in DEFAULT_OPPORTUNITY_EDGES:
        db.add(
            StatusTransition(
                id=_uid(),
                entity_type=SALES_OPPORTUNITY_ENTITY,
                scope_id=None,
                from_status_id=by_key[from_key].id,
                to_status_id=by_key[to_key].id,
                label=label,
                trigger_mode="manual",
            )
        )
    for from_key in _LIVE:
        for to_key, label in (("won", "Mark won"), ("lost", "Mark lost")):
            db.add(
                StatusTransition(
                    id=_uid(),
                    entity_type=SALES_OPPORTUNITY_ENTITY,
                    scope_id=None,
                    from_status_id=by_key[from_key].id,
                    to_status_id=by_key[to_key].id,
                    label=label,
                    trigger_mode="manual",
                )
            )
    db.flush()
    return len(by_key)


def seed_opportunity_lost_reasons(db: Session) -> int:
    """The lost-reason lookup set (S2-1), on the same generic machinery as the project
    lead's disqualify reasons - an admin already has a screen to edit these."""
    existing = db.query(LookupSet).filter(LookupSet.set_key == LOST_REASON_SET_KEY).first()
    if existing:
        return 0

    lookup_set = LookupSet(
        id=_uid(),
        set_key=LOST_REASON_SET_KEY,
        name="Sales opportunity lost reasons",
        description=(
            "Why a sales opportunity was lost. Required when an opportunity moves to Lost."
        ),
    )
    db.add(lookup_set)
    db.flush()
    for order, (value, label) in enumerate(DEFAULT_LOST_REASONS):
        db.add(
            LookupOption(
                id=_uid(),
                set_id=lookup_set.id,
                value=value,
                label=label,
                sort_order=order,
            )
        )
    db.flush()
    return len(DEFAULT_LOST_REASONS)


def run(db: Session) -> Dict[str, int]:
    """Seed everything the Sales module needs on day one. Safe to call on every boot."""
    summary: Dict[str, int] = {
        "numbering": 0,
        "opportunity_statuses": 0,
        "opportunity_lost_reasons": 0,
    }
    summary["numbering"] = 1 if seed_opportunity_numbering_rule(db) else 0
    summary["opportunity_statuses"] = seed_default_opportunity_graph(db)
    summary["opportunity_lost_reasons"] = seed_opportunity_lost_reasons(db)
    return summary
