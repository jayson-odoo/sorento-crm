"""r9 S3/D7-D11: who prints, and the collection hand-over (AC-S3-1 .. AC-S3-8).

`ready` said a PDF had been generated. It did not say anybody had the tags in
their hands, which is the thing the office actually needs to know. So the
request now records who prints, and the two answers end differently: a
salesperson printing their own tags is FINISHED at `approved`, and an office
print carries on to `ready_for_collection` and then `collected` - by hand, or
by the sweep after the configured days.

What each class pins down, and why it is not obvious:

* `print_by` has NO default (E1). A guessed default silently sends half the
  requests down the wrong branch, so submit refuses instead.
* `request_tag_sheet_export` no longer transitions ANYTHING. It used to flip
  approved -> ready on first export, which is what made "the PDF exists" and
  "the tags are collected" the same fact.
* terminality is REQUEST-aware, not status-aware: `approved` is the end for a
  self print and the middle for an office print.

Red before the coder starts: the column, the two statuses, the setting and the
handler do not exist.
"""
from __future__ import annotations

import glob
import importlib.util
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

_PORTAL = "/api/v1/public/portal/submissions/price_tag_request/{id}"
_CRM = "/api/v1/dealer-kit/price-tag-requests/{id}"
_SETTINGS = "/api/v1/user-management/settings/"
_SETTINGS_GENERAL = "/api/v1/user-management/settings/general"
_APP_CONFIG = "/api/v1/user-management/settings/app-config"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def portal():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    with blank_session() as db:
        seed.seed_marketer(db)
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


@pytest.fixture
def db_only():
    with blank_session() as db:
        yield db


def _draft_request(db, contact_id, *, print_by=None):
    """A request the salesperson has NOT submitted yet."""
    from app.services.price_tag_request_service import PriceTagRequestService

    product = seed.seed_product(db)
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact_id,
        company_id=seed.SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [{"line_type": "product", "product_id": product.id}],
        },
    )
    if print_by is not None:
        request.print_by = print_by
    db.flush()
    db.commit()
    return request


# ---------------------------------------------------------------------------
# AC-S3-1 - submit refuses without a print choice
# ---------------------------------------------------------------------------


class TestSubmitRequiresAPrintChoice:
    def test_a_draft_with_no_print_by_is_refused_with_its_own_code(self, portal):
        client, db, contact_id = portal
        request = _draft_request(db, contact_id)

        response = client.post(f"{_PORTAL.format(id=request.id)}/submit")

        assert response.status_code == 422, response.text
        body = response.json()
        assert body.get("code") == "PRINT_BY_REQUIRED", body
        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        fresh = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert fresh.portal_draft_at is not None, "a refused submit stays a draft"

    @pytest.mark.parametrize("choice", ["office", "self"])
    def test_a_draft_that_answered_it_submits(self, portal, choice):
        client, db, contact_id = portal
        request = _draft_request(db, contact_id, print_by=choice)

        response = client.post(f"{_PORTAL.format(id=request.id)}/submit")

        assert response.status_code == 200, response.text
        assert response.json()["print_by"] == choice

    def test_the_service_guard_names_the_field_on_its_own(self, db_only):
        """`validate_submittable` is the bar, so a second caller cannot skip it."""
        from app.services.error_handler import AppException
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        request = _draft_request(db_only, contact_id)

        with pytest.raises(AppException) as excinfo:
            PriceTagRequestService.validate_submittable(request)

        assert excinfo.value.code == "PRINT_BY_REQUIRED"
        assert excinfo.value.status_code == 422


# ---------------------------------------------------------------------------
# AC-S3-2 - the office fixing the choice
# ---------------------------------------------------------------------------


class TestTheOfficeCanFixThePrintChoice:
    def test_a_processor_patches_print_by_while_the_request_is_live(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product], print_by="self"
        )

        response = client.patch(_CRM.format(id=request.id), json={"print_by": "office"})

        assert response.status_code == 200, response.text
        assert response.json()["print_by"] == "office"
        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        assert (
            db.query(PriceTagRequest)
            .filter(PriceTagRequest.id == request.id)
            .first()
            .print_by
            == "office"
        )

    def test_a_terminal_request_refuses_the_change(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="collected", products=[product], print_by="office"
        )

        response = client.patch(_CRM.format(id=request.id), json={"print_by": "self"})

        assert response.status_code == 409, response.text

    def test_every_read_carries_the_choice(self, crm):
        """`response_model` drops an undeclared field silently (LESSONS)."""
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product], print_by="office"
        )

        detail = client.get(_CRM.format(id=request.id)).json()

        assert detail["print_by"] == "office"
        for key in (
            "ready_for_collection_at",
            "collected_at",
            "collected_auto",
        ):
            assert key in detail, f"the detail response is missing {key!r}"


