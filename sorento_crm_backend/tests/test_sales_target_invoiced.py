"""TARGET-INVOICED: a sales target can count Invoiced (owner, 4 Nov 2026).

Plan: `documentation/plans/sales/PLAN-target-invoiced-04nov.md`. Invoiced achievement is the
27 Oct sales definition (IV + CS + DN - CN, `local_net_total`, by DocDate, cancelled excluded),
read through the one shared sales service (`app/services/sales/invoiced_sales.py`).

Postgres only (`tests/_pg_fixture.blank_session`); every row is seeded here, CI has none.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from tests._sales_unified_seed import agent, cust, doc, line  # noqa: F401  (imports app.main first)
from app.models.base import set_company_scope
from app.models.finance import BillingDocument
from app.models.sales import (
    SalesTarget,
    SalesTargetAccount,
    SalesTargetPeriod,
    SalesTargetScope,
    SalesTeam,
    SalesTeamMember,
)
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.sales import invoiced_sales
from app.services.sales import target_service
from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session

D = Decimal
_SEQ = itertools.count(1)
Q1 = (date(2026, 1, 1), date(2026, 3, 31))
Q2 = (date(2026, 4, 1), date(2026, 6, 30))


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


def _uid() -> str:
    return str(uuid.uuid4())


def _target(db, kind, *, agent_row=None, team=None, accounts=(), metric="amount",
            basis="invoiced", periods=(Q1, Q2), scope="all", products=()):
    n = next(_SEQ)
    row = SalesTarget(
        id=_uid(), company_id=DEFAULT_COMPANY_ID, target_no=f"TGT-9{n:05d}", name=f"ZZT inv {n}",
        subject_kind=kind, sales_agent_id=agent_row.id if agent_row else None,
        sales_team_id=team.id if team else None, metric=metric, basis=basis,
        product_scope=scope, start_date=periods[0][0], end_date=periods[-1][1],
        commission_method="none", threshold_unit="pct", rounding="sen", tiers_per_period=False,
    )
    db.add(row)
    db.flush()
    for start, end in periods:
        db.add(SalesTargetPeriod(
            id=_uid(), company_id=DEFAULT_COMPANY_ID, target_id=row.id, period_start=start,
            period_end=end, target_value=D("100000"),
        ))
    for order, customer in enumerate(accounts):
        db.add(SalesTargetAccount(
            id=_uid(), company_id=DEFAULT_COMPANY_ID, target_id=row.id, customer_id=customer.id,
            sort_order=order,
        ))
    for prod in products:
        db.add(SalesTargetScope(
            id=_uid(), company_id=DEFAULT_COMPANY_ID, target_id=row.id, product_id=prod.id,
        ))
    db.flush()
    return row


def _pairs(db, target):
    periods = (
        db.query(SalesTargetPeriod)
        .filter(SalesTargetPeriod.target_id == target.id)
        .order_by(SalesTargetPeriod.period_start)
        .all()
    )
    return [(target, p) for p in periods]


def _achieved(db, target):
    """[(period_start, achieved)] in period order, through the target screens' own path."""
    pairs = _pairs(db, target)
    by_period = target_service._achieved_by_account(db, DEFAULT_COMPANY_ID, pairs)
    return [(p.period_start, sum(by_period[p.id].values(), D("0"))) for _, p in pairs]


def _by_account(db, target, period_start):
    pairs = _pairs(db, target)
    by_period = target_service._achieved_by_account(db, DEFAULT_COMPANY_ID, pairs)
    period = next(p for _, p in pairs if p.period_start == period_start)
    return by_period[period.id]


def _shared_total(db, customers, start, end):
    """The shared sales service's own total for these accounts over [start, end]."""
    return D(db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(invoiced_sales.signed_amount()), 0)).where(
            invoiced_sales.posted(),
            BillingDocument.company_id == DEFAULT_COMPANY_ID,
            BillingDocument.customer_id.in_([c.id for c in customers]),
            BillingDocument.doc_date.between(start, end),
        )
    ).scalar())


