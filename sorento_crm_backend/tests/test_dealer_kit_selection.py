"""Golden set for the Selection spine (AC-S1 - AC-S6).

Written BEFORE the implementation.

A Selection is what the user chose. Everything downstream - the room, the
summary, the quote - hangs off it, which is why it holds product ids and
quantities and NOTHING price-shaped. Prices are resolved for whoever is reading,
at read time, exactly as tiles are (AC-G1). A price stored on a line is a price
that is wrong the moment the price list changes, and nobody notices until a
customer holds a quote nobody can honour.

The owner is either a CRM user or a contact, never both and never neither, and
that is a CHECK constraint rather than a convention. A Selection with two owners
is a Selection two people can edit and one of them is wrong; a Selection with no
owner is unreachable data.

The case worth reading twice is a discontinued product. Collection resolution
drops those before they ever become tiles - correct there, because nobody chose
them. Here somebody DID choose it, so dropping the line silently would edit a
person's basket behind their back. It stays, flagged.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.base import company_scope
from app.services.dealer_kit.viewer import ViewerContext
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
SCOPE = frozenset({SORENTO})

STAFF = ViewerContext(is_staff=True, show_invoice_price=True)
CONSUMER = ViewerContext(is_staff=False, show_invoice_price=True)


def _product(db, **overrides):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTS")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        invoice_price=Decimal("70.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    fields.update(overrides)
    product = Product(**fields)
    db.add(product)
    db.flush()
    return product


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"6019{unique_code('')[-7:]}",
        name=f"ZZT contact {unique_code('c')}",
    )
    db.add(contact)
    db.flush()
    return contact


def _user_id(db) -> str:
    from app.models.user import User

    user = db.query(User).first()
    assert user is not None, "the dev database always has users"
    return user.id


# --- AC-S1: exactly one owner, enforced by the database ----------------------


def test_a_selection_owned_by_a_user_is_valid():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        db.flush()

        assert selection.user_id is not None
        assert selection.contact_id is None


def test_a_selection_owned_by_a_contact_is_valid():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        contact = _contact(db)
        selection = selection_service.create_selection(db, contact_id=contact.id)
        db.flush()

        assert selection.contact_id == contact.id
        assert selection.user_id is None


def test_a_selection_with_two_owners_is_refused_by_the_database():
    from app.models.dealer_kit import Selection

    with pg_session() as db, company_scope(db, SCOPE):
        contact = _contact(db)
        # Straight to the model, bypassing the service, because the guarantee
        # under test is the CHECK constraint - a service-level validation would
        # be bypassed by the next caller who writes their own insert.
        db.add(Selection(user_id=_user_id(db), contact_id=contact.id, company_id=SORENTO))
        with pytest.raises(IntegrityError):
            db.flush()


def test_a_selection_with_no_owner_is_refused_by_the_database():
    from app.models.dealer_kit import Selection

    with pg_session() as db, company_scope(db, SCOPE):
        db.add(Selection(company_id=SORENTO))
        with pytest.raises(IntegrityError):
            db.flush()


# --- AC-S2: lines carry a quantity and never a price -------------------------


def test_a_line_holds_a_product_and_a_quantity_and_no_price():
    from app.models.dealer_kit import SelectionLine

    columns = {column.name for column in SelectionLine.__table__.columns}
    assert "product_id" in columns
    assert "quantity" in columns
    # Any of these would be a price frozen at pick time - the exact bug the
    # viewer-resolved model exists to prevent.
    assert not columns & {"price", "unit_price", "list_price", "invoice_price", "total"}


def test_adding_the_same_product_twice_increases_the_quantity():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(db)

        selection_service.add_line(db, selection, product.id, quantity=2)
        selection_service.add_line(db, selection, product.id, quantity=3)
        db.flush()

        lines = selection_service.list_lines(db, selection)
        assert len(lines) == 1
        assert lines[0].quantity == 5


def test_setting_a_quantity_to_zero_removes_the_line():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(db)
        selection_service.add_line(db, selection, product.id, quantity=2)
        db.flush()

        selection_service.set_quantity(db, selection, product.id, quantity=0)
        db.flush()

        assert selection_service.list_lines(db, selection) == []


# --- AC-S5: prices resolve for whoever is reading ----------------------------


def test_one_selection_reads_differently_for_staff_and_a_consumer():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(db)
        selection_service.add_line(db, selection, product.id, quantity=2)
        db.flush()

        staff_view = selection_service.resolve_selection(db, selection, STAFF)
        consumer_view = selection_service.resolve_selection(db, selection, CONSUMER)

        assert staff_view["lines"][0]["invoice_price"] is not None
        # Absent, not hidden. A field that is not in the payload cannot leak.
        assert consumer_view["lines"][0]["invoice_price"] is None
        assert staff_view["lines"][0]["price"] == consumer_view["lines"][0]["price"]


def test_the_total_counts_quantity_and_skips_unavailable_lines():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        good = _product(db, list_price=Decimal("100.00"))
        gone = _product(db, list_price=Decimal("999.00"))
        selection_service.add_line(db, selection, good.id, quantity=3)
        selection_service.add_line(db, selection, gone.id, quantity=1)
        db.flush()

        gone.is_discontinued = True
        db.flush()

        resolved = selection_service.resolve_selection(db, selection, CONSUMER)

        # A total that included something nobody can buy is a promise we cannot
        # keep; the line is still listed, it just does not count.
        assert resolved["total"] == "300.00"


# --- AC-S6: a discontinued choice is flagged, never silently dropped ---------


def test_a_discontinued_product_stays_on_the_selection_and_is_flagged():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(db)
        selection_service.add_line(db, selection, product.id, quantity=1)
        db.flush()

        product.is_discontinued = True
        db.flush()

        resolved = selection_service.resolve_selection(db, selection, CONSUMER)

        assert len(resolved["lines"]) == 1
        assert resolved["lines"][0]["is_available"] is False
        assert resolved["lines"][0]["product_name"]


def test_an_inactive_product_is_also_flagged_rather_than_dropped():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(db)
        selection_service.add_line(db, selection, product.id, quantity=1)
        db.flush()

        product.is_active = False
        db.flush()

        resolved = selection_service.resolve_selection(db, selection, CONSUMER)
        assert resolved["lines"][0]["is_available"] is False


def test_lines_carry_millimetre_dimensions_for_the_designer():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(
            db,
            dimensions_length=Decimal("1200"),
            dimensions_width=Decimal("600"),
            dimensions_height=Decimal("850"),
        )
        selection_service.add_line(db, selection, product.id, quantity=1)
        db.flush()

        line = selection_service.resolve_selection(db, selection, CONSUMER)["lines"][0]

        # Numbers, not the display string - the 3D view multiplies these.
        assert line["dimensions_mm"] == {"length": 1200.0, "width": 600.0, "height": 850.0}


def test_a_product_without_dimensions_reports_none_rather_than_zero():
    from app.services.dealer_kit import selection_service

    with pg_session() as db, company_scope(db, SCOPE):
        selection = selection_service.create_selection(db, user_id=_user_id(db))
        product = _product(db)
        selection_service.add_line(db, selection, product.id, quantity=1)
        db.flush()

        line = selection_service.resolve_selection(db, selection, CONSUMER)["lines"][0]

        # Zero would render as a flat box that looks deliberate. None makes the
        # designer say "estimated" instead of lying at 1:1 scale.
        assert line["dimensions_mm"] is None
