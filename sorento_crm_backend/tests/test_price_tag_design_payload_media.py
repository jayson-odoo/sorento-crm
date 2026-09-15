"""r9 S1/D1: both design endpoints answer the PRINT payload (AC-S1-1, AC-S1-1b).

The portal preview and the CRM detail preview drew the same document the PDF
draws, but without the three media maps the PDF gets - so every image layer
painted a grey box and every brand face fell back to a system sans. The fix is
not "add three fields": it is that ONE resolver answers all three readers, so a
proof, a preview and a print can never disagree again.

These tests therefore do not merely assert the keys are present. They compute
the print payload for the SAME page, through
``tag_sheet_export_service._resolved_payload``, and assert the endpoint's
``assets`` / ``images`` / ``fonts`` equal it value for value. A hand-rolled
second resolver in the route would satisfy "the key exists" and fail this.

Red before the coder starts because ``PortalTagSheetDesignResponse`` and
``TagSheetDocResponse`` declare none of the three, and ``response_model``
drops an undeclared field without a word (LESSONS).
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

_PORTAL = "/api/v1/public/portal/submissions/price_tag_request/{id}/design"
_CRM_BASE = "/api/v1/dealer-kit/price-tag-requests/{id}"
_CRM = _CRM_BASE + "/design"

MEDIA_KEYS = ("assets", "images", "fonts")


@pytest.fixture(autouse=True)
def no_respond(monkeypatch):
    """S8: no test run reaches api.respond.io. See `_ptag_r9_seed.block_respond`."""
    return seed.block_respond(monkeypatch)



def _sign(path, **_kwargs):
    return f"https://signed.example.test/{path.rsplit('/', 1)[-1]}"


@pytest.fixture(autouse=True)
def signable_assets(monkeypatch):
    """Sign every stored path deterministically.

    The real signer talks to S3/R2 and returns None in a test process (locally
    it cannot even find the CloudFront private key), which would leave
    ``assets`` and ``images`` empty for a reason that has nothing to do with the
    route. BOTH names have to be patched: library artwork signs through
    ``asset_service`` and product photos through ``product_images``, and each
    module imported the function by name, so patching one leaves the other real.
    """
    monkeypatch.setattr(
        "app.services.dealer_kit.asset_service.resolve_signed_url", _sign
    )
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url", _sign
    )


def _print_payload(db, request, page, doc, version: int) -> dict:
    """What the PDF route resolves for this page. The comparison baseline."""
    from app.services.dealer_kit import tag_sheet_export_service

    return tag_sheet_export_service._resolved_payload(
        db,
        {
            "page_id": page.id,
            "version_id": None,
            "version": version,
            "doc": doc,
            "request": request,
            "page": page,
        },
    )


# ---------------------------------------------------------------------------
# AC-S1-1 - the portal half
# ---------------------------------------------------------------------------


@pytest.fixture
def portal():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    with blank_session() as db:
        contact_id = seed.seed_portal_contact(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = lambda: PortalToken(
            id=str(uuid.uuid4()), contact_id=contact_id, space_id="zzt-space"
        )
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as client:
                yield client, db, contact_id
        finally:
            app.dependency_overrides.clear()


class TestPortalDesignPayloadCarriesItsMedia:
    def test_a_proof_ready_design_answers_assets_images_and_fonts(self, portal):
        """AC-S1-1: the three keys exist and are the PRINT payload's own."""
        client, db, contact_id = portal
        artwork = seed.seed_asset(db, kind="decorative")
        seed.seed_asset(db, kind="font")
        product = seed.seed_product(db)
        seed.seed_product_photo(db, product)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )
        page, doc = seed.attach_design(db, request, asset_id=artwork.id)

        response = client.get(_PORTAL.format(id=request.id))

        assert response.status_code == 200, response.text
        body = response.json()
        for key in MEDIA_KEYS:
            assert key in body, f"the portal design payload is missing {key!r}"

        expected = _print_payload(db, request, page, doc, 1)
        assert body["assets"] == expected["assets"]
        assert body["images"] == expected["images"]
        assert body["fonts"] == expected["fonts"]

    def test_every_asset_the_document_names_is_signed(self, portal):
        """The grey box the owner saw: an image layer's asset had no URL."""
        client, db, contact_id = portal
        artwork = seed.seed_asset(db, kind="decorative")
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )
        seed.attach_design(db, request, asset_id=artwork.id)

        body = client.get(_PORTAL.format(id=request.id)).json()

        assert artwork.id in body["assets"], body.get("assets")
        assert body["assets"][artwork.id].startswith("https://signed.example.test/")

    def test_every_product_photo_on_the_lines_is_in_the_image_map(self, portal):
        client, db, contact_id = portal
        product = seed.seed_product(db)
        photo = seed.seed_product_photo(db, product)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )
        seed.attach_design(db, request)

        body = client.get(_PORTAL.format(id=request.id)).json()

        assert photo.id in body["images"], body.get("images")

    def test_the_brand_fonts_travel_with_the_design(self, portal):
        client, db, contact_id = portal
        font = seed.seed_asset(db, kind="font")
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )
        seed.attach_design(db, request)

        body = client.get(_PORTAL.format(id=request.id)).json()

        families = [row["family"] for row in body["fonts"]]
        assert font.name in families, body.get("fonts")
        assert all(
            row["url"].startswith("/api/v1/public/dealer-kit/fonts/")
            for row in body["fonts"]
        ), "a signed CDN font URL has no CORS header and never loads"

    def test_a_page_with_no_saved_version_404s_rather_than_leaking_the_draft(
        self, portal
    ):
        """The portal reads ``prefer="version"``: a draft-only page has nothing
        the salesperson was ever meant to see."""
        client, db, contact_id = portal
        from app.models.dealer_kit import Page, PageVersion

        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )
        page, doc = seed.attach_design(db, request)
        db.query(PageVersion).filter(PageVersion.page_id == page.id).delete()
        db.query(Page).filter(Page.id == page.id).update({"draft_doc": doc})
        db.commit()

        response = client.get(_PORTAL.format(id=request.id))

        assert response.status_code == 404, response.text

    def test_a_designing_request_still_404s(self, portal):
        """AC-S1-1: adding media must not widen the status gate."""
        client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product]
        )
        seed.attach_design(db, request)

        assert client.get(_PORTAL.format(id=request.id)).status_code == 404


