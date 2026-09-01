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
from datetime import date, timedelta

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
# The promotions lookup (S4, #477)
# ---------------------------------------------------------------------------


def _seed_promotion(
    db: Session,
    *,
    description: str = "ZZT Promo",
    is_active: bool = True,
    start_date: date | None = None,
    end_date: date | None = None,
    access_levels: list[str] | None = None,
) -> str:
    from app.models.marketing import Promotion

    kwargs = {}
    if access_levels is not None:
        kwargs["access_levels"] = access_levels
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        is_active=is_active,
        start_date=start_date,
        end_date=end_date,
        **kwargs,
    )
    db.add(promo)
    db.flush()
    return promo.id


def _grant_promotion_audience_code(db: Session, contact_id: str, code: str = "dealer") -> None:
    """Adds ONE more access code to the contact seeded by ``client``.

    The audience gate on this lookup reads a DIFFERENT code than the
    form-visibility grant ``_seed_contact_who_can_see_the_form`` already set
    up - a contact who may see the form is not automatically an audience a
    promotion is priced for, so a test that asserts a promotion IS returned
    needs its own grant of a code that matches ``Promotion.access_levels``.
    """
    from app.models.access import ContactAccessType, respond_contact_access_types

    if db.query(ContactAccessType).filter(ContactAccessType.code == code).first() is None:
        db.add(ContactAccessType(code=code, name=code))
        db.flush()
    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact_id, access_type_code=code
        )
    )
    db.flush()


