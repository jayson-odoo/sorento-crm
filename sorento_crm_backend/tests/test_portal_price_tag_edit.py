"""Red tests for PLAN-portal-price-tag-journey-r8 slice S8 (D-P6 BE, D-P2 BE,
D-P2b BE).

Contract under test (plan section "D-P6", UAC AC-B1..B6, B9):

- ``PUT /api/v1/public/portal/submissions/price_tag_request/{id}`` succeeds
  (200) when ``portal_draft_at`` is set (existing draft-edit behaviour) OR the
  request is NOT a draft but its ``status`` is ``new`` / ``changes_requested``
  (the new post-submit edit gate, ``_require_editable``). On that new path:
  ``status``, ``assigned_to_id`` and ``portal_draft_at`` are unchanged, no form
  SLA event fires, and an audit row is written (action containing
  ``portal_edit_after_submit``).
- Every other post-submit status (``designing``, ``proof_ready``, ``approved``,
  ``ready``, ``void``) refuses PUT with 409 ``NOT_EDITABLE``.
- Ownership (another contact's request) still 403/404s as today.
- ``POST .../submit`` on an already-submitted request is still 409
  ``NOT_DRAFT``-shaped (today's code + message is ``ALREADY_SUBMITTED``; the
  UAC's own AC-B4 wording is "NOT_DRAFT" - either way this must still be a
  409 with a code the FE treats as "already submitted", so the assertion
  pins the STATUS CODE and refusal-family rather than the exact code string).
- Submitting a draft with ``price_mode=selling`` and no ``promotion_id``
  succeeds (200), and every line comes back with ``show_promo_price=True``
  (the ``PRICE_MODE_NEEDS_PROMOTION`` submit guard is retired).
- Submitting a draft with no ``needed_by_date`` succeeds (200) (need-by is
  optional).
- The detail GET carries ``is_editable``: True for a draft, True for a
  non-draft ``new``/``changes_requested`` request, False for every other
  status.

Fixtures modelled on ``tests/test_portal_price_tag_routes.py``: Postgres via
``tests/_pg_fixture.py::blank_session``, own seeded contact/product/promotion/
user chain, never borrowed rows.
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


def _seed_promotion(db: Session, *, description: str = "ZZT Promo") -> str:
    from app.models.marketing import Promotion

    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        is_active=True,
    )
    db.add(promo)
    db.flush()
    return promo.id


def _seed_user(db: Session) -> str:
    """A minimal designer/staff user, for ``assigned_to_id`` (FK to users.id)."""
    from app.models.user import User, UserStatus

    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('user')}@example.com",
        name=unique_code("Designer"),
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    return user.id


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
            return PortalToken(
                id=str(uuid.uuid4()),
                contact_id=contact_id,
                space_id="zzt-space",
            )

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = _override_portal_token
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                yield c, db, contact_id
        finally:
            app.dependency_overrides.clear()


def _create_draft(c, product_id: str, **extra) -> dict:
    payload = {"lines": [{"line_type": "product", "product_id": product_id}]}
    payload.update(extra)
    res = c.post(_BASE, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _force_status(
    db: Session,
    request_id: str,
    *,
    status: str,
    portal_draft_at=None,
    assigned_to_id: str | None = None,
):
    """Move a request straight to ``status`` without going through the whole
    submit/claim/transition pipeline - only the state this suite cares about,
    set directly on the row, then flushed so the API's next call sees it."""
    from app.services.price_tag_request_service import PriceTagRequestService

    req = PriceTagRequestService.get_request(db, request_id)
    req.status = status
    req.portal_draft_at = portal_draft_at
    if assigned_to_id is not None:
        req.assigned_to_id = assigned_to_id
    db.flush()
    return req


# ---------------------------------------------------------------------------
# AC-B1: PUT succeeds post-submit while status is new/changes_requested
# ---------------------------------------------------------------------------


