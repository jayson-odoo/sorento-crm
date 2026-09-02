"""G12 write-time claiming, and the three repairs that go with it (captain, 2 Sep 2026).

`PLAN-scm-reorder-oi-feedback-1sep.md` G12. The rule, stated strictly: the automatic pass
may take (a) pool-location documents and (b) project-bin lines explicitly attributed to the
row's OWN sales order. It NEVER takes a project-bin line that is unattributed or attributed
to somebody else, and it NEVER writes the attribution itself.

Attribution therefore has to arrive from somewhere the pass does not control, and this file
pins the two feeds that supply it plus what the buyer then sees:

  D1  the cascade writes no claim for a line it did not create
      (`tests/test_order_inquiry_dedication.py` holds the candidate-level half);
  D2  the outstanding PO/SPO book's `FromSODocList` column becomes a `po_upload` claim,
      idempotently, so a re-upload seeds dedication rather than doubling it;
  D3  the purchase order's "Allocated to" panel nets a dedication out of `Free` and names
      who holds it;
  D4  the one-shot repair that undoes the withdrawn born-claimed pass's own writes.

Plus the captain's own worry about the reorder plan: a plan Confirm lands its buy at a
PROJECT BIN (the buy lands where the demand is), and unless something attributes that line
to the rows that sized it the strict rule would refuse the very placement the buy was made
for. `supply_claim.claim_purchase_order_for_sizing_rows` is what closes that, in the same
transaction the confirm opens the line in.

`pg_session` (rolled back), with every row behind the `ZZTWTC` marker: the shared local
database is a copy of production and holds the captain's real book.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.services.scm import order_link_service, supply_claim
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTWTC"

SOON = date.today() + timedelta(days=45)


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    """A rolled-back session with the SCM suite's shared reference rows guaranteed.

    `ensure_reference_data` is not optional (CI's database has NO data): the builders this
    file borrows - `tests.scm.test_m3_run._mk_product`, `test_channel_read_model.
    _confirmed_leg` - resolve their FK targets with `LIMIT 1` off `products`, which finds
    something real on the local prod copy and returns None on an empty one.
    """
    from app.models.base import company_scope
    from tests.scm.conftest import SORENTO_COMPANY_ID, ensure_reference_data

    with pg_session() as session:
        ensure_reference_data(session)
        with company_scope(session, frozenset({SORENTO_COMPANY_ID})):
            yield session


def _project_bin(db, code: str) -> str:
    """A `segment = 'project'` warehouse - where a plan's buy for project demand lands, and
    the only segment G12's lock applies to."""
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


def _draft_line(db, *, product_id, warehouse_id, qty, po_id=None, number=None) -> tuple:
    """One `draft_recommendation` purchase order line - the shape a plan Confirm drafts and
    `bulk_confirm` turns into live supply."""
    po_id = po_id or _u()
    if number is None:
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
                "SELECT so_number, source, so_line_id FROM scm.order_link_claim "
                " WHERE po_line_id = :i ORDER BY so_number"
            ),
            {"i": line_id},
        )
    ]


def _linked(db, row_id) -> float:
    return float(
        db.execute(
            text(
                "SELECT COALESCE(SUM(qty), 0) FROM projects.order_inquiry_links "
                " WHERE row_id = :r"
            ),
            {"r": row_id},
        ).scalar()
        or 0
    )


def _so_ref(db, pso_id) -> str:
    """What `claim_identity` writes into a claim: the project order's AutoCount number
    where it has one, its provisional reference where it does not."""
    return db.execute(
        text(
            "SELECT COALESCE(autocount_doc_no, provisional_ref) "
            "  FROM projects.sales_orders WHERE id = :i"
        ),
        {"i": pso_id},
    ).scalar()


# ------------------------------------------------------------------ the captain's case


def _two_sizing_rows(db, *, bin_id):
    """SO X (30) and SO Y (84) of one product, both needing it at the SAME project bin -
    the plan row a 114 buy is sized from."""
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product

    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    x = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=30)
    y = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=84)
    return pid, x, y


