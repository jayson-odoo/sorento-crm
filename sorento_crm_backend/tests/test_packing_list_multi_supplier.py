"""One container, several factories: the second packing list must not erase the first.

This is the data-loss test. `uk_inbound_shipment_lines_shipment_product` said one row per
product per shipment and `create_shipment` replaced every line on an update, so uploading
Caizhou's list for a container that already held Kailu's lines left the container holding
Caizhou's alone. Nobody was told; the quantities simply went.

The rule under test:

  * a line belongs to a supplier (its own, else the header's);
  * an upload that NAMES a supplier replaces only that supplier's lines;
  * an upload that names none replaces everything, exactly as it always did (the n8n PDF
    path knows no supplier and speaks for the whole container);
  * the header supplier is derived - one supplier across the lines, or NULL when mixed.

Postgres only, on a blank schema, seeding every FK target itself: the CI database is empty,
so a test that borrows an existing category or supplier passes here and fails there.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest

from app.models.import_alias import ImportFieldAlias
from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.procurement import (
    InboundShipmentCreate,
    InboundShipmentLineCreate,
    InboundShipmentUpdate,
)
from app.services.error_handler import AppException
from app.services.procurement_service import InboundShipmentService
from app.services.scm import packing_list_service
from tests._pg_fixture import blank_session

MARKER = "ZZMS"

#: "the payload said nothing about this field", as distinct from "the payload said None".
_UNSET = object()

#: The headers migration 311 seeds for doc type `packing_list`. Seeded by the test rather
#: than borrowed from the database, because CI's is empty.
_ALIASES = [
    ("item_code", "产品型号"),
    ("product_name", "品名"),
    ("qty", "数量"),
    ("cartons", "箱数"),
    ("cbm_per_unit", "体积(cbm)"),
    ("cbm_total", "总体积(cbm)"),
    ("container_no", "货柜号"),
    ("remark", "备注"),
]


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uom(db) -> str:
    uid = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uid, uom_code=f"{MARKER}{uuid.uuid4().hex[:6]}"[:20], uom_name="pcs"))
    db.flush()
    return uid


def _category(db) -> str:
    cid = str(uuid.uuid4())
    db.add(
        ProductCategory(
            id=cid,
            category_code=f"{MARKER}-CAT-{uuid.uuid4().hex[:6]}",
            category_name=f"{MARKER} category",
        )
    )
    db.flush()
    return cid


def _product(db, code: str, *, category_id: str, uom_id: str) -> Product:
    p = Product(
        id=str(uuid.uuid4()),
        product_code=f"{MARKER}-{code}-{uuid.uuid4().hex[:6]}",
        product_name=code,
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=0,
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _supplier(db, name: str) -> Supplier:
    s = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=f"{MARKER}-{name}-{uuid.uuid4().hex[:6]}",
        supplier_name=f"{MARKER} {name}",
        is_active=True,
    )
    db.add(s)
    db.flush()
    return s


class World:
    """Two factories, two products, one container."""

    def __init__(self, db):
        self.db = db
        category = _category(db)
        uom = _uom(db)
        self.category_id = category
        self.uom_id = uom
        self.kailu = _supplier(db, "KAILU")
        self.caizhou = _supplier(db, "CAIZHOU")
        self.tap = _product(db, "TAP", category_id=category, uom_id=uom)
        self.sink = _product(db, "SINK", category_id=category, uom_id=uom)
        self.container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
        db.flush()

    def product(self, code: str) -> Product:
        return _product(self.db, code, category_id=self.category_id, uom_id=self.uom_id)

    def upload(self, *, supplier_id, lines, container=None):
        """One packing list for this container, as `create_shipment` receives it."""
        payload = InboundShipmentCreate(
            shipment_number=container or self.container,
            supplier_id=supplier_id,
            shipment_date=date(2026, 1, 1),
            shipping_container_number=container or self.container,
            shipment_lines=[
                InboundShipmentLineCreate(
                    product_id=str(product.id),
                    quantity_shipped=qty,
                    supplier_id=line_supplier,
                )
                for product, qty, line_supplier in lines
            ],
        )
        return InboundShipmentService(self.db).create_shipment(payload)

    def update(self, shipment_id, *, lines, supplier_id=_UNSET):
        """The edit form's save: the whole line set, as `update_shipment` receives it.

        `supplier_id` is left UNSET unless a test states one, because
        `InboundShipmentUpdate` is dumped with `exclude_unset` - passing None would be a
        save that clears the header rather than one that says nothing about it.
        """
        fields = {
            "shipment_lines": [
                InboundShipmentLineCreate(
                    product_id=str(product.id),
                    quantity_shipped=qty,
                    supplier_id=line_supplier,
                )
                for product, qty, line_supplier in lines
            ]
        }
        if supplier_id is not _UNSET:
            fields["supplier_id"] = supplier_id
        payload = InboundShipmentUpdate(**fields)
        return InboundShipmentService(self.db).update_shipment(
            str(shipment_id), payload, updated_by=None
        )

    def lines(self, shipment_id) -> list[InboundShipmentLine]:
        return (
            self.db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == shipment_id)
            .all()
        )


def _by_product(lines) -> dict[str, InboundShipmentLine]:
    return {str(ln.product_id): ln for ln in lines}


# --------------------------------------------------------------------------- #
# create_shipment                                                              #
# --------------------------------------------------------------------------- #


def test_a_second_factorys_packing_list_does_not_erase_the_first(db):
    """THE test. Kailu, then Caizhou, on one container: both survive."""
    w = World(db)

    first = w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None)])
    db.commit()
    second = w.upload(supplier_id=str(w.caizhou.id), lines=[(w.sink, 5, None)])
    db.commit()

    # One container is one shipment, updated in place.
    assert second.id == first.id
    assert getattr(second, "_already_existed", False) is True

    lines = _by_product(w.lines(first.id))
    assert len(lines) == 2
    assert lines[str(w.tap.id)].quantity_shipped == 10
    assert str(lines[str(w.tap.id)].supplier_id) == str(w.kailu.id)
    assert lines[str(w.sink.id)].quantity_shipped == 5
    assert str(lines[str(w.sink.id)].supplier_id) == str(w.caizhou.id)

    # A mixed container has no single supplier, so the header states none rather than
    # naming whichever uploaded last.
    db.refresh(second)
    assert second.supplier_id is None


def test_a_corrected_list_replaces_only_that_suppliers_lines(db):
    w = World(db)
    w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None)])
    db.commit()
    shipment = w.upload(supplier_id=str(w.caizhou.id), lines=[(w.sink, 5, None)])
    db.commit()

    corrected = w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 42, None)])
    db.commit()

    assert corrected.id == shipment.id
    lines = _by_product(w.lines(shipment.id))
    assert len(lines) == 2
    assert lines[str(w.tap.id)].quantity_shipped == 42  # Kailu's, corrected
    assert lines[str(w.sink.id)].quantity_shipped == 5  # Caizhou's, untouched


def test_an_upload_that_names_no_supplier_still_replaces_everything(db):
    """The n8n PDF path is unchanged: no supplier stated means the whole container."""
    w = World(db)
    w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None)])
    db.commit()
    shipment = w.upload(supplier_id=str(w.caizhou.id), lines=[(w.sink, 5, None)])
    db.commit()

    legacy = w.upload(supplier_id=None, lines=[(w.tap, 7, None)])
    db.commit()

    assert legacy.id == shipment.id
    lines = w.lines(shipment.id)
    assert len(lines) == 1
    assert str(lines[0].product_id) == str(w.tap.id)
    assert lines[0].quantity_shipped == 7
    assert lines[0].supplier_id is None
    # Every line on the container is unattributed now, so the header names nobody. It is
    # derived from the lines each time, never left holding the last supplier it saw.
    db.refresh(legacy)
    assert legacy.supplier_id is None


def test_an_n8n_resend_clears_the_header_the_container_used_to_name(db):
    """The header is DERIVED, and derivation is total: a supplier-less resend empties it.

    A single-factory container names that factory on the header. The n8n PDF path then
    re-reads the same container and names nobody, so what the header said is no longer
    supported by any line on it - and every supplier filter that trusts the header would go
    on showing the container as Kailu's.
    """
    w = World(db)
    first = w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None)])
    db.commit()
    db.refresh(first)
    assert str(first.supplier_id) == str(w.kailu.id)

    resend = w.upload(supplier_id=None, lines=[(w.tap, 12, None)])
    db.commit()

    assert resend.id == first.id
    db.refresh(resend)
    assert resend.supplier_id is None
    lines = w.lines(resend.id)
    assert len(lines) == 1
    assert lines[0].supplier_id is None
    assert lines[0].quantity_shipped == 12


def test_a_container_with_no_lines_takes_the_supplier_the_payload_stated(db):
    """Nothing to derive from, so the caller's word is all there is."""
    w = World(db)

    shipment = w.upload(supplier_id=str(w.kailu.id), lines=[])
    db.commit()

    db.refresh(shipment)
    assert str(shipment.supplier_id) == str(w.kailu.id)
    assert w.lines(shipment.id) == []


