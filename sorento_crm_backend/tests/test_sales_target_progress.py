"""Phase 2 RED tests - `GET /api/v1/sales/target-progress`, UAC T1 (who sees which target)
and T2 (what each target line holds) of lane SALES-TARGET-CHAT, slice 1.

Contract: `documentation/plans/sales/PLAN-sales-target-chat-25oct.md`, "Slice 1 design" /
"Contract (route response ...)". UAC: `sales-target-chat-25oct-acceptance-criteria.md`.

Every assertion goes through the HTTP route with the API-key principal (the act-as user holds
`sales.reports.view`, patched as `tests/test_sales_analysis_route.py` does). No implementation
symbol is imported at module level, so a missing route fails each test on its own (404).
Postgres only (`tests/_pg_fixture.blank_session`); every row is seeded here, CI has none.
"Today" is pinned to 25 Oct 2026 through `team_service._today`.
"""
from __future__ import annotations

import itertools
import json
import re
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact, RespondContactCustomer
from app.models.base import set_company_scope
from app.models.company import RespondContactCompany
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.sales import (
    SalesOpportunity,
    SalesPointRatio,
    SalesTarget,
    SalesTargetAccount,
    SalesTargetCommissionTier,
    SalesTargetPeriod,
    SalesTargetTierRate,
    SalesTeam,
    SalesTeamMember,
)
from app.models.sales_agent import SalesAgent
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests.test_top_selling_report import _access, _link

ROUTE = "/api/v1/sales/target-progress"
SLUG = "sales.reports.view"
GRANT = "sales.sales_target"
TODAY = date(2026, 10, 25)
Q3 = {"date_from": "2026-07-01", "date_to": "2026-09-30"}
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SEQ = itertools.count(1)


def _uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    from app.services.sales import team_service

    monkeypatch.setattr(team_service, "_today", lambda: TODAY)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


@contextmanager
def make_client(db, allow=(SLUG,)):
    from app.services.user_service import UserPermissionService

    user = User(id=_uid(), email=f"{unique_code('A')}@integrations.local", name="Act as", status="ACTIVE")
    db.add(user)
    db.flush()
    principal = {"id": user.id, "email": user.email}

    def _override_db():
        yield db

    async def _scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _scope
    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in allow
    try:
        yield TestClient(app, headers={"X-API-Key": "k"})
    finally:
        UserPermissionService.check_user_has_permission = original
        app.dependency_overrides.clear()


@pytest.fixture
def client(db):
    with make_client(db) as c:
        yield c


# --------------------------------------------------------------------------------- seed helpers


def _contact(db, *, granted=(GRANT,), companies=(DEFAULT_COMPANY_ID,)) -> RespondContact:
    from app.services.contact_field_reveal_service import set_granted_keys

    contact = RespondContact(
        id=_uid(), respond_io_id=unique_code("C"), phone_number=f"+6010{uuid.uuid4().hex[:7]}",
        name="ZZT Contact", workspace_id=None,
    )
    db.add(contact)
    db.flush()
    for company_id in companies:
        db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=company_id))
    db.flush()
    if granted:
        set_granted_keys(db, contact.id, list(granted), actor_id=None)
    db.flush()
    return contact


def _me(contact) -> dict:
    return {"contact_id": contact.id, "space_id": "zzt-space"}


def _agent(db, code, *, contact=None, person_label=None, company_id=DEFAULT_COMPANY_ID) -> SalesAgent:
    row = SalesAgent(
        id=_uid(), sales_agent=f"ZZT{code}{next(_SEQ)}", description=f"Agent {code}",
        company_id=company_id, is_active=True, person_label=person_label,
        contact_id=contact.id if contact else None,
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, name, level=None, *, agent=None, company_id=DEFAULT_COMPANY_ID) -> Customer:
    row = Customer(
        id=_uid(), company_id=company_id, customer_code=f"300-{unique_code('C')[-8:]}",
        customer_name=name, account_level=level, sales_agent_id=agent.id if agent else None,
    )
    db.add(row)
    db.flush()
    return row


def _order(db, *, customer=None, agent=None, when, amount, company_id=DEFAULT_COMPANY_ID) -> SalesOrder:
    so = SalesOrder(
        id=_uid(), so_number=unique_code("SO"), order_date=when, status="open", company_id=company_id,
        customer_id=customer.id if customer else None, sales_agent_id=agent.id if agent else None,
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_uid(), sales_order_id=so.id, product_id=product(db, company_id=company_id).id,
        qty_ordered=1, qty_delivered=1, line_total=Decimal(str(amount)), line_status="open",
        company_id=company_id,
    ))
    db.flush()
    return so


