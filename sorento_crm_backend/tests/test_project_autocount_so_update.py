"""AC-QTSO-CRM Phase 2, RED: update an AutoCount sales order from a published amendment.

UAC U10-U13, R3. Route: `POST /api/v1/project-sales/sales-orders/amendments/{amendment_id}/autocount`.

Plan, "Update SO (U10-U13)": the rows of the published amendment's accepted AutoCount change
list. QTY_CHANGE -> PATCH line qty; ADVANCE / DELAY -> PATCH line deliveryDate; ADD_LINE ->
POST lines; any other verb -> `waiting` with no call while the feed keeps delete_line / cancel_doc
off. PATCH body `{companyCode, header{docDate}, expectedLastModified, lines[{dtlKey, ...}]}`,
dtlKey = the last `:` segment of the core SO line's `source_ref`.

Delta row shape (from `ProjectSODeltaService`): `{so_line_id, line_no, product_code, description,
verb, field, from_value, to_value}`; the new verbs QTY_CHANGE / ADD_LINE / REMOVE_LINE are the
constants in `app.models.project_so`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.order import SalesOrderLine
from app.models.project_so import ProjectSalesOrderLine
from tests._ac_write_support import (
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
    add_row,
    api_fixture,
    delay_row,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    find_dicts,
    myt_today_candidates,
    put_in_autocount,
    qty_row,
    refused_body,
    remove_row,
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

    line = ProjectSalesOrderLine(
        id=str(uuid.uuid4()), company_id=world.company_id,
        project_sales_order_id=world.order.id, line_no=world.line2.line_no + 1,
        product_id=world.product2.id, description="Third line", qty=Decimal("7"), uom="UNIT",
        unit_price=Decimal("5.00"), amount=Decimal("35.00"), delivery_date=date(2026, 9, 1),
        stock_location="MWH-BB",
    )
    db.add(line)
    db.flush()
    core_order = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=core_order.id, product_id=world.product2.id,
        qty_ordered=Decimal("7"), qty_delivered=Decimal("0"), required_date=date(2026, 9, 1),
        source_system="autocount", source_ref=f"AED_SRT:{DOC_KEY}:{DTL_3}",
    )
    core.company_id = world.company_id
    db.add(core)
    db.flush()
    line.core_sales_order_line_id = core.id
    db.flush()
    return line


def _answer_edits(fake_ss, *, patch=None, post=None):
    after = [
        detail(DTL_1, "X1", "80", "392.85", "BRW-BB", "2026-07-01", 1),
        detail(DTL_2, "X2", "20", "50.00", "MWH-BB", "2027-01-07", 2),
    ]
    fake_ss.answers[("PATCH", DOC_PATH)] = patch or (
        200, done_body(details=after, last_modified="2026-11-05T11:00:00")
    )
    fake_ss.answers[("POST", LINES_PATH)] = post or (
        200, done_body(details=after + [detail(12099, "NEW", "5", "10.00", "BRW-BB", "2026-09-01", 3)],
                       last_modified="2026-11-05T11:05:00")
    )


def _setup_mixed(db, world):
    put_in_autocount(db, world)
    line3 = _third_line(db, world)
    amendment = add_amendment(
        db,
        world,
        [
            qty_row(world, world.line1, "80"),
            delay_row(world.line2, "2027-01-07"),
            add_row(world, "5"),
            remove_row(line3),
        ],
    )
    db.commit()
    return amendment


def _url(amendment) -> str:
    return f"{BASE}/sales-orders/amendments/{amendment.id}/autocount"


# --------------------------------------------------------------------------- U11 / U12: the mixed amendment


def test_qty_and_date_rows_go_as_one_patch_with_docdate_expected_last_modified_and_dtlkeys(api, fake_ss):
    client, db, world = api
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    response = client.post(_url(amendment))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", DOC_PATH)
    body = fake_ss.body(patch)
    assert body["companyCode"] == "SRT"
    assert body["header"]["docDate"] in myt_today_candidates()
    assert body["expectedLastModified"] == LAST_MODIFIED
    by_key = {str(l["dtlKey"]): l for l in body["lines"]}
    assert set(by_key) == {str(DTL_1), str(DTL_2)}, "REMOVE_LINE and ADD_LINE must not ride the PATCH"
    assert D(by_key[str(DTL_1)]["qty"]) == 80
    assert by_key[str(DTL_2)]["deliveryDate"] == "2027-01-07"
    assert patch.headers["Idempotency-Key"] == f"crm-amd-{amendment.id}-update"


def test_an_added_line_goes_as_a_post_lines_with_its_item_and_qty(api, fake_ss):
    client, db, world = api
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    client.post(_url(amendment))

    [post] = fake_ss.to("POST", LINES_PATH)
    sent = fake_ss.body(post)
    assert sent["companyCode"] == "SRT"
    assert find_dicts(sent, itemCode=world.product.product_code, qty="5"), sent
    assert post.headers["Idempotency-Key"]


def test_remove_line_is_listed_as_waiting_and_never_deleted(api, fake_ss):
    client, db, world = api
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    assert [w["verb"] for w in body["waiting"]] == ["REMOVE_LINE"]
    assert body["waiting"][0]["reason"] == WAITING
    assert [r for r in fake_ss.calls if r.method == "DELETE"] == []
    assert all("cancel" not in r.url.path for r in fake_ss.calls)
    assert all(str(DTL_3) not in r.content.decode() for r in fake_ss.writes())


def test_done_lists_the_read_back_and_stores_the_new_last_modified(api, fake_ss):
    client, db, world = api
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    body = client.post(_url(amendment)).json()

    assert body["outcome"] == "done"
    assert body["lines"], "the dialog lists AutoCount's read-back lines"
    db.refresh(world.order)
    assert world.order.autocount_last_modified == "2026-11-05T11:05:00"
    assert world.order.autocount_doc_no == "SO412345"


def test_a_declined_row_is_not_sent(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(
        db, world, [qty_row(world, world.line1, "80"), delay_row(world.line2, "2027-01-07")]
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
    line3 = _third_line(db, world)
    amendment = add_amendment(db, world, [remove_row(line3)])
    db.commit()
    _answer_edits(fake_ss)

    response = client.post(_url(amendment))

    assert WAITING in response.text
    assert fake_ss.writes() == []


def test_the_feed_is_read_not_hard_coded(api, fake_ss):
    """U14 applies here too: the capability read is what keeps REMOVE_LINE waiting."""
    client, db, world = api
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    client.post(_url(amendment))

    assert fake_ss.to("GET", "/api/v1/autocount/write-capabilities")


# --------------------------------------------------------------------------- U12: DOC_STALE


def test_doc_stale_says_changed_in_autocount_since_the_stored_date_and_changes_nothing(api, fake_ss):
    client, db, world = api
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss, patch=(409, refused_body("DOC_STALE", "document changed since expectedLastModified")))

    response = client.post(_url(amendment))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "refused"
    assert body["message"] == "Changed in AutoCount since 01/10/2026, open Compare first."
    assert fake_ss.to("POST", LINES_PATH) == [], "no add-line after a stale refusal"
    db.refresh(world.order)
    assert world.order.autocount_last_modified == LAST_MODIFIED


# --------------------------------------------------------------------------- U13


def test_qty_below_transferred_is_shown_as_autocounts_refusal_and_changes_nothing(api, fake_ss):
    client, db, world = api
    amendment = _setup_mixed(db, world)
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
    amendment = add_amendment(db, world, [qty_row(world, world.line1, "80")])
    db.commit()

    response = client.post(_url(amendment))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_an_amendment_that_is_not_published_gets_409_and_no_call(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [qty_row(world, world.line1, "80")], status="proposed")
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
    amendment = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    client.post(_url(amendment), json={"docKey": 1, "expectedLastModified": "1999-01-01", "companyCode": "MCH"})

    [patch] = fake_ss.to("PATCH", DOC_PATH)
    body = fake_ss.body(patch)
    assert body["companyCode"] == "SRT"
    assert body["expectedLastModified"] == LAST_MODIFIED
