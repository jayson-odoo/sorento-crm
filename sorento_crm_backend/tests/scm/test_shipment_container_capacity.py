"""S5, PLAN-scm-pi-packing-list-feedback-3sep.md ruling 1, AC-E6.

The convert dialog chooses the CONTAINER SIZE; the over-capacity check compares the
COMBINED volume of every selected invoice against that one size (never any single invoice's
own volume); the fill gauge (`_fit`) is on the SHIPMENT payload only, never the PI's.

TEST-FIRST: `convert_to_draft_shipment` takes no `container_size_id` keyword and
`_over_capacity` still judges one invoice at a time until this lands, so every test here is
expected to be red (TypeError / an over-capacity refusal on a combination that should pass,
or the reverse) until it does.

Runs on the REAL Postgres via `pg_session` (rolled back at teardown), same substrate as its
neighbours in this directory - `_seed_container_sizes` seeds the three real sizes migration
336 defines, `20GP` 28 cbm / `40GP` 58 cbm / `40HQ` 65 cbm (the default).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ContainerSize
from app.services.error_handler import AppException
from app.services.procurement_service import InboundShipmentService
from app.services.scm import proforma_invoice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_proforma_invoice_adjust import _apply_preloading, _seed_container_sizes
from tests.scm.test_proforma_invoice_import import World, _lines


def _flatten_to(db, invoice, cbm: float) -> dict[str, float]:
    """Overwrite every matched line's volume so the WHOLE invoice measures exactly `cbm` -
    the same technique `test_a_box_of_its_own_is_judged_on_its_own_volume` uses, so two
    invoices can be given controlled, independent volumes for the combined-capacity tests
    below. Returns the `line_quantities` map a convert needs to place all of it."""
    matched = [ln for ln in _lines(db, invoice.id) if ln.product_id]
    for i, ln in enumerate(matched):
        ln.cbm_per_unit = (cbm / float(ln.qty)) if i == 0 else 0
        ln.cbm_total = cbm if i == 0 else 0
    db.flush()
    return {str(ln.id): float(ln.qty) for ln in matched}


# --------------------------------------------------------------------------------- #
# The dialog's size is WRITTEN onto the draft
# --------------------------------------------------------------------------------- #


def test_convert_writes_the_dialog_chosen_size_onto_the_draft():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        # Block 5 is 27.1 cbm - comfortably inside every size seeded, so the size choice
        # itself is what is under test here, not the capacity gate.
        invoice = _apply_preloading(db, w)[4]
        small = db.query(ContainerSize).filter(ContainerSize.code == "20GP").one()

        out = svc.convert_to_draft_shipment(
            db, [str(invoice.id)], container_size_id=str(small.id)
        )

        shipment = InboundShipmentService(db).get_shipment(out["shipment_id"])
        assert str(shipment.container_size_id) == str(small.id)


def test_convert_with_no_size_chosen_leaves_the_draft_at_the_tenant_default():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        shipment = InboundShipmentService(db).get_shipment(out["shipment_id"])
        assert shipment.container_size_id is None
        # NULL reads as the default at render time, not as "no box chosen ever".
        assert shipment.container_size_code == "40HQ"


def test_an_unknown_container_size_id_is_refused_by_name():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(
                db, [str(invoice.id)], container_size_id="00000000-0000-0000-0000-000000000000"
            )
        assert exc.value.status_code == 404
        assert exc.value.detail["detail"] == "container_size_id"


# --------------------------------------------------------------------------------- #
# The over-capacity check is on the COMBINED selection, against the ONE chosen size
# --------------------------------------------------------------------------------- #


def test_two_invoices_each_under_capacity_alone_are_refused_together():
    """Neither 40 nor 30 cbm alone is over a 65 cbm 40HQ; 70 combined is (ruling 1)."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        first_q = _flatten_to(db, invoices[3], 40)
        second_q = _flatten_to(db, invoices[4], 30)

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(
                db,
                [str(invoices[3].id), str(invoices[4].id)],
                line_quantities={**first_q, **second_q},
            )

        assert exc.value.status_code == 409
        body = exc.value.detail
        assert body["code"] == "over_capacity"
        assert "70" in body["message"] and "65" in body["message"]


def test_the_same_two_invoices_fit_a_bigger_size_chosen_on_the_dialog():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        first_q = _flatten_to(db, invoices[3], 40)
        second_q = _flatten_to(db, invoices[4], 30)
        big = ContainerSize(id=str(uuid.uuid4()), code="45HQ", cbm=90, is_active=True)
        db.add(big)
        db.flush()

        out = svc.convert_to_draft_shipment(
            db,
            [str(invoices[3].id), str(invoices[4].id)],
            line_quantities={**first_q, **second_q},
            container_size_id=str(big.id),
        )

        assert out["shipment_id"]


