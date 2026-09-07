"""`scripts/dedupe_spo_number_format.py` - the plain/typo SPO spelling merge.

Runs on the real database through `pg_session` (rolled back), same substrate as
`test_backfill_retire_superseded_order_inquiry_rows.py`. Every SPO number this file mints
uses year 2099 (real data tops out well before that) plus a random 4-digit sequence, and
every `run()` call passes an explicit `spo_filter` - the shared local Postgres holds real
production rows under `spo_allocations`/`purchase_orders`, and an unfiltered scan would both
be slow and, on `--apply`, touch documents this test knows nothing about.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import date
from pathlib import Path

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    PickingHeader,
    PickingLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import OrderInquiry, OrderInquiryLink, OrderInquiryRow, ProjectSalesOrder
from app.models.scm import OrderLinkClaim
from app.services.company_scope import DEFAULT_COMPANY_ID

import scripts.dedupe_spo_number_format as dedupe
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZT"


def _u() -> str:
    return str(uuid.uuid4())


def _seq4() -> str:
    return f"{random.randint(0, 9999):04d}"


def _new_plain() -> str:
    """`SPO-yyyymm-xxxx` - the CRM-conversion shape, before its numbering fix."""
    return f"SPO-2099{random.randint(1, 12):02d}-{_seq4()}"


def _slash_of(plain: str) -> str:
    """`SPO-yyyymm-xxxx` -> `SPO-yyyy/mm-xxxx` - the canonical (book) spelling."""
    body = plain[len("SPO-"):]
    ymm, seq = body.split("-")
    return f"SPO-{ymm[:4]}/{ymm[4:]}-{seq}"


def _typo_of(slash: str) -> str:
    """`SPO-yyyy/mm-xxxx` -> `SPO-yyyy4/mm-xxxx` - the book-upload typo shape (a stray
    digit before the slash), exactly `SPO-20254/12-0074`'s own shape."""
    body = slash[len("SPO-"):]
    year, rest = body.split("/")
    return f"SPO-{year}4/{rest}"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db():
    with pg_session(autoflush=False) as session:
        # A script run has no request and no principal - `None` is the sanctioned
        # system / all-companies scope, mirroring what `main()` itself sets.
        set_company_scope(session, None)
        yield session


@pytest.fixture()
def world(db):
    """Shared masters (category, uom) plus factories for everything a document needs."""
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}", category_name=f"{MARKER} cat"
    )
    uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER[:2]}{uuid.uuid4().hex[:6]}", uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()

    def product(suffix: str = "A") -> Product:
        p = Product(
            id=_u(), product_code=f"{MARKER}-ITEM-{suffix}-{uuid.uuid4().hex[:6]}",
            product_name=f"{MARKER} item {suffix}", category_id=cat.id, base_uom_id=uom.id,
            list_price=0, is_active=True,
        )
        db.add(p)
        db.flush()
        return p

    def warehouse(suffix: str = "A") -> Warehouse:
        w = Warehouse(
            id=_u(), warehouse_code=f"{MARKER[:3]}{suffix}{uuid.uuid4().hex[:6]}"[:50],
            warehouse_name=f"{MARKER} wh {suffix}", is_active=True, counts_as_available=True,
        )
        db.add(w)
        db.flush()
        return w

    return {"db": db, "company_id": DEFAULT_COMPANY_ID, "product": product, "warehouse": warehouse}


def _alloc(world, spo_number, line_number, product, warehouse=None, qty=10, **extra):
    db = world["db"]
    a = SPOAllocation(
        id=_u(), company_id=world["company_id"], spo_number=spo_number, spo_line_number=line_number,
        product_id=product.id, warehouse_id=warehouse.id if warehouse else None,
        allocated_quantity=qty,
        quantity_received=extra.pop("quantity_received", 0),
        receipt_status=extra.pop("receipt_status", "pending"),
        **extra,
    )
    db.add(a)
    db.flush()
    return a


def _po_header(world, po_number, **extra):
    db = world["db"]
    po = PurchaseOrder(
        id=_u(), company_id=world["company_id"], po_number=po_number, status="active", **extra
    )
    db.add(po)
    db.flush()
    return po


