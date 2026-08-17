"""The outbound kill switch, driven from the screen instead of the CLI.

`scripts/set_contact_outbound.py` could already do all of this, but a script is
not delivered: nobody can see WHO is silenced without shelling into a box. These
routes back System Management -> Respond.io Contacts.

What is pinned here:
  - the list carries whole-table counts, so the page can say "X can be messaged,
    Y are silenced" without a second request;
  - a read needs `system.respond_workspaces.view`; every WRITE needs `.edit`, so
    a read-only admin cannot silence a customer;
  - the kill switch (`all: true`) and the selection path are the SAME endpoint,
    and asking for both at once is a 422, never a guess;
  - every write delegates to `respond_outbound_service`, so the route can never
    drift from what the CLI does.

Run: pytest tests/test_respond_contacts_outbound_routes.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import RespondContact
from tests._pg_fixture import blank_session

URL = "/api/v1/system/respond-contacts"
VIEW_PERM = "system.respond_workspaces.view"
EDIT_PERM = "system.respond_workspaces.edit"


@pytest.fixture
def db():
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _seed(db, *, name: str, enabled: bool = True, phone: str | None = None) -> RespondContact:
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone or f"+6011{str(uuid.uuid4().int)[:8]}",
        name=name,
        respond_io_id=str(uuid.uuid4().int)[:9],
        session_vars={},
        outbound_enabled=enabled,
    )
    db.add(row)
    db.commit()
    return row


def _client(db, *, granted: set[str]):
    """A TestClient whose principal holds exactly `granted`."""
    from app.database import get_db as database_get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db as dependencies_get_db,
    )
    from app.main import app
    from app.services.user_service import UserPermissionService

    user = {"id": "zzt-admin"}
    app.dependency_overrides[database_get_db] = lambda: db
    app.dependency_overrides[dependencies_get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user

    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug in granted
    )
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        UserPermissionService.check_user_has_permission = original
        app.dependency_overrides.clear()


@pytest.fixture
def client(db):
    yield from _client(db, granted={VIEW_PERM, EDIT_PERM})


@pytest.fixture
def read_only_client(db):
    yield from _client(db, granted={VIEW_PERM})


@pytest.fixture
def no_permission_client(db):
    yield from _client(db, granted=set())


# --------------------------------------------------------------------------
# GET - the list, and the audit line above it
# --------------------------------------------------------------------------


def test_list_returns_the_contact_and_its_switch(client, db):
    contact = _seed(db, name="ZZT Aisyah", enabled=False)

    resp = client.get(URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = next(r for r in body["data"] if r["id"] == contact.id)
    assert row["name"] == "ZZT Aisyah"
    assert row["phone_number"] == contact.phone_number
    assert row["respond_io_id"] == contact.respond_io_id
    assert row["outbound_enabled"] is False


def test_list_carries_whole_table_counts(client, db):
    _seed(db, name="ZZT On 1", enabled=True)
    _seed(db, name="ZZT On 2", enabled=True)
    _seed(db, name="ZZT Off", enabled=False)

    body = client.get(URL).json()
    assert body["counts"] == {"enabled": 2, "disabled": 1, "total": 3}


def test_counts_ignore_the_filter_so_the_audit_stays_honest(client, db):
    _seed(db, name="ZZT On", enabled=True)
    _seed(db, name="ZZT Off", enabled=False)

    body = client.get(URL, params={"outbound": "disabled"}).json()
    assert len(body["data"]) == 1, "the grid shows only the disabled contact"
    assert body["counts"] == {"enabled": 1, "disabled": 1, "total": 2}, (
        "the counts describe the whole table, not the current page"
    )


def test_empty_table_is_a_200_with_empty_true(client, db):
    body = client.get(URL).json()
    assert body["data"] == []
    assert body["empty"] is True
    assert body["counts"] == {"enabled": 0, "disabled": 0, "total": 0}


@pytest.mark.parametrize("field", ["name", "phone_number", "respond_io_id"])
def test_search_matches_name_phone_and_respond_id(client, db, field):
    wanted = _seed(db, name="ZZT Findable", enabled=True)
    _seed(db, name="ZZT Other", enabled=True)

    term = getattr(wanted, field)
    body = client.get(URL, params={"query": term}).json()
    assert [r["id"] for r in body["data"]] == [wanted.id], f"search by {field} failed"


def test_search_is_case_insensitive(client, db):
    wanted = _seed(db, name="ZZT Nurul Huda", enabled=True)

    body = client.get(URL, params={"query": "nurul"}).json()
    assert [r["id"] for r in body["data"]] == [wanted.id]


def test_outbound_filter_selects_the_enabled_slice(client, db):
    on = _seed(db, name="ZZT On", enabled=True)
    _seed(db, name="ZZT Off", enabled=False)

    body = client.get(URL, params={"outbound": "enabled"}).json()
    assert [r["id"] for r in body["data"]] == [on.id]


def test_pagination_reports_the_full_total(client, db):
    for i in range(3):
        _seed(db, name=f"ZZT Page {i}", enabled=True)

    body = client.get(URL, params={"page": 1, "limit": 2}).json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {"total": 3, "page": 1, "limit": 2}


def test_list_denied_without_the_view_permission(no_permission_client, db):
    _seed(db, name="ZZT Hidden", enabled=True)
    assert no_permission_client.get(URL).status_code == 403


# --------------------------------------------------------------------------
# POST /{id}/outbound - one contact
# --------------------------------------------------------------------------


def test_disable_one_contact(client, db):
    contact = _seed(db, name="ZZT Mute Me", enabled=True)

    resp = client.post(f"{URL}/{contact.id}/outbound", json={"enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["outbound_enabled"] is False

    db.expire_all()
    assert db.get(RespondContact, contact.id).outbound_enabled is False


def test_enable_one_contact_again(client, db):
    contact = _seed(db, name="ZZT Unmute Me", enabled=False)

    resp = client.post(f"{URL}/{contact.id}/outbound", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["outbound_enabled"] is True


def test_setting_the_value_it_already_has_is_not_an_error(client, db):
    contact = _seed(db, name="ZZT Already Off", enabled=False)

    resp = client.post(f"{URL}/{contact.id}/outbound", json={"enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["outbound_enabled"] is False


def test_unknown_contact_is_a_404(client, db):
    resp = client.post(f"{URL}/{uuid.uuid4()}/outbound", json={"enabled": False})
    assert resp.status_code == 404, resp.text


def test_missing_enabled_is_a_422(client, db):
    contact = _seed(db, name="ZZT No Body", enabled=True)
    assert client.post(f"{URL}/{contact.id}/outbound", json={}).status_code == 422


def test_a_read_only_admin_cannot_silence_a_contact(read_only_client, db):
    contact = _seed(db, name="ZZT Protected", enabled=True)

    resp = read_only_client.post(f"{URL}/{contact.id}/outbound", json={"enabled": False})
    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.get(RespondContact, contact.id).outbound_enabled is True


# --------------------------------------------------------------------------
# POST /outbound/bulk - the selection AND the kill switch
# --------------------------------------------------------------------------


def test_bulk_disables_only_the_selected_contacts(client, db):
    a = _seed(db, name="ZZT Bulk A", enabled=True)
    b = _seed(db, name="ZZT Bulk B", enabled=True)
    untouched = _seed(db, name="ZZT Bulk C", enabled=True)

    resp = client.post(
        f"{URL}/outbound/bulk", json={"enabled": False, "contact_ids": [a.id, b.id]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested"] == 2
    assert body["changed"] == 2
    assert body["counts"] == {"enabled": 1, "disabled": 2, "total": 3}

    db.expire_all()
    assert db.get(RespondContact, untouched.id).outbound_enabled is True


def test_bulk_counts_only_what_actually_changed(client, db):
    already_off = _seed(db, name="ZZT Off Already", enabled=False)
    on = _seed(db, name="ZZT Still On", enabled=True)

    body = client.post(
        f"{URL}/outbound/bulk",
        json={"enabled": False, "contact_ids": [already_off.id, on.id]},
    ).json()
    assert body["requested"] == 2
    assert body["changed"] == 1, "an already-disabled contact is not a change"


def test_bulk_deduplicates_repeated_ids(client, db):
    contact = _seed(db, name="ZZT Dup", enabled=True)

    body = client.post(
        f"{URL}/outbound/bulk",
        json={"enabled": False, "contact_ids": [contact.id, contact.id, contact.id]},
    ).json()
    assert body["requested"] == 1


def test_bulk_re_enables_a_selection(client, db):
    a = _seed(db, name="ZZT Back On A", enabled=False)
    b = _seed(db, name="ZZT Back On B", enabled=False)

    body = client.post(
        f"{URL}/outbound/bulk", json={"enabled": True, "contact_ids": [a.id, b.id]}
    ).json()
    assert body["changed"] == 2
    assert body["counts"]["disabled"] == 0


def test_all_true_is_the_kill_switch(client, db):
    for i in range(4):
        _seed(db, name=f"ZZT Everyone {i}", enabled=True)

    resp = client.post(f"{URL}/outbound/bulk", json={"enabled": False, "all": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed"] == 4
    assert body["counts"] == {"enabled": 0, "disabled": 4, "total": 4}

    db.expire_all()
    assert (
        db.query(RespondContact).filter(RespondContact.outbound_enabled.is_(True)).count()
        == 0
    ), "the kill switch left someone reachable"


def test_all_true_re_enables_everyone(client, db):
    for i in range(3):
        _seed(db, name=f"ZZT Recover {i}", enabled=False)

    body = client.post(f"{URL}/outbound/bulk", json={"enabled": True, "all": True}).json()
    assert body["changed"] == 3
    assert body["counts"]["enabled"] == 3


def test_all_true_reports_requested_as_the_whole_table(client, db):
    _seed(db, name="ZZT Whole 1", enabled=True)
    _seed(db, name="ZZT Whole 2", enabled=False)

    body = client.post(f"{URL}/outbound/bulk", json={"enabled": False, "all": True}).json()
    assert body["requested"] == 2
    assert body["changed"] == 1


def test_neither_ids_nor_all_is_a_422(client, db):
    _seed(db, name="ZZT Guard", enabled=True)
    resp = client.post(f"{URL}/outbound/bulk", json={"enabled": False})
    assert resp.status_code == 422, resp.text


def test_empty_id_list_is_a_422_not_a_silent_no_op(client, db):
    resp = client.post(f"{URL}/outbound/bulk", json={"enabled": False, "contact_ids": []})
    assert resp.status_code == 422, resp.text


def test_ids_and_all_together_is_a_422(client, db):
    contact = _seed(db, name="ZZT Ambiguous", enabled=True)

    resp = client.post(
        f"{URL}/outbound/bulk",
        json={"enabled": False, "all": True, "contact_ids": [contact.id]},
    )
    assert resp.status_code == 422, resp.text

    db.expire_all()
    assert db.get(RespondContact, contact.id).outbound_enabled is True, (
        "an ambiguous request must change nothing"
    )


def test_bulk_with_an_unknown_id_is_a_404_and_writes_nothing(client, db):
    contact = _seed(db, name="ZZT Partial", enabled=True)

    resp = client.post(
        f"{URL}/outbound/bulk",
        json={"enabled": False, "contact_ids": [contact.id, str(uuid.uuid4())]},
    )
    assert resp.status_code == 404, resp.text

    db.expire_all()
    assert db.get(RespondContact, contact.id).outbound_enabled is True, (
        "a bulk write must be all-or-nothing, not half applied"
    )


def test_a_read_only_admin_cannot_pull_the_kill_switch(read_only_client, db):
    contact = _seed(db, name="ZZT Safe", enabled=True)

    resp = read_only_client.post(f"{URL}/outbound/bulk", json={"enabled": False, "all": True})
    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.get(RespondContact, contact.id).outbound_enabled is True


def test_bulk_denied_without_any_permission(no_permission_client, db):
    _seed(db, name="ZZT Denied", enabled=True)
    resp = no_permission_client.post(
        f"{URL}/outbound/bulk", json={"enabled": False, "all": True}
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# The route is a thin shell over the service the CLI already uses
# --------------------------------------------------------------------------


def test_the_routes_reuse_the_outbound_service(client, db, monkeypatch):
    """No second copy of the switch logic hiding in the router."""
    import app.api.v1.system.respond_contacts as mod

    for name in ("set_contact_outbound", "set_all_outbound", "status_counts"):
        assert hasattr(mod, name), f"the router must import {name} from the service"

    from app.services import respond_outbound_service

    assert mod.set_contact_outbound is respond_outbound_service.set_contact_outbound
    assert mod.set_all_outbound is respond_outbound_service.set_all_outbound
    assert mod.status_counts is respond_outbound_service.status_counts
