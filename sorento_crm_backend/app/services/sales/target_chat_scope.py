"""Who sees which sales target in chat (SALES-TARGET-CHAT, UAC T1).

A dealer sees the dealer targets whose EVERY counted account is a customer linked to the
contact. A salesperson sees their own agent targets, the team targets of teams they belong to
today, and the dealer targets whose EVERY counted account is owned by one of their agents.
Staff and unclassified contacts see nothing. Targets are read through the session's company
scope, narrowed again to the contact's own companies.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import RespondContactCompany
from app.models.order import Customer, SalesOrder
from app.models.sales import SalesTarget, SalesTargetAccount, SalesTargetPeriod
from app.services.error_handler import AppException
from app.services.sales import team_service
from app.services.sales import target_service as ts


def _forbidden(message: str, code: str) -> AppException:
    return AppException(status_code=403, message=message, code=code)


def _targets(db: Session, company_ids: Set[str], date_from: date, date_to: date, **filters) -> List[SalesTarget]:
    overlapping = select(SalesTargetPeriod.target_id).where(
        SalesTargetPeriod.period_start <= date_to, SalesTargetPeriod.period_end >= date_from
    )
    q = db.query(SalesTarget).filter(
        SalesTarget.company_id.in_(company_ids), SalesTarget.id.in_(overlapping)
    )
    for column, value in filters.items():
        attr = getattr(SalesTarget, column)
        q = q.filter(attr.in_(value) if isinstance(value, (set, list)) else attr == value)
    return q.all()


def _dealer_targets(
    db: Session, company_ids: Set[str], date_from: date, date_to: date, allowed: Set[str]
) -> List[SalesTarget]:
    """Dealer targets whose every counted account id is in `allowed`."""
    targets = _targets(db, company_ids, date_from, date_to, subject_kind="dealer")
    links: Dict[str, Set[str]] = {}
    if targets:
        for target_id, customer_id in db.query(SalesTargetAccount.target_id, SalesTargetAccount.customer_id).filter(
            SalesTargetAccount.target_id.in_([t.id for t in targets])
        ):
            links.setdefault(target_id, set()).add(str(customer_id))
    return [t for t in targets if links.get(t.id) and links[t.id] <= allowed]


def _as_of(db: Session, company_ids: Set[str], today: date) -> Optional[date]:
    return (
        db.query(func.max(SalesOrder.order_date))
        .filter(SalesOrder.company_id.in_(company_ids), SalesOrder.order_date <= today)
        .scalar()
    )


def _sorted(lines: List[dict]) -> List[dict]:
    return sorted(lines, key=lambda l: (l["period_start"], l["target_no"]))


def _by_gap(lines: List[dict]) -> List[dict]:
    def key(line: dict):
        nxt = line["next_tier"]
        return (nxt is None, nxt["gap"] if nxt else 0, line["subject_label"], line["target_no"])

    return sorted(lines, key=key)


def _user_revoked(db: Session, contact_id: str) -> bool:
    """The contact is linked to a CRM user and none of them is live (ACTIVE, not trashed): the
    revoke rule of the chat report (V1-CHATREPORT-REVOKE). A contact with no user (an agent-only
    salesperson, a dealer) is not revoked."""
    from app.models.user import User

    users = db.query(User.status, User.is_trashed).filter(User.respond_contact_id == str(contact_id)).all()
    return bool(users) and not any(status == "ACTIVE" and not trashed for status, trashed in users)


def contact_company_ids(db: Session, contact_id: str) -> Set[str]:
    from app.models.base import company_scope

    with company_scope(db, None):
        return {
            str(cid)
            for (cid,) in db.query(RespondContactCompany.company_id).filter(
                RespondContactCompany.respond_contact_id == str(contact_id)
            )
        }


def staff_target_progress(
    db: Session,
    *,
    user_id: str,
    date_from: Optional[date],
    date_to: Optional[date],
    customer_ids: Sequence[str],
) -> dict:
    """`target_progress` for a staff member on an identity read (AGENTIC-UNIFY AC-7): a salesperson's
    view of their own agents (through their linked contact), in their active company. No agent is an
    answer with nothing in it, not a refusal."""
    from app.models.base import get_company_scope
    from app.services import own_scope

    scope = get_company_scope(db)
    return target_progress(
        db,
        contact_id=own_scope.me(db, user_id).contact_id,
        date_from=date_from,
        date_to=date_to,
        customer_ids=customer_ids,
        staff_companies={str(c) for c in scope} if isinstance(scope, frozenset) else set(),
    )


def target_progress(
    db: Session,
    *,
    contact_id: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    customer_ids: Sequence[str],
    staff_companies: Optional[Set[str]] = None,
) -> dict:
    from app.services.contact_asker import classify
    from app.services.contact_customer_scope import contact_customer_scope
    from app.services.sales.portal_agent import agents_for_contact

    today = team_service._today()
    date_from = date_from or date_to or today
    date_to = date_to or date_from
    if staff_companies is not None:
        asker = "salesperson"
    else:
        asker = classify(db, contact_id)
        if _user_revoked(db, contact_id):
            asker = "revoked"
    if asker not in ("dealer", "salesperson"):
        raise _forbidden("Sales targets are not available for this contact.", "sales_target_not_available")

    company_ids = staff_companies if staff_companies is not None else contact_company_ids(db, contact_id)
    named = {str(c) for c in customer_ids}
    own: List[SalesTarget] = []
    team: List[SalesTarget] = []
    if asker == "dealer":
        allowed = {str(c) for c in contact_customer_scope(db, contact_id).customer_ids}
        dealers = _dealer_targets(db, company_ids, date_from, date_to, allowed) if company_ids else []
    else:
        agents = agents_for_contact(db, contact_id) if contact_id else []
        agent_ids = {a.id for a in agents}
        owned: Set[str] = set()
        if agent_ids:
            owned = {
                str(cid)
                for (cid,) in db.query(Customer.id).filter(Customer.sales_agent_id.in_(agent_ids))
            }
        allowed = owned
        dealers = _dealer_targets(db, company_ids, date_from, date_to, owned) if company_ids and owned else []
        if agent_ids and company_ids and not named:
            own = _targets(db, company_ids, date_from, date_to, subject_kind="agent", sales_agent_id=agent_ids)
            team_ids = {
                m.sales_team_id for m, _t in ts._covering_on(db, today) if m.sales_agent_id in agent_ids
            }
            if team_ids:
                team = _targets(db, company_ids, date_from, date_to, subject_kind="team", sales_team_id=team_ids)

    if named:
        if not named <= allowed:
            raise _forbidden("I can only share targets for your own accounts.", "customer_not_permitted")
        counted: Dict[str, Set[str]] = {}
        if dealers:
            for target_id, customer_id in db.query(SalesTargetAccount.target_id, SalesTargetAccount.customer_id).filter(
                SalesTargetAccount.target_id.in_([t.id for t in dealers])
            ):
                counted.setdefault(target_id, set()).add(str(customer_id))
        dealers = [t for t in dealers if counted.get(t.id, set()) & named]

    lines = {
        "own": ts.period_progress(db, own, date_from=date_from, date_to=date_to),
        "team": ts.period_progress(db, team, date_from=date_from, date_to=date_to),
        "dealers": ts.period_progress(db, dealers, date_from=date_from, date_to=date_to),
    }
    shown = {t.company_id for t in [*own, *team, *dealers]} or company_ids
    return {
        "asker": asker,
        "as_of": _as_of(db, shown, today) if shown else None,
        "window": {"date_from": date_from, "date_to": date_to},
        "narrowed": bool(named),
        "own": _sorted(lines["own"]),
        "team": _sorted(lines["team"]),
        "dealers": _by_gap(lines["dealers"]),
    }
