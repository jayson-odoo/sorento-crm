"""The tag sheet DRAFT write path (B1, captain ruling 2 Sep).

Autosave must not write history. Before this, the request designer's ~1s
autosave called the same ``PUT /design`` the manual Save button calls, so a
minute of dragging a layer around produced sixty immutable ``page_version``
rows and the Versions story for a request became unreadable.

The split, mirroring S5's template draft/live model:

* ``PUT /{id}/design/draft`` updates ``dealer_kit.page.draft_doc`` IN PLACE.
  No version row, ever - it is the same column being overwritten.
* ``PUT /{id}/design`` (manual Save) snapshots whatever the draft holds into
  exactly ONE new ``page_version`` and clears ``draft_doc``.
* ``GET /{id}/design`` prefers the draft when one is present and says which it
  answered with (``source``), so the designer reopens on the work in progress
  rather than on the last deliberate save.
* Export and proof rendering keep reading versions only - which is precisely
  why the draft must never become one by accident.

Auth-override and seeding come from ``test_price_tag_request_crm_routes.py``;
this file re-uses them rather than growing a second copy.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session
from tests.test_price_tag_request_crm_routes import (
    _MARKETER_ID,
    _seed_principals,
    _submitted_request,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
_BASE = "/api/v1/dealer-kit/price-tag-requests"


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
# Helpers
# ---------------------------------------------------------------------------


def _claimed_request(client, db):
    """A request in ``designing`` with its tag_sheet page created."""
    request, _contact = _submitted_request(db)
    assert client.post(f"{_BASE}/{request.id}/claim").status_code == 200
    return request


def _page_id(db, request_id: str) -> str:
    from app.models.price_tag import PriceTagRequest

    row = db.query(PriceTagRequest).filter(PriceTagRequest.id == request_id).first()
    db.expire(row)
    return row.page_id


def _versions(db, request_id: str):
    from app.models.dealer_kit import PageVersion

    return (
        db.query(PageVersion)
        .filter(PageVersion.page_id == _page_id(db, request_id))
        .order_by(PageVersion.version)
        .all()
    )


def _draft_doc(db, request_id: str):
    from app.models.dealer_kit import Page

    page = db.query(Page).filter(Page.id == _page_id(db, request_id)).first()
    db.expire(page)
    return page.draft_doc


def _doc(marker: str) -> dict:
    return {"kind": "tag_sheet", "sheets": [], "marker": marker}


# ---------------------------------------------------------------------------
# The draft route writes no history (the whole point of the split)
# ---------------------------------------------------------------------------


class TestTheDraftRouteNeverWritesAVersion:
    def test_two_draft_puts_create_zero_versions_and_leave_the_latest_draft(
        self, api
    ):
        client, db = api
        request = _claimed_request(client, db)

        first = client.put(
            f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("one")}
        )
        second = client.put(
            f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("two")}
        )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert _versions(db, request.id) == []
        assert _draft_doc(db, request.id) == _doc("two")

    def test_the_draft_response_says_it_answered_from_the_draft(self, api):
        client, db = api
        request = _claimed_request(client, db)

        body = client.put(
            f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("one")}
        ).json()

        assert body["source"] == "draft"
        assert body["doc"] == _doc("one")
        # No version has been written, so there is no version NUMBER to report.
        assert body["version"] == 0

    def test_it_refuses_from_a_status_the_designer_is_not_offered_from(self, api):
        """Same ``validate_designable`` guard the manual Save route carries
        (S10 review) - a stale tab must not be able to autosave over an
        approved request either."""
        client, db = api
        request = _claimed_request(client, db)
        for status in ("proof_ready", "approved"):
            PriceTagRequestService.transition_status(db, request.id, status)
        db.commit()

        resp = client.put(
            f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("late")}
        )

        assert resp.status_code == 409, resp.text
        assert _draft_doc(db, request.id) is None

    def test_an_unknown_request_is_404(self, api):
        client, _db = api

        resp = client.put(
            f"{_BASE}/{uuid.uuid4()}/design/draft", json={"doc": _doc("nobody")}
        )

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Manual Save is the ONE deliberate act that writes history
# ---------------------------------------------------------------------------


class TestManualSaveSnapshotsTheDraft:
    def test_it_writes_exactly_one_version_equal_to_the_draft_and_clears_it(
        self, api
    ):
        client, db = api
        request = _claimed_request(client, db)
        client.put(f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("one")})
        client.put(f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("two")})

        resp = client.put(f"{_BASE}/{request.id}/design", json={"doc": _doc("two")})

        assert resp.status_code == 200, resp.text
        versions = _versions(db, request.id)
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].doc == _doc("two")
        assert _draft_doc(db, request.id) is None
        assert resp.json()["source"] == "version"

    def test_the_cleared_draft_is_SQL_NULL_and_not_the_json_value_null(self, api):
        """Measured on the lane, 2 Sep: the ORM read said ``None`` while
        ``draft_doc IS NULL`` said false.

        Postgres JSONB can hold the JSON value ``null``, and SQLAlchemy's
        default is to store exactly that for a Python ``None`` - so clearing
        the draft left a row that looks empty through the ORM and full to any
        SQL that asks. Two representations of "nothing in progress", one of
        them invisible until somebody writes a query. ``JSONB(none_as_null=True)``
        on the column is the fix; this asserts through raw SQL, because an ORM
        read is exactly what hid it.
        """
        from sqlalchemy import select

        from app.models.dealer_kit import Page

        client, db = api
        request = _claimed_request(client, db)
        client.put(f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("wip")})

        client.put(f"{_BASE}/{request.id}/design", json={"doc": _doc("wip")})

        # `Page.draft_doc.is_(None)` compiles to `draft_doc IS NULL` and is
        # evaluated by Postgres, so this asks the DATABASE rather than reading
        # a value back through the type that hid the difference. Expressed
        # through the ORM column, not raw SQL, so it resolves through the
        # scratch schema's translate map like everything else here.
        assert (
            db.execute(
                select(Page.draft_doc.is_(None)).where(
                    Page.id == _page_id(db, request.id)
                )
            ).scalar()
            is True
        )

    def test_marking_the_proof_ready_snapshots_a_draft_the_user_never_saved(
        self, api
    ):
        """The designer's own Mark proof ready saves first, but the detail
        page's header can transition a request whose designer tab still holds
        an unsaved draft. Proof rendering reads VERSIONS, so the draft has to
        become one here or the proof shows the last manual save."""
        client, db = api
        request = _claimed_request(client, db)
        client.put(f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("wip")})

        resp = client.post(
            f"{_BASE}/{request.id}/transition", json={"status": "proof_ready"}
        )

        assert resp.status_code == 200, resp.text
        versions = _versions(db, request.id)
        assert len(versions) == 1
        assert versions[0].doc == _doc("wip")
        assert _draft_doc(db, request.id) is None

    def test_marking_the_proof_ready_with_no_draft_writes_nothing(self, api):
        client, db = api
        request = _claimed_request(client, db)
        client.put(f"{_BASE}/{request.id}/design", json={"doc": _doc("saved")})

        resp = client.post(
            f"{_BASE}/{request.id}/transition", json={"status": "proof_ready"}
        )

        assert resp.status_code == 200, resp.text
        assert len(_versions(db, request.id)) == 1


# ---------------------------------------------------------------------------
# GET precedence: reopening the designer lands on the work in progress
# ---------------------------------------------------------------------------


class TestTheGetPrefersTheDraft:
    def test_it_answers_the_draft_when_one_is_present(self, api):
        client, db = api
        request = _claimed_request(client, db)
        client.put(f"{_BASE}/{request.id}/design", json={"doc": _doc("saved")})
        client.put(f"{_BASE}/{request.id}/design/draft", json={"doc": _doc("wip")})

        body = client.get(f"{_BASE}/{request.id}/design").json()

        assert body["doc"] == _doc("wip")
        assert body["source"] == "draft"
        # Still reports which version the draft is sitting on top of.
        assert body["version"] == 1

    def test_it_falls_back_to_the_latest_version_with_no_draft(self, api):
        client, db = api
        request = _claimed_request(client, db)
        client.put(f"{_BASE}/{request.id}/design", json={"doc": _doc("v1")})
        client.put(f"{_BASE}/{request.id}/design", json={"doc": _doc("v2")})

        body = client.get(f"{_BASE}/{request.id}/design").json()

        assert body["doc"] == _doc("v2")
        assert body["source"] == "version"
        assert body["version"] == 2

    def test_a_page_with_neither_answers_nothing_rather_than_erroring(self, api):
        client, db = api
        request = _claimed_request(client, db)

        body = client.get(f"{_BASE}/{request.id}/design").json()

        assert body["doc"] is None
        assert body["version"] == 0
        assert body["source"] == "version"
