"""SPARE-PART-OR-B C, red-first (Phase 2). C2: the purchasing email on approval.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md C2.1-C2.6.
Observed through the shared purchasing-email harness (`tests/_purchasing_email_tripwire.py`):
its dispatch spy records what the post-commit drain actually fires (context included), so the
assertions do not depend on the template text. Template relabel (C2.4) is rendered off the
real migration chain on a blank schema, as `tests/test_so_remark_template.py` does.
Postgres only; every row seeded here.

NAMED CONTRACT CHOICES (the UAC leaves them open):
1. The OR facts ride on the existing handover keys: each `handover.orders[]` entry (and each
   queued line) has `so_number` = the OR number (inquiry_no), `so_date` = submitted_at as
   dd/mm/yyyy in Asia/Kuala_Lumpur, `customer` = the requester's name, `project` = the reason
   ("-" when blank). `handover.subject_scope` = "<location> @ <OR number>" for one location.
2. The per-row flag the relabelled template reads is `is_order_request: true` on an OR's
   `handover.orders[]` entry.
3. The C2.4 data step is a module-level function `relabel_handover_template(connection)` in
   the ONE new migration (the file that adds `revised_product_id`), called by its upgrade;
   the test runs it alone because a blank schema already has the new columns (create_all).
4. The "Send to purchasing" builder is `OrderInquiryHandoverResend(db)._context(rows, actor)`
   (what `preview` renders, `oi_handover_resend.py`).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from app.utils.date_format import fmt_date

from ._purchasing_email_tripwire import Tripwire
from ._spare_part_or_c_support import (  # noqa: F401  (fixtures)
    approve_as,
    create_as,
    handovers,
    plain,
    reload,
    revise_as,
    row_for,
    rows_of,
    sent,
    submit_as,
    svc,
    world,
)
from ._spare_part_request_support import line

HANDOVER = "order_inquiry_handover"
CODE = "order_inquiry_handover_default"


def _one_location_lines(w):
    return [
        line(w.product_a, w.loc_a, qty="10", unit_price="25.00"),
        line(w.product_b, w.loc_a, qty="4", unit_price="12.50"),
    ]


def _requester_name(w) -> str:
    from app.models.user import User

    return w.db.query(User).filter(User.id == w.requester).one().name


def _first_approval(w, monkeypatch, **over):
    inquiry = submit_as(w, create_as(w, w.requester, **over), w.requester)
    assert inquiry.state == "pending_approval", "precondition"
    wire = Tripwire.arm(w.db, monkeypatch)
    before = wire.dispatches.count(HANDOVER)
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    return inquiry, wire, before


def _handover_context(wire) -> dict:
    found = [p for p in wire.pending if p[0] == HANDOVER]
    assert found, f"a handover email was dispatched: {wire.dispatches}"
    return found[-1][1]


# =============================================================================
# C2.1 - the first approval emails purchasing at commit
# =============================================================================


def test_C2_1_the_first_approval_fires_the_handover_email_at_commit(plain, monkeypatch):
    w = plain
    inquiry, wire, before = _first_approval(w, monkeypatch, lines=_one_location_lines(w))
    assert inquiry.state == "raised"
    assert wire.dispatches.count(HANDOVER) == before + 1, wire.dispatches
    lines = (_handover_context(wire).get("handover") or {}).get("lines") or []
    codes = {l.get("item_code") for l in lines}
    assert {w.product_a.product_code, w.product_b.product_code} <= codes, lines


def test_C2_1_every_raised_row_records_a_raised_line(plain, handovers):
    w = plain
    inquiry = submit_as(w, create_as(w, w.requester), w.requester)
    handovers.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    ids = {str(r.id) for r in rows_of(w.db, inquiry)}
    assert {h[0] for h in handovers if h[1] == "raised"} == ids, handovers


def test_C2_1_a_row_cancelled_at_zero_records_no_raised_line(plain, handovers):
    w = plain
    inquiry = submit_as(w, create_as(w, w.requester), w.requester)
    row_b = row_for(w.db, inquiry, w.product_b)
    svc().edit_line(w.db, reload(w.db, inquiry), row_b.id, w.stage1.tier1, qty="0")
    w.db.commit()
    handovers.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    raised_ids = {h[0] for h in handovers if h[1] == "raised"}
    assert str(row_for(w.db, inquiry, w.product_a).id) in raised_ids
    assert str(row_b.id) not in raised_ids


# =============================================================================
# C2.2 - the OR header facts and the subject
# =============================================================================


def test_C2_2_the_header_row_carries_the_or_facts(plain, monkeypatch):
    w = plain
    inquiry, wire, _before = _first_approval(w, monkeypatch, lines=_one_location_lines(w))
    orders = _handover_context(wire)["handover"]["orders"]
    assert len(orders) == 1, orders
    order = orders[0]
    assert order["so_number"] == inquiry.inquiry_no, order
    assert re.fullmatch(r"OR-\d{4}-\d{4}", inquiry.inquiry_no or ""), inquiry.inquiry_no
    assert order["so_date"] == fmt_date(inquiry.submitted_at), order
    assert order["customer"] == _requester_name(w), order
    assert order["project"] == "Spare parts for the service van", order


def test_C2_2_a_blank_reason_reads_a_dash(plain, monkeypatch):
    w = plain
    _inquiry, wire, _before = _first_approval(
        w, monkeypatch, lines=_one_location_lines(w), reason=None
    )
    assert _handover_context(wire)["handover"]["orders"][0]["project"] == "-"


def test_C2_2_the_subject_reads_location_at_or_number(plain, monkeypatch):
    w = plain
    inquiry, wire, _before = _first_approval(w, monkeypatch, lines=_one_location_lines(w))
    scope = _handover_context(wire)["handover"]["subject_scope"]
    assert scope == f"{w.loc_a.warehouse_code} @ {inquiry.inquiry_no}", scope


def test_C2_2_each_line_prints_the_or_number(plain, monkeypatch):
    w = plain
    inquiry, wire, _before = _first_approval(w, monkeypatch, lines=_one_location_lines(w))
    lines = _handover_context(wire)["handover"]["lines"]
    assert lines and all(l.get("so_number") == inquiry.inquiry_no for l in lines), lines


# =============================================================================
# C2.3 - two ORs in one email are two header rows
# =============================================================================


def _or_items(w):
    """One real handover item per OR (a raised row of each), as `_record_handover` queues
    them. Built here and aggregated directly: an approval commits inside
    `FormSLAOrchestrator.resolve_stage` (`sla_service.update_tracking`), so two approvals
    can never share one write's email; the rule under test is the aggregation (C2.3)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    service = ProjectOrderInquiryService(w.db)
    ors, items = [], []
    for _ in range(2):
        inquiry = approve_as(
            w, submit_as(w, create_as(w, w.requester), w.requester), w.stage1.tier1
        )
        ors.append(inquiry)
        items.append(service.handover_item(row_for(w.db, inquiry, w.product_a), kind="raised"))
    return ors, items


