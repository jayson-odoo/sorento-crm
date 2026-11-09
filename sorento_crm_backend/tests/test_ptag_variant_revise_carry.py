"""PRICETAG-UPGRADE-VARIANTS review fix round 1, items 1 and 2: a revise carries the line's
unticked variant members when it does not send them, replaces them when it does, and a carried id
whose product left the family since is dropped silently rather than blocking the revision.

Same revise path and seed helpers as `test_portal_price_tag_revise.py`. Postgres only.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.price_tag import PriceTagRequestLine
from app.models.product import Product
from app.services.portal_revision_service import PortalRevisionService

from tests._pg_fixture import blank_session
from tests.test_portal_price_tag_revise import _seed_product, _seed_token, _setup
from tests.test_portal_price_tag_revise import no_queue, no_respond  # noqa: F401  (autouse fixtures)


def _family(db, base_id: str, count: int = 2) -> list[str]:
    """`count` variants directly under the line's product."""
    ids = []
    for _ in range(count):
        child_id = _seed_product(db)
        db.get(Product, child_id).variant_of_id = base_id
        ids.append(child_id)
    db.flush()
    return ids


def _line(db, row) -> PriceTagRequestLine:
    return db.query(PriceTagRequestLine).filter_by(request_id=row.id).one()


def _revise(db, contact, row, product_id: str, **line_extra):
    PortalRevisionService(db).revise(
        _seed_token(contact), "price_tag_request", str(row.id),
        {"products": [{"product_id": product_id, "quantity": 2, **line_extra}]}, "Reason", 0,
    )
    db.expire_all()


def test_a_revise_without_the_field_keeps_the_unticked_members():
    with blank_session() as db:
        contact, product_id, row = _setup(db)
        a, _b = _family(db, product_id)
        _line(db, row).excluded_variant_ids = [a]
        db.commit()

        _revise(db, contact, row, product_id)

        assert _line(db, row).excluded_variant_ids == [a]


def test_a_revise_with_the_field_replaces_them():
    with blank_session() as db:
        contact, product_id, row = _setup(db)
        a, b = _family(db, product_id)
        _line(db, row).excluded_variant_ids = [a]
        db.commit()

        _revise(db, contact, row, product_id, excluded_variant_ids=[b])

        assert _line(db, row).excluded_variant_ids == [b]


def test_a_revise_with_an_empty_list_clears_them():
    with blank_session() as db:
        contact, product_id, row = _setup(db)
        a, _b = _family(db, product_id)
        _line(db, row).excluded_variant_ids = [a]
        db.commit()

        _revise(db, contact, row, product_id, excluded_variant_ids=[])

        assert _line(db, row).excluded_variant_ids == []


def test_a_carried_id_that_left_the_family_is_dropped_not_refused():
    with blank_session() as db:
        contact, product_id, row = _setup(db)
        a, b = _family(db, product_id)
        _line(db, row).excluded_variant_ids = [a, b]
        db.get(Product, a).variant_of_id = None  # re-parented out of the family since
        db.commit()

        _revise(db, contact, row, product_id)

        assert _line(db, row).excluded_variant_ids == [b]


def test_a_sent_id_outside_the_family_is_still_refused():
    with blank_session() as db:
        contact, product_id, row = _setup(db)
        a, _b = _family(db, product_id)
        db.get(Product, a).variant_of_id = None
        db.commit()

        with pytest.raises(Exception) as caught:
            _revise(db, contact, row, product_id, excluded_variant_ids=[a])
        assert "NOT_A_VARIANT" in repr(getattr(caught.value, "detail", None) or caught.value) or (
            getattr(caught.value, "code", None) == "NOT_A_VARIANT"
        )
