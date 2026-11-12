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
from ._ocn_support import (  # noqa: F401  (fixtures)
    approved,
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