def test_C2_3_two_ors_in_one_email_are_two_header_rows(plain):
    from app.services.project_order_inquiry_service import _build_handover_context

    w = plain
    ors, items = _or_items(w)
    context, _source = _build_handover_context(items)
    orders = context["handover"]["orders"]
    assert len(orders) == 2, orders
    by_number = {o["so_number"]: o for o in orders}
    for inquiry in ors:
        order = by_number.get(inquiry.inquiry_no)
        assert order is not None, orders
        assert order["so_date"] == fmt_date(inquiry.submitted_at), order
        assert order["customer"] == _requester_name(w), order
        assert order["project"] == "Spare parts for the service van", order


def test_C2_3_two_lines_of_one_so_stay_one_header_row(plain):
    """Unchanged rule for sales orders: the header row is per SO (`pso_id`), whatever OI
    each line came from."""
    from app.services.project_order_inquiry_service import _build_handover_context

    w = plain
    _ors, items = _or_items(w)
    so_items = [
        dict(item, pso_id="zzt-pso-1", so_number="SO400001", customer="Example Customer",
             project="Example Project")
        for item in items
    ]
    context, _source = _build_handover_context(so_items)
    orders = context["handover"]["orders"]
    assert [o["so_number"] for o in orders] == ["SO400001"], orders


# =============================================================================
# C2.5 - the "Send to purchasing" preview builds the same facts
# =============================================================================


def test_C2_5_the_resend_preview_context_has_the_same_or_facts(plain):
    from app.services.oi_handover_resend import OrderInquiryHandoverResend

    w = plain
    inquiry = approve_as(
        w,
        submit_as(w, create_as(w, w.requester, lines=_one_location_lines(w)), w.requester),
        w.stage1.tier1,
    )
    rows = [r for r in rows_of(w.db, inquiry) if r.state != "cancelled"]
    context, _count = OrderInquiryHandoverResend(w.db)._context(rows, w.buyer)
    handover = context["handover"]
    order = handover["orders"][0]
    assert order["so_number"] == inquiry.inquiry_no, order
    assert order["so_date"] == fmt_date(inquiry.submitted_at), order
    assert order["customer"] == _requester_name(w), order
    assert order["project"] == "Spare parts for the service van", order
    assert handover["subject_scope"].startswith(
        f"{w.loc_a.warehouse_code} @ {inquiry.inquiry_no}"
    ), handover["subject_scope"]


