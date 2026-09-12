"""Slice C, recompute-and-diff (`documentation/plans/scm/PLAN-scm-change-management-one-
engine.md`, UAC AC-C1 to AC-C8, issue #858, scenarios S2/S3/S5/S7/S8/S9/S10/S12 in
`documentation/plans/scm/mockups/so-change-management-grill-v4.html`). RED before the
coder's slice lands.

`suggest()` and its rule table are retired by this slice (`compose_suggestion` replaces
it); every test below builds a REAL held decision through the app's own confirm path, then
re-runs `build_batch` against a changed core line and reads `PlanningChangeRow
.suggestion_json`. That attribute does not exist on the model yet, so every test's first
real assertion fails with a clean `AttributeError` today - the expected red, not a fixture
bug (`suggested`/`why` still being non-null strings on the model is the SAME defect from
the other direction and would fail just as cleanly if reached first).

Fixture patterns, imported rather than copied:
- `tests.test_planning_changes` (`api` fixture: `(client, world)` with `world.company_id`
  /`.actor`/`.project`/`.product`/`.own_wh`/`.pool_wh`/`.db`; `_confirm`/`_line_payload`/
  `_diff_change`/`_place_row_on_a_real_po`/`_core_so`/`_core_line`/`_project_so`/
  `_project_line`/`_product`/`_stock`/`_uid`) - the same convention
  `tests/scm/test_planning_change_batch_kind_parity.py` already uses for this exact
  `(client, world)` shape.
- `tests.scm.test_planning_change_delta_seam` (`_held_buy_world`/`_held_reserve_world`/
  `_change_and_batch`/`_only_row`/`_confirm_and_apply`/`_live_order_rows`/
  `_active_decision`/`NON_IMMEDIATE`/`IMMEDIATE`) for the scenarios that need no PO/product
  swap - a self-contained `_world` (via `test_project_supply_service_ladder`), not the
  `api` client.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.planning_change import PlanningChangeRow
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    IV_ORDER,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.services import planning_change_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm.outstanding_diff import (
    CLOSED,
    DATE_AND_QTY_CHANGED,
    DATE_MOVED,
    PRODUCT_CHANGED,
    QTY_CHANGED,
    Change,
    Diff,
    Line,
)

from tests._pg_fixture import blank_session
from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    api,
    _confirm,
    _core_line,
    _core_so,
    _diff_change,
    _line_payload,
    _place_row_on_a_real_po,
    _product,
    _project_line,
    _project_so,
    _stock,
    _uid,
)
from tests.scm.test_planning_change_delta_seam import (
    IMMEDIATE,
    NON_IMMEDIATE,
    STILL_OUTSIDE,
    _active_decision,
    _change_and_batch,
    _confirm_and_apply,
    _held_buy_world,
    _held_reserve_world,
    _live_order_rows,
    _only_row,
)

MARKER = "zzt-recompdiff"


def _rows_for(db, batch_id: str) -> list:
    return (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch_id)
        .order_by(PlanningChangeRow.created_at)
        .all()
    )


def _components(row: PlanningChangeRow) -> list:
    """Every test's real first assertion: `suggestion_json` does not exist on the model
    yet, so this line is where each test goes red today (`AttributeError`)."""
    return row.suggestion_json["components"]


# --------------------------------------------------------------------------- #
# AC-C1: every held-line row carries a composed suggestion, no reaction words
# --------------------------------------------------------------------------- #

def test_row_carries_a_composed_suggestion_and_no_reaction_words(api):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="134",
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="134", buy_reason="ZZT no stock anywhere"),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 3, 1), new_date=date(2027, 3, 15), old_qty="134", new_qty="134",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    row = _only_row(db, batch)

    components = _components(row)
    assert components, row.suggestion_json
    for component in components:
        assert "label" in component, component
    assert row.suggested is None, row.suggested
    assert row.why is None, row.why
    all_labels = " ".join(c["label"] for c in components).lower()
    for reaction_word in ("replan", "retire", "accept"):
        assert reaction_word not in all_labels, all_labels


# --------------------------------------------------------------------------- #
# AC-C2: small delay inside the window suggests keep only (S9)
# --------------------------------------------------------------------------- #

def test_small_delay_inside_the_window_suggests_keep_only():
    # NOT `NON_IMMEDIATE`: it is already past the 60-day reserve window on its own, so a
    # further 21-day delay off it correctly answers Release+Buy (AC-C3), not Keep. A date
    # inside the window to start with is what this scenario is actually about.
    starting_date = date.today() + timedelta(days=20)
    with blank_session() as db:
        world = _held_reserve_world(db, qty="134", required_date=starting_date)
        batch = _change_and_batch(
            db, world, new_required_date=starting_date + timedelta(days=21),
        )
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "delayed"

        components = _components(row)
        assert len(components) == 1, components
        assert components[0]["action"] == "keep"
        assert components[0]["source"] == "reserve"
        assert components[0]["qty_now"] == "134"
        assert components[0]["label"] == "Keep 134"
        composition = planning_change_service.composition_from_proposal(row.proposal_json)
        # qty + warehouse only: `held_json`'s reserve items also carry `location`, which
        # `composition_from_proposal`'s do not.
        composed_reserve = [
            {"warehouse_id": r["warehouse_id"], "qty": r["qty"]}
            for r in composition.get("reserve") or []
        ]
        held_reserve = [
            {"warehouse_id": r["warehouse_id"], "qty": r["qty"]}
            for r in row.held_json.get("reserve") or []
        ]
        assert composed_reserve == held_reserve, (composition, row.held_json)


# --------------------------------------------------------------------------- #
# AC-C3: delay past the window suggests release + buy (S10)
# --------------------------------------------------------------------------- #

def test_delay_past_the_window_suggests_release_and_buy():
    with blank_session() as db:
        world = _held_reserve_world(db, qty="134", required_date=NON_IMMEDIATE)
        new_date = NON_IMMEDIATE + timedelta(days=90)
        batch = _change_and_batch(db, world, new_required_date=new_date)
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "delayed"

        components = _components(row)
        assert len(components) == 2, components
        release, buy = components
        assert release["action"] == "release"
        assert release["source"] == "reserve"
        assert release["qty_now"] == "134"
        assert release["label"] == f"Release 134, free at {world['own'].warehouse_code}"
        assert buy["action"] == "buy"
        assert buy["qty_now"] == "134"
        assert buy["label"] == f"Buy 134 for {new_date.strftime('%-d %b')}"

        composition = planning_change_service.composition_from_proposal(row.proposal_json)
        assert composition.get("buy_qty") == "134", composition
        assert composition.get("reserve") == [], composition


def test_delay_past_the_window_keep_is_an_amend():
    with blank_session() as db:
        world = _held_reserve_world(db, qty="134", required_date=NON_IMMEDIATE)
        new_date = NON_IMMEDIATE + timedelta(days=90)
        batch = _change_and_batch(db, world, new_required_date=new_date)
        assert batch is not None
        row = _only_row(db, batch)
        held_composition = dict(row.held_json)
        held_composition["project_line_id"] = str(world["line"].id)

        result = planning_change_service.set_row_decision(
            db, str(batch.id), str(row.id), "amend", held_composition,
        )
        db.commit()
        assert result["decision"] == "amend", result
        # Compare the meaningful sourcing only - the echoed composition also carries
        # `revision_no` and drops `held_json`'s own `location` key on each reserve item,
        # neither of which this assertion is about.
        composed = result["composition"]
        assert composed["buy_qty"] == held_composition["buy_qty"], result
        assert composed["borrow"] == held_composition["borrow"], result
        assert [
            {"warehouse_id": r["warehouse_id"], "qty": r["qty"]} for r in composed["reserve"]
        ] == [
            {"warehouse_id": r["warehouse_id"], "qty": r["qty"]}
            for r in held_composition["reserve"]
        ], result


# --------------------------------------------------------------------------- #
# AC-C4: qty down with a placed PO + a raised remainder (S2)
# --------------------------------------------------------------------------- #

def _qty_down_with_po_world(api):
    """234 held wholly as Buy, 134 of it placed on a real PO (`place_on_po_allocations`,
    never a hand-set state), 100 left unlinked - then the book drops the line to 100."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="234",
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="234", buy_reason="ZZT no stock anywhere"),
    ]})
    raised_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("134"), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        raised_row.id, [{"po_line_id": po_line.id, "qty": "134"}], actor_user_id=world.actor,
    )
    db.commit()
    db.expire_all()
    raised_row = db.get(OrderInquiryRow, raised_row.id)
    assert raised_row.state == INQUIRY_PARTLY_LINKED, raised_row.state
    return world, core_so, core_line, order, line, po