def test_a_factorys_upload_supersedes_the_unattributed_lines_for_its_own_products(db):
    """The doubling case. n8n reads the PDF first, the factory's Excel arrives second.

    n8n's read names no supplier, so its lines are unattributed. When Kailu then uploads the
    same container's list as Kailu, the tap it carries is the SAME goods described twice -
    two rows for one product would show 200 on a container that holds 100. The unattributed
    line for a product Kailu's file says nothing about is a different item nobody has claimed
    yet, and it survives untouched.
    """
    w = World(db)
    mat = w.product("MAT")
    first = w.upload(supplier_id=None, lines=[(w.tap, 100, None), (mat, 40, None)])
    db.commit()

    w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 100, None)])
    db.commit()

    lines = w.lines(first.id)
    taps = [ln for ln in lines if str(ln.product_id) == str(w.tap.id)]
    assert len(taps) == 1
    assert taps[0].quantity_shipped == 100
    assert str(taps[0].supplier_id) == str(w.kailu.id)

    mats = [ln for ln in lines if str(ln.product_id) == str(mat.id)]
    assert len(mats) == 1
    assert mats[0].supplier_id is None
    assert mats[0].quantity_shipped == 40


def test_a_payload_that_names_a_supplier_on_only_some_lines_is_still_product_scoped(db):
    """A mixed payload does not become a statement about the whole container.

    Kailu's file is uploaded with the supplier on one line and nothing on another (the
    reader could not tell whose the second was). The unattributed line it carries is still
    only about the product on it, so an unattributed line already on the container for a
    product NOBODY in this payload mentions is a different item and survives - the same rule
    as for a fully-attributed payload.
    """
    w = World(db)
    mat = w.product("MAT")
    first = w.upload(supplier_id=None, lines=[(w.tap, 100, None), (mat, 40, None)])
    db.commit()

    w.upload(supplier_id=None, lines=[(w.tap, 100, str(w.kailu.id)), (w.sink, 5, None)])
    db.commit()

    lines = _by_product(w.lines(first.id))
    assert set(lines) == {str(w.tap.id), str(mat.id), str(w.sink.id)}
    assert str(lines[str(w.tap.id)].supplier_id) == str(w.kailu.id)
    assert lines[str(mat.id)].supplier_id is None
    assert lines[str(mat.id)].quantity_shipped == 40
    assert lines[str(w.sink.id)].supplier_id is None