def test_a_plan_confirm_claims_its_bin_line_for_both_rows_that_sized_it(db):
    """The captain's own worry (2 Sep 2026). A reorder plan's buy lands at a PROJECT BIN,
    because the buy lands where the demand is - so under the strict rule the confirm would
    refuse to place the very rows that sized it unless the line is attributed to them.

    One line of 114 at BRW-IB sized by SO X (30) and SO Y (84): TWO claims, both
    `crm_supply`, and both rows linked for their own quantity. One PO line, never two -
    the claim is an attribution, not a split.
    """
    actor = seed_user(db, None)
    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid, x, y = _two_sizing_rows(db, bin_id=bin_id)
    po_id, line_id = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=114)

    PurchaseOrderService(db).bulk_confirm([po_id], actor=actor)

    claims = _claims_on(db, line_id)
    assert {c["so_number"] for c in claims} == {
        _so_ref(db, x["pso"].id), _so_ref(db, y["pso"].id)
    }
    assert {c["source"] for c in claims} == {supply_claim.SOURCE}
    assert all(c["so_line_id"] for c in claims), (
        "an unresolved claim is invisible to dedication, so the attribution would do nothing"
    )
    assert _linked(db, x["inquiry_row"].id) == 30.0
    assert _linked(db, y["inquiry_row"].id) == 84.0
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM purchase_order_lines WHERE purchase_order_id = :p"
            ),
            {"p": po_id},
        ).scalar()
        == 1
    ), "the claim attributes the line, it does not split it"


def test_a_third_sales_order_cannot_auto_take_the_line_the_plan_bought_for_two_others(db):
    """The other half of the same case: SO Z, raised afterwards and needing the same
    product at the same bin, is refused the line - not cascadable, greyed with the SO that
    holds it - because nothing attributed it to Z.

    Confirmed with NO actor on purpose. The claim is written in the confirm's own
    transaction and does not depend on there being somebody to attribute a placement to, so
    this leaves the line CLAIMED and UNLINKED, which is exactly the state the Link dialog
    has to grey rather than offer.
    """
    from tests.scm.test_channel_read_model import _confirmed_leg
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid, x, y = _two_sizing_rows(db, bin_id=bin_id)
    po_id, line_id = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=114)

    PurchaseOrderService(db).bulk_confirm([po_id], actor=None)
    assert len(_claims_on(db, line_id)) == 2, "claims do not wait on an actor"

    z = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=10)
    z["inquiry_row"].stock_location = db.execute(
        text("SELECT warehouse_code FROM warehouses WHERE id = :i"), {"i": bin_id}
    ).scalar()
    db.flush()

    service = ProjectOrderInquiryService(db)
    candidate = next(
        c for c in service._candidates_for_row(z["inquiry_row"])
        if c["target_id"] == line_id
    )
    assert candidate["cascadable"] is False, "an unattributed bin line is not Z's to take"
    assert candidate["dedicated_to"] in {
        _so_ref(db, x["pso"].id), _so_ref(db, y["pso"].id)
    }
    assert candidate["remaining"] == 0, "both claims reserve the whole 114"


def test_the_cascade_never_claims_a_project_bin_line_it_did_not_create(db):
    """D1, the defect this round removes. PO 202607-S0067's 114 at BRW-IB was bought for
    SO391853 per the AutoCount book and was auto-linked to SO381895 at 02:47 on 2 Sep with
    a claim SO381895 had written for itself moments earlier.

    A project-bin line NOTHING attributed stays untaken and unclaimed, however good its
    location tier: the automatic pass may not manufacture its own permission.
    """
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    code = db.execute(
        text("SELECT warehouse_code FROM warehouses WHERE id = :i"), {"i": bin_id}
    ).scalar()
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    leg = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=30)
    leg["inquiry_row"].stock_location = code
    db.flush()

    # A line NOBODY raised off this codebase: the AutoCount book wrote it.
    po_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
            "source_system) VALUES (:i, :n, 'active', :d, 'MYR', 'scm_upload')"
        ),
        {"i": po_id, "n": f"{MARKER}-BOOK-{uuid.uuid4().hex[:6].upper()}",
         "d": date(2026, 7, 1)},
    )
    _, line_id = _draft_line(
        db, product_id=pid, warehouse_id=bin_id, qty=114, po_id=po_id, number="already"
    )

    ProjectOrderInquiryService(db).auto_place_for_products(
        [pid], actor_user_id=seed_user(db, None), trigger="test", include_awaiting=True,
    )

    assert _linked(db, leg["inquiry_row"].id) == 0.0, (
        "the cascade took an unattributed project-bin line"
    )
    assert _claims_on(db, line_id) == [], (
        "the cascade wrote itself the claim it then read - the theft G12 forbids"
    )

    # THE CONTROL, so the assertions above cannot pass because the cascade was never
    # reachable: attribute the SAME line to this row's own order and the same call places
    # it. Nothing else changes.
    core_line_id = db.execute(
        text(
            "SELECT core_sales_order_line_id FROM projects.sales_order_lines "
            " WHERE id = :i"
        ),
        {"i": str(leg["inquiry_row"].so_line_id)},
    ).scalar()
    # The DOCUMENT'S OWN number, never a made-up one (nit, review of PR #490): the claim's
    # identity is (company, SO, PO, item), so a claim naming a purchase order that does not
    # exist would be a different pairing from the one the book would have written, and the
    # control would prove nothing about the line under test.
    book_po_number = db.execute(
        text("SELECT po_number FROM purchase_orders WHERE id = :i"), {"i": po_id}
    ).scalar()
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=_so_ref(db, leg["pso"].id),
        po_number=book_po_number, item_code=leg["inquiry_row"].item_code,
        so_line_id=core_line_id, po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    ProjectOrderInquiryService(db).auto_place_for_products(
        [pid], actor_user_id=seed_user(db, None), trigger="test", include_awaiting=True,
    )
    assert _linked(db, leg["inquiry_row"].id) == 30.0, (
        "with the book's own attribution the identical pass places it"
    )


