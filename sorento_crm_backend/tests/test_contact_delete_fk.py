"""CONTACT-DELETE-FK: deleting a contact that other records still reference.

A. `price_tag_requests.contact_id` is the one FK on `respond_contacts` with no ON DELETE,
   so deleting a contact that ever raised a price tag request died with a
   ForeignKeyViolation. Business history (price tag requests, ticket comments) is never
   destroyed: the delete is refused with a message naming what is linked. Link rows
   (tags, agent assignments, company links) still go with the contact.
B. The raw psycopg / SQLAlchemy text (SQL, constraint names, ids) reached the toast through
   `handle_internal_error(str(e))`. It must never leave the server.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.main  # noqa: F401 - registers every model before any query
from app.database import engine
from app.services.error_handler import AppException, handle_internal_error

# What the prod toast carried. Any of these in a client body is the defect.
_LEAK_MARKERS = ("[SQL:", "psycopg", "ForeignKeyViolation", "_fkey", "sqlalche.me")


@pytest.fixture
def db() -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _contact(db: Session) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, 'ZZT contact')"),
        {"i": cid, "p": f"+000{uuid.uuid4().int % 10**12:012d}"},
    )
    return cid


def _price_tag_request(db: Session, contact_id: str) -> str:
    rid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO price_tag_requests (id, contact_id, doc_number) VALUES (:i, :c, :d)"),
        {"i": rid, "c": contact_id, "d": f"ZZT{uuid.uuid4().hex[:20]}"},
    )
    return rid


def _ticket_comment(db: Session, contact_id: str) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO conversation_ticket_comments (id, respond_contact_id, body, source) "
            "VALUES (:i, :c, 'ZZT note', 'respond')"
        ),
        {"i": cid, "c": contact_id},
    )
    return cid


def _tag_link(db: Session, contact_id: str) -> None:
    tag_id = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO contact_tags (id, name) VALUES (:i, :n)"),
        {"i": tag_id, "n": f"ZZT{uuid.uuid4().hex[:12]}"},
    )
    db.execute(
        text("INSERT INTO respond_contact_tags (contact_id, tag_id) VALUES (:c, :t)"),
        {"c": contact_id, "t": tag_id},
    )


def _exists(db: Session, table: str, row_id: str, col: str = "id") -> bool:
    return db.execute(text(f"SELECT 1 FROM {table} WHERE {col} = :i"), {"i": row_id}).first() is not None


def _service(db: Session):
    from app.services.contact_service import ContactService

    return ContactService(db)


# --------------------------------------------------------------------------- #
# A. single delete
# --------------------------------------------------------------------------- #


def test_delete_contact_with_a_price_tag_request_is_refused_and_names_it(db: Session) -> None:
    contact_id = _contact(db)
    request_id = _price_tag_request(db, contact_id)
    _price_tag_request(db, contact_id)

    with pytest.raises(AppException) as exc_info:
        _service(db).delete_contact(contact_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == (
        "This contact has 2 price tag requests; it cannot be deleted."
    )
    assert _exists(db, "respond_contacts", contact_id)
    assert _exists(db, "price_tag_requests", request_id)


def test_delete_contact_with_ticket_comments_is_refused_and_keeps_them(db: Session) -> None:
    contact_id = _contact(db)
    comment_id = _ticket_comment(db, contact_id)
    _price_tag_request(db, contact_id)

    with pytest.raises(AppException) as exc_info:
        _service(db).delete_contact(contact_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == (
        "This contact has 1 price tag request and 1 ticket comment; it cannot be deleted."
    )
    assert _exists(db, "conversation_ticket_comments", comment_id)


def test_kill_a_contact_with_only_link_rows_is_still_deleted(db: Session) -> None:
    """Kill test: the guard must not become "never delete" - assignment / link rows go
    with the contact, as the dialog says."""
    contact_id = _contact(db)
    _tag_link(db, contact_id)

    _service(db).delete_contact(contact_id)

    assert not _exists(db, "respond_contacts", contact_id)
    assert not _exists(db, "respond_contact_tags", contact_id, col="contact_id")


# --------------------------------------------------------------------------- #
# A. bulk delete: delete what is deletable, report the rest per contact
# --------------------------------------------------------------------------- #


def test_bulk_delete_deletes_the_free_and_reports_the_linked(db: Session) -> None:
    free_id = _contact(db)
    linked_id = _contact(db)
    _price_tag_request(db, linked_id)

    result = _service(db).bulk_delete_contacts([free_id, linked_id])

    assert result["deleted_count"] == 1
    assert result["blocked"] == [
        {
            "id": linked_id,
            "name": "ZZT contact",
            "reason": "This contact has 1 price tag request; it cannot be deleted.",
        }
    ]
    assert result["message"] == (
        "Deleted 1 contact. 1 contact was not deleted because it has linked records."
    )
    assert not _exists(db, "respond_contacts", free_id)
    assert _exists(db, "respond_contacts", linked_id)


def test_kill_bulk_delete_with_nothing_linked_reports_nothing_blocked(db: Session) -> None:
    ids = [_contact(db), _contact(db)]

    result = _service(db).bulk_delete_contacts(ids)

    assert result["deleted_count"] == 2
    assert result["blocked"] == []
    assert result["message"] == "Deleted 2 contacts."


# --------------------------------------------------------------------------- #
# B. no SQL text reaches the client
# --------------------------------------------------------------------------- #


def _fk_error() -> IntegrityError:
    orig = Exception(
        'update or delete on table "respond_contacts" violates foreign key constraint '
        '"price_tag_requests_contact_id_fkey" on table "price_tag_requests"'
    )
    return IntegrityError("DELETE FROM respond_contacts WHERE respond_contacts.id = %(id)s", {"id": "x"}, orig)


def test_handle_internal_error_never_carries_db_error_text() -> None:
    exc = handle_internal_error(str(_fk_error()))

    body = exc.detail
    assert body["code"] == "INTERNAL_ERROR"
    for marker in _LEAK_MARKERS:
        assert marker not in str(body), f"{marker!r} leaked: {body}"
    assert body["message"] == "Oops! Something went wrong. Please try again in a moment."


def test_kill_handle_internal_error_keeps_a_plain_message() -> None:
    """Kill test: a caller's own readable message is not swallowed."""
    exc = handle_internal_error("Failed to render the catalogue.")

    assert exc.detail["message"] == "Failed to render the catalogue."


def _client(db: Session):
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.main import app

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4())}
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def allow_all(monkeypatch):
    from app.main import app
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    app.dependency_overrides.clear()


def test_delete_route_refuses_a_linked_contact_with_a_readable_409(db: Session, allow_all) -> None:
    contact_id = _contact(db)
    _price_tag_request(db, contact_id)

    resp = _client(db).delete(f"/api/v1/user-management/contacts/{contact_id}")

    assert resp.status_code == 409, resp.text
    assert resp.json()["message"] == "This contact has 1 price tag request; it cannot be deleted."
    for marker in _LEAK_MARKERS:
        assert marker not in resp.text


def test_delete_route_never_returns_sql_text_on_an_integrity_error(db: Session, allow_all, monkeypatch) -> None:
    from app.services.contact_service import ContactService

    def _boom(self, contact_id):
        raise _fk_error()

    monkeypatch.setattr(ContactService, "delete_contact", _boom)

    resp = _client(db).delete(f"/api/v1/user-management/contacts/{uuid.uuid4()}")

    assert resp.status_code == 500
    for marker in _LEAK_MARKERS:
        assert marker not in resp.text, f"{marker!r} leaked: {resp.text}"
