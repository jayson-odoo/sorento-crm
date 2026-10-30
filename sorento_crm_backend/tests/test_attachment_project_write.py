"""A file on a project is project work (ATTACH-PROJECT-WRITE).

Plan: documentation/plans/projects/PLAN-attach-project-write-30oct.md.

The attachment router checked only the attachment slugs, never the right to work the
project a file is filed under. Any staff user could attach a document to another
salesperson's project (which satisfies the Spec In document gate), re-point one onto or
off it, restore one, or archive / delete it to block a stage move. Every one of those
writes now takes `project_service.assert_can_edit_project`, the same rule `change_status`
runs.

The second half: project documents upload with no folder, so the filename collision check
(scoped by folder alone) matched a same-named file on ANY project, and Replace overwrote
that other project's file. With an entity given, only files on that entity collide.

Postgres only, blank schema, every row seeded here.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.projects import Project
from app.models.resources import Attachment, AttachmentType
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/resource-management/attachments"
UPLOAD = "resource.attachments.upload"
DELETE = "resource.attachments.delete"
BULK_DELETE = "resource.attachments.bulk_delete"
MANAGE = "projects.projects.manage"
ALL_ATTACHMENT_SLUGS = {UPLOAD, DELETE, BULK_DELETE}


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _user(db, name: str) -> str:
    user_id = str(uuid.uuid4())
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _project(db, owner: str) -> Project:
    # (company, developer, normalised_title) is unique, so every project needs its own title.
    code = unique_code("apw")
    project = Project(
        id=str(uuid.uuid4()),
        company_id=DEFAULT_COMPANY_ID,
        project_code=code[:40],
        title=f"Setia Alam {code}",
        normalised_title=f"setia alam {code.lower()}",
        owner_user_id=owner,
    )
    db.add(project)
    db.flush()
    return project


@pytest.fixture
def world(db, monkeypatch):
    """Owner Ali holds project A, Siti holds project B. The caller is switchable."""
    import app.api.v1.resources.attachments as attachments_module
    import app.services.storage_router as storage_router
    from app.services.contact_access_type_service import ContactAccessTypeService

    ali = _user(db, "zzt-apw Ali")
    siti = _user(db, "zzt-apw Siti")
    state = {
        "caller": {"id": siti, "email": "siti@zzt.test"},
        "allow": set(ALL_ATTACHMENT_SLUGS),
        "ali": ali,
        "siti": siti,
        "project_a": _project(db, ali),
        "project_b": _project(db, siti),
        "uploads": [],
    }

    def _override_db():
        yield db

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: state["caller"]
    app.dependency_overrides[get_current_user_or_api_key] = lambda: state["caller"]
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in state["allow"],
    )
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_permission_slugs",
        lambda self, uid: sorted(state["allow"]),
    )

    class _Backend:
        def upload_file(self, *, file_content, file_path, content_type=None):
            state["uploads"].append(file_path)
            return file_path, f"https://cdn.test/{file_path}"

    monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _Backend())
    monkeypatch.setattr(
        storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}"
    )
    monkeypatch.setattr(attachments_module, "_create_and_send_webhook", lambda *a, **k: None)
    monkeypatch.setattr(
        ContactAccessTypeService, "get_default_access_levels", lambda self: ["dealer"]
    )
    monkeypatch.setattr(
        ContactAccessTypeService,
        "validate_access_levels",
        lambda self, levels, field_name="access_levels": list(levels),
    )
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)

    type_id = str(uuid.uuid4())
    db.add(
        AttachmentType(
            id=type_id,
            code=unique_code("pdoc")[:40],
            type_name=unique_code("Project Document")[:40],
            allowed_extensions="pdf",
            max_file_size_mb=10,
        )
    )
    db.flush()
    state["type_id"] = type_id
    state["client"] = TestClient(app)
    try:
        yield state
    finally:
        app.dependency_overrides.clear()


def _as(world, who: str, *extra_slugs: str) -> None:
    world["caller"] = {"id": world[who], "email": f"{who}@zzt.test"}
    world["allow"] = set(ALL_ATTACHMENT_SLUGS) | set(extra_slugs)


def _upload(world, project: Project, name: str | None = None, **form):
    return world["client"].post(
        f"{BASE}/",
        data={
            "attachment_type_id": world["type_id"],
            "entity_type": "project",
            "entity_id": str(project.id),
            **form,
        },
        files={"file": (name or f"{unique_code('spec')}.pdf", b"%PDF-1.4 apw", "application/pdf")},
    )


def _seed_file(db, project: Project | None, name: str | None = None, *, archived=False) -> str:
    name = name or f"{unique_code('spec')}.pdf"
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=name,
        stored_filename=name,
        file_path=f"https://cdn.test/project/{name}",
        file_hash="original-bytes",
        storage_provider="s3",
        entity_type="project" if project is not None else None,
        entity_id=str(project.id) if project is not None else None,
        is_deleted=archived,
    )
    db.add(att)
    db.flush()
    return str(att.id)


def _row(db, attachment_id: str) -> Attachment | None:
    db.expire_all()
    return db.query(Attachment).filter(Attachment.id == attachment_id).first()


def _project_files(db, project: Project) -> list[Attachment]:
    db.expire_all()
    return (
        db.query(Attachment)
        .filter(Attachment.entity_type == "project", Attachment.entity_id == str(project.id))
        .all()
    )


# ------------------------------------------------------------------------- upload


def test_an_outsider_cannot_attach_a_file_to_another_salespersons_project(db, world):
    _as(world, "siti")

    res = _upload(world, world["project_a"])

    assert res.status_code == 403, res.text
    assert res.json()["code"] == "project_not_editable"
    assert _project_files(db, world["project_a"]) == []
    assert world["uploads"] == []  # refused before any bytes reach storage


def test_the_owner_can_attach_a_file_to_their_project(db, world):
    _as(world, "ali")

    res = _upload(world, world["project_a"])

    assert res.status_code == 201, res.text
    assert len(_project_files(db, world["project_a"])) == 1


def test_a_manager_can_attach_to_any_project(db, world):
    _as(world, "siti", MANAGE)

    res = _upload(world, world["project_a"])

    assert res.status_code == 201, res.text


def test_entity_type_is_matched_the_way_upload_stores_it(db, world):
    """Upload lowercases the type before storing it, so `Project` lands as `project`."""
    _as(world, "siti")

    res = _upload(world, world["project_a"], entity_type="Project")

    assert res.status_code == 403, res.text


def test_upload_onto_an_unknown_project_is_not_found(db, world):
    _as(world, "siti")
    ghost = Project(id=str(uuid.uuid4()))

    res = _upload(world, ghost)

    assert res.status_code == 404, res.text


def test_a_non_project_upload_is_unchanged(db, world):
    _as(world, "siti")

    res = world["client"].post(
        f"{BASE}/",
        data={"attachment_type_id": world["type_id"]},
        files={"file": (f"{unique_code('free')}.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert res.status_code == 201, res.text


# ------------------------------------------------------------------------- edit


def test_an_outsider_cannot_repoint_a_file_onto_another_project(db, world):
    _as(world, "siti")
    own_file = _seed_file(db, world["project_b"])

    res = world["client"].put(
        f"{BASE}/{own_file}", json={"entity_id": str(world["project_a"].id)}
    )

    assert res.status_code == 403, res.text
    assert _row(db, own_file).entity_id == str(world["project_b"].id)


def test_an_outsider_cannot_repoint_a_loose_file_onto_a_project(db, world):
    _as(world, "siti")
    loose = _seed_file(db, None)

    res = world["client"].put(
        f"{BASE}/{loose}",
        json={"entity_type": "project", "entity_id": str(world["project_a"].id)},
    )

    assert res.status_code == 403, res.text
    assert _row(db, loose).entity_id is None


def test_an_outsider_cannot_move_a_file_off_another_project(db, world):
    _as(world, "siti")
    theirs = _seed_file(db, world["project_a"])

    res = world["client"].put(
        f"{BASE}/{theirs}", json={"entity_id": str(world["project_b"].id)}
    )

    assert res.status_code == 403, res.text
    assert _row(db, theirs).entity_id == str(world["project_a"].id)


def test_an_outsider_cannot_rename_a_file_on_another_project(db, world):
    _as(world, "siti")
    theirs = _seed_file(db, world["project_a"])

    res = world["client"].put(f"{BASE}/{theirs}", json={"stored_filename": "renamed.pdf"})

    assert res.status_code == 403, res.text


def test_the_owner_can_edit_their_project_file(db, world):
    _as(world, "ali")
    mine = _seed_file(db, world["project_a"])

    res = world["client"].put(f"{BASE}/{mine}", json={"stored_filename": "renamed.pdf"})

    assert res.status_code == 200, res.text
    assert _row(db, mine).stored_filename == "renamed.pdf"


def test_moving_between_projects_needs_both(db, world):
    """Owner of the source but not the target: refused. Owner of both (manager): allowed."""
    _as(world, "ali")
    mine = _seed_file(db, world["project_a"])

    refused = world["client"].put(
        f"{BASE}/{mine}", json={"entity_id": str(world["project_b"].id)}
    )
    assert refused.status_code == 403, refused.text

    _as(world, "ali", MANAGE)
    allowed = world["client"].put(
        f"{BASE}/{mine}", json={"entity_id": str(world["project_b"].id)}
    )
    assert allowed.status_code == 200, allowed.text
    assert _row(db, mine).entity_id == str(world["project_b"].id)


# ------------------------------------------------------------- archive / restore / delete


def test_an_outsider_cannot_archive_another_projects_file(db, world):
    _as(world, "siti")
    theirs = _seed_file(db, world["project_a"])

    res = world["client"].post(f"{BASE}/{theirs}/archive")

    assert res.status_code == 403, res.text
    assert _row(db, theirs).is_deleted is False


def test_an_outsider_cannot_restore_another_projects_file(db, world):
    _as(world, "siti")
    theirs = _seed_file(db, world["project_a"], archived=True)

    res = world["client"].put(f"{BASE}/{theirs}/restore")

    assert res.status_code == 403, res.text
    assert _row(db, theirs).is_deleted is True


def test_an_outsider_cannot_delete_another_projects_file(db, world):
    _as(world, "siti")
    theirs = _seed_file(db, world["project_a"])

    res = world["client"].delete(f"{BASE}/{theirs}")

    assert res.status_code == 403, res.text
    assert _row(db, theirs) is not None


def test_an_outsider_cannot_bulk_archive_or_bulk_delete_another_projects_file(db, world):
    _as(world, "siti")
    theirs = _seed_file(db, world["project_a"])
    mine = _seed_file(db, world["project_b"])

    archived = world["client"].post(
        f"{BASE}/bulk-archive", json={"attachment_ids": [mine, theirs]}
    )
    deleted = world["client"].post(
        f"{BASE}/bulk-delete", json={"attachment_ids": [mine, theirs]}
    )

    assert archived.status_code == 403, archived.text
    assert deleted.status_code == 403, deleted.text
    # All or nothing: the caller's own file is not touched either.
    assert _row(db, theirs).is_deleted is False
    assert _row(db, mine) is not None and _row(db, mine).is_deleted is False


def test_the_owner_can_archive_and_restore_their_file(db, world):
    _as(world, "ali")
    mine = _seed_file(db, world["project_a"])

    assert world["client"].post(f"{BASE}/{mine}/archive").status_code == 200
    assert _row(db, mine).is_deleted is True
    assert world["client"].put(f"{BASE}/{mine}/restore").status_code == 200
    assert _row(db, mine).is_deleted is False


def test_archive_and_restore_take_the_attachment_delete_slug(db, world):
    """The same slug `POST /bulk-archive` already takes."""
    _as(world, "ali")
    world["allow"] = {UPLOAD}
    mine = _seed_file(db, world["project_a"])

    archived = world["client"].post(f"{BASE}/{mine}/archive")
    assert archived.status_code == 403, archived.text
    assert DELETE in archived.text

    _seed_archived = _seed_file(db, world["project_a"], archived=True)
    restored = world["client"].put(f"{BASE}/{_seed_archived}/restore")
    assert restored.status_code == 403, restored.text
    assert DELETE in restored.text


# ------------------------------------------------------------------------ collision


def test_a_same_named_file_on_another_project_does_not_collide(db, world):
    _as(world, "siti")
    name = f"{unique_code('shared')}.pdf"
    _seed_file(db, world["project_a"], name)

    res = _upload(world, world["project_b"], name)

    assert res.status_code == 201, res.text


def test_collision_check_with_an_entity_ignores_other_projects(db, world):
    _as(world, "siti")
    name = f"{unique_code('shared')}.pdf"
    _seed_file(db, world["project_a"], name)

    other = world["client"].get(
        f"{BASE}/collision-check",
        params={"filename": name, "entity_type": "project", "entity_id": str(world["project_b"].id)},
    )
    same = world["client"].get(
        f"{BASE}/collision-check",
        params={"filename": name, "entity_type": "project", "entity_id": str(world["project_a"].id)},
    )

    assert other.status_code == 200 and other.json()["collides"] is False, other.text
    assert same.status_code == 200 and same.json()["collides"] is True, same.text


def test_replace_never_touches_another_projects_file(db, world):
    """The bug from #1991's browser pass: Replace overwrote the OTHER project's document."""
    _as(world, "siti")
    name = f"{unique_code('shared')}.pdf"
    theirs = _seed_file(db, world["project_a"], name)

    res = _upload(world, world["project_b"], name, on_conflict="replace")

    assert res.status_code == 201, res.text
    assert res.json()["id"] != theirs
    untouched = _row(db, theirs)
    assert untouched.file_hash == "original-bytes"
    assert untouched.entity_id == str(world["project_a"].id)
    assert untouched.uploaded_by is None
    assert len(_project_files(db, world["project_b"])) == 1


def test_replace_on_the_same_project_still_replaces(db, world):
    _as(world, "ali")
    name = f"{unique_code('shared')}.pdf"
    mine = _seed_file(db, world["project_a"], name)

    blocked = _upload(world, world["project_a"], name)
    assert blocked.status_code == 409, blocked.text

    res = _upload(world, world["project_a"], name, on_conflict="replace")
    assert res.status_code == 201, res.text
    assert res.json()["id"] == mine
    assert _row(db, mine).file_hash != "original-bytes"


def test_replace_without_an_entity_cannot_overwrite_another_projects_file(db, world):
    """A folderless upload with no entity still collides on the folderless project file;
    replacing it is a write to that project and needs the edit right."""
    _as(world, "siti")
    name = f"{unique_code('shared')}.pdf"
    theirs = _seed_file(db, world["project_a"], name)

    res = world["client"].post(
        f"{BASE}/",
        data={"attachment_type_id": world["type_id"], "on_conflict": "replace"},
        files={"file": (name, b"%PDF-1.4 apw", "application/pdf")},
    )

    assert res.status_code == 403, res.text
    assert _row(db, theirs).file_hash == "original-bytes"