def _target(
    db, kind, *, agent=None, team=None, accounts=(), start=date(2026, 10, 1), end=date(2026, 12, 31),
    periods=None, unit="amount", metric="amount", tiers=(), name=None, company_id=DEFAULT_COMPANY_ID,
    value=100000,
) -> SalesTarget:
    """`periods`: [(start, end, value)], default one period of the whole range. `tiers`: dicts
    with `threshold` (amount / points) or `pct`, `rate`, optional `additional`, `account_rates`
    ({customer: rate})."""
    n = next(_SEQ)
    row = SalesTarget(
        id=_uid(), company_id=company_id, target_no=f"TGT-{n:06d}", name=name or f"ZZT Target {n}",
        subject_kind=kind, sales_agent_id=agent.id if agent else None,
        sales_team_id=team.id if team else None, metric=metric, basis="ordered", product_scope="all",
        start_date=start, end_date=end, commission_method="retroactive", threshold_unit=unit,
        rounding="sen", tiers_per_period=False,
    )
    db.add(row)
    db.flush()
    for p_start, p_end, p_value in periods or [(start, end, value)]:
        db.add(SalesTargetPeriod(
            id=_uid(), company_id=company_id, target_id=row.id, period_start=p_start, period_end=p_end,
            target_value=Decimal(str(p_value)),
        ))
    for order, customer in enumerate(accounts):
        db.add(SalesTargetAccount(
            id=_uid(), company_id=company_id, target_id=row.id, customer_id=customer.id, sort_order=order,
        ))
    for spec in tiers:
        tier = SalesTargetCommissionTier(
            id=_uid(), company_id=company_id, target_id=row.id,
            from_pct=Decimal(str(spec["pct"])) if "pct" in spec else None,
            threshold=Decimal(str(spec["threshold"])) if "threshold" in spec else None,
            rate=Decimal(str(spec.get("rate", 0))), is_additional=spec.get("additional", False),
        )
        db.add(tier)
        db.flush()
        for customer, rate in (spec.get("account_rates") or {}).items():
            db.add(SalesTargetTierRate(
                id=_uid(), company_id=company_id, tier_id=tier.id, customer_id=customer.id,
                rate=Decimal(str(rate)),
            ))
    db.flush()
    return row


def _dealer_target(db, accounts, **kw) -> SalesTarget:
    return _target(db, "dealer", accounts=accounts, **kw)


AMOUNT_TIERS = [
    {"threshold": 50000, "rate": 3}, {"threshold": 70000, "rate": 4}, {"threshold": 90000, "rate": 5},
]


def _team(db, name, agent, *, valid_from=None, valid_to=None) -> SalesTeam:
    team = SalesTeam(id=_uid(), company_id=DEFAULT_COMPANY_ID, name=name, is_active=True)
    db.add(team)
    db.flush()
    db.add(SalesTeamMember(
        id=_uid(), company_id=DEFAULT_COMPANY_ID, sales_team_id=team.id, sales_agent_id=agent.id,
        valid_from=valid_from, valid_to=valid_to,
    ))
    db.flush()
    return team


def _opportunity(db, agent, amount, close, *, outcome="open") -> SalesOpportunity:
    n = next(_SEQ)
    row = SalesOpportunity(
        id=_uid(), company_id=DEFAULT_COMPANY_ID, opportunity_no=f"OPP-{n:06d}", prospect_name="ZZT Prospect",
        sales_agent_id=agent.id, title=f"ZZT job {n}", outcome=outcome, expected_amount=Decimal(str(amount)),
        expected_close_date=close, source="crm",
    )
    db.add(row)
    db.flush()
    return row


def _dealer_contact(db, *customers, granted=(GRANT,)) -> RespondContact:
    contact = _contact(db, granted=granted)
    for c in customers:
        _link(db, contact, c)
    return contact


def _salesperson_contact(db, code="SP", **agent_kw):
    contact = _contact(db)
    return contact, _agent(db, code, contact=contact, **agent_kw)


def _get(client, contact, **params):
    return client.get(ROUTE, params={**_me(contact), **params})


def _nos(lines) -> list[str]:
    return [line["target_no"] for line in lines]


def _code(resp) -> str | None:
    return resp.json().get("code")


def _walk(node):
    """Every (key, value) pair of a JSON tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


# ===================================================================================== T1


def test_dealer_sees_only_fully_linked_targets(client, db):
    """T1-1."""
    a1 = _customer(db, "ZZT DEALER ONE", 1)
    a3 = _customer(db, "ZZT DEALER ONE", 3)
    foreign = _customer(db, "ZZT RIVAL", 1)
    full = _dealer_target(db, [a1, a3])
    part = _dealer_target(db, [a1])
    mixed = _dealer_target(db, [a1, foreign])
    rival = _dealer_target(db, [foreign])
    contact = _dealer_contact(db, a1, a3)

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["asker"] == "dealer"
    assert sorted(_nos(body["dealers"])) == sorted([full.target_no, part.target_no])
    assert mixed.target_no not in resp.text and rival.target_no not in resp.text


def test_dealer_never_gets_agent_or_team_targets(client, db):
    """T1-2: even when the agent owns the dealer's account."""
    agent = _agent(db, "OWN")
    acct = _customer(db, "ZZT DEALER TWO", 1, agent=agent)
    team = _team(db, "ZZT Team Two", agent, valid_from=date(2026, 1, 1))
    own_t = _target(db, "agent", agent=agent)
    team_t = _target(db, "team", team=team)
    dealer_t = _dealer_target(db, [acct])
    contact = _dealer_contact(db, acct)

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["own"] == [] and body["team"] == []
    assert _nos(body["dealers"]) == [dealer_t.target_no]
    assert own_t.target_no not in resp.text and team_t.target_no not in resp.text


