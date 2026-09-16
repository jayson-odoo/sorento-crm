"""The list's stored product-data-change cache (AC-D2, AC-D3, AC-D4, AC-D5).

PLAN-price-tag-currency-token-extract-prompt.md section D: computing the diff
per list row would add up to 50 x 60 ms to every page load. Instead the count
is cached on the request (`store_data_change_count`) and refreshed only for
rows a cheap query (`touched_request_ids`) says were touched since the last
check.

Written test-FIRST (PRINCIPLES.md Phase 2): neither function exists yet -
every call below raises `AttributeError`, the right red for a missing
function. Seeds its own chain throughout; never `LIMIT 1` off existing data.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
BASE_TIME = datetime(2026, 9, 1, 12, 0, 0)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _product(db, stem="ZZTD12", *, list_price="100.00"):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

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
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _touch(db, table: str, row_id: str, column: str, when: datetime) -> None:
    """Set an exact timestamp, bypassing any ORM `onupdate=func.now()` trigger
    (which would only fire on an ORM-tracked change and could not be pinned to
    an arbitrary moment anyway)."""
    from sqlalchemy import text

    db.execute(text(f"UPDATE {table} SET {column} = :t WHERE id = :i"), {"t": when, "i": row_id})
    db.flush()


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


def _request_with_product_line(db, product, *, status="designing"):
    from app.services.price_tag_request_service import PriceTagRequestService

    # `submit_request`, not `create_request` (fixture note): `create_request`
    # alone leaves `portal_draft_at` set, which `_list_query`'s
    # `include_drafts=False` filter - the listing route's own default -
    # excludes entirely, so the row would answer 0 rows for a reason that has
    # nothing to do with the feature under test.
    request = PriceTagRequestService.submit_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {"line_type": "product", "product_id": product.id, "quantity": 1}
            ],
        },
    )
    request.status = status
    db.flush()
    return request


def _product_set(db, members: list):
    from app.models.product_set import ProductSet, ProductSetMember

    product_set = ProductSet(
        id=_uid(), set_code=unique_code("ZZTSET"), name="ZZT set", company_id=SORENTO
    )
    db.add(product_set)
    db.flush()
    member_ids = []
    for index, product in enumerate(members):
        member_id = _uid()
        db.add(
            ProductSetMember(
                id=member_id,
                product_set_id=product_set.id,
                product_id=product.id,
                quantity=Decimal("1"),
                contributes_to_price=True,
                sort_order=index,
            )
        )
        member_ids.append(member_id)
    db.flush()
    return product_set, member_ids


def _request_with_set_line(db, product_set):
    from app.services.price_tag_request_service import PriceTagRequestService

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {
                    "line_type": "product_set",
                    "product_set_id": product_set.id,
                    "quantity": 1,
                }
            ],
        },
    )
    request.status = "designing"
    db.flush()
    return request


def _promotion(db):
    from app.models.marketing import Promotion

    promotion = Promotion(
        id=_uid(), description=unique_code("ZZT promo"), is_active=True, company_id=SORENTO
    )
    db.add(promotion)
    db.flush()
    return promotion


def _attach_promotion_to_line(db, request, promotion) -> None:
    request.lines[0].promotion_id = promotion.id
    db.flush()


def _attachment(db, product):
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment

    name = unique_code("zztimg")
    attachment = Attachment(
        id=_uid(),
        original_filename=f"{name}.jpg",
        stored_filename=f"{name}.jpg",
        file_path=f"https://cdn.example.test/products/{name}.jpg",
        mime_type="image/jpeg",
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    link_id = _uid()
    db.add(
        ProductAttachment(
            id=link_id,
            product_id=product.id,
            attachment_id=attachment.id,
            is_primary=True,
            sort_order=0,
            access_levels=["dealer", "end_user"],
            company_id=SORENTO,
        )
    )
    db.flush()
    return link_id


def _spec_row(db, product):
    from app.models.product_spec import ProductSpecifications

    row_id = _uid()
    db.add(
        ProductSpecifications(
            id=row_id, product_id=product.id, values={}, provenance={}, rendered_text="x"
        )
    )
    db.flush()
    return row_id


# --------------------------------------------------------------------------- AC-D2


class TestStoreDataChangeCount:
    def test_writes_the_count_of_changed_rows_and_a_timestamp(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        request = _request_with_product_line(db, product)
        rows = [
            {"tag_id": "t1", "changes": [{"field": "list_price", "label": "List price"}]},
            {"tag_id": "t2", "changes": []},
        ]

        tag_data_service.store_data_change_count(db, request, rows)
        db.flush()

        assert request.data_changed_tag_count == 1
        assert request.data_checked_at is not None

    def test_a_terminal_request_stores_zero(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        request = _request_with_product_line(db, product, status="void")
        rows = [{"tag_id": "t1", "changes": [{"field": "list_price", "label": "List price"}]}]

        tag_data_service.store_data_change_count(db, request, rows)
        db.flush()

        assert request.data_changed_tag_count == 0

    def test_checked_at_horizon_is_the_callers_own_not_a_post_resolve_read(self, db):
        """Security review 16 Sep: `checked_at` must be a horizon captured
        BEFORE the resolve, never a timestamp read after it - stamping
        post-resolve would swallow a product edit that landed WHILE the
        resolve ran."""
        from app.services.dealer_kit import tag_data_service
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        horizon = BASE_TIME
        rows = [{"tag_id": "t1", "changes": []}]

        # The product moves AFTER the horizon was captured but BEFORE the
        # store call runs - the window a post-resolve stamp would miss.
        _touch(db, "products", product.id, "updated_at", horizon + timedelta(minutes=5))
        tag_data_service.store_data_change_count(db, request, rows, horizon)
        db.flush()

        assert request.data_checked_at == horizon

        touched = PriceTagRequestService.touched_request_ids(db, [request])
        assert request.id in touched


# --------------------------------------------------------------------------- AC-D3


class TestTouchedRequestIds:
    def test_null_data_checked_at_is_touched(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        request.data_checked_at = None
        db.flush()

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_not_touched_when_checked_after_every_source(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME + timedelta(hours=1)
        db.flush()

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id not in touched

    def test_touched_when_the_lines_product_updated_after_the_check(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        request.data_checked_at = BASE_TIME
        db.flush()
        _touch(db, "products", product.id, "updated_at", BASE_TIME + timedelta(hours=1))

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_touched_when_a_spec_row_of_that_product_updated_after_the_check(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        spec_id = _spec_row(db, product)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()
        _touch(
            db,
            "product_specifications",
            spec_id,
            "updated_at",
            BASE_TIME + timedelta(hours=1),
        )

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_touched_when_the_lines_promotion_updated_after_the_check(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        promotion = _promotion(db)
        _attach_promotion_to_line(db, request, promotion)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        _touch(db, "promotions", promotion.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()
        _touch(db, "promotions", promotion.id, "updated_at", BASE_TIME + timedelta(hours=1))

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_touched_when_a_set_members_row_updated_after_the_check(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        member_product = _product(db, "ZZTSETM")
        product_set, member_ids = _product_set(db, [member_product])
        request = _request_with_set_line(db, product_set)
        _touch(db, "products", member_product.id, "updated_at", BASE_TIME)
        _touch(db, "product_set_members", member_ids[0], "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()
        _touch(
            db,
            "product_set_members",
            member_ids[0],
            "updated_at",
            BASE_TIME + timedelta(hours=1),
        )

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_touched_when_a_product_attachment_was_created_after_the_check(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()
        _attachment(db, product)
        attachment_link_id = db.execute(
            sql_text("SELECT id FROM product_attachments WHERE product_id = :p"),
            {"p": product.id},
        ).scalar()
        _touch(
            db,
            "product_attachments",
            attachment_link_id,
            "created_at",
            BASE_TIME + timedelta(hours=1),
        )

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_a_terminal_request_is_never_touched(self, db):
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product, status="void")
        request.data_checked_at = None
        db.flush()
        _touch(db, "products", product.id, "updated_at", BASE_TIME + timedelta(days=1))

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id not in touched

    def test_touched_when_a_parts_own_product_updated_after_the_check(self, db):
        """Code review 16 Sep: `diff_pin_against_live` diffs a part's own
        product too, not just the line's - the touched query has to follow."""
        from app.models.price_tag import PriceTagRequestLinePart
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        part_product = _product(db, "ZZTPART")
        request = _request_with_product_line(db, product)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()
        db.add(
            PriceTagRequestLinePart(
                id=_uid(),
                line_id=request.lines[0].id,
                product_id=part_product.id,
                role="accessory",
            )
        )
        db.flush()
        _touch(db, "products", part_product.id, "updated_at", BASE_TIME + timedelta(hours=1))

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_touched_when_a_freshly_derived_spec_row_has_no_updated_at(self, db):
        """Code review 16 Sep: `write_spec_row` never sets
        `product_specifications.updated_at` on insert - only `created_at` is
        real here, so the touched query must read `GREATEST(updated_at,
        created_at)` or a freshly-derived spec row reads as "never moved"."""
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()

        _spec_row(db, product)  # created_at defaults to real now(); updated_at stays NULL

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched

    def test_touched_when_the_sets_own_name_updated_at_moves(self, db):
        """Code review 16 Sep: a set rename changes the `name` a set line
        diffs, not just its members."""
        from app.services.price_tag_request_service import PriceTagRequestService

        member_product = _product(db, "ZZTSETR")
        product_set, member_ids = _product_set(db, [member_product])
        request = _request_with_set_line(db, product_set)
        _touch(db, "products", member_product.id, "updated_at", BASE_TIME)
        _touch(db, "product_set_members", member_ids[0], "updated_at", BASE_TIME)
        _touch(db, "product_sets", product_set.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME
        db.flush()
        _touch(db, "product_sets", product_set.id, "updated_at", BASE_TIME + timedelta(hours=1))

        touched = PriceTagRequestService.touched_request_ids(db, [request])

        assert request.id in touched


class TestListItemsZerosTerminalCount:
    def test_terminal_request_lists_as_zero_even_with_a_stale_stored_count(self, db):
        """Code review 16 Sep (BLOCKER): `touched_request_ids` never revisits
        a terminal request, so nothing ever zeroes a count stored before it
        closed - `list_items` has to zero it at read time instead."""
        from app.services.price_tag_request_service import PriceTagRequestService

        product = _product(db)
        request = _request_with_product_line(db, product, status="designing")
        request.data_changed_tag_count = 2
        request.data_checked_at = BASE_TIME
        db.flush()

        request.status = "void"
        db.flush()

        items = PriceTagRequestService.list_items(db, [request])

        assert items[0].data_changed_tag_count == 0


# --------------------------------------------------------------------------- AC-D4/AC-D5

_MARKETER_ID = "3a7c5e91-6d24-5f38-a915-2b6c8d4e7a53"
_MARKETER_ROLE = "8c4d6f13-9e37-5a26-b184-3d7e5f9a6c21"


def _seed_principals(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_MARKETER_ROLE,
            slug="zzt_price_tag_marketer_d",
            name="ZZT Price Tag Marketer D",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_MARKETER_ID,
            email="zzt-price-tag-marketer-d@test.com",
            name="ZZT Marketer D",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_MARKETER_ID, role_id=_MARKETER_ROLE))
    for slug in ("dealer_kit.price_tag_requests.view",):
        perm_id = _uid()
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(
                id=_uid(), role_id=_MARKETER_ROLE, permission_id=perm_id
            )
        )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_principals(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope
        principal = {"id": _MARKETER_ID, "email": "zzt-price-tag-marketer-d@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        with TestClient(app) as client:
            yield client, db

        app.dependency_overrides.clear()


class TestListRouteRefreshesOnlyTouchedRows:
    def test_touched_row_returns_a_refreshed_count_and_sets_data_checked_at(self, api, monkeypatch):
        client, db = api
        product = _product(db)
        request = _request_with_product_line(db, product)
        request.data_checked_at = None
        db.flush()
        db.commit()

        res = client.get("/api/v1/dealer-kit/price-tag-requests")

        assert res.status_code == 200, res.text
        row = next(r for r in res.json()["data"] if r["id"] == request.id)
        assert "data_changed_tag_count" in row
        assert isinstance(row["data_changed_tag_count"], int)

        db.refresh(request)
        assert request.data_checked_at is not None

    def test_untouched_row_is_served_from_the_stored_count_and_the_resolver_is_not_called(
        self, api, monkeypatch
    ):
        client, db = api
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        request = _request_with_product_line(db, product)
        _touch(db, "products", product.id, "updated_at", BASE_TIME)
        request.data_checked_at = BASE_TIME + timedelta(days=365)
        request.data_changed_tag_count = 3
        db.flush()
        db.commit()

        calls: list[str] = []
        real_resolver = tag_data_service.resolve_request_line_data

        def counting_resolver(db_arg, req_arg):
            calls.append(req_arg.id)
            return real_resolver(db_arg, req_arg)

        monkeypatch.setattr(tag_data_service, "resolve_request_line_data", counting_resolver)

        res = client.get("/api/v1/dealer-kit/price-tag-requests")

        assert res.status_code == 200, res.text
        row = next(r for r in res.json()["data"] if r["id"] == request.id)
        assert row["data_changed_tag_count"] == 3
        assert request.id not in calls

    def test_refresh_is_capped_at_ten_touched_rows_per_call(self, api, monkeypatch):
        """Security review 16 Sep: unbounded, a page where every row is
        touched (a bulk product edit) turns one list load into dozens of
        resolves - `_DATA_CHANGE_REFRESH_CAP` caps it at 10, in page order."""
        client, db = api
        from app.services.dealer_kit import tag_data_service

        requests = []
        for _ in range(12):
            product = _product(db)
            request = _request_with_product_line(db, product)
            request.data_checked_at = None
            requests.append(request)
        db.flush()
        db.commit()

        calls: list[str] = []
        real_resolver = tag_data_service.resolve_request_line_data

        def counting_resolver(db_arg, req_arg):
            calls.append(req_arg.id)
            return real_resolver(db_arg, req_arg)

        monkeypatch.setattr(tag_data_service, "resolve_request_line_data", counting_resolver)

        res = client.get("/api/v1/dealer-kit/price-tag-requests", params={"limit": 50})

        assert res.status_code == 200, res.text
        seeded_ids = {r.id for r in requests}
        assert len({c for c in calls if c in seeded_ids}) == 10

        for r in requests:
            db.refresh(r)
        checked = [r for r in requests if r.data_checked_at is not None]
        unchecked = [r for r in requests if r.data_checked_at is None]
        assert len(checked) == 10
        assert len(unchecked) == 2