# ---------------------------------------------------------------------------
# AC-S3-3 - `ready` is gone, and the export stops moving the request
# ---------------------------------------------------------------------------


def _load_migration(pattern: str):
    """Import an alembic revision by FILENAME PATTERN.

    Revision filenames start with a digit, so they cannot be imported by module
    path (the `_run_migration` idiom, tests/test_prompt_registry_is_seeded_by
    _migrations.py). Matched by pattern, not by exact name, so the coder is free
    to pick the numeric prefix that lands on main's head at merge time.
    """
    matches = sorted(
        glob.glob(
            str(Path(__file__).resolve().parent.parent / "alembic" / "versions" / pattern)
        )
    )
    assert matches, f"no alembic revision matching {pattern!r}"
    path = matches[-1]
    spec = importlib.util.spec_from_file_location(f"migration_{Path(path).stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestReadyIsRetired:
    def test_the_migration_maps_every_ready_row_to_approved(self, db_only):
        """The migration exposes ``map_ready_rows_to_approved(bind) -> int``.

        A data migration hidden inside ``upgrade()`` cannot be tested without
        running the whole chain, and there is exactly one row shape that matters
        here, so the step is a named function the migration calls and this test
        calls.
        """
        from app.models.price_tag import PriceTagRequest

        module = _load_migration("*print_collection*.py")
        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        stale = seed.seed_request(
            db_only, contact_id, status="ready", products=[product]
        )
        untouched = seed.seed_request(
            db_only, contact_id, status="proof_ready", products=[product]
        )

        module.map_ready_rows_to_approved(db_only.get_bind())
        db_only.expire_all()

        assert (
            db_only.query(PriceTagRequest)
            .filter(PriceTagRequest.id == stale.id)
            .first()
            .status
            == "approved"
        )
        assert (
            db_only.query(PriceTagRequest)
            .filter(PriceTagRequest.id == untouched.id)
            .first()
            .status
            == "proof_ready"
        )

    def test_the_status_graph_has_no_ready_edge_left(self):
        from app.services import price_tag_request_service as svc

        assert "ready" not in svc.VALID_TRANSITIONS, svc.VALID_TRANSITIONS
        for current, allowed in svc.VALID_TRANSITIONS.items():
            assert "ready" not in allowed, f"{current} still offers 'ready'"

    @pytest.mark.parametrize(
        "status", ["approved", "ready_for_collection", "collected"]
    )
    def test_the_export_accepts_the_three_finished_statuses_and_moves_nothing(
        self, db_only, monkeypatch, status
    ):
        from app.models.price_tag import PriceTagRequest
        from app.services.dealer_kit import tag_sheet_export_service

        monkeypatch.setattr(
            "app.services.queue_service.enqueue_job", lambda *a, **k: None
        )
        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only, contact_id, status=status, products=[product], print_by="office"
        )
        seed.attach_design(db_only, request)

        tag_sheet_export_service.request_tag_sheet_export(
            db_only, request_id=request.id, user_id=seed.MARKETER_ID, sheet_ids=None
        )

        db_only.expire_all()
        assert (
            db_only.query(PriceTagRequest)
            .filter(PriceTagRequest.id == request.id)
            .first()
            .status
            == status
        ), "requesting a PDF is not a step in the hand-over"


# ---------------------------------------------------------------------------
# AC-S3-4 / 5 / 6 - the collection transitions
# ---------------------------------------------------------------------------