def test_salesperson_gets_own_agent_targets(client, db):
    """T1-3: every agent linked to the contact (label siblings), none of another agent's."""
    contact = _contact(db)
    a1 = _agent(db, "ONE", contact=contact, person_label="ZZT Y")
    a2 = _agent(db, "TWO", contact=contact, person_label="ZZT Y")
    other = _agent(db, "OTHER")
    t1, t2 = _target(db, "agent", agent=a1), _target(db, "agent", agent=a2)
    stranger = _target(db, "agent", agent=other)

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["asker"] == "salesperson"
    assert sorted(_nos(body["own"])) == sorted([t1.target_no, t2.target_no])
    assert stranger.target_no not in resp.text
    assert all(line["subject_kind"] == "agent" for line in body["own"])


def test_salesperson_gets_team_target_by_dated_membership(client, db):
    """T1-4: a team the agent is in on the date; a stay that ended before it does not count."""
    contact, agent = _salesperson_contact(db)
    current = _team(db, "ZZT Current Team", agent, valid_from=date(2026, 1, 1), valid_to=None)
    past = _team(db, "ZZT Past Team", agent, valid_from=date(2025, 1, 1), valid_to=date(2026, 9, 30))
    other_agent = _agent(db, "ELSE")
    foreign = _team(db, "ZZT Foreign Team", other_agent, valid_from=date(2026, 1, 1))
    t_cur, t_past, t_foreign = (_target(db, "team", team=t) for t in (current, past, foreign))

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert _nos(body["team"]) == [t_cur.target_no]
    assert body["team"][0]["subject_kind"] == "team"
    assert body["team"][0]["subject_label"] == "ZZT Current Team"
    assert t_past.target_no not in resp.text and t_foreign.target_no not in resp.text


def test_salesperson_gets_owned_dealer_targets_only(client, db):
    """T1-5: EVERY counted account owned by one of the contact's agents."""
    contact, agent = _salesperson_contact(db)
    rival_agent = _agent(db, "RIVAL")
    c1 = _customer(db, "ZZT OWNED ONE", 1, agent=agent)
    c2 = _customer(db, "ZZT OWNED ONE", 3, agent=agent)
    c3 = _customer(db, "ZZT NOT MINE", 1, agent=rival_agent)
    owned = _dealer_target(db, [c1, c2])
    mixed = _dealer_target(db, [c1, c3])
    foreign = _dealer_target(db, [c3])

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    assert _nos(resp.json()["dealers"]) == [owned.target_no]
    assert mixed.target_no not in resp.text and foreign.target_no not in resp.text


def test_named_customer_narrows_and_foreign_customer_403(client, db):
    """T1-6: customer_ids narrows inside the rules; one outside them is 403 customer_not_permitted."""
    contact, agent = _salesperson_contact(db)
    rival_agent = _agent(db, "RIVAL")
    c1 = _customer(db, "ZZT NAMED ONE", 1, agent=agent)
    c2 = _customer(db, "ZZT NAMED TWO", 1, agent=agent)
    c3 = _customer(db, "ZZT RIVAL LEDGER", 1, agent=rival_agent)
    t_both = _dealer_target(db, [c1, c2])
    t_two = _dealer_target(db, [c2])
    _dealer_target(db, [c3])

    resp = _get(client, contact, customer_ids=[c1.id])
    assert resp.status_code == 200, resp.text
    assert _nos(resp.json()["dealers"]) == [t_both.target_no]
    assert t_two.target_no not in resp.text

    both = _get(client, contact, customer_ids=[c1.id, c2.id])
    assert both.status_code == 200, both.text
    assert sorted(_nos(both.json()["dealers"])) == sorted([t_both.target_no, t_two.target_no])

    refused = _get(client, contact, customer_ids=[c3.id])
    assert refused.status_code == 403, refused.text
    assert _code(refused) == "customer_not_permitted", refused.text
    assert "RIVAL" not in refused.text

    dealer = _dealer_contact(db, c1)
    dealer_refused = _get(client, dealer, customer_ids=[c2.id])
    assert dealer_refused.status_code == 403, dealer_refused.text
    assert _code(dealer_refused) == "customer_not_permitted", dealer_refused.text


def test_staff_and_unclassified_get_no_targets(client, db):
    """T1-7: staff (office access) and an unclassified contact, both granted: 403, no figure."""
    acct = _customer(db, "ZZT ANY DEALER", 1)
    target = _dealer_target(db, [acct], tiers=AMOUNT_TIERS)
    staff = _contact(db)
    _access(db, staff, "Sorento Office")
    nobody = _contact(db)
    for contact in (staff, nobody):
        resp = _get(client, contact)
        assert resp.status_code == 403, resp.text
        assert _code(resp) == "sales_target_not_available", resp.text
        assert target.target_no not in resp.text and "dealers" not in resp.json()


def test_route_requires_sales_target_grant(client, db):
    """T1-8: no `sales.sales_target` grant (none, or only the sales report grant) is 403
    sales_target_not_enabled; the key is registered, default off."""
    from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

    assert (GRANT, "Sales target") in FIELD_REVEAL_KEYS
    acct = _customer(db, "ZZT GATED DEALER", 1)
    target = _dealer_target(db, [acct])
    no_grant = _dealer_contact(db, acct, granted=())
    report_only = _dealer_contact(db, acct, granted=("sales_orders.sales_report",))
    for contact in (no_grant, report_only):
        resp = _get(client, contact)
        assert resp.status_code == 403, resp.text
        assert _code(resp) == "sales_target_not_enabled", resp.text
        assert target.target_no not in resp.text

    granted = _get(client, _dealer_contact(db, acct))
    assert granted.status_code == 200, granted.text