class TestThePromotionsLookup:
    """``GET /portal/lookups/promotions`` - active-window, audience-gated promotions.

    The active-window half mirrors ``resolve_prices``' ``_offer_prices``:
    ``is_active`` plus an inclusive ``[start_date, end_date]`` window with
    either end open. Company scoping is the ordinary ORM scope filter the
    portal's ``X-Portal-Token`` header primes.

    The audience half mirrors ``pricing._may_see_offer``'s intersection rule -
    a promotion reaches only the contacts whose access codes overlap its
    ``access_levels``, and an empty ``access_levels`` reaches nobody. A first
    cut of this endpoint shipped without that gate, so every contact's
    dropdown carried every other audience's promotions too.
    """

    def test_an_active_promotion_is_returned(self, client):
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        promo_id = _seed_promotion(db, description="ZZT Spring Sale")

        res = c.get("/api/v1/public/portal/lookups/promotions")

        assert res.status_code == 200, res.text
        rows = res.json()
        assert {"id": promo_id, "name": "ZZT Spring Sale"} in rows

    def test_an_expired_promotion_is_excluded(self, client):
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        _seed_promotion(
            db, description="ZZT Last Year", end_date=date.today() - timedelta(days=1)
        )

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert not any(r["name"] == "ZZT Last Year" for r in rows)

    def test_a_not_yet_started_promotion_is_excluded(self, client):
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        _seed_promotion(
            db, description="ZZT Not Yet", start_date=date.today() + timedelta(days=7)
        )

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert not any(r["name"] == "ZZT Not Yet" for r in rows)

    def test_a_switched_off_promotion_is_excluded(self, client):
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        _seed_promotion(db, description="ZZT Switched Off", is_active=False)

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert not any(r["name"] == "ZZT Switched Off" for r in rows)

    def test_q_filters_by_name(self, client):
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        _seed_promotion(db, description="ZZT Kitchen Bash")
        _seed_promotion(db, description="ZZT Bathroom Blitz")

        rows = c.get(
            "/api/v1/public/portal/lookups/promotions", params={"q": "kitchen"}
        ).json()

        names = {r["name"] for r in rows}
        assert "ZZT Kitchen Bash" in names
        assert "ZZT Bathroom Blitz" not in names

    def test_the_end_date_is_included(self, client):
        """The window is inclusive at both ends, same as `_offer_prices`."""
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        from app.services.dealer_kit.pricing import business_today

        _seed_promotion(
            db,
            description="ZZT Last Day",
            start_date=business_today() - timedelta(days=7),
            end_date=business_today(),
        )

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert any(r["name"] == "ZZT Last Day" for r in rows)

    def test_the_start_date_is_included(self, client):
        """The window is inclusive at both ends, same as `_offer_prices`."""
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id)
        from app.services.dealer_kit.pricing import business_today

        _seed_promotion(
            db,
            description="ZZT First Day",
            start_date=business_today(),
            end_date=business_today() + timedelta(days=7),
        )

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert any(r["name"] == "ZZT First Day" for r in rows)

    def test_a_promotion_for_another_audience_is_hidden(self, client):
        """A dealer-coded contact does not see a mocha_dealer-only promotion."""
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id, code="dealer")
        _seed_promotion(
            db, description="ZZT Mocha Only", access_levels=["mocha_dealer"]
        )

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert not any(r["name"] == "ZZT Mocha Only" for r in rows)

    def test_a_promotion_for_an_overlapping_audience_is_shown(self, client):
        """The same dealer-coded contact sees a promotion tagged for dealers too."""
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id, code="dealer")
        _seed_promotion(
            db, description="ZZT Dealer Overlap", access_levels=["mocha_dealer", "dealer"]
        )

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert any(r["name"] == "ZZT Dealer Overlap" for r in rows)

    def test_an_empty_access_levels_promotion_is_hidden_from_everyone(self, client):
        """An empty ``access_levels`` reaches nobody, same as `_may_see_offer`."""
        c, db, contact_id = client
        _grant_promotion_audience_code(db, contact_id, code="dealer")
        _seed_promotion(db, description="ZZT Nobody", access_levels=[])

        rows = c.get("/api/v1/public/portal/lookups/promotions").json()

        assert not any(r["name"] == "ZZT Nobody" for r in rows)

    def test_a_contact_with_no_access_codes_sees_no_promotions(self):
        """Fail closed rather than falling back to a default audience.

        A ``ContactPortalFormOverride`` can grant a contact ``price_tag_request``
        visibility with no access-type membership at all (``TestPortalFormVisibility
        .test_override_enable_adds_type`` in ``test_price_tag_request.py`` proves the
        override alone is enough). Such a contact passes the route's grant check but
        carries zero access codes, and must not fall back to
        ``pricing.PUBLIC_ACCESS_CODE`` the way an anonymous public-catalogue viewer
        does - a portal contact is never anonymous, so no code means no promotions,
        not "the public ones".
        """
        from app.api.v1.public.portal import get_portal_token
        from app.database import get_db
        from app.models.access import RespondContact
        from app.models.portal import PortalToken
        from app.models.price_tag import ContactPortalFormOverride

        with blank_session() as db:
            contact = RespondContact(
                id=str(uuid.uuid4()),
                phone_number=f"+60{uuid.uuid4().hex[:9]}",
                name=unique_code("contact"),
            )
            db.add(contact)
            db.add(
                ContactPortalFormOverride(
                    contact_id=contact.id,
                    form_type="price_tag_request",
                    is_enabled=True,
                )
            )
            db.flush()
            # Defaults to access_levels=["dealer","end_user"] - broadly visible to
            # anyone WITH a code, and still hidden from a contact with none.
            _seed_promotion(db, description="ZZT Anyones Guess")

            def _override_get_db():
                yield db

            def _override_portal_token():
                return PortalToken(
                    id=str(uuid.uuid4()), contact_id=contact.id, space_id="zzt-space"
                )

            app.dependency_overrides[get_db] = _override_get_db
            app.dependency_overrides[get_portal_token] = _override_portal_token
            try:
                with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                    res = c.get("/api/v1/public/portal/lookups/promotions")
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200, res.text
        assert res.json() == []

    def test_the_grant_gates_this_lookup_too(self, client):
        """The control: its sibling lookups are already gated the same way."""
        c, db, contact_id = client
        _revoke_the_grant(db, contact_id)

        res = c.get("/api/v1/public/portal/lookups/promotions")

        assert res.status_code == 403, res.text
        assert res.json()["code"] == "FORM_TYPE_NOT_VISIBLE"

    def test_a_missing_token_is_refused(self):
        """Auth runs before the grant check and before any DB read."""
        from app.database import get_db

        with blank_session() as db:

            def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db
            try:
                with TestClient(app) as c:
                    res = c.get("/api/v1/public/portal/lookups/promotions")
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 401, res.text
