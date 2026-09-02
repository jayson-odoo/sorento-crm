"""The portal's price tag routes, through the app rather than the service (D49).

The service-level suite in ``test_price_tag_request.py`` was green while every
write path was dead, because the app mounts ``portal.router`` and
``portal_price_tag.router`` under the same ``/portal`` prefix and Starlette serves
the FIRST route whose path matches. ``POST /submissions/{kind}`` in the generic
portal module matched ``POST /submissions/price_tag_request``, ``price_tag_request``
is in ``SUPPORTED_TYPES`` so the kind check waved it through, and the salesperson
got a 422 about ``body.fields`` - a key belonging to a different form's schema.

So these tests go through ``TestClient``: mounting order is not something a
service call can prove.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves the circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402
from tests._pg_fixture import blank_session, unique_code

_BASE = "/api/v1/public/portal/submissions/price_tag_request"
_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def _seed_contact_who_can_see_the_form(db: Session) -> str:
    """A contact whose access type grants ``price_tag_request``."""
    from app.models.access import (
        ContactAccessType,
        RespondContact,
        respond_contact_access_types,
    )

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
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
            contact_id=contact.id,
            access_type_code=access_type.code,
        )
    )
    db.flush()
    return contact.id


def _seed_product(db: Session, *, class_label: str = "Kitchen Sink") -> str:
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("cat"),
        category_name=unique_code("Category"),
        class_label=class_label,
    )
    brand = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code("br"),
        brand_name=unique_code("Brand"),
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("uom"), uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("prod"),
        product_name=unique_code("Product"),
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=100.00,
    )
    db.add(product)
    db.flush()
    return product.id


@pytest.fixture
def client():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    with blank_session() as db:
        contact_id = _seed_contact_who_can_see_the_form(db)

        def _override_get_db():
            yield db

        def _override_portal_token():
            # Never added to the session: the routes read contact_id off it and
            # nothing persists it.
            return PortalToken(
                id=str(uuid.uuid4()),
                contact_id=contact_id,
                space_id="zzt-space",
            )

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = _override_portal_token
        try:
            # The header is what the company-scope resolver reads to give a portal
            # request the incumbent company. Without it every owned-table READ is
            # fail-closed and a request that was just created comes back 404.
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                yield c, db, contact_id
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# The shadowing regression
# ---------------------------------------------------------------------------


class TestTheRouteThatServesTheRequest:
    def test_create_reaches_the_price_tag_route(self, client):
        """The payload the form actually posts, with no ``fields`` key in sight."""
        c, db, _ = client
        product_id = _seed_product(db)

        res = c.post(
            _BASE,
            json={
                "debtor_code": "ZZT-D1",
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "notes": "ZZT",
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": product_id,
                        "quantity": 2,
                    }
                ],
            },
        )

        assert res.status_code == 201, res.text
        body = res.json()
        assert body["doc_number"].startswith("PT-")
        assert body["portal_draft_at"] is not None
        assert len(body["lines"]) == 1

    def test_a_draft_needs_neither_a_debtor_nor_a_date(self, client):
        """D48a: the only requirement is that there is something to save."""
        c, db, _ = client
        product_id = _seed_product(db)

        res = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        )

        assert res.status_code == 201, res.text
        body = res.json()
        assert body["debtor_name"] is None
        assert body["needed_by_date"] is None

    def test_the_detail_route_answers_with_the_lines_resolved(self, client):
        """Reopening a draft: the row stores an id, the form needs a code and a name."""
        c, db, _ = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        res = c.get(f"{_BASE}/{created['id']}")

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["id"] == created["id"]
        assert body["lines"][0]["code"]
        assert body["lines"][0]["name"]
        # The portal form reads this unconditionally.
        assert body["attachments"] == []

    def test_the_detail_route_hides_another_contacts_request(self, client):
        c, db, _ = client
        from app.services.price_tag_request_service import PriceTagRequestService

        other = _seed_contact_who_can_see_the_form(db)
        theirs = PriceTagRequestService.create_request(
            db,
            contact_id=other,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "ZZT Theirs"},
        )
        db.flush()

        assert c.get(f"{_BASE}/{theirs.id}").status_code == 404

    def test_update_keeps_the_draft_and_replaces_its_lines(self, client):
        c, db, _ = client
        first = _seed_product(db)
        second = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": first}]},
        ).json()

        res = c.put(
            f"{_BASE}/{created['id']}",
            json={
                "debtor_name": "ZZT Filled In Later",
                "lines": [{"line_type": "product", "product_id": second, "quantity": 4}],
            },
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["id"] == created["id"]
        assert body["debtor_name"] == "ZZT Filled In Later"
        assert len(body["lines"]) == 1
        assert body["lines"][0]["product_id"] == second
        assert body["lines"][0]["quantity"] == 4

    def test_lines_keep_the_order_they_were_posted_in(self, client):
        """The row a refusal names (`line:<index>`) must be the row on screen.

        The form posts the table in order and sends no `sort_order`; a schema
        default of 0 gave every line the same one and the order came back at
        Postgres's discretion.
        """
        c, db, _ = client
        first = _seed_product(db)
        second = _seed_product(db)
        third = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "lines": [
                    {"line_type": "product", "product_id": first},
                    {"line_type": "product", "product_id": second},
                    {"line_type": "product", "product_id": third},
                ]
            },
        ).json()

        body = c.get(f"{_BASE}/{created['id']}").json()

        assert [l["product_id"] for l in body["lines"]] == [first, second, third]
        assert [l["sort_order"] for l in body["lines"]] == [0, 1, 2]

    def test_a_draft_can_be_deleted(self, client):
        c, db, _ = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        assert c.delete(f"{_BASE}/{created['id']}").status_code == 204
        assert c.get(f"{_BASE}/{created['id']}").status_code == 404


# ---------------------------------------------------------------------------
# Submit is where completeness is enforced (D48a / D48b)
# ---------------------------------------------------------------------------


class TestSubmitRefusals:
    def test_submit_refuses_an_empty_draft_and_names_every_field(self, client):
        c, _db, _ = client
        created = c.post(_BASE, json={"notes": "ZZT nothing else"}).json()

        res = c.post(f"{_BASE}/{created['id']}/submit")

        assert res.status_code == 422, res.text
        body = res.json()
        assert body["code"] == "SUBMIT_INCOMPLETE"
        assert body["detail"] == "debtor_name,needed_by_date,lines"

    def test_submit_refuses_an_ala_carte_bathroom_furniture_line_by_row(self, client):
        c, db, _ = client
        ok_product = _seed_product(db)
        bad_product = _seed_product(db, class_label="Bathroom Furniture")
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "lines": [
                    {"line_type": "product", "product_id": ok_product},
                    {"line_type": "product", "product_id": bad_product},
                ],
            },
        ).json()

        res = c.post(f"{_BASE}/{created['id']}/submit")

        assert res.status_code == 422, res.text
        body = res.json()
        assert body["code"] == "SET_GUARD_VIOLATION"
        assert body["detail"] == "line:1"

    def test_a_complete_request_submits(self, client):
        c, db, _ = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "lines": [{"line_type": "product", "product_id": product_id}],
            },
        ).json()

        res = c.post(f"{_BASE}/{created['id']}/submit")

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["portal_draft_at"] is None
        assert body["status"] == "new"

    def test_a_request_cannot_be_submitted_twice(self, client):
        """The second submit would fire the form SLA again."""
        c, db, _ = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "lines": [{"line_type": "product", "product_id": product_id}],
            },
        ).json()
        assert c.post(f"{_BASE}/{created['id']}/submit").status_code == 200

        res = c.post(f"{_BASE}/{created['id']}/submit")

        assert res.status_code == 409
        assert res.json()["code"] == "ALREADY_SUBMITTED"

    def test_a_submitted_request_cannot_be_deleted(self, client):
        """Delete is a draft affordance. A submitted request is marketing's work."""
        c, db, _ = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "lines": [{"line_type": "product", "product_id": product_id}],
            },
        ).json()
        c.post(f"{_BASE}/{created['id']}/submit")

        assert c.delete(f"{_BASE}/{created['id']}").status_code == 409