def test_other_company_targets_never_returned(client, db):
    """T1-9: a target of another company is never returned, whatever the links."""
    own_acct = _customer(db, "ZZT SRT DEALER", 1)
    mocha_acct = _customer(db, "ZZT MOCHA DEALER", 1, company_id=MOCHA_ID)
    mocha_agent = _agent(db, "MCH", company_id=MOCHA_ID)
    mine = _dealer_target(db, [own_acct])
    theirs = _dealer_target(db, [mocha_acct], company_id=MOCHA_ID)
    dealer = _dealer_contact(db, own_acct, mocha_acct)

    resp = _get(client, dealer)
    assert resp.status_code == 200, resp.text
    assert _nos(resp.json()["dealers"]) == [mine.target_no]
    assert theirs.target_no not in resp.text

    contact, agent = _salesperson_contact(db)
    owned_mocha = _customer(db, "ZZT MOCHA OWNED", 1, agent=agent, company_id=MOCHA_ID)
    link_target = _dealer_target(db, [owned_mocha], company_id=MOCHA_ID)
    agent_target = _target(db, "agent", agent=mocha_agent, company_id=MOCHA_ID)
    sp = _get(client, contact)
    assert sp.status_code == 200, sp.text
    assert link_target.target_no not in sp.text and agent_target.target_no not in sp.text


@pytest.mark.parametrize("missing", [["contact_id"], ["space_id"], ["contact_id", "space_id"]])
def test_route_contact_and_space_required(client, db, missing):
    """T1-10: either id missing is 422 contact_identity_required."""
    acct = _customer(db, "ZZT IDENT DEALER", 1)
    _dealer_target(db, [acct])
    params = {k: v for k, v in _me(_dealer_contact(db, acct)).items() if k not in missing}
    resp = client.get(ROUTE, params=params)
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "contact_identity_required", resp.text


def test_route_needs_sales_reports_view(db):
    """T1-10: callable with the API key whose act-as user holds `sales.reports.view`; without it, 403."""
    acct = _customer(db, "ZZT PERM DEALER", 1)
    target = _dealer_target(db, [acct])
    contact = _dealer_contact(db, acct)
    with make_client(db, allow=(SLUG,)) as allowed:
        ok = _get(allowed, contact)
        assert ok.status_code == 200, ok.text
        assert _nos(ok.json()["dealers"]) == [target.target_no]
    with make_client(db, allow=()) as denied:
        resp = _get(denied, contact)
        assert resp.status_code == 403, resp.text
        assert target.target_no not in resp.text


# ===================================================================================== T2


def test_default_current_period_and_named_span(client, db):
    """T2-1: default = the period of each live target holding today; a span = periods overlapping it."""
    acct = _customer(db, "ZZT SPAN DEALER", 1)
    quarters = [
        (date(2026, 1, 1), date(2026, 3, 31), 1000), (date(2026, 4, 1), date(2026, 6, 30), 2000),
        (date(2026, 7, 1), date(2026, 9, 30), 3000), (date(2026, 10, 1), date(2026, 12, 31), 4000),
    ]
    quarterly = _dealer_target(db, [acct], start=date(2026, 1, 1), end=date(2026, 12, 31), periods=quarters)
    yearly = _dealer_target(db, [acct], start=date(2026, 1, 1), end=date(2026, 12, 31), value=9000)
    old = _dealer_target(db, [acct], start=date(2025, 1, 1), end=date(2025, 12, 31), value=500)
    contact = _dealer_contact(db, acct)

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["window"] == {"date_from": "2026-10-25", "date_to": "2026-10-25"}
    pairs = {(l["target_no"], l["period_start"], l["period_end"]) for l in body["dealers"]}
    assert pairs == {
        (quarterly.target_no, "2026-10-01", "2026-12-31"), (yearly.target_no, "2026-01-01", "2026-12-31"),
    }
    assert all(l["is_current"] for l in body["dealers"])
    assert old.target_no not in resp.text

    span = _get(client, contact, date_from="2026-06-15", date_to="2026-07-15").json()
    assert span["window"] == {"date_from": "2026-06-15", "date_to": "2026-07-15"}
    got = {(l["target_no"], l["period_start"]) for l in span["dealers"]}
    assert got == {
        (quarterly.target_no, "2026-04-01"), (quarterly.target_no, "2026-07-01"),
        (yearly.target_no, "2026-01-01"),
    }
    assert {l["is_current"] for l in span["dealers"]} == {False}


def test_replaced_target_listed(client, db):
    """T2-2: a target with `replaced_by_target_id` is listed like any other."""
    a1, a3 = _customer(db, "ZZT REPL DEALER", 1), _customer(db, "ZZT REPL DEALER", 3)
    replaced = _dealer_target(db, [a1])
    replacing = _dealer_target(db, [a1, a3])
    replaced.replaced_by_target_id = replacing.id
    db.flush()
    contact = _dealer_contact(db, a1, a3)

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    assert sorted(_nos(resp.json()["dealers"])) == sorted([replaced.target_no, replacing.target_no])


