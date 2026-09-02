"""457_ptag_line_xco_repair - a line pointing at the OTHER company's product
row gets repointed at the sibling row with the same ``product_code`` in its
own request's company. A line with no such sibling is left alone.

Driven through `upgrade()`/`downgrade()` against the real database inside a
rolled-back transaction, exactly as `test_migration_450_spec_rules_backfill.py`
and `test_migration_454_tag_template_versions.py` do and for the same reason:
the repair is raw SQL against `price_tag_request_lines` / `products` /
`price_tag_requests`, which does not resolve through `blank_session`'s
schema-translate map, so a scratch copy would prove nothing about the
cross-company rows this migration exists to fix.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.access import RespondContact
from app.models.company import Company
from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import pg_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "457_ptag_line_xco_repair.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_457", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _company(db) -> Company:
    stem = unique_code("XCO")
    company = Company(id=str(uuid.uuid4()), name=f"ZZT {stem}", code=stem[:20])
    db.add(company)
    db.flush()
    return company


def _product(db, *, company_id: str, code: str, category, brand, uom) -> Product:
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=100,
        is_active=True,
        company_id=company_id,
    )
    db.add(product)
    db.flush()
    return product


@pytest.fixture
def world(db):
    """Two companies, both cloning the same product code, plus one code that
    exists ONLY in company B (the unfixable case)."""
    company_a = _company(db)
    company_b = _company(db)

    stem = unique_code("XCOCAT")
    category = ProductCategory(id=str(uuid.uuid4()), category_code=stem, category_name=stem, company_id=company_a.id)
    brand = Brand(id=str(uuid.uuid4()), brand_code=stem[:50], brand_name=stem, company_id=company_a.id)
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Each", company_id=company_a.id)
    db.add_all([category, brand, uom])
    db.flush()

    shared_code = unique_code("SHARED")
    product_a = _product(db, company_id=company_a.id, code=shared_code, category=category, brand=brand, uom=uom)
    product_b = _product(db, company_id=company_b.id, code=shared_code, category=category, brand=brand, uom=uom)

    b_only_code = unique_code("BONLY")
    product_b_only = _product(db, company_id=company_b.id, code=b_only_code, category=category, brand=brand, uom=uom)

    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("Contact"))
    db.add(contact)
    db.flush()

    request = PriceTagRequest(
        id=str(uuid.uuid4()),
        contact_id=contact.id,
        company_id=company_a.id,
        doc_number=unique_code("PT"),
        status="new",
    )
    db.add(request)
    db.flush()

    return {
        "company_a": company_a,
        "company_b": company_b,
        "product_a": product_a,
        "product_b": product_b,
        "product_b_only": product_b_only,
        "request": request,
    }


def _line(db, request_id: str, product_id: str) -> PriceTagRequestLine:
    line = PriceTagRequestLine(
        id=str(uuid.uuid4()),
        request_id=request_id,
        line_type="product",
        product_id=product_id,
    )
    db.add(line)
    db.flush()
    return line


def test_a_line_pointing_at_the_other_companys_product_is_repointed(db, world):
    """The core bug: a request in company A holding a line whose product_id is
    company B's row for the SAME product_code gets repointed at company A's
    own row."""
    mismatched = _line(db, world["request"].id, world["product_b"].id)

    _run(db)

    db.refresh(mismatched)
    assert mismatched.product_id == world["product_a"].id


def test_a_line_already_pointing_at_its_own_company_is_untouched(db, world):
    correct = _line(db, world["request"].id, world["product_a"].id)

    _run(db)

    db.refresh(correct)
    assert correct.product_id == world["product_a"].id


def test_a_line_with_no_same_code_sibling_in_its_company_is_left_alone(db, world):
    """No product with this code exists in the request's own company - there is
    nothing to repoint it to, and the migration must not delete the line."""
    unfixable = _line(db, world["request"].id, world["product_b_only"].id)

    _run(db)

    db.refresh(unfixable)
    assert unfixable.product_id == world["product_b_only"].id


def test_upgrade_prints_a_repaired_and_unfixable_count(db, world, capsys):
    _line(db, world["request"].id, world["product_b"].id)  # repairable
    _line(db, world["request"].id, world["product_b_only"].id)  # not repairable

    _run(db)

    out = capsys.readouterr().out
    assert "457_ptag_line_xco_repair" in out
    assert "1 repointed" in out
    assert "1 left unrepaired" in out


def test_running_upgrade_a_second_time_is_a_no_op(db, world):
    """Replay-safe by construction: once a line is repointed it no longer
    matches the WHERE clause, so a second run (e.g. against a database this
    already ran against) changes nothing and does not error."""
    mismatched = _line(db, world["request"].id, world["product_b"].id)
    unfixable = _line(db, world["request"].id, world["product_b_only"].id)

    _run(db)
    _run(db)  # replay - must not raise

    db.refresh(mismatched)
    db.refresh(unfixable)
    assert mismatched.product_id == world["product_a"].id
    assert unfixable.product_id == world["product_b_only"].id


def test_downgrade_is_a_no_op(db, world):
    """There is no record of which company a line used to point at, so the
    downgrade does not (and cannot) reverse the repair."""
    mismatched = _line(db, world["request"].id, world["product_b"].id)

    _run(db)
    _run(db, "downgrade")  # must not raise, must not change anything

    db.refresh(mismatched)
    assert mismatched.product_id == world["product_a"].id
