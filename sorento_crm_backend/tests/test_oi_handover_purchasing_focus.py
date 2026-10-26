"""OI-EMAIL-PURCHASING-FOCUS (owner, 26 Oct 2026, rulings ~13:05): the purchasing email tells
purchasing only what they act on. "Use own location" and "Use BRW" lines are not sent, and
neither are Use incoming / Borrow incoming / LOCAL BUY. A mixed line reads only purchasing's part
(Q1 a), Cancel SO reads as today (Q2), and a Buy turned to stock says it CHANGED, never "CANCEL
ORDER", which purchasing would read as the customer cancelling (Q4).

Plan: `documentation/plans/scm/PLAN-oi-email-purchasing-focus-26oct.md` (rule 2, section 3).

TEST-FIRST. `purchasing_remark` is pure; the flows run through the board's own Confirm route
with the dispatch captured (nothing is sent).
"""
from __future__ import annotations

from datetime import date

from app.models.order import SalesOrderLine
from app.services.project_order_inquiry_service import purchasing_remark

from .test_oi_saved_line_email import _lines, _order, _post, emails  # noqa: F401 - fixture
from .test_planning_change_apply_on_board import BASE, api, world  # noqa: F401 - fixtures
from .test_planning_changes import _line_payload
from .test_so_supply_confirmation import _stock

__all__ = ["api", "world", "emails"]


# ------------------------------------------------------------------ pure: purchasing_remark


def _snap(*components, own="BRW-IB", **extra):
    return {"location": own, "open_qty": "10", "components": list(components), **extra}


def _buy(qty="10"):
    return {"kind": "buy", "qty": qty}


def _reserve(qty, location, rung=None):
    return {"kind": "reserve", "qty": qty, "source_location": location, "rung": rung}


def _borrow(qty, location, rung=None, supply_document=None):
    return {
        "kind": "borrow", "qty": qty, "source_location": location, "rung": rung,
        "supply_document": supply_document,
    }


def test_a_buy_and_an_order_back_are_purchasings():
    assert purchasing_remark(_snap(_buy())) == "ORDER"
    assert purchasing_remark(_snap(_buy(), order_back=True)) == "ORDER BACK"
    assert purchasing_remark(_snap(_borrow("10", "BRW-BB"))) == "ORDER BACK BRW-BB"


def test_use_own_location_and_use_brw_say_nothing_to_purchasing():
    assert purchasing_remark(_snap(_reserve("10", "BRW-IB"))) == ""
    assert purchasing_remark(_snap(_reserve("10", "BRW", rung="pool"))) == ""


def test_incoming_stock_and_local_buy_say_nothing_to_purchasing():
    """Q3 (a): Use incoming / Borrow incoming are stock on its way; LOCAL BUY does not go to
    purchasing (owner, 26 Oct 2026)."""
    timely = {"kind": "timely_spo", "qty": "10"}
    assert purchasing_remark(_snap(timely, timely_spo_refs=[{"spo_number": "SPO-1"}])) == ""
    assert purchasing_remark(
        _snap(_borrow("10", "BRW-BB", rung="supply_borrow", supply_document="SPO-2"))
    ) == ""
    assert purchasing_remark(_snap(_buy(), buy_origin="local")) == ""


def test_a_mixed_line_reads_only_purchasings_part_with_its_qty():
    """Q1 (a): USE BRW-BB 6 & ORDER 4 reads ORDER 4."""
    assert purchasing_remark(_snap(_reserve("6", "BRW-BB"), _buy("4"), own="BRW-BB")) == "ORDER 4"
    assert purchasing_remark(
        _snap(_reserve("6", "BRW", rung="pool"), _borrow("2", "BRW-IC"), _buy("2"))
    ) == "ORDER BACK BRW-IC 2 & ORDER 2"


# ------------------------------------------------------------------ flows: the email itself