def test_one_claim_backing_two_links_on_one_document_is_netted_once(db):
    """The netting that decides how much of a claim is still to come.

    A claim's identity is (company, SO number, PO number, item) - a DOCUMENT-level
    pairing - so a row whose need is spread over TWO lines of one purchase order writes
    two links under the SAME claim, while the claim's own `po_line_id` names only one of
    them. Netting per (claim, line) rather than per CLAIM left the rest of the
    reservation reading as untaken and subtracted it a second time off whatever was left
    on that line, which is how a second sales order's row found its only candidate at 0
    remaining (`test_po_confirm_links_the_sizing_rows.py::test_a_purchase_order_naming_
    two_runs_falls_back_to_the_latest_completed`, half the time - the two lines tie on
    every sort key, so which one the first row starts on is a coin flip).

    Both lines at a POOL here on purpose: this is G7's arithmetic, not G12's lock.
    """
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    actor = seed_user(db, None)
    pool = _mk_warehouse(db, f"{MARKER}POOL{uuid.uuid4().hex[:5].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    first = _confirmed_leg(db, product_id=pid, warehouse_id=pool, buy_qty=5)
    second = _confirmed_leg(db, product_id=pid, warehouse_id=pool, buy_qty=3)

    po_id, _ = _draft_line(db, product_id=pid, warehouse_id=pool, qty=5)
    _draft_line(db, product_id=pid, warehouse_id=pool, qty=3, po_id=po_id,
                number="already")

    PurchaseOrderService(db).bulk_confirm([po_id], actor=actor)

    assert _linked(db, first["inquiry_row"].id) == 5.0
    assert _linked(db, second["inquiry_row"].id) == 3.0, (
        "the first row's own claim was subtracted a second time from what it had already "
        "taken, and the second row found nothing left"
    )
    claims = [
        r[0]
        for r in db.execute(
            text(
                "SELECT count(*) FROM scm.order_link_claim c "
                "  JOIN purchase_orders p ON p.po_number = c.po_number "
                " WHERE p.id = :i"
            ),
            {"i": po_id},
        )
    ]
    assert claims == [2], "one claim per sales order, whatever the line count"


# ------------------------------------------------------------------------------- D2


def _po_book(rows, headers) -> bytes:
    from tests.scm._outstanding_workbooks import po_workbook

    return po_workbook(rows, headers=headers)


_BOOK_HEADERS = (
    "PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "ETA", "STOCK LOCATION",
    "FromSODocList",
)


def test_the_outstanding_book_claims_every_line_its_from_so_column_names(db):
    """D2. The outstanding PO book states the pairing per LINE in `FromSODocList` and, until
    this round, the channel resolved that column and threw the value away - so the feed most
    attribution arrives on could not seed a single dedication.

    A `po_upload` claim per line, RESOLVED onto the line the same upload wrote, and a
    re-upload of the same book leaves exactly the same claims (the identity is
    SO + PO + item, `uq_scm_order_link_claim_identity`).
    """
    from app.services.scm import outstanding_import_service as svc
    from app.services.scm.outstanding_reader import PO
    from tests.scm._outstanding_workbooks import make_codes, seed_catalogue, seed_suppliers

    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:6].upper()}"

    book = _po_book(
        [
            (codes.main_po, codes.creditor_main, codes.item_rl, 114, SOON,
             codes.loc_project, so_number),
            # A line the book states no sales order for: it stays unattributed, which is
            # what the unclaimed-bin count exists to make visible.
            (codes.main_po, codes.creditor_main, codes.item_wt, 40, SOON,
             codes.loc_project, None),
        ],
        _BOOK_HEADERS,
    )

    first = svc.apply(db, book, doc_type=PO)
    assert first["ok"] is True
    assert first["so_links_claimed"] == 1

    claims = [
        dict(r._mapping)
        for r in db.execute(
            text(
                "SELECT so_number, item_code, source, po_line_id "
                "  FROM scm.order_link_claim WHERE po_number = :p"
            ),
            {"p": codes.main_po},
        )
    ]
    assert len(claims) == 1
    assert claims[0]["so_number"] == so_number
    assert claims[0]["item_code"] == codes.item_rl
    assert claims[0]["source"] == order_link_service.SOURCE_PO_UPLOAD
    assert claims[0]["po_line_id"], "the claim resolved onto the line this upload wrote"

    second = svc.apply(db, book, doc_type=PO)
    assert second["so_links_claimed"] == 1
    assert (
        db.execute(
            text("SELECT count(*) FROM scm.order_link_claim WHERE po_number = :p"),
            {"p": codes.main_po},
        ).scalar()
        == 1
    ), "a re-upload restates the pairing, it does not double it"