def _po_line(world, po, product, qty_ordered=10, **extra):
    db = world["db"]
    line = PurchaseOrderLine(
        id=_u(), company_id=world["company_id"], purchase_order_id=po.id, product_id=product.id,
        qty_ordered=qty_ordered, qty_received=0, line_status="open", **extra,
    )
    db.add(line)
    db.flush()
    return line


def _shipment(world) -> InboundShipment:
    db = world["db"]
    s = InboundShipment(
        id=_u(), company_id=world["company_id"], shipment_number=unique_code("SHP")[:50],
        shipment_date=date(2099, 1, 1),
    )
    db.add(s)
    db.flush()
    return s


def _picking_line(world, alloc, product, qty=5) -> PickingLine:
    db = world["db"]
    header = PickingHeader(
        id=_u(), company_id=world["company_id"], picking_number=unique_code("GRN"),
        picking_type="goods_received", picking_status="approved", inspection_status="pending",
    )
    db.add(header)
    db.flush()
    line = PickingLine(
        id=_u(), company_id=world["company_id"], picking_header_id=header.id,
        spo_allocation_id=alloc.id, product_id=product.id,
        quantity_expected=qty, quantity_picked=qty,
    )
    db.add(line)
    db.flush()
    return line


def _order_inquiry_link(world, alloc, document) -> OrderInquiryLink:
    """The `projects.order_inquiry_links` chain, built with the minimum each parent needs."""
    db = world["db"]
    pso = ProjectSalesOrder(
        id=_u(), company_id=world["company_id"], provisional_ref=unique_code("PSO")
    )
    db.add(pso)
    db.flush()
    oi = OrderInquiry(
        id=_u(), company_id=world["company_id"], project_sales_order_id=pso.id,
        inquiry_no=unique_code("OI")[:20],
    )
    db.add(oi)
    db.flush()
    row = OrderInquiryRow(
        id=_u(), company_id=world["company_id"], order_inquiry_id=oi.id, qty=1, verb="ORDER"
    )
    db.add(row)
    db.flush()
    link = OrderInquiryLink(
        id=_u(), company_id=world["company_id"], row_id=row.id, spo_allocation_id=alloc.id,
        document=document, qty=1,
    )
    db.add(link)
    db.flush()
    return link


def _order_link_claim(world, alloc) -> OrderLinkClaim:
    db = world["db"]
    claim = OrderLinkClaim(
        id=_u(), company_id=world["company_id"], so_number=unique_code("SO"),
        po_number=alloc.spo_number, source="manual", spo_allocation_id=alloc.id,
    )
    db.add(claim)
    db.flush()
    return claim


# --------------------------------------------------------------------------- #
# Step A - solo rename, no twin
# --------------------------------------------------------------------------- #


def test_a_solo_plain_spelling_is_renamed_with_no_twin(world):
    """Header + lines + allocations, no twin anywhere: rename in place, nothing deleted,
    a rerun is a no-op."""
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)

    po = _po_header(world, plain)
    line = _po_line(world, po, product, qty_ordered=5)
    a1 = _alloc(world, plain, 1, product, qty=5)
    a2 = _alloc(world, plain, 2, product, qty=7)

    result = dedupe.run(db, apply=True, spo_filter=[plain, target])

    assert result["merged_docs"] == 0
    # `renamed` counts distinct (table, value) candidates, not rows: one for
    # purchase_orders.po_number, one for spo_allocations.spo_number (a1 and a2 share it).
    assert result["renamed"] == 2

    db.expire_all()
    po_after = db.query(PurchaseOrder).filter(PurchaseOrder.id == po.id).one()
    assert po_after.po_number == target
    line_after = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == line.id).one()
    assert line_after.purchase_order_id == po.id, "the line was never touched, only its header"
    a1_after = db.query(SPOAllocation).filter(SPOAllocation.id == a1.id).one()
    a2_after = db.query(SPOAllocation).filter(SPOAllocation.id == a2.id).one()
    assert a1_after.spo_number == target
    assert a2_after.spo_number == target

    rerun = dedupe.run(db, apply=True, spo_filter=[plain, target])
    assert rerun["renamed"] == 0
    assert rerun["merged_docs"] == 0


