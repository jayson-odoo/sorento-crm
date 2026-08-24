"""D10: the link a PRODUCT SET fanned out is found, and cleaned up, when
membership changes.

`linked_via_set_id` (migration 412) is stamped on `product_attachments` and
`promotion_products` ONLY when `_resolve_codes` expanded a set code into its
members (`app/api/v1/external/product_attachments.py`,
`app/api/v1/external/promotions.py`). NULL means a person, or an exact product
code, made the link - and that must never be touched here.

Two different questions, two different answers:

- A MEMBER leaves a set that still exists (`_replace_members`, reached through
  `ProductSetService.update`): the links that member's fan-out created are no
  longer valid and are hard-deleted (`_detach_set_fanout_links`).
- The WHOLE SET is deleted (`ProductSetService.delete`): the documents it once
  linked must survive it - only their provenance goes, via the
  `ON DELETE SET NULL` foreign key. Nothing in this module deletes a link row
  on that path; the FK does the work.

UAC group D (D10). Plan: `documentation/plans/master-data/PLAN-product-sets.md`.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database import engine
from app.models.company import Company
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet
from app.models.resources import Attachment
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_set_service import ProductSetService

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def db() -> Session:
    """A session whose writes are DISCARDED, even when the code under test commits.

    Same shape as `tests/test_product_set_routes.py::db` - `join_transaction_mode
    ="create_savepoint"` is what makes a committing service safe to test against
    the shared database.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def world(db: Session):
    """A set with three members, and every shape of link `_replace_members`
    must tell apart: fanned-out (this set), fanned-out (a DIFFERENT set - not
    modelled here, covered by the "other members" case within this same set),
    and manual (NULL provenance)."""
    company = Company(id=str(uuid.uuid4()), name=_uid("co"), code=_uid("C")[:20])
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([company, category, uom])
    db.flush()

    def product(stem: str, price: str) -> Product:
        row = Product(
            id=str(uuid.uuid4()),
            product_code=_uid(stem),
            product_name=_uid(stem),
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal(price),
            company_id=company.id,
        )
        db.add(row)
        db.flush()
        return row

    pedestal = product("pedestal", "1180.00")
    cistern = product("cistern", "0.00")
    seat = product("seat", "85.00")

    def attachment(stem: str) -> Attachment:
        row = Attachment(
            id=str(uuid.uuid4()),
            original_filename=f"{stem}.pdf",
            stored_filename=f"{_uid(stem)}.pdf",
            file_path=f"/{_uid(stem)}.pdf",
            company_id=company.id,
        )
        db.add(row)
        db.flush()
        return row

    with company_scope(db, frozenset({str(company.id)})):
        created_set = ProductSetService(db).create(
            {
                "set_code": _uid("set"),
                "name": "S-trap assembly",
                "members": [
                    {"product_code": pedestal.product_code, "quantity": 1,
                     "contributes_to_price": True, "sort_order": 0},
                    {"product_code": cistern.product_code, "quantity": 1,
                     "contributes_to_price": False, "sort_order": 1},
                    {"product_code": seat.product_code, "quantity": 1,
                     "contributes_to_price": False, "sort_order": 2},
                ],
            },
            created_by=None,
        )
    product_set = db.query(ProductSet).filter(ProductSet.id == created_set.id).one()

    flyer = attachment("flyer")
    manual_doc = attachment("manual")

    # The flyer's fan-out: pedestal (stays a member) and cistern (about to be
    # removed). Both stamped with THIS set's id, exactly what a code-resolved
    # `/external/product-attachments` link would carry.
    fanned_pedestal_link = ProductAttachment(
        id=str(uuid.uuid4()), product_id=pedestal.id, attachment_id=flyer.id,
        linked_via_set_id=product_set.id, company_id=company.id,
    )
    fanned_cistern_link = ProductAttachment(
        id=str(uuid.uuid4()), product_id=cistern.id, attachment_id=flyer.id,
        linked_via_set_id=product_set.id, company_id=company.id,
    )
    # A person linked `manual_doc` to the SAME product (cistern) by hand. NULL
    # provenance - must survive the cistern being dropped from the set.
    manual_cistern_link = ProductAttachment(
        id=str(uuid.uuid4()), product_id=cistern.id, attachment_id=manual_doc.id,
        linked_via_set_id=None, company_id=company.id,
    )
    db.add_all([fanned_pedestal_link, fanned_cistern_link, manual_cistern_link])
    db.flush()

    promotion = Promotion(id=str(uuid.uuid4()), description=_uid("promo"), company_id=company.id)
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name="Default", company_id=company.id)
    db.add(group)
    db.flush()

    fanned_pedestal_promo = PromotionProduct(
        id=str(uuid.uuid4()), promotion_id=promotion.id, promotion_group_id=group.id,
        product_id=pedestal.id, linked_via_set_id=product_set.id, company_id=company.id,
    )
    fanned_cistern_promo = PromotionProduct(
        id=str(uuid.uuid4()), promotion_id=promotion.id, promotion_group_id=group.id,
        product_id=cistern.id, linked_via_set_id=product_set.id, company_id=company.id,
    )
    # A person picked `seat` into the promotion by hand - NULL provenance, must
    # survive too, even though it belongs to a member that STAYS in the set.
    manual_seat_promo = PromotionProduct(
        id=str(uuid.uuid4()), promotion_id=promotion.id, promotion_group_id=group.id,
        product_id=seat.id, linked_via_set_id=None, company_id=company.id,
    )
    db.add_all([fanned_pedestal_promo, fanned_cistern_promo, manual_seat_promo])
    db.flush()

    return {
        "company": company,
        "product_set": product_set,
        "pedestal": pedestal,
        "cistern": cistern,
        "seat": seat,
        "flyer": flyer,
        "manual_doc": manual_doc,
        "fanned_pedestal_link_id": fanned_pedestal_link.id,
        "fanned_cistern_link_id": fanned_cistern_link.id,
        "manual_cistern_link_id": manual_cistern_link.id,
        "promotion": promotion,
        "fanned_pedestal_promo_id": fanned_pedestal_promo.id,
        "fanned_cistern_promo_id": fanned_cistern_promo.id,
        "manual_seat_promo_id": manual_seat_promo.id,
    }


