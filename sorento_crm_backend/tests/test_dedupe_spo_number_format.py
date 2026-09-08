"""`scripts/dedupe_spo_number_format.py` - the plain/typo SPO spelling merge.

Runs on the real database through `pg_session` (rolled back), same substrate as
`test_backfill_retire_superseded_order_inquiry_rows.py`. Every SPO number this file mints
uses year 2099 (real data tops out well before that) plus a random 4-digit sequence, and
every `run()` call passes an explicit `spo_filter` - the shared local Postgres holds real
production rows under `spo_allocations`/`purchase_orders`, and an unfiltered scan would both
be slow and, on `--apply`, touch documents this test knows nothing about. Every `run()` call
also passes `out_dir=str(tmp_path)` so the backup JSON never lands in the real `scripts/out/`.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session as SASession

import app.database as database_module
from app.models.base import set_company_scope
from app.models.company import Company
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
def world(db, tmp_path):
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

    return {
        "db": db, "company_id": DEFAULT_COMPANY_ID, "product": product, "warehouse": warehouse,
        "out_dir": str(tmp_path),
    }


def _run(world, apply, spo_filter):
    """`dedupe.run` with this test's throwaway backup directory (T6) - never touches the
    real `scripts/out/`."""
    return dedupe.run(world["db"], apply=apply, spo_filter=spo_filter, out_dir=world["out_dir"])


def _alloc(world, spo_number, line_number, product, warehouse=None, qty=10, **extra):
    db = world["db"]
    a = SPOAllocation(
        id=_u(), company_id=extra.pop("company_id", world["company_id"]), spo_number=spo_number,
        spo_line_number=line_number, product_id=product.id,
        warehouse_id=warehouse.id if warehouse else None,
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
        id=_u(), company_id=extra.pop("company_id", world["company_id"]), po_number=po_number,
        status="active", **extra
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


def _picking_line(world, alloc, product, qty=5, **extra) -> PickingLine:
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
        quantity_expected=qty, quantity_picked=qty, **extra,
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

    result = _run(world, True, [plain, target])

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

    rerun = _run(world, True, [plain, target])
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

    result = _run(world, True, [plain, target])

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

    _run(world, True, [plain, target])
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
    """S already has more lines than P states: every P line matches or moves, S's count is
    the union of both, AND something P actually held lands on the survivor - not merely that
    S's own original count is unchanged (T5)."""
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
    # P's own provenance on one matched line - must land on the survivor it was matched to.
    shipment = _shipment(world)
    p_allocs[0].inbound_shipment_id = shipment.id
    db.flush()

    _run(world, True, [plain, target])
    db.expire_all()

    remaining = db.query(SPOAllocation).filter(SPOAllocation.spo_number == target).all()
    assert len(remaining) == 5, "S's count is the union - nothing lost, nothing duplicated"
    for p in p_allocs:
        assert db.query(SPOAllocation).filter(SPOAllocation.id == p.id).first() is None

    matched_survivor = (
        db.query(SPOAllocation)
        .filter(SPOAllocation.spo_number == target, SPOAllocation.product_id == products[0].id)
        .one()
    )
    assert str(matched_survivor.inbound_shipment_id) == str(shipment.id), (
        "P's provenance must actually land on the survivor it was matched to"
    )


# --------------------------------------------------------------------------- #
# typo shape (B3) - rename-only, target from issue_date, never merged
# --------------------------------------------------------------------------- #


def test_typo_renames_to_its_own_issue_date_year_not_the_malformed_year(world):
    """`SPO-20254/12-0074`'s own rows carry issue_date 2024-12-18 - the target is
    `SPO-2024/12-0074`, never `SPO-2025/12-0074` (what naively reading the malformed
    string's own leading digits, `\\1` = 2025, would give - a different, unrelated
    document). Mirrored here with year 2099 (the "naive" reading) vs 2098 (the real
    `issue_date` year) so the two candidate targets are unambiguously different."""
    db = world["db"]
    product = world["product"]()
    seq = _seq4()
    typo = f"SPO-20994/06-{seq}"  # naive \1 reading = "2099"
    naive_target = f"SPO-2099/06-{seq}"
    correct_target = f"SPO-2098/06-{seq}"  # the doc's real issue_date year

    p_alloc = _alloc(world, typo, 1, product, qty=5, issue_date=date(2098, 6, 1))

    result = _run(world, True, [typo, correct_target, naive_target])

    assert result["merged_docs"] == 0
    assert result["renamed"] == 1
    db.expire_all()
    after = db.query(SPOAllocation).filter(SPOAllocation.id == p_alloc.id).one()
    assert after.spo_number == correct_target
    assert after.spo_number != naive_target