def test_the_refusal_names_the_dialog_size_not_the_tenant_default():
    """65 (default 40HQ) would swallow 40+? no - swap: choose the SMALL 20GP size (28 cbm)
    for two invoices that individually fit the 40HQ default but not the box actually
    picked."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        first_q = _flatten_to(db, invoices[3], 15)
        second_q = _flatten_to(db, invoices[4], 15)
        small = db.query(ContainerSize).filter(ContainerSize.code == "20GP").one()

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(
                db,
                [str(invoices[3].id), str(invoices[4].id)],
                line_quantities={**first_q, **second_q},
                container_size_id=str(small.id),
            )

        body = exc.value.detail
        assert body["code"] == "over_capacity"
        assert "20GP" in body["message"]
        assert "30" in body["message"] and "28" in body["message"]


# --------------------------------------------------------------------------------- #
# The fill gauge is on the SHIPMENT payload, never the PI's
# --------------------------------------------------------------------------------- #


def test_the_shipment_payload_carries_the_fill_gauge_after_convert():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]
        # A controlled volume (only the MATCHED line's cbm reaches a shipment line, never
        # an unmatched sibling's - see `_flatten_to`), so the assertion below is exact
        # rather than assuming full catalogue coverage of the block.
        q = _flatten_to(db, invoice, 27.1)

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)], line_quantities=q)

        shipment = InboundShipmentService(db).get_shipment(out["shipment_id"])
        assert shipment.total_cbm == pytest.approx(27.1, abs=0.01)
        assert shipment.container_cbm == pytest.approx(65)
        assert shipment.container_size_code == "40HQ"
        assert shipment.over_by_cbm is None
        assert shipment.fill_pct is not None


def test_the_pi_payload_carries_no_fill_gauge_after_convert():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]
        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        out = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))

        for key in ("container_cbm", "container_size_code", "fill_pct", "over_by_cbm",
                    "container_size_id"):
            assert key not in out, key
        assert out["total_cbm"] == pytest.approx(27.1)


# --------------------------------------------------------------------------------- #
# S12 - the fill gauge reads a dims-only line's OWN carton volume, not zero
# --------------------------------------------------------------------------------- #


def test_a_dims_only_line_raises_total_cbm_on_the_fill_gauge():
    """`_attach_capacity` used to sum `InboundShipmentLine.cbm` alone, so a line typed
    with a pack size and its own carton L/W/H and no STORED cbm counted as zero here even
    though `consolidated_packing_list.to_xlsx` derives a real figure for it live from those
    same dimensions. `line_cbm` (S12) is the one rule both readers use now.

    Seeded directly rather than through a proforma-invoice convert: the gauge is a property
    of the SHIPMENT's own lines, and a dims-only line is exactly what a raw packing-list
    upload (never touched a PI) looks like.
    """
    with pg_session() as db:
        tag = uuid.uuid4().hex[:8].upper()
        category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=f"ZZTCAP-CAT-{tag}",
            category_name=f"ZZTCAP category {tag}",
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=f"ZZTCAP{tag}"[:20], uom_name="pcs"
        )
        db.add_all([category, uom])
        db.flush()
        supplier = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=f"ZZTCAP-{tag}"[:50],
            supplier_name=f"ZZTCAP factory {tag}",
            is_active=True,
        )
        product = Product(
            id=str(uuid.uuid4()),
            product_code=f"ZZTCAP-{tag}-DIMS",
            product_name="dims-only product",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=0,
            is_active=True,
        )
        db.add_all([supplier, product])
        db.flush()

        shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"ZZTCAP-SH-{tag}",
            shipment_date=date(2026, 8, 1),
            shipping_container_number=f"ZZTCAP-U{tag}",
            shipment_status="in_transit",
        )
        db.add(shipment)
        db.flush()

        line = InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=shipment.id,
            supplier_id=supplier.id,
            product_id=product.id,
            quantity_shipped=200,
            pcs_per_carton=20,
            carton_length_cm=60,
            carton_width_cm=50,
            carton_height_cm=40,
            currency="CNY",
        )
        db.add(line)
        db.flush()

        out = InboundShipmentService(db).get_shipment(str(shipment.id))

        # ctn = 200 / 20 = 10; cbm = 10 * (60 * 50 * 40 / 1e6) = 1.2 - never zero.
        assert out.total_cbm == pytest.approx(1.2, abs=0.001)
        assert out.unmeasured_lines == 0