# ---------------------------------------------------------------------------
# AC-S1-1b - the CRM half, same shape, draft first
# ---------------------------------------------------------------------------


@pytest.fixture
def crm():
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        seed.seed_marketer(db)

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({seed.SORENTO})
            set_company_scope(db, scope)
            return scope

        principal = {"id": seed.MARKETER_ID, "email": "zzt-ptag-r9-marketer@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()


class TestCrmDesignPayloadCarriesTheSameMedia:
    def test_the_processor_gets_lines_assets_images_and_fonts(self, crm):
        """AC-S1-1b: the CRM Design section makes ONE call.

        Before r9 it fetched the doc here and the artwork from the asset
        library route, which is gated on ``dealer_kit.library.manage`` - a
        permission marketing does not hold, so the section drew grey boxes for
        the one role that needs it most (Phase 1 finding, 14 Sep).
        """
        client, db = crm
        artwork = seed.seed_asset(db, kind="decorative")
        seed.seed_asset(db, kind="font")
        product = seed.seed_product(db)
        seed.seed_product_photo(db, product)
        contact_id = seed.seed_portal_contact(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product]
        )
        page, doc = seed.attach_design(db, request, asset_id=artwork.id)

        response = client.get(_CRM.format(id=request.id))

        assert response.status_code == 200, response.text
        body = response.json()
        for key in ("page_id", "version", "source", "doc", "lines", *MEDIA_KEYS):
            assert key in body, f"the CRM design payload is missing {key!r}"

        expected = _print_payload(db, request, page, doc, 1)
        assert body["assets"] == expected["assets"]
        assert body["images"] == expected["images"]
        assert body["fonts"] == expected["fonts"]
        assert [line["code"] for line in body["lines"]] == [product.product_code]

    def test_it_is_draft_first_so_the_office_sees_its_own_work(self, crm):
        client, db = crm
        from app.models.dealer_kit import Page

        product = seed.seed_product(db)
        contact_id = seed.seed_portal_contact(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product]
        )
        page, doc = seed.attach_design(db, request)
        draft = {**doc, "sheets": [{"id": "zzt-draft-sheet", "tags": []}]}
        db.query(Page).filter(Page.id == page.id).update({"draft_doc": draft})
        db.commit()

        body = client.get(_CRM.format(id=request.id)).json()

        assert body["source"] == "draft"
        assert body["doc"]["sheets"][0]["id"] == "zzt-draft-sheet"

    def test_a_request_with_no_page_404s(self, crm):
        client, db = crm
        product = seed.seed_product(db)
        contact_id = seed.seed_portal_contact(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product]
        )

        assert client.get(_CRM.format(id=request.id)).status_code == 404


# ---------------------------------------------------------------------------
# S10 - the diff travels WITH the line, on every payload that carries lines
# ---------------------------------------------------------------------------