class TestPostSubmitEditAllowed:
    def test_put_new_not_draft_updates_and_keeps_status(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        designer_id = _seed_user(db)
        created = _create_draft(c, product_id, debtor_name="ZZT Original")
        _force_status(
            db,
            created["id"],
            status="new",
            portal_draft_at=None,
            assigned_to_id=designer_id,
        )

        res = c.put(
            f"{_BASE}/{created['id']}",
            json={"debtor_name": "ZZT Edited After Submit"},
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["debtor_name"] == "ZZT Edited After Submit"
        assert body["status"] == "new"
        assert body["assigned_to_id"] == designer_id
        assert body["portal_draft_at"] is None

    def test_put_changes_requested_updates(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id, debtor_name="ZZT Original")
        _force_status(
            db, created["id"], status="changes_requested", portal_draft_at=None,
        )

        res = c.put(
            f"{_BASE}/{created['id']}",
            json={"debtor_name": "ZZT Revised Per Feedback"},
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["debtor_name"] == "ZZT Revised Per Feedback"
        assert body["status"] == "changes_requested"
        assert body["portal_draft_at"] is None

    def test_put_after_submit_writes_an_audit_row_and_no_form_event(
        self, client, monkeypatch
    ):
        """AC-B1: an audit row records the edit; no form SLA event fires (a
        post-submit edit must never re-open or re-fire the tracker)."""
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id, debtor_name="ZZT Original")
        _force_status(db, created["id"], status="new", portal_draft_at=None)

        emitted = []
        import app.services.form_sla_service as form_sla_service

        monkeypatch.setattr(
            form_sla_service,
            "emit_form_event",
            lambda *a, **k: emitted.append((a, k)),
        )

        res = c.put(
            f"{_BASE}/{created['id']}",
            json={"debtor_name": "ZZT Edited"},
        )

        assert res.status_code == 200, res.text
        assert emitted == []

        from app.models.audit import AuditLog

        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "price_tag_request",
                AuditLog.entity_id == created["id"],
            )
            .all()
        )
        assert len(rows) == 1, rows
        assert "portal_edit" in rows[0].action.lower()

    def test_put_after_submit_lines_are_replaced(self, client):
        """The header fields AND the lines are the whole payload the plan
        promises is editable, not just header fields."""
        c, db, _contact_id = client
        first = _seed_product(db)
        second = _seed_product(db)
        created = _create_draft(c, first, debtor_name="ZZT Original")
        _force_status(db, created["id"], status="new", portal_draft_at=None)

        res = c.put(
            f"{_BASE}/{created['id']}",
            json={
                "lines": [
                    {"line_type": "product", "product_id": second, "quantity": 3}
                ]
            },
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["lines"]) == 1
        assert body["lines"][0]["product_id"] == second
        assert body["lines"][0]["quantity"] == 3


# ---------------------------------------------------------------------------
# AC-B2: every other post-submit status refuses PUT with 409 NOT_EDITABLE
# ---------------------------------------------------------------------------


class TestPostSubmitEditRefused:
    @pytest.mark.parametrize(
        "status_value",
        ["designing", "proof_ready", "approved", "ready", "void"],
    )
    def test_put_refused_with_409_not_editable(self, client, status_value):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id, debtor_name="ZZT Original")
        _force_status(db, created["id"], status=status_value, portal_draft_at=None)

        res = c.put(
            f"{_BASE}/{created['id']}",
            json={"debtor_name": "ZZT Should Not Land"},
        )

        assert res.status_code == 409, res.text
        assert res.json()["code"] == "NOT_EDITABLE"

    def test_put_designing_409_not_editable(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id)
        _force_status(db, created["id"], status="designing", portal_draft_at=None)

        res = c.put(f"{_BASE}/{created['id']}", json={"debtor_name": "ZZT"})

        assert res.status_code == 409, res.text
        assert res.json()["code"] == "NOT_EDITABLE"

    def test_put_proof_ready_409_not_editable(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id)
        _force_status(db, created["id"], status="proof_ready", portal_draft_at=None)

        res = c.put(f"{_BASE}/{created['id']}", json={"debtor_name": "ZZT"})

        assert res.status_code == 409, res.text
        assert res.json()["code"] == "NOT_EDITABLE"

    def test_put_approved_409_not_editable(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id)
        _force_status(db, created["id"], status="approved", portal_draft_at=None)

        res = c.put(f"{_BASE}/{created['id']}", json={"debtor_name": "ZZT"})

        assert res.status_code == 409, res.text
        assert res.json()["code"] == "NOT_EDITABLE"

    def test_put_ready_409_not_editable(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id)
        _force_status(db, created["id"], status="ready", portal_draft_at=None)

        res = c.put(f"{_BASE}/{created['id']}", json={"debtor_name": "ZZT"})

        assert res.status_code == 409, res.text
        assert res.json()["code"] == "NOT_EDITABLE"

    def test_put_void_409_not_editable(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = _create_draft(c, product_id)
        _force_status(db, created["id"], status="void", portal_draft_at=None)

        res = c.put(f"{_BASE}/{created['id']}", json={"debtor_name": "ZZT"})

        assert res.status_code == 409, res.text
        assert res.json()["code"] == "NOT_EDITABLE"


# ---------------------------------------------------------------------------
# AC-B3: ownership gate unchanged
# ---------------------------------------------------------------------------


class TestOwnershipUnchanged:
    def test_put_other_contact_denied(self, client):
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

        res = c.put(
            f"{_BASE}/{theirs.id}",
            json={"debtor_name": "ZZT Should Not Land"},
        )

        assert res.status_code in (403, 404), res.text


# ---------------------------------------------------------------------------
# AC-B4: a second submit is still refused - a post-submit edit must never
# re-open the door to re-firing the SLA via submit.
# ---------------------------------------------------------------------------


class TestSubmitTwiceStillRefused:
    def test_submit_twice_409_not_draft(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "lines": [{"line_type": "product", "product_id": product_id}],
            },
        ).json()
        first = c.post(f"{_BASE}/{created['id']}/submit")
        assert first.status_code == 200, first.text

        # A post-submit edit via PUT in between must not have re-opened submit.
        c.put(f"{_BASE}/{created['id']}", json={"debtor_name": "ZZT Edited"})

        second = c.post(f"{_BASE}/{created['id']}/submit")

        assert second.status_code == 409, second.text
        assert second.json()["code"] in ("NOT_DRAFT", "ALREADY_SUBMITTED")