def test_achieved_matches_target_detail(client, db):
    """T2-3: the engine's own figure, the one the CRM target page shows."""
    from app.services.sales import target_service

    a1 = _customer(db, "ZZT ACH DEALER", 1)
    target = _dealer_target(db, [a1], tiers=AMOUNT_TIERS, unit="amount", value=90000)
    _order(db, customer=a1, when=date(2026, 10, 5), amount="10000.50")
    _order(db, customer=a1, when=date(2026, 10, 20), amount="7413.55")
    contact = _dealer_contact(db, a1)

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    line = resp.json()["dealers"][0]
    assert line["achieved_value"] == 17414.05
    detail = target_service.target_detail(db, target, on=TODAY)
    assert line["achieved_value"] == detail["periods"][0]["achieved_value"]


def _bkin_q3(db, *, unit, tiers, value, orders=("30000.00", "17407.44")):
    acct = _customer(db, "BKIN ELECTRICAL SDN BHD", 1)
    target = _dealer_target(
        db, [acct], start=date(2026, 7, 1), end=date(2026, 9, 30), unit=unit, tiers=tiers, value=value,
    )
    for i, amount in enumerate(orders):
        _order(db, customer=acct, when=date(2026, 8, 1 + i), amount=amount)
    return acct, target


def test_next_tier_gap_amount_tiers(client, db):
    """T2-4: achieved 47,407.44 vs 50,000 3% / 70,000 4% / 90,000 5% -> next tier 1, gap 2,592.56."""
    acct, target = _bkin_q3(db, unit="amount", tiers=AMOUNT_TIERS, value=90000)
    resp = _get(client, _dealer_contact(db, acct), **Q3)
    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["dealers"]
    assert line["target_no"] == target.target_no
    assert line["achieved_value"] == 47407.44
    assert line["tier_reached"] is None
    assert line["next_tier"] == {
        "tier": 1, "threshold": 50000.0, "threshold_points": None,
        "rates": [{"label": None, "rate": 3.0}], "additional_rates": [], "gap": 2592.56,
    }


def test_next_tier_gap_pct_tiers(client, db):
    """T2-4: pct tiers resolve to % x the period target (50% of 100,000 = 50,000)."""
    pct = [{"pct": 50, "rate": 3}, {"pct": 70, "rate": 4}, {"pct": 90, "rate": 5}]
    acct, _target_row = _bkin_q3(db, unit="pct", tiers=pct, value=100000)
    resp = _get(client, _dealer_contact(db, acct), **Q3)
    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["dealers"]
    assert line["target_value"] == 100000.0
    assert line["tier_reached"] is None
    assert line["next_tier"] == {
        "tier": 1, "threshold": 50000.0, "threshold_points": None,
        "rates": [{"label": None, "rate": 3.0}], "additional_rates": [], "gap": 2592.56,
    }


def test_tier_reached_and_top_tier(client, db):
    """T2-5: highest tier at or below achieved (with its additional rate); above the top: no next."""
    tiers = AMOUNT_TIERS + [{"threshold": 70000, "rate": 1, "additional": True}]
    acct, _t = _bkin_q3(db, unit="amount", tiers=tiers, value=90000, orders=("45000.00", "30000.00"))
    (mid,) = _get(client, _dealer_contact(db, acct), **Q3).json()["dealers"]
    assert mid["achieved_value"] == 75000.0
    assert mid["tier_reached"]["tier"] == 2
    assert mid["tier_reached"]["threshold"] == 70000.0
    assert mid["tier_reached"]["rates"] == [{"label": None, "rate": 4.0}]
    assert [r["rate"] for r in mid["tier_reached"]["additional_rates"]] == [1.0]
    assert mid["next_tier"]["tier"] == 3 and mid["next_tier"]["gap"] == 15000.0

    acct2, _t2 = _bkin_q3(db, unit="amount", tiers=AMOUNT_TIERS, value=90000, orders=("60000.00", "35000.00"))
    (top,) = _get(client, _dealer_contact(db, acct2), **Q3).json()["dealers"]
    assert top["achieved_value"] == 95000.0
    assert top["tier_reached"]["tier"] == 3
    assert top["tier_reached"]["rates"] == [{"label": None, "rate": 5.0}]
    assert top["next_tier"] is None


def test_no_incentive_amount_in_response(client, db):
    """T2-6: no RM incentive / rebate / commission anywhere (key names or the 4% of 75,000 = 3,000)."""
    acct, _t = _bkin_q3(db, unit="amount", tiers=AMOUNT_TIERS, value=90000, orders=("45000.00", "30000.00"))
    resp = _get(client, _dealer_contact(db, acct), **Q3)
    assert resp.status_code == 200, resp.text
    pairs = list(_walk(resp.json()))
    assert pairs, "empty body proves nothing"
    banned = ("commission", "incentive", "rebate", "payout", "bonus", "earned")
    assert [k for k, _ in pairs if any(b in k.lower() for b in banned)] == []
    numbers = [v for _, v in pairs if isinstance(v, (int, float)) and not isinstance(v, bool)]
    assert 3000.0 not in numbers and 3000 not in numbers
    assert 75000.0 in numbers


