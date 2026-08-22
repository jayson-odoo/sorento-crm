"""S4 quotation template ROUTES (UAC-project-quotation-document, Group E).

Written against the UAC rather than against the handlers: nothing here was derived from reading
``app/api/v1/projects/quotation_templates.py``, so it states what the routes owe a client rather
than restating what they happen to do. The sibling suite
``test_project_quotation_template.py`` already proves the rules; this proves they reach the wire.

The three cases worth the most:

- **The merge-field registry is served by the backend** (AC-E4). The FE picker and the renderer
  must not drift, and the only way to guarantee that is one declared list, served. A picker with
  its own hardcoded copy is a hole in a customer letter waiting to happen.
- **A refusal arrives as a 422 the admin can act on**, naming the mistyped token. A 500, or a
  200 that quietly saved the typo, both end with the raw `{{token}}` on letterhead.
- **Setup permission is actually enforced.** These routes rewrite the letter every future
  quotation carries; a salesperson holding only project permissions must not reach them.

Postgres only, via ``blank_session``. Every row carries the ``zzt-qtmplroute`` marker.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from app.models.user import User

from ._pg_fixture import blank_session

MARKER = "zzt-qtmplroute"

# The project router mounts under the project-sales module prefix, and template administration
# sits on the same /config surface as project types and templates.
BASE = "/api/v1/project-sales/config/quotation-templates"

VIEW = "projects.types.view"
EDIT = "projects.types.edit"

ALL_SLUGS = [
    "projects.projects.view",
    "projects.projects.edit",
    "projects.projects.delete",
    "projects.projects.manage",
    VIEW,
    EDIT,
]

COVER_LETTER = "cover_letter"
TERMS = "terms"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    # The router-level resolver would otherwise re-stamp the scope from a request that carries
    # no active company (see tests/test_project_quotation_routes.py).
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(ALL_SLUGS)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@contextmanager
def _without_permission(slug: str):
    """Run the block as a user holding every project permission EXCEPT ``slug``."""
    from app.services.user_service import UserPermissionService

    granted = [s for s in ALL_SLUGS if s != slug]
    original_check = UserPermissionService.check_user_has_permission
    original_slugs = UserPermissionService.get_user_permission_slugs
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, wanted, _denied=slug: wanted != _denied
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    try:
        yield
    finally:
        UserPermissionService.check_user_has_permission = original_check
        UserPermissionService.get_user_permission_slugs = original_slugs


@pytest.fixture()
def api():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        user_id = _user(db, f"{MARKER} Admin")
        db.commit()
        client, originals = _client(db, user_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id
        finally:
            _restore(originals)


def _create(client, *, kind=COVER_LETTER, name=None, body=None, is_active=None):
    payload = {
        "kind": kind,
        "name": name or f"{MARKER} Standard letter",
        "body_html": body if body is not None else "<p>Dear {{attn_name}}</p>",
    }
    if is_active is not None:
        payload["is_active"] = is_active
    return client.post(BASE, json=payload)


# ------------------------------------------------------------------- happy path


def test_an_admin_can_create_list_and_switch_the_active_template(api):
    """The whole admin journey in one pass: write a letter, write its replacement, switch over.

    The switch is the part that matters on the wire. If the response said the new one was active
    while the list still showed the old one active too, an admin would have no way to tell which
    letter the next quotation carries.
    """
    client, _db, _company_id = api

    created = _create(client, name=f"{MARKER} 2025 letter", body="<p>Old wording</p>")
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["kind"] == COVER_LETTER
    assert first["name"] == f"{MARKER} 2025 letter"
    assert first["body_html"] == "<p>Old wording</p>"
    # The first template of a kind arrives active, or a company has a template and no letter.
    assert first["is_active"] is True

    second = _create(client, name=f"{MARKER} 2026 letter", body="<p>New wording</p>")
    assert second.status_code == 201, second.text
    second = second.json()
    assert second["is_active"] is False

    listed = client.get(BASE, params={"kind": COVER_LETTER})
    assert listed.status_code == 200, listed.text
    rows = {row["id"]: row for row in listed.json()["data"]}
    assert set(rows) >= {first["id"], second["id"]}
    assert rows[first["id"]]["is_active"] is True
    assert rows[second["id"]]["is_active"] is False

    activated = client.post(f"{BASE}/{second['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True

    listed = client.get(BASE, params={"kind": COVER_LETTER})
    rows = {row["id"]: row for row in listed.json()["data"]}
    assert rows[second["id"]]["is_active"] is True
    assert rows[first["id"]]["is_active"] is False, "two letters both claim to be the active one"

    # And the single row reads back through its own URL, which is what the edit modal loads.
    one = client.get(f"{BASE}/{second['id']}")
    assert one.status_code == 200, one.text
    assert one.json()["body_html"] == "<p>New wording</p>"

    edited = client.put(
        f"{BASE}/{second['id']}",
        json={"name": f"{MARKER} 2026 letter v2", "body_html": "<p>{{project_title}}</p>"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["body_html"] == "<p>{{project_title}}</p>"


def test_the_merge_field_registry_is_served_by_the_backend(api):
    """One declared list, served, so the FE picker cannot offer a token the renderer does not
    know. Each entry carries a human label and an example value, because "{{our_ref}}" alone
    tells an admin nothing about what will appear in its place."""
    client, _db, _company_id = api

    response = client.get(f"{BASE}/merge-fields")
    assert response.status_code == 200, response.text
    fields = response.json()["data"]
    assert fields, "the picker would have nothing to offer"

    by_token = {field["token"]: field for field in fields}
    # The facts the letter in the real artifact actually needs (AC-E1).
    for token in (
        "project_title",
        "developer_name",
        "recipient_name",
        "attn_name",
        "our_ref",
        "doc_date",
        "subject_title",
        "grand_total",
        "salesperson_name",
        "company_name",
    ):
        assert token in by_token, f"{token} is not offered by the picker"
        assert by_token[token]["label"]
        assert by_token[token]["example"]
        assert by_token[token]["placeholder"] == "{{" + token + "}}"


def test_the_registry_is_readable_by_a_viewer_but_not_writable(api):
    """Reading the picker is a view; rewriting the company letter is not. Both gates asserted
    on the same surface, because it is the one screen where the two are easy to conflate."""
    client, _db, _company_id = api

    with _without_permission(EDIT):
        refused = _create(client)
        assert refused.status_code == 403, refused.text
        # The read is still allowed: the picker renders for anyone who can see setup.
        assert client.get(f"{BASE}/merge-fields").status_code == 200

    with _without_permission(VIEW):
        assert client.get(BASE).status_code == 403


# -------------------------------------------------------------------- validation


def test_a_mistyped_merge_token_is_refused_with_a_422_that_names_it(api):
    """An admin cannot find `{{grand_totals}}` in a page of HTML. The refusal has to name the
    token, and it has to be a 422 the modal can render rather than a 500."""
    client, _db, _company_id = api

    refused = _create(client, body="<p>{{grand_totals}} and {{projekt_title}}</p>")
    assert refused.status_code == 422, refused.text
    body = refused.text
    assert "grand_totals" in body
    assert "projekt_title" in body

    # Nothing was saved.
    listed = client.get(BASE).json()["data"]
    assert not listed, "the refused template was stored anyway"


def test_a_template_needs_a_name_and_a_body(api):
    """A nameless template is unpickable in a list, and an empty one renders an empty letter
    that looks like the feature is broken."""
    client, _db, _company_id = api

    assert _create(client, name="   ").status_code == 422
    assert _create(client, body="").status_code == 422
    assert _create(client, kind="invoice_footer").status_code == 422


def test_an_unknown_template_is_a_404_not_a_500(api):
    """Through the app's own error envelope, so the modal can render the message. A bare
    framework 404 ("Not Found") would also be a 404 and tells the admin nothing."""
    client, _db, _company_id = api

    missing = client.get(f"{BASE}/{_uid()}")
    assert missing.status_code == 404, missing.text
    body = missing.json()
    assert "template" in (body.get("message") or "").lower(), missing.text
    assert body.get("code") == "quotation_template_not_found"


# ------------------------------------------------------------------------ delete


def test_deleting_the_active_template_is_refused_so_a_company_is_never_left_without_one(api):
    """Hard delete, and refused for the one row the company actually depends on. Without the
    refusal the next document created carries an empty letter and nothing reports an error, so
    the failure surfaces as a salesperson emailing a blank page."""
    client, _db, _company_id = api

    active = _create(client, name=f"{MARKER} Active letter").json()
    spare = _create(client, name=f"{MARKER} Spare letter").json()
    assert active["is_active"] is True and spare["is_active"] is False

    refused = client.delete(f"{BASE}/{active['id']}")
    assert refused.status_code == 422, refused.text

    still_there = client.get(f"{BASE}/{active['id']}")
    assert still_there.status_code == 200, "the refusal deleted it anyway"

    gone = client.delete(f"{BASE}/{spare['id']}")
    assert gone.status_code == 200, gone.text
    assert client.get(f"{BASE}/{spare['id']}").status_code == 404


def test_deleting_needs_the_setup_permission(api):
    client, _db, _company_id = api

    spare = _create(client, name=f"{MARKER} Doomed letter").json()
    _create(client, name=f"{MARKER} Keeper letter", is_active=True)

    with _without_permission(EDIT):
        assert client.delete(f"{BASE}/{spare['id']}").status_code == 403