def test_a_confirm_of_only_use_own_location_and_use_brw_sends_no_email(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    world.db.commit()
    order, line_a, line_b = _order(api)

    _post(api, order, [
        _line_payload(line_a.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "10"}]),
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "6"}]),
    ])

    assert emails == [], [_lines(e) for e in emails]


def test_a_buy_beside_a_use_brw_line_sends_only_the_buy(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    order, line_a, line_b = _order(api)

    _post(api, order, [
        _line_payload(line_a.id, buy_qty="10"),
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "6"}]),
    ])

    assert len(emails) == 1, emails
    assert _lines(emails[0]) == [
        (world.product.product_code, "10", world.own_wh.warehouse_code, "ORDER"),
    ]


def test_a_mixed_line_is_sent_reading_only_its_order(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    order, line_a, _line_b = _order(api)

    _post(api, order, [
        _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "6"}],
                      buy_qty="4", amend_reason="Part from BRW, buy the rest."),
    ])

    assert len(emails) == 1, emails
    assert _lines(emails[0]) == [
        (world.product.product_code, "10", world.own_wh.warehouse_code, "ORDER 4"),
    ]


def test_a_buy_turned_to_use_brw_says_it_changed_never_cancel_order(api, emails):
    """Q4: today this read `USE <pool>, CANCEL ORDER 10`; purchasing read that as the customer
    cancelling. It now states the change."""
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    order, line_a, _line_b = _order(api)
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()
    pool = world.pool_wh.warehouse_code

    _post(api, order, [
        _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}],
                      amend_reason="BRW has it."),
    ])

    assert len(emails) == 1, emails
    [(_code, qty, _loc, remark)] = _lines(emails[0])
    assert qty == "10"
    assert remark == f"CHANGED: ORDER 10 -> USE {pool} 10", remark
    assert "CANCEL" not in remark


def test_a_use_brw_line_whose_date_moved_sends_nothing(api, emails):
    """A line purchasing never held anything for: its date move is not theirs either."""
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    order, line_a, _line_b = _order(api)
    use = [{"warehouse_id": world.pool_wh.id, "qty": "10"}]
    _post(api, order, [_line_payload(line_a.id, reserve=use)])
    emails.clear()
    line_a.delivery_date = date(2026, 12, 1)
    world.db.get(SalesOrderLine, line_a.core_sales_order_line_id).required_date = date(2026, 12, 1)
    world.db.commit()

    _post(api, order, [_line_payload(line_a.id, reserve=use, amend_reason="Later.")])

    assert emails == [], [_lines(e) for e in emails]


def test_cancel_so_on_a_use_brw_line_still_reads_cancel_as_today(api, emails):
    """Q2 (owner: "same as now"): `record_cancelled_lines` tells every line transferred to Cancel
    SO, whatever it held."""
    client, world = api
    order, line_a, line_b = _order(api)

    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json={
        "lines": [_line_payload(line_a.id, buy_qty="10")],
        "cancelled_lines": [{"project_line_id": str(line_b.id), "reason": "Customer dropped it."}],
    })
    assert response.status_code == 200, response.text
    world.db.commit()

    assert len(emails) == 1, emails
    assert sorted(r for *_x, r in _lines(emails[0])) == ["CANCEL", "ORDER"]


# ------------------------- crew audit 26 Oct: CHANGED on qty moves, never "CANCEL ORDER"


def _buy_then(api, emails, cut_to, second):
    """Line A Buy 10 confirmed; AutoCount moves the line to `cut_to`; re-Confirm `second`. The
    one email line of the re-Confirm."""
    from decimal import Decimal

    from .test_oi_saved_line_email import _one_line_order

    _client, world = api
    order, line, core_line = _one_line_order(world, "10")
    _post(api, order, [_line_payload(line.id, buy_qty="10")])
    emails.clear()
    if cut_to is not None:
        core_line.qty_ordered = Decimal(cut_to)
        line.qty = Decimal(cut_to)
        world.db.commit()
    _post(api, order, [_line_payload(line.id, amend_reason="Changed.", **second)])
    assert len(emails) == 1, emails
    [entry] = emails[0]["lines"]
    return entry


