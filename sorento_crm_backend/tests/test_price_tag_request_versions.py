"""r9 S5/D19: a request's own design history (AC-S5-6).

Templates have had a version list, a viewer and a restore since r4. Requests
have been WRITING versions the whole time - ``_snapshot_draft`` fires on every
manual Save and on proof_ready - and offering no way to read one back, so the
history existed and was unreachable.

Three things worth stating, because a naive implementation gets each wrong:

* newest FIRST. A list that grows downwards buries the version somebody wants.
* a version carries ``pinned_line_data`` (D19). Restoring the document without
  the pins puts old artwork over today's prices, which is worse than not
  restoring at all.
* Restore ADDS a version ("Restored v<n>") rather than truncating the history.
  That is why it needs no confirmation: the way back is the list itself.

Red before the coder starts: the three routes and the column do not exist.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

_CRM = "/api/v1/dealer-kit/price-tag-requests/{id}"


@pytest.fixture(autouse=True)
def quiet_notifier(monkeypatch):
    try:
        from app.services import price_tag_notify
    except ImportError:
        return
    monkeypatch.setattr(price_tag_notify, "notify_salesperson", lambda *a, **k: None)


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


def _request_with_three_versions(db):
    """A designing request whose page carries versions 1, 2 and 3."""
    from app.services.price_tag_request_service import PriceTagRequestService

    product = seed.seed_product(db)
    contact_id = seed.seed_portal_contact(db)
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
    page, doc = seed.attach_design(db, request)

    from app.models.dealer_kit import PageVersion

    for version, message in ((2, "Saved"), (3, "Marked proof ready")):
        db.add(
            PageVersion(
                page_id=page.id,
                version=version,
                doc={**doc, "sheets": [{"id": f"sheet-v{version}", "tags": []}]},
                commit_message=message,
            )
        )
    db.flush()
    db.commit()
    return request, page, doc


class TestTheVersionList:
    def test_it_lists_newest_first_with_a_readable_author(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        response = client.get(f"{_CRM.format(id=request.id)}/versions")

        assert response.status_code == 200, response.text
        rows = response.json()
        assert [row["version"] for row in rows] == [3, 2, 1]
        assert rows[0]["commit_message"] == "Marked proof ready"
        for row in rows:
            assert "created_by_name" in row, "no UUID reaches a screen"
            assert "created_at" in row

    def test_a_request_with_no_page_answers_an_empty_list_not_a_404(self, crm):
        """An empty history is a state the sheet draws, not an error."""
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request = seed.seed_request(
            db, contact_id, status="new", products=[seed.seed_product(db)]
        )

        response = client.get(f"{_CRM.format(id=request.id)}/versions")

        assert response.status_code == 200, response.text
        assert response.json() == []


class TestReadingOneVersion:
    def test_it_answers_the_full_design_payload_for_that_version(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        response = client.get(f"{_CRM.format(id=request.id)}/versions/2")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["version"] == 2
        assert body["doc"]["sheets"][0]["id"] == "sheet-v2"
        for key in ("lines", "assets", "images", "fonts"):
            assert key in body, (
                f"missing {key!r} - a version opens in the shared lightbox "
                "(D19), which needs the same media maps a live design needs"
            )

    def test_a_version_that_does_not_exist_404s(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        assert client.get(f"{_CRM.format(id=request.id)}/versions/99").status_code == 404


class TestRestore:
    def test_it_writes_the_doc_and_the_pins_back_and_adds_a_version(self, crm):
        client, db = crm
        from app.models.dealer_kit import Page, PageVersion
        from app.models.price_tag import PriceTagRequestLine

        request, page, _doc = _request_with_three_versions(db)
        # Version 1 is the one the pins were taken with; move the pin on since,
        # so a restore that only put the DOC back would be visible.
        version_one = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id, PageVersion.version == 1)
            .first()
        )
        version_one.pinned_line_data = {
            request.lines[0].id: {"code": "ZZT-PINNED-V1", "list_price": 111.0}
        }
        db.query(PriceTagRequestLine).filter(
            PriceTagRequestLine.request_id == request.id
        ).update({"pinned_tag_data": {"code": "ZZT-MOVED-ON", "list_price": 999.0}})
        db.commit()

        response = client.post(f"{_CRM.format(id=request.id)}/versions/1/restore")

        assert response.status_code == 200, response.text
        assert response.json()["version"] == 4

        db.expire_all()
        versions = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page.id)
            .order_by(PageVersion.version)
            .all()
        )
        assert [row.version for row in versions] == [1, 2, 3, 4], (
            "Restore adds to the history, it does not truncate it"
        )
        assert versions[-1].commit_message == "Restored v1"

        restored_page = db.query(Page).filter(Page.id == page.id).first()
        drawn = restored_page.draft_doc or versions[-1].doc
        assert drawn["sheets"][0]["id"] == "sheet-1"

        line = (
            db.query(PriceTagRequestLine)
            .filter(PriceTagRequestLine.request_id == request.id)
            .first()
        )
        assert line.pinned_tag_data["code"] == "ZZT-PINNED-V1", (
            "the pins are half the version - a doc restored over today's data "
            "shows old artwork at new prices"
        )

    def test_restoring_a_version_that_does_not_exist_404s(self, crm):
        client, db = crm
        request, _page, _doc = _request_with_three_versions(db)

        assert (
            client.post(f"{_CRM.format(id=request.id)}/versions/99/restore").status_code
            == 404
        )