# ---------------------------------------------------------------------------
# The grant gates every route, lookups included
# ---------------------------------------------------------------------------


def _revoke_the_grant(db: Session, contact_id: str) -> None:
    """Take ``price_tag_request`` off every access type this contact holds."""
    from app.models.access import ContactAccessType, respond_contact_access_types

    codes = [
        row.access_type_code
        for row in db.execute(
            respond_contact_access_types.select().where(
                respond_contact_access_types.c.contact_id == contact_id
            )
        )
    ]
    db.query(ContactAccessType).filter(ContactAccessType.code.in_(codes)).update(
        {"portal_form_types": []}, synchronize_session=False
    )
    db.flush()


class TestTheGenericPortalDoesNotServeThisKind:
    """Two different questions were being answered by one tuple.

    ``SUPPORTED_TYPES`` says which kinds the GENERIC portal machinery serves -
    the submission CRUD, the neighbours, the revision policy rows. A price tag
    request is served by none of them: it has its own routes, its own service
    and no revision policy at all. Adding it to that tuple made the generic
    listing answer ``200 []`` instead of refusing, offered a revision-config row
    that configures nothing, and left the router include ORDER load-bearing -
    the only thing keeping the generic handler off the real price tag writes.

    Being GRANTABLE on an access type is the other question, and it has its own
    tuple now.
    """

    def test_the_generic_listing_refuses_the_kind(self, client):
        c, _db, _contact_id = client

        res = c.get(
            "/api/v1/public/portal/submissions",
            params={"type": "price_tag_request"},
        )

        assert res.status_code == 400, res.text
        assert "price_tag_request" in res.text

    def test_the_generic_neighbours_route_refuses_the_kind(self, client):
        c, _db, _contact_id = client

        res = c.get(
            f"/api/v1/public/portal/submissions/price_tag_request/{uuid.uuid4()}/neighbours"
        )

        assert res.status_code == 400, res.text
        assert "Unsupported submission type" in res.text

    def test_the_kind_is_still_grantable_on_an_access_type(self):
        """The grant schema asks the OTHER question and must still say yes."""
        from app.schemas.user import ContactAccessTypeUpdate

        updated = ContactAccessTypeUpdate(
            code="zzt-dealer",
            name="ZZT Dealer",
            portal_form_types=["stock_inquiry", "price_tag_request"],
        )

        assert "price_tag_request" in (updated.portal_form_types or [])

    def test_an_unknown_kind_is_still_refused_by_the_grant_schema(self):
        from pydantic import ValidationError

        from app.schemas.user import ContactAccessTypeUpdate

        with pytest.raises(ValidationError):
            ContactAccessTypeUpdate(
                code="zzt-dealer",
                name="ZZT Dealer",
                portal_form_types=["not_a_form"],
            )


