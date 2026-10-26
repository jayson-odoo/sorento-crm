"""LINKAGE-UNIFY U5 (PLAN section 10): one PO -> SPO key everywhere, and a candidate walk
that sees the placements that follow a PO line onto its SPO.

The key is `goods_chain`'s: PO number + trimmed line ref + product (+ company). Every
chain is seeded here; helpers are `test_goods_chain._World`.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_goods_chain import _World
from tests.scm.test_goods_chain_received import TODAY
from tests.scm.test_stock_debt_routes import _product, _u

pytestmark = requires_pg


def _service(db):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    return ProjectOrderInquiryService(db)


# ---------------------------------------------------------------------------- K1


def _unlinked_row(db, w, qty):
    """A second open row of the same product with no link of its own."""
    from app.models.project_so import OrderInquiryLink

    spare = w.onto  # noqa: F841 (keeps the helper surface obvious)
    other = _spo_for_spare(db, w)
    row, link = w.place_on_spo(other, qty, minute=50)
    db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link.id).delete()
    db.flush()
    return row


def _spo_for_spare(db, w):
    from tests.scm.test_stock_debt_routes import _spo

    return _spo(db, w.product, w.b2, qty=1, arrives=w.due, received=1,
                receipt_status="fully_received", line_status="closed")


def test_seed_key_everywhere_builds(scm_app):
    """Seeding only (passes today): the PO line, the SPO naming it, the placement and the
    second unlinked row exist."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=486, transferred=486)
    a = w.onto(po, po_line, qty=486)
    _row1, link = w.place_on_po(po_line, 486, minute=1)
    row2 = _unlinked_row(db, w, 486)
    assert a.from_po_line_ref == po_line.source_ref and link.po_line_id == po_line.id
    assert row2.id


def test_k1_a_placement_that_follows_the_po_onto_its_spo_leaves_no_free_quantity(scm_app):
    """PO line 486 transferred onto SPO A 486 (in transit, at a pool bin). Row 1 places 486
    on the PO line, so it holds A's goods: row 2 is not offered A's 486 again."""
    db = scm_app[1]
    w = _World(db)
    w.b2.pool_warehouse_id = w.b1.id  # b1 is a pool, so the SPO there is a candidate
    db.flush()
    po, po_line = w.po(ordered=486, transferred=486)
    a = w.onto(po, po_line, qty=486, warehouse=w.b1)
    _row1, _link = w.place_on_po(po_line, 486, minute=1)
    row2 = _unlinked_row(db, w, 486)

    offered = [
        c for c in _service(db).po_candidates_for_row(str(row2.id))
        if c["spo_allocation_id"] == str(a.id)
    ]
    assert all(Decimal(str(c["remaining"])) == 0 for c in offered), offered


# ---------------------------------------------------------------------------- K2 / K3


def _own_arrival_world(db, *, spo_ref=None, spo_po_number=None, spo_product=None):
    """PO line (from_so_line_ref = the SO line's source_ref) and an SPO that received 50
    against it, naming it through `from_po_number` + `from_po_line_ref`."""
    from tests.scm.test_stock_debt_routes import _spo

    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    so_ref = f"ZZTSO{_u()[:6]}"
    po_line.from_so_line_ref = so_ref
    a = _spo(db, spo_product or w.product, w.b1, qty=50, arrives=TODAY - timedelta(days=3),
             received=50, receipt_status="fully_received", line_status="closed")
    a.from_po_number = spo_po_number or po.po_number
    a.from_po_line_ref = spo_ref if spo_ref is not None else po_line.source_ref
    db.flush()
    return w, po, po_line, a, so_ref


def _landed_single(db, w, so_ref):
    from app.services.project_supply_service import ProjectSupplyService

    out = ProjectSupplyService(db)._po_received_by_so_line_ref(
        [so_ref], product_id=str(w.product.id), company_id=SORENTO_COMPANY_ID,
    )
    return Decimal(str(out.get(so_ref, (Decimal("0"), None))[0]))