def test_typo_is_reported_and_skipped_when_its_target_already_exists(world):
    """A typo whose corrected target ALREADY holds a document is a manual decision, never
    a merge - the typo shape never reaches Step B."""
    db = world["db"]
    product = world["product"]()
    typo = f"SPO-20994/06-{_seq4()}"
    body = typo[len("SPO-"):]
    year_and_stray, rest = body.split("/")
    year = year_and_stray[:-1]
    correct_target = f"SPO-{year}/{rest}"

    existing = _alloc(world, correct_target, 1, product, qty=99)
    p_alloc = _alloc(world, typo, 1, product, qty=5, issue_date=date(2099, 6, 1))

    result = _run(world, True, [typo, correct_target])

    assert result["merged_docs"] == 0
    assert result["renamed"] == 0
    db.expire_all()
    still_typo = db.query(SPOAllocation).filter(SPOAllocation.id == p_alloc.id).one()
    assert still_typo.spo_number == typo, "left untouched - never merged, never renamed"
    existing_after = db.query(SPOAllocation).filter(SPOAllocation.id == existing.id).one()
    assert existing_after.allocated_quantity == 99, "the existing target document is untouched"
    skipped = [s for s in result["backup"]["typo_skipped"] if s["raw"] == typo]
    assert skipped and "manual decision" in skipped[0]["reason"]


def test_typo_with_disagreeing_issue_dates_is_reported_and_skipped(world):
    db = world["db"]
    product = world["product"]()
    typo = f"SPO-20994/06-{_seq4()}"

    _alloc(world, typo, 1, product, qty=5, issue_date=date(2099, 6, 1))
    _alloc(world, typo, 2, product, qty=3, issue_date=date(2098, 6, 1))

    result = _run(world, True, [typo])

    assert result["renamed"] == 0
    assert result["merged_docs"] == 0
    db.expire_all()
    rows = db.query(SPOAllocation).filter(SPOAllocation.spo_number == typo).all()
    assert len(rows) == 2, "left untouched - a disagreement makes the guess unsafe"


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

    result = _run(world, False, [plain, target])

    db.expire_all()
    after = {
        r.id: r.spo_number
        for r in db.query(SPOAllocation).filter(SPOAllocation.spo_number.in_([plain, target])).all()
    }
    assert before == after, "a dry run must change no row"
    assert result["merged_docs"] == 1

    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    assert str(backup_path).startswith(world["out_dir"])
    data = json.loads(backup_path.read_text())
    assert data["dry_run"] is True


def test_a_second_apply_run_finds_nothing_left_to_do(world):
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)
    _alloc(world, target, 1, product, qty=5)
    _alloc(world, plain, 1, product, qty=5)

    first = _run(world, True, [plain, target])
    assert first["merged_docs"] == 1

    second = _run(world, True, [plain, target])
    assert second["merged_docs"] == 0
    assert second["renamed"] == 0


def test_a_forced_failure_mid_run_rolls_back_everything(world, monkeypatch):
    """T1: real prior writes happen BEFORE the crash (a fill on the first pair, an FK
    repoint already applied) - the crash fires on the SECOND delete, and every row (both
    pairs, plus the picking line attached to the first P) must be exactly as it was."""
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)

    s1 = _alloc(world, target, 1, product, qty=5)
    p1 = _alloc(world, plain, 1, product, qty=5)
    p1.inbound_shipment_id = _shipment(world).id
    db.flush()
    picking = _picking_line(world, p1, product)

    other_product = world["product"]("second")
    s2 = _alloc(world, target, 2, other_product, qty=8)
    p2 = _alloc(world, plain, 2, other_product, qty=8)

    def _snapshot():
        db.expire_all()
        allocs = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.id.in_([s1.id, p1.id, s2.id, p2.id]))
            .order_by(SPOAllocation.id)
            .all()
        )
        picking_after = db.query(PickingLine).filter(PickingLine.id == picking.id).one()
        return (
            [(r.id, r.spo_number, r.spo_line_number, r.allocated_quantity,
              r.inbound_shipment_id) for r in allocs],
            picking_after.spo_allocation_id,
        )

    before = _snapshot()

    real_delete = db.delete
    calls = {"n": 0}

    def _delete_second_time(obj):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash mid-merge")
        return real_delete(obj)

    monkeypatch.setattr(db, "delete", _delete_second_time)

    with pytest.raises(RuntimeError, match="simulated crash"):
        with db.begin_nested():
            _run(world, True, [plain, target])

    after = _snapshot()
    assert before == after, "a forced failure must leave every row exactly as it was, real prior writes included"