def _seed_dealer_docs(db):
    """Two accounts of one dealer, one stranger, IV + CS + DN + CN across Q1 and Q2."""
    a1, a2, other = cust(db), cust(db), cust(db)
    iv = doc(db, "invoice", "1000.00", date(2026, 1, 15), customer=a1)
    doc(db, "cash_sale", "250.50", date(2026, 2, 1), customer=a2)
    doc(db, "debit_note", "40.25", date(2026, 3, 31), customer=a1, against=iv)
    doc(db, "credit_note", "100.00", date(2026, 3, 1), customer=a1, against=iv)
    # Cancelled: never counts.
    doc(db, "invoice", "9999.00", date(2026, 2, 2), customer=a1, status="cancelled")
    # DocDate decides the period: 1 Apr is Q2.
    doc(db, "invoice", "500.00", date(2026, 4, 1), customer=a2)
    doc(db, "credit_note", "75.00", date(2026, 5, 5), customer=a2)
    # Another account's sale: never this dealer's.
    doc(db, "invoice", "7777.00", date(2026, 1, 20), customer=other)
    return a1, a2, other


def test_dealer_invoiced_amount_equals_shared_sales_total(db):
    a1, a2, _ = _seed_dealer_docs(db)
    target = _target(db, "dealer", accounts=(a1, a2))

    got = _achieved(db, target)

    # Q1: 1000 + 250.50 + 40.25 - 100 = 1190.75 ; Q2: 500 - 75 = 425
    assert got == [(Q1[0], D("1190.75")), (Q2[0], D("425.00"))]
    assert got[0][1] == _shared_total(db, (a1, a2), *Q1)
    assert got[1][1] == _shared_total(db, (a1, a2), *Q2)


def test_dealer_invoiced_split_per_account(db):
    a1, a2, _ = _seed_dealer_docs(db)
    target = _target(db, "dealer", accounts=(a1, a2))

    split = _by_account(db, target, Q1[0])

    assert split == {a1.id: D("940.25"), a2.id: D("250.50")}


def test_agent_invoiced_counts_the_sales_agent_and_label_siblings(db):
    me = agent(db)
    stranger = agent(db)
    c = cust(db)
    doc(db, "invoice", "300.00", date(2026, 2, 10), customer=c, agent_row=me)
    doc(db, "credit_note", "20.00", date(2026, 2, 11), customer=c, agent_row=me)
    doc(db, "invoice", "50.00", date(2026, 2, 12), customer=c, agent_row=me, status="cancelled")
    doc(db, "invoice", "999.00", date(2026, 2, 12), customer=c, agent_row=stranger)
    target = _target(db, "agent", agent_row=me)

    assert _achieved(db, target) == [(Q1[0], D("280.00")), (Q2[0], D("0"))]


def test_team_invoiced_counts_member_docs_inside_their_stay(db):
    member = agent(db)
    team = SalesTeam(id=_uid(), company_id=DEFAULT_COMPANY_ID, name="ZZT inv team", is_active=True)
    db.add(team)
    db.flush()
    db.add(SalesTeamMember(
        id=_uid(), company_id=DEFAULT_COMPANY_ID, sales_team_id=team.id, sales_agent_id=member.id,
        valid_from=date(2026, 2, 1), valid_to=None,
    ))
    db.flush()
    c = cust(db)
    doc(db, "invoice", "100.00", date(2026, 1, 31), customer=c, agent_row=member)  # before stay
    doc(db, "invoice", "200.00", date(2026, 2, 1), customer=c, agent_row=member)
    target = _target(db, "team", team=team)

    assert _achieved(db, target)[0] == (Q1[0], D("200.00"))