def _landed_batch(db, w, so_ref):
    from app.services.project_supply_service import ProjectSupplyService

    out = ProjectSupplyService(db)._po_received_by_product({str(w.product.id): [so_ref]})
    return Decimal(str(out.get(str(w.product.id), {}).get(so_ref, (Decimal("0"), None))[0]))


def test_k2_a_space_padded_from_po_line_ref_is_counted_by_the_own_arrival_readers(scm_app):
    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db)
    a.from_po_line_ref = f"  {po_line.source_ref} "
    db.flush()
    assert _landed_single(db, w, so_ref) == Decimal("50")
    assert _landed_batch(db, w, so_ref) == Decimal("50")


def test_k3_an_spo_naming_the_same_line_ref_under_another_po_is_not_counted(scm_app):
    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db, spo_po_number="ZZT-OTHER-PO-1")
    assert _landed_single(db, w, so_ref) == Decimal("0")
    assert _landed_batch(db, w, so_ref) == Decimal("0")


def test_k3_the_matching_po_number_still_counts(scm_app):
    """The guard for K3: the same chain under the RIGHT PO number is counted."""
    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db)
    assert _landed_single(db, w, so_ref) == Decimal("50")
    assert _landed_batch(db, w, so_ref) == Decimal("50")


# ---------------------------------------------------------------------------- K4


def test_k4_the_ingest_hook_trims_the_po_side_ref_too(scm_app):
    """The SPO names the line as `ref`; the PO line carries it padded (`" ref "`). The
    chain key trims both sides, so the hook resolves the PO line's SO ref."""
    from app.api.v1.external.ingest import _refs_from_written_spo_allocations

    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db)
    po_line.source_ref = f"  {a.from_po_line_ref} "
    db.flush()
    refs = _refs_from_written_spo_allocations(db, {str(a.id)}, company_id=SORENTO_COMPANY_ID)
    assert so_ref in refs


def test_k4_the_ingest_hook_requires_the_same_product(scm_app):
    from app.api.v1.external.ingest import _refs_from_written_spo_allocations

    db = scm_app[1]
    other = None
    w = _World(db)
    other = _product(db, f"{w.marker}-OTHERP")
    w2, po, po_line, a, so_ref = _own_arrival_world(db, spo_product=other)
    refs = _refs_from_written_spo_allocations(db, {str(a.id)}, company_id=SORENTO_COMPANY_ID)
    assert so_ref not in refs


def _core_line_with_ref(db, w, so_ref):
    from tests.scm.test_stock_debt_routes import _demand

    _order, core = _demand(
        db, w.product, w.b1, qty=50, required_date=w.due, so_number=f"{w.marker}-K4",
    )
    core.source_ref = so_ref
    db.flush()
    return core


def test_k4_book_names_target_trims_a_padded_spo_line_ref(scm_app):
    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db)
    a.from_po_line_ref = f"  {po_line.source_ref} "
    db.flush()
    core = _core_line_with_ref(db, w, so_ref)
    assert _service(db)._book_names_target_for_line(
        core, po_line_id=None, spo_allocation_id=str(a.id),
    ) is True


def test_k4_book_names_target_requires_the_same_product(scm_app):
    db = scm_app[1]
    w = _World(db)
    other = _product(db, f"{w.marker}-OTHERQ")
    w2, po, po_line, a, so_ref = _own_arrival_world(db, spo_product=other)
    core = _core_line_with_ref(db, w2, so_ref)
    assert _service(db)._book_names_target_for_line(
        core, po_line_id=None, spo_allocation_id=str(a.id),
    ) is False


# ---------------------------------------------------------------------------- U5 round 2


