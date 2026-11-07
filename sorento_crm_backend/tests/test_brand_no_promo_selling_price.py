"""CABANA-NO-SELLING-PRICE: a brand whose promotions carry no selling price.

Owner, 2 Nov 2026: Cabana products have no selling price; the n8n flyer reader
invented one. `Brand.no_promo_selling_price` marks such a brand. Writers drop or
refuse the selling price (and the discount derived from it) on its promotion
lines, and readers never show one, so flipping the flag on another brand hides
its old values without a data change.

UAC: documentation/plans/master-data/brand-no-selling-price-02nov-acceptance-criteria.md
Every row is created inside ``blank_session()``; nothing touches a shared DB.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.services.dealer_kit.viewer import ViewerContext
from tests._pg_fixture import blank_session, unique_code

DEALER = ViewerContext(access_codes=frozenset({"dealer"}))


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _brand(db, *, flagged: bool, code: str | None = None):
    from app.models.product import Brand

    brand = Brand(
        id=str(uuid.uuid4()),
        brand_code=code or unique_code("BR")[:40],
        brand_name=unique_code("Brand"),
        no_promo_selling_price=flagged,
    )
    db.add(brand)
    db.flush()
    return brand


def _product(db, brand, list_price=Decimal("1000.00")):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("c")[:20],
        category_name=unique_code("cat"),
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_name=unique_code("uom"), uom_code=unique_code("u")[:10])
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("SKU"),
        product_name="Test product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=list_price,
        brand_id=brand.id if brand is not None else None,
    )
    db.add(product)
    db.flush()
    return product


def _promotion(db):
    from app.models.marketing import Promotion, PromotionGroup

    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=unique_code("promo"),
        is_active=True,
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        access_levels=["dealer"],
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name=unique_code("grp"))
    db.add(group)
    db.flush()
    return promotion, group


def _line(db, promotion, group, product, price, discount_amount=None, discount_percent=None):
    from app.models.marketing import PromotionProduct

    row = PromotionProduct(
        id=str(uuid.uuid4()),
        promotion_id=promotion.id,
        promotion_group_id=group.id,
        product_id=product.id,
        promo_selling_price=price,
        discount_amount=discount_amount,
        discount_percent=discount_percent,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# AC-1: the n8n external promotions API drops the price on a flagged brand
# ---------------------------------------------------------------------------


def _external_payload(lines: list[dict]):
    from app.schemas.external.marketing import PromotionRequest

    return PromotionRequest.model_validate(
        {
            "description": unique_code("FLYER") + ".pdf",
            "promotions": {"is_active": True},
            "promotion_products": lines,
        }
    )


def test_external_api_drops_selling_price_and_discount_for_flagged_brand(db):
    from app.api.v1.external.promotions import create_promotion
    from app.models.marketing import PromotionProduct

    flagged = _product(db, _brand(db, flagged=True), Decimal("12.50"))
    normal = _product(db, _brand(db, flagged=False), Decimal("1000.00"))

    result = create_promotion(
        payload=_external_payload(
            [
                {"product_code": flagged.product_code, "selling_price": 430, "dealer_discount": 0.3},
                {"product_code": normal.product_code, "selling_price": 800},
            ]
        ),
        current_user={"id": str(uuid.uuid4())},
        db=db,
    )

    rows = {
        r.product_id: r
        for r in db.query(PromotionProduct).filter(PromotionProduct.promotion_id == result.promotion.id)
    }
    cab = rows[flagged.id]
    assert cab.promo_selling_price is None
    assert cab.discount_amount is None
    assert cab.discount_percent is None
    # The line itself and the dealer discount survive: only the price is invented.
    assert cab.dealer_discount_percent is not None

    other = rows[normal.id]
    assert other.promo_selling_price == Decimal("800.00")
    assert other.discount_amount == Decimal("200.00")


def test_external_api_drops_explicit_discount_for_flagged_brand(db):
    from app.api.v1.external.promotions import create_promotion
    from app.models.marketing import PromotionProduct

    flagged = _product(db, _brand(db, flagged=True))
    result = create_promotion(
        payload=_external_payload(
            [{"product_code": flagged.product_code, "discount_percent": 15, "discount_amount": 150}]
        ),
        current_user={"id": str(uuid.uuid4())},
        db=db,
    )
    row = db.query(PromotionProduct).filter(PromotionProduct.promotion_id == result.promotion.id).one()
    assert row.discount_percent is None
    assert row.discount_amount is None


# ---------------------------------------------------------------------------
# AC-2: the promotion editor refuses a typed price on a flagged brand
# ---------------------------------------------------------------------------


def test_editor_add_line_with_price_on_flagged_brand_is_refused(db):
    from app.schemas.marketing import PromotionProductCreate
    from app.services.error_handler import AppException
    from app.services.marketing_service import PromotionProductService

    brand = _brand(db, flagged=True)
    product = _product(db, brand)
    promotion, group = _promotion(db)

    with pytest.raises(AppException) as exc:
        PromotionProductService(db).create_promotion_product(
            PromotionProductCreate(
                promotion_id=promotion.id,
                product_id=product.id,
                promotion_group_id=str(group.id),
                promo_selling_price=Decimal("430"),
            )
        )
    assert exc.value.status_code == 400
    assert brand.brand_name in exc.value.message


def test_editor_add_line_without_price_on_flagged_brand_is_allowed(db):
    from app.schemas.marketing import PromotionProductCreate
    from app.services.marketing_service import PromotionProductService

    product = _product(db, _brand(db, flagged=True))
    promotion, group = _promotion(db)

    row = PromotionProductService(db).create_promotion_product(
        PromotionProductCreate(
            promotion_id=promotion.id,
            product_id=product.id,
            promotion_group_id=str(group.id),
        )
    )
    assert row.promo_selling_price is None


def test_editor_update_price_on_flagged_brand_is_refused_but_clearing_is_allowed(db):
    from app.schemas.marketing import PromotionProductUpdate
    from app.services.error_handler import AppException
    from app.services.marketing_service import PromotionProductService

    product = _product(db, _brand(db, flagged=True))
    promotion, group = _promotion(db)
    line = _line(db, promotion, group, product, Decimal("430"), Decimal("-417.5"), Decimal("-999.99"))

    service = PromotionProductService(db)
    with pytest.raises(AppException):
        service.update_promotion_product(
            promotion.id, line.id, PromotionProductUpdate(promo_selling_price=Decimal("430"))
        )

    cleared = service.update_promotion_product(
        promotion.id, line.id, PromotionProductUpdate(promo_selling_price=None)
    )
    assert cleared.promo_selling_price is None
    # Clearing the price also clears the discount derived from it.
    assert cleared.discount_amount is None
    assert cleared.discount_percent is None


def test_editor_price_on_normal_brand_still_saves(db):
    from app.schemas.marketing import PromotionProductCreate
    from app.services.marketing_service import PromotionProductService

    product = _product(db, _brand(db, flagged=False))
    promotion, group = _promotion(db)
    row = PromotionProductService(db).create_promotion_product(
        PromotionProductCreate(
            promotion_id=promotion.id,
            product_id=product.id,
            promotion_group_id=str(group.id),
            promo_selling_price=Decimal("800"),
        )
    )
    assert row.promo_selling_price == Decimal("800.00")


# ---------------------------------------------------------------------------
# AC-3: readers never show a selling price for a flagged brand
# ---------------------------------------------------------------------------


def test_price_tag_falls_back_to_list_price_for_flagged_brand(db):
    from app.services.dealer_kit.pricing import resolve_prices

    flagged = _product(db, _brand(db, flagged=True), Decimal("1260.00"))
    normal = _product(db, _brand(db, flagged=False), Decimal("1260.00"))
    promotion, group = _promotion(db)
    _line(db, promotion, group, flagged, Decimal("599.00"))
    _line(db, promotion, group, normal, Decimal("599.00"))

    views = resolve_prices(db, [flagged, normal], DEALER, promotion.id)

    assert views[flagged.id].offer_price is None
    assert views[flagged.id].list_price == Decimal("1260.00")
    assert views[normal.id].offer_price == Decimal("599.00")


def test_api_response_masks_selling_price_for_flagged_brand(db):
    from app.models.marketing import PromotionProduct
    from app.schemas.marketing import PromotionProductResponse

    flagged = _product(db, _brand(db, flagged=True))
    normal = _product(db, _brand(db, flagged=False))
    promotion, group = _promotion(db)
    a = _line(db, promotion, group, flagged, Decimal("430"), Decimal("570"), Decimal("57"))
    b = _line(db, promotion, group, normal, Decimal("800"), Decimal("200"), Decimal("20"))
    db.expire_all()

    ra = PromotionProductResponse.model_validate(db.get(PromotionProduct, a.id))
    rb = PromotionProductResponse.model_validate(db.get(PromotionProduct, b.id))

    assert (ra.promotion_price, ra.discount_amount, ra.discount_percent) == (None, None, None)
    assert ra.no_selling_price is True
    assert rb.no_selling_price is False
    assert rb.promotion_price == Decimal("800.00")
    assert rb.discount_percent == Decimal("20.00")


def test_flag_reaches_brand_listing_dict(db):
    """The brand list is a manual dict builder: a column missing there never reaches the FE."""
    from app.services.product_service import BrandService

    brand = _brand(db, flagged=True)
    rows = BrandService(db).list_brands(page=1, limit=50, query=brand.brand_code)["data"]
    assert [r["no_promo_selling_price"] for r in rows if r["id"] == brand.id] == [True]


# ---------------------------------------------------------------------------
# AC-4: the cleanup migration clears flagged-brand lines, reversibly
# ---------------------------------------------------------------------------

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "bnsp_0001_brand_no_selling_price.py"


def _migration():
    spec = importlib.util.spec_from_file_location("bnsp0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn_name: str):
    module = _migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, fn_name)()


def test_migration_clears_cabana_lines_and_downgrade_restores_them(db):
    # create_all built the post-migration column; rewind it so upgrade adds it.
    db.execute(text("ALTER TABLE brands DROP COLUMN no_promo_selling_price"))
    db.execute(text("DROP TABLE IF EXISTS promotion_products_selling_price_backup"))
    db.expire_all()

    def raw_brand(code):
        bid = str(uuid.uuid4())
        db.execute(
            text("INSERT INTO brands (id, brand_code, brand_name) VALUES (:id, :c, :c)"),
            {"id": bid, "c": code},
        )
        return bid

    def raw_product(brand_id):
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        category = ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code("c")[:20], category_name=unique_code("cat")
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_name=unique_code("uom"), uom_code=unique_code("u")[:10])
        db.add_all([category, uom])
        db.flush()
        pid = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, list_price, brand_id) "
                "VALUES (:id, :code, 'x', :cat, :uom, 12.50, :b)"
            ),
            {"id": pid, "code": unique_code("SKU"), "cat": category.id, "uom": uom.id, "b": brand_id},
        )
        return pid

    def raw_line(product_id, promotion_id, group_id):
        lid = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO promotion_products (id, promotion_id, promotion_group_id, product_id, "
                "promo_selling_price, discount_amount, discount_percent) "
                "VALUES (:id, :p, :g, :prod, 430, -417.50, -999.99)"
            ),
            {"id": lid, "p": promotion_id, "g": group_id, "prod": product_id},
        )
        return lid

    from app.models.marketing import Promotion, PromotionGroup

    promotion = Promotion(id=str(uuid.uuid4()), description=unique_code("promo"), is_active=True)
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name="g")
    db.add(group)
    db.flush()

    cabana_line = raw_line(raw_product(raw_brand("CABANA")), promotion.id, group.id)
    other_line = raw_line(raw_product(raw_brand(unique_code("OTH")[:40])), promotion.id, group.id)

    def values(line_id):
        return db.execute(
            text(
                "SELECT promo_selling_price, discount_amount, discount_percent "
                "FROM promotion_products WHERE id = :id"
            ),
            {"id": line_id},
        ).one()

    _run(db, "upgrade")

    assert db.execute(
        text("SELECT no_promo_selling_price FROM brands WHERE brand_code = 'CABANA'")
    ).scalar() is True
    assert tuple(values(cabana_line)) == (None, None, None)
    assert tuple(values(other_line)) == (Decimal("430.00"), Decimal("-417.50"), Decimal("-999.99"))

    # Re-running the data step is a no-op (idempotent), and keeps the original backup.
    _run(db, "upgrade_data")
    backed_up = db.execute(
        text("SELECT promo_selling_price FROM promotion_products_selling_price_backup WHERE id = :id"),
        {"id": cabana_line},
    ).scalar()
    assert backed_up == Decimal("430.00")

    _run(db, "downgrade")

    assert tuple(values(cabana_line)) == (Decimal("430.00"), Decimal("-417.50"), Decimal("-999.99"))
    cols = db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'brands' AND column_name = 'no_promo_selling_price' "
            "AND table_schema = current_schema()"
        )
    ).scalar()
    assert cols == 0


def test_promotion_detail_masks_flagged_lines_on_the_nested_path(db):
    """Promotion detail, n8n's reply and the list response models go through the wrap
    validator (from_attributes), not the custom model_validate dict path."""
    from app.models.marketing import PromotionProduct
    from app.schemas.marketing import PromotionResponse
    from app.services.marketing_service import PromotionService

    flagged_brand = _brand(db, flagged=True)
    promotion, group = _promotion(db)
    _line(db, promotion, group, _product(db, flagged_brand), Decimal("430"), Decimal("570"), Decimal("57"))
    _line(db, promotion, group, _product(db, _brand(db, flagged=False)), Decimal("800"), Decimal("200"), Decimal("20"))
    db.expire_all()

    loaded = PromotionService(db).get_promotion(promotion.id, include_products=True)
    for pp in loaded.products:  # what the route does before serialising
        pp.promotion_price = pp.promo_selling_price
    flagged_ids = {pp.id for pp in loaded.products if pp.product.brand_id == flagged_brand.id}

    response = PromotionResponse.model_validate(loaded)

    grouped = [x for g in response.promotion_groups for x in g.promotion_products]
    for collection in (response.products, grouped):
        assert len(collection) == 2
        for x in collection:
            if x.id in flagged_ids:
                assert (x.promotion_price, x.discount_amount, x.discount_percent) == (None, None, None)
                assert x.no_selling_price is True
            else:
                assert x.promotion_price == Decimal("800.00")
                assert x.no_selling_price is False
    # Masked on the response only: the stored row is untouched and nothing is dirty.
    assert not db.dirty
    db.expire_all()
    stored = {r.promo_selling_price for r in db.query(PromotionProduct).filter(PromotionProduct.promotion_id == promotion.id)}
    assert stored == {Decimal("430.00"), Decimal("800.00")}
