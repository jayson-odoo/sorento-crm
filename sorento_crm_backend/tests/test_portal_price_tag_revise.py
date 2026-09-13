"""Red tests for PLAN-portal-price-tag-journey-r8 Round 3, R3-2 and AC-R2..R6.

R3-1 registers ``price_tag_request`` as a fourth ``RevisionAdapter`` in
``app/services/portal_revision_service.py`` (model ``PriceTagRequest``,
``number_attr="doc_number"``, an ``apply_lines`` callable running
``PriceTagRequestService.replace_lines`` + the submit validators). Today
``ADAPTERS`` holds only ``stock_inquiry`` / ``purchase_request`` /
``sponsorship_form`` (grep ``ADAPTERS: dict[str, RevisionAdapter]``), so
``get_adapter("price_tag_request")`` is ``None`` and every entry point below
(``PortalRevisionService.revise`` / ``policy_for`` / the generic portal.py
routes / the settings API) refuses BEFORE reaching any of this file's
assertions - the missing adapter registration, not a fixture bug.

Modelled on ``tests/test_portal_revise_flow.py`` (direct-service harness
style) and ``tests/test_portal_revision_config_routes.py`` (settings HTTP).
Every test seeds its own contact/request chain - Postgres via
``tests/_pg_fixture.py::blank_session``, never a borrowed row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# MUST be first app import - resolves the circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.portal import PortalRevisionConfig, PortalToken
from app.models.user import SystemSetting
from app.services.portal_revision_service import PortalRevisionService
from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session, unique_code

_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_PORTAL_BASE = "/api/v1/public/portal"
_PTAG_BASE = "/api/v1/public/portal/submissions/price_tag_request"


# --------------------------------------------------------------------------- #
# Seeding (price_tag_request has no entry in tests/_revision_harness.py's
# seed_entity - stock_inquiry/purchase_request/sponsorship_form only)
# --------------------------------------------------------------------------- #


def _seed_system_settings(db, *, enabled: bool = True, cap: int = 2) -> SystemSetting:
    row = SystemSetting(id=str(uuid.uuid4()), portal_revisions_enabled=enabled, portal_max_revisions=cap)
    db.add(row)
    db.commit()
    return row


def _seed_ptag_config(
    db, *, is_enabled: bool = True, max_revisions=None, allowed_statuses=None,
) -> PortalRevisionConfig:
    row = PortalRevisionConfig(
        id=str(uuid.uuid4()),
        source_entity_type="price_tag_request",
        is_enabled=is_enabled,
        max_revisions=max_revisions,
        allowed_statuses=(
            ["new", "changes_requested"] if allowed_statuses is None else allowed_statuses
        ),
        restart_stage_code=None,
    )
    db.add(row)
    db.commit()
    return row


def _seed_contact(db):
    from app.models.access import ContactAccessType, RespondContact, respond_contact_access_types

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("ZZT Contact"),
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
            contact_id=contact.id, access_type_code=access_type.code,
        )
    )
    db.commit()
    return contact


def _seed_token(contact) -> PortalToken:
    """A token object, not persisted, for direct-service calls (matches
    ``_revision_harness.seed_token``)."""
    return PortalToken(
        token=unique_code("tok"),
        contact_id=contact.id,
        space_id="zzt-space",
        expires_at=datetime(2099, 1, 1),
        verified_at=datetime(2026, 1, 1),
    )


def _persisted_token(db, contact) -> str:
    row = PortalToken(
        id=str(uuid.uuid4()),
        token=f"tok-{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id="zzt-space",
        expires_at=datetime.utcnow() + timedelta(days=30),
        verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(row)
    db.commit()
    return row.token


def _seed_product(db, *, class_label: str = "Kitchen Sink") -> str:
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("cat"),
        category_name=unique_code("Category"),
        class_label=class_label,
    )
    brand = Brand(id=str(uuid.uuid4()), brand_code=unique_code("br"), brand_name=unique_code("Brand"))
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


def _seed_request(
    db, contact, product_id: str, *, status: str = "new", portal_draft_at=None, revision_no: int = 0,
):
    req = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=_SORENTO_COMPANY_ID,
        data={
            "debtor_name": "ZZT Original Dealer",
            "lines": [{"line_type": "product", "product_id": product_id}],
        },
    )
    req.status = status
    req.portal_draft_at = portal_draft_at
    # AC-R2: the model needs `revision_no` / `last_revised_at` (migration
    # ptag_0006_revisions) - this raises AttributeError today, which is the
    # right red reason: the column does not exist yet.
    req.revision_no = revision_no
    db.commit()
    return req


@pytest.fixture(autouse=True)
def no_queue():
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _setup(db, *, cap: int = 3, status: str = "new", **request_kwargs):
    _seed_system_settings(db, cap=cap)
    _seed_ptag_config(db, max_revisions=None)
    contact = _seed_contact(db)
    product_id = _seed_product(db)
    row = _seed_request(db, contact, product_id, status=status, **request_kwargs)
    return contact, product_id, row


def _revise_payload(product_id: str) -> dict:
    return {"debtor_name": "ZZT Revised Dealer", "products": [{"product_id": product_id, "quantity": 5}]}


# =========================================================================== #
# AC-R2: revise happy path + disabled / status / cap / terminal / ownership
# =========================================================================== #


class TestReviseHappyPath:
    def test_revise_increments_counter_and_stamps_time(self, db):
        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        PortalRevisionService(db).revise(
            token, "price_tag_request", str(row.id), _revise_payload(product_id),
            "Dealer changed their mind", 0,
        )

        db.expire_all()
        fresh = PriceTagRequestService.get_request(db, str(row.id))
        assert fresh.revision_no == 1
        assert fresh.last_revised_at is not None

    def test_revise_writes_a_history_row_with_the_previous_snapshot(self, db):
        from app.models.portal import PortalFormRevision

        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        PortalRevisionService(db).revise(
            token, "price_tag_request", str(row.id), _revise_payload(product_id),
            "Dealer changed their mind", 0,
        )

        rows = (
            db.query(PortalFormRevision)
            .filter(
                PortalFormRevision.source_entity_type == "price_tag_request",
                PortalFormRevision.source_entity_id == str(row.id),
            )
            .order_by(PortalFormRevision.version_no.asc())
            .all()
        )
        assert [r.kind for r in rows] == ["original", "revision"]
        assert rows[0].snapshot_json["debtor_name"] == "ZZT Original Dealer"
        assert rows[1].snapshot_json["debtor_name"] == "ZZT Revised Dealer"
        assert "products" in rows[1].snapshot_json  # lines ride along, like PR/SF

    def test_revise_replaces_fields_and_lines(self, db):
        contact, product_id, row = _setup(db)
        second_product = _seed_product(db)
        token = _seed_token(contact)

        PortalRevisionService(db).revise(
            token, "price_tag_request", str(row.id),
            {"debtor_name": "ZZT Revised", "products": [{"product_id": second_product, "quantity": 2}]},
            "Swapped the product", 0,
        )

        db.expire_all()
        fresh = PriceTagRequestService.get_request(db, str(row.id))
        assert fresh.debtor_name == "ZZT Revised"
        assert [line.product_id for line in fresh.lines] == [second_product]

    def test_revise_restarts_status_at_new(self, db):
        contact, product_id, row = _setup(db, status="changes_requested")
        token = _seed_token(contact)

        PortalRevisionService(db).revise(
            token, "price_tag_request", str(row.id), _revise_payload(product_id),
            "Dealer changed their mind", 0,
        )

        db.expire_all()
        assert PriceTagRequestService.get_request(db, str(row.id)).status == "new"

    def test_revise_fires_the_form_sla_restart_once(self, db):
        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        with patch("app.services.form_sla_service.emit_form_event") as emit:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id), _revise_payload(product_id),
                "Dealer changed their mind", 0,
            )
        assert emit.call_count == 1


class TestReviseRefused:
    def test_disabled_config_refuses_422(self, db):
        contact, product_id, row = _setup(db)
        token = _seed_token(contact)
        db.query(PortalRevisionConfig).filter(
            PortalRevisionConfig.source_entity_type == "price_tag_request"
        ).update({"is_enabled": False})
        db.commit()

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id), _revise_payload(product_id), "Reason", 0,
            )
        assert exc.value.status_code == 422
        db.expire_all()
        assert PriceTagRequestService.get_request(db, str(row.id)).revision_no == 0

    @pytest.mark.parametrize("status_value", ["designing", "proof_ready", "approved", "ready", "void"])
    def test_status_outside_allowed_refuses_422(self, db, status_value):
        contact, product_id, row = _setup(db, status=status_value)
        token = _seed_token(contact)

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id), _revise_payload(product_id), "Reason", 0,
            )
        assert exc.value.status_code == 422
        db.expire_all()
        assert PriceTagRequestService.get_request(db, str(row.id)).revision_no == 0

    def test_max_reached_refuses_422(self, db):
        contact, product_id, row = _setup(db, cap=1, revision_no=1)
        token = _seed_token(contact)

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id), _revise_payload(product_id), "Reason", 1,
            )
        assert exc.value.status_code == 422
        assert "used all 1 revision" in str(exc.value.detail)

    def test_another_contact_gets_404(self, db):
        contact, product_id, row = _setup(db)
        intruder = _seed_contact(db)
        token = _seed_token(intruder)

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id), _revise_payload(product_id), "Reason", 0,
            )
        assert exc.value.status_code in (403, 404)
        db.expire_all()
        assert PriceTagRequestService.get_request(db, str(row.id)).revision_no == 0


# =========================================================================== #
# AC-R3: zero lines / set-guard / duplicate product / override survival
# =========================================================================== #


class TestReviseValidatesLines:
    def test_zero_lines_refuses_422_and_nothing_changes(self, db):
        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id),
                {"debtor_name": "ZZT Revised", "products": []}, "Reason", 0,
            )
        assert exc.value.status_code == 422
        db.expire_all()
        fresh = PriceTagRequestService.get_request(db, str(row.id))
        assert fresh.revision_no == 0
        assert len(fresh.lines) == 1  # the original line survives untouched

    def test_set_guarded_line_refuses_422(self, db):
        contact, product_id, row = _setup(db)
        guarded_product = _seed_product(db, class_label="Bathroom Furniture")
        token = _seed_token(contact)

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id),
                {"products": [{"product_id": guarded_product, "quantity": 1}]}, "Reason", 0,
            )
        assert exc.value.status_code == 422
        db.expire_all()
        assert PriceTagRequestService.get_request(db, str(row.id)).revision_no == 0

    def test_duplicate_product_refuses_422_duplicate_line(self, db):
        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token, "price_tag_request", str(row.id),
                {
                    "products": [
                        {"product_id": product_id, "quantity": 1},
                        {"product_id": product_id, "quantity": 2},
                    ]
                },
                "Reason",
                0,
            )
        assert exc.value.status_code == 422
        # AC-R7: the code names the duplicate product, never a raw 500 from
        # uq_ptag_line_request_product.
        detail = getattr(exc.value, "detail", None)
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "DUPLICATE_LINE"

    def test_override_survives_when_the_same_product_is_revised(self, db):
        from app.models.price_tag import PriceTagRequestLine

        contact, product_id, row = _setup(db)
        line = db.query(PriceTagRequestLine).filter(PriceTagRequestLine.request_id == row.id).one()
        line.marketing_price_override = 42.50
        line.marketing_override_reason = "Marketing override ZZT"
        db.commit()
        token = _seed_token(contact)

        PortalRevisionService(db).revise(
            token, "price_tag_request", str(row.id),
            {"products": [{"product_id": product_id, "quantity": 9}]}, "Reason", 0,
        )

        db.expire_all()
        fresh_line = (
            db.query(PriceTagRequestLine).filter(PriceTagRequestLine.request_id == row.id).one()
        )
        assert float(fresh_line.marketing_price_override or 0) == pytest.approx(42.50)
        assert fresh_line.marketing_override_reason == "Marketing override ZZT"


# =========================================================================== #
# AC-R4: create / draft PUT with a duplicate product never 500s
# =========================================================================== #


class TestCreateAndDraftPutRefuseDuplicateProduct:
    @pytest.fixture
    def http_client(self):
        from app.api.v1.public.portal import get_portal_token
        from app.database import get_db

        with blank_session() as db:
            contact = _seed_contact(db)

            def _override_get_db():
                yield db

            def _override_portal_token():
                return PortalToken(id=str(uuid.uuid4()), contact_id=contact.id, space_id="zzt-space")

            app.dependency_overrides[get_db] = _override_get_db
            app.dependency_overrides[get_portal_token] = _override_portal_token
            try:
                with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                    yield c, db, contact
            finally:
                app.dependency_overrides.clear()

    def test_post_create_duplicate_product_422_not_500(self, http_client):
        c, db, _contact = http_client
        product_id = _seed_product(db)

        res = c.post(
            _PTAG_BASE,
            json={
                "debtor_name": "ZZT Dealer",
                "lines": [
                    {"line_type": "product", "product_id": product_id, "quantity": 1},
                    {"line_type": "product", "product_id": product_id, "quantity": 2},
                ],
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "DUPLICATE_LINE"

    def test_put_draft_duplicate_product_422_not_500(self, http_client):
        c, db, _contact = http_client
        product_id = _seed_product(db)
        created = c.post(
            _PTAG_BASE,
            json={"lines": [{"line_type": "product", "product_id": product_id}]},
        ).json()

        res = c.put(
            f"{_PTAG_BASE}/{created['id']}",
            json={
                "lines": [
                    {"line_type": "product", "product_id": product_id, "quantity": 1},
                    {"line_type": "product", "product_id": product_id, "quantity": 3},
                ]
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "DUPLICATE_LINE"


# =========================================================================== #
# AC-R5: revisions list GET, revision-draft PUT/DELETE for price_tag_request
# =========================================================================== #


class TestRevisionsListAndDraftRoutes:
    @pytest.fixture
    def route_client(self):
        from app.database import get_db

        with blank_session() as db:

            def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db
            try:
                with TestClient(app) as c:
                    yield c, db
            finally:
                app.dependency_overrides.clear()

    def _seeded(self, db):
        contact, product_id, row = _setup(db)
        headers = {"X-Portal-Token": _persisted_token(db, contact)}
        return contact, product_id, row, headers

    def test_get_revisions_list_for_owner(self, route_client):
        c, db = route_client
        _contact, _product_id, row, headers = self._seeded(db)

        res = c.get(f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revisions", headers=headers)
        assert res.status_code == 200, res.text

    def test_get_revisions_list_other_contact_404(self, route_client):
        c, db = route_client
        _contact, _product_id, row, _headers = self._seeded(db)
        intruder = _seed_contact(db)
        intruder_headers = {"X-Portal-Token": _persisted_token(db, intruder)}

        res = c.get(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revisions",
            headers=intruder_headers,
        )
        assert res.status_code == 404, res.text

    def test_put_revision_draft_saved_and_resumed_on_detail(self, route_client):
        c, db = route_client
        _contact, product_id, row, headers = self._seeded(db)

        put_res = c.put(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revision-draft",
            headers=headers,
            json={"base_revision_no": 0, "reason": "In progress", "fields": {"debtor_name": "ZZT Draft"}},
        )
        assert put_res.status_code == 200, put_res.text

        detail = c.get(f"{_PTAG_BASE}/{row.id}", headers=headers).json()
        assert detail.get("revision_draft") is not None
        assert detail["revision_draft"]["fields"]["debtor_name"] == "ZZT Draft"

    def test_delete_revision_draft_discards_it(self, route_client):
        c, db = route_client
        _contact, product_id, row, headers = self._seeded(db)
        c.put(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revision-draft",
            headers=headers,
            json={"base_revision_no": 0, "fields": {"debtor_name": "ZZT Draft"}},
        )

        del_res = c.delete(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revision-draft", headers=headers,
        )
        assert del_res.status_code == 200, del_res.text
        assert PortalRevisionService(db).get_draft("price_tag_request", str(row.id)) is None

    def test_revision_draft_other_contact_404(self, route_client):
        c, db = route_client
        _contact, _product_id, row, _headers = self._seeded(db)
        intruder = _seed_contact(db)
        intruder_headers = {"X-Portal-Token": _persisted_token(db, intruder)}

        res = c.put(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revision-draft",
            headers=intruder_headers,
            json={"base_revision_no": 0, "fields": {}},
        )
        assert res.status_code == 404, res.text

    def test_list_summaries_carry_revision_fields(self, route_client):
        c, db = route_client
        _contact, product_id, row, headers = self._seeded(db)

        items = c.get(f"{_PTAG_BASE}", headers=headers).json()["items"]
        assert items, "the seeded request must show up in its own list"
        item = next(i for i in items if i["id"] == str(row.id))
        assert {"revision_no", "last_revised_at", "has_revision_draft"} <= set(item)


# =========================================================================== #
# AC-R6: settings API - price_tag_request row, enable with its own statuses
# =========================================================================== #


class TestPortalRevisionSettingsIncludesPriceTagRequest:
    BASE = "/api/v1/forms-management/revision-configs"

    @pytest.fixture
    def settings_client(self):
        from app.database import get_db

        with blank_session() as db:

            def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db
            try:
                with TestClient(app) as c:
                    yield c, db
            finally:
                app.dependency_overrides.clear()

    def _as_office_user(self):
        from app.dependencies import get_current_user, get_current_user_or_api_key

        actor = {"id": str(uuid.uuid4()), "email": "office@example.test", "role": "admin"}
        app.dependency_overrides[get_current_user] = lambda: actor
        app.dependency_overrides[get_current_user_or_api_key] = lambda: actor

    def test_get_lists_price_tag_request_seeded_disabled(self, settings_client):
        """The migration seeds this row disabled - a create_all schema (this
        fixture) has the table with no rows, mirroring the other three types'
        own 'missing row means disabled' test."""
        c, db = settings_client
        self._as_office_user()
        _seed_ptag_config(db, is_enabled=False, allowed_statuses=[])

        items = c.get(self.BASE).json()["items"]
        row = next((i for i in items if i["source_entity_type"] == "price_tag_request"), None)
        assert row is not None, items
        assert row["is_enabled"] is False

    def test_put_enables_price_tag_request_with_its_own_statuses(self, settings_client):
        c, _db = settings_client
        self._as_office_user()

        res = c.put(
            f"{self.BASE}/price_tag_request",
            json={
                "is_enabled": True,
                "max_revisions": 2,
                "allowed_statuses": ["new", "designing", "changes_requested"],
                "restart_stage_code": None,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["source_entity_type"] == "price_tag_request"
        assert body["allowed_statuses"] == ["new", "designing", "changes_requested"]


# =========================================================================== #
# Security review of S10 (aa3ff8e21) - five gaps in the revise path.
# =========================================================================== #


def _revoke_grant(db, contact) -> None:
    """Take price_tag_request off every access type this contact holds -
    mirrors ``test_portal_price_tag_routes.py::_revoke_the_grant``."""
    from app.models.access import ContactAccessType, respond_contact_access_types

    codes = [
        row.access_type_code
        for row in db.execute(
            respond_contact_access_types.select().where(
                respond_contact_access_types.c.contact_id == contact.id
            )
        )
    ]
    db.query(ContactAccessType).filter(ContactAccessType.code.in_(codes)).update(
        {"portal_form_types": []}, synchronize_session=False
    )
    db.commit()


class TestRevisePromotionAudienceGate:
    """Gap A: ``_apply_price_tag_lines`` never calls
    ``PriceTagRequestService.validate_promotion_access`` - a revise payload
    setattrs ``promotion_id`` straight onto the row (via the generic portal
    field-whitelist writer), so a promotion this contact's audience cannot
    see, or one belonging to another company, lands anyway."""

    def test_revise_promotion_outside_audience_422(self, db):
        from app.models.marketing import Promotion

        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        outside_audience = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT Dealer-Only Promo",
            is_active=True,
            access_levels=["some-other-access-code"],
            company_id=_SORENTO_COMPANY_ID,
        )
        db.add(outside_audience)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token,
                "price_tag_request",
                str(row.id),
                {"promotion_id": outside_audience.id},
                "Reason",
                0,
            )
        assert exc.value.status_code == 422
        detail = exc.value.detail
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "PROMOTION_NOT_AVAILABLE", detail

        db.expire_all()
        fresh = PriceTagRequestService.get_request(db, str(row.id))
        assert fresh.promotion_id is None
        assert fresh.revision_no == 0
        from app.models.portal import PortalFormRevision

        assert (
            db.query(PortalFormRevision)
            .filter(
                PortalFormRevision.source_entity_type == "price_tag_request",
                PortalFormRevision.source_entity_id == str(row.id),
                PortalFormRevision.kind == "revision",
            )
            .count()
            == 0
        )

    def test_revise_promotion_from_another_company_422(self, db):
        from app.models.company import Company
        from app.models.marketing import Promotion

        contact, product_id, row = _setup(db)
        token = _seed_token(contact)

        other_company = Company(
            id=str(uuid.uuid4()), name=unique_code("ZZT Other Co"), code=unique_code("co")[:20],
        )
        db.add(other_company)
        db.flush()
        other_company_promo = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT Other Company Promo",
            is_active=True,
            access_levels=["dealer", "end_user"],
            company_id=other_company.id,
        )
        db.add(other_company_promo)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            PortalRevisionService(db).revise(
                token,
                "price_tag_request",
                str(row.id),
                {"promotion_id": other_company_promo.id},
                "Reason",
                0,
            )
        assert exc.value.status_code == 422
        db.expire_all()
        assert PriceTagRequestService.get_request(db, str(row.id)).promotion_id is None


class TestRevisionRoutesRequireFormVisibility:
    """Gap B: ``_require_own_request`` (the ownership check the generic
    revision routes dispatch to for price_tag_request) checks ownership
    ONLY - never ``_assert_visible``/``_require_price_tag_request_visible``.
    A contact whose price_tag_request grant is revoked can still list, revise
    and save/discard a revision draft on their own old request."""

    @pytest.fixture
    def route_client(self):
        from app.database import get_db

        with blank_session() as db:

            def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db
            try:
                with TestClient(app) as c:
                    yield c, db
            finally:
                app.dependency_overrides.clear()

    def _seeded_but_revoked(self, db):
        contact, product_id, row = _setup(db)
        _revoke_grant(db, contact)
        headers = {"X-Portal-Token": _persisted_token(db, contact)}
        return row, headers

    def test_list_revisions_refused_without_visibility(self, route_client):
        c, db = route_client
        row, headers = self._seeded_but_revoked(db)

        res = c.get(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revisions",
            headers=headers,
        )
        assert res.status_code in (403, 404), res.text

    def test_revise_refused_without_visibility(self, route_client):
        c, db = route_client
        row, headers = self._seeded_but_revoked(db)

        res = c.post(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revise",
            headers=headers,
            json={"reason": "Reason", "expected_revision_no": 0, "fields": {}},
        )
        assert res.status_code in (403, 404), res.text

    def test_save_revision_draft_refused_without_visibility(self, route_client):
        c, db = route_client
        row, headers = self._seeded_but_revoked(db)

        res = c.put(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revision-draft",
            headers=headers,
            json={"base_revision_no": 0, "fields": {}},
        )
        assert res.status_code in (403, 404), res.text

    def test_discard_revision_draft_refused_without_visibility(self, route_client):
        c, db = route_client
        row, headers = self._seeded_but_revoked(db)

        res = c.delete(
            f"{_PORTAL_BASE}/submissions/price_tag_request/{row.id}/revision-draft",
            headers=headers,
        )
        assert res.status_code in (403, 404), res.text


class TestAttachmentGateRechecksPolicy:
    """Gap C: ``_require_editable`` treats the mere EXISTENCE of a revision
    draft row as "editable", never re-checking whether the request's CURRENT
    status still allows a revision. A draft saved while the request was
    `new` keeps unlocking attachments after the request moves to a terminal
    status the policy would refuse outright (`ready`, `void`)."""

    class _FakeStorageBackend:
        def upload_file(self, *args, **kwargs):
            key = args[1] if len(args) > 1 else kwargs.get("file_path")
            return key, f"https://cdn.test/{key}"

        def download_file(self, key: str) -> bytes:
            return b"zzt-file-bytes"

    @pytest.fixture
    def attachment_client(self, monkeypatch):
        from app.database import get_db
        from app.models.resources import AttachmentType
        from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE
        import app.services.storage_router as storage_router

        with blank_session() as db:
            db.add(
                AttachmentType(
                    id=str(uuid.uuid4()),
                    code=PORTAL_ATTACHMENT_TYPE_CODE,
                    type_name="Portal Submission",
                    allowed_extensions="jpg,jpeg,png,pdf",
                    max_file_size_mb=10,
                )
            )
            db.commit()

            fake_backend = self._FakeStorageBackend()
            monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
            monkeypatch.setattr(storage_router, "get_backend", lambda provider: fake_backend)
            monkeypatch.setattr(
                storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}"
            )

            def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db
            try:
                with TestClient(app) as c:
                    yield c, db
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.parametrize("terminal_status", ["ready", "void"])
    def test_attachment_gate_rechecks_policy(self, attachment_client, terminal_status):
        import io

        c, db = attachment_client
        contact, product_id, row = _setup(db)
        token_str = _persisted_token(db, contact)

        # A revision draft saved while the request is still `new`.
        PortalRevisionService(db).save_draft(
            _seed_token(contact),
            "price_tag_request",
            str(row.id),
            {"debtor_name": "ZZT Draft Edit"},
            "In progress",
            0,
        )

        # The request then moves on - approved/produced/voided, well past
        # any status the policy would still allow a revision at.
        db.expire_all()
        fresh = PriceTagRequestService.get_request(db, str(row.id))
        fresh.status = terminal_status
        db.commit()

        upload_res = c.post(
            f"{_PORTAL_BASE}/attachments",
            data={"kind": "price_tag_request", "submission_id": str(row.id)},
            files={"file": ("po.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token_str},
        )
        assert upload_res.status_code == 409, upload_res.text

        from app.models.entity_attachment import EntityAttachmentLink
        from app.models.resources import Attachment

        att = Attachment(
            id=str(uuid.uuid4()),
            original_filename="ZZT-existing.pdf",
            stored_filename="ZZT-existing.pdf",
            file_path=f"portal/zzt/{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            uploader_kind="contact",
            uploaded_by_contact_id=contact.id,
        )
        db.add(att)
        db.flush()
        link = EntityAttachmentLink(
            entity_type="price_tag_request", entity_id=str(row.id), attachment_id=att.id
        )
        db.add(link)
        db.commit()

        delete_res = c.delete(
            f"{_PORTAL_BASE}/attachments/{link.id}",
            headers={"X-Portal-Token": token_str},
        )
        assert delete_res.status_code == 409, delete_res.text


class TestReviseCarriesAlternativesAndAccessories:
    """Gap D: ``_convert_ptag_revise_line`` only reads ``product_id`` /
    ``product_set_id`` / ``quantity`` / ``remarks`` off a revise payload
    line, so ``replace_lines`` -> ``_add_lines`` writes every revised line's
    ``alternatives`` back as ``[]`` and ``included_accessories`` as ``None``
    - the same "silently wipes a per-line detail on re-save" bug the
    marketing-override carry-over already fixed, left open for these two
    fields."""

    def test_revise_carries_alternatives_and_accessories(self, db):
        from app.models.price_tag import PriceTagRequestLine

        contact, product_id, row = _setup(db)
        line = db.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == row.id
        ).one()
        line.alternatives = ["ALT-CODE-1", "ALT-CODE-2"]
        line.included_accessories = "Tap + waste kit"
        db.commit()
        token = _seed_token(contact)

        PortalRevisionService(db).revise(
            token,
            "price_tag_request",
            str(row.id),
            {"products": [{"product_id": product_id, "quantity": 4}]},
            "Reason",
            0,
        )

        db.expire_all()
        fresh_line = (
            db.query(PriceTagRequestLine).filter(PriceTagRequestLine.request_id == row.id).one()
        )
        assert fresh_line.alternatives == ["ALT-CODE-1", "ALT-CODE-2"]
        assert fresh_line.included_accessories == "Tap + waste kit"


class TestRevisionRoutesMalformedId:
    """Gap E: neither ``PriceTagRequestService.get_request`` (used by
    ``_require_own_request``) nor ``PortalRevisionService.fetch_owned``
    validate the path id is a UUID before it reaches the query - a
    non-UUID id 500s from Postgres refusing the comparison instead of
    answering the usual "not found" 404."""

    @pytest.fixture
    def route_client(self):
        from app.database import get_db

        with blank_session() as db:

            def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db
            try:
                with TestClient(app) as c:
                    yield c, db
            finally:
                app.dependency_overrides.clear()

    def test_list_revisions_malformed_id_404(self, route_client):
        c, db = route_client
        contact = _seed_contact(db)
        headers = {"X-Portal-Token": _persisted_token(db, contact)}

        res = c.get(
            f"{_PORTAL_BASE}/submissions/price_tag_request/not-a-uuid/revisions",
            headers=headers,
        )
        assert res.status_code == 404, res.text

    def test_revise_malformed_id_404(self, route_client):
        c, db = route_client
        contact = _seed_contact(db)
        headers = {"X-Portal-Token": _persisted_token(db, contact)}

        res = c.post(
            f"{_PORTAL_BASE}/submissions/price_tag_request/not-a-uuid/revise",
            headers=headers,
            json={"reason": "Reason", "expected_revision_no": 0, "fields": {}},
        )
        assert res.status_code == 404, res.text