def test_a_buy_turned_use_own_location_with_a_qty_cut_reads_changed_not_cancel(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    world.db.commit()
    own = world.own_wh.warehouse_code

    entry = _buy_then(api, emails, "8", {"reserve": [{"warehouse_id": world.own_wh.id, "qty": "8"}]})

    assert entry["remark"] == f"CHANGED: ORDER 10 -> USE {own} 8", entry
    assert entry["was"] == {"qty": "10"} and entry["qty"] == "8", entry


def test_a_buy_turned_use_own_location_with_a_qty_rise_is_never_blank(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    world.db.commit()
    own = world.own_wh.warehouse_code

    entry = _buy_then(
        api, emails, "12", {"reserve": [{"warehouse_id": world.own_wh.id, "qty": "12"}]}
    )

    assert entry["remark"] == f"CHANGED: ORDER 10 -> USE {own} 12", entry
    assert entry["was"] == {"qty": "10"} and entry["qty"] == "12", entry


def test_a_buy_turned_order_back_reads_changed_never_cancel_order(api, emails):
    """Crew audit (3): purchasing reads CANCEL ORDER as a customer cancel, so a Buy moved to an
    Order back states the change too."""
    from .test_oi_saved_line_email import _borrow_from, _donor

    _client, world = api
    donor = _donor(world, "KL")

    entry = _buy_then(api, emails, None, {"borrow": _borrow_from(world, donor, "10")})

    assert entry["remark"] == f"CHANGED: ORDER 10 -> ORDER BACK {donor.warehouse_code} 10", entry
    assert "CANCEL" not in entry["remark"]


def test_a_customer_cut_of_the_same_buy_still_reads_cancel_n(api, emails):
    """The one cancel purchasing must read as such: the customer cut the line."""
    entry = _buy_then(api, emails, "8", {"buy_qty": "8"})

    assert entry["remark"] == "CANCEL 2", entry
    assert entry["was"] == {"qty": "10"}, entry


def test_a_stock_only_saved_line_keeps_its_cancel_balance_notice_and_drops_its_delay():
    """Lane review S3: a saved line that tells purchasing nothing (stock only) no longer has a
    `saved:` line to carry its rows' news, so the apply's CANCEL BALANCE notice (an AutoCount cut
    of a row purchasing holds) stays; its DELAY notice still goes. A line that WAS told keeps
    today's rule: every notice of it goes."""
    from uuid import uuid4

    from app.services.project_order_inquiry_service import (
        _HANDOVER_PENDING_KEY,
        _SAVED_TOLD_KEY,
        ProjectOrderInquiryService,
    )

    from ._pg_fixture import blank_session

    with blank_session() as db:
        pso_id, quiet, told = str(uuid4()), str(uuid4()), str(uuid4())

        def item(line_id, keys, row_id=None):
            return {
                "row_id": row_id or str(uuid4()), "so_line_id": line_id, "pso_id": pso_id,
                "verb_keys": list(keys), "line": {},
            }

        cut = item(quiet, ["CANCEL_BALANCE"])
        db.info[_SAVED_TOLD_KEY] = {pso_id: {quiet, told}}
        db.info[_HANDOVER_PENDING_KEY] = [
            cut,
            item(quiet, ["DELAY"]),
            item(told, ["ORDER"], row_id=f"saved:{told}"),
            item(told, ["CANCEL_BALANCE"]),
        ]

        ProjectOrderInquiryService(db).forget_rows_told_for_saved_lines(pso_id)

        left = db.info[_HANDOVER_PENDING_KEY]
        assert [i["row_id"] for i in left] == [cut["row_id"], f"saved:{told}"], left


def test_the_board_preview_says_what_the_email_says():
    """Crew audit (4): the board's "email words" are the email's. `before` is the confirmed
    decision, passed only while purchasing still holds an open OI row for the line."""
    from app.services.project_order_inquiry_service import saved_draft_remark

    use_own = {"verdict": "amended", "reserve": [{"location": "BRW-BB", "qty": "10"}],
               "borrow": [], "buy_qty": "0"}
    mixed = {**use_own, "reserve": [{"location": "BRW-BB", "qty": "6"}], "buy_qty": "4"}
    held_buy = {"reserve": [], "borrow": [], "buy_qty": "10"}

    assert saved_draft_remark(use_own, location="BRW-BB") is None
    assert saved_draft_remark(mixed, location="BRW-BB") == "ORDER 4"
    assert saved_draft_remark(use_own, location="BRW-BB", before=held_buy) == (
        "CHANGED: ORDER 10 -> USE BRW-BB 10"
    )


def test_the_board_preview_reads_a_grown_purchasing_part_as_the_email_does():
    """Lane review S6: purchasing's part only grows, nothing is taken back, so the email reads
    ORDER words, never CHANGED, and the preview says the same."""
    from app.services.project_order_inquiry_service import saved_draft_remark

    held_mix = {"reserve": [{"location": "BRW-BB", "qty": "6"}], "borrow": [], "buy_qty": "4"}
    whole_buy = {"verdict": "amended", "reserve": [], "borrow": [], "buy_qty": "10"}
    more_buy = {"verdict": "amended", "reserve": [{"location": "BRW-BB", "qty": "4"}],
                "borrow": [], "buy_qty": "6"}

    assert saved_draft_remark(whole_buy, location="BRW-BB", before=held_mix) == "ORDER"
    assert saved_draft_remark(more_buy, location="BRW-BB", before=held_mix) == "ORDER 6"


# ----------- crew final audit (26 Oct): a raised order cancelled on a line's FIRST Confirm


def _imported_raised_order(api, qty="10"):
    """An undecided line that already carries a raised ORDER row (as a 20 Sep sheet import
    left them): purchasing holds that order though no decision was ever confirmed."""
    from .test_oi_cancelled_line_used_confirm import _inquiry, _oi_row
    from .test_oi_saved_line_email import _one_line_order

    _client, world = api
    order, line, _core = _one_line_order(world, qty)
    inquiry = _inquiry(world.db, world.company_id, order.id)
    _oi_row(world.db, world.company_id, inquiry.id, line.id, world.product.product_code, qty)
    world.db.commit()
    return order, line


def test_a_first_confirm_that_turns_an_imported_order_to_own_stock_says_it_changed(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    world.db.commit()
    own = world.own_wh.warehouse_code
    order, line = _imported_raised_order(api)
    emails.clear()

    _post(api, order, [_line_payload(
        line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "10"}],
    )])

    assert len(emails) == 1, "purchasing holds that order: it must be told"
    assert [l["remark"] for l in emails[0]["lines"]] == [f"CHANGED: ORDER 10 -> USE {own} 10"]


def test_a_first_confirm_that_moves_part_of_an_imported_order_to_own_stock(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    world.db.commit()
    own = world.own_wh.warehouse_code
    order, line = _imported_raised_order(api)
    emails.clear()

    _post(api, order, [_line_payload(
        line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "6"}], buy_qty="4",
        amend_reason="Part from stock.",
    )])

    assert len(emails) == 1, emails
    assert [l["remark"] for l in emails[0]["lines"]] == [
        f"ORDER 4, CHANGED: ORDER 10 -> USE {own} 6"
    ]