def test_one_product_from_two_factories_in_one_payload_is_two_lines(db):
    """The merge key is (product, supplier). Merging on product alone would lose the split."""
    w = World(db)
    shipment = w.upload(
        supplier_id=None,
        lines=[
            (w.tap, 10, str(w.kailu.id)),
            (w.tap, 4, str(w.caizhou.id)),
            (w.tap, 6, str(w.kailu.id)),  # same pair twice -> summed
        ],
    )
    db.commit()

    lines = w.lines(shipment.id)
    assert len(lines) == 2
    by_supplier = {str(ln.supplier_id): ln.quantity_shipped for ln in lines}
    assert by_supplier[str(w.kailu.id)] == 16
    assert by_supplier[str(w.caizhou.id)] == 4
    # Two suppliers on the lines -> the header names none.
    db.refresh(shipment)
    assert shipment.supplier_id is None


def test_a_single_supplier_container_still_names_it_on_the_header(db):
    w = World(db)
    shipment = w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None), (w.sink, 3, None)])
    db.commit()

    db.refresh(shipment)
    assert str(shipment.supplier_id) == str(w.kailu.id)
    assert {str(ln.supplier_id) for ln in w.lines(shipment.id)} == {str(w.kailu.id)}


# --------------------------------------------------------------------------- #
# update_shipment - the edit form saves over a mixed container                  #
# --------------------------------------------------------------------------- #


