"""Crew finding (11 Nov, db3 + AutoCount): a sales order created from the CRM never said which
quotation it came from, so AutoCount showed no "transferred from" and the quotation's outstanding
qty never dropped. AutoCount carries the link per ROW (FromDocType QT, FromDocNo, FromDocDtlKey;
never on the SO header); SS takes it as `fromQuotation {docNo, dtlKey}` on each create line.

Each SO line made from a quotation line (`quotation_line_id`) whose quotation is in AutoCount, in
the same book, carries `fromQuotation`: the AutoCount quotation's DocNo and the DtlKey of its row
for that item, read from AutoCount at create time (one GET, the same item-code matching the
quotation update uses). A line not from a quotation carries none; a partial transfer carries it
with the SO line's own qty.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests._ac_write_support import (
    BASE,
    BOOK,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    api_fixture,
    build_qt_world,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
)

QT_KEY = 7001
QT_DOC = f"{QT_CREATE_PATH}/{QT_KEY}"


@pytest.fixture
def api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def _url(world) -> str:
    return f"{BASE}/sales-orders/{world.order.id}/autocount"


def _quotation_in_autocount(db, world, *, book=BOOK, doc_key=QT_KEY):
    """A CRM quotation already created in AutoCount as QT-000042; its first line is line 1's item."""
    from app.models.projects import ProjectQuotationLine

    qt = build_qt_world(db, world.company_id, world.owner, debtor_code=f"ZZT-QTD-{world.order.id[:4]}")
    qt.document.autocount_doc_no = "QT-000042"
    qt.document.autocount_doc_key = str(doc_key) if doc_key else None
    qt.document.autocount_book = book
    quoted = (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id == qt.version.id)
        .order_by(ProjectQuotationLine.sort_order)
        .first()
    )
    world.line1.quotation_line_id = quoted.id
    db.commit()
    return qt


def _ac_quotation(fake_ss, world, rows):
    fake_ss.answers[("GET", QT_DOC)] = (200, done_body(doc_no="QT-000042", doc_key=QT_KEY, details=rows))


def _create(client, fake_ss, world):
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())
    response = client.post(_url(world))
    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    return fake_ss.body(request)["lines"]


def test_a_line_from_the_quotation_carries_its_autocount_row(api, fake_ss):
    client, db, world = api
    _quotation_in_autocount(db, world)
    code = world.product.product_code
    _ac_quotation(fake_ss, world, [
        detail(9001, "ZZT-OTHER", "2", "10.00", "BRW-BB", None, 1),
        detail(9002, code, "200", "12.00", "BRW-BB", None, 2),
    ])

    lines = _create(client, fake_ss, world)

    assert lines[0]["fromQuotation"] == {"docNo": "QT-000042", "dtlKey": 9002}
    assert "fromQuotation" not in lines[1], "line 2 was not made from a quotation line"
    [read] = fake_ss.to("GET", QT_DOC)
    assert read.url.params["companyCode"] == "SRT"


def test_a_partial_transfer_carries_the_link_with_the_so_lines_own_qty(api, fake_ss):
    client, db, world = api
    _quotation_in_autocount(db, world)
    world.line1.qty = Decimal("40")
    db.commit()
    _ac_quotation(fake_ss, world, [detail(9002, world.product.product_code, "200", "12.00", "BRW-BB", None, 1)])

    lines = _create(client, fake_ss, world)

    assert lines[0]["fromQuotation"] == {"docNo": "QT-000042", "dtlKey": 9002}
    assert Decimal(str(lines[0]["qty"])) == 40


def test_no_link_when_the_quotation_is_not_in_autocount(api, fake_ss):
    client, db, world = api
    _quotation_in_autocount(db, world, doc_key=None)

    lines = _create(client, fake_ss, world)

    assert all("fromQuotation" not in line for line in lines)
    assert fake_ss.to("GET", QT_DOC) == []


def test_no_link_when_the_quotation_is_in_another_book(api, fake_ss):
    """R8: a link names a row in the book the SO lands in, never another."""
    client, db, world = api
    _quotation_in_autocount(db, world, book="db1")

    lines = _create(client, fake_ss, world)

    assert all("fromQuotation" not in line for line in lines)
    assert fake_ss.to("GET", QT_DOC) == []


def test_no_link_when_autocount_holds_no_row_for_the_item(api, fake_ss):
    client, db, world = api
    _quotation_in_autocount(db, world)
    _ac_quotation(fake_ss, world, [detail(9001, "ZZT-OTHER", "2", "10.00", "BRW-BB", None, 1)])

    lines = _create(client, fake_ss, world)

    assert "fromQuotation" not in lines[0]