def test_a_first_confirm_over_two_imported_orders_reads_each_row_as_a_later_confirm(api, emails):
    """Lane review nit: two raised rows (10 + 3) on an undecided line, first Confirmed as Buy 8,
    read per row like the same fold on a later Confirm: CHANGED: ORDER 10 & ORDER 3 -> ORDER 8."""
    from decimal import Decimal

    from .test_oi_cancelled_line_used_confirm import _inquiry, _oi_row
    from .test_oi_saved_line_email import _one_line_order

    _client, world = api
    order, line, core = _one_line_order(world, "13")
    inquiry = _inquiry(world.db, world.company_id, order.id)
    _oi_row(world.db, world.company_id, inquiry.id, line.id, world.product.product_code, "10")
    _oi_row(world.db, world.company_id, inquiry.id, line.id, world.product.product_code, "3")
    core.qty_ordered = Decimal("8")
    line.qty = Decimal("8")
    world.db.commit()
    emails.clear()

    _post(api, order, [_line_payload(line.id, buy_qty="8")])

    assert len(emails) == 1, emails
    assert [l["remark"] for l in emails[0]["lines"]] == ["CHANGED: ORDER 10 & ORDER 3 -> ORDER 8"]


def test_a_first_confirm_that_turns_an_imported_order_to_use_brw_says_it_changed(api, emails):
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    pool = world.pool_wh.warehouse_code
    order, line = _imported_raised_order(api)
    emails.clear()

    _post(api, order, [_line_payload(
        line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}],
    )])

    assert len(emails) == 1, emails
    assert [l["remark"] for l in emails[0]["lines"]] == [f"CHANGED: ORDER 10 -> USE {pool} 10"]


