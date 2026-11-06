"""AC-QTSO-CRM Phase 2: update an AutoCount sales order from a published amendment.

UAC U10-U13, R3. Route: `POST /api/v1/project-sales/sales-orders/amendments/{amendment_id}/autocount`.

The rows are the real producer's (`ProjectSODeltaService`, verbs ORDER, RESERVE & ORDER, ADVANCE,
DELAY, CHANGE SO NO, CANCEL BALANCE). ORDER / RESERVE & ORDER (qty up on an existing line) PATCH
the line's qty to `to_value`; ADVANCE / DELAY PATCH deliveryDate; CHANGE SO NO waits; CANCEL
BALANCE waits while `_SEND_CANCEL_BALANCE_AS_QTY_EDIT` is False (owner pending) and goes as a qty
edit down to `to_value` when it is True. A new product never arrives as a row (the delta service
reports it in `unmatched`). The PATCH's key is `crm-amd-{id}-update-edit`, stable across retries.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import ProjectSalesOrderLine
from tests._ac_write_support import (
    BOOK,
    BASE,
    DOC_KEY,
    DTL_1,
    DTL_2,
    EDIT,
    LAST_MODIFIED,
    SO_CREATE_PATH,
    VIEW,
    WAITING,
    WRITE,
    add_amendment,
    advance_row,
    api_fixture,
    cancel_balance_row,
    change_so_no_row,
    delay_row,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    caps_with,
    myt_today_candidates,
    order_row,
    put_in_autocount,
    refused_body,
    reserve_row,
)

DTL_3 = 12011
DOC_PATH = f"{SO_CREATE_PATH}/{DOC_KEY}"
LINES_PATH = f"{DOC_PATH}/lines"


@pytest.fixture
def api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def D(value) -> Decimal:
    return Decimal(str(value))


def _third_line(db, world):
    """A third project line, already in AutoCount as dtl 12011 (the one a REMOVE_LINE names)."""
    from app.models.order import SalesOrder

    from tests.test_project_so_draft import _product

    # Its own product: one item on two lines would (rightly) wait for a hand change.
    product3 = _product(db, f"ZZT-P3-{uuid.uuid4().hex[:6]}")
    line = ProjectSalesOrderLine(
        id=str(uuid.uuid4()), company_id=world.company_id,
        project_sales_order_id=world.order.id, line_no=world.line2.line_no + 1,
        product_id=product3.id, description="Third line", qty=Decimal("7"), uom="UNIT",
        unit_price=Decimal("5.00"), amount=Decimal("35.00"), delivery_date=date(2026, 9, 1),
        stock_location="MWH-BB",
    )
    db.add(line)
    db.flush()
    core_order = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=core_order.id, product_id=product3.id,
        qty_ordered=Decimal("7"), qty_delivered=Decimal("0"), required_date=date(2026, 9, 1),
        source_system="autocount", source_ref=f"AED_SRT:{DOC_KEY}:{DTL_3}",
    )
    core.company_id = world.company_id
    db.add(core)
    db.flush()
    line.core_sales_order_line_id = core.id
    db.flush()
    return line


def _answer_edits(fake_ss, *, patch=None):
    after = [
        detail(DTL_1, "X1", "120", "392.85", "BRW-BB", "2026-07-01", 1),
        detail(DTL_2, "X2", "20", "50.00", "MWH-BB", "2027-01-07", 2),
    ]
    fake_ss.answers[("PATCH", DOC_PATH)] = patch or (
        200, done_body(details=after, last_modified="2026-11-05T11:00:00")
    )


def _setup_mixed(db, world):
    """ORDER (qty up) and DELAY go; CHANGE SO NO and CANCEL BALANCE (third line) do not."""
    put_in_autocount(db, world)
    line3 = _third_line(db, world)
    amendment = add_amendment(
        db,
        world,
        [
            order_row(world, world.line1, "120"),
            delay_row(world, world.line2, "2027-01-07"),
            change_so_no_row(world, world.line2),
            cancel_balance_row(world, line3, "0"),
        ],
    )
    db.commit()
    return amendment, line3


def _url(amendment) -> str:
    return f"{BASE}/sales-orders/amendments/{amendment.id}/autocount"


def _calls_after_setup(fake_ss):
    return [r for r in fake_ss.calls if r.url.path != "/api/v1/autocount/write-capabilities"]


# --------------------------------------------------------------------------- U11 / U12: the mixed amendment


def test_order_and_delay_rows_go_as_one_patch_with_docdate_expected_last_modified_and_dtlkeys(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    response = client.post(_url(amendment))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", DOC_PATH)
    body = fake_ss.body(patch)
    assert body["companyCode"] == "SRT"
    assert body["docDate"] in myt_today_candidates()
    assert body["expectedLastModified"] == LAST_MODIFIED
    by_key = {str(l["dtlKey"]): l for l in body["lines"]}
    assert set(by_key) == {str(DTL_1), str(DTL_2)}, "CHANGE SO NO and CANCEL BALANCE must not ride the PATCH"
    assert D(by_key[str(DTL_1)]["qty"]) == 120
    assert by_key[str(DTL_2)]["deliveryDate"] == "2027-01-07"
    assert patch.headers["Idempotency-Key"] == f"crm-amd-{amendment.id}-update-edit"
    assert fake_ss.to("POST", LINES_PATH) == [], "a new product is never a row, so no add-line"


def test_reserve_and_order_and_advance_go_as_patch_edits(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(
        db,
        world,
        [reserve_row(world, world.line1, "130"), advance_row(world, world.line2, "2026-06-01")],
    )
    db.commit()
    _answer_edits(fake_ss)

    client.post(_url(amendment))

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    by_key = {str(l["dtlKey"]): l for l in fake_ss.body(patch)["lines"]}
    assert D(by_key[str(DTL_1)]["qty"]) == 130
    assert by_key[str(DTL_2)]["deliveryDate"] == "2026-06-01"


def test_change_so_no_and_cancel_balance_are_listed_as_waiting_and_never_deleted(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    assert [w["verb"] for w in body["waiting"]] == ["CHANGE SO NO", "CANCEL BALANCE"]
    assert all(w["reason"] == WAITING for w in body["waiting"])
    assert [r for r in fake_ss.calls if r.method == "DELETE"] == []
    assert all("cancel" not in r.url.path for r in fake_ss.calls)
    assert all(str(DTL_3) not in r.content.decode() for r in fake_ss.writes())


def test_cancel_balance_goes_as_a_qty_edit_when_the_owner_switch_is_on(api, fake_ss, monkeypatch):
    from app.services import project_autocount_write_service as svc

    monkeypatch.setattr(svc, "_SEND_CANCEL_BALANCE_AS_QTY_EDIT", True)
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    by_key = {str(l["dtlKey"]): l for l in fake_ss.body(patch)["lines"]}
    assert D(by_key[str(DTL_3)]["qty"]) == 0
    assert [w["verb"] for w in body["waiting"]] == ["CHANGE SO NO"]


def test_cancel_balance_waits_when_the_owner_switch_is_off(api, fake_ss, monkeypatch):
    from app.services import project_autocount_write_service as svc

    monkeypatch.setattr(svc, "_SEND_CANCEL_BALANCE_AS_QTY_EDIT", False)
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    assert str(DTL_3) not in {str(l["dtlKey"]) for l in fake_ss.body(patch)["lines"]}
    assert "CANCEL BALANCE" in [w["verb"] for w in body["waiting"]]


def test_done_lists_the_read_back_stores_last_modified_and_marks_the_step(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    assert body["outcome"] == "done"
    assert body["lines"], "the dialog lists AutoCount's read-back lines"
    db.refresh(world.order)
    db.refresh(amendment)
    assert world.order.autocount_last_modified == "2026-11-05T11:00:00"
    assert world.order.autocount_doc_no == "SO412345"
    assert amendment.autocount_edit_sent_at is not None


def test_a_second_press_after_done_makes_no_call_and_answers_already(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)
    client.post(_url(amendment))
    calls = len(fake_ss.calls)

    second = client.post(_url(amendment))

    assert second.status_code == 200
    assert second.json()["outcome"] == "done"
    assert second.json()["message"] == "Already in AutoCount."
    assert len(fake_ss.calls) == calls, "a second press replays nothing"
    assert [w["verb"] for w in second.json()["waiting"]] == ["CHANGE SO NO", "CANCEL BALANCE"]


def test_a_refused_patch_retried_sends_the_same_key_and_body_and_marks_only_on_done(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss, patch=(422, refused_body("ITEM_LOCKED", "Item locked")))
    client.post(_url(amendment))
    db.refresh(amendment)
    assert amendment.autocount_edit_sent_at is None
    _answer_edits(fake_ss)

    client.post(_url(amendment))

    first, second = fake_ss.to("PATCH", DOC_PATH)
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert first.content == second.content
    db.refresh(amendment)
    assert amendment.autocount_edit_sent_at is not None


def test_a_declined_row_is_not_sent(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(
        db, world, [order_row(world, world.line1, "120"), delay_row(world, world.line2, "2027-01-07")]
    )
    amendment.row_decisions = {"0": {"decision": "declined", "reason": "customer reversed"}}
    db.commit()
    _answer_edits(fake_ss)

    client.post(_url(amendment))

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    keys = {str(l["dtlKey"]) for l in fake_ss.body(patch)["lines"]}
    assert keys == {str(DTL_2)}


def test_an_amendment_of_only_waiting_rows_makes_no_write_call(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [change_so_no_row(world, world.line2)])
    db.commit()
    _answer_edits(fake_ss)

    response = client.post(_url(amendment))

    assert WAITING in response.text
    assert fake_ss.writes() == []


def test_a_line_with_no_core_line_yet_waits_for_the_next_sync(api, fake_ss):
    """After a CRM create the core lines arrive with the next AutoCount sync: no dtlKey yet."""
    client, db, world = api
    put_in_autocount(db, world)
    world.line1.core_sales_order_line_id = None
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()

    body = client.post(_url(amendment)).json()

    assert [w["reason"] for w in body["waiting"]] == ["Waiting for the next AutoCount sync"]
    assert fake_ss.writes() == []


def test_edit_doc_off_in_the_feed_keeps_the_edits_waiting_with_its_reason(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    fake_ss.answers[("GET", "/api/v1/autocount/write-capabilities")] = (
        200, {"book": BOOK, "capabilities": caps_with(edit_doc=(False, "WRITE_DISABLED"))}
    )

    body = client.post(_url(amendment)).json()

    assert fake_ss.writes() == []
    assert "Changes to AutoCount are switched off here" in [w["reason"] for w in body["waiting"]]


def test_a_recovered_answer_writes_nothing_to_the_crm(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    recovered = {**done_body(), "outcome": "recovered"}
    _answer_edits(fake_ss, patch=(200, recovered))

    body = client.post(_url(amendment)).json()

    assert body["outcome"] != "done"
    db.refresh(world.order)
    db.refresh(amendment)
    assert world.order.autocount_last_modified == LAST_MODIFIED
    assert amendment.autocount_edit_sent_at is None


def test_the_feed_is_read_not_hard_coded(api, fake_ss):
    """U14 applies here too: the capability read is what gates the edits."""
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    client.post(_url(amendment))

    assert fake_ss.to("GET", "/api/v1/autocount/write-capabilities")


# --------------------------------------------------------------------------- adopted orders


def _adopt(db, world):
    """Keyed by hand from the import file and adopted by ingest: a doc number and a core order
    whose source_ref is `{database}:{DocKey}`, but no CRM-held key or last-modified."""
    put_in_autocount(db, world)
    core = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core.source_ref = f"AED_SRT:{DOC_KEY}"
    world.order.autocount_doc_key = None
    world.order.autocount_last_modified = None
    db.commit()


def test_an_adopted_order_shows_in_autocount_on_the_wire(api, fake_ss):
    client, db, world = api
    _adopt(db, world)

    response = client.get(f"{BASE}/sales-orders/{world.order.id}")

    assert response.status_code == 200, response.text
    assert '"in_autocount":true' in response.text.replace(" ", "")


def test_an_adopted_order_updates_with_its_core_keys_after_reading_the_document(api, fake_ss):
    client, db, world = api
    _adopt(db, world)
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()
    fake_ss.answers[("GET", DOC_PATH)] = (
        200, done_body(details=[], last_modified="2026-10-30T07:00:00")
    )
    # SS names the order's book (owner ruling R7), so the adopted order may be updated.
    fake_ss.answers[("GET", "/api/v1/autocount/write-capabilities")] = (
        200, {"book": "AED_SRT", "capabilities": caps_with()}
    )
    _answer_edits(fake_ss)

    response = client.post(_url(amendment))

    assert response.status_code == 200, response.text
    assert len(fake_ss.to("GET", DOC_PATH)) == 1, "no stored last-modified, so it is read first"
    [patch] = fake_ss.to("PATCH", DOC_PATH)
    body = fake_ss.body(patch)
    assert body["expectedLastModified"] == "2026-10-30T07:00:00"
    assert [str(l["dtlKey"]) for l in body["lines"]] == [str(DTL_1)]


def test_a_non_numeric_core_key_is_not_in_autocount(api, fake_ss):
    client, db, world = api
    _adopt(db, world)
    core = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core.source_ref = "AED_SRT:12008/../x"
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()

    response = client.post(_url(amendment))

    assert response.status_code == 409
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- U12: DOC_STALE


def test_doc_stale_says_changed_in_autocount_since_the_stored_date_and_changes_nothing(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss, patch=(409, refused_body("DOC_STALE", "document changed since expectedLastModified")))

    response = client.post(_url(amendment))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "refused"
    assert body["message"] == "Changed in AutoCount since 01/10/2026, open Compare first."
    db.refresh(world.order)
    assert world.order.autocount_last_modified == LAST_MODIFIED


# --------------------------------------------------------------------------- U13


def test_qty_below_transferred_is_shown_as_autocounts_refusal_and_changes_nothing(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(
        fake_ss,
        patch=(422, refused_body("QTY_BELOW_TRANSFERRED", "Qty 80 is below the 100 already delivered")),
    )

    body = client.post(_url(amendment)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == (
        "AutoCount refused: Qty 80 is below the 100 already delivered. Nothing was changed."
    )
    db.refresh(world.order)
    db.refresh(world.line1)
    assert world.order.autocount_last_modified == LAST_MODIFIED
    assert world.line1.qty == Decimal("100")


# --------------------------------------------------------------------------- U10: eligibility


def test_an_order_not_in_autocount_gets_409_and_no_call(api, fake_ss):
    client, db, world = api
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()

    response = client.post(_url(amendment))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_an_amendment_that_is_not_published_gets_409_and_no_call(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")], status="proposed")
    db.commit()

    response = client.post(_url(amendment))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_an_unknown_amendment_is_an_application_404(api, fake_ss):
    client, _db, _world = api

    response = client.post(f"{BASE}/sales-orders/amendments/{uuid.uuid4()}/autocount")

    assert response.status_code == 404
    assert response.json().get("code"), response.text
    assert fake_ss.calls == []


def test_the_dtl_key_is_resolved_on_the_server_never_taken_from_the_request(api, fake_ss):
    client, db, world = api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    client.post(_url(amendment), json={"docKey": 1, "expectedLastModified": "1999-01-01", "companyCode": "MCH"})

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    body = fake_ss.body(patch)
    assert body["companyCode"] == "SRT"
    assert body["expectedLastModified"] == LAST_MODIFIED


# --------------------------------------------------------------------------- fix round 2: one item on several lines


def _second_line_of_the_same_product(db, world):
    """A set split can leave one product on two lines: line 1's product again, as dtl 12011."""
    line = ProjectSalesOrderLine(
        id=str(uuid.uuid4()), company_id=world.company_id,
        project_sales_order_id=world.order.id, line_no=world.line2.line_no + 1,
        product_id=world.product.id, description="Same product again", qty=Decimal("7"), uom="UNIT",
        unit_price=Decimal("5.00"), amount=Decimal("35.00"), delivery_date=date(2026, 9, 1),
        stock_location="MWH-BB",
    )
    db.add(line)
    db.flush()
    core_order = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=core_order.id, product_id=world.product.id,
        qty_ordered=Decimal("7"), qty_delivered=Decimal("0"), required_date=date(2026, 9, 1),
        source_system="autocount", source_ref=f"AED_SRT:{DOC_KEY}:{DTL_3}",
    )
    core.company_id = world.company_id
    db.add(core)
    db.flush()
    line.core_sales_order_line_id = core.id
    db.flush()
    return line


