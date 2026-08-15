"""The two PDF export routes, over HTTP, with the revision options.

PLAN-portal-submission-revisions 6.3 / 6.4:

  POST /api/v1/procurement/stock-inquiries/{id}/export/pdf
  POST /api/v1/procurement/purchase-requests/{id}/export/pdf
  body (optional): {"revision_id"?: str, "include_revisions"?: bool}

What matters on the wire, and is therefore asserted here:

* no body still works - every existing caller sends none;
* the options reach the RQ task as KEYWORDS, so a job queued by an older release
  (three positional args) keeps running;
* the two options together are a 400, and a revision that is not this record's
  is a 404 - both raised at the route, because the render itself happens on a
  worker where a failure would only surface as a broken row in My Downloads;
* the download row's filename carries the version, so two versions of one form
  do not overwrite each other in a downloads folder.

Auth follows the promotions export test: dependency overrides on a blank schema,
with the permission check stubbed (the permission wiring is not what is under
test here). enqueue_job is captured, never sent to Redis.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (resolves a circular import in guards)
from app.services.portal_revision_service import PortalRevisionService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
    seed_token,
)

_USER_ID = "9c2b1f34-1c2e-4d4b-9e8a-7f6a5b4c3d2e"

SI_EXPORT = "/api/v1/procurement/stock-inquiries/{id}/export/pdf"
PR_EXPORT = "/api/v1/procurement/purchase-requests/{id}/export/pdf"


@pytest.fixture
def ctx(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    with blank_session() as db:

        def _override_get_db():
            yield db

        def _override_user():
            return {"id": _USER_ID, "email": "exporter@test.com"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_user
        # No auth header on the test request -> the router-level scope resolver
        # would compute UNSET (fail-closed) and hide the seeded rows.
        app.dependency_overrides[apply_company_scope] = lambda: None
        monkeypatch.setattr(
            UserPermissionService, "check_user_has_permission", lambda *a, **kw: True
        )

        calls: list = []
        import app.services.queue_service as qs

        monkeypatch.setattr(qs, "enqueue_job", lambda *a, **kw: calls.append((a, kw)))

        try:
            with TestClient(app) as client:
                yield client, db, calls
        finally:
            app.dependency_overrides.clear()


def _seed_with_revision(db, kind):
    """A submitted entity plus one contact revision, so the lineage has two entries."""
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact)
    PortalRevisionService(db).revise(
        seed_token(contact),
        kind,
        str(row.id),
        {"item_description": "Revised description"}
        if kind == "stock_inquiry"
        else {"project_title": "Revised project"},
        "Customer corrected the quantity",
        0,
    )
    entries = PortalRevisionService(db).list_revisions(kind, str(row.id))
    return row, entries


def _download(db, download_id):
    from app.models.download import UserDownload

    return db.query(UserDownload).filter(UserDownload.id == download_id).one()


def _download_id(response) -> str:
    body = response.json()
    return body.get("download_id") or body["id"]


# ------------------------------------------------------------ backwards compatible


def test_purchase_request_export_without_a_body_is_unchanged(ctx):
    client, db, calls = ctx
    row, _entries = _seed_with_revision(db, "purchase_request")

    response = client.post(PR_EXPORT.format(id=row.id))

    assert response.status_code == 200, response.text
    _args, kwargs = calls[-1]
    assert kwargs["revision_id"] is None
    assert kwargs["include_revisions"] is False
    assert _download(db, _download_id(response)).filename.endswith(
        f"{row.request_number}-R1.pdf"
    )


def test_stock_inquiry_export_without_a_body_is_unchanged(ctx):
    client, db, calls = ctx
    row, _entries = _seed_with_revision(db, "stock_inquiry")

    response = client.post(SI_EXPORT.format(id=row.id))

    assert response.status_code == 200, response.text
    _args, kwargs = calls[-1]
    assert kwargs["revision_id"] is None
    assert kwargs["include_revisions"] is False


# ------------------------------------------------------------------ the options


def test_purchase_request_export_passes_the_revision_id_to_the_task(ctx):
    client, db, calls = ctx
    row, entries = _seed_with_revision(db, "purchase_request")
    original = next(e for e in entries if e["version_no"] == 0)

    response = client.post(
        PR_EXPORT.format(id=row.id), json={"revision_id": original["id"]}
    )

    assert response.status_code == 200, response.text
    args, kwargs = calls[-1]
    # Positional args unchanged - the task plus (download_id, entity_id, user_id);
    # the options travel as keywords.
    assert len(args) == 4
    assert kwargs["revision_id"] == original["id"]
    assert kwargs["include_revisions"] is False
    # Version 0's own number is the bare one, which is exactly the current form's
    # filename on a never-revised record - so it keeps an explicit marker.
    assert _download(db, _download_id(response)).filename == (
        f"purchase-request-{row.request_number}-original.pdf"
    )


def test_stock_inquiry_export_names_the_row_after_that_version(ctx):
    """The pending row is named exactly as the artifact will be: one composer,
    used by the route and the service, so the drawer cannot promise one filename
    and hand over another."""
    client, db, calls = ctx
    row, entries = _seed_with_revision(db, "stock_inquiry")
    revision = next(e for e in entries if e["revision_no"] == 1)

    response = client.post(
        SI_EXPORT.format(id=row.id), json={"revision_id": revision["id"]}
    )

    assert response.status_code == 200, response.text
    assert calls[-1][1]["revision_id"] == revision["id"]
    # The record sits at R1 as well, and its own export is a DIFFERENT document
    # (live status, purchasing reply), so the marker keeps the two apart in the
    # drawer.
    assert _download(db, _download_id(response)).filename == (
        f"product-inquiry-{row.inquiry_number}-R1-as-submitted.pdf"
    )


def test_include_revisions_reaches_the_task(ctx):
    client, db, calls = ctx
    row, _entries = _seed_with_revision(db, "stock_inquiry")

    response = client.post(
        SI_EXPORT.format(id=row.id), json={"include_revisions": True}
    )

    assert response.status_code == 200, response.text
    assert calls[-1][1]["include_revisions"] is True
    assert calls[-1][1]["revision_id"] is None
    # The lineage export IS the whole record, so the filename stays the record's.
    assert _download(db, _download_id(response)).filename == (
        f"product-inquiry-{row.inquiry_number}-R1.pdf"
    )


# ------------------------------------------------------------------- validation


@pytest.mark.parametrize("route,kind", [(SI_EXPORT, "stock_inquiry"), (PR_EXPORT, "purchase_request")])
def test_both_options_together_are_rejected(ctx, route, kind):
    client, db, calls = ctx
    row, entries = _seed_with_revision(db, kind)
    original = next(e for e in entries if e["version_no"] == 0)

    response = client.post(
        route.format(id=row.id),
        json={"revision_id": original["id"], "include_revisions": True},
    )

    assert response.status_code == 400, response.text
    assert not calls  # nothing queued, and no download row to explain away


@pytest.mark.parametrize("route,kind", [(SI_EXPORT, "stock_inquiry"), (PR_EXPORT, "purchase_request")])
def test_an_unknown_revision_id_is_a_404(ctx, route, kind):
    client, db, calls = ctx
    row, _entries = _seed_with_revision(db, kind)

    response = client.post(
        route.format(id=row.id), json={"revision_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404, response.text
    assert not calls


@pytest.mark.parametrize("route,kind", [(SI_EXPORT, "stock_inquiry"), (PR_EXPORT, "purchase_request")])
def test_a_revision_of_another_record_is_a_404(ctx, route, kind):
    """A real revision id from a different submission is still a 404: the export
    is scoped to ONE record's lineage."""
    client, db, calls = ctx
    row, _entries = _seed_with_revision(db, kind)

    other_contact = seed_contact(db)
    other_row = seed_entity(db, kind, other_contact)
    PortalRevisionService(db).revise(
        seed_token(other_contact),
        kind,
        str(other_row.id),
        {"item_description": "Other"} if kind == "stock_inquiry" else {"purpose": "Other"},
        "Another correction",
        0,
    )
    other_entries = PortalRevisionService(db).list_revisions(kind, str(other_row.id))

    response = client.post(
        route.format(id=row.id), json={"revision_id": other_entries[0]["id"]}
    )

    assert response.status_code == 404, response.text
    assert not calls
