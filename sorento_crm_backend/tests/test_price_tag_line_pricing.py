"""`line_pricing` - one call answering what a LINE costs, for the form and the

CRM lines table (D2, D3, D4, S7).

UAC: AC-S7-1 to AC-S7-5. Written test-FIRST (PRINCIPLES.md Phase 2):
`app.services.dealer_kit.pricing.line_pricing` does not exist yet, so the
import below fails the WHOLE FILE at collection with one `ImportError` - the
same accepted pattern `test_price_tag_tag_render_data.py` uses for a slice
that has not landed.

Contract this file pins down (Plan D4's shape, made concrete because the
plan's prose left the exact call signature to the tester):

    line_pricing(db, lines: list[dict], viewer: ViewerContext) -> list[dict]

Each input line dict: ``{key, product_id, part_product_ids, candidate_product_ids,
promotion_id, manual_sell_price}`` - the last two optional. ``manual_sell_price``
is NOT part of either route's request body (the plan's two lookup routes never
send it - a line has no manual figure until it is saved), but the service
function accepts it as a plain dict key so `resolve_tags_live` (S9) can call the
SAME engine with a persisted line's `manual_sell_price` rather than
re-implementing the "manual wins" rule a second time.

Each output row: ``{key, list_price, promotion_options, auto_promotion_id,
sell_price, sell_price_basis, parts_at_list, candidates}`` per the plan's API
contract section.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.dealer_kit.pricing import line_pricing  # THE red import
from app.services.dealer_kit.viewer import ViewerContext

from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _staff_viewer() -> ViewerContext:
    return ViewerContext(is_staff=True, is_internal_copy=True)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _product(db, *, list_price="1599.00"):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("LP")
    category = ProductCategory(
        id=_uid(), category_code=stem, category_name=f"ZZT cat {stem}"
    )
    brand = Brand(id=_uid(), brand_code=stem[:50], brand_name=f"ZZT {stem}")
    uom = UnitOfMeasure(id=_uid(), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=stem,
        product_name=f"ZZT {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
        currency="MYR",
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _promotion(
    db,
    lines: list[tuple],
    *,
    is_active: bool = True,
    start=None,
    end=None,
    access_levels: list[str] | None = None,
    description: str | None = None,
):
    """``lines`` is a list of (product, promo_selling_price)."""
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(
        id=_uid(),
        description=description or unique_code("ZZT promo"),
        start_date=start if start is not None else date.today() - timedelta(days=1),
        end_date=end if end is not None else date.today() + timedelta(days=30),
        is_active=is_active,
        access_levels=access_levels or ["dealer", "end_user"],
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name="ZZT group", sort_order=0)
    db.add(group)
    db.flush()
    for product, price in lines:
        db.add(
            PromotionProduct(
                id=_uid(),
                promotion_id=promotion.id,
                promotion_group_id=str(group.id),
                product_id=product.id,
                promo_selling_price=Decimal(price),
                company_id=SORENTO,
            )
        )
    db.flush()
    return promotion


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


# --------------------------------------------------------------------------- AC-S7-1


def test_line_pricing_shape(db):
    parent = _product(db, list_price="1599.00")
    part = _product(db, list_price="199.00")
    # promo_a covers only the parent; its total (1299 + 199 list) is WORSE than
    # promo_b, which also covers the part.
    promo_a = _promotion(db, [(parent, "1299.00")], description="ZZT Promo A")
    promo_b = _promotion(
        db, [(parent, "1199.00"), (part, "149.00")], description="ZZT Promo B"
    )

    result = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": parent.id,
                "part_product_ids": [part.id],
                "candidate_product_ids": [],
                "promotion_id": None,
            }
        ],
        viewer=_staff_viewer(),
    )

    assert len(result) == 1
    row = result[0]
    assert row["key"] == "L1"
    assert row["list_price"] == Decimal("1798.00")
    option_ids = [option["id"] for option in row["promotion_options"]]
    assert option_ids == [promo_b.id, promo_a.id], "lowest total first"
    assert {"id", "description", "sell_price"} <= set(row["promotion_options"][0].keys())
    assert row["auto_promotion_id"] == promo_b.id
    assert row["sell_price"] == Decimal("1348.00")
    assert row["sell_price_basis"] == "promotion"
    assert row["parts_at_list"] == []
    assert row["candidates"] == []


# --------------------------------------------------------------------------- AC-S7-2


def test_options_only_active_covering_audience(db):
    parent = _product(db, list_price="500.00")
    candidate = _product(db, list_price="80.00")
    unrelated = _product(db, list_price="10.00")

    wrong_audience = _promotion(db, [(parent, "400.00")], access_levels=["dealer"])
    expired = _promotion(
        db, [(parent, "1.00")], end=date.today() - timedelta(days=1)
    )
    inactive = _promotion(db, [(parent, "1.00")], is_active=False)
    not_covering = _promotion(db, [(unrelated, "1.00")])
    covers_candidate_only = _promotion(db, [(candidate, "50.00")])

    row = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": parent.id,
                "part_product_ids": [],
                "candidate_product_ids": [candidate.id],
                "promotion_id": None,
            }
        ],
        viewer=ViewerContext(access_codes=frozenset({"end_user"})),
    )[0]

    ids = {option["id"] for option in row["promotion_options"]}
    assert wrong_audience.id not in ids
    assert expired.id not in ids
    assert inactive.id not in ids
    assert not_covering.id not in ids
    assert covers_candidate_only.id in ids, (
        "a promotion covering only a CANDIDATE still counts as covering the line"
    )


# --------------------------------------------------------------------------- AC-S7-3


def test_sell_price_sums_offer_else_list(db):
    parent = _product(db, list_price="1599.00")
    part_no_offer = _product(db, list_price="199.00")
    part_with_offer = _product(db, list_price="299.00")
    unresolved_candidate = _product(db, list_price="349.00")
    promo = _promotion(db, [(parent, "899.00"), (part_with_offer, "249.00")])

    row = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": parent.id,
                "part_product_ids": [part_no_offer.id, part_with_offer.id],
                "candidate_product_ids": [unresolved_candidate.id],
                "promotion_id": promo.id,
            }
        ],
        viewer=_staff_viewer(),
    )[0]

    assert row["sell_price"] == Decimal("1347.00"), "899 offer + 199 list + 249 offer"
    assert row["parts_at_list"] == [part_no_offer.id]


def test_manual_wins(db):
    parent = _product(db, list_price="1599.00")
    promo = _promotion(db, [(parent, "999.00")])

    row = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": parent.id,
                "part_product_ids": [],
                "candidate_product_ids": [],
                "promotion_id": promo.id,
                "manual_sell_price": "1200.00",
            }
        ],
        viewer=_staff_viewer(),
    )[0]

    assert row["sell_price"] == Decimal("1200.00")
    assert row["sell_price_basis"] == "manual"


# --------------------------------------------------------------------------- AC-S7-4


def test_basis_list_when_nothing_covers(db):
    parent = _product(db, list_price="899.00")

    row = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": parent.id,
                "part_product_ids": [],
                "candidate_product_ids": [],
                "promotion_id": None,
            }
        ],
        viewer=_staff_viewer(),
    )[0]

    assert row["promotion_options"] == []
    assert row["auto_promotion_id"] is None
    assert row["sell_price"] == row["list_price"] == Decimal("899.00")
    assert row["sell_price_basis"] == "list"


def test_auto_pick_is_lowest_total(db):
    parent = _product(db, list_price="1599.00")
    cheaper = _promotion(db, [(parent, "999.00")], description="ZZT Cheaper")
    pricier = _promotion(db, [(parent, "1099.00")], description="ZZT Pricier")

    row = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": parent.id,
                "part_product_ids": [],
                "candidate_product_ids": [],
                "promotion_id": None,
            }
        ],
        viewer=_staff_viewer(),
    )[0]

    assert row["auto_promotion_id"] == cheaper.id
    assert row["sell_price"] == Decimal("999.00")
    assert pricier.id in {o["id"] for o in row["promotion_options"]}


# --------------------------------------------------------------------------- AC-S7-5


def test_show_promo_price_derived_on_save(db):
    """`show_promo_price` is written per-line at save time, from `sell_price_basis`.

    Exercised through `PriceTagRequestService.create_request` (the actual save
    path, D1) rather than `line_pricing` directly, since the derivation lives
    beside `_add_lines`.
    """
    from app.services.price_tag_request_service import PriceTagRequestService

    covered = _product(db, list_price="500.00")
    not_covered = _product(db, list_price="500.00")
    promo = _promotion(db, [(covered, "400.00")])
    contact = _contact(db)

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "price_mode": "selling",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": covered.id,
                    "promotion_id": promo.id,
                },
                {"line_type": "product", "product_id": not_covered.id},
            ],
        },
    )
    db.flush()

    by_product = {line.product_id: line for line in request.lines}
    assert by_product[covered.id].show_promo_price is True
    assert by_product[not_covered.id].show_promo_price is False, (
        "a line with no covering promotion and no manual price is LP even in "
        "Selling mode"
    )

    list_mode_request = PriceTagRequestService.create_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "price_mode": "list",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": covered.id,
                    "promotion_id": promo.id,
                }
            ],
        },
    )
    db.flush()
    assert list_mode_request.lines[0].show_promo_price is False


# --------------------------------------------------------------------------- routes


@pytest.fixture
def portal_client():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.main import app  # noqa: E402  first app import in this fixture
    from app.models.access import ContactAccessType, RespondContact, respond_contact_access_types
    from app.models.portal import PortalToken
    from fastapi.testclient import TestClient

    with blank_session() as db:
        contact = RespondContact(
            id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
        )
        db.add(contact)
        access_type = ContactAccessType(
            code=unique_code("at"),
            name=unique_code("Access Type"),
            portal_form_types=["price_tag_request"],
        )
        db.add(access_type)
        db.flush()
        db.execute(
            respond_contact_access_types.insert().values(
                contact_id=contact.id, access_type_code=access_type.code
            )
        )
        db.flush()

        def _override_get_db():
            yield db

        def _override_portal_token():
            return PortalToken(id=_uid(), contact_id=contact.id, space_id="zzt-space")

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = _override_portal_token
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as client:
                yield client, db, contact.id
        finally:
            app.dependency_overrides.clear()


def test_portal_route_uses_contact_audience(portal_client):
    """`POST /public/portal/lookups/line-pricing` gates on the CONTACT's codes.

    A dealer-only promotion must not price a line for a contact who holds no
    dealer access code, even though the promotion genuinely covers the product.
    """
    client, db, contact_id = portal_client
    from app.models.access import ContactAccessType, respond_contact_access_types

    parent = _product(db, list_price="500.00")
    _promotion(db, [(parent, "400.00")], access_levels=["dealer"])

    res = client.post(
        "/api/v1/public/portal/lookups/line-pricing",
        json={
            "price_mode": "selling",
            "lines": [
                {
                    "key": "L1",
                    "product_id": parent.id,
                    "part_product_ids": [],
                    "candidate_product_ids": [],
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    row = res.json()[0]
    assert row["promotion_options"] == []
    assert row["sell_price_basis"] == "list"

    # Granting the contact the "dealer" code makes it visible.
    code = "dealer"
    if db.query(ContactAccessType).filter(ContactAccessType.code == code).first() is None:
        db.add(ContactAccessType(code=code, name=code))
        db.flush()
    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact_id, access_type_code=code
        )
    )
    db.flush()

    res2 = client.post(
        "/api/v1/public/portal/lookups/line-pricing",
        json={
            "price_mode": "selling",
            "lines": [
                {
                    "key": "L1",
                    "product_id": parent.id,
                    "part_product_ids": [],
                    "candidate_product_ids": [],
                }
            ],
        },
    )
    assert res2.status_code == 200, res2.text
    assert res2.json()[0]["sell_price_basis"] == "promotion"


@pytest.fixture
def crm_client():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.main import app  # noqa: E402
    from app.models.base import set_company_scope
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )
    from app.services.company_scope_resolver import apply_company_scope
    from fastapi.testclient import TestClient

    with blank_session() as db:
        role_id = _uid()
        user_id = _uid()
        db.add(
            UserRole(
                id=role_id,
                slug=unique_code("role").lower(),
                name="ZZT Line Pricing Role",
                is_protected=False,
                is_default=False,
            )
        )
        db.add(
            User(
                id=user_id,
                email=f"{unique_code('u').lower()}@test.com",
                name="ZZT Line Pricing User",
                status="ACTIVE",
            )
        )
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        view_perm = str(uuid.uuid4())
        db.add(
            UserPermission(
                id=view_perm, slug="dealer_kit.price_tag_requests.view", name="view", description=""
            )
        )
        db.flush()
        db.add(
            UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=view_perm)
        )
        db.commit()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope
        principal = {"id": user_id, "email": "zzt-line-pricing@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _grant_process():
            process_perm = str(uuid.uuid4())
            db.add(
                UserPermission(
                    id=process_perm,
                    slug="dealer_kit.price_tag_requests.process",
                    name="process",
                    description="",
                )
            )
            db.flush()
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=role_id, permission_id=process_perm
                )
            )
            db.commit()
            # RBAC contract: permissions are cached per user; a grant made mid-test
            # is invisible to the next request until the cache is dropped.
            from app.services.user_service import invalidate_rbac_cache

            invalidate_rbac_cache(user_id)

        with TestClient(app) as client:
            yield client, db, _grant_process
        app.dependency_overrides.clear()


def test_crm_route_requires_process_permission(crm_client):
    client, db, grant_process = crm_client
    parent = _product(db, list_price="500.00")

    without = client.post(
        "/api/v1/dealer-kit/price-tag-requests/line-pricing",
        json={
            "price_mode": "selling",
            "lines": [
                {
                    "key": "L1",
                    "product_id": parent.id,
                    "part_product_ids": [],
                    "candidate_product_ids": [],
                }
            ],
        },
    )
    assert without.status_code == 403, without.text

    grant_process()

    granted = client.post(
        "/api/v1/dealer-kit/price-tag-requests/line-pricing",
        json={
            "price_mode": "selling",
            "lines": [
                {
                    "key": "L1",
                    "product_id": parent.id,
                    "part_product_ids": [],
                    "candidate_product_ids": [],
                }
            ],
        },
    )
    assert granted.status_code == 200, granted.text