def test_a_first_confirm_that_turns_an_imported_order_to_incoming_names_the_spo(api, emails):
    """Hand-test step 8's shape: Use incoming on a line purchasing holds a raised ORDER for."""
    import uuid
    from datetime import date

    from app.models.procurement import InboundShipment, SPOAllocation

    _client, world = api
    shipment = InboundShipment(
        id=str(uuid.uuid4()), shipment_number=f"ZZT-SHIP-{uuid.uuid4().hex[:8]}",
        shipment_date=date(2026, 9, 1), estimated_arrival_date=date(2026, 10, 1),
    )
    world.db.add(shipment)
    world.db.flush()
    spo = f"ZZT-SPO-{uuid.uuid4().hex[:6]}"
    world.db.add(SPOAllocation(
        id=str(uuid.uuid4()), spo_number=spo, spo_line_number=1,
        inbound_shipment_id=shipment.id, warehouse_id=world.own_wh.id,
        product_id=world.product.id, allocated_quantity=10, quantity_received=0,
        receipt_status="pending", company_id=world.company_id,
    ))
    world.db.commit()
    order, line = _imported_raised_order(api)
    emails.clear()

    _post(api, order, [_line_payload(line.id, timely_spo_qty="10")])

    assert len(emails) == 1, emails
    [remark] = [l["remark"] for l in emails[0]["lines"]]
    assert remark.startswith("CHANGED: ORDER 10 -> ") and remark.endswith(" 10"), remark
    assert spo in remark, remark


def test_the_first_take_back_words_local_buy_and_an_order_back_row_by_their_own_kind():
    """Local buy is not purchasing's, so a raised order turned LOCAL BUY reads as the change;
    an ORDER BACK row taken back names ORDER BACK, its own kind (crew final audit (3))."""
    from decimal import Decimal

    from app.services.project_order_inquiry_service import first_take_back_remark

    local = _snap(_buy("10"), buy_origin="local")
    assert first_take_back_remark([("ORDER", Decimal("10"))], local) == (
        "CHANGED: ORDER 10 -> LOCAL BUY 10"
    )
    own = _snap(_reserve("10", "BRW-IB"))
    assert first_take_back_remark([("ORDER BACK", Decimal("10"))], own) == (
        "CHANGED: ORDER BACK 10 -> USE BRW-IB 10"
    )


def test_a_planners_own_remark_never_hides_a_first_confirm_take_back(api, emails):
    """Crew final audit (2): a stock-only first Confirm that carries the planner's own REMARK
    still tells the raised order it takes back, as the change."""
    _client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    world.db.commit()
    own = world.own_wh.warehouse_code
    order, line = _imported_raised_order(api)
    emails.clear()

    payload = _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "10"}])
    payload["remark"] = "Site wants it from stock."
    _post(api, order, [payload])

    assert len(emails) == 1, emails
    assert [l["remark"] for l in emails[0]["lines"]] == [f"CHANGED: ORDER 10 -> USE {own} 10"]