def _mixed_container(db) -> tuple[World, InboundShipment]:
    """One container, Kailu's tap and Caizhou's sink, both with volume and a remark.

    Carton counts are deliberately NOT 1: 1 is the line schema's default for
    `cartons_count`, the only field on it with a non-None default, so a payload dumped
    without `exclude_unset` restates it and a save that never mentioned cartons resets
    every line to a single carton.
    """
    w = World(db)
    w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None)])
    db.commit()
    shipment = w.upload(supplier_id=str(w.caizhou.id), lines=[(w.sink, 5, None)])
    db.commit()
    cartons = {str(w.tap.id): 86, str(w.sink.id): 12}
    for line in w.lines(shipment.id):
        line.cbm = Decimal("1.5000")
        line.remarks = "as packed"
        line.cartons_count = cartons[str(line.product_id)]
    db.commit()
    return w, shipment


def test_an_edit_that_states_only_products_and_quantities_keeps_everything_else(db):
    """The procurement edit form sends `{product_id, quantity_shipped}` and nothing else.

    Deleting every line and re-inserting from that payload set each line's supplier, cbm and
    remark to NULL, so one save on a mixed container erased which factory packed what. The
    payload states the line set; it does not state everything about a line.
    """
    w, shipment = _mixed_container(db)
    before = {str(ln.product_id): str(ln.id) for ln in w.lines(shipment.id)}

    w.update(shipment.id, lines=[(w.tap, 12, None), (w.sink, 6, None)])
    db.commit()

    lines = _by_product(w.lines(shipment.id))
    assert len(lines) == 2
    tap = lines[str(w.tap.id)]
    sink = lines[str(w.sink.id)]
    assert (tap.quantity_shipped, sink.quantity_shipped) == (12, 6)
    assert str(tap.supplier_id) == str(w.kailu.id)
    assert str(sink.supplier_id) == str(w.caizhou.id)
    assert float(tap.cbm) == pytest.approx(1.5)
    assert tap.remarks == "as packed"
    # The carton counts the packing list gave, not the schema default of 1.
    assert (tap.cartons_count, sink.cartons_count) == (86, 12)
    # The same rows, updated - not new ones wearing the old quantities.
    assert {str(ln.product_id): str(ln.id) for ln in lines.values()} == before
    db.refresh(shipment)
    assert shipment.supplier_id is None


def test_an_edit_naming_the_supplier_claims_the_n8n_lines_instead_of_replacing_them(db):
    """An n8n container's lines have NO supplier, and the edit form's save states one.

    Every `(product, supplier)` lookup missed, so every line was deleted and re-inserted
    from a payload that carries only product and quantity - and the cbm and remarks the PDF
    had read off the packing list went with them. The rows are the same goods, so they are
    CLAIMED: they take the supplier the save states and keep everything else.
    """
    w = World(db)
    shipment = w.upload(supplier_id=None, lines=[(w.tap, 10, None), (w.sink, 5, None)])
    db.commit()
    assert {ln.supplier_id for ln in w.lines(shipment.id)} == {None}
    for line in w.lines(shipment.id):
        line.cbm = Decimal("2.1053")
        line.remarks = "read off the PDF"
        line.cartons_count = 40
    db.commit()
    before = {str(ln.product_id): str(ln.id) for ln in w.lines(shipment.id)}

    w.update(
        shipment.id,
        supplier_id=str(w.kailu.id),
        lines=[(w.tap, 12, None), (w.sink, 6, None)],
    )
    db.commit()

    lines = _by_product(w.lines(shipment.id))
    assert len(lines) == 2
    tap = lines[str(w.tap.id)]
    sink = lines[str(w.sink.id)]
    # The same two rows, claimed - not new ones wearing the new quantities.
    assert {str(ln.product_id): str(ln.id) for ln in lines.values()} == before
    assert (tap.quantity_shipped, sink.quantity_shipped) == (12, 6)
    for line in (tap, sink):
        assert str(line.supplier_id) == str(w.kailu.id)
        assert float(line.cbm) == pytest.approx(2.1053)
        assert line.remarks == "read off the PDF"
        assert line.cartons_count == 40
    # One supplier across the lines now, so the header names them.
    db.refresh(shipment)
    assert str(shipment.supplier_id) == str(w.kailu.id)