def test_points_target_with_and_without_ratio(client, db):
    """T2-7: points thresholds in RM at the ratio in force on the period's last day; no ratio ->
    ratio_missing, the target in points, no tier, next tier or gap."""
    acct = _customer(db, "BKIN ELECTRICAL SDN BHD", 1)
    q3 = (date(2026, 7, 1), date(2026, 9, 30), 25000)
    q4 = (date(2026, 10, 1), date(2026, 12, 31), 25000)
    _dealer_target(
        db, [acct], start=date(2026, 7, 1), end=date(2026, 12, 31), unit="points",
        periods=[q3, q4], tiers=[{"threshold": 25000, "rate": 4}],
    )
    for effective, rm in ((date(2026, 10, 1), "2.0"), (date(2027, 1, 1), "9.0")):
        db.add(SalesPointRatio(
            id=_uid(), company_id=DEFAULT_COMPANY_ID, effective_from=effective, rm_per_point=Decimal(rm),
        ))
    _order(db, customer=acct, when=date(2026, 8, 10), amount="22140.48")
    _order(db, customer=acct, when=date(2026, 10, 10), amount="1000.00")
    db.flush()

    resp = _get(client, _dealer_contact(db, acct), date_from="2026-07-01", date_to="2026-12-31")
    assert resp.status_code == 200, resp.text
    by_start = {l["period_start"]: l for l in resp.json()["dealers"]}

    missing = by_start["2026-07-01"]
    assert missing["ratio_missing"] is True
    assert missing["target_value"] is None and missing["target_points"] == 25000.0
    assert missing["achieved_value"] == 22140.48
    assert missing["tier_reached"] is None and missing["next_tier"] is None

    ok = by_start["2026-10-01"]
    assert ok["ratio_missing"] is False
    assert ok["target_value"] == 50000.0
    assert ok["achieved_value"] == 1000.0
    assert ok["next_tier"]["tier"] == 1
    assert ok["next_tier"]["threshold"] == 50000.0
    assert ok["next_tier"]["threshold_points"] == 25000.0
    assert ok["next_tier"]["gap"] == 49000.0


def test_rate_per_account_label(client, db):
    """T2-7b: a per-account tier shows its rate per account label; a one-rate tier shows label null."""
    a1, a3 = _customer(db, "ZZT PERACC DEALER", 1), _customer(db, "ZZT PERACC DEALER", 3)
    tiers = [
        {"threshold": 50000, "rate": 0, "account_rates": {a1: 3}},
        {"threshold": 70000, "rate": 4},
    ]
    _dealer_target(
        db, [a1, a3], start=date(2026, 7, 1), end=date(2026, 9, 30), unit="amount", tiers=tiers, value=70000,
    )
    _order(db, customer=a1, when=date(2026, 8, 1), amount="40000.00")
    _order(db, customer=a3, when=date(2026, 8, 2), amount="20000.00")
    (line,) = _get(client, _dealer_contact(db, a1, a3), **Q3).json()["dealers"]
    assert line["achieved_value"] == 60000.0
    assert line["tier_reached"]["tier"] == 1
    assert line["tier_reached"]["rates"] == [{"label": "A/C I", "rate": 3.0}]
    assert line["next_tier"]["tier"] == 2
    assert line["next_tier"]["rates"] == [{"label": None, "rate": 4.0}]
    assert line["next_tier"]["gap"] == 10000.0


def test_dealer_line_provisional_and_accounts(client, db):
    """T2-8: provisional + account codes and labels in the order entered; as_of = latest order date
    of the lines' company, not after today."""
    a1, a3 = _customer(db, "ZZT PROV DEALER", 1), _customer(db, "ZZT PROV DEALER", 3)
    _dealer_target(db, [a3, a1], tiers=AMOUNT_TIERS)
    _order(db, customer=a1, when=date(2026, 10, 20), amount="100.00")
    _order(db, customer=a3, when=date(2026, 10, 23), amount="200.00")
    _order(db, customer=a1, when=date(2026, 11, 2), amount="300.00")
    mocha_cust = _customer(db, "ZZT MOCHA BUYER", 1, company_id=MOCHA_ID)
    _order(db, customer=mocha_cust, when=date(2026, 10, 24), amount="1.00", company_id=MOCHA_ID)

    resp = _get(client, _dealer_contact(db, a1, a3))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["as_of"] == "2026-10-23"
    (line,) = body["dealers"]
    assert line["provisional"] is True
    assert line["accounts"] == [
        {"code": a3.customer_code, "label": "A/C III"}, {"code": a1.customer_code, "label": "A/C I"},
    ]
    assert line["company_code"]


def test_agent_line_carries_open_pipeline(client, db):
    """T2-9: open opportunities closing within the target (agent_progress), nothing else."""
    contact, agent = _salesperson_contact(db)
    other = _agent(db, "ELSE")
    _target(db, "agent", agent=agent, value=100000)
    _order(db, agent=agent, when=date(2026, 10, 12), amount="30000.00")
    _opportunity(db, agent, "12000.00", date(2026, 11, 15))
    _opportunity(db, agent, "500.00", date(2026, 12, 31))
    _opportunity(db, agent, "7000.00", date(2027, 2, 1))
    _opportunity(db, agent, "9000.00", date(2026, 11, 20), outcome="won")
    _opportunity(db, other, "4000.00", date(2026, 11, 20))

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    (line,) = body["own"]
    assert line["subject_kind"] == "agent"
    assert line["achieved_value"] == 30000.0
    assert line["pipeline_value"] == 12500.0
    assert body["as_of"] == "2026-10-12"


