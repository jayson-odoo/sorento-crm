"""AC-6.14 + AC-6.15 (G12/G13, captain 2 Sep 2026), the combined case the coder's own
suites test in isolation but never together: a reorder plan's Confirm write-claims a
project-bin line for the two sales orders that sized it (`tests/scm/test_write_time_
supply_claim.py`), and the outstanding PO/SPO book restates the SAME document later
(`_claim_stated_so_links`, tested there only against a single hand-seeded claim).

This file is the round trip: bulk_confirm's TWO `crm_supply` claims (X, Y) have to survive
a REAL outstanding-book upload of the SAME purchase order untouched - no third claim, no
source relabelled, no duplicate on a second identical upload. The two are never both
statable in one `FromSODocList` cell (`outstanding_import_service._clean_so` refuses a
cell naming more than one order on purpose - see that module's docstring), so the book here
states only X, which is the harder case: Y's claim has to survive on evidence the book
never repeats.

The PO number reused between the confirm and the book is the "adoption" path
(`outstanding_import_service.apply`, the `header.source_system not in ("", "scm_upload")`
branch), not the CRM<->AutoCount supersession path (`_supersede_crm_raised_pos`), which only
fires for a DIFFERENT document number naming the same (product, supplier) - reusing the
literal number is what a buyer does when AutoCount is keyed under the CRM's own suggested
number, and the header flips to `scm_upload` before the supersession scan runs, so it never
becomes its own candidate.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.services.scm import order_link_service, supply_claim
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTWTCB"

SOON = date.today() + timedelta(days=45)


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    from app.models.base import company_scope
    from tests.scm.conftest import SORENTO_COMPANY_ID, ensure_reference_data

    with pg_session() as session:
        ensure_reference_data(session)
        with company_scope(session, frozenset({SORENTO_COMPANY_ID})):
            yield session


def _project_bin(db, code: str) -> str:
    wid = _u()
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "segment, created_at, updated_at) "
            "VALUES (:i, :c, :c, true, 'project', now(), now())"
        ),
        {"i": wid, "c": code},
    )
    db.flush()
    return wid


def _draft_line(db, *, product_id, warehouse_id, qty) -> tuple:
    po_id = _u()
    number = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, status, issue_date, "
            "currency, source_system) "
            "VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', 'scm_recommendation')"
        ),
        {"i": po_id, "n": number, "d": date(2026, 8, 1)},
    )
    line_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status, "
            "expected_date) VALUES (:i, :po, :p, :w, :q, 0, 10, 'MYR', 'open', :e)"
        ),
        {"i": line_id, "po": po_id, "p": product_id, "w": warehouse_id, "q": qty,
         "e": SOON},
    )
    db.flush()
    return po_id, line_id


def _claims_on(db, line_id) -> list[dict]:
    return [
        dict(r._mapping)
        for r in db.execute(
            text(
                "SELECT so_number, source, po_line_id FROM scm.order_link_claim "
                " WHERE po_line_id = :i ORDER BY so_number"
            ),
            {"i": line_id},
        )
    ]


def _so_ref(db, pso_id) -> str:
    return db.execute(
        text(
            "SELECT COALESCE(autocount_doc_no, provisional_ref) "
            "  FROM projects.sales_orders WHERE id = :i"
        ),
        {"i": pso_id},
    ).scalar()


def _two_sizing_rows(db, *, bin_id):
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product

    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    x = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=30)
    y = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=84)
    return pid, x, y


def test_ac_6_14_and_ac_6_15_a_book_reupload_of_the_confirmed_po_leaves_both_claims(db):
    """AC-6.14: bulk_confirm writes ONE line, TWO `crm_supply` claims (X 30, Y 84), both
    rows linked. AC-6.15: an outstanding-PO book later naming the SAME document (adoption,
    not supersession) and restating only X's pairing - the one `FromSODocList` cell it can
    honestly state - leaves BOTH claims exactly as they were: X's source untouched (a
    pairing another feed already made keeps ITS source), Y's claim untouched on evidence
    the book never repeats, no third claim, one line. A second identical upload changes
    nothing (idempotent).
    """
    from app.services.scm import outstanding_import_service as svc
    from app.services.scm.outstanding_reader import PO
    from tests.scm._outstanding_workbooks import po_workbook

    actor = seed_user(db, None)
    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    bin_code = db.execute(
        text("SELECT warehouse_code FROM warehouses WHERE id = :i"), {"i": bin_id}
    ).scalar()
    pid, x, y = _two_sizing_rows(db, bin_id=bin_id)
    product_code = db.execute(
        text("SELECT product_code FROM products WHERE id = :i"), {"i": pid}
    ).scalar()
    # `_confirmed_leg` (a test helper, not the production writer) never stamps
    # `OrderInquiryRow.item_code` - production DOES (`project_supply_service.py`,
    # `fact.item_code`), and `claim_identity` reads it for the claim's own identity
    # column. Left NULL here, the crm_supply claim below and the book's po_upload claim
    # differ only in that one column and the unique index treats NULL as never equal to
    # itself, so a "restated" pairing mints a THIRD claim instead of finding the first -
    # exactly the failure this test caught before this line existed.
    x["inquiry_row"].item_code = product_code
    y["inquiry_row"].item_code = product_code
    db.flush()
    po_id, line_id = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=114)

    PurchaseOrderService(db).bulk_confirm([po_id], actor=actor)

    before = _claims_on(db, line_id)
    assert {c["so_number"] for c in before} == {_so_ref(db, x["pso"].id), _so_ref(db, y["pso"].id)}
    assert {c["source"] for c in before} == {supply_claim.SOURCE}

    confirmed_po_number = db.execute(
        text("SELECT po_number FROM purchase_orders WHERE id = :i"), {"i": po_id}
    ).scalar()
    assert confirmed_po_number != f"{MARKER}-", "bulk_confirm stamps a real canonical number"

    creditor = f"{MARKER}-CR-{uuid.uuid4().hex[:6].upper()}"
    db.execute(
        text(
            "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active) "
            "VALUES (:i, :c, :c, true)"
        ),
        {"i": _u(), "c": creditor},
    )
    db.flush()

    headers = ("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "ETA",
              "STOCK LOCATION", "FromSODocList")
    book = po_workbook(
        [(confirmed_po_number, creditor, product_code, 114, SOON, bin_code,
          _so_ref(db, x["pso"].id))],
        headers=headers,
    )

    first = svc.apply(db, book, doc_type=PO)
    assert first["ok"] is True

    after = _claims_on(db, line_id)
    assert len(after) == 2, "no third claim was minted for the pairing the book restated"
    assert {c["so_number"] for c in after} == {c["so_number"] for c in before}
    assert {c["source"] for c in after} == {supply_claim.SOURCE}, (
        "the book upload must not relabel a claim another feed already made - "
        "including Y's, which the book never states at all"
    )
    assert all(str(c["po_line_id"]) == line_id for c in after), (
        "still the one line, never split"
    )
    line_count = db.execute(
        text("SELECT count(*) FROM purchase_order_lines WHERE purchase_order_id = :p"),
        {"p": po_id},
    ).scalar()
    assert line_count == 1, (
        "the book restating an unchanged quantity must not fork a second line"
    )
    header_source_system = db.execute(
        text("SELECT source_system FROM purchase_orders WHERE id = :i"), {"i": po_id}
    ).scalar()
    assert header_source_system == "scm_upload", (
        "the ADOPTION path (same document number) ran, not the CRM<->AutoCount "
        "supersession path, which would have closed this line instead of updating it"
    )

    second = svc.apply(db, book, doc_type=PO)
    assert second["ok"] is True
    assert len(_claims_on(db, line_id)) == 2, "a second identical upload is a no-op"