def test_an_edit_that_drops_a_product_deletes_that_line_and_leaves_the_rest(db):
    """An explicit update still states the WHOLE line set: what it omits is gone."""
    w, shipment = _mixed_container(db)

    w.update(shipment.id, lines=[(w.sink, 5, None)])
    db.commit()

    lines = w.lines(shipment.id)
    assert len(lines) == 1
    assert str(lines[0].product_id) == str(w.sink.id)
    assert str(lines[0].supplier_id) == str(w.caizhou.id)
    # One supplier left on the container, so the header names them again.
    db.refresh(shipment)
    assert str(shipment.supplier_id) == str(w.caizhou.id)


def test_editing_a_product_two_factories_shipped_needs_the_supplier_named(db):
    """There is no one line an unattributed edit of that product could mean.

    Picking either would move a quantity from one factory to the other silently, so the save
    is refused and says what to state instead.
    """
    w = World(db)
    shipment = w.upload(
        supplier_id=None,
        lines=[(w.tap, 16, str(w.kailu.id)), (w.tap, 4, str(w.caizhou.id))],
    )
    db.commit()

    with pytest.raises(AppException) as excinfo:
        w.update(shipment.id, lines=[(w.tap, 20, None)])

    assert excinfo.value.status_code == 409
    message = excinfo.value.detail["message"]
    assert w.tap.product_code in message
    assert "more than one supplier" in message
    db.rollback()
    # Nothing was written: both factories' lines are exactly as they were.
    assert {str(ln.supplier_id): ln.quantity_shipped for ln in w.lines(shipment.id)} == {
        str(w.kailu.id): 16,
        str(w.caizhou.id): 4,
    }


def test_the_same_edit_naming_the_supplier_per_line_updates_the_right_one(db):
    w = World(db)
    shipment = w.upload(
        supplier_id=None,
        lines=[(w.tap, 16, str(w.kailu.id)), (w.tap, 4, str(w.caizhou.id))],
    )
    db.commit()

    w.update(
        shipment.id,
        lines=[(w.tap, 20, str(w.kailu.id)), (w.tap, 4, str(w.caizhou.id))],
    )
    db.commit()

    lines = w.lines(shipment.id)
    assert len(lines) == 2
    assert {str(ln.supplier_id): ln.quantity_shipped for ln in lines} == {
        str(w.kailu.id): 20,
        str(w.caizhou.id): 4,
    }


def test_the_update_schema_carries_the_per_line_supplier_and_its_volume(db):
    """`InboundShipmentUpdate.shipment_lines` is the same line schema the upload uses.

    A field the schema does not declare never reaches the row and the save still returns 200,
    so the supplier a caller states per line has to be on THIS schema, not only on create's.
    """
    w = World(db)
    payload = InboundShipmentUpdate(
        shipment_lines=[
            InboundShipmentLineCreate(
                product_id=str(w.tap.id),
                quantity_shipped=7,
                supplier_id=str(w.kailu.id),
                cbm=Decimal("2.1000"),
                remarks="one pallet",
            )
        ]
    )
    line = payload.shipment_lines[0]
    assert line.supplier_id == str(w.kailu.id)
    assert line.cbm == Decimal("2.1000")
    assert line.remarks == "one pallet"

    shipment = w.upload(supplier_id=None, lines=[(w.tap, 1, None)])
    db.commit()
    InboundShipmentService(db).update_shipment(str(shipment.id), payload, updated_by=None)
    db.commit()

    lines = w.lines(shipment.id)
    assert len(lines) == 1
    assert str(lines[0].supplier_id) == str(w.kailu.id)
    assert lines[0].quantity_shipped == 7
    assert float(lines[0].cbm) == pytest.approx(2.1)
    assert lines[0].remarks == "one pallet"
    db.refresh(shipment)
    assert str(shipment.supplier_id) == str(w.kailu.id)