def test_qty_down_with_a_placed_po_and_a_raised_buy(api):
    world, core_so, core_line, order, line, po = _qty_down_with_po_world(api)
    db = world.db

    # Write-first (production always writes the book before building the batch off it):
    # the core line AND its mirror, or compose_suggestion re-reads the still-234 row and
    # answers "Keep 134" - not a Slice C defect, a fixture ordering bug.
    core_line.qty_ordered = Decimal("100")
    line.qty = Decimal("100")
    db.flush()

    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 3, 1), new_date=date(2027, 3, 1), old_qty="234", new_qty="100",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    row = _only_row(db, batch)
    assert row.kind == "qty_down"

    components = _components(row)
    labels = [c["label"] for c in components]
    assert "Reduce Buy 100 to 0" in labels, labels
    assert f"Keep {po.po_number} 100 of 134" in labels, labels
    assert f"Reallocate {po.po_number} 34 to pool" in labels, labels


def test_qty_down_reallocate_targets_another_raised_order_row(api):
    """Same shape, but a SECOND raised ORDER row for the same product on another SO
    changes the leftover's reallocation target from "pool" to "SO<n> ORDER <qty>"
    (rule 6)."""
    world, core_so, core_line, order, line, po = _qty_down_with_po_world(api)
    db = world.db

    other_core_so = _core_so(db, world.company_id)
    other_core_so.so_number = f"{MARKER}-SO420103"
    db.flush()
    other_core_line = _core_line(db, other_core_so, world.product, world.own_wh,
                                  qty_ordered="50", required_date=date(2027, 3, 1))
    other_order = _project_so(db, world.project, so_id=other_core_so.id,
                               autocount_doc_no=other_core_so.so_number)
    other_line = _project_line(db, other_order, line_no=1, product=world.product,
                                core_line=other_core_line)
    db.commit()

    # Write-first: the core line AND its mirror, before build_batch runs.
    core_line.qty_ordered = Decimal("100")
    line.qty = Decimal("100")
    db.flush()

    from tests.test_planning_changes import _client, _restore
    other_client, originals = _client(db, world.actor)
    try:
        _confirm(other_client, other_order.id, {"lines": [
            _line_payload(other_line.id, buy_qty="50", buy_reason="ZZT no stock anywhere"),
        ]})
    finally:
        _restore(originals)

    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 3, 1), new_date=date(2027, 3, 1), old_qty="234", new_qty="100",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    row = _only_row(db, batch)
    components = _components(row)
    labels = [c["label"] for c in components]
    assert f"Reallocate {po.po_number} 34 to {other_core_so.so_number} ORDER 50" in labels, (
        labels
    )