# --------------------------------------------------------------------------- #
# Step B - genuine twins
# --------------------------------------------------------------------------- #


def test_a_twin_with_identical_lines_merges_and_repoints_every_fk(world):
    """P is deleted; S carries P's provenance; every FK anywhere in the database that
    pointed at P's allocation now points at S, and none is NULL."""
    db = world["db"]
    product = world["product"]()
    warehouse = world["warehouse"]()
    plain = _new_plain()
    target = _slash_of(plain)

    s_alloc = _alloc(world, target, 1, product, warehouse, qty=10)
    p_alloc = _alloc(world, plain, 1, product, warehouse, qty=10)
    shipment = _shipment(world)
    p_alloc.inbound_shipment_id = shipment.id
    p_alloc.created_by = _u()
    db.flush()

    picking = _picking_line(world, p_alloc, product)
    link = _order_inquiry_link(world, p_alloc, plain)
    claim = _order_link_claim(world, p_alloc)

    result = dedupe.run(db, apply=True, spo_filter=[plain, target])

    assert result["merged_docs"] == 1
    db.expire_all()
    assert db.query(SPOAllocation).filter(SPOAllocation.id == p_alloc.id).first() is None

    s_after = db.query(SPOAllocation).filter(SPOAllocation.id == s_alloc.id).one()
    assert str(s_after.inbound_shipment_id) == str(shipment.id)
    assert s_after.created_by is not None

    picking_after = db.query(PickingLine).filter(PickingLine.id == picking.id).one()
    assert str(picking_after.spo_allocation_id) == str(s_alloc.id)
    link_after = db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link.id).one()
    assert str(link_after.spo_allocation_id) == str(s_alloc.id)
    claim_after = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim.id).one()
    assert str(claim_after.spo_allocation_id) == str(s_alloc.id)


def test_a_product_only_p_has_is_moved_not_deleted(world):
    """P names a product S has never seen: that allocation and PO line are MOVED under
    S, never dropped, and the empty P header follows once its lines are gone."""
    db = world["db"]
    common = world["product"]("common")
    only_p = world["product"]("onlyp")
    warehouse = world["warehouse"]()
    plain = _new_plain()
    target = _slash_of(plain)

    s_alloc = _alloc(world, target, 1, common, warehouse, qty=10)
    p_alloc_common = _alloc(world, plain, 1, common, warehouse, qty=10)
    p_alloc_only = _alloc(world, plain, 2, only_p, warehouse, qty=3)

    po_s = _po_header(world, target)
    _po_line(world, po_s, common, qty_ordered=10)
    po_p = _po_header(world, plain)
    po_p_line_common = _po_line(world, po_p, common, qty_ordered=10)
    po_p_line_only = _po_line(world, po_p, only_p, qty_ordered=3)

    dedupe.run(db, apply=True, spo_filter=[plain, target])
    db.expire_all()

    assert db.query(SPOAllocation).filter(SPOAllocation.id == p_alloc_common.id).first() is None
    assert db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == po_p_line_common.id).first() is None

    only_after = db.query(SPOAllocation).filter(SPOAllocation.id == p_alloc_only.id).one()
    assert only_after.spo_number == target, "moved onto the survivor number, not deleted"
    s_after = db.query(SPOAllocation).filter(SPOAllocation.id == s_alloc.id).one()
    assert only_after.spo_line_number != s_after.spo_line_number, (
        "the fresh line number must not collide with the survivor line it was matched around"
    )

    line_only_after = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == po_p_line_only.id).one()
    assert str(line_only_after.purchase_order_id) == str(po_s.id)

    # every P line is accounted for (matched or moved), so the empty P header is gone
    assert db.query(PurchaseOrder).filter(PurchaseOrder.id == po_p.id).first() is None
    assert db.query(PurchaseOrder).filter(PurchaseOrder.id == po_s.id).first() is not None