def test_dealer_block_smallest_gap_first(client, db):
    """T2-10: dealers by gap to the next tier ascending; no next tier last, then by subject_label."""
    contact, agent = _salesperson_contact(db)
    first = _customer(db, "ZZT GAP BIG", 1, agent=agent)
    second = _customer(db, "ZZT GAP SMALL", 1, agent=agent)
    top = _customer(db, "ZZT GAP AAA TOP", 1, agent=agent)
    none = _customer(db, "ZZT GAP BBB NOTIERS", 1, agent=agent)
    t_big = _dealer_target(db, [first], tiers=AMOUNT_TIERS, value=90000)
    t_small = _dealer_target(db, [second], tiers=AMOUNT_TIERS, value=90000)
    t_top = _dealer_target(db, [top], tiers=AMOUNT_TIERS, value=90000)
    t_none = _dealer_target(db, [none], value=90000)
    _order(db, customer=first, when=date(2026, 10, 3), amount="5275.80")
    _order(db, customer=second, when=date(2026, 10, 3), amount="47407.44")
    _order(db, customer=top, when=date(2026, 10, 3), amount="95000.00")
    _order(db, customer=none, when=date(2026, 10, 3), amount="10.00")

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    lines = resp.json()["dealers"]
    assert _nos(lines) == [t_small.target_no, t_big.target_no, t_top.target_no, t_none.target_no]
    assert [l["next_tier"]["gap"] if l["next_tier"] else None for l in lines] == [2592.56, 44724.2, None, None]


def test_response_has_no_ids(client, db):
    """T2-11: no UUID anywhere: subjects by name / code, accounts by code and label."""
    contact, agent = _salesperson_contact(db)
    acct = _customer(db, "ZZT NOID DEALER", 1, agent=agent)
    team = _team(db, "ZZT NoId Team", agent, valid_from=date(2026, 1, 1))
    _target(db, "agent", agent=agent)
    _target(db, "team", team=team)
    _dealer_target(db, [acct], tiers=AMOUNT_TIERS)
    _order(db, customer=acct, agent=agent, when=date(2026, 10, 3), amount="100.00")
    _opportunity(db, agent, "1000.00", date(2026, 11, 1))

    resp = _get(client, contact)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["own"] and body["team"] and body["dealers"]
    text = json.dumps(body)
    assert UUID_RE.findall(text) == []
    assert not [k for k, _ in _walk(body) if k == "id" or k.endswith("_id")]


# ===================================================================================== fix round


def _linked_user(db, contact, *, status="ACTIVE", trashed=False) -> User:
    user = User(
        id=_uid(), email=f"{unique_code('U')}@zzt.test", name="ZZT Linked", status=status,
        is_trashed=trashed, respond_contact_id=contact.id,
    )
    db.add(user)
    db.flush()
    return user


def test_revoked_user_contact_refused(client, db):
    """T1-11: a contact whose linked user is not ACTIVE, or is trashed, is 403
    sales_target_not_available; a salesperson linked only through the agent still gets through."""
    acct = _customer(db, "ZZT REVOKE DEALER", 1)
    target = _dealer_target(db, [acct])
    for status, trashed in (("INACTIVE", False), ("ACTIVE", True)):
        agent_contact, _agent_row = _salesperson_contact(db)
        _linked_user(db, agent_contact, status=status, trashed=trashed)
        dealer_contact = _dealer_contact(db, acct)
        _linked_user(db, dealer_contact, status=status, trashed=trashed)
        for contact in (agent_contact, dealer_contact):
            resp = _get(client, contact)
            assert resp.status_code == 403, (status, trashed, resp.text)
            assert _code(resp) == "sales_target_not_available", resp.text
            assert target.target_no not in resp.text

    agent_only, _row = _salesperson_contact(db)
    ok = _get(client, agent_only)
    assert ok.status_code == 200, ok.text
    assert ok.json()["asker"] == "salesperson"


@pytest.mark.parametrize("blank", ["", "  "])
@pytest.mark.parametrize("field", ["contact_id", "space_id"])
def test_blank_contact_ids_422(client, db, field, blank):
    """T1-12: a blank or whitespace-only id is 422 contact_identity_required."""
    acct = _customer(db, "ZZT BLANK DEALER", 1)
    _dealer_target(db, [acct])
    params = {**_me(_dealer_contact(db, acct)), field: blank}
    resp = client.get(ROUTE, params=params)
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "contact_identity_required", resp.text


def test_pct_tiers_on_zero_target_follow_engine(client, db):
    """T2-12: pct tiers 100% / 120% on a 0 target: only the 100% tier counts as reached."""
    acct = _customer(db, "ZZT ZERO DEALER", 1)
    _dealer_target(
        db, [acct], start=date(2026, 7, 1), end=date(2026, 9, 30), unit="pct", value=0,
        tiers=[{"pct": 100, "rate": 3}, {"pct": 120, "rate": 4}],
    )
    resp = _get(client, _dealer_contact(db, acct), **Q3)
    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["dealers"]
    assert line["tier_reached"]["tier"] == 1
    assert line["next_tier"]["tier"] == 2