# --------------------------------------------------------------------------- #
# AC-C5: a cancelled line releases every held component (S5); a product change
# releases the old and sources the new (S7)
# --------------------------------------------------------------------------- #

def test_cancelled_line_releases_every_held_component():
    with blank_session() as db:
        world = _held_reserve_world(db, qty="134", required_date=NON_IMMEDIATE)
        core_so = world["core_so"]
        core_line = world["core_line"]
        item_code = world["product"].product_code
        location = world["own"].warehouse_code
        before = Line(doc_number=core_so.so_number, item_code=item_code, location=location,
                      qty=134.0, required_date=world["core_line"].required_date,
                      row_ref=str(core_line.id))
        change = Change(CLOSED, core_so.so_number, item_code, location, before=before,
                         after=None)
        diff = Diff(scope_documents=(core_so.so_number,), changes=[change])
        batch = planning_change_service.build_batch(
            db, diff, applied_line_ids={id(change): str(core_line.id)},
            order_ids={core_so.so_number: str(core_so.id)}, actor=world["actor"],
            import_job_id=None, file_name="test.xlsx",
        )
        db.commit()
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "cancelled"

        components = _components(row)
        assert len(components) == 1, components
        assert components[0]["action"] == "release"
        assert components[0]["source"] == "reserve"
        assert components[0]["qty_now"] == "134"