def test_s_with_more_lines_than_p_keeps_the_union(world):
    """S already has more lines than P states: every P line matches or moves, S's count
    is the union of both, nothing lost."""
    db = world["db"]
    warehouse = world["warehouse"]()
    plain = _new_plain()
    target = _slash_of(plain)

    products = [world["product"](f"L{i}") for i in range(5)]
    for i, product in enumerate(products):
        _alloc(world, target, i + 1, product, warehouse, qty=10)
    p_allocs = [
        _alloc(world, plain, i + 1, products[i], warehouse, qty=10) for i in range(2)
    ]

    dedupe.run(db, apply=True, spo_filter=[plain, target])
    db.expire_all()

    remaining = db.query(SPOAllocation).filter(SPOAllocation.spo_number == target).all()
    assert len(remaining) == 5, "S's count is the union - nothing lost, nothing duplicated"
    for p in p_allocs:
        assert db.query(SPOAllocation).filter(SPOAllocation.id == p.id).first() is None


def test_typo_spelling_merges_into_its_target(world):
    """`SPO-20254/12-0074`'s own shape: the typo shares no `_spo_match_key` with its
    target, so this exercises the exact-string mapping rather than key grouping."""
    db = world["db"]
    product = world["product"]()
    slash = _slash_of(_new_plain())
    typo = _typo_of(slash)

    s_alloc = _alloc(world, slash, 1, product, qty=5)
    p_alloc = _alloc(world, typo, 1, product, qty=5)

    result = dedupe.run(db, apply=True, spo_filter=[typo, slash])

    assert result["merged_docs"] == 1
    db.expire_all()
    assert db.query(SPOAllocation).filter(SPOAllocation.id == p_alloc.id).first() is None
    remaining = db.query(SPOAllocation).filter(SPOAllocation.spo_number == slash).all()
    assert [r.id for r in remaining] == [s_alloc.id]


# --------------------------------------------------------------------------- #
# dry run / idempotency / rollback
# --------------------------------------------------------------------------- #


def test_dry_run_changes_nothing_but_emits_the_json(world):
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)
    _alloc(world, target, 1, product, qty=5)
    _alloc(world, plain, 1, product, qty=5)

    before = {
        r.id: r.spo_number
        for r in db.query(SPOAllocation).filter(SPOAllocation.spo_number.in_([plain, target])).all()
    }

    result = dedupe.run(db, apply=False, spo_filter=[plain, target])

    db.expire_all()
    after = {
        r.id: r.spo_number
        for r in db.query(SPOAllocation).filter(SPOAllocation.spo_number.in_([plain, target])).all()
    }
    assert before == after, "a dry run must change no row"
    assert result["merged_docs"] == 1

    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    data = json.loads(backup_path.read_text())
    assert data["dry_run"] is True
    backup_path.unlink()


def test_a_second_apply_run_finds_nothing_left_to_do(world):
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)
    _alloc(world, target, 1, product, qty=5)
    _alloc(world, plain, 1, product, qty=5)

    first = dedupe.run(db, apply=True, spo_filter=[plain, target])
    assert first["merged_docs"] == 1

    second = dedupe.run(db, apply=True, spo_filter=[plain, target])
    assert second["merged_docs"] == 0
    assert second["renamed"] == 0


def test_a_forced_failure_mid_run_rolls_back_everything(world, monkeypatch):
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)
    s_alloc = _alloc(world, target, 1, product, qty=5)
    p_alloc = _alloc(world, plain, 1, product, qty=5)

    def _snapshot():
        db.expire_all()
        rows = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.id.in_([s_alloc.id, p_alloc.id]))
            .order_by(SPOAllocation.id)
            .all()
        )
        return [(r.id, r.spo_number, r.spo_line_number, r.allocated_quantity) for r in rows]

    before = _snapshot()

    def _boom(*_a, **_k):
        raise RuntimeError("simulated crash mid-merge")

    monkeypatch.setattr(db, "delete", _boom)

    with pytest.raises(RuntimeError, match="simulated crash"):
        with db.begin_nested():
            dedupe.run(db, apply=True, spo_filter=[plain, target])

    after = _snapshot()
    assert before == after, "a forced failure must leave every row exactly as it was"
    assert len(after) == 2, "nothing was actually deleted"
