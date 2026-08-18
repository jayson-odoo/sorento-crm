"""S10 - the Sorento packing list: one container, every factory that loaded it.

What Ms Tee used to build by hand: the lines of two or three suppliers under one container,
each factory subtotalled, a grand total, the SORENTO / MOCHA split, and a remarks column that
already says where the shipment differs from the loading plan that supplier was sent.

Everything asserted here is DERIVED. The factory is the supplier the line was uploaded as, the
company is the product's brand, the discrepancies are the latest supplier notice compared with
what actually arrived. None of it is typed in, so the test is about the derivation being right
rather than about a form being saved.

Postgres only, on a blank schema, seeding every FK target itself: CI's database is empty, so a
test that borrows an existing category, brand or supplier passes locally and fails there.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.scm import LoadingPlan
from app.models.supplier_notice import SupplierNotice, SupplierNoticeLine
from app.services.error_handler import AppException
from app.services.scm import consolidated_packing_list as svc
from tests._pg_fixture import blank_session

MARKER = "ZZCPL"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


class World:
    """Two factories on one container, plus a line whose factory we were never told.

    Deliberately mixed: one MOCHA-brand product (the company split), one line the supplier
    stated a volume for and one that only the catalogue can measure (the cbm fallback), one
    line with no volume anywhere (so a partial cbm is visible as partial), and a supplier
    notice for the first factory that asked for more of one product, less of another, and one
    product that never turned up at all.
    """

    def __init__(self, db):
        self.db = db
        self.tag = uuid.uuid4().hex[:8].upper()

        self.category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=f"{MARKER}-CAT-{self.tag}",
            category_name=f"{MARKER} category",
        )
        self.uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=f"{MARKER}{self.tag}"[:20], uom_name="pcs"
        )
        self.mocha = Brand(
            id=str(uuid.uuid4()), brand_code="MOCHA", brand_name="Mocha", is_active=True
        )
        self.sandel = Brand(
            id=str(uuid.uuid4()),
            brand_code=f"SANDEL-{self.tag}"[:50],
            brand_name="Sandel",
            is_active=True,
        )
        db.add_all([self.category, self.uom, self.mocha, self.sandel])
        db.flush()

        # Codes carry the shared tag then the sort key, so "ordered by product code" is a
        # deterministic assertion rather than whatever uuid4 happened to produce.
        self.tap = self.product("1TAP", brand=self.sandel)
        self.mocha_basin = self.product("2BASIN", brand=self.mocha, dims=(500, 400, 300))
        self.mat = self.product("3MAT")
        self.sink = self.product("4SINK")
        self.orphan = self.product("5ORPHAN")
        self.never_packed = self.product("6GONE")

        # Ordered by supplier NAME, so A sorts before B whatever their ids are.
        self.kailu = self.supplier("A-KAILU")
        self.caizhou = self.supplier("B-CAIZHOU")

        self.shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"{MARKER}-SH-{self.tag}",
            shipment_date=date(2026, 8, 1),
            shipping_container_number=f"{MARKER}U{self.tag}",
            bill_of_lading_number=f"BL-{self.tag}",
            shipment_status="in_transit",
        )
        db.add(self.shipment)
        db.flush()

        self.line(self.kailu, self.tap, qty=490, cartons=86, cbm="2.1053", remarks="fragile")
        self.line(self.kailu, self.mocha_basin, qty=100, cartons=10)
        self.line(self.kailu, self.mat, qty=120, cartons=12)
        self.line(self.caizhou, self.sink, qty=50, cartons=5, cbm="1.5000")
        self.line(None, self.orphan, qty=7, cartons=1)

    # -- seeding ---------------------------------------------------------- #

    def product(self, key: str, *, brand: Brand | None = None, dims=None) -> Product:
        p = Product(
            id=str(uuid.uuid4()),
            product_code=f"{MARKER}-{self.tag}-{key}",
            product_name=f"{key} product",
            category_id=self.category.id,
            base_uom_id=self.uom.id,
            brand_id=brand.id if brand else None,
            list_price=0,
            is_active=True,
        )
        if dims:
            p.dimensions_length, p.dimensions_width, p.dimensions_height = dims
        self.db.add(p)
        self.db.flush()
        return p

    def supplier(self, name: str) -> Supplier:
        s = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=f"{MARKER}-{name}-{self.tag}"[:50],
            supplier_name=f"{MARKER} {name}",
            is_active=True,
        )
        self.db.add(s)
        self.db.flush()
        return s

    def line(self, supplier, product, *, qty, cartons, cbm=None, remarks=None):
        row = InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=self.shipment.id,
            supplier_id=supplier.id if supplier else None,
            product_id=product.id,
            quantity_shipped=qty,
            cartons_count=cartons,
            cbm=cbm,
            remarks=remarks,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def notice(
        self,
        supplier,
        lines,
        *,
        created_at: datetime,
        plan: bool = True,
        kind: str = "pack",
        sent_at: datetime | None = None,
    ):
        """One notice with its lines, as the supplier received it.

        `kind` is `pack` (goods the factory holds and was asked to load) unless a test wants
        `produce` (goods it still has to make), which is not a pack plan at all.
        """
        loading_plan = None
        if plan:
            loading_plan = LoadingPlan(
                id=str(uuid.uuid4()),
                supplier_id=supplier.id,
                container_count=1,
                container_cbm=68,
                capacity_cbm=68,
            )
            self.db.add(loading_plan)
            self.db.flush()
        row = SupplierNotice(
            id=str(uuid.uuid4()),
            supplier_id=supplier.id,
            loading_plan_id=loading_plan.id if loading_plan else None,
            channel="email",
            status="sent",
            created_at=created_at,
            sent_at=sent_at,
        )
        self.db.add(row)
        self.db.flush()
        for i, (product, qty) in enumerate(lines):
            self.db.add(
                SupplierNoticeLine(
                    id=str(uuid.uuid4()),
                    notice_id=row.id,
                    product_id=product.id,
                    item_code=product.product_code,
                    product_name=product.product_name,
                    qty=qty,
                    kind=kind,
                    sort_order=i,
                )
            )
        self.db.flush()
        return row

    def notice_for_kailu(self) -> SupplierNotice:
        """The plan Kailu was sent: more taps, fewer mats, and a product that never came.

        An older notice is seeded first so "the latest one" is a claim under test rather than
        an accident of there being only one.
        """
        self.notice(
            self.kailu,
            [(self.tap, 1000)],
            created_at=datetime(2026, 7, 1, 9, 0, 0),
        )
        return self.notice(
            self.kailu,
            [(self.tap, 500), (self.mat, 100), (self.never_packed, 100)],
            created_at=datetime(2026, 8, 1, 9, 0, 0),
        )


def _factory(payload: dict, name_fragment: str) -> dict:
    return next(f for f in payload["factories"] if name_fragment in (f["supplier_name"] or ""))


def _line(factory: dict, code_suffix: str) -> dict:
    return next(l for l in factory["lines"] if l["product_code"].endswith(code_suffix))


# --------------------------------------------------------------------------- #
# grouping and arithmetic
# --------------------------------------------------------------------------- #


def test_the_container_is_grouped_by_factory_with_the_unknown_one_last(db):
    # The header of a mixed container names nobody, so the factory has to come off the line.
    w = World(db)

    out = svc.build(db, str(w.shipment.id))

    assert out["shipment_id"] == str(w.shipment.id)
    assert out["container_no"] == w.shipment.shipping_container_number
    assert out["bl_no"] == w.shipment.bill_of_lading_number
    assert out["status"] == "in_transit"
    assert [f["supplier_name"] for f in out["factories"]] == [
        w.kailu.supplier_name,
        w.caizhou.supplier_name,
        "Unassigned",
    ]
    assert out["factories"][-1]["supplier_id"] is None
    # Within a factory, the order of the sheet is the order of the model numbers.
    assert [l["product_code"] for l in out["factories"][0]["lines"]] == [
        w.tap.product_code,
        w.mocha_basin.product_code,
        w.mat.product_code,
    ]


def test_each_factory_subtotals_its_own_lines_and_says_how_much_volume_it_knows(db):
    w = World(db)

    out = svc.build(db, str(w.shipment.id))

    kailu = _factory(out, "A-KAILU")
    assert kailu["subtotal"]["lines"] == 3
    assert kailu["subtotal"]["qty"] == 710
    assert kailu["subtotal"]["cartons"] == 108
    # 2.1053 stated by the supplier + 6.0 measured from the catalogue. The mat has no
    # volume anywhere, so two of three lines are known and the figure says so.
    assert kailu["subtotal"]["cbm"] == pytest.approx(8.1053)
    assert kailu["subtotal"]["cbm_known_lines"] == 2

    unassigned = _factory(out, "Unassigned")
    assert unassigned["subtotal"] == {
        "lines": 1,
        "qty": 7,
        "cartons": 1,
        "cbm": 0.0,
        "cbm_known_lines": 0,
    }


def test_the_grand_total_is_the_whole_container(db):
    w = World(db)

    out = svc.build(db, str(w.shipment.id))

    assert out["total"]["lines"] == 5
    assert out["total"]["qty"] == 767
    assert out["total"]["cartons"] == 114
    assert out["total"]["cbm"] == pytest.approx(9.6053)
    assert out["total"]["cbm_known_lines"] == 3


def test_a_missing_volume_falls_back_to_the_catalogue_and_then_to_nothing(db):
    # A cbm invented for a product nobody measured would be worse than an empty cell.
    w = World(db)

    out = svc.build(db, str(w.shipment.id))
    kailu = _factory(out, "A-KAILU")

    assert _line(kailu, "1TAP")["cbm"] == pytest.approx(2.1053)
    assert _line(kailu, "2BASIN")["cbm"] == pytest.approx(6.0)  # 500*400*300mm x 100
    assert _line(kailu, "3MAT")["cbm"] is None


def test_the_company_split_is_read_off_the_brand_and_always_prints_both_rows(db):
    w = World(db)

    out = svc.build(db, str(w.shipment.id))

    kailu = _factory(out, "A-KAILU")
    assert _line(kailu, "2BASIN")["company"] == "MOCHA"
    assert _line(kailu, "2BASIN")["brand"] == "MOCHA"
    assert _line(kailu, "1TAP")["company"] == "SORENTO"
    # No brand at all is Sorento's, the same as SANDEL / CABANA are.
    assert _line(_factory(out, "B-CAIZHOU"), "4SINK")["company"] == "SORENTO"

    split = {row["company"]: row for row in out["split"]}
    assert [row["company"] for row in out["split"]] == ["SORENTO", "MOCHA"]
    assert split["SORENTO"]["lines"] == 4
    assert split["SORENTO"]["qty"] == 667
    assert split["SORENTO"]["cartons"] == 104
    assert split["SORENTO"]["cbm"] == pytest.approx(3.6053)
    assert split["SORENTO"]["cbm_known_lines"] == 2
    assert split["MOCHA"]["lines"] == 1
    assert split["MOCHA"]["qty"] == 100
    assert split["MOCHA"]["cartons"] == 10
    assert split["MOCHA"]["cbm"] == pytest.approx(6.0)
    assert split["MOCHA"]["cbm_known_lines"] == 1


def test_both_split_rows_are_present_even_when_one_company_shipped_nothing(db):
    w = World(db)
    db.query(InboundShipmentLine).filter(
        InboundShipmentLine.product_id == w.mocha_basin.id
    ).delete(synchronize_session=False)

    out = svc.build(db, str(w.shipment.id))

    mocha = next(row for row in out["split"] if row["company"] == "MOCHA")
    assert mocha == {
        "company": "MOCHA",
        "lines": 0,
        "qty": 0,
        "cartons": 0,
        "cbm": 0.0,
        "cbm_known_lines": 0,
    }


# --------------------------------------------------------------------------- #
# what the supplier was asked for, against what arrived
# --------------------------------------------------------------------------- #


def test_the_remarks_say_where_the_shipment_differs_from_the_loading_plan(db):
    w = World(db)
    notice = w.notice_for_kailu()

    out = svc.build(db, str(w.shipment.id))
    kailu = _factory(out, "A-KAILU")

    assert kailu["notice_id"] == str(notice.id)
    assert kailu["loading_plan_id"] == str(notice.loading_plan_id)
    # The LATEST notice (500), not the one from July that asked for 1000.
    assert _line(kailu, "1TAP")["discrepancies"] == [
        "Loading plan asked 500, packed 490 (short 10)"
    ]
    assert _line(kailu, "3MAT")["discrepancies"] == [
        "Loading plan asked 100, packed 120 (over 20)"
    ]
    assert _line(kailu, "2BASIN")["discrepancies"] == ["Not on the loading plan"]
    # The supplier's own note is kept apart from the words the system derived.
    assert _line(kailu, "1TAP")["remarks"] == "fragile"


def test_what_was_asked_for_and_never_came_is_listed_rather_than_dropped(db):
    w = World(db)
    w.notice_for_kailu()

    out = svc.build(db, str(w.shipment.id))
    kailu = _factory(out, "A-KAILU")

    assert kailu["not_packed"] == [
        {
            "product_id": str(w.never_packed.id),
            "product_code": w.never_packed.product_code,
            "product_name": w.never_packed.product_name,
            "planned_qty": 100,
        }
    ]


def test_a_factory_that_was_never_sent_a_plan_is_compared_against_nothing(db):
    # Silence, not "Not on the loading plan" against every line, which would read as a
    # container full of mistakes.
    w = World(db)
    w.notice_for_kailu()

    out = svc.build(db, str(w.shipment.id))

    for name in ("B-CAIZHOU", "Unassigned"):
        factory = _factory(out, name)
        assert factory["notice_id"] is None
        assert factory["loading_plan_id"] is None
        assert factory["not_packed"] == []
        assert all(l["discrepancies"] == [] for l in factory["lines"])


def test_a_quantity_that_matches_the_plan_says_nothing(db):
    w = World(db)
    w.notice(w.kailu, [(w.tap, 490)], created_at=datetime(2026, 8, 2, 9, 0, 0))

    out = svc.build(db, str(w.shipment.id))

    assert _line(_factory(out, "A-KAILU"), "1TAP")["discrepancies"] == []


def test_a_notice_that_only_asked_for_production_is_not_a_pack_plan(db):
    """`produce` lines are stock the factory still has to make.

    A notice made entirely of them asked for nothing to be loaded, so there is nothing for
    this container to be short of - comparing against it would mark every line "Not on the
    loading plan" and read as a container full of mistakes. The notice is still named, so
    the screen can say which document was looked at.
    """
    w = World(db)
    notice = w.notice(
        w.kailu,
        [(w.tap, 500), (w.never_packed, 100)],
        created_at=datetime(2026, 8, 1, 9, 0, 0),
        kind="produce",
    )

    out = svc.build(db, str(w.shipment.id))
    kailu = _factory(out, "A-KAILU")

    assert kailu["notice_id"] == str(notice.id)
    # Named, but not compared against: without this flag a silent line is indistinguishable
    # from a line that matched its plan exactly.
    assert kailu["has_pack_plan"] is False
    assert all(l["discrepancies"] == [] for l in kailu["lines"])
    assert kailu["not_packed"] == []


def test_a_factory_says_whether_the_notice_it_names_is_a_pack_plan(db):
    """`has_pack_plan` is true only when the notice actually asked for goods to be loaded.

    Kailu was sent one; Caizhou was sent nothing at all. Both report a `notice_id` the screen
    can name (Caizhou's being null), and only Kailu's is something a container can be short of.
    """
    w = World(db)
    w.notice_for_kailu()

    out = svc.build(db, str(w.shipment.id))

    assert _factory(out, "A-KAILU")["has_pack_plan"] is True
    assert _factory(out, "B-CAIZHOU")["has_pack_plan"] is False
    assert _factory(out, "Unassigned")["has_pack_plan"] is False


def test_the_notice_compared_against_is_the_one_the_container_could_have_been_packed_to(db):
    """A notice is sent to a supplier, not to a container, so the date is the only link.

    The container sailed on 1 Aug. A plan approved in September is a plan for the NEXT
    container, and comparing this one against it would invent a shortfall in every line.
    """
    w = World(db)
    in_time = w.notice(w.kailu, [(w.tap, 500)], created_at=datetime(2026, 8, 1, 9, 0, 0))
    w.notice(w.kailu, [(w.tap, 900)], created_at=datetime(2026, 9, 15, 9, 0, 0))

    out = svc.build(db, str(w.shipment.id))
    kailu = _factory(out, "A-KAILU")

    assert kailu["notice_id"] == str(in_time.id)
    assert _line(kailu, "1TAP")["discrepancies"] == [
        "Loading plan asked 500, packed 490 (short 10)"
    ]


def test_a_container_older_than_every_notice_falls_back_to_the_latest(db):
    """Better a comparison against a later plan, said out loud, than no comparison at all."""
    w = World(db)
    w.notice(w.kailu, [(w.tap, 900)], created_at=datetime(2026, 9, 1, 9, 0, 0))
    latest = w.notice(w.kailu, [(w.tap, 800)], created_at=datetime(2026, 9, 15, 9, 0, 0))

    out = svc.build(db, str(w.shipment.id))
    kailu = _factory(out, "A-KAILU")

    assert kailu["notice_id"] == str(latest.id)


def test_the_factory_says_when_the_notice_it_was_compared_against_was_written_and_sent(db):
    """A comparison that looks wrong has to be traceable to the document it was made against."""
    w = World(db)
    notice = w.notice(
        w.kailu,
        [(w.tap, 500)],
        created_at=datetime(2026, 8, 1, 9, 0, 0),
        sent_at=datetime(2026, 8, 1, 9, 30, 0),
    )

    out = svc.build(db, str(w.shipment.id))

    kailu = _factory(out, "A-KAILU")
    assert kailu["notice_created_at"] == notice.created_at.isoformat()
    assert kailu["notice_sent_at"] == "2026-08-01T09:30:00"
    # A factory with no notice states both as nothing rather than omitting the keys.
    caizhou = _factory(out, "B-CAIZHOU")
    assert caizhou["notice_created_at"] is None
    assert caizhou["notice_sent_at"] is None


# --------------------------------------------------------------------------- #
# the edges
# --------------------------------------------------------------------------- #


def test_a_container_with_no_lines_is_an_empty_list_not_a_404(db):
    # "Read but not yet unpacked" is a state the screen has to be able to draw.
    w = World(db)
    db.query(InboundShipmentLine).filter(
        InboundShipmentLine.shipment_id == w.shipment.id
    ).delete(synchronize_session=False)

    out = svc.build(db, str(w.shipment.id))

    assert out["factories"] == []
    assert out["total"] == {"lines": 0, "qty": 0, "cartons": 0, "cbm": 0.0, "cbm_known_lines": 0}
    assert [row["company"] for row in out["split"]] == ["SORENTO", "MOCHA"]
    assert all(row["qty"] == 0 for row in out["split"])


def test_an_unknown_container_is_a_404(db):
    with pytest.raises(AppException) as err:
        svc.build(db, str(uuid.uuid4()))

    assert err.value.status_code == 404


# --------------------------------------------------------------------------- #
# the workbook
# --------------------------------------------------------------------------- #


def _cells(payload: dict) -> list[list]:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(svc.to_xlsx(payload)))
    assert wb.sheetnames == ["PACKING LIST"]
    return [list(row) for row in wb["PACKING LIST"].iter_rows(values_only=True)]


def test_the_workbook_carries_every_factory_its_subtotal_and_the_split(db):
    w = World(db)
    w.notice_for_kailu()
    payload = svc.build(db, str(w.shipment.id))

    rows = _cells(payload)
    first_column = [r[0] for r in rows]

    assert ["FACTORY", "NO", "MODEL", "DESCRIPTION", "QTY", "CTN QTY", "CBM", "LOGO", "REMARKS"] in [
        list(r) for r in rows
    ]
    assert f"{w.kailu.supplier_name} subtotal" in first_column
    assert f"{w.caizhou.supplier_name} subtotal" in first_column
    assert "TOTAL" in first_column
    assert "SORENTO" in first_column
    assert "MOCHA" in first_column


def test_the_workbook_writes_quantities_as_numbers_not_text(db):
    # A total the recipient cannot sum in Excel is a picture of a packing list.
    w = World(db)
    payload = svc.build(db, str(w.shipment.id))

    rows = _cells(payload)
    total = next(r for r in rows if r[0] == "TOTAL")

    assert total[4] == 767
    assert total[5] == 114
    assert isinstance(total[6], float)


def test_the_download_is_named_after_the_container_with_nothing_a_filesystem_argues_with(db):
    w = World(db)
    w.shipment.shipping_container_number = "FSCU 810/3365"
    db.flush()
    payload = svc.build(db, str(w.shipment.id))

    assert svc.export_filename(payload) == "FSCU8103365-packing-list.xlsx"


def test_a_container_with_no_number_falls_back_to_the_shipment_number(db):
    w = World(db)
    w.shipment.shipping_container_number = None
    db.flush()
    payload = svc.build(db, str(w.shipment.id))

    assert svc.export_filename(payload) == f"{w.shipment.shipment_number}-packing-list.xlsx"


def test_the_workbook_states_what_was_asked_for_and_never_packed(db):
    w = World(db)
    w.notice_for_kailu()
    payload = svc.build(db, str(w.shipment.id))

    rows = _cells(payload)
    gone = next(r for r in rows if r[2] == w.never_packed.product_code)

    assert gone[4] is None
    assert gone[8] == "Not packed - loading plan asked 100"


# --------------------------------------------------------------------------- #
# over the wire
# --------------------------------------------------------------------------- #


#: The incumbent company every row this suite seeds is auto-stamped with (tests/conftest.py).
SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def _caller(db, monkeypatch, *, email: str, permitted: bool) -> TestClient:
    """A TestClient reading the session the test seeded, with a company to read it under.

    The company half is not optional: the api router depends on `apply_company_scope`, which
    in a real request resolves the caller's companies from their token. Overridden away, the
    session falls to a fail-closed empty scope and every owned row - shipment included -
    disappears, which reads as a 404 from the route rather than as a missing test principal.
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    principal = {"id": str(uuid.uuid4()), "email": email}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: principal
    # The scm router is wrapped in the module guard, which authenticates separately.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: permitted and slug == "scm.dashboard.view",
    )

    scope = frozenset({SORENTO_COMPANY_ID})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return TestClient(app)