def test_a_book_upload_never_relabels_a_claim_another_feed_already_made(db):
    """The idempotency the captain asked for from the other side: a line the reorder plan's
    own confirm already claimed (`crm_supply`) keeps that provenance when the book restates
    the same pairing. The first feed to state a pairing is the one that knows it, and the
    one-shot repair reads the source to tell a real attribution from the cascade's own
    helping itself."""
    from app.services.scm import outstanding_import_service as svc
    from app.services.scm.outstanding_reader import PO
    from tests.scm._outstanding_workbooks import make_codes, seed_catalogue, seed_suppliers

    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:6].upper()}"

    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=so_number, po_number=codes.main_po,
        item_code=codes.item_rl, so_line_id=None,
        source=order_link_service.SOURCE_CRM_SUPPLY,
    )
    db.flush()

    svc.apply(
        db,
        _po_book(
            [(codes.main_po, codes.creditor_main, codes.item_rl, 114, SOON,
              codes.loc_project, so_number)],
            _BOOK_HEADERS,
        ),
        doc_type=PO,
    )

    sources = [
        r[0]
        for r in db.execute(
            text("SELECT source FROM scm.order_link_claim WHERE po_number = :p"),
            {"p": codes.main_po},
        )
    ]
    assert sources == [order_link_service.SOURCE_CRM_SUPPLY]


# ------------------------------------------------------------------------------- D3


