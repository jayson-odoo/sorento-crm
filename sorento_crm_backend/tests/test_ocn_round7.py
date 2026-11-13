"""OCN-ORDER-CHANGE-NOTICE round 7 (browser pass), pinned: an order change notice's History reads
in words. A status move names the statuses ("Status: Approved -> Done", never "processed_by_cs"),
and a held move names itself ("Mark done applied", never "ocn.finalize"). Other record types read
exactly as before.

Postgres only for the route test, every row seeded.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.api.v1.audit.audit_logs import _derive_description

from ._forms_chain_support import world  # noqa: F401
from .test_ocn_amendment_link import build  # noqa: F401  (fixture)
from ._ocn_support import (  # noqa: F401  (fixtures)
    approved,
    create,
    move,
    ocn,
    ok,
    sla,
    svc,
)


def _row(entity_type, old=None, new=None, description=None, action="UPDATE"):
    return SimpleNamespace(entity_type=entity_type, old_values=old, new_values=new,
                           description=description, action=action)


def test_r7_a_notice_status_move_reads_in_words():
    got = _derive_description(_row("order_change_notice", {"status": "approved"}, {"status": "processed_by_cs"}))
    assert got == "Status: Approved → Done"


def test_r11_a_move_with_a_reason_names_it_in_the_one_history_row():
    row = _row("order_change_notice", {"status": "approved"}, {"status": "draft"})
    row.reason = "Picked for a sales order amendment: the change needs approval."
    assert _derive_description(row) == (
        "Status: Approved → Draft. Picked for a sales order amendment: the change needs approval."
    )


def test_r11_module_row_in_scope_reads_the_notice_by_its_own_rule_and_refuses_unknown_kinds(ocn):
    """No fall-through to the sales opportunity rule (review R3): the notice's own rule (raised
    or named), and an unknown kind is never theirs."""
    from app.services import own_scope
    from app.services.own_scope import Me

    mine = create(ocn, user_id=ocn.own, cs_in_charge_user_id=None)
    theirs = create(ocn, user_id=ocn.raiser, cs_in_charge_user_id=None)
    me = Me(user_id=ocn.own, contact_id=None, agent_ids=())
    assert own_scope.module_row_in_scope(ocn.db, "order_change_notice", mine["id"], me) is True
    assert own_scope.module_row_in_scope(ocn.db, "order_change_notice", theirs["id"], me) is False
    assert own_scope.module_row_in_scope(ocn.db, "zzt_unknown_kind", mine["id"], me) is False


def test_r7_an_approval_only_move_gets_no_code_summary():
    got = _derive_description(_row("order_change_notice", {"approval_status": None}, {"approval_status": "pending"}))
    assert got is None  # the trail's own field line says "Approval status: (empty) -> pending"


def test_r7_a_held_notice_move_reads_by_its_name():
    assert _derive_description(_row("order_change_notice", description="Action applied (ocn.finalize)")) == (
        "Mark done applied"
    )
    assert _derive_description(_row(
        "order_change_notice", description="Action requested (ocn.reject_submitted); held 10s before applying",
    )) == "Send back requested; held 10s before applying"


def test_r7_other_record_types_read_as_before():
    assert _derive_description(_row("purchase_request", {"status": "approved"}, {"status": "rejected"})) == (
        "status: approved → rejected"
    )
    assert _derive_description(_row("purchase_request", description="Action applied (pr.finalize)")) == (
        "Action applied (pr.finalize)"
    )


def test_r7_the_history_route_words_a_real_done(ocn, sla):
    d = approved(ocn)
    ok(move(ocn, d["id"], "done", ocn.cs, json={"cs_comment": "Stock released."}))
    res = ocn.as_(ocn.sales_admin).get(
        "/api/v1/audit/logs/", params={"entity_type": "order_change_notice", "entity_id": d["id"], "limit": 100},
    )
    assert res.status_code == 200, res.text
    said = [r["description"] for r in res.json()["data"] if r["description"]]
    assert "Status: Approved → Done" in said
    assert not any("processed_by_cs" in s or "(ocn." in s or "approval_status" in s for s in said)


# ================================================================== round 14: drafted notice prefill


def test_r14_a_drafted_notice_takes_the_orders_customer_and_po_from_its_links(build):
    """The PO's issuing party's customer record and that PO's number (explicit links, never text)."""
    from app.models.project_so import OrderChangeNotice
    from app.models.projects import ProjectParty, ProjectPurchaseOrder

    from .test_ocn_amendment_link import _create
    from .test_project_so_draft import _customer

    b = build
    customer = _customer(b.db, "ZZT Prefill Customer")
    po = b.db.get(ProjectPurchaseOrder, b.orders["TOWER"].purchase_order_id)
    b.db.get(ProjectParty, po.issuing_party_id).customer_id = customer.id
    b.db.flush()
    created = _create(b)
    ocn = b.db.get(OrderChangeNotice, created["ocn_id"])
    assert ocn.customer_id == customer.id
    assert ocn.customer_name == customer.customer_name
    assert ocn.customer_po_no == po.po_number == "HQ/26/01/121"


def test_r14_a_missing_link_leaves_the_field_blank(build):
    from app.models.project_so import OrderChangeNotice

    from .test_ocn_amendment_link import _create

    b = build  # the build's party has no customer record
    created = _create(b)
    ocn = b.db.get(OrderChangeNotice, created["ocn_id"])
    assert ocn.customer_id is None and ocn.customer_name is None
    assert ocn.customer_po_no == "HQ/26/01/121"