# --------------------------------------------------------------------------- #
# main() / cross-company / FK-on-a-matched-PO-line
# --------------------------------------------------------------------------- #


def test_main_applies_through_the_cli_and_never_touches_receipts(world, monkeypatch):
    """T2: a run through `main()` itself (argv, not `run()` directly) actually commits, and
    a survivor's `quantity_received` / `receipt_status` are unchanged - the B1 regression
    guard (no sync is ever called)."""
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)

    s_alloc = _alloc(
        world, target, 1, product, qty=10, quantity_received=7, receipt_status="pending"
    )
    _alloc(world, plain, 1, product, qty=10)

    bind = db.get_bind()

    def _session_on_this_connection():
        return SASession(bind=bind, join_transaction_mode="create_savepoint")

    monkeypatch.setattr(database_module, "SessionLocal", _session_on_this_connection)

    rc = dedupe.main(
        ["--apply", "--spo", plain, "--spo", target, "--out-dir", world["out_dir"]]
    )
    assert rc == 0

    db.expire_all()
    assert db.query(SPOAllocation).filter(SPOAllocation.spo_number == plain).first() is None
    survivor = db.query(SPOAllocation).filter(SPOAllocation.id == s_alloc.id).one()
    assert survivor.quantity_received == 7, "no sync ever touches quantity_received"
    assert survivor.receipt_status == "pending", "no sync ever touches receipt_status"


def test_main_rejects_dry_run_together_with_apply():
    """S9: a hard CLI error, never a silent pick-one."""
    with pytest.raises(SystemExit):
        dedupe.main(["--dry-run", "--apply"])


def test_cross_company_documents_stay_apart(world):
    """T3: the same malformed number under a second company must never merge across the
    company boundary."""
    db = world["db"]
    other_company = Company(id=_u(), name=f"{MARKER} co2", code=f"Z{uuid.uuid4().hex[:8]}")
    db.add(other_company)
    db.flush()

    product_a = world["product"]("mine")
    product_b = Product(
        id=_u(), product_code=f"{MARKER}-ITEM-theirs-{uuid.uuid4().hex[:6]}",
        product_name=f"{MARKER} theirs", category_id=product_a.category_id,
        base_uom_id=product_a.base_uom_id, list_price=0, is_active=True,
    )
    db.add(product_b)
    db.flush()

    plain = _new_plain()
    target = _slash_of(plain)

    mine_s = _alloc(world, target, 1, product_a, qty=5)
    mine_p = _alloc(world, plain, 1, product_a, qty=5)
    theirs_s = _alloc(world, target, 1, product_b, qty=9, company_id=other_company.id)
    theirs_p = _alloc(world, plain, 1, product_b, qty=9, company_id=other_company.id)

    result = _run(world, True, [plain, target])

    assert result["merged_docs"] == 2, "one twin per company, not one merge across both"
    db.expire_all()
    assert db.query(SPOAllocation).filter(SPOAllocation.id == mine_p.id).first() is None
    assert db.query(SPOAllocation).filter(SPOAllocation.id == theirs_p.id).first() is None
    mine_after = db.query(SPOAllocation).filter(SPOAllocation.id == mine_s.id).one()
    theirs_after = db.query(SPOAllocation).filter(SPOAllocation.id == theirs_s.id).one()
    assert str(mine_after.company_id) == str(world["company_id"])
    assert str(theirs_after.company_id) == str(other_company.id)
    assert mine_after.allocated_quantity == 5
    assert theirs_after.allocated_quantity == 9


def test_a_po_line_fk_on_a_matched_line_lands_on_the_survivor(world):
    """T4: `picking_lines.po_line_id` (`ON DELETE SET NULL`) attached to a P line that gets
    matched-and-deleted must be repointed onto the survivor line, never cascaded away."""
    db = world["db"]
    product = world["product"]()
    plain = _new_plain()
    target = _slash_of(plain)

    po_s = _po_header(world, target)
    s_line = _po_line(world, po_s, product, qty_ordered=10)
    po_p = _po_header(world, plain)
    p_line = _po_line(world, po_p, product, qty_ordered=10)

    picking = _picking_line(world, _alloc(world, target, 1, product, qty=10), product, po_line_id=p_line.id)

    _run(world, True, [plain, target])
    db.expire_all()

    assert db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == p_line.id).first() is None
    picking_after = db.query(PickingLine).filter(PickingLine.id == picking.id).one()
    assert str(picking_after.po_line_id) == str(s_line.id), (
        "must land on the survivor line, not go NULL under ON DELETE SET NULL"
    )
