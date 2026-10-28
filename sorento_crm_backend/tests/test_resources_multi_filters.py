"""FILTER-MULTISELECT PR6 (resources): the attachment list and the drive listing take several Companies,
Storage statuses, Uploaders, Attachment types and (list only) Folders (OR within a filter, AND across);
comma-joined, repeated and single all read. Several Companies never widen the caller's company scope: a
company outside it stays invisible. Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.company import Company
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

MOCHA = "00000000-0000-0000-0000-000000000002"
LIST = "/api/v1/resource-management/attachments/"
DRIVE = "/api/v1/resource-management/attachments/drive"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


@pytest.fixture
def client(db, monkeypatch):
    from app.services.user_service import UserPermissionService

    with open_client(db, monkeypatch) as (c, _actor):
        monkeypatch.setattr(
            UserPermissionService,
            "get_user_permission_slugs",
            lambda self, uid: ["resource.attachments.view", "resource.attachment_directories.view"],
        )
        yield c


def _type(db, key):
    t = AttachmentType(id=_uid(), type_name=unique_code(key)[:50], allowed_extensions="pdf")
    db.add(t)
    db.flush()
    return t


def _user(db, key):
    u = User(id=_uid(), email=f"zzt-{key}-{uuid.uuid4().hex[:6]}@test.com", name=f"ZZT {key}")
    db.add(u)
    db.flush()
    return u


def _att(db, key, *, company, type_id, uploader, storage, directory=None):
    row = Attachment(
        id=_uid(), original_filename=f"ZZT-{key}.pdf", stored_filename=f"ZZT-{key}-{uuid.uuid4().hex[:6]}.pdf",
        file_path=f"https://cdn.test/zzt-{key}.pdf", attachment_type_id=type_id, is_deleted=False, company_id=company,
        uploaded_by=uploader, storage_status=storage, directory_id=directory,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def world(db):
    t1, t2, t3 = _type(db, "T1"), _type(db, "T2"), _type(db, "T3")
    u1, u2, u3 = _user(db, "u1"), _user(db, "u2"), _user(db, "u3")
    rows = {
        "a": _att(db, "a", company=DEFAULT_COMPANY_ID, type_id=t1.id, uploader=u1.id, storage="accessible"),
        "b": _att(db, "b", company=None, type_id=t2.id, uploader=u2.id, storage="missing"),
        "c": _att(db, "c", company=MOCHA, type_id=t1.id, uploader=u1.id, storage="accessible"),
        "d": _att(db, "d", company=DEFAULT_COMPANY_ID, type_id=t3.id, uploader=u3.id, storage="unchecked"),
    }
    db.commit()
    return dict(types=(t1, t2, t3), users=(u1, u2, u3), **rows)


def _ids(client, url, pairs):
    resp = get(client, url, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return {r["id"] for r in data if r.get("kind", "file") == "file"}


SORENTO = DEFAULT_COMPANY_ID


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_company_single_shared_and_default(client, world, url):
    s = world
    assert _ids(client, url, []) == {s["a"].id, s["b"].id, s["d"].id}
    assert _ids(client, url, [("company", SORENTO)]) == {s["a"].id, s["d"].id}
    assert _ids(client, url, [("company", "shared")]) == {s["b"].id}


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_company_union_comma_and_repeated(client, world, url):
    s = world
    assert _ids(client, url, [("company", f"shared,{SORENTO}")]) == {s["a"].id, s["b"].id, s["d"].id}
    assert _ids(client, url, [("company", "shared"), ("company", SORENTO)]) == {s["a"].id, s["b"].id, s["d"].id}


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_several_companies_never_widen_past_the_callers_scope(client, world, url):
    s = world
    assert _ids(client, url, [("company", MOCHA)]) == set()
    assert _ids(client, url, [("company", f"{SORENTO},{MOCHA}")]) == {s["a"].id, s["d"].id}
    assert _ids(client, url, [("company", f"shared,{MOCHA}")]) == {s["b"].id}
    assert s["c"].id not in _ids(client, url, [("company", MOCHA), ("company", SORENTO), ("company", "shared")])


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_storage_status_union(client, world, url):
    s = world
    assert _ids(client, url, [("storage_status", "missing")]) == {s["b"].id}
    assert _ids(client, url, [("storage_status", "missing,unchecked")]) == {s["b"].id, s["d"].id}
    assert _ids(client, url, [("storage_status", "accessible"), ("storage_status", "unchecked")]) == {s["a"].id, s["d"].id}


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_uploaded_by_union(client, world, url):
    s = world
    u1, u2, u3 = (u.id for u in s["users"])
    assert _ids(client, url, [("uploaded_by", u2)]) == {s["b"].id}
    assert _ids(client, url, [("uploaded_by", f"{u2},{u3}")]) == {s["b"].id, s["d"].id}
    assert _ids(client, url, [("uploaded_by", u1), ("uploaded_by", u3)]) == {s["a"].id, s["d"].id}


def test_list_attachment_type_ids_guard(client, world):
    s = world
    t1, t2, t3 = (t.id for t in s["types"])
    assert _ids(client, LIST, [("attachment_type_ids", f"{t2},{t3}")]) == {s["b"].id, s["d"].id}
    assert _ids(client, LIST, [("attachment_type_ids", t2), ("attachment_type_ids", t3)]) == {s["b"].id, s["d"].id}
    assert _ids(client, LIST, [("attachment_type_ids", t1)]) == {s["a"].id}


def test_drive_attachment_type_union(client, world):
    s = world
    t1, t2, t3 = (t.id for t in s["types"])
    assert _ids(client, DRIVE, [("attachment_type_id", t2)]) == {s["b"].id}
    assert _ids(client, DRIVE, [("attachment_type_id", f"{t2},{t3}")]) == {s["b"].id, s["d"].id}
    assert _ids(client, DRIVE, [("attachment_type_id", t2), ("attachment_type_id", t3)]) == {s["b"].id, s["d"].id}


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_filters_and_across(client, world, url):
    s = world
    got = _ids(client, url, [("company", f"shared,{SORENTO}"), ("storage_status", "missing,unchecked")])
    assert got == {s["b"].id, s["d"].id}
    got = _ids(client, url, [("company", SORENTO), ("storage_status", "missing,unchecked")])
    assert got == {s["d"].id}


def test_list_folder_union(client, db):
    t = _type(db, "T")
    u = _user(db, "u")
    folders = []
    for i in range(3):
        f = AttachmentDirectory(id=_uid(), name=f"ZZT folder {i}")
        db.add(f)
        folders.append(f)
    db.flush()
    rows = [
        _att(db, f"f{i}", company=DEFAULT_COMPANY_ID, type_id=t.id, uploader=u.id, storage="accessible", directory=folders[i].id)
        for i in range(3)
    ]
    db.commit()
    f0, f1, f2 = (f.id for f in folders)
    assert _ids(client, LIST, [("directory_id", f0)]) == {rows[0].id}
    assert _ids(client, LIST, [("directory_id", f"{f1},{f2}")]) == {rows[1].id, rows[2].id}
    assert _ids(client, LIST, [("directory_id", f1), ("directory_id", f2)]) == {rows[1].id, rows[2].id}
