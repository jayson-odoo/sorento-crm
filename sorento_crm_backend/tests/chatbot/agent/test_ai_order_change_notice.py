"""OCN-ORDER-CHANGE-NOTICE round 13 (AI-GATE, DoD line 6): the assistant reads order change notices through
the registry, with the list screen's columns in its words, inside the user's company and the notice's own
view rule (`.view` every notice, `.view_own` the ones they raised or are named on, no grant none).

Helpers: the AI-QUERY-CORE suite's. Postgres only, every row seeded.
"""
from __future__ import annotations

import uuid
from datetime import date

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.project_so import OrderChangeNotice, OrderChangeType
from tests.chatbot.agent.test_ai_query_core import (  # noqa: F401  (fixtures by import)
    SORENTO,
    _listeners,
    core,
    db,
    mk_company_b,
    mk_user,
    refusal,
    tag,
)

VIEW = "procurement.order_change_notices.view"
VIEW_OWN = "procurement.order_change_notices.view_own"


def mk_type(db, name="Exchange", risk="High"):
    row = OrderChangeType(id=str(uuid.uuid4()), name=f"ZZT {name}", risk_level=risk, position=99)
    db.add(row)
    db.flush()
    return row


def mk_notice(db, number, *, created_by, company_id=SORENTO, **kw):
    values = dict(
        id=str(uuid.uuid4()),
        company_id=company_id,
        ocn_number=number,
        status="submitted",
        source="crm",
        customer_name="ZZT Customer A",
        customer_po_no="XT04/3871 (R1)",
        ocn_date=date(2026, 11, 13),
        created_by=created_by,
        description="ZZT delivery pushed",
    )
    values.update(kw)
    row = OrderChangeNotice(**values)
    db.add(row)
    db.flush()
    return row


def _numbers(out):
    return {r.get("ocn_number") or r.get("label") for r in out["rows"]}


def test_r13_the_list_columns_read_in_words(db):
    t = tag()
    raiser = mk_user(db)
    kind = mk_type(db)
    mk_notice(db, f"{t}-1", created_by=raiser, change_type_id=kind.id, status="processed_by_cs",
              requested_by="ZZT Requestor A")
    viewer = mk_user(db, VIEW)
    out = core(db, viewer, {
        "entity": "order_change_notice",
        "fields": ["ocn_date", "customer_name", "customer_po_no", "change_type", "risk", "requested_by", "status"],
        "filters": [{"field": "ocn_number", "op": "eq", "value": f"{t}-1"}],
    })
    [row] = out["rows"]
    assert row["change_type"] == "ZZT Exchange"
    assert row["risk"] == "High"
    assert row["requested_by"] == "ZZT Requestor A"
    assert row["status"] == "Done"
    assert row["customer_po_no"] == "XT04/3871 (R1)"
    by_word = core(db, viewer, {
        "entity": "order_change_notice", "fields": ["ocn_number"],
        "filters": [{"field": "status", "op": "eq", "value": "Done"},
                    {"field": "ocn_number", "op": "starts_with", "value": t}],
    })
    assert len(by_word["rows"]) == 1


def test_r13_view_own_reads_only_the_notices_they_raised_or_are_named_on(db):
    t = tag()
    me = mk_user(db, VIEW_OWN)
    other = mk_user(db)
    mk_notice(db, f"{t}-RAISED", created_by=me)
    mk_notice(db, f"{t}-NAMED", created_by=other, cs_in_charge_user_id=me)
    mk_notice(db, f"{t}-OTHER", created_by=other)
    out = core(db, me, {
        "entity": "order_change_notice", "fields": ["ocn_number"],
        "filters": [{"field": "ocn_number", "op": "starts_with", "value": t}],
    })
    assert len(out["rows"]) == 2
    assert all("OTHER" not in str(n) for n in _numbers(out))


def test_r13_another_companys_notice_never_shows(db):
    t = tag()
    other_company = mk_company_b(db)
    mk_notice(db, f"{t}-B", created_by=mk_user(db), company_id=other_company)
    out = core(db, mk_user(db, VIEW), {
        "entity": "order_change_notice", "fields": ["ocn_number"],
        "filters": [{"field": "ocn_number", "op": "starts_with", "value": t}],
    })
    assert out["rows"] == []


def test_r13_no_notice_grant_is_refused(db):
    refusal(db, mk_user(db), {"entity": "order_change_notice", "fields": ["ocn_number"]})