class TestDataChangesReachEveryPayload:
    """`lib/dealer-kit/product-data-changes.ts` says every resolver read of a
    non-terminal request carries `data_changes` per line, and that is how the
    portal preview and the designer know a line is waiting on a decision
    without asking a second time.

    `ResolvedLineData` does not declare the field, and `response_model` drops
    an undeclared key without a word (LESSONS) - so the resolver computes the
    diff, the route serialises it away, and every reader sees a request with
    nothing pending on it.
    """

    def _designing_request_with_a_changed_product(self, db, contact_id):
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        product = seed.seed_product(db, list_price=1000.00)
        request = seed.seed_request(
            db,
            contact_id,
            status="new",
            products=[product],
            print_by="office",
            assigned_to_id=seed.MARKETER_ID,
        )
        PriceTagRequestService.transition_status(
            db, request.id, "designing", user_id=seed.MARKETER_ID
        )
        db.commit()
        seed.attach_design(db, request)
        product.list_price = 1200.00
        db.commit()
        db.expire_all()
        return db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()

    def test_the_crm_design_payload_carries_it(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request = self._designing_request_with_a_changed_product(db, contact_id)

        body = client.get(_CRM.format(id=request.id)).json()

        line = body["lines"][0]
        assert "data_changes" in line, line
        assert [change["field"] for change in line["data_changes"]] == ["list_price"]

    def test_resolve_prices_carries_it(self, crm):
        """The designer's own call, and the one the LINES rail reads."""
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request = self._designing_request_with_a_changed_product(db, contact_id)

        response = client.post(f"{_CRM_BASE.format(id=request.id)}/resolve-prices")

        assert response.status_code == 200, response.text
        line = response.json()[0]
        assert "data_changes" in line, line
        assert [change["field"] for change in line["data_changes"]] == ["list_price"]

    def test_the_portal_design_payload_carries_it(self, portal):
        """The salesperson's preview draws the PIN, so it has to be able to say
        that the pin is not what master data says any more."""
        from app.models.price_tag import PriceTagRequest

        client, db, contact_id = portal
        seed.seed_marketer(db)
        request = self._designing_request_with_a_changed_product(db, contact_id)
        db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).update(
            {"status": "proof_ready"}
        )
        db.commit()

        body = client.get(_PORTAL.format(id=request.id)).json()

        line = body["lines"][0]
        assert "data_changes" in line, line

    def test_a_terminal_request_carries_no_key_at_all(self, crm):
        """The contract is explicit: a terminal request never carries it,
        because there is nothing to decide and the live resolve does not run."""
        from app.models.price_tag import PriceTagRequest

        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request = self._designing_request_with_a_changed_product(db, contact_id)
        db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).update(
            {"status": "collected"}
        )
        db.commit()

        body = client.get(_CRM.format(id=request.id)).json()

        assert "data_changes" not in body["lines"][0]


# ---------------------------------------------------------------------------
# R9 (Phase 3 review) - `design_media`'s `images` map only walks each row's
# own HOST images (`row["images"]`), never `row["parts"][*]["images"]` - a
# layer bound to a PART's photo (D7: "a layer may pick ANY part as its
# subject") has no signed URL in the export payload at all.
# ---------------------------------------------------------------------------


def test_every_part_photo_is_in_the_image_map_too():
    """R9: a part's own photo must reach `images` the same way the host's
    does - `design_media` unit-tested directly (service level), since the
    gap is in the map builder itself, not any one route."""
    from app.models.product_combo import ProductCombo, ProductComboPart
    from app.services.dealer_kit.tag_sheet_export_service import design_media
    from app.services.price_tag_request_service import PriceTagRequestService

    with blank_session() as db:
        contact_id = seed.seed_portal_contact(db)
        cabinet = seed.seed_product(db)
        mirror = seed.seed_product(db)
        mirror_photo = seed.seed_product_photo(db, mirror)

        combo = ProductCombo(
            id=str(uuid.uuid4()), host_product_id=cabinet.id, name="2 pc", sort_order=0
        )
        db.add(combo)
        db.flush()
        db.add(
            ProductComboPart(
                id=str(uuid.uuid4()),
                combo_id=combo.id,
                part_product_id=mirror.id,
                choice_group=None,
                sort_order=0,
            )
        )
        db.flush()

        request = PriceTagRequestService.create_request(
            db,
            contact_id=contact_id,
            company_id=seed.SORENTO,
            data={
                "debtor_name": "ZZT Dealer",
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": cabinet.id,
                        "combo_id": combo.id,
                        "parts": [{"product_id": mirror.id}],
                    }
                ],
            },
        )
        db.flush()

        _rows, media = design_media(db, request, doc={})

    assert mirror_photo.id in media["images"], media["images"]
