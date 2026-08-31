"""Group D - Upload, move, create rules (backend rows: AC-D1..D7).

`documentation/plans/multi-company/shared-brand-attachments-acceptance-criteria.md`.
Postgres only via `tests/_pg_fixture.py::blank_session`, own seeded `ZZT-` chain
per test. AC-D8 (the FE checkbox) is out of scope here.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import set_company_scope
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.schemas.resources import AttachmentDirectoryCreate, AttachmentUpdate
from app.services.resources_service import AttachmentDirectoryService, AttachmentService

from tests import _shared_brand_seed as seed
from tests._pg_fixture import blank_session, unique_code

SORENTO = seed.SORENTO_ID
MOCHA = seed.MOCHA_ID


@pytest.fixture
def db():
    with blank_session() as session:
        seed.seed_mocha(session)
        yield session


def _payload(db, *, type_id: str, directory_id: str | None = None, **overrides):
    from app.schemas.resources import AttachmentCreate

    fn = f"{unique_code('file')}.pdf"
    data = dict(
        id=str(uuid.uuid4()),
        attachment_type_id=type_id,
        original_filename=fn,
        stored_filename=fn,
        file_path=f"https://cdn.test/{fn}",
        file_size_bytes=100,
        mime_type="application/pdf",
        file_hash=uuid.uuid4().hex,
        storage_provider="r2",
        directory_id=directory_id,
    )
    data.update(overrides)
    return AttachmentCreate(**data)


# --------------------------------------------------------------------------- #
# AC-D1 - a SHARED type uploads NULL and pulls the owned destination chain up
# --------------------------------------------------------------------------- #


def test_ac_d1_shared_type_upload_nulls_the_file_and_the_ancestor_chain(db):
    t = seed.att_type(db, is_shared=True, name="ZZT-Photos")
    root_owned = seed.folder(db, company_id=SORENTO, name="ZZT-parent")
    own = seed.folder(db, company_id=SORENTO, name="ZZT-own", parent_id=root_owned.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO}))
    attachment = AttachmentService(db).create_attachment(
        _payload(db, type_id=t.id, directory_id=own.id), str(uuid.uuid4())
    )

    assert attachment.company_id is None, "an is_shared TYPE upload must land NULL"
    db.expire_all()
    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    assert db.query(AttachmentDirectory).filter(AttachmentDirectory.id == own.id).first().company_id is None
    assert db.query(AttachmentDirectory).filter(AttachmentDirectory.id == root_owned.id).first().company_id is None, (
        "the ancestor chain must be pulled to shared too (R19), or the path to the "
        "now-shared file cannot resolve from every company"
    )


# --------------------------------------------------------------------------- #
# AC-D2 - the TYPE decides, never the folder: a non-shared type uploads S
# even into a SHARED folder
# --------------------------------------------------------------------------- #


def test_ac_d2_non_shared_type_upload_is_owned_even_in_a_shared_folder(db):
    t = seed.att_type(db, is_shared=False, name="ZZT-Specs")
    shared_folder = seed.folder(db, company_id=None, name="ZZT-shared-folder")
    db.commit()

    set_company_scope(db, frozenset({SORENTO}))
    attachment = AttachmentService(db).create_attachment(
        _payload(db, type_id=t.id, directory_id=shared_folder.id), str(uuid.uuid4())
    )

    assert attachment.company_id == SORENTO, (
        "the file's company must come from the TYPE flag, not the destination folder"
    )


# --------------------------------------------------------------------------- #
# AC-D3 - moving a NULL-company file into an owned folder leaves the file
# NULL and pulls the destination folder's ancestor chain to shared
# --------------------------------------------------------------------------- #


def test_ac_d3_moving_a_shared_file_into_an_owned_folder_pulls_the_chain_via_update(db):
    t = seed.att_type(db)
    root_owned = seed.folder(db, company_id=SORENTO, name="ZZT-parent")
    dest = seed.folder(db, company_id=SORENTO, name="ZZT-dest", parent_id=root_owned.id)
    set_company_scope(db, None)
    shared_file = seed.attachment(db, company_id=None, type_id=t.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    AttachmentService(db).update_attachment(shared_file.id, AttachmentUpdate(directory_id=dest.id))

    db.expire_all()
    assert db.query(Attachment).filter(Attachment.id == shared_file.id).first().company_id is None, (
        "a move never re-stamps the FILE's own company (R10)"
    )
    assert db.query(AttachmentDirectory).filter(AttachmentDirectory.id == dest.id).first().company_id is None
    assert db.query(AttachmentDirectory).filter(AttachmentDirectory.id == root_owned.id).first().company_id is None


def test_ac_d3_moving_a_shared_file_into_an_owned_folder_pulls_the_chain_via_bulk_move(db):
    t = seed.att_type(db)
    root_owned = seed.folder(db, company_id=SORENTO, name="ZZT-parent")
    dest = seed.folder(db, company_id=SORENTO, name="ZZT-dest", parent_id=root_owned.id)
    set_company_scope(db, None)
    shared_file = seed.attachment(db, company_id=None, type_id=t.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    moved = AttachmentService(db).bulk_move([shared_file.id], dest.id)

    assert moved == 1
    db.expire_all()
    assert db.query(Attachment).filter(Attachment.id == shared_file.id).first().company_id is None
    assert db.query(AttachmentDirectory).filter(AttachmentDirectory.id == dest.id).first().company_id is None
    assert db.query(AttachmentDirectory).filter(AttachmentDirectory.id == root_owned.id).first().company_id is None


# --------------------------------------------------------------------------- #
# AC-D4 - an S file moved into a SHARED folder stays S
# --------------------------------------------------------------------------- #


def test_ac_d4_sorento_file_moved_into_shared_folder_stays_sorento(db):
    t = seed.att_type(db)
    shared_folder = seed.folder(db, company_id=None, name="ZZT-shared-dest")
    owned_file = seed.attachment(db, company_id=SORENTO, type_id=t.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    AttachmentService(db).update_attachment(owned_file.id, AttachmentUpdate(directory_id=shared_folder.id))

    db.expire_all()
    assert db.query(Attachment).filter(Attachment.id == owned_file.id).first().company_id == SORENTO


# --------------------------------------------------------------------------- #
# AC-D5 - a folder created under a shared parent is NULL; at root under S it
# is S
# --------------------------------------------------------------------------- #


def test_ac_d5_folder_created_under_shared_parent_is_null(db):
    shared_parent = seed.folder(db, company_id=None, name="ZZT-shared-parent")
    db.commit()

    set_company_scope(db, frozenset({SORENTO}))
    created = AttachmentDirectoryService(db).create_directory(
        AttachmentDirectoryCreate(name="ZZT-new-child", parent_id=shared_parent.id)
    )

    assert created.company_id is None


def test_ac_d5_folder_created_at_root_takes_the_active_company(db):
    set_company_scope(db, frozenset({SORENTO}))
    created = AttachmentDirectoryService(db).create_directory(
        AttachmentDirectoryCreate(name="ZZT-new-root")
    )

    assert created.company_id == SORENTO


# --------------------------------------------------------------------------- #
# Review fix S4 - a root folder is never silently shared by a guess. The
# retired auto-stamp resolved an owned write the same way for every other
# table: DEFAULT_COMPANY_ID under an all-companies (None) scope, a 400 under
# an ambiguous one (UNSET / several companies). create_directory must do the
# same for the ROOT case now that it stamps company_id itself.
# --------------------------------------------------------------------------- #


def test_root_folder_under_all_companies_scope_takes_the_incumbent_company(db):
    """The import-task path: an X-API-Key call with no contact identity
    resolves to scope None (all companies), and `get_or_create_directory`
    (import flows building a folder path) must land the folder on the
    incumbent company rather than silently sharing it."""
    set_company_scope(db, None)

    created = AttachmentDirectoryService(db).get_or_create_directory(
        None, "ZZT-import-root"
    )

    assert created.company_id == SORENTO, (
        "a root folder created under an all-companies scope must resolve to "
        "the incumbent company, not be left NULL (shared)"
    )


def test_root_folder_under_an_ambiguous_scope_is_rejected(db):
    from app.models.base import UNSET
    from app.services.error_handler import AppException

    for scope in (UNSET, frozenset({SORENTO, MOCHA})):
        set_company_scope(db, scope)
        with pytest.raises(AppException) as exc_info:
            AttachmentDirectoryService(db).create_directory(
                AttachmentDirectoryCreate(name=f"ZZT-ambiguous-{scope!r}")
            )
        assert exc_info.value.status_code == 400, (
            f"scope {scope!r} must be rejected, not guessed at"
        )


# --------------------------------------------------------------------------- #
# AC-D6 - flipping is_shared on a TYPE never touches an existing attachment
# --------------------------------------------------------------------------- #


def test_ac_d6_flipping_is_shared_leaves_existing_rows_alone(db):
    t = seed.att_type(db, is_shared=False, name="ZZT-Flip")
    db.commit()

    set_company_scope(db, frozenset({SORENTO}))
    existing = AttachmentService(db).create_attachment(_payload(db, type_id=t.id), str(uuid.uuid4()))
    assert existing.company_id == SORENTO

    from app.schemas.resources import AttachmentTypeUpdate
    from app.services.resources_service import AttachmentTypeService

    AttachmentTypeService(db).update_type(t.id, AttachmentTypeUpdate(is_shared=True))

    db.expire_all()
    unchanged = db.query(Attachment).filter(Attachment.id == existing.id).first()
    assert unchanged.company_id == SORENTO, "flipping the type flag must not rewrite an existing row"


# --------------------------------------------------------------------------- #
# AC-D7 - is_shared round-trips through create / update / list, over HTTP
# (response_model can drop undeclared fields silently, so assert the JSON body)
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(db):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db

    def _override_get_db():
        yield db

    def _override_current_user():
        return {"id": "773b536d-c675-5a29-b44c-37f956462ba0"}

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_current_user_or_api_key] = _override_current_user
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


_URL = "/api/v1/resource-management/attachment-types/"


def test_ac_d7_is_shared_round_trips_through_create_update_list(client):
    created = client.post(
        _URL,
        json={
            "type_name": unique_code("ZZT Round Trip")[:50],
            "allowed_extensions": "pdf",
            "is_shared": True,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["is_shared"] is True, "is_shared must be on the CREATE response body"
    type_id = body["id"]

    updated = client.put(
        f"{_URL}{type_id}",
        json={"is_shared": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_shared"] is False, "is_shared must be on the UPDATE response body"

    listing = client.get(_URL, params={"limit": 200})
    assert listing.status_code == 200, listing.text
    row = next(r for r in listing.json()["data"] if r["id"] == type_id)
    assert row["is_shared"] is False, "is_shared must be on the LIST response body"