def test_product_change_releases_held_and_sources_the_new_product(api):
    client, world = api
    db = world.db
    old_product = world.product
    from tests.test_so_supply_confirmation import _product as _make_product
    new_product = _make_product(db)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, old_product, world.own_wh, qty_ordered="134",
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=old_product, core_line=core_line)
    _stock(db, old_product, world.own_wh, on_hand=134)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "134"}]),
    ]})

    core_line.product_id = new_product.id
    db.flush()
    before = Line(doc_number=core_so.so_number, item_code=old_product.product_code,
                  location=world.own_wh.warehouse_code, qty=134.0, required_date=date(2027, 3, 1),
                  row_ref=str(core_line.id))
    after = Line(doc_number=core_so.so_number, item_code=new_product.product_code,
                 location=world.own_wh.warehouse_code, qty=134.0, required_date=date(2027, 3, 1),
                 row_ref=str(core_line.id))
    change = Change(PRODUCT_CHANGED, core_so.so_number, new_product.product_code,
                     world.own_wh.warehouse_code, before=before, after=after)
    diff = Diff(scope_documents=(core_so.so_number,), changes=[change])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(change): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    row = _only_row(db, batch)
    assert row.kind == "product_changed"

    components = _components(row)
    release = next(c for c in components if c["action"] == "release")
    assert release["item_code"] == old_product.product_code, release
    assert release["qty_now"] == "134", release
    sourced = next(c for c in components if c is not release)
    assert sourced["item_code"] == new_product.product_code, sourced
    assert sourced["qty_now"] == "134", sourced


# --------------------------------------------------------------------------- #
# AC-C6: advance the PO cannot meet, no donor -> keep, late (S12)
# --------------------------------------------------------------------------- #

def test_advance_the_po_cannot_meet_with_no_donor_suggests_keep_late(api):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="134",
                            required_date=NON_IMMEDIATE)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="134", buy_reason="ZZT no stock anywhere"),
    ]})
    raised_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    po_arrival = NON_IMMEDIATE  # the PO's own eta stays where it was placed against
    po, po_line = _place_row_on_a_real_po(db, world, raised_row, qty_ordered="134")
    db.commit()

    new_required_date = NON_IMMEDIATE - timedelta(days=40)  # advanced, well before arrival
    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=NON_IMMEDIATE, new_date=new_required_date, old_qty="134", new_qty="134",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    row = _only_row(db, batch)
    assert row.kind == "advanced"

    components = _components(row)
    assert len(components) == 1, components
    assert components[0]["action"] == "keep"
    late_days = (po_arrival - new_required_date).days
    assert row.suggestion_json.get("late_days") == late_days, row.suggestion_json
    assert components[0]["label"] == f"Keep 134, late by {late_days} days", components[0]

    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    db.commit()
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]

    decision = _active_decision(db, order.id)
    snapshot = next(
        s for s in decision.line_snapshots if s["project_line_id"] == str(line.id)
    )
    assert snapshot.get("late_days") == late_days, snapshot
    db.expire_all()
    reloaded_row = db.get(OrderInquiryRow, raised_row.id)
    assert reloaded_row.note and f"late by {late_days} days" in reloaded_row.note, (
        reloaded_row.note
    )


# --------------------------------------------------------------------------- #
# AC-C7: the row-decision route accepts confirm/amend only
# --------------------------------------------------------------------------- #

def test_decision_accepts_confirm_and_amend_only(api):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="134",
                            required_date=NON_IMMEDIATE)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="134", buy_reason="ZZT no stock anywhere"),
    ]})

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=NON_IMMEDIATE, new_date=NON_IMMEDIATE + timedelta(days=5), old_qty="134",
        new_qty="134",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    assert batch is not None
    row = _only_row(db, batch)
    url = f"/api/v1/project-sales/planning-changes/{batch.id}/rows/{row.id}"

    for bad_decision in ("accept", "keep", "board"):
        response = client.put(url, json={"decision": bad_decision})
        assert response.status_code == 422, (bad_decision, response.status_code, response.text)

    response = client.put(url, json={"decision": "confirm"})
    assert response.status_code == 200, response.text