def test_the_allocated_to_panel_nets_a_dedication_out_of_free_and_names_it(db):
    """D3. 202607-S0067's BRW-IB line printed `Free 69` while the AutoCount book dedicated
    the whole 114 to SO391853 - which is how the same quantity gets bought twice.

    `Free` now nets what other sales orders' claims still reserve, and the block names who
    holds it. The claiming order's LIVE outstanding is what reserves (G7), so a settled
    line reserves nothing.
    """
    from app.models.procurement import PurchaseOrder
    from tests.scm.test_channel_read_model import _core_so_line
    from tests.scm.test_m3_run import _mk_product

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=114)
    db.execute(
        text("UPDATE purchase_orders SET status = 'active' WHERE id = :i"), {"i": po_id}
    )

    claiming_so, claiming_line = _core_so_line(
        db, product_id=pid, warehouse_id=bin_id, qty=114, demand_class="project",
    )
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=claiming_so.so_number, po_number=f"{MARKER}-x",
        item_code=None, so_line_id=str(claiming_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
    block = next(
        b for b in PurchaseOrderService(db)._allocations_for(po) if b["line_id"] == line_id
    )
    assert block["outstanding"] == 114.0
    assert block["allocated"] == 0.0
    assert block["free"] == 0.0, "a line the book dedicates elsewhere is not free to buy on"
    assert [d["so_number"] for d in block["dedicated_to"]] == [claiming_so.so_number]
    assert block["dedicated_to"][0]["reserved"] == 114.0

    # The claiming order ships: the claim row stays, the reservation does not (G7). With
    # nothing left to report the line drops out of the panel entirely, which is the same
    # rule an unlinked, undedicated line has always been read by.
    claiming_line.qty_delivered = 114
    db.flush()
    blocks = PurchaseOrderService(db)._allocations_for(po)
    assert [b for b in blocks if b["line_id"] == line_id] == [], (
        "a settled claim reserves nothing and dedicates nothing"
    )


# ------------------------------------------------------------------------------- D4


def test_the_repair_undoes_the_born_claimed_pass_and_spares_a_real_attribution(db):
    """D4. Two automatic placements on project-bin lines, identical but for their evidence:
    one whose only claim is the self-written `order_inquiry` row the withdrawn born-claimed
    pass made for itself, one the BOOK attributes to the same order.

    `today` takes the first and leaves the second. A human link (`auto = false`) is never
    touched in either scope.
    """
    import importlib.util
    import os

    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts", "repair_project_bin_self_claims.py",
    )
    spec = importlib.util.spec_from_file_location("_repair_pbsc", path)
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")

    stolen = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=30)
    kept = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=20)
    manual = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=10)
    _, stolen_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=30)
    _, kept_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=20)
    _, manual_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=10)

    def _link(row, line_id, qty, *, claim_source, auto, claimed_at):
        claim_id = _u()
        db.execute(
            text(
                "INSERT INTO scm.order_link_claim (id, so_number, po_number, item_code, "
                "source, claimed_at, po_line_id, resolved_at) "
                "VALUES (:i, :son, :pon, NULL, :src, :at, :pol, now())"
            ),
            {"i": claim_id, "son": _so_ref(db, row["pso"].id),
             "pon": f"{MARKER}-{uuid.uuid4().hex[:6]}", "src": claim_source,
             "at": claimed_at, "pol": line_id},
        )
        db.execute(
            text(
                "INSERT INTO projects.order_inquiry_links (id, row_id, po_line_id, "
                "document, qty, auto, claim_id, linked_at) "
                "VALUES (:i, :r, :pol, :doc, :q, :auto, :c, :at)"
            ),
            {"i": _u(), "r": str(row["inquiry_row"].id), "pol": line_id,
             "doc": f"{MARKER}-doc", "q": qty, "auto": auto, "c": claim_id,
             "at": claimed_at},
        )
        db.flush()

    born = datetime(2026, 9, 2, 2, 47, 49)
    _link(stolen, stolen_line, 30, claim_source="order_inquiry", auto=True, claimed_at=born)
    _link(kept, kept_line, 20, claim_source="po_upload", auto=True, claimed_at=born)
    _link(manual, manual_line, 10, claim_source="order_inquiry", auto=False,
          claimed_at=born)

    found = {f["link_id"] for f in repair._find(db, "today")}
    assert len(found) == 1
    repair._repair(db, "today", apply=True)

    assert _linked(db, stolen["inquiry_row"].id) == 0.0, "the self-claimed take is undone"
    assert _claims_on(db, stolen_line) == [], "and so is the claim it wrote for itself"
    assert _linked(db, kept["inquiry_row"].id) == 20.0, "the book justified this one"
    assert _linked(db, manual["inquiry_row"].id) == 10.0, "a human link is never touched"

    assert repair._find(db, "today") == [], "idempotent: a second run finds nothing"


# ---------------------------------------------------- review round 2 (B1-B4, S1-S3)


