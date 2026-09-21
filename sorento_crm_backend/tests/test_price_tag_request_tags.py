"""One line, many tags (S3, D3).

UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
(AC-S3-1 create half, AC-S3-4, AC-S3-5, AC-S3-6, AC-S3-8). The migration half of
AC-S3-1 and AC-S3-7 live in `tests/test_migration_ptag_0009_combos_tags.py`.

Written test-FIRST (PRINCIPLES.md Phase 2). `price_tag_request_tags` does not
exist yet, so the model import below fails the WHOLE FILE with one
`ImportError` at collection rather than every case failing separately.

The distinction the whole slice turns on: a LINE is what the salesperson asked
for, a TAG is what gets printed. They were the same object until S3. A line whose
package leaves a choice group open is split by marketing into one tag per
candidate, each with its own quantity, choices, geometry and marketing override.

Routes (`app/api/v1/dealer_kit/price_tag_requests.py`, all behind
`dealer_kit.price_tag_requests.process`):

    PATCH  /price-tag-requests/{id}/tags/{tag_id}
    POST   /price-tag-requests/{id}/tags/{tag_id}/split   body {"role": ...}
    DELETE /price-tag-requests/{id}/tags/{tag_id}         204, or 422 LAST_TAG
    PUT    /price-tag-requests/{id}/lines/{line_id}       REMOVED

Auth-override pattern from `tests/test_price_tag_request_crm_routes.py`.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.price_tag_request_service import PriceTagRequestService

# THE red imports. S1's combo tables and S3's tag table (PLAN D1/D3).
from app.models.product_combo import ProductCombo, ProductComboPart  # noqa: E402
from app.models.price_tag import (  # noqa: E402
    PriceTagRequestLine,
    PriceTagRequestLinePart,
    PriceTagRequestTag,
)

from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
_BASE = "/api/v1/dealer-kit/price-tag-requests"

_MARKETER_ID = "2d6f8a41-5c93-5e27-b108-7a4d3f9c6e16"
_MARKETER_ROLE = "7b3e5d20-8f41-5a96-c274-1e6b9d4a8f31"


def _uid() -> str:
    return str(uuid.uuid4())


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
            slug="zzt_price_tag_tag_marketer",
            name="ZZT Price Tag Tag Marketer",
            description="Designs price tags",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_MARKETER_ID,
            email="zzt-tag-marketer@test.com",
            name="ZZT Marketing Mei",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_MARKETER_ID, role_id=_MARKETER_ROLE))
    for slug in (
        "dealer_kit.price_tag_requests.view",
        "dealer_kit.price_tag_requests.process",
    ):
        perm_id = _uid()
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(id=_uid(), role_id=_MARKETER_ROLE, permission_id=perm_id)
        )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
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

        principal = {"id": _MARKETER_ID, "email": "zzt-tag-marketer@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        with TestClient(app) as client:
            yield client, db

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


def _product(db, stem: str, *, class_label: str | None = None, list_price="1599.00"):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    code = unique_code(stem)
    category = ProductCategory(
        id=_uid(),
        category_code=code[:50],
        category_name=f"ZZT cat {code}",
        class_label=class_label,
    )
    brand = Brand(id=_uid(), brand_code=code[:50], brand_name=f"ZZT {code}")
    uom = UnitOfMeasure(id=_uid(), uom_code=code[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _combo(db, host, name: str, parts) -> ProductCombo:
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


def _open_basin_request(db, *, candidates: int = 4):
    """A submitted request whose one line leaves a 4-candidate Basin group open.

    The journey's own case: the salesperson asks for the cabinet and does not
    know which basin colour, so marketing splits the line's tag into four.
    """
    contact = _contact(db)
    cabinet = _product(db, "SRTBF11834", class_label="Bathroom Furniture")
    mirror = _product(db, "SRTMR502-BL", list_price="199.00")
    basins = [_product(db, f"SRTBS900-{i}", list_price="299.00") for i in range(candidates)]
    combo = _combo(
        db,
        cabinet,
        "4 in 1",
        [(mirror, None)] + [(basin, "Basin") for basin in basins],
    )

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": cabinet.id,
                    "combo_id": combo.id,
                    "quantity": 3,
                    "parts": [
                        {"product_id": mirror.id},
                        {
                            "role": "Basin",
                            "candidates": [basin.id for basin in basins],
                        },
                    ],
                }
            ],
        },
    )
    db.commit()
    return request, cabinet, mirror, basins


def _tags_of(db, line_id: str) -> list[PriceTagRequestTag]:
    return (
        db.query(PriceTagRequestTag)
        .filter(PriceTagRequestTag.line_id == line_id)
        .order_by(PriceTagRequestTag.sort_order)
        .all()
    )


# --------------------------------------------------------------------------- AC-S3-1


def test_submit_creates_one_tag_per_line(api):
    """Exactly one tag per line at submit, carrying the line's quantity.

    Not zero (the designer would have nothing to key its document on) and not
    one per candidate (auto-split was rejected by the owner - marketing decides
    in the designer). `show_promo_price`, `quantity` and `remarks` stay on the
    LINE as the salesperson's ask; the tag's quantity is seeded from it and is
    the marketing user's to change afterwards.
    """
    _client, db = api
    contact = _contact(db)
    first = _product(db, "SRTAC100")
    second = _product(db, "SRTAC200")

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {"line_type": "product", "product_id": first.id, "quantity": 3,
                 "remarks": "ZZT note"},
                {"line_type": "product", "product_id": second.id, "quantity": 1},
            ],
        },
    )
    db.commit()

    by_order = sorted(request.lines, key=lambda l: (l.sort_order or 0, l.id))
    for line, expected_quantity in zip(by_order, [3, 1]):
        tags = _tags_of(db, line.id)
        assert len(tags) == 1, "one tag per line at submit, never zero and never N"
        assert tags[0].quantity == expected_quantity
        assert tags[0].choices == {}
        assert tags[0].sort_order == 0

    # The salesperson's ask stays on the line.
    assert by_order[0].quantity == 3
    assert by_order[0].remarks == "ZZT note"

    # The override moved OFF the line (D3) - it is a tag fact now.
    assert not hasattr(PriceTagRequestLine, "marketing_price_override")
    assert not hasattr(PriceTagRequestLine, "marketing_override_reason")


# --------------------------------------------------------------------------- AC-S3-4


# D6 (PLAN-price-tag-line-promo-combo-subject.md, owner ruling): the rail's
# Split and Pick one are retired outright - a line's open choice group
# auto-splits into one tag per candidate at submit (`_add_line_tags`), so
# there is no "one tag, still open" state left for either action to act on.
# `test_split_tag_resolves_first_and_adds_siblings` (asserted
# `POST .../tags/{id}/split` minted the siblings) and
# `test_pick_one_resolves_the_group_on_that_tag_alone` (asserted
# `PATCH .../tags/{id}` accepted a `choices` key) both tested routes/fields
# this revision removes; `test_price_tag_auto_split.py::
# test_split_route_gone_and_choices_rejected` is the replacement covering the
# route is gone and `choices` is refused. What each proved about SHAPE (the
# label ordinals, `open_groups` empty once resolved, one tag per candidate)
# is re-proven directly off the auto-split tags in
# `test_print_payload_one_row_per_tag` below and in
# `test_price_tag_auto_split.py`.


# --------------------------------------------------------------------------- AC-S3-5


def test_tag_patch_override_round_trip(api):
    """The marketing override and its reason live on the TAG and round-trip.

    They have to be per tag: two tags split off one line print two different
    basins at two different prices, and a line-level override would put the same
    hand-set figure on both.
    """
    client, db = api
    request, _cabinet, _mirror, _basins = _open_basin_request(db)
    tag = _tags_of(db, request.lines[0].id)[0]

    response = client.patch(
        f"{_BASE}/{request.id}/tags/{tag.id}",
        json={
            "quantity": 5,
            "marketing_price_override": "1299.00",
            "marketing_override_reason": "ZZT roadshow price",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quantity"] == 5
    assert Decimal(str(body["marketing_price_override"])) == Decimal("1299.00")
    assert body["marketing_override_reason"] == "ZZT roadshow price"

    db.expire_all()
    stored = db.query(PriceTagRequestTag).filter(PriceTagRequestTag.id == tag.id).one()
    assert stored.quantity == 5
    assert Decimal(str(stored.marketing_price_override)) == Decimal("1299.00")


def test_line_override_route_gone(api):
    """`PUT /lines/{line_id}` is removed with the columns it wrote.

    Left mounted it would keep accepting a blind `setattr` of fields that no
    longer exist, so a stale FE build would get a 200 for a write that did
    nothing.
    """
    client, db = api
    request, _cabinet, _mirror, _basins = _open_basin_request(db)
    line_id = request.lines[0].id

    response = client.put(
        f"{_BASE}/{request.id}/lines/{line_id}",
        json={"marketing_price_override": "1.00"},
    )
    assert response.status_code in (404, 405, 410), response.text


# --------------------------------------------------------------------------- AC-S3-6


def test_delete_last_tag_422(api):
    """A line always keeps at least one tag: removing the last one is refused.

    A line with no tags is a line that can never be printed and never be
    designed, and nothing in the UI would say why. D6: the open Basin group
    already auto-splits into 4 tags at submit - there is no Split route left
    to mint the other three by hand, so this deletes down to the last
    survivor directly instead.
    """
    client, db = api
    request, _cabinet, _mirror, _basins = _open_basin_request(db, candidates=4)
    line = request.lines[0]
    tags = _tags_of(db, line.id)
    assert len(tags) == 4, "D6: auto-split off the one open Basin group"

    for tag in tags[1:]:
        removed = client.delete(f"{_BASE}/{request.id}/tags/{tag.id}")
        assert removed.status_code == 204, removed.text

    db.expire_all()
    assert len(_tags_of(db, line.id)) == 1

    # The last survivor is refused.
    last = client.delete(f"{_BASE}/{request.id}/tags/{_tags_of(db, line.id)[0].id}")
    assert last.status_code == 422
    assert last.json()["code"] == "LAST_TAG"


# --------------------------------------------------------------------------- AC-S3-8


def test_print_payload_one_row_per_tag(api):
    """The resolver answers one row per TAG, with that tag's own quantity.

    D6 (PLAN-price-tag-line-promo-combo-subject.md): the line's one open
    Basin group auto-splits into 4 tags straight off `submit_request` - there
    is no longer a "one row, then split, then four rows" progression to
    observe, `_open_basin_request` already returns a line with all 4. One
    resolver still feeds the designer, the portal, the detail body and the
    print payload (D3), so this is the single place the per-tag shape has to
    be true for the proof on screen and the PDF to agree. The sheet's tile
    count is `quantity` copies of each row, laid out by `autoArrange` on the
    client - pinned separately in `lib/dealer-kit/request-tags.test.ts`.
    """
    client, db = api
    from app.services.dealer_kit import tag_data_service

    request, cabinet, _mirror, basins = _open_basin_request(db, candidates=4)
    line = request.lines[0]

    rows = tag_data_service.resolve_request_line_data(db, request)
    assert len(rows) == 4
    assert [row["tag_label"] for row in rows] == ["1a", "1b", "1c", "1d"]
    assert {row["line_id"] for row in rows} == {line.id}
    assert [row["tag_id"] for row in rows] == [tag.id for tag in _tags_of(db, line.id)]
    assert [row["open_groups"] for row in rows] == [[], [], [], []]
    assert rows[0]["code"] == cabinet.product_code
    # The sheet prints 4 tags x 3 copies (the LINE's own quantity, seeded
    # onto every auto-split tag).
    assert [row["quantity"] for row in rows] == [3, 3, 3, 3]
    assert sum(row["quantity"] for row in rows) == 12

    # A per-tag quantity change is what the payload reports, not the line's.
    client.patch(f"{_BASE}/{request.id}/tags/{rows[1]['tag_id']}", json={"quantity": 1})
    db.expire_all()
    requantified = tag_data_service.resolve_request_line_data(db, request)
    assert [row["quantity"] for row in requantified] == [3, 1, 3, 3]
    assert sum(row["quantity"] for row in requantified) == 10
    assert len(basins) == 4


# ---------------------------------------------------------------------------
# AC-S6-2 (PLAN-price-tag-r10.md S6): round 4 replaced the earlier "merge onto
# one tag" design - submit still mints ONE TAG PER CANDIDATE off an open
# group. This pins the kept behaviour through the S6 refactor.
# ---------------------------------------------------------------------------


def test_ac_s6_2_submit_with_a_3_candidate_open_group_still_mints_three_tags(api):
    _client, db = api
    request, _cabinet, _mirror, basins = _open_basin_request(db, candidates=3)

    tags = _tags_of(db, request.lines[0].id)

    assert len(tags) == 3
    assert len(basins) == 3
    # Each tag resolved a DIFFERENT candidate - never the same one twice, and
    # never all three folded onto one tag's `choices`.
    chosen = [set(tag.choices.values()) for tag in tags]
    assert all(len(c) == 1 for c in chosen)
    assert len({frozenset(c) for c in chosen}) == 3


# ---------------------------------------------------------------------------
# AC-S6-7 (PLAN-price-tag-r10.md S6): `PATCH .../tags/{tag_id}` accepts
# `print_excluded`; refused (409) once the request has reached `proof_ready`,
# like every other design edit. Cross-company 404 is covered by the existing
# B1 guard, `test_price_tag_combos_security.py::
# test_cross_company_tag_routes_404_and_change_nothing`, which already PATCHes
# this same route - a new field on an already-guarded route inherits that
# guard rather than needing its own copy.
# ---------------------------------------------------------------------------


def test_ac_s6_7_print_excluded_round_trips_through_patch(api):
    client, db = api
    request, _cabinet, _mirror, _basins = _open_basin_request(db)
    tag = _tags_of(db, request.lines[0].id)[0]

    response = client.patch(
        f"{_BASE}/{request.id}/tags/{tag.id}", json={"print_excluded": True}
    )

    assert response.status_code == 200, response.text
    assert response.json()["print_excluded"] is True

    db.expire_all()
    stored = db.query(PriceTagRequestTag).filter(PriceTagRequestTag.id == tag.id).one()
    assert stored.print_excluded is True

    cleared = client.patch(
        f"{_BASE}/{request.id}/tags/{tag.id}", json={"print_excluded": False}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["print_excluded"] is False


def test_ac_s6_7_print_excluded_refused_at_proof_ready(api):
    client, db = api
    request, _cabinet, _mirror, _basins = _open_basin_request(db)
    tag = _tags_of(db, request.lines[0].id)[0]
    request.status = "proof_ready"
    db.commit()

    response = client.patch(
        f"{_BASE}/{request.id}/tags/{tag.id}", json={"print_excluded": True}
    )

    assert response.status_code == 409, response.text