def test_apply_ignores_rows_without_a_decision():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134", required_date=NON_IMMEDIATE)
        batch = _change_and_batch(
            db, world, new_required_date=NON_IMMEDIATE + timedelta(days=5),
        )
        assert batch is not None
        row = _only_row(db, batch)
        assert row.decision is None

        result = planning_change_service.apply(db, str(batch.id), world["actor"])
        db.commit()
        assert result["failed_orders"] == [], result["failed_orders"]
        db.expire_all()
        row = db.get(PlanningChangeRow, row.id)
        assert row.applied_state == "pending", row.applied_state


# --------------------------------------------------------------------------- #
# AC-C8: date AND qty change in one edit -> one row, one composed suggestion (S8)
# --------------------------------------------------------------------------- #

def test_date_and_qty_in_one_edit_yields_one_row_and_one_suggestion():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134", required_date=NON_IMMEDIATE)
        core_so = world["core_so"]
        core_line = world["core_line"]
        item_code = world["product"].product_code
        location = world["own"].warehouse_code
        new_date = NON_IMMEDIATE + timedelta(days=30)

        before = Line(doc_number=core_so.so_number, item_code=item_code, location=location,
                      qty=134.0, required_date=NON_IMMEDIATE, row_ref=str(core_line.id))
        core_line.qty_ordered = Decimal("200")
        core_line.required_date = new_date
        db.flush()
        after = Line(doc_number=core_so.so_number, item_code=item_code, location=location,
                     qty=200.0, required_date=new_date, row_ref=str(core_line.id))
        change = Change(DATE_AND_QTY_CHANGED, core_so.so_number, item_code, location,
                         before=before, after=after)
        diff = Diff(scope_documents=(core_so.so_number,), changes=[change])
        batch = planning_change_service.build_batch(
            db, diff, applied_line_ids={id(change): str(core_line.id)},
            order_ids={core_so.so_number: str(core_so.id)}, actor=world["actor"],
            import_job_id=None, file_name="test.xlsx",
        )
        db.commit()
        assert batch is not None
        rows = _rows_for(db, batch.id)
        assert len(rows) == 1, [r.kind for r in rows]
        row = rows[0]

        components = _components(row)
        assert len(components) == 1, components
        assert components[0]["qty_now"] == "200", components[0]
        assert components[0]["qty_was"] == "134", components[0]
        assert components[0]["label"] == "Buy 200 (was 134)", components[0]


# --------------------------------------------------------------------------- #
# Shortfall (rule 8): the re-run cannot cover the whole remainder inside the
# window, and the uncovered part is stated, not silently bought
# --------------------------------------------------------------------------- #

def test_advance_inside_the_window_the_ladder_cannot_cover_shows_it_short():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134", required_date=NON_IMMEDIATE)
        _stock_pool = world["pool"]
        from tests.test_so_supply_confirmation import _stock as _seed_stock
        _seed_stock(db, world["product"], world["pool"], on_hand=100)

        batch = _change_and_batch(db, world, new_required_date=IMMEDIATE)
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "advanced"

        components = _components(row)
        pool_component = next(c for c in components if c["source"] == "pool_share")
        buy_component = next(c for c in components if c["action"] == "buy")
        assert pool_component["qty_now"] == "50", components
        assert buy_component["qty_now"] == "84", components
        assert row.suggestion_json.get("shortfall_qty") == "84", row.suggestion_json
        assert buy_component["label"].startswith("Short 84 by"), buy_component


# --------------------------------------------------------------------------- #
# Schema contract: PlanningChangeDecision is exactly confirm/amend now
# --------------------------------------------------------------------------- #

def test_planning_change_decision_literal_is_confirm_and_amend_only():
    import typing

    from app.schemas.planning_change import PlanningChangeDecision

    # `PlanningChangeDecision = Optional[Literal[...]]` - `get_args` on the Optional
    # returns `(Literal[...], NoneType)`, so the Literal's own members are one level
    # deeper (`get_args` again on the first arg).
    args = typing.get_args(PlanningChangeDecision)
    literal_type = next(a for a in args if a is not type(None))
    literal_values = set(typing.get_args(literal_type))
    assert literal_values == {"confirm", "amend"}, (
        f"PlanningChangeDecision carries {literal_values} - Slice C retires accept/keep/"
        "board (compose_suggestion replaces suggest(), the row-decision route accepts "
        "confirm/amend only)"
    )