@pytest.fixture
def client(db, monkeypatch):
    """A caller holding `scm.dashboard.view`."""
    try:
        yield _caller(db, monkeypatch, email="zzt-scm@example.com", permitted=True)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def stranger(db, monkeypatch):
    """The same caller without the read permission."""
    try:
        yield _caller(db, monkeypatch, email="zzt-nobody@example.com", permitted=False)
    finally:
        app.dependency_overrides.clear()


def test_the_packing_list_route_returns_the_consolidated_list(db, client):
    w = World(db)
    w.notice_for_kailu()

    r = client.get(f"/api/v1/scm/inbound-shipments/{w.shipment.id}/packing-list")

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["factories"]) == 3
    assert body["total"]["qty"] == 767
    assert [row["company"] for row in body["split"]] == ["SORENTO", "MOCHA"]


def test_the_export_route_returns_a_workbook_named_after_the_container(db, client):
    import openpyxl

    w = World(db)

    r = client.get(f"/api/v1/scm/inbound-shipments/{w.shipment.id}/packing-list/export")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == _XLSX
    assert (
        r.headers["content-disposition"]
        == f'attachment; filename="{w.shipment.shipping_container_number}-packing-list.xlsx"'
    )
    wb = openpyxl.load_workbook(BytesIO(r.content))
    first_column = [row[0] for row in wb["PACKING LIST"].iter_rows(values_only=True)]
    assert f"{w.kailu.supplier_name} subtotal" in first_column
    assert "SORENTO" in first_column
    assert "MOCHA" in first_column


def test_an_unknown_container_is_a_404_over_the_wire(db, client):
    r = client.get(f"/api/v1/scm/inbound-shipments/{uuid.uuid4()}/packing-list")

    assert r.status_code == 404, r.text


def test_both_routes_require_the_scm_read_permission(db, stranger):
    w = World(db)

    assert stranger.get(
        f"/api/v1/scm/inbound-shipments/{w.shipment.id}/packing-list"
    ).status_code == 403
    assert stranger.get(
        f"/api/v1/scm/inbound-shipments/{w.shipment.id}/packing-list/export"
    ).status_code == 403
