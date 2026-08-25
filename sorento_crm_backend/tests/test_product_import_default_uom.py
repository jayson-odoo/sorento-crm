"""A product-list row that states no unit takes the DEFAULT - on an existing product too.

The rule used to be split: a new product got the default, while an existing one kept
whatever unit it already had unless the file carried a UOM column. That is why 11,415
products are still stamped `L` from an older fallback and no amount of re-importing the
stock item list could correct them: the file has no UOM column at all, so the import
declined to touch the column on every one of them.

So the rule is now one rule, for every row:

  * the row states a unit -> that unit wins, existing product or new;
  * the row states none  -> the configured default unit (`system_settings.default_uom_id`,
    falling back to the built-in `EA`), existing product or new.

And a row whose unit actually MOVED says so in its own outcome, naming the unit it left and
the one it landed on: "9,000 products updated" would otherwise bury the only change the
operator ran the import to make.

Postgres only, blank scratch schema, everything this file needs seeded by it.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import Product, UnitOfMeasure
from app.models.user import SystemSetting
from app.services import product_service as product_service_mod
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session

USER_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """Supplier linking and embedding publishing are irrelevant here and enqueue RQ jobs."""
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_bulk_publish_product_embedding_events",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_resolve_default_supplier_for_new_product",
        lambda self: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_default_standard_lead_time_days",
        lambda self: None,
    )


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uom(db, code: str, name: str) -> UnitOfMeasure:
    row = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=code, uom_name=name)
    db.add(row)
    db.commit()
    return row


def _default_setting(db, uom_id: str | None) -> None:
    settings = SystemSetting(id=str(uuid.uuid4()), name="ZZTUOMIMP Co", default_uom_id=uom_id)
    db.add(settings)
    db.commit()


def _row(code: str, **over):
    row = {
        "Item Code": code,
        "Description": f"desc {code}",
        "Item Group": "SRT-FT",
        "Item Brand": "SORENTO",
        "Price": "10",
        "Is Active": "T",
    }
    row.update(over)
    return row


def _existing_product(db, code: str, uom: UnitOfMeasure) -> Product:
    from app.models.product import ProductCategory

    category = ProductCategory(
        id=str(uuid.uuid4()), category_code="SRT-FT", category_name="SRT-FT"
    )
    db.add(category)
    db.commit()
    product = Product(
        id=str(uuid.uuid4()), product_code=code, product_name=code,
        category_id=category.id, base_uom_id=uom.id, list_price=0,
    )
    db.add(product)
    db.commit()
    return product


class _Recorder:
    """A stand-in for `ImportOutcome` that keeps what it was told.

    The real recorder throws the per-row detail away when `persist=False` (which is what
    `bulk_import_products` builds for itself), and the message is exactly what this test is
    about - so it is captured here rather than asserted through a database round trip that
    would say nothing more.
    """

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def _record(self, outcome: str, **kw) -> None:
        self.entries.append({"outcome": outcome, **kw})

    def success(self, **kw):
        self._record("created", **kw)

    def updated(self, **kw):
        self._record("updated", **kw)

    def unchanged(self, **kw):
        self._record("unchanged", **kw)

    def skip(self, **kw):
        self._record("skipped", **kw)

    def fail(self, **kw):
        self._record("failed", **kw)

    def messages(self) -> str:
        return " | ".join(str(e.get("message") or "") for e in self.entries)

    def codes(self) -> list[str]:
        return [str(e.get("code") or "") for e in self.entries]


def _uom_of(db, code: str) -> str:
    return (
        db.query(UnitOfMeasure)
        .join(Product, Product.base_uom_id == UnitOfMeasure.id)
        .filter(Product.product_code == code)
        .one()
        .uom_code
    )


def test_a_file_with_no_uom_column_repoints_an_existing_product_to_the_default(db):
    """The 11,415 rows. The file has no UOM column, and that used to mean "leave it" - so
    the wrong unit was unfixable by the only tool the operator has."""
    litre = _uom(db, "L", "Litre")
    each = _uom(db, "EA", "Each")
    _default_setting(db, each.id)
    _existing_product(db, "P1", litre)

    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID)

    assert result["errors"] == []
    assert result["updated"] == 1
    assert _uom_of(db, "P1") == "EA"


def test_the_row_that_moved_names_the_unit_it_left_and_the_one_it_landed_on(db):
    """"9,000 products updated" buries the only change the operator ran the import for, so
    the row carries its own code AND says which unit it left."""
    litre = _uom(db, "L", "Litre")
    each = _uom(db, "EA", "Each")
    _default_setting(db, each.id)
    _existing_product(db, "P1", litre)
    recorder = _Recorder()

    ProductService(db).bulk_import_products([_row("P1")], USER_ID, outcome=recorder)

    assert "uom_defaulted" in recorder.codes(), recorder.codes()
    message = recorder.messages()
    assert "L" in message and "EA" in message, message
    assert "P1" in message, message


def test_a_uom_cell_still_wins_over_the_default(db):
    """The file is the record of what the unit IS when it says so at all."""
    litre = _uom(db, "L", "Litre")
    each = _uom(db, "EA", "Each")
    _default_setting(db, each.id)
    _existing_product(db, "P1", litre)

    result = ProductService(db).bulk_import_products([_row("P1", UOM="CTN")], USER_ID)

    assert result["errors"] == []
    assert _uom_of(db, "P1") == "CTN"


def test_with_no_setting_the_default_is_still_ea(db):
    """The built-in fallback is unchanged: `EA`, created if the database has none. What
    changed is only WHICH rows the default is applied to, not what it resolves to."""
    litre = _uom(db, "L", "Litre")
    _default_setting(db, None)
    _existing_product(db, "P1", litre)

    result = ProductService(db).bulk_import_products([_row("P1"), _row("P2")], USER_ID)

    assert result["errors"] == []
    assert _uom_of(db, "P1") == "EA"
    assert _uom_of(db, "P2") == "EA"


def test_a_new_product_takes_the_configured_default(db):
    ctn = _uom(db, "CTN", "Carton")
    _default_setting(db, ctn.id)

    result = ProductService(db).bulk_import_products([_row("P-NEW")], USER_ID)

    assert result["errors"] == []
    assert result["created"] == 1
    assert _uom_of(db, "P-NEW") == "CTN"


def test_a_product_already_on_the_default_is_not_reported_as_having_moved(db):
    """It is still an updated row - the import rewrote its name and price - but the unit
    did not move, so the outcome must not claim it did."""
    each = _uom(db, "EA", "Each")
    _default_setting(db, each.id)
    _existing_product(db, "P1", each)
    recorder = _Recorder()

    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID, outcome=recorder)

    assert result["updated"] == 1
    assert "uom_defaulted" not in recorder.codes(), recorder.codes()