class TestCollectionTransitions:
    def test_a_self_print_request_is_terminal_at_approved(self, db_only):
        from app.services.error_handler import AppException
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only, contact_id, status="approved", products=[product], print_by="self"
        )

        with pytest.raises(AppException) as excinfo:
            PriceTagRequestService.transition_status(
                db_only, request.id, "ready_for_collection", user_id=seed.MARKETER_ID
            )

        assert excinfo.value.status_code == 409
        assert PriceTagRequestService.is_terminal(request) is True

    def test_an_office_print_reaches_collection_and_stamps_the_time(self, db_only):
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only,
            contact_id,
            status="approved",
            products=[product],
            print_by="office",
        )

        result = PriceTagRequestService.transition_status(
            db_only, request.id, "ready_for_collection", user_id=seed.MARKETER_ID
        )

        assert result.status == "ready_for_collection"
        assert result.ready_for_collection_at is not None
        assert PriceTagRequestService.is_terminal(result) is False

    def test_a_request_with_no_print_choice_reaches_neither(self, db_only):
        from app.services.error_handler import AppException
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only, contact_id, status="approved", products=[product], print_by=None
        )

        with pytest.raises(AppException) as excinfo:
            PriceTagRequestService.transition_status(
                db_only, request.id, "ready_for_collection", user_id=seed.MARKETER_ID
            )

        assert excinfo.value.status_code == 409

    def test_the_office_marking_it_collected_records_the_user(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="ready_for_collection",
            products=[product],
            print_by="office",
        )

        response = client.post(
            f"{_CRM.format(id=request.id)}/transition", json={"status": "collected"}
        )

        assert response.status_code == 200, response.text
        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        row = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert row.status == "collected"
        assert row.collected_at is not None
        assert row.collected_by_user_id == seed.MARKETER_ID
        assert row.collected_by_contact_id is None
        assert row.collected_auto is False

    def test_the_salesperson_marking_it_collected_records_the_contact(self, portal):
        client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="ready_for_collection",
            products=[product],
            print_by="office",
        )

        response = client.post(f"{_PORTAL.format(id=request.id)}/collect")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "collected"
        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        row = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert row.collected_by_contact_id == contact_id
        assert row.collected_by_user_id is None

    def test_collected_is_terminal(self, db_only):
        from app.services.error_handler import AppException
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only,
            contact_id,
            status="collected",
            products=[product],
            print_by="office",
        )

        assert PriceTagRequestService.is_terminal(request) is True
        with pytest.raises(AppException):
            PriceTagRequestService.transition_status(
                db_only, request.id, "void", user_id=seed.MARKETER_ID
            )


# ---------------------------------------------------------------------------
# AC-S3-7 - the setting
# ---------------------------------------------------------------------------


class TestAutoCollectSetting:
    @pytest.fixture
    def settings_api(self, monkeypatch):
        from app.database import get_db
        from app.dependencies import get_current_user
        from app.models.user import SystemSetting
        from app.services.user_service import UserPermissionService

        caller = {"id": str(uuid.uuid4()), "email": "zzt-settings@zzt.test"}
        with blank_session() as db:
            db.add(SystemSetting(id=str(uuid.uuid4()), name=unique_code("Co")))
            db.commit()

            def _override_db():
                yield db

            app.dependency_overrides[get_db] = _override_db
            app.dependency_overrides[get_current_user] = lambda: caller
            monkeypatch.setattr(
                UserPermissionService,
                "check_user_has_permission",
                lambda self, uid, slug: True,
            )
            try:
                with TestClient(app) as client:
                    yield client, db
            finally:
                app.dependency_overrides.clear()

    def test_the_column_defaults_to_seven(self, db_only):
        from app.models.user import SystemSetting

        row = SystemSetting(id=str(uuid.uuid4()), name=unique_code("Co"))
        db_only.add(row)
        db_only.commit()
        db_only.refresh(row)

        assert row.price_tag_auto_collect_days == 7

    def test_it_is_on_the_full_settings_read_and_the_narrow_projection(
        self, settings_api
    ):
        """D10: marketing does NOT hold `user_management.settings.view`, and the
        CRM detail card reads the value - so it has to be on `/app-config` too,
        or the card cannot say when a request auto-collects."""
        client, _db = settings_api

        full = client.get(_SETTINGS)
        assert full.status_code == 200, full.text
        assert "price_tag_auto_collect_days" in full.json()

        narrow = client.get(_APP_CONFIG)
        assert narrow.status_code == 200, narrow.text
        assert "price_tag_auto_collect_days" in narrow.json()

    @pytest.mark.parametrize("days", [0, 1, 7, 90])
    def test_the_bounds_accept_zero_to_ninety(self, settings_api, days):
        client, _db = settings_api

        response = client.put(
            _SETTINGS_GENERAL, json={"price_tag_auto_collect_days": days}
        )

        assert response.status_code == 200, response.text
        assert client.get(_SETTINGS).json()["price_tag_auto_collect_days"] == days

    @pytest.mark.parametrize("days", [-1, 91])
    def test_out_of_bounds_is_refused(self, settings_api, days):
        client, _db = settings_api

        response = client.put(
            _SETTINGS_GENERAL, json={"price_tag_auto_collect_days": days}
        )

        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# AC-S3-8 - the sweep
