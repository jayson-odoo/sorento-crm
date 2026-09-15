"""Auto-split at submit: an open choice group becomes N tags, no Split UI (D6, S8).

UAC: AC-S8-1 to AC-S8-4. Written test-FIRST (PRINCIPLES.md Phase 2). The tag
builder (`PriceTagRequestService._add_line_tags`, called from `_add_lines`)
currently mints exactly ONE tag per line regardless of any open group left on
it - straight from the code:

    rows = carried if carried else [
        {"sort_order": 0, "quantity": line.quantity or 1, "choices": {}}
    ]

so `test_one_open_group_makes_n_tags` and `test_two_open_groups_cartesian`
below fail today on a plain `len(tags) == 1`, not an import error - this file
imports nothing that does not already exist.

AC-S8-5 (the migration-time split of PRE-EXISTING open tags) lives in
`test_migration_ptag_0011_line_promotion.py`, since it is a property of the
migration, not of `_add_line_tags`.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.dealer_kit import tag_data_service
from app.services.price_tag_request_service import PriceTagRequestService
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


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _product(db, stem: str, *, list_price="199.00"):
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
        company_id=SORENTO,
        product_code=code,
        product_name=f"ZZT {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=list_price,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _combo(db, host, name, parts):
    combo = ProductCombo(id=_uid(), host_product_id=host.id, name=name, sort_order=0)
    db.add(combo)
    db.flush()
    for index, (product, choice_group) in enumerate(parts):
        db.add(
            ProductComboPart(
                id=_uid(),
                combo_id=combo.id,
                part_product_id=product.id,
                choice_group=choice_group,
                sort_order=index,
            )
        )
    db.flush()
    return combo


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


# --------------------------------------------------------------------------- AC-S8-1


def test_one_open_group_makes_n_tags(db):
    cabinet = _product(db, "cab", list_price="1599.00")
    white = _product(db, "wh", list_price="299.00")
    black = _product(db, "bk", list_price="349.00")
    combo = _combo(db, cabinet, "2 in 1", [(white, "Basin"), (black, "Basin")])

    request = PriceTagRequestService.create_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": cabinet.id,
                    "combo_id": combo.id,
                    "parts": [{"role": "Basin", "candidates": [white.id, black.id]}],
                }
            ],
        },
    )
    db.flush()

    tags = sorted(request.lines[0].tags, key=lambda tag: tag.sort_order or 0)
    assert len(tags) == 2, "one tag per candidate, straight off submit"
    assert [tag.choices.get("Basin") for tag in tags] == [white.id, black.id]
    assert all(tag.choices for tag in tags), "no tag is left with an empty choices map"

    rows = tag_data_service.resolve_request_line_data(db, request)
    assert all(row["open_groups"] == [] for row in rows), (
        "open_groups stays on the shape and is always empty - the designer never "
        "sees an Open tag"
    )


# --------------------------------------------------------------------------- AC-S8-2


def test_two_open_groups_cartesian(db):
    cabinet = _product(db, "cab2", list_price="999.00")
    tap_a = _product(db, "tapa", list_price="49.00")
    tap_b = _product(db, "tapb", list_price="59.00")
    basin_a = _product(db, "basa", list_price="199.00")
    basin_b = _product(db, "basb", list_price="249.00")
    basin_c = _product(db, "basc", list_price="299.00")
    combo = _combo(
        db,
        cabinet,
        "combo",
        [
            (tap_a, "Tap"),
            (tap_b, "Tap"),
            (basin_a, "Basin"),
            (basin_b, "Basin"),
            (basin_c, "Basin"),
        ],
    )

    request = PriceTagRequestService.create_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": cabinet.id,
                    "combo_id": combo.id,
                    "parts": [
                        {"role": "Tap", "candidates": [tap_a.id, tap_b.id]},
                        {
                            "role": "Basin",
                            "candidates": [basin_a.id, basin_b.id, basin_c.id],
                        },
                    ],
                }
            ],
        },
    )
    db.flush()

    tags = sorted(request.lines[0].tags, key=lambda tag: tag.sort_order or 0)
    assert len(tags) == 6, "2 taps x 3 basins"
    labels = [tag_data_service._tag_label(0, index) for index in range(6)]
    assert labels == ["1a", "1b", "1c", "1d", "1e", "1f"]


# --------------------------------------------------------------------------- AC-S8-3


def test_resave_keeps_split_tags(db):
    cabinet = _product(db, "cab3", list_price="500.00")
    white = _product(db, "wh3", list_price="100.00")
    black = _product(db, "bk3", list_price="150.00")
    combo = _combo(db, cabinet, "combo3", [(white, "Basin"), (black, "Basin")])
    line_data = {
        "line_type": "product",
        "product_id": cabinet.id,
        "combo_id": combo.id,
        "parts": [{"role": "Basin", "candidates": [white.id, black.id]}],
    }

    request = PriceTagRequestService.create_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={"debtor_name": "ZZT Dealer", "lines": [line_data]},
    )
    db.flush()
    before = sorted(
        (tag.id, tag.sort_order, tag.quantity) for tag in request.lines[0].tags
    )
    assert len(before) == 2, "seed assumption: the line split into two on create"

    PriceTagRequestService.replace_lines(
        db, request, [{**line_data, "remarks": "ZZT re-saved, parts unchanged"}]
    )
    db.flush()

    after = sorted(
        (tag.id, tag.sort_order, tag.quantity) for tag in request.lines[0].tags
    )
    assert after == before, "a re-save with unchanged parts keeps the same tags"


# --------------------------------------------------------------------------- AC-S8-4


@pytest.fixture
def crm_client():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        role_id, user_id = _uid(), _uid()
        db.add(
            UserRole(
                id=role_id,
                slug=unique_code("role").lower(),
                name="ZZT Split Role",
                is_protected=False,
                is_default=False,
            )
        )
        db.add(
            User(
                id=user_id,
                email=f"{unique_code('u').lower()}@test.com",
                name="ZZT Split User",
                status="ACTIVE",
            )
        )
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for slug in (
            "dealer_kit.price_tag_requests.view",
            "dealer_kit.price_tag_requests.process",
        ):
            perm_id = str(uuid.uuid4())
            db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
            db.flush()
            db.add(
                UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_id)
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
        principal = {"id": user_id, "email": "zzt-split@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        with TestClient(app) as client:
            yield client, db
        app.dependency_overrides.clear()


def test_split_route_gone_and_choices_rejected(crm_client):
    client, db = crm_client
    cabinet = _product(db, "cab4", list_price="500.00")
    white = _product(db, "wh4", list_price="100.00")
    black = _product(db, "bk4", list_price="150.00")
    combo = _combo(db, cabinet, "combo4", [(white, "Basin"), (black, "Basin")])
    request = PriceTagRequestService.create_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": cabinet.id,
                    "combo_id": combo.id,
                    "parts": [{"role": "Basin", "candidates": [white.id, black.id]}],
                }
            ],
        },
    )
    request.portal_draft_at = None
    db.commit()
    tag_id = request.lines[0].tags[0].id
    base = f"/api/v1/dealer-kit/price-tag-requests/{request.id}"

    split = client.post(f"{base}/tags/{tag_id}/split", json={"role": "Basin"})
    assert split.status_code in (404, 405), split.text

    patched = client.patch(
        f"{base}/tags/{tag_id}", json={"choices": {"Basin": white.id}}
    )
    assert patched.status_code == 422, patched.text