def test_the_board_preview_of_a_first_confirm_take_back_equals_the_email():
    """Crew final audit (4): the guide gets the raised rows' kind and qty, so hand-test step 4
    previews exactly what the email says."""
    from decimal import Decimal

    from app.services.project_order_inquiry_service import saved_draft_remark

    draft = {"verdict": "amended", "reserve": [{"location": "BRW-BB", "qty": "48"}],
             "borrow": [], "buy_qty": "4"}
    assert saved_draft_remark(
        draft, location="BRW-BB", held_rows=[("ORDER", Decimal("52"))]
    ) == "ORDER 4, CHANGED: ORDER 52 -> USE BRW-BB 48"
    # A whole Buy over its own raised row takes nothing back: plain ORDER.
    whole = {"verdict": "amended", "reserve": [], "borrow": [], "buy_qty": "52"}
    assert saved_draft_remark(whole, location="BRW-BB", held_rows=[("ORDER", Decimal("52"))]) == (
        "ORDER"
    )


def test_a_first_confirm_over_an_imported_order_back_names_it_order_back(api, emails):
    """Crew final audit (3): the row taken back was an ORDER BACK, so the email says so, not
    ORDER."""
    from app.models.project_so import IV_ORDER_BACK, OrderInquiryRow

    from .test_oi_cancelled_line_used_confirm import _inquiry, _oi_row
    from .test_oi_saved_line_email import _one_line_order

    _client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=50)
    order, line, _core = _one_line_order(world, "10")
    inquiry = _inquiry(world.db, world.company_id, order.id)
    row = _oi_row(world.db, world.company_id, inquiry.id, line.id, world.product.product_code, "10")
    world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).update(
        {"verb": IV_ORDER_BACK}
    )
    world.db.commit()
    own = world.own_wh.warehouse_code
    emails.clear()

    _post(api, order, [_line_payload(
        line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "10"}],
    )])

    assert len(emails) == 1, emails
    assert [l["remark"] for l in emails[0]["lines"]] == [
        f"CHANGED: ORDER BACK 10 -> USE {own} 10"
    ]


# ------------------------------- crew audit (26 Oct, c19f2486): SPO refs once, own kinds


def test_each_spo_prints_once_by_arrival_then_number():
    """One ref per SPO ALLOCATION row: SPO-B twice (17 Oct), SPO-A once (16 Oct) read
    "SPO-A, SPO-B", never "SPO-B, SPO-A, SPO-B" (SO399381 printed one SPO 31 times)."""
    from app.services.project_order_inquiry_service import saved_line_remark

    refs = [
        {"spo_number": "ZZT-SPO-B", "arrival_date": "2026-10-17"},
        {"spo_number": "ZZT-SPO-A", "arrival_date": "2026-10-16"},
        {"spo_number": "ZZT-SPO-B", "arrival_date": "2026-10-17"},
    ]
    snap = _snap({"kind": "timely_spo", "qty": "10"}, timely_spo_refs=refs)
    assert saved_line_remark(snap)[0] == "ZZT-SPO-A, ZZT-SPO-B"
    # Bare numbers (older frozen snapshots): once each, in their own order.
    bare = _snap({"kind": "timely_spo", "qty": "10"}, timely_spo_refs=["S2", "S1", "S2"])
    assert saved_line_remark(bare)[0] == "S2, S1"