# ---------------------------------------------------------------------------


class TestAutoCollectHandler:
    def _settings(self, db, days: int):
        from app.models.user import SystemSetting

        row = db.query(SystemSetting).first()
        if row is None:
            row = SystemSetting(id=str(uuid.uuid4()), name=unique_code("Co"))
            db.add(row)
        row.price_tag_auto_collect_days = days
        db.commit()

    def _waiting(self, db, contact_id, *, days_ago: int):
        from app.models.price_tag import PriceTagRequest

        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="ready_for_collection",
            products=[product],
            print_by="office",
        )
        db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).update(
            {"ready_for_collection_at": datetime.utcnow() - timedelta(days=days_ago)}
        )
        db.commit()
        return request

    def test_only_rows_older_than_the_configured_days_flip(self, db_only):
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        self._settings(db_only, 7)
        stale = self._waiting(db_only, contact_id, days_ago=9)
        fresh = self._waiting(db_only, contact_id, days_ago=2)

        PriceTagRequestService.run_auto_collect(db_only)
        db_only.expire_all()

        stale_row = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == stale.id
        ).first()
        fresh_row = db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == fresh.id
        ).first()
        assert stale_row.status == "collected"
        assert stale_row.collected_auto is True
        assert stale_row.collected_at is not None
        assert stale_row.collected_by_user_id is None
        assert stale_row.collected_by_contact_id is None
        assert fresh_row.status == "ready_for_collection"

    def test_zero_days_turns_the_sweep_off_entirely(self, db_only):
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        self._settings(db_only, 0)
        ancient = self._waiting(db_only, contact_id, days_ago=400)

        PriceTagRequestService.run_auto_collect(db_only)
        db_only.expire_all()

        assert (
            db_only.query(PriceTagRequest)
            .filter(PriceTagRequest.id == ancient.id)
            .first()
            .status
            == "ready_for_collection"
        )

    def test_an_approved_office_request_is_not_swept(self, db_only):
        """Only the hand-over waits. An approved request has not been printed."""
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        contact_id = seed.seed_portal_contact(db_only)
        self._settings(db_only, 7)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only,
            contact_id,
            status="approved",
            products=[product],
            print_by="office",
        )

        PriceTagRequestService.run_auto_collect(db_only)
        db_only.expire_all()

        assert (
            db_only.query(PriceTagRequest)
            .filter(PriceTagRequest.id == request.id)
            .first()
            .status
            == "approved"
        )

    def test_the_handler_is_registered_under_its_key(self):
        from app.scheduler import task_scheduler
        from app.services.scheduled_task_service import TASK_HANDLERS

        task_scheduler.register_task_handlers()
        assert "price_tag_auto_collect" in TASK_HANDLERS

    def test_the_migration_seeds_the_scheduled_task_row(self, db_only):
        """The migration exposes ``seed_auto_collect_task(bind)``, called from
        ``upgrade()`` - same reason as ``map_ready_rows_to_approved`` above."""
        from app.models.scheduled_task import ScheduledTask

        module = _load_migration("*print_collection*.py")

        module.seed_auto_collect_task(db_only.get_bind())
        db_only.expire_all()

        row = (
            db_only.query(ScheduledTask)
            .filter(ScheduledTask.key == "price_tag_auto_collect")
            .first()
        )
        assert row is not None, "no scheduled_tasks row for price_tag_auto_collect"
        assert row.enabled is True
        assert (row.interval_unit, row.interval_value) == ("hours", 1)
