"""AC-17 (PRICETAG-ALA-CARTE): an empty Package is ala carte, not a warning.

UAC: `documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md`.

A guarded product line whose host has combos, saved with combo_id None, is the
salesperson's ala carte choice, so package_warning is None ("No package chosen"
is dropped). Kept: "No package defined" (guarded host with zero combos) and
"Missing: <code>" (a chosen combo with a fixed part removed).

Seed helpers are the ones the package-warning suite already uses, so the chain
(category, brand, uom, contact + segment grant, combo cover photo) is identical.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.price_tag_request_service import STATUS_NEW
from tests._pg_fixture import blank_session
from tests.test_price_tag_package_warning import (
    _combo,
    _contact,
    _line_warnings,
    _product,
    _submit,
)


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        yield session


def test_guarded_host_with_one_combo_saved_ala_carte_has_no_warning(db: Session):
    contact = _contact(db)
    cabinet = _product(db, "ZZTBF0001", class_label="Bathroom Furniture")
    mirror = _product(db, "ZZTMR0001")
    _combo(db, cabinet, "ZZT 2 in 1", [(mirror, None)])

    request = _submit(
        db,
        contact,
        [{"line_type": "product", "product_id": cabinet.id, "combo_id": None, "parts": []}],
    )
    assert request.status == STATUS_NEW
    assert _line_warnings(request) == [None]


def test_guarded_host_with_two_combos_saved_ala_carte_has_no_warning(db: Session):
    contact = _contact(db)
    cabinet = _product(db, "ZZTBF0002", class_label="Kitchen Sink")
    mirror = _product(db, "ZZTMR0002")
    top = _product(db, "ZZTTT0002")
    first = _combo(db, cabinet, "ZZT 3 in 1", [(mirror, None), (top, None)])
    # `_combo` seeds the host's primary photo, which is unique per product, so the
    # second combo is built inline and shares the first one's cover.
    second = ProductCombo(
        id=str(uuid.uuid4()),
        host_product_id=cabinet.id,
        name="ZZT 2 in 1",
        sort_order=1,
        description="ZZT description",
        image_attachment_id=first.image_attachment_id,
    )
    db.add(second)
    db.flush()
    db.add(
        ProductComboPart(
            id=str(uuid.uuid4()),
            combo_id=second.id,
            part_product_id=top.id,
            choice_group=None,
            sort_order=0,
        )
    )
    db.flush()

    request = _submit(db, contact, [{"line_type": "product", "product_id": cabinet.id}])
    assert _line_warnings(request) == [None]


def test_guarded_host_with_no_combos_still_warns_no_package_defined(db: Session):
    contact = _contact(db)
    bare = _product(db, "ZZTBF0003", class_label="Bathroom Furniture")

    request = _submit(db, contact, [{"line_type": "product", "product_id": bare.id}])
    assert _line_warnings(request) == ["No package defined"]


def test_chosen_combo_missing_a_fixed_part_still_warns_missing(db: Session):
    contact = _contact(db)
    cabinet = _product(db, "ZZTBF0004", class_label="Bathroom Furniture")
    mirror = _product(db, "ZZTMR0004")
    top = _product(db, "ZZTTT0004")
    combo = _combo(db, cabinet, "ZZT 3 in 1", [(mirror, None), (top, None)])

    request = _submit(
        db,
        contact,
        [
            {
                "line_type": "product",
                "product_id": cabinet.id,
                "combo_id": combo.id,
                "parts": [{"product_id": top.id}],
            }
        ],
    )
    assert _line_warnings(request) == [f"Missing: {mirror.product_code}"]