# =============================================================================
# C2.6 - a revision's final approval keeps the OR header facts
# =============================================================================


def test_C2_6_a_revision_email_carries_the_or_header_facts(plain, monkeypatch):
    w = plain
    inquiry = approve_as(
        w,
        submit_as(w, create_as(w, w.requester, lines=_one_location_lines(w)), w.requester),
        w.stage1.tier1,
    )
    inquiry = revise_as(w, inquiry, w.requester)
    row = row_for(w.db, inquiry, w.product_a)
    svc().edit_line(w.db, reload(w.db, inquiry), row.id, w.requester, qty="12")
    w.db.commit()
    inquiry = submit_as(w, inquiry, w.requester)
    wire = Tripwire.arm(w.db, monkeypatch)
    approve_as(w, inquiry, w.stage1.tier1)
    order = _handover_context(wire)["handover"]["orders"][0]
    assert order["so_number"] == inquiry.inquiry_no, order
    assert order["customer"] == _requester_name(w), order


# =============================================================================
# C2.4 - the seeded default template is relabelled for OR rows (guarded)
# =============================================================================

_CHAIN = (
    "oihr_0006_no_remark_column", "oihr_0007_excel_remark", "oihr_0008_so_table_on_top",
    "oihr_0009_split_rows", "oihr_0010_so_remark_column", "oihr_0011_item_code_wrap",
    "oihr_0012_new_location",
)


def _new_migration():
    import importlib.util

    root = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    found = [p for p in root.glob("*.py") if "revised_product_id" in p.read_text()]
    assert len(found) == 1, f"one migration adds revised_product_id: {found}"
    spec = importlib.util.spec_from_file_location("zzt_spr_or_c", found[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seeded(db):
    from app.models.email_template import EmailTemplate

    from .test_oi_saved_line_email import _migration
    from .test_order_inquiry_handover_automation import _run_upgrade

    for name in _CHAIN:
        _run_upgrade(_migration(name), db)
    row = db.query(EmailTemplate).filter(EmailTemplate.code == CODE).one()
    db.refresh(row)
    return row


def _context(orders):
    from .test_oi_saved_line_email import _line

    lines = [_line(so_number=orders[0]["so_number"])]
    return {
        "handover": {
            "subject_scope": f"BRW @ {orders[0]['so_number']}", "verbs": ["ORDER"],
            "headline": "ORDER", "orders": orders, "lines": lines, "line_count": len(lines),
            "link": "https://crm.test/project-sales/order-inquiries",
        },
        "actor": {"name": "Requester", "email": "req@example.com"},
        "today": "14/11/2026",
    }


OR_ORDER = {
    "so_number": "OR-2611-0001", "so_date": "14/11/2026", "customer": "Requester One",
    "project": "Van spares", "remark": "", "is_order_request": True,
}
SO_ORDER = {
    "so_number": "SO400001", "so_date": "10/11/2026", "customer": "Example Customer",
    "project": "Example Project", "remark": "",
}


def _render(db, row, orders):
    from app.services.email_template_service import EmailTemplateService

    from .test_oi_saved_line_email import _rows

    db.refresh(row)
    rendered = EmailTemplateService(db).render(row, _context(orders))
    return _rows(rendered["body_html"]), rendered["body_text"]


def test_C2_4_an_or_header_row_reads_or_labels():
    from ._pg_fixture import blank_session

    with blank_session() as db:
        row = _seeded(db)
        _new_migration().relabel_handover_template(db.connection())
        rows, text = _render(db, row, [OR_ORDER])
        assert rows[0][:4] == ["OR NO", "OR DATE", "REQUESTER", "REASON"], rows[0]
        assert rows[1][:4] == ["OR-2611-0001", "14/11/2026", "Requester One", "Van spares"], rows[1]
        assert "OR NO" in text, text


def test_C2_4_an_so_header_row_keeps_so_labels():
    from ._pg_fixture import blank_session

    with blank_session() as db:
        row = _seeded(db)
        _new_migration().relabel_handover_template(db.connection())
        rows, _text = _render(db, row, [SO_ORDER])
        assert rows[0][:4] == ["S/O NO", "SO DATE", "CUSTOMER", "PROJECT"], rows[0]


def test_C2_4_an_owner_edited_template_is_left_alone(caplog):
    from ._pg_fixture import blank_session

    with blank_session() as db:
        row = _seeded(db)
        row.body_text = (row.body_text or "") + "\nOwner footer."
        db.flush()
        edited = (row.body_text, row.body_html, row.layout_json)
        with caplog.at_level(logging.WARNING):
            _new_migration().relabel_handover_template(db.connection())
        db.refresh(row)
        assert (row.body_text, row.body_html, row.layout_json) == edited