def test_a_first_confirm_to_incoming_names_each_spo_once_by_arrival(api, emails):
    """Hand-test step 8's shape with two allocation rows of one SPO beside a second SPO."""
    import uuid
    from datetime import date

    from app.models.procurement import InboundShipment, SPOAllocation

    _client, world = api
    tag = uuid.uuid4().hex[:6]
    early, late = f"ZZT-SPO-{tag}-A", f"ZZT-SPO-{tag}-B"
    for spo, eta, rows in ((late, date(2026, 10, 17), 2), (early, date(2026, 10, 16), 1)):
        shipment = InboundShipment(
            id=str(uuid.uuid4()), shipment_number=f"ZZT-SHIP-{uuid.uuid4().hex[:8]}",
            shipment_date=date(2026, 9, 1), estimated_arrival_date=eta,
        )
        world.db.add(shipment)
        world.db.flush()
        for line_no in range(1, rows + 1):
            world.db.add(SPOAllocation(
                id=str(uuid.uuid4()), spo_number=spo, spo_line_number=line_no,
                inbound_shipment_id=shipment.id, warehouse_id=world.own_wh.id,
                product_id=world.product.id, allocated_quantity=5, quantity_received=0,
                receipt_status="pending", company_id=world.company_id,
            ))
    world.db.commit()
    order, line = _imported_raised_order(api)
    emails.clear()

    _post(api, order, [_line_payload(line.id, timely_spo_qty="10")])

    assert len(emails) == 1, emails
    assert [l["remark"] for l in emails[0]["lines"]] == [
        f"CHANGED: ORDER 10 -> {early}, {late} 10"
    ]


def _fold(db, before, now, items):
    """`record_saved_lines` over hand-built queued row lines of one saved line."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.project_order_inquiry_service import (
        _HANDOVER_PENDING_KEY,
        ProjectOrderInquiryService,
    )

    pso_id = str(uuid4())
    line = SimpleNamespace(
        id=str(uuid4()), line_no=10, core_sales_order_line_id=None, delivery_date=None,
    )
    db.info[_HANDOVER_PENDING_KEY] = [
        {"row_id": str(uuid4()), "so_line_id": line.id, "pso_id": pso_id, **item}
        for item in items
    ]
    ProjectOrderInquiryService(db).record_saved_lines(pso_id=pso_id, saved=[(line, now, before)])
    (told,) = db.info[_HANDOVER_PENDING_KEY]
    return told["line"]["remark"]


def test_order_back_rows_taken_back_read_order_back_on_both_sides():
    """c19f2486: the right side names the rows' own kind too (an Order back folded into a
    fresh, smaller Order back), never plain ORDER."""
    from ._pg_fixture import blank_session

    before = _snap(_buy("10"), order_back=True, open_qty="10")
    now = _snap(_buy("8"), order_back=True, open_qty="8")
    with blank_session() as db:
        remark = _fold(db, before, now, [
            {"kind": "cancelled", "verb": "ORDER_BACK", "verb_keys": ["CANCEL_BALANCE"],
             "adds_order": "0", "line": {"qty": "0", "was": {"qty": "10"}}},
            {"kind": "raised", "verb": "ORDER_BACK", "verb_keys": ["ORDER_BACK"],
             "adds_order": "8", "line": {"qty": "8", "was": None}},
        ])
    assert remark == "CHANGED: ORDER BACK 10 -> ORDER BACK 8", remark


def test_a_borrow_hole_only_take_back_reads_order_back_not_order():
    """Crew audit: two Borrow holes cut from 6 + 4 to 4 + 4 with the line's own qty unchanged
    take back 2 at the donors: the rows' numbers read ORDER BACK, not a plain ORDER."""
    from ._pg_fixture import blank_session

    before = _snap(_borrow("6", "BRW-X"), _borrow("4", "BRW-Y"), open_qty="10")
    now = _snap(_borrow("4", "BRW-X"), _borrow("4", "BRW-Y"), open_qty="10")
    hole = {"kind": "settled", "verb": "ORDER_BACK", "verb_keys": ["CANCEL_BALANCE"],
            "adds_order": "0", "borrow_hole": True}
    with blank_session() as db:
        remark = _fold(db, before, now, [
            {**hole, "line": {"qty": "4", "was": {"qty": "6"}}},
            {**hole, "line": {"qty": "4", "was": {"qty": "4"}}},
        ])
    assert remark == "CHANGED: ORDER BACK 10 -> ORDER BACK 8", remark
    assert "ORDER 0" not in remark