def test_a_placement_on_another_line_never_repoints_the_books_claim(db):
    """B1. A claim's identity is DOCUMENT-level - (company, SO, PO, item) - while its
    `po_line_id` names ONE line of that document. `claim_placed_on_po` used to overwrite
    that pointer on every placement, so linking a row to line B of a purchase order moved
    the book's own claim off line A, the line it bought: A was left carrying no claim at
    all, which under G12 means unattributed and locked to the automatic pass for ever.

    Worst on a `po_history` claim with a NULL `item_code`, which matches every item on the
    order and so was repointed by any placement anywhere on it.
    """
    from tests.scm.test_channel_read_model import _core_so_line
    from tests.scm.test_m3_run import _mk_product

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_a = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=50)
    _, line_b = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=50,
                            po_id=po_id, number="already")
    po_number = db.execute(
        text("SELECT po_number FROM purchase_orders WHERE id = :i"), {"i": po_id}
    ).scalar()

    so, so_line = _core_so_line(db, product_id=pid, warehouse_id=bin_id, qty=50,
                                demand_class="project")
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=so.so_number, po_number=po_number,
        item_code=None, so_line_id=str(so_line.id), po_line_id=line_a,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    # The SAME pairing restated while a placement lands on the OTHER line.
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=so.so_number, po_number=po_number,
        item_code=None, so_line_id=str(so_line.id), po_line_id=line_b,
    )
    db.flush()

    pointed_at = db.execute(
        text("SELECT po_line_id FROM scm.order_link_claim WHERE po_number = :p"),
        {"p": po_number},
    ).scalar()
    assert str(pointed_at) == line_a, (
        "the placement repointed the book's claim off the line the book bought"
    )


def test_a_sales_order_lines_need_is_reserved_once_across_its_documents(db):
    """B2, first shape. SO line of 100 with 70 placed on PO-A and 10 on PO-B still needs
    20 - so 20 is reserved, once, on the first document in order. Reserving the whole live
    outstanding per claim gave 30 + 90 = 120 against that 20, and made PO-B read as fully
    spoken for when 90 of it was free.
    """
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse

    actor = seed_user(db, None)
    pool = _mk_warehouse(db, f"{MARKER}POOL{uuid.uuid4().hex[:5].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")

    leg = _confirmed_leg(db, product_id=pid, warehouse_id=pool, buy_qty=100)
    row = leg["inquiry_row"]
    row.item_code = db.execute(
        text("SELECT product_code FROM products WHERE id = :i"), {"i": pid}
    ).scalar()
    db.flush()

    po_a, line_a = _draft_line(db, product_id=pid, warehouse_id=pool, qty=100)
    po_b, line_b = _draft_line(db, product_id=pid, warehouse_id=pool, qty=100)
    PurchaseOrderService(db).bulk_confirm([po_a, po_b], actor=actor)

    # Place 70 on A and 10 on B by hand, so the row has 20 of its 100 still to find.
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    service = ProjectOrderInquiryService(db)
    for link in service._links_of(str(row.id)):
        db.delete(link)
    db.flush()
    service.refresh_link_state([row])
    db.flush()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        str(row.id),
        [{"po_line_id": line_a, "qty": 70}, {"po_line_id": line_b, "qty": 10}],
        actor_user_id=actor,
    )

    reservations = order_link_service.reservations_by_target(
        db, target_ids=[line_a, line_b]
    )
    total = sum(
        float(c["reserved"]) for claims in reservations.values() for c in claims
    )
    assert total == 20.0, (
        "the line's unplaced need is reserved ONCE across its documents, not per claim"
    )


def test_a_partial_link_on_a_pool_line_does_not_reserve_more_than_the_line_holds(db):
    """B2, second shape. A claim can never reserve more of a document than the document
    has: the reservation is capped at that line's own open capacity. A 200-unit sales
    order line that has placed 10 on a 30-unit pool line reserves at most the 30, not the
    190 it still needs everywhere else in the world."""
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse

    actor = seed_user(db, None)
    pool = _mk_warehouse(db, f"{MARKER}POOL{uuid.uuid4().hex[:5].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")

    leg = _confirmed_leg(db, product_id=pid, warehouse_id=pool, buy_qty=200)
    row = leg["inquiry_row"]
    row.item_code = db.execute(
        text("SELECT product_code FROM products WHERE id = :i"), {"i": pid}
    ).scalar()
    db.flush()

    po_id, line_id = _draft_line(db, product_id=pid, warehouse_id=pool, qty=30)
    PurchaseOrderService(db).bulk_confirm([po_id], actor=actor)

    reservations = order_link_service.reservations_by_target(db, target_ids=[line_id])
    reserved = sum(float(c["reserved"]) for c in reservations.get(line_id, []))
    assert reserved <= 30.0, (
        "a claim reserved more of the document than the document holds"
    )