def _remove_cistern(db: Session, world) -> None:
    """Update the set to drop `cistern`, keeping `pedestal` and `seat`."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        ProductSetService(db).update(
            world["product_set"].id,
            {"members": [
                {"product_code": world["pedestal"].product_code, "quantity": 1,
                 "contributes_to_price": True, "sort_order": 0},
                {"product_code": world["seat"].product_code, "quantity": 1,
                 "contributes_to_price": False, "sort_order": 1},
            ]},
            updated_by=None,
        )


def _attachment_link_exists(db: Session, link_id) -> bool:
    return db.query(ProductAttachment).filter(ProductAttachment.id == link_id).first() is not None


def _promotion_link_exists(db: Session, link_id) -> bool:
    return db.query(PromotionProduct).filter(PromotionProduct.id == link_id).first() is not None


# ---------------------------------------------------------- removing a member


def test_removing_a_member_detaches_the_links_its_own_set_created(db: Session, world):
    """The core case: cistern's FANNED links (attachment + promotion), stamped
    with THIS set's id, are gone once cistern leaves the set."""
    _remove_cistern(db, world)

    assert not _attachment_link_exists(db, world["fanned_cistern_link_id"])
    assert not _promotion_link_exists(db, world["fanned_cistern_promo_id"])


def test_removing_a_member_leaves_manual_links_on_the_same_product_untouched(
    db: Session, world
):
    """NULL provenance is a person's own link. It must survive even though it
    names the SAME product (cistern) that just left the set."""
    _remove_cistern(db, world)

    assert _attachment_link_exists(db, world["manual_cistern_link_id"])


def test_removing_a_member_leaves_other_members_links_untouched(db: Session, world):
    """Pedestal STAYS a member - its own fanned links, from the SAME set and the
    SAME flyer, must not be swept up by the cistern's removal."""
    _remove_cistern(db, world)

    assert _attachment_link_exists(db, world["fanned_pedestal_link_id"])
    assert _promotion_link_exists(db, world["fanned_pedestal_promo_id"])


def test_removing_a_member_leaves_a_manual_link_on_a_staying_member_untouched(
    db: Session, world
):
    """Seat also stays a member, and its manually-picked promotion link (NULL
    provenance) is untouched regardless."""
    _remove_cistern(db, world)

    assert _promotion_link_exists(db, world["manual_seat_promo_id"])


def test_removing_a_member_with_no_fanned_out_links_is_a_no_op(db: Session, world):
    """A member that leaves with nothing fanned out for it must not raise, and
    must not touch any other row."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        # Seat has no fan-out (only a manual promotion link). Drop it too, on
        # top of cistern, in the SAME update.
        ProductSetService(db).update(
            world["product_set"].id,
            {"members": [
                {"product_code": world["pedestal"].product_code, "quantity": 1,
                 "contributes_to_price": True, "sort_order": 0},
            ]},
            updated_by=None,
        )

    # Seat's own manual promotion link survives (NULL provenance); nothing
    # blew up resolving a product with zero fanned links to detach.
    assert _promotion_link_exists(db, world["manual_seat_promo_id"])
    assert _attachment_link_exists(db, world["fanned_pedestal_link_id"])


# ------------------------------------------------------------ deleting a set


def test_deleting_a_set_does_not_orphan_its_fanned_out_links(db: Session, world):
    """The OTHER path: the whole set goes. The documents it once linked must
    survive it - `ON DELETE SET NULL` (migration 412), not a cleanup delete."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        ProductSetService(db).delete(world["product_set"].id)

    attachment_link = (
        db.query(ProductAttachment)
        .filter(ProductAttachment.id == world["fanned_pedestal_link_id"])
        .one()
    )
    promotion_link = (
        db.query(PromotionProduct)
        .filter(PromotionProduct.id == world["fanned_pedestal_promo_id"])
        .one()
    )
    assert attachment_link.linked_via_set_id is None
    assert promotion_link.linked_via_set_id is None
    # The row - and the document/promotion it names - is still there.
    assert attachment_link.product_id == world["pedestal"].id
    assert promotion_link.product_id == world["pedestal"].id