class TestTheListTheSalespersonReads:
    def test_a_row_carries_the_line_count_the_card_prints(self, client):
        """The portal card prints "N lines" and N was ``undefined``.

        ``PriceTagRequestListItem`` never declared ``line_count``, so the field
        was dropped on the way out and the card rendered nothing where the count
        belongs.
        """
        c, db, _contact_id = client
        product_id = _seed_product(db)
        c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "lines": [{"line_type": "product", "product_id": product_id}],
            },
        )

        rows = c.get(_BASE).json()["items"]

        assert len(rows) == 1
        assert rows[0]["line_count"] == 1


class TestTheGrantGatesEveryRoute:
    def test_the_debtor_lookup_refuses_a_contact_without_the_grant(self, client):
        """A revoked contact cannot enumerate their agent's debtor book.

        This was the one route of the ten that never called ``_assert_visible``,
        so the customer names, the customer codes and who buys from whom stayed
        readable with the form itself switched off.
        """
        c, db, contact_id = client
        _revoke_the_grant(db, contact_id)

        res = c.get("/api/v1/public/portal/lookups/debtors-for-agent")

        assert res.status_code == 403, res.text
        assert res.json()["code"] == "FORM_TYPE_NOT_VISIBLE"

    def test_the_item_lookup_beside_it_refuses_the_same_way(self, client):
        """The control: its sibling lookup was already gated."""
        c, db, contact_id = client
        _revoke_the_grant(db, contact_id)

        res = c.get("/api/v1/public/portal/lookups/price-tag-items")

        assert res.status_code == 403, res.text
        assert res.json()["code"] == "FORM_TYPE_NOT_VISIBLE"

    def test_the_debtor_lookup_still_answers_a_granted_contact(self, client):
        """And the gate does not cost the contact who IS granted the form."""
        c, _db, _contact_id = client

        res = c.get("/api/v1/public/portal/lookups/debtors-for-agent")

        assert res.status_code == 200, res.text
        assert isinstance(res.json(), list)


