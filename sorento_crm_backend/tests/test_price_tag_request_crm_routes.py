"""The CRM price tag routes, on the wire.

``test_price_tag_request.py`` covers the service. This file covers what a
service test structurally cannot: FastAPI's ``response_model`` drops any field
the schema does not declare, silently, so the listing and the detail page drew
blanks for the line count, the salesperson, the promotion and the assignee while
every service call underneath was answering correctly.

Auth-override pattern from ``test_dealer_kit_tag_data_routes.py``.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session, unique_code
from tests import _ptag_r9_seed

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
_BASE = "/api/v1/dealer-kit/price-tag-requests"

_MARKETER_ID = "2d6f8a41-5c93-5e27-b108-7a4d3f9c6e15"
_MARKETER_ROLE = "7b3e5d20-8f41-5a96-c274-1e6b9d4a8f30"
_MARKETER_NAME = "ZZT Marketing Mei"


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
            slug="zzt_price_tag_marketer",
            name="ZZT Price Tag Marketer",
            description="Designs price tags",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_MARKETER_ID,
            email="zzt-price-tag-marketer@test.com",
            name=_MARKETER_NAME,
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_MARKETER_ID, role_id=_MARKETER_ROLE))

    for slug in (
        "dealer_kit.price_tag_requests.view",
        "dealer_kit.price_tag_requests.process",
    ):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=_MARKETER_ROLE, permission_id=perm_id
            )
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

        principal = {"id": _MARKETER_ID, "email": "zzt-price-tag-marketer@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        with TestClient(app) as client:
            yield client, db

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _contact(db, name: str):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=name,
    )
    db.add(contact)
    db.flush()
    return contact


def _promotion(db, description: str) -> str:
    from app.models.marketing import Promotion

    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        is_active=True,
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    return promotion.id


def _cover_promotion(db, promotion_id: str, product) -> None:
    """D1/AC-S6-5: a line's promotion is accepted only if it has a
    ``PromotionProduct`` row for a product on that line - the request-level
    "distributes to lines" convenience is gone, so every promotion a test
    attaches to a line has to actually cover it."""
    from decimal import Decimal

    from app.models.marketing import PromotionGroup, PromotionProduct

    group = PromotionGroup(promotion_id=promotion_id, group_name="ZZT group", sort_order=0)
    db.add(group)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion_id,
            promotion_group_id=str(group.id),
            product_id=product.id,
            promo_selling_price=Decimal("400.00"),
            company_id=SORENTO,
        )
    )
    db.flush()


def _product(db):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("PTR")
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=stem, category_name=f"ZZT cat {stem}"
    )
    brand = Brand(id=str(uuid.uuid4()), brand_code=stem[:50], brand_name=f"ZZT {stem}")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=1599.00,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _submitted_request(
    db,
    *,
    lines: int = 2,
    promotion_id: str | None = None,
    price_mode: str = "list",
):
    """A request the salesperson has SENT: no ``portal_draft_at``.

    D1: a promotion is a LINE fact, never the header - when ``promotion_id``
    is given it is attached to the FIRST line's own dict, and (AC-S6-5) that
    promotion must already cover that line's product, so this covers it
    before building the line.
    """
    contact = _contact(db, unique_code("ZZT Sales Sam"))
    products = [_product(db) for _ in range(lines)]
    if promotion_id and products:
        _cover_promotion(db, promotion_id, products[0])
    line_dicts = [
        {
            "line_type": "product",
            "product_id": product.id,
            **({"promotion_id": promotion_id} if index == 0 and promotion_id else {}),
        }
        for index, product in enumerate(products)
    ]
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "price_mode": price_mode,
            "lines": line_dicts,
        },
    )
    request.portal_draft_at = None
    db.commit()
    return request, contact


# ---------------------------------------------------------------------------
# What the screens draw
# ---------------------------------------------------------------------------


class TestTheDetailNamesWhoClaimedIt:
    def test_a_claim_records_the_claimer_and_the_detail_names_them(self, api):
        """"Assigned to" read "Unclaimed" forever after a successful claim.

        The claim wrote the user id into ``created_by``, which nothing reads
        back, and neither the column the page reads nor the name beside it was
        declared on the response - so the request moved to ``designing`` with no
        sign of who was designing it.
        """
        client, db = api
        request, _contact = _submitted_request(db)

        claimed = client.post(f"{_BASE}/{request.id}/claim")
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["assigned_to_id"] == _MARKETER_ID
        assert claimed.json()["assigned_to_name"] == _MARKETER_NAME

        detail = client.get(f"{_BASE}/{request.id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["assigned_to_id"] == _MARKETER_ID
        assert body["assigned_to_name"] == _MARKETER_NAME
        assert body["status"] == "designing"

    def test_the_creator_is_not_overwritten_by_a_claim(self, api):
        """``created_by`` says who made the row; it is not the assignee field."""
        client, db = api
        request, _contact = _submitted_request(db)
        assert request.created_by is None

        client.post(f"{_BASE}/{request.id}/claim")

        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        row = db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).first()
        assert row.created_by is None
        assert row.assigned_to_id == _MARKETER_ID

    def test_the_detail_names_the_salesperson_and_the_promotion(self, api):
        """D1 (S6): a promotion is a LINE fact - the header carries no
        `promotion_name` any more, so this reads it off the covered line."""
        client, db = api
        promotion_id = _promotion(db, "ZZT August Promo")
        request, contact = _submitted_request(db, promotion_id=promotion_id)

        body = client.get(f"{_BASE}/{request.id}").json()

        assert body["contact_name"] == contact.name
        assert "promotion_name" not in body
        assert body["lines"][0]["promotion_name"] == "ZZT August Promo"

    def test_an_unclaimed_request_says_so_rather_than_guessing(self, api):
        client, db = api
        request, _contact = _submitted_request(db)

        body = client.get(f"{_BASE}/{request.id}").json()

        assert body["assigned_to_id"] is None
        assert body["assigned_to_name"] is None

    def test_the_detail_carries_price_mode_and_each_lines_remarks(self, api):
        """AC-S2-7: `response_model` drops an undeclared field without a
        word, so this has to be asserted on the wire, not just in the
        service layer (`test_price_tag_request.py` covers that side).

        D1: no promotion here - this test is about `price_mode`/`remarks`,
        neither of which a promotion affects, so it does not seed one."""
        client, db = api
        contact = _contact(db, unique_code("ZZT Sales Sam"))
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
                        "product_id": _product(db).id,
                        "remarks": "Face out on the top shelf",
                    }
                ],
            },
        )
        request.portal_draft_at = None
        db.commit()

        body = client.get(f"{_BASE}/{request.id}").json()

        assert body["price_mode"] == "selling"
        assert body["lines"][0]["remarks"] == "Face out on the top shelf"


class TestTheListingCarriesWhatItDraws:
    def test_the_row_carries_the_line_count_and_the_names(self, api):
        """D1 (S6): `PriceTagRequestListItem` dropped `promotion_id`/
        `promotion_name` outright - a promotion is a line fact now, and the
        queue's columns never showed a per-line breakdown - so this checks
        the field is gone rather than asserting a value for it."""
        client, db = api
        promotion_id = _promotion(db, "ZZT Listing Promo")
        request, contact = _submitted_request(db, lines=3, promotion_id=promotion_id)

        listed = client.get(_BASE, params={"query": request.doc_number})
        assert listed.status_code == 200, listed.text
        rows = listed.json()
        row = next(r for r in _rows_of(rows) if r["id"] == request.id)

        assert row["line_count"] == 3
        assert row["contact_name"] == contact.name
        assert "promotion_name" not in row
        assert row["assigned_to_name"] is None

    def test_a_claimed_row_shows_the_claimer_in_the_listing(self, api):
        client, db = api
        request, _contact = _submitted_request(db)
        client.post(f"{_BASE}/{request.id}/claim")

        listed = client.get(_BASE, params={"query": request.doc_number})
        row = next(r for r in _rows_of(listed.json()) if r["id"] == request.id)

        assert row["assigned_to_id"] == _MARKETER_ID
        assert row["assigned_to_name"] == _MARKETER_NAME


class TestTheQueuePagesOnTheServer:
    """The listing answered the WHOLE table and the page was cut on the client.

    Every keystroke and every page turn shipped every request in the system to
    the browser, and the record count under the grid was the size of the array
    that happened to arrive rather than what the table holds.
    """

    def test_the_answer_is_one_page_with_the_real_total(self, api):
        client, db = api
        for _ in range(3):
            _submitted_request(db, lines=1)

        first = client.get(_BASE, params={"page": 1, "limit": 2}).json()

        assert len(first["data"]) == 2
        assert first["pagination"]["total"] >= 3
        assert first["pagination"]["page"] == 1
        assert first["pagination"]["limit"] == 2

    def test_the_second_page_carries_different_rows(self, api):
        client, db = api
        for _ in range(3):
            _submitted_request(db, lines=1)

        first = client.get(_BASE, params={"page": 1, "limit": 2}).json()
        second = client.get(_BASE, params={"page": 2, "limit": 2}).json()

        assert {row["id"] for row in first["data"]}.isdisjoint(
            {row["id"] for row in second["data"]}
        )

    def test_it_sorts_by_the_column_it_is_asked_for(self, api):
        client, db = api
        for _ in range(3):
            _submitted_request(db, lines=1)

        ascending = client.get(
            _BASE, params={"sort": "doc_number", "dir": "asc", "limit": 100}
        ).json()["data"]
        descending = client.get(
            _BASE, params={"sort": "doc_number", "dir": "desc", "limit": 100}
        ).json()["data"]

        numbers = [row["doc_number"] for row in ascending]
        assert numbers == sorted(numbers)
        assert [row["doc_number"] for row in descending] == list(reversed(numbers))

    def test_an_unknown_sort_column_falls_back_rather_than_failing(self, api):
        client, db = api
        _submitted_request(db, lines=1)

        answered = client.get(_BASE, params={"sort": "nonsense", "dir": "asc"})

        assert answered.status_code == 200, answered.text

    def test_search_narrows_the_page_and_the_total(self, api):
        client, db = api
        wanted, _contact = _submitted_request(db, lines=1)
        _submitted_request(db, lines=1)

        answered = client.get(_BASE, params={"query": wanted.doc_number}).json()

        assert [row["id"] for row in answered["data"]] == [wanted.id]
        assert answered["pagination"]["total"] == 1


def _rows_of(body):
    """The listing rows, whether the body is a bare list or a paged envelope."""
    return body["data"] if isinstance(body, dict) else body


# ---------------------------------------------------------------------------
# AC-S1-5 (CRM half): the detail route answers with real attachments
#
# response_model drops any field the schema does not declare, silently
# (LESSONS-LEARNT.md) - this is that trap, exercised on the wire rather than
# on the service, same as the rest of this file.
# ---------------------------------------------------------------------------


def _link_attachment_to_request(db, request_id: str, *, filename: str = "ZZT-po.pdf") -> str:
    import uuid as _uuid

    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    att = Attachment(
        id=str(_uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"portal/zzt/{_uuid.uuid4()}.pdf",
        mime_type="application/pdf",
        uploader_kind="contact",
    )
    db.add(att)
    db.flush()
    link = EntityAttachmentLink(
        entity_type="price_tag_request", entity_id=request_id, attachment_id=att.id
    )
    db.add(link)
    db.commit()
    return str(att.id)


class TestTheCRMDetailCarriesPOAttachments:
    def test_the_detail_route_lists_the_po_attachments(self, api):
        client, db = api
        request, _contact = _submitted_request(db)
        attachment_id = _link_attachment_to_request(db, request.id)

        body = client.get(f"{_BASE}/{request.id}").json()

        assert len(body["attachments"]) == 1
        att = body["attachments"][0]
        assert att["attachment_id"] == attachment_id
        assert att["filename"] == "ZZT-po.pdf"
        assert att["content_type"] == "application/pdf"
        assert "url" in att

    def test_a_request_with_no_attachments_still_answers_with_an_empty_list(self, api):
        client, db = api
        request, _contact = _submitted_request(db)

        body = client.get(f"{_BASE}/{request.id}").json()

        assert body["attachments"] == []


# ---------------------------------------------------------------------------
# has_completed_export: the same response_model trap, on the CRM detail route
#
# The portal detail route has its own assertion of this
# (``test_portal_price_tag_routes.py::TestTheDownloadRoute``); this is the
# CRM twin. `get_price_tag_request` answers with `response_model=
# PriceTagRequestResponse` (LESSONS-LEARNT.md: an undeclared field is dropped
# silently), so a schema change on the portal side that missed this route
# would pass every portal test and still ship a marketing screen that always
# reads "no export".
# ---------------------------------------------------------------------------


def _seed_completed_export(db, request_id: str, *, filename: str = "ZZT-tags.pdf") -> None:
    from app.models.download import DownloadStatus, UserDownload
    from app.services.dealer_kit.tag_sheet_export_service import KIND

    db.add(
        UserDownload(
            id=str(uuid.uuid4()),
            user_id=_MARKETER_ID,
            kind=KIND,
            source_entity_type="price_tag_request",
            source_entity_id=str(request_id),
            status=DownloadStatus.READY.value,
            filename=filename,
            storage_provider="s3",
            storage_key=f"zzt/{uuid.uuid4()}.pdf",
        )
    )
    db.commit()


class TestTheDetailCarriesHasCompletedExport:
    def test_a_completed_export_flips_the_flag(self, api):
        client, db = api
        request, _contact = _submitted_request(db)
        assert client.get(f"{_BASE}/{request.id}").json()["has_completed_export"] is False

        _seed_completed_export(db, request.id)

        assert client.get(f"{_BASE}/{request.id}").json()["has_completed_export"] is True


# ---------------------------------------------------------------------------
# The design route only writes from a status the FE's own Lines tab /
# header would offer Design from (PLAN-price-tag-feedback-r2 S10 review):
# ``save_tag_sheet_design`` wrote a PageVersion in ANY status before this,
# so a stale tab on an approved/void/ready request could still overwrite
# the tag sheet doc after the record had moved on.
# ---------------------------------------------------------------------------


class TestTheDesignRouteOnlySavesFromADesignableStatus:
    @staticmethod
    def _page_version_count(db, request_id: str) -> int:
        from app.models.dealer_kit import PageVersion
        from app.models.price_tag import PriceTagRequest

        row = (
            db.query(PriceTagRequest).filter(PriceTagRequest.id == request_id).first()
        )
        db.expire(row)
        return (
            db.query(PageVersion)
            .filter(PageVersion.page_id == row.page_id)
            .count()
        )

    def test_designing_may_save(self, api):
        """Claim moves the request to ``designing`` and creates its page - the
        one status every request reaches this route through in practice."""
        client, db = api
        request, _contact = _submitted_request(db)
        assert client.post(f"{_BASE}/{request.id}/claim").status_code == 200

        resp = client.put(
            f"{_BASE}/{request.id}/design",
            json={"doc": {"kind": "tag_sheet", "sheets": []}},
        )

        assert resp.status_code == 200, resp.text
        assert self._page_version_count(db, request.id) == 1

    @pytest.mark.parametrize(
        "target_status",
        ["void", "approved", "ready_for_collection"],
    )
    def test_refuses_to_save_once_the_request_has_moved_past_designing(
        self, api, target_status
    ):
        client, db = api
        request, _contact = _submitted_request(db)
        assert client.post(f"{_BASE}/{request.id}/claim").status_code == 200

        # Walk the real transition graph to the target status rather than
        # writing the column directly, so this exercises exactly the states a
        # request can actually be in.
        #
        # r9 D8 retired `ready`: the office hand-over replaces it, and it is
        # only reachable when somebody has said the OFFICE prints.
        if target_status == "ready_for_collection":
            from app.models.price_tag import PriceTagRequest

            db.query(PriceTagRequest).filter(
                PriceTagRequest.id == request.id
            ).update({"print_by": "office"})
            db.flush()
        path = {
            "void": ["void"],
            "approved": ["proof_ready", "approved"],
            "ready_for_collection": [
                "proof_ready",
                "approved",
                "ready_for_collection",
            ],
        }[target_status]
        for status in path:
            PriceTagRequestService.transition_status(db, request.id, status)
        db.commit()

        before = self._page_version_count(db, request.id)
        resp = client.put(
            f"{_BASE}/{request.id}/design",
            json={"doc": {"kind": "tag_sheet", "sheets": []}},
        )

        assert resp.status_code == 409, resp.text
        assert self._page_version_count(db, request.id) == before


# ---------------------------------------------------------------------------
# S11 - PATCH one line's price basis (D5). Written test-FIRST: the route does
# not exist yet, so every call below 404s where it should not, which is the
# accepted "missing route" red.
# ---------------------------------------------------------------------------


class TestLinePricePatch:
    def test_patch_line_promotion_sets_and_clears_pins(self, api):
        """AC-S6-5: the PATCH's own promotion has to cover the line's product,
        same as create/update - covered here after the request exists, since
        the PATCH validates against what the line holds at PATCH time."""
        client, db = api
        request, _contact = _submitted_request(db, lines=1, price_mode="selling")
        line = request.lines[0]
        promotion_id = _promotion(db, "ZZT Line Promo")
        from app.models.product import Product

        product = db.query(Product).filter(Product.id == line.product_id).one()
        _cover_promotion(db, promotion_id, product)
        from app.services.dealer_kit import tag_data_service

        tag_data_service.pin_tags(db, request, only_unpinned=True)
        db.commit()
        tag = line.tags[0]
        old_pin = tag.pinned_tag_data
        assert old_pin is not None, "seed assumption: the tag is pinned"

        res = client.patch(
            f"{_BASE}/{request.id}/lines/{line.id}", json={"promotion_id": promotion_id}
        )
        assert res.status_code == 200, res.text
        body_line = next(l for l in res.json()["lines"] if l["id"] == line.id)
        assert body_line["promotion_id"] == promotion_id

        db.expire_all()
        from app.models.price_tag import PriceTagRequestTag

        refreshed = (
            db.query(PriceTagRequestTag).filter(PriceTagRequestTag.id == tag.id).first()
        )
        # The PATCH itself clears the pin (`pinned_tag_data = None`), but the
        # SAME response-building read (`_with_resolved_lines`, which every
        # caller of this route gets back) goes through
        # `resolve_request_line_data`, whose r9/D16 "pin on the first
        # unpinned read" rule immediately re-pins any tag it finds unpinned -
        # so what is observable from outside is a FRESH pin (the promotion's
        # own change baked in, no ack yet), never a lastingly-absent one.
        assert refreshed.pinned_tag_data is not None
        assert refreshed.pinned_tag_data != old_pin, (
            "the line's own promotion changed, so its tag's pin must be replaced"
        )
        assert refreshed.data_change_ack_hash is None

    def test_patch_line_manual_price(self, api):
        """AC-S6-4: a manual price only applies in Selling mode."""
        client, db = api
        request, _contact = _submitted_request(db, lines=1, price_mode="selling")
        line = request.lines[0]

        res = client.patch(
            f"{_BASE}/{request.id}/lines/{line.id}", json={"manual_sell_price": 888.5}
        )
        assert res.status_code == 200, res.text
        body_line = next(l for l in res.json()["lines"] if l["id"] == line.id)
        # `Decimal` fields serialise as a JSON string, not a float.
        assert body_line["manual_sell_price"] == "888.50"
        assert float(body_line["manual_sell_price"]) == 888.5

    def test_patch_line_409_on_a_terminal_request(self, api):
        client, db = api
        request, _contact = _submitted_request(db, lines=1)
        request.status = "collected"
        db.commit()

        res = client.patch(
            f"{_BASE}/{request.id}/lines/{request.lines[0].id}",
            json={"manual_sell_price": 100},
        )
        assert res.status_code == 409, res.text

    def test_patch_line_403_without_process(self, api):
        client, db = api
        from app.models.user import UserPermission, UserRolePermission

        db.query(UserRolePermission).filter(
            UserRolePermission.permission_id.in_(
                db.query(UserPermission.id).filter(
                    UserPermission.slug == "dealer_kit.price_tag_requests.process"
                )
            )
        ).delete(synchronize_session=False)
        db.commit()
        request, _contact = _submitted_request(db, lines=1)

        res = client.patch(
            f"{_BASE}/{request.id}/lines/{request.lines[0].id}",
            json={"manual_sell_price": 100},
        )
        assert res.status_code == 403, res.text

    def test_patch_line_404_for_a_line_on_another_request(self, api):
        """A 404 has to come from the CROSS-REQUEST check, not from the route
        being absent - proven by first patching request_a's OWN line and
        requiring that to succeed, so a coincidental "every unknown path 404s"
        cannot pass this test for the wrong reason. AC-S6-4: a manual price
        only applies in Selling mode."""
        client, db = api
        request_a, _ = _submitted_request(db, lines=1, price_mode="selling")
        request_b, _ = _submitted_request(db, lines=1, price_mode="selling")

        own_line = client.patch(
            f"{_BASE}/{request_a.id}/lines/{request_a.lines[0].id}",
            json={"manual_sell_price": 100},
        )
        assert own_line.status_code == 200, own_line.text

        res = client.patch(
            f"{_BASE}/{request_a.id}/lines/{request_b.lines[0].id}",
            json={"manual_sell_price": 100},
        )
        assert res.status_code == 404, res.text

    def test_patch_line_404_for_a_malformed_line_id(self, api):
        """R8a: `_line_or_404` filters `PriceTagRequestLine.id == line_id`
        with NO `validate_uuid_path` on `line_id` (unlike `request_id`, which
        the route DOES run through it) - a bad-format id must read as a
        guaranteed-missing row (404), not a Postgres `DataError` (500)."""
        client, db = api
        request, _ = _submitted_request(db, lines=1, price_mode="selling")

        res = client.patch(
            f"{_BASE}/{request.id}/lines/not-a-uuid",
            json={"manual_sell_price": 100},
        )
        assert res.status_code == 404, res.text

    def test_patch_line_manual_price_rejects_out_of_bounds_values(self, api):
        """R6: `manual_sell_price` has no `Field` bound at all - -5 and 0 are
        valid `Decimal`s pydantic happily accepts, and `1E+400` is a valid
        (if absurd) arbitrary-precision `Decimal` too, so all three save
        as-is today with no 422. 175.50 stays accepted (the existing
        `test_patch_line_manual_price` already covers that at 888.5)."""
        client, db = api
        request, _ = _submitted_request(db, lines=1, price_mode="selling")
        line_id = request.lines[0].id

        for bad in (-5, 0, "1E+400"):
            res = client.patch(
                f"{_BASE}/{request.id}/lines/{line_id}",
                json={"manual_sell_price": bad},
            )
            assert res.status_code == 422, (bad, res.text)


@pytest.fixture(autouse=True)
def no_respond(monkeypatch):
    """S8: no test run reaches api.respond.io. See `_ptag_r9_seed.block_respond`.

    Every transition here goes through the real notifier, which sends over the
    network unless something stops it - the run log used to carry a live
    ``Window check: Respond.io list_messages failed`` per transition.
    """
    return _ptag_r9_seed.block_respond(monkeypatch)