def test_invoiced_quantity_nets_credit_note_quantity(db):
    a1 = cust(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    iv = doc(db, "invoice", "500.00", date(2026, 1, 5), customer=a1,
             lines=[line(net="500.00", qty="10", prod=p)])
    doc(db, "credit_note", "100.00", date(2026, 1, 9), customer=a1, against=iv,
        lines=[line(net="100.00", qty="2", prod=p)])
    doc(db, "invoice", "50.00", date(2026, 1, 6), customer=a1, status="cancelled",
        lines=[line(net="50.00", qty="1", prod=p)])
    target = _target(db, "dealer", accounts=(a1,), metric="quantity")

    assert _achieved(db, target)[0] == (Q1[0], D("8"))


def test_invoiced_amount_with_product_scope_counts_in_scope_lines(db):
    a1 = cust(db)
    p_in, p_out = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=DEFAULT_COMPANY_ID)
    doc(db, "invoice", "700.00", date(2026, 1, 5), customer=a1, rate="1",
        lines=[line(net="400.00", qty="1", prod=p_in), line(net="300.00", qty="1", prod=p_out)])
    doc(db, "credit_note", "50.00", date(2026, 1, 7), customer=a1,
        lines=[line(net="50.00", qty="1", prod=p_in)])
    target = _target(db, "dealer", accounts=(a1,), scope="products", products=(p_in,))

    assert _achieved(db, target)[0] == (Q1[0], D("350.00"))


def test_other_company_documents_never_count(db):
    from app.models.company import Company

    other_company = Company(id=_uid(), name="ZZT other co", code="ZZTOC" + uuid.uuid4().hex[:4])
    db.add(other_company)
    db.flush()
    a1 = cust(db)
    doc(db, "invoice", "100.00", date(2026, 1, 5), customer=a1)
    doc(db, "invoice", "900.00", date(2026, 1, 5), customer=a1, company_id=other_company.id)
    target = _target(db, "dealer", accounts=(a1,))

    assert _achieved(db, target)[0] == (Q1[0], D("100.00"))


def test_mixed_batch_keeps_ordered_and_invoiced_apart(db):
    """One screen shows an Ordered and an Invoiced target together: each counts its own basis."""
    a1 = cust(db)
    doc(db, "invoice", "120.00", date(2026, 1, 5), customer=a1)
    invoiced = _target(db, "dealer", accounts=(a1,))
    ordered = _target(db, "dealer", accounts=(a1,), basis="ordered")
    pairs = _pairs(db, invoiced) + _pairs(db, ordered)

    by_period = target_service._achieved_by_account(db, DEFAULT_COMPANY_ID, pairs)

    first = {t.id: p.id for t, p in pairs if p.period_start == Q1[0]}
    assert sum(by_period[first[invoiced.id]].values(), D("0")) == D("120.00")
    assert sum(by_period[first[ordered.id]].values(), D("0")) == D("0")


def test_counts_label_reads_invoiced(db):
    assert target_service.counts_label(db, "invoiced", DEFAULT_COMPANY_ID) == "Invoiced"


def test_schema_accepts_invoiced_basis():
    from app.schemas.sales import SalesTargetCreate

    fields = SalesTargetCreate.model_fields
    assert "invoiced" in str(fields["basis"].annotation)


def test_database_accepts_invoiced_basis(db):
    a1 = cust(db)
    target = _target(db, "dealer", accounts=(a1,))
    db.refresh(target)
    assert target.basis == "invoiced"


def test_chat_progress_line_counts_invoiced_and_is_not_provisional(db, monkeypatch):
    """The chatbot's target answer (`period_progress`): an Invoiced dealer target reads the
    billing figure, final and net of tax, so it is never labelled provisional."""
    monkeypatch.setattr(target_service, "_today", lambda: date(2026, 2, 15))
    a1, a2, _ = _seed_dealer_docs(db)
    invoiced = _target(db, "dealer", accounts=(a1, a2))
    ordered = _target(db, "dealer", accounts=(a1, a2), basis="ordered")

    lines = target_service.period_progress(
        db, [invoiced, ordered], date_from=Q1[0], date_to=Q1[1]
    )

    by_no = {line["target_no"]: line for line in lines}
    assert by_no[invoiced.target_no]["achieved_value"] == 1190.75
    assert by_no[invoiced.target_no]["provisional"] is False
    assert by_no[ordered.target_no]["provisional"] is True