# ---------------------------------------------------------------------------
# Download the latest completed tag sheet PDF (PLAN-price-tag-feedback-r2 S2)
# ---------------------------------------------------------------------------


def _seed_completed_export(
    db: Session,
    request_id: str,
    *,
    filename: str = "ZZT-tags-v1.pdf",
    offset_seconds: int = 0,
) -> str:
    """A READY ``user_downloads`` row for ``request_id``, storage key returned.

    Directly seeded rather than driven through ``request_tag_sheet_export`` +
    the RQ render task: the render leg needs a live worker and a rendered
    catalogue page, neither of which this suite stands up. What the route under
    test reads is the finished row - status, kind, source pointer, storage key -
    so seeding that row directly proves the same contract.

    ``created_at`` is set explicitly rather than left to the column's
    ``server_default=func.now()``: within one transaction Postgres's `now()` is
    the transaction start time, constant for every statement in it, so two rows
    seeded back to back in the same test transaction would tie on it. A real
    export never has this problem (each export is its own request/transaction);
    only stacking two of them inside one test does.
    """
    from app.models.download import DownloadStatus, UserDownload
    from app.services.dealer_kit.tag_sheet_export_service import KIND

    key = f"zzt/{uuid.uuid4()}.pdf"
    download = UserDownload(
        id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),  # the marketing staffer who exported it
        kind=KIND,
        source_entity_type="price_tag_request",
        source_entity_id=request_id,
        status=DownloadStatus.READY.value,
        filename=filename,
        storage_provider="s3",
        storage_key=key,
        created_at=datetime.utcnow() + timedelta(seconds=offset_seconds),
    )
    db.add(download)
    db.flush()
    return key


