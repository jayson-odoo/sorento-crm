"""AC-S2-4, AC-S2-5: a line's `parts` are only acceptable when its product
carries at least one `ProductCombo`. No combo, non-empty `parts` -> 422 naming
the line index, and nothing is left behind. A combo present -> unchanged
(regression).

See documentation/plans/dealer-kit/PLAN-price-tag-ai-extract-resolver.md (D5)
and price-tag-ai-extract-resolver-acceptance-criteria.md (S2).

Drives `PriceTagRequestService.create_request` / `.replace_lines` directly
(the `_add_line_parts` seam named in the plan), against a real Postgres
session. Seeding shape copied from `tests/test_price_tag_combos_security.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.price_tag import PriceTagRequest, PriceTagRequestLine, PriceTagRequestLinePart
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.error_handler import AppException
from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db, stem: str, *, company_id: str = SORENTO) -> Product:
    code = unique_code(stem)
    category = ProductCategory(
        id=_uid(), category_code=code[:50], category_name=f"ZZT cat {code}"
    )
    brand = Brand(id=_uid(), brand_code=code[:50], brand_name=f"ZZT {code}")
    uom = UnitOfMeasure(id=_uid(), uom_code=code[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=company_id,
        product_code=code,
        product_name=f"ZZT {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


def _combo(db, host: Product, name: str, parts: list[tuple[Product, str | None]]) -> ProductCombo:
    combo = ProductCombo(id=_uid(), host_product_id=host.id, name=name, sort_order=0)
    db.add(combo)
    db.flush()
    for index, (product, group) in enumerate(parts):
        db.add(
            ProductComboPart(
                id=_uid(),
                combo_id=combo.id,
                part_product_id=product.id,
                choice_group=group,
                sort_order=index,
            )
        )
    db.flush()
    return combo


def _line_with_part(product: Product, part_product: Product) -> dict:
    return {
        "line_type": "product",
        "product_id": product.id,
        "quantity": 1,
        "parts": [{"product_id": part_product.id}],
    }


# --------------------------------------------------------------------------- #
# AC-S2-4: create - a product with zero ProductCombo rows and non-empty parts.
# --------------------------------------------------------------------------- #
def test_create_request_with_parts_on_no_combo_product_returns_422(db):
    contact = _contact(db)
    cabinet = _product(db, "SRTNC001")  # no ProductCombo row for this product
    mirror = _product(db, "SRTNC002")

    savepoint = db.begin_nested()
    with pytest.raises(AppException) as exc:
        PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=SORENTO,
            data={
                "debtor_name": "ZZT Dealer",
                "lines": [_line_with_part(cabinet, mirror)],
            },
        )
    savepoint.rollback()

    assert exc.value.status_code == 422
    # AppException.detail is the wire dict ({"message", "detail", "code"}),
    # never the bare string - `detail=f"line:{index}"` lands in its own
    # "detail" key, the same shape every other AppException raise in this
    # service uses (see `_add_line_parts`'s sibling checks / `_part_uuid`).
    assert exc.value.detail["detail"] == "line:0"
    # The request is unchanged: nothing from the failed create survives.
    assert db.query(PriceTagRequest).count() == 0


# --------------------------------------------------------------------------- #
# AC-S2-4: replace - an existing draft gains a no-combo line with parts.
# --------------------------------------------------------------------------- #
def test_replace_lines_with_parts_on_no_combo_product_returns_422(db):
    contact = _contact(db)
    cabinet = _product(db, "SRTRC001")
    mirror = _product(db, "SRTRC002")

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={"debtor_name": "ZZT Dealer", "lines": []},
    )
    db.flush()

    savepoint = db.begin_nested()
    with pytest.raises(AppException) as exc:
        PriceTagRequestService.replace_lines(
            db, request, [_line_with_part(cabinet, mirror)]
        )
    savepoint.rollback()

    assert exc.value.status_code == 422
    # AppException.detail is the wire dict ({"message", "detail", "code"}),
    # never the bare string - `detail=f"line:{index}"` lands in its own
    # "detail" key, the same shape every other AppException raise in this
    # service uses (see `_add_line_parts`'s sibling checks / `_part_uuid`).
    assert exc.value.detail["detail"] == "line:0"
    # The draft's line set is unchanged (still empty, as before the replace).
    db.expire_all()
    assert (
        db.query(PriceTagRequestLine)
        .filter(PriceTagRequestLine.request_id == request.id)
        .count()
        == 0
    )


# --------------------------------------------------------------------------- #
# AC-S2-5 (regression): the same payload on a product WITH a combo is accepted.
# --------------------------------------------------------------------------- #
def test_create_request_with_parts_on_combo_product_is_accepted(db):
    contact = _contact(db)
    cabinet = _product(db, "SRTC001")
    mirror = _product(db, "SRTC002")
    _combo(db, cabinet, "regression combo", [(mirror, None)])

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [_line_with_part(cabinet, mirror)],
        },
    )
    db.flush()

    parts = (
        db.query(PriceTagRequestLinePart)
        .join(PriceTagRequestLine, PriceTagRequestLine.id == PriceTagRequestLinePart.line_id)
        .filter(PriceTagRequestLine.request_id == request.id)
        .all()
    )
    assert len(parts) == 1
    assert parts[0].product_id == mirror.id
