"""NON-CANCELLABLE-ITEMS: the amendment-publish gate, the board Transfer to Cancel SO gate and
the AutoCount cut detection, end to end on the existing fixtures.

Which SO line is Non-cancellable is read through `non_cancellable_service.so_lines_non_cancellable`
(the quotation-line flag; its own resolution is pinned in test_non_cancellable_items.py), so these
tests flag lines by patching that one function and exercise everything around it for real.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.audit import AuditLog
from app.services import non_cancellable_service as nc
from app.services.error_handler import AppException
from app.services.planning_change_service import non_cancellable_cut_moves
from app.services.scm.outstanding_diff import CLOSED, DATE_AND_QTY_CHANGED, QTY_CHANGED

from .test_project_so_delta import (  # noqa: F401 - `seeded` is a fixture
    _created_amendment,
    _revision,
    _tuju,
    seeded,
)
from .test_so_cancel_line import _cancel_body, _cb_world, _confirm_all, _raw
from .test_so_supply_confirmation import api  # noqa: F401 - fixture


def _flag_all(monkeypatch):
    monkeypatch.setattr(
        nc, "so_lines_non_cancellable", lambda _db, lines: {str(line.id) for line in lines}
    )


# ------------------------------------------------------------ amendment publish


def _cut_amendment(db, company_id, owner):
    project, po, po_version, _r1, phases, orders, products = _tuju(db, company_id, owner)
    r2 = _revision(
        db, project, po, po_version, phases, products,
        use_r2=False, tweaks={("TOWER", 1, "p1"): "105"},
    )
    service, amendment, ocn = _created_amendment(db, orders, r2, owner)
    rows = (amendment.delta_json or {}).get("rows") or []
    cut = [str(i) for i, row in enumerate(rows) if row["verb"] == "CANCEL BALANCE"]
    assert len(cut) == 1
    return service, amendment, cut[0]


def test_publishing_a_cut_of_a_non_cancellable_line_is_refused(seeded, monkeypatch):
    db, company_id, owner = seeded
    _flag_all(monkeypatch)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: False)
    service, amendment, _key = _cut_amendment(db, company_id, owner)

    detail = service.get_amendment(amendment.id)
    flagged = [row for row in detail["delta"]["rows"] if row["non_cancellable"]]
    assert flagged, "every row on a flagged line says so"

    with pytest.raises(AppException) as refused:
        service.publish_amendment(amendment.id, actor_user_id=owner)
    assert refused.value.code == "non_cancellable_line"
    assert refused.value.detail["details"]["lines"][0]["from_qty"] == "135"
    assert refused.value.detail["details"]["lines"][0]["to_qty"] == "105"


def test_declining_the_cut_row_publishes_without_an_override(seeded, monkeypatch):
    db, company_id, owner = seeded
    _flag_all(monkeypatch)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: False)
    service, amendment, key = _cut_amendment(db, company_id, owner)
    service.update_row_decisions(
        amendment.id, {key: {"decision": "declined", "reason": "Non-cancellable"}}
    )
    body = service.publish_amendment(amendment.id, actor_user_id=owner)
    assert body["status"] == "published"


def test_an_override_holder_publishes_the_cut_with_a_reason_and_it_is_logged(
    seeded, monkeypatch
):
    db, company_id, owner = seeded
    _flag_all(monkeypatch)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: True)
    service, amendment, _key = _cut_amendment(db, company_id, owner)
    body = service.publish_amendment(
        amendment.id,
        actor_user_id=owner,
        non_cancellable_override_reason="Customer pays the storage charge",
    )
    assert body["status"] == "published"
    logged = (
        db.query(AuditLog)
        .filter(AuditLog.event == nc.AUDIT_EVENT, AuditLog.entity_id == str(amendment.project_sales_order_id))
        .all()
    )
    assert len(logged) == 1
    assert logged[0].reason == "Customer pays the storage charge"


# ------------------------------------------------------------ board cancel line


def test_board_cancel_of_a_non_cancellable_line_is_refused_per_order(api, monkeypatch):
    client, world = api
    w = _cb_world(world)
    core_a, mirror_a, _product_a = w["a"]
    _flag_all(monkeypatch)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: False)

    result = _confirm_all(client, w["order"], **_cancel_body(mirror_a))

    assert result["ok"] is False
    assert result["error_code"] == "non_cancellable_line"
    assert result["error_details"]["can_override"] is False
    assert _raw(world.db, core_a.id).line_status == "closed"


def test_board_cancel_with_an_override_cancels_the_line(api, monkeypatch):
    client, world = api
    w = _cb_world(world)
    core_a, mirror_a, _product_a = w["a"]
    _flag_all(monkeypatch)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: True)
    body = _cancel_body(mirror_a)
    body["cancelled_lines"][0]["non_cancellable_override_reason"] = "Customer agreed restock fee"

    result = _confirm_all(client, w["order"], **body)

    assert result["ok"] is True, result
    assert _raw(world.db, core_a.id).line_status == "cancelled"


def test_board_override_reasons_must_agree(api, monkeypatch):
    client, world = api
    w = _cb_world(world)
    _core_a, mirror_a, _pa = w["a"]
    _core_b, mirror_b, _pb = w["b"]
    _flag_all(monkeypatch)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: True)
    body = _cancel_body(mirror_a, mirror_b)
    body["cancelled_lines"][0]["non_cancellable_override_reason"] = "one"
    body["cancelled_lines"][1]["non_cancellable_override_reason"] = "two"

    result = _confirm_all(client, w["order"], **body)

    assert result["ok"] is False
    assert "one override reason" in result["error"]


# ------------------------------------------------------- AutoCount cut detection


def _entry(kind, before, after, *, line_id="pl1"):
    line = lambda q: SimpleNamespace(qty=q)  # noqa: E731
    return {
        "project_line": SimpleNamespace(id=line_id),
        "core_line_id": f"core-{line_id}",
        "change": SimpleNamespace(
            kind=kind,
            before=line(before) if before is not None else None,
            after=line(after) if after is not None else None,
        ),
    }


def test_cut_detection_alerts_drops_only_on_flagged_lines():
    drop = _entry(QTY_CHANGED, 53, 40)
    moved_and_cut = _entry(DATE_AND_QTY_CHANGED, 53, 0, line_id="pl2")
    raise_ = _entry(QTY_CHANGED, 53, 60, line_id="pl3")
    settled = _entry(CLOSED, 53, 0, line_id="pl4")
    unflagged = _entry(QTY_CHANGED, 53, 10, line_id="pl5")
    new_line = _entry("added", None, 10, line_id="pl6")
    entries = [drop, moved_and_cut, raise_, settled, unflagged, new_line]

    cuts = non_cancellable_cut_moves(entries, {"pl1", "pl2", "pl3", "pl4", "pl6"})

    assert cuts == [("core-pl1", 53, 40), ("core-pl2", 53, 0)]
    assert drop.get("non_cancellable") and moved_and_cut.get("non_cancellable")
    for untouched in (raise_, settled, unflagged, new_line):
        assert not untouched.get("non_cancellable")


def test_series_category_beats_a_company_product_exemption():
    """Series before company default: a series category marks the model even though the
    company default exempts that exact product."""
    setting = nc.SeriesNonCancellable(categories={"cat"}, company_products={"p": False})

    class _Db:
        pass

    import app.services.project_pricing_service as pricing

    original = pricing.category_ancestry
    pricing.category_ancestry = lambda _db, cid: [cid]
    try:
        assert nc.product_is_non_cancellable(
            _Db(), product_id="p", category_id="cat", setting=setting
        )
    finally:
        pricing.category_ancestry = original