# ---------------------------------------------------------------------------
# AC-B5: selling with no promotion now submits fine (r7's guard is retired)
# ---------------------------------------------------------------------------


class TestSellingWithoutPromotionNowSubmits:
    def test_submit_selling_without_promotion_succeeds(self, client):
        c, db, _contact_id = client
        first = _seed_product(db)
        second = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": str(date.today() + timedelta(days=7)),
                "price_mode": "selling",
                "lines": [
                    {"line_type": "product", "product_id": first},
                    {"line_type": "product", "product_id": second},
                ],
            },
        ).json()
        assert created["promotion_id"] is None

        res = c.post(f"{_BASE}/{created['id']}/submit")

        assert res.status_code == 200, res.text

        from app.models.price_tag import PriceTagRequestLine

        rows = (
            db.query(PriceTagRequestLine)
            .filter(PriceTagRequestLine.request_id == created["id"])
            .all()
        )
        assert len(rows) == 2
        assert all(row.show_promo_price is True for row in rows)


# ---------------------------------------------------------------------------
# AC-B9: need-by is optional at submit
# ---------------------------------------------------------------------------


class TestNeedByOptionalAtSubmit:
    def test_submit_without_needed_by_succeeds(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)
        created = c.post(
            _BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "price_mode": "list",
                "lines": [{"line_type": "product", "product_id": product_id}],
            },
        ).json()
        assert created["needed_by_date"] is None

        res = c.post(f"{_BASE}/{created['id']}/submit")

        assert res.status_code == 200, res.text
        assert res.json()["status"] == "new"


# ---------------------------------------------------------------------------
# AC-B6: detail GET carries is_editable
# ---------------------------------------------------------------------------


class TestIsEditableMatrix:
    def test_detail_is_editable_matrix(self, client):
        c, db, _contact_id = client
        product_id = _seed_product(db)

        # Draft: portal_draft_at is set (created and never submitted).
        draft = _create_draft(c, product_id)
        assert c.get(f"{_BASE}/{draft['id']}").json()["is_editable"] is True

        # Non-draft new / changes_requested: still editable.
        for editable_status in ("new", "changes_requested"):
            req_body = _create_draft(c, product_id)
            _force_status(
                db, req_body["id"], status=editable_status, portal_draft_at=None,
            )
            body = c.get(f"{_BASE}/{req_body['id']}").json()
            assert body["is_editable"] is True, (editable_status, body)

        # Every other post-submit status: not editable.
        for locked_status in ("designing", "proof_ready", "approved", "ready", "void"):
            req_body = _create_draft(c, product_id)
            _force_status(
                db, req_body["id"], status=locked_status, portal_draft_at=None,
            )
            body = c.get(f"{_BASE}/{req_body['id']}").json()
            assert body["is_editable"] is False, (locked_status, body)