def test_rounding_half_up(client, db):
    """T2-13: a figure ending in exactly .xx5 rounds up (0.125 -> 0.13). Order lines are stored
    at 2 decimals, so the tie comes from a pct tier: 50% of a 0.25 target is exactly 0.125."""
    acct = _customer(db, "ZZT ROUND DEALER", 1)
    _dealer_target(
        db, [acct], start=date(2026, 7, 1), end=date(2026, 9, 30), unit="pct", value="0.25",
        tiers=[{"pct": 50, "rate": 3}],
    )
    resp = _get(client, _dealer_contact(db, acct), **Q3)
    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["dealers"]
    assert line["next_tier"]["threshold"] == 0.13
    assert line["next_tier"]["gap"] == 0.13


def test_agent_line_target_end_date(client, db):
    """T2-14: agent lines carry the whole target's end as `target_end_date`; team and dealer null."""
    contact, agent = _salesperson_contact(db)
    team = _team(db, "ZZT End Team", agent, valid_from=date(2026, 1, 1))
    acct = _customer(db, "ZZT END DEALER", 1, agent=agent)
    months = [
        (date(2026, 10, 1), date(2026, 10, 31), 1000), (date(2026, 11, 1), date(2026, 11, 30), 1000),
        (date(2026, 12, 1), date(2026, 12, 31), 1000),
    ]
    _target(db, "agent", agent=agent, periods=months)
    _target(db, "team", team=team, periods=months)
    _dealer_target(db, [acct], periods=months)

    resp = _get(client, contact, date_from="2026-10-01", date_to="2026-12-31")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["own"]) == 3
    assert {l["target_end_date"] for l in body["own"]} == {"2026-12-31"}
    assert body["team"] and all(l["target_end_date"] is None for l in body["team"])
    assert body["dealers"] and all(l["target_end_date"] is None for l in body["dealers"])


def test_response_narrowed_flag(client, db):
    """T2-15: `narrowed` is false with no customer_ids, true with them (own and team then [])."""
    contact, agent = _salesperson_contact(db)
    owned = _customer(db, "ZZT NARROW DEALER", 1, agent=agent)
    _target(db, "agent", agent=agent)
    _dealer_target(db, [owned])

    wide = _get(client, contact)
    assert wide.status_code == 200, wide.text
    assert wide.json()["narrowed"] is False
    assert wide.json()["own"]

    narrow = _get(client, contact, customer_ids=[owned.id])
    assert narrow.status_code == 200, narrow.text
    body = narrow.json()
    assert body["narrowed"] is True
    assert body["own"] == [] and body["team"] == []
    assert len(body["dealers"]) == 1


def test_dealer_subject_label_without_marker(client, db):
    """T2-16: no ledger marker in a dealer's subject_label; a shared customer group keeps its name."""
    from app.models.order import CustomerGroup

    ply1 = _customer(db, "W-PLY HOMEWARE SDN BHD [A/C I]", 1)
    ply3 = _customer(db, "W-PLY HOMEWARE SDN BHD [A/C III]", 3)
    dash = _customer(db, "BKIN ELECTRICAL SDN BHD - [IBORN]")
    g1 = _customer(db, "ZZT GROUPED [A/C I]", 1)
    g3 = _customer(db, "ZZT GROUPED [A/C III]", 3)
    group = CustomerGroup(id=_uid(), company_id=DEFAULT_COMPANY_ID, name="ZZT Group Name")
    db.add(group)
    db.flush()
    g1.customer_group_id = g3.customer_group_id = group.id
    db.flush()
    t_ply = _dealer_target(db, [ply1, ply3])
    t_dash = _dealer_target(db, [dash])
    t_group = _dealer_target(db, [g1, g3])

    resp = _get(client, _dealer_contact(db, ply1, ply3, dash, g1, g3))
    assert resp.status_code == 200, resp.text
    labels = {l["target_no"]: l["subject_label"] for l in resp.json()["dealers"]}
    assert labels[t_ply.target_no] == "W-PLY HOMEWARE SDN BHD"
    assert labels[t_dash.target_no] == "BKIN ELECTRICAL SDN BHD"
    assert labels[t_group.target_no] == "ZZT Group Name"


def test_group_name_with_brackets_kept(client, db):
    """T2-16: a shared customer group's name is kept exactly, brackets included."""
    from app.models.order import CustomerGroup

    a1 = _customer(db, "JUBIN BMS [A/C I]", 1)
    a3 = _customer(db, "JUBIN BMS [A/C III]", 3)
    group = CustomerGroup(id=_uid(), company_id=DEFAULT_COMPANY_ID, name="JUBIN BMS (1990) SDN BHD")
    db.add(group)
    db.flush()
    a1.customer_group_id = a3.customer_group_id = group.id
    db.flush()
    _dealer_target(db, [a1, a3])

    resp = _get(client, _dealer_contact(db, a1, a3))
    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["dealers"]
    assert line["subject_label"] == "JUBIN BMS (1990) SDN BHD"