def test_an_edit_that_states_only_products_and_quantities_keeps_the_price(db):
    """BL-025: a routine save must not wipe the captured `unit_cost` and `currency`.

    The proforma ingest fills both columns on the line; the procurement edit form's line
    schema sends only `{product_id, quantity_shipped}`. When the save rebuilt every line
    from that payload the price went with it, and the supplier then read as "never
    received" on the Order Decision sheet while the PI-vs-PO check lost its incoming side.
    Same rule as the supplier / cbm / remarks case above - the payload states the line set,
    not everything about a line - pinned separately because these two columns are the ones
    the money reports read.
    """
    w = World(db)
    shipment = w.upload(supplier_id=str(w.kailu.id), lines=[(w.tap, 10, None)])
    db.commit()
    for line in w.lines(shipment.id):
        line.unit_cost = Decimal("12.50")
        line.currency = "USD"
    db.commit()

    w.update(shipment.id, lines=[(w.tap, 12, None)])
    db.commit()

    lines = w.lines(shipment.id)
    assert len(lines) == 1
    assert lines[0].quantity_shipped == 12
    assert lines[0].unit_cost == Decimal("12.50")
    assert lines[0].currency == "USD"


# --------------------------------------------------------------------------- #
# packing_list_service.apply - the same story through a workbook                #
# --------------------------------------------------------------------------- #


def _seed_aliases(db) -> None:
    for field, alias in _ALIASES:
        db.add(
            ImportFieldAlias(
                id=str(uuid.uuid4()), doc_type="packing_list", field=field, alias=alias, locale="zh"
            )
        )
    db.flush()


def _workbook(container: str, rows: list[tuple[str, float, float, float, str]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([f"货柜号：{container}"])
    ws.append(["产品型号", "品名", "数量", "箱数", "体积(cbm)", "备注"])
    for code, qty, cartons, cbm, remark in rows:
        ws.append([code, "座厕", qty, cartons, cbm, remark])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_two_workbooks_for_one_container_keep_both_factories(db):
    w = World(db)
    _seed_aliases(db)
    db.commit()

    packing_list_service.apply(
        db,
        _workbook(w.container, [(w.tap.product_code, 10, 2, 0.21, "loaded first")]),
        supplier_id=str(w.kailu.id),
    )
    db.commit()
    out = packing_list_service.apply(
        db,
        _workbook(w.container, [(w.sink.product_code, 5, 1, 0.5, "")]),
        supplier_id=str(w.caizhou.id),
    )
    db.commit()

    assert out["shipments_created"] == 0
    assert out["shipments_updated"] == 1

    shipments = (
        db.query(InboundShipment)
        .filter(InboundShipment.shipping_container_number == w.container)
        .all()
    )
    assert len(shipments) == 1
    lines = _by_product(w.lines(shipments[0].id))
    assert len(lines) == 2

    tap = lines[str(w.tap.id)]
    assert str(tap.supplier_id) == str(w.kailu.id)
    assert tap.quantity_shipped == 10
    # cbm and the supplier's own remark are carried, not thrown away: 0.21 per unit x 10.
    assert float(tap.cbm) == pytest.approx(2.1)
    assert tap.remarks == "loaded first"

    sink = lines[str(w.sink.id)]
    assert str(sink.supplier_id) == str(w.caizhou.id)
    assert sink.quantity_shipped == 5
    assert float(sink.cbm) == pytest.approx(2.5)
    assert sink.remarks is None

    assert shipments[0].supplier_id is None  # mixed container