class TestTheDownloadRoute:
    def test_the_detail_route_says_whether_a_completed_export_exists(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()
        assert created["has_completed_export"] is False

        _seed_completed_export(db, created["id"])

        body = c.get(f"{_BASE}/{created['id']}").json()
        assert body["has_completed_export"] is True

    def test_the_owner_streams_the_latest_completed_export(self, client, monkeypatch):
        c, db, _contact_id = client
        from app.api.v1.public import portal_price_tag
        from tests._fake_storage import FakeStorage

        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        storage = FakeStorage()
        monkeypatch.setattr(portal_price_tag, "get_backend", lambda provider: storage)
        key = _seed_completed_export(db, created["id"], filename="ZZT-tags-v1.pdf")
        storage.objects[key] = (b"%PDF-1.4 zzt bytes", "application/pdf")

        res = c.get(f"{_BASE}/{created['id']}/download")

        assert res.status_code == 200, res.text
        assert res.content == b"%PDF-1.4 zzt bytes"
        assert "ZZT-tags-v1.pdf" in res.headers["content-disposition"]

    def test_a_second_later_export_wins_over_the_first(self, client, monkeypatch):
        """"Latest completed" - a re-export after a proof revision must win."""
        c, db, _contact_id = client
        from app.api.v1.public import portal_price_tag
        from tests._fake_storage import FakeStorage

        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        storage = FakeStorage()
        monkeypatch.setattr(portal_price_tag, "get_backend", lambda provider: storage)
        first_key = _seed_completed_export(
            db, created["id"], filename="v1.pdf", offset_seconds=0
        )
        storage.objects[first_key] = (b"v1 bytes", "application/pdf")
        second_key = _seed_completed_export(
            db, created["id"], filename="v2.pdf", offset_seconds=5
        )
        storage.objects[second_key] = (b"v2 bytes", "application/pdf")

        res = c.get(f"{_BASE}/{created['id']}/download")

        assert res.status_code == 200, res.text
        assert res.content == b"v2 bytes"

    def test_no_completed_export_refuses_with_404(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        res = c.get(f"{_BASE}/{created['id']}/download")

        assert res.status_code == 404, res.text

    def test_a_foreign_token_gets_404_not_found_no_existence_oracle(self, client):
        """Ownership fails BEFORE the export lookup runs, so a foreign token
        gets ``_require_own_request``'s message ("Price tag request not
        found.") rather than anything about the export - it never learns one
        exists. That message differs from the "no export yet" 404 an owner
        gets (asserted below); what neither one leaks is whether the OTHER
        fact is true.
        """
        c, db, _contact_id = client
        from app.services.price_tag_request_service import PriceTagRequestService

        other = _seed_contact_who_can_see_the_form(db)
        theirs = PriceTagRequestService.create_request(
            db,
            contact_id=other,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "ZZT Theirs"},
        )
        db.flush()
        _seed_completed_export(db, theirs.id)

        res = c.get(f"{_BASE}/{theirs.id}/download")

        assert res.status_code == 404, res.text
        assert res.json()["message"] == "Price tag request not found."

    def test_visibility_revoked_refuses_before_looking_for_an_export(self, client):
        c, db, contact_id = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()
        _seed_completed_export(db, created["id"])
        _revoke_the_grant(db, contact_id)

        res = c.get(f"{_BASE}/{created['id']}/download")

        assert res.status_code == 403, res.text
        assert res.json()["code"] == "FORM_TYPE_NOT_VISIBLE"

    def test_a_storage_outage_answers_502_not_a_relabeled_404(self, client, monkeypatch):
        """Mirrors ``portal_download_attachment``: a bucket that refuses is a
        502 the caller can retry, not a 404 that reads like the file was
        deleted."""
        c, db, _contact_id = client
        from app.api.v1.public import portal_price_tag
        from tests._fake_storage import FakeStorage

        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        storage = FakeStorage()
        storage.downloading_fails = True
        monkeypatch.setattr(portal_price_tag, "get_backend", lambda provider: storage)
        _seed_completed_export(db, created["id"])

        res = c.get(f"{_BASE}/{created['id']}/download")

        assert res.status_code == 502, res.text


# ---------------------------------------------------------------------------
# A malformed id must 404, never 500 (uuid_path_param gap)
# ---------------------------------------------------------------------------


class TestMalformedRequestId:
    """A non-UUID ``{request_id}`` used to reach the service layer, whose
    ``get_request`` would either raise a raw DB error or simply find nothing
    the hard way. Either path is a client-visible 500 for what is, from the
    caller's side, a guaranteed-missing row - the same thing a well-formed but
    absent id already answers with a clean 404."""

    _BAD_ID = "not-a-uuid"

    def test_the_detail_route_404s_on_a_malformed_id(self, client):
        c, _db, _contact_id = client

        res = c.get(f"{_BASE}/{self._BAD_ID}")

        assert res.status_code == 404, res.text

    def test_the_download_route_404s_on_a_malformed_id(self, client):
        c, _db, _contact_id = client

        res = c.get(f"{_BASE}/{self._BAD_ID}/download")

        assert res.status_code == 404, res.text

    def test_the_update_route_404s_on_a_malformed_id(self, client):
        c, _db, _contact_id = client

        res = c.put(f"{_BASE}/{self._BAD_ID}", json={"debtor_name": "ZZT"})

        assert res.status_code == 404, res.text

    def test_the_submit_route_404s_on_a_malformed_id(self, client):
        c, _db, _contact_id = client

        res = c.post(f"{_BASE}/{self._BAD_ID}/submit")

        assert res.status_code == 404, res.text