def _followed_world(db):
    """PO line 486 transferred onto SPO A 486 (in transit, at a pool bin B1); row 1 places 486
    on the PO line; row 2 is a second unlinked row of the same product."""
    w = _World(db)
    w.b2.pool_warehouse_id = w.b1.id
    db.flush()
    po, po_line = w.po(ordered=486, transferred=486)
    a = w.onto(po, po_line, qty=486, warehouse=w.b1)
    row1, _link = w.place_on_po(po_line, 486, minute=1)
    row2 = _unlinked_row(db, w, 486)
    return w, a, row1, row2


def _remaining_of(db, row, spo):
    offered = [
        c for c in _service(db).po_candidates_for_row(str(row.id))
        if c["spo_allocation_id"] == str(spo.id)
    ]
    return [Decimal(str(c["remaining"])) for c in offered]


def test_b1_the_row_that_placed_on_the_po_is_still_offered_the_spo_its_own_goods_followed_onto(scm_app):
    """Own links are credited back (S8 "choose document"): row 1's own 486 sits on A, so for
    row 1 A still reads 486 remaining; for row 2 it reads 0 (K1)."""
    db = scm_app[1]
    w, a, row1, row2 = _followed_world(db)
    assert _remaining_of(db, row1, a) == [Decimal("486")]
    assert all(r == 0 for r in _remaining_of(db, row2, a))


def test_k5_an_spo_of_another_company_is_not_counted_by_the_batch_own_arrival_reader(scm_app):
    """The key's company condition, stated by the reader itself (the batch read states no
    company of its own): an SPO of ANOTHER company naming the same PO number, ref and product
    lands nothing for this company's SO line."""
    from app.models.company import Company

    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db)
    other = _u()
    db.add(Company(id=other, name="ZZT K5 other", code=f"ZZTK5{_u()[:6]}".upper(), is_active=True))
    db.flush()
    a.company_id = other
    db.flush()
    # Widen the session scope to BOTH companies, so only the key's own company condition can
    # keep the other company's SPO out.
    from app.models.base import set_company_scope

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID, other}))
    assert _landed_batch(db, w, so_ref) == Decimal("0")
    assert _landed_single(db, w, so_ref) == Decimal("0")


def test_k6_an_spo_naming_the_po_line_by_fk_is_counted_as_landed(scm_app):
    """The FK route of the one key: `spo_allocations.po_line_id` names the PO line, with no
    from_po_number / from_po_line_ref at all."""
    db = scm_app[1]
    w, po, po_line, a, so_ref = _own_arrival_world(db)
    a.from_po_number = None
    a.from_po_line_ref = None
    a.po_line_id = po_line.id
    db.flush()
    assert _landed_single(db, w, so_ref) == Decimal("50")
    assert _landed_batch(db, w, so_ref) == Decimal("50")


def test_the_followed_cache_resets_when_a_followed_claim_is_added_on_the_same_service(scm_app):
    """PO line 972 (486 transferred onto SPO A, 486 still on order), no placements yet. One
    service instance walks row 2's candidates (A reads 486), row 1 is placed on the PO line
    through the normal write path (adding a followed claim on A), and the SAME instance walks
    again: A reads 0. A cache that kept the first walk's answer would still read 486."""
    from tests.scm.conftest import seed_user

    db = scm_app[1]
    w = _World(db)
    w.b2.pool_warehouse_id = w.b1.id
    db.flush()
    po, po_line = w.po(ordered=972, transferred=486)
    a = w.onto(po, po_line, qty=486, warehouse=w.b1)
    row1 = _unlinked_row(db, w, 486)
    row2 = _unlinked_row(db, w, 486)
    svc = _service(db)

    def offered():
        return [
            Decimal(str(c["remaining"]))
            for c in svc.po_candidates_for_row(str(row2.id))
            if c["spo_allocation_id"] == str(a.id)
        ]

    assert offered() == [Decimal("486")]
    svc.place_on_po(str(row1.id), str(po_line.id), actor_user_id=seed_user(db, None))
    assert all(r == 0 for r in offered())