def test_a_person_may_link_a_fully_dedicated_line_by_hand(db):
    """B3, AC-6.5's "manual override stays". The dialog greys a dedicated line and still
    offers it, and G12's whole answer for an unattributed project bin is "link it
    manually" - but the validation measured a manual allocation against the
    dedication-reduced `remaining`, so exactly those links came back 409. A person is
    measured against what the line ACTUALLY has left."""
    from tests.scm.test_channel_read_model import _confirmed_leg, _core_so_line
    from tests.scm.test_m3_run import _mk_product
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=40)
    db.execute(text("UPDATE purchase_orders SET status = 'active' WHERE id = :i"),
               {"i": po_id})
    po_number = db.execute(
        text("SELECT po_number FROM purchase_orders WHERE id = :i"), {"i": po_id}
    ).scalar()

    # Somebody else's order claims the whole line.
    other, other_line = _core_so_line(db, product_id=pid, warehouse_id=bin_id, qty=40,
                                      demand_class="project")
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=other.so_number, po_number=po_number,
        item_code=None, so_line_id=str(other_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    leg = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=10)
    row = leg["inquiry_row"]
    service = ProjectOrderInquiryService(db)
    candidate = next(
        c for c in service._candidates_for_row(row, manual=True)
        if c["target_id"] == line_id
    )
    assert candidate["remaining"] == 0, "the automatic pass sees nothing left"
    assert candidate["raw_remaining"] == 40, "no link has taken any of it"

    ProjectOrderInquiryService(db).place_on_po_allocations(
        str(row.id), [{"po_line_id": line_id, "qty": 10}], actor_user_id=None,
    )

    assert _linked(db, row.id) == 10.0, "the override the dialog offers was refused"
    note = db.execute(
        text("SELECT note FROM projects.order_inquiry_rows WHERE id = :i"),
        {"i": str(row.id)},
    ).scalar()
    assert po_number in (note or ""), "a manual override is audited like any placement"


def test_an_unresolvable_claim_is_never_stamped_resolved(db):
    """S3. `resolve()` only ever looks at claims where `resolved_at IS NULL`, and
    dedication reads only claims it can join through `so_line_id`. Stamping a claim
    resolved before its sales line is known therefore retired it permanently: invisible to
    both. Reachable through `supply_claim` whenever a project line carries no
    `core_sales_order_line_id` yet."""
    claim = order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:6].upper()}",
        po_number=f"{MARKER}-PO-{uuid.uuid4().hex[:6].upper()}", item_code=None,
        so_line_id=None, po_line_id=None,
        source=order_link_service.SOURCE_CRM_SUPPLY,
    )
    db.flush()
    assert claim.resolved_at is None, (
        "a claim with neither side found was retired before the resolver could finish it"
    )


def test_the_today_repair_leaves_a_claimless_orphan_link_alone(db):
    """S2. `today` is scoped to the born-claimed pass's own signature - a self-written
    `order_inquiry` claim from the cut-off onward. Its NOT EXISTS half is vacuously true
    of a link whose line carries NO claim at all, which is every pre-claims-era automatic
    link, so without the matching EXISTS this scope swept those up too - before the book
    upload that is meant to justify them, and against its own docstring."""
    import importlib.util
    import os

    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts", "repair_project_bin_self_claims.py",
    )
    spec = importlib.util.spec_from_file_location("_repair_s2", path)
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    orphan = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=12)
    _, line_id = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=12)
    db.execute(
        text(
            "INSERT INTO projects.order_inquiry_links (id, row_id, po_line_id, document, "
            "qty, auto, claim_id, linked_at) "
            "VALUES (:i, :r, :pol, :doc, 12, true, NULL, :at)"
        ),
        {"i": _u(), "r": str(orphan["inquiry_row"].id), "pol": line_id,
         "doc": f"{MARKER}-orphan", "at": datetime(2026, 8, 1, 9, 0, 0)},
    )
    db.flush()

    company_id = repair.default_company_id(db)
    found = {f["link_id"] for f in repair._find(db, "today", company_id)}
    assert not found, "the claimless orphan is legacy's to judge, after the book upload"
    assert any(
        str(f["row_id"]) == str(orphan["inquiry_row"].id)
        for f in repair._find(db, "legacy", company_id)
    ), "and legacy does see it"
