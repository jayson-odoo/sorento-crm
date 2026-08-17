"""S2-BE-1: `units_of_measure.decimal_places` (AC-F12, UOM half).

Contract: `documentation/plans/scm/PLAN-scm-front-planning.md` section 6.4, `UAC-scm-front-
planning.md` AC-F12, `STAGE2-scm-front-planning-worknotes.md` slice S2-BE-1.

**TDD red.** None of this exists yet:

* `UnitOfMeasure.decimal_places` (SmallInteger, `CHECK 0..4`, `NOT NULL DEFAULT 0`) is not a
  column on the model.
* create/update/list/detail/select do not carry it.
* `app.services.uom_decimal_places` (`classify_uom_name`, `backfill_uom_decimal_places`) does
  not exist.
* `CanonicalUnitOfMeasure` / `_uom_columns` do not accept it.

Every test below is written to PASS once the coder lands that surface, and to fail NOW for a
reason that names the missing piece - a route assertion on a dropped/absent field, a
`TypeError: 'decimal_places' is an invalid keyword argument` from the ORM, or an `ImportError`
on the not-yet-created service module (imported locally inside the classify/backfill tests so
one missing module does not mask the unrelated CRUD/model failures in this same file).

Postgres only. `tests/_pg_fixture.py` `blank_session()` gives an isolated blank schema (own
scratch schema per test run, `companies` auto-seeded) for the CRUD/model/backfill tests;
`master_ingest_service` tests reuse the real-engine-rolled-back-transaction idiom already
established by `tests/test_master_ingest.py`, since that module's own suite runs that way.
Every row this file creates is marker-prefixed (`ZZTUOM`) and none is borrowed with `LIMIT 1`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.database import engine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import blank_session

MARKER = "ZZTUOM"
_SORENTO = "00000000-0000-0000-0000-000000000001"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str = "") -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()[:50]


# =========================================================================== #
# route fixture: TestClient over a blank isolated schema, superadmin caller
# =========================================================================== #


@pytest.fixture()
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        uid = _u()
        role_id = _u()
        db.add(UserRole(id=role_id, slug="superadmin", name="Superadmin", is_protected=True))
        db.add(User(id=uid, email=f"{uid}@zzt-uom.test", name="UOM Tester", status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
        db.commit()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": uid, "email": f"{uid}@zzt-uom.test", "name": "UOM Tester"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db

        app.dependency_overrides.clear()


def _client() -> TestClient:
    return TestClient(app)


# =========================================================================== #
# create
# =========================================================================== #


def test_create_stores_given_decimal_places(api):
    client = _client()
    resp = client.post(
        "/api/v1/master-data/units-of-measure/",
        json={"uom_code": _code("KG"), "uom_name": "Kilogram", "decimal_places": 3},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["decimal_places"] == 3


def test_create_omitted_decimal_places_defaults_to_zero(api):
    client = _client()
    resp = client.post(
        "/api/v1/master-data/units-of-measure/",
        json={"uom_code": _code("EA"), "uom_name": "Each"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["decimal_places"] == 0


@pytest.mark.parametrize("bad_value", [5, -1])
def test_create_rejects_out_of_range_decimal_places(api, bad_value):
    client = _client()
    resp = client.post(
        "/api/v1/master-data/units-of-measure/",
        json={"uom_code": _code("BAD"), "uom_name": "Bad unit", "decimal_places": bad_value},
    )
    assert resp.status_code == 422, resp.text


# =========================================================================== #
# update
# =========================================================================== #


def _create(client, name="Kilogram", decimal_places=3) -> dict:
    resp = client.post(
        "/api/v1/master-data/units-of-measure/",
        json={"uom_code": _code("U"), "uom_name": name, "decimal_places": decimal_places},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_update_omitted_decimal_places_preserves_stored_value(api):
    client = _client()
    created = _create(client, decimal_places=3)

    resp = client.put(
        f"/api/v1/master-data/units-of-measure/{created['id']}",
        json={"description": "renamed description only"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["decimal_places"] == 3


def test_update_sets_new_decimal_places(api):
    client = _client()
    created = _create(client, decimal_places=3)

    resp = client.put(
        f"/api/v1/master-data/units-of-measure/{created['id']}",
        json={"decimal_places": 2},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["decimal_places"] == 2


def test_update_rejects_out_of_range_decimal_places(api):
    client = _client()
    created = _create(client, decimal_places=3)

    resp = client.put(
        f"/api/v1/master-data/units-of-measure/{created['id']}",
        json={"decimal_places": 5},
    )
    assert resp.status_code == 422, resp.text


# =========================================================================== #
# list / detail / select
# =========================================================================== #


def test_list_returns_decimal_places(api):
    client = _client()
    _create(client, decimal_places=3)

    resp = client.get("/api/v1/master-data/units-of-measure/")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert rows, "the created row must appear in the list"
    assert any(r.get("decimal_places") == 3 for r in rows)


def test_detail_returns_decimal_places(api):
    client = _client()
    created = _create(client, decimal_places=3)

    resp = client.get(f"/api/v1/master-data/units-of-measure/{created['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["decimal_places"] == 3


def test_select_returns_decimal_places(api):
    client = _client()
    code = _code("SEL")
    resp = client.post(
        "/api/v1/master-data/units-of-measure/",
        json={"uom_code": code, "uom_name": "Selectable kg", "decimal_places": 3},
    )
    assert resp.status_code == 201, resp.text

    resp = client.get("/api/v1/master-data/units-of-measure/select", params={"query": code})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows, "the created row must appear in the select list"
    assert rows[0]["decimal_places"] == 3


# =========================================================================== #
# model: column default + DB CHECK 0..4
# =========================================================================== #


def test_model_decimal_places_defaults_to_zero():
    with blank_session() as db:
        uom = UnitOfMeasure(id=_u(), uom_code=_code("MZ"), uom_name="model default")
        db.add(uom)
        db.flush()
        db.refresh(uom)
        assert uom.decimal_places == 0


@pytest.mark.parametrize("bad_value", [5, -1])
def test_model_check_constraint_rejects_out_of_range(bad_value):
    with blank_session() as db:
        with pytest.raises(IntegrityError):
            uom = UnitOfMeasure(
                id=_u(), uom_code=_code("CK"), uom_name="check test",
                decimal_places=bad_value,
            )
            db.add(uom)
            db.flush()


# =========================================================================== #
# classify_uom_name
# =========================================================================== #


@pytest.mark.parametrize(
    "name",
    ["ea", "each", "piece", "pieces", "unit", "units", "pc", "pcs", "set", "sets",
     "EA", "Each", "PIECE"],
)
def test_classify_count_aliases(name):
    from app.services.uom_decimal_places import classify_uom_name

    assert classify_uom_name(name) == "count"


@pytest.mark.parametrize(
    "name",
    ["kg", "kilogram", "kilograms", "g", "gram", "grams", "m", "meter", "meters",
     "metre", "metres", "cm", "centimeter", "centimeters", "centimetre", "centimetres",
     "l", "liter", "liters", "litre", "litres", "ml", "milliliter", "milliliters",
     "millilitre", "millilitres", "m2", "m²", "square meter", "square meters",
     "square metre", "square metres", "m3", "m³", "cubic meter", "cubic meters",
     "cubic metre", "cubic metres", "KG", "Kilogram", "Litre"],
)
def test_classify_measure_aliases(name):
    from app.services.uom_decimal_places import classify_uom_name

    assert classify_uom_name(name) == "measure"


def test_classify_uses_name_only_never_code():
    """`code='EA', name='Kilogram'` is a measure unit - the code is never consulted."""
    from app.services.uom_decimal_places import classify_uom_name

    assert classify_uom_name("Kilogram") == "measure"


def test_classify_unknown_name():
    from app.services.uom_decimal_places import classify_uom_name

    assert classify_uom_name(_code("nonsense-uom-name")) == "unknown"


# =========================================================================== #
# backfill_uom_decimal_places
# =========================================================================== #


def _category(db):
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    db.add(cat)
    db.flush()
    return cat


def _product(db, uom, cat):
    p = Product(
        id=_u(), product_code=_code("SKU"), product_name="backfill product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0, is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _sales_order_line(db, product, qty_ordered):
    from app.models.order import Customer, SalesOrder, SalesOrderLine

    cust = Customer(id=_u(), customer_code=_code("C")[:30], customer_name="backfill co")
    db.add(cust)
    db.flush()
    so = SalesOrder(id=_u(), so_number=_code("SO")[:50], customer_id=cust.id, status="open")
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id,
        qty_ordered=Decimal(qty_ordered), qty_delivered=0,
    )
    db.add(line)
    db.flush()
    return line


def test_backfill_count_alias_uom_is_zero():
    from app.services.uom_decimal_places import backfill_uom_decimal_places

    with blank_session() as db:
        uom = UnitOfMeasure(id=_u(), uom_code=_code("EACH"), uom_name="each")
        db.add(uom)
        db.flush()

        backfill_uom_decimal_places(db)
        db.refresh(uom)
        assert uom.decimal_places == 0


def test_backfill_unknown_name_uom_is_zero():
    from app.services.uom_decimal_places import backfill_uom_decimal_places

    with blank_session() as db:
        uom = UnitOfMeasure(id=_u(), uom_code=_code("UNK"), uom_name=_code("mystery unit"))
        db.add(uom)
        db.flush()

        backfill_uom_decimal_places(db)
        db.refresh(uom)
        assert uom.decimal_places == 0


def test_backfill_measure_uom_takes_greatest_observed_scale_capped_at_four():
    from app.services.uom_decimal_places import backfill_uom_decimal_places

    with blank_session() as db:
        uom = UnitOfMeasure(id=_u(), uom_code=_code("KG"), uom_name="kilogram")
        db.add(uom)
        db.flush()
        cat = _category(db)
        product = _product(db, uom, cat)
        # trailing-zero scale 1, and a scale of 7 that must be capped at 4.
        _sales_order_line(db, product, "2.50000")
        _sales_order_line(db, product, "1.2345678")

        backfill_uom_decimal_places(db)
        db.refresh(uom)
        assert uom.decimal_places == 4


def test_backfill_only_fills_null_rows_leaving_a_carried_value_untouched():
    from app.services.uom_decimal_places import backfill_uom_decimal_places

    with blank_session() as db:
        already_set = UnitOfMeasure(
            id=_u(), uom_code=_code("SET"), uom_name="kilogram", decimal_places=1,
        )
        null_row = UnitOfMeasure(id=_u(), uom_code=_code("NUL"), uom_name="each")
        db.add_all([already_set, null_row])
        db.flush()

        backfill_uom_decimal_places(db)
        db.refresh(already_set)
        db.refresh(null_row)

        assert already_set.decimal_places == 1, "an already-carried value is left alone"
        assert null_row.decimal_places == 0


def test_backfill_does_not_rewrite_any_quantity_row():
    from app.services.uom_decimal_places import backfill_uom_decimal_places

    with blank_session() as db:
        uom = UnitOfMeasure(id=_u(), uom_code=_code("KG2"), uom_name="kilogram")
        db.add(uom)
        db.flush()
        cat = _category(db)
        product = _product(db, uom, cat)
        line = _sales_order_line(db, product, "2.50000")
        before = line.qty_ordered

        backfill_uom_decimal_places(db)
        db.refresh(line)

        assert line.qty_ordered == before


# =========================================================================== #
# canonical master ingest
# =========================================================================== #


def test_canonical_uom_accepts_decimal_places_and_defaults_to_zero():
    from app.schemas.canonical_masters import CanonicalUnitOfMeasure

    with_value = CanonicalUnitOfMeasure(
        source_ref=_code("R1"), code=_code("KGC"), name="Kilogram", decimal_places=3,
    )
    assert with_value.decimal_places == 3

    without_value = CanonicalUnitOfMeasure(
        source_ref=_code("R2"), code=_code("EAC"), name="Each",
    )
    assert without_value.decimal_places == 0


@pytest.fixture()
def ingest_db():
    """Real-engine, rolled-back transaction - matches tests/test_master_ingest.py, whose
    own per-record SAVEPOINT isolation this service needs to exercise for real."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_ingest_carries_decimal_places_onto_the_created_row(ingest_db):
    from sqlalchemy import text

    from app.services.master_ingest_service import MasterIngestService

    svc = MasterIngestService(ingest_db, integration_id=None)
    # units_of_measure.uom_code is varchar(20) on the live (prod-copy) schema this fixture
    # runs against - stay short, unlike the blank-schema tests above.
    code = f"ZZTU{uuid.uuid4().hex[:12]}"
    result = svc.ingest(
        "units_of_measure",
        [{"source_ref": _code("DK"), "code": code, "name": "Kilogram", "decimal_places": 3}],
    )
    assert result.created == 1, getattr(result, "records", result)
    assert (
        ingest_db.execute(
            text("SELECT decimal_places FROM units_of_measure WHERE uom_code = :c"), {"c": code}
        ).scalar()
        == 3
    )


def test_ingest_without_decimal_places_defaults_to_zero(ingest_db):
    from sqlalchemy import text

    from app.services.master_ingest_service import MasterIngestService

    svc = MasterIngestService(ingest_db, integration_id=None)
    code = f"ZZTU{uuid.uuid4().hex[:12]}"
    result = svc.ingest(
        "units_of_measure",
        [{"source_ref": _code("DK"), "code": code, "name": "Each"}],
    )
    assert result.created == 1, getattr(result, "records", result)
    assert (
        ingest_db.execute(
            text("SELECT decimal_places FROM units_of_measure WHERE uom_code = :c"), {"c": code}
        ).scalar()
        == 0
    )