SPLIT_REASON = "This item is on more than one line; change it in AutoCount by hand"


def test_a_qty_row_for_an_item_on_several_lines_waits_but_its_date_row_still_goes(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    _second_line_of_the_same_product(db, world)
    amendment = add_amendment(
        db,
        world,
        [order_row(world, world.line1, "120"), delay_row(world, world.line1, "2027-01-07")],
    )
    db.commit()
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    [line] = fake_ss.body(patch)["lines"]
    assert str(line["dtlKey"]) == str(DTL_1) and "qty" not in line
    assert line["deliveryDate"] == "2027-01-07"
    assert [(w["verb"], w["reason"]) for w in body["waiting"]] == [("ORDER", SPLIT_REASON)]


def test_cancel_balance_for_an_item_on_several_lines_waits_when_the_switch_is_on(api, fake_ss, monkeypatch):
    from app.services import project_autocount_write_service as svc

    monkeypatch.setattr(svc, "_SEND_CANCEL_BALANCE_AS_QTY_EDIT", True)
    client, db, world = api
    put_in_autocount(db, world)
    _second_line_of_the_same_product(db, world)
    amendment = add_amendment(db, world, [cancel_balance_row(world, world.line1, "0")])
    db.commit()

    body = client.post(_url(amendment)).json()

    assert fake_ss.writes() == []
    assert [w["reason"] for w in body["waiting"]] == [SPLIT_REASON]


def test_the_change_list_marks_which_rows_the_crm_can_send(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    _second_line_of_the_same_product(db, world)
    amendment = add_amendment(
        db,
        world,
        [
            order_row(world, world.line1, "120"),                 # item on two lines: no
            delay_row(world, world.line1, "2027-01-07"),          # yes
            order_row(world, world.line2, "30"),                  # yes
            change_so_no_row(world, world.line2),                 # no
            cancel_balance_row(world, world.line2, "0"),          # no (owner switch off)
        ],
    )
    db.commit()

    response = client.get(f"{BASE}/amendments/{amendment.id}/autocount-change-list")

    assert response.status_code == 200, response.text
    assert [(r["verb"], r["autocount_sendable"]) for r in response.json()["rows"]] == [
        ("ORDER", False), ("DELAY", True), ("ORDER", True), ("CHANGE SO NO", False), ("CANCEL BALANCE", False),
    ]
