"""PS-REGISTER-CHECK-FIRST UAC G2-G6: any live document gates Registered -> Spec In.

Red-first. The gate lives in `project_service.change_status`, so the service and the HTTP route
both see it. Every row is seeded here (Postgres, isolated schema).
"""
from __future__ import annotations

import uuid

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._project_register_v2_support import (  # noqa: F401
    STAFF,
    approved_project,
    as_user,
    title,
    v2,
)

DOC_CODE = "project_document"
REFUSAL = "Upload the requirements document before moving this project to Spec In."


def _stage(db, key: str):
    from app.models.status import Status

    return (
        db.query(Status)
        .filter(Status.entity_type == "project", Status.scope_id.is_(None), Status.key == key)
        .one()
    )


def _kind(db, code: str, name: str):
    """Get-or-create a document kind by code, so the helper does not depend on the seed."""
    from app.models.resources import AttachmentType

    row = db.query(AttachmentType).filter(AttachmentType.code == code).first()
    if row is None:
        row = AttachmentType(
            id=str(uuid.uuid4()), code=code, type_name=name, allowed_extensions="pdf,docx,xlsx"
        )
        db.add(row)
        db.flush()
    return row


def _file(w, project, code: str = DOC_CODE, name: str = "Project Document", deleted: bool = False):
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    kind = _kind(w.db, code, name)
    att = Attachment(
        id=str(uuid.uuid4()),
        company_id=w.company_id,
        attachment_type_id=kind.id,
        original_filename="zzt-req.pdf",
        stored_filename=f"zzt-{uuid.uuid4().hex}.pdf",
        file_path="zzt/req.pdf",
        entity_type="project",
        entity_id=project.id,
        is_deleted=deleted,
    )
    w.db.add(att)
    w.db.flush()
    w.db.add(
        EntityAttachmentLink(
            id=str(uuid.uuid4()), entity_type="project", entity_id=str(project.id), attachment_id=att.id
        )
    )
    w.db.flush()
    return att


def _at(w, key: str):
    project = approved_project(w)
    project.status_id = _stage(w.db, key).id
    w.db.flush()
    return project


def _move(w, project, to_key: str):
    return as_user(w, w.owner).post(
        f"{STAFF}/{project.id}/status", json={"to_status_id": _stage(w.db, to_key).id}
    )


def _status_key(w, project) -> str:
    from app.models.projects import Project

    w.db.expire_all()
    return _stage_key(w, w.db.get(Project, project.id).status_id)


def _stage_key(w, status_id) -> str:
    from app.models.status import Status

    return w.db.get(Status, status_id).key


def _service_move(w, project, to_key: str):
    from app.services import project_service

    return project_service.change_status(
        w.db,
        project,
        to_status_id=_stage(w.db, to_key).id,
        actor_user_id=w.owner,
        permissions={"projects.projects.edit", "projects.projects.view"},
    )


# ------------------------------------------------------------------ G2, G3 through the route


def test_ac_g2_registered_to_spec_in_without_a_document_refused(v2):
    project = _at(v2, "registered")
    v2.db.commit()  # the route rolls back on a refusal; a flush-only seed would vanish
    res = _move(v2, project, "specified")
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["code"] == "project_requirements_missing", body
    assert REFUSAL in res.text
    assert _status_key(v2, project) == "registered"


def test_ac_g2_service_raises_with_code_and_exact_message_and_leaves_status(v2):
    from app.services.error_handler import AppException

    project = _at(v2, "registered")
    with pytest.raises(AppException) as exc:
        _service_move(v2, project, "specified")
    assert exc.value.status_code == 422
    assert exc.value.code == "project_requirements_missing"
    assert exc.value.message == REFUSAL
    assert _stage_key(v2, project.status_id) == "registered"


def test_ac_g3_registered_to_spec_in_with_a_live_document_moves(v2):
    project = _at(v2, "registered")
    _file(v2, project)
    res = _move(v2, project, "specified")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "specified"


def test_ac_g3_service_moves_with_a_live_document(v2):
    project = _at(v2, "registered")
    _file(v2, project)
    _service_move(v2, project, "specified")
    assert _stage_key(v2, project.status_id) == "specified"


# ------------------------------------------------------------------ G4 what does not count


def test_ac_g3_a_project_document_kind_file_counts(v2):
    project = _at(v2, "registered")
    _file(v2, project, code=DOC_CODE)
    _service_move(v2, project, "specified")
    assert _stage_key(v2, project.status_id) == "specified"


def test_ac_g3_a_document_with_no_attachment_type_counts(v2):
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    project = _at(v2, "registered")
    att = Attachment(
        id=str(uuid.uuid4()), company_id=v2.company_id, attachment_type_id=None,
        original_filename="zzt.pdf", stored_filename=f"zzt-{uuid.uuid4().hex}.pdf",
        file_path="zzt/x.pdf", entity_type="project", entity_id=project.id,
    )
    v2.db.add(att)
    v2.db.flush()
    v2.db.add(EntityAttachmentLink(
        id=str(uuid.uuid4()), entity_type="project", entity_id=str(project.id), attachment_id=att.id
    ))
    v2.db.flush()
    _service_move(v2, project, "specified")
    assert _stage_key(v2, project.status_id) == "specified"


def test_ac_g4_a_deleted_document_does_not_count(v2):
    from app.services.error_handler import AppException

    project = _at(v2, "registered")
    _file(v2, project, deleted=True)
    with pytest.raises(AppException) as exc:
        _service_move(v2, project, "specified")
    assert exc.value.code == "project_requirements_missing"


def test_ac_g4_a_document_of_another_project_does_not_count(v2):
    from app.services.error_handler import AppException

    other = _at(v2, "registered")
    _file(v2, other)
    project = _at(v2, "registered")
    with pytest.raises(AppException) as exc:
        _service_move(v2, project, "specified")
    assert exc.value.code == "project_requirements_missing"


# ------------------------------------------------------------------ G5 not gated (regression guards)


@pytest.mark.parametrize("to_key", ["lost", "dormant", "po_received", "identified"])
def test_ac_g5_other_moves_out_of_registered_need_no_file(v2, to_key):
    project = _at(v2, "registered")
    res = _move(v2, project, to_key)
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == to_key


def test_ac_g5_a_move_not_starting_at_registered_needs_no_file(v2):
    project = _at(v2, "specified")
    res = _move(v2, project, "quoted")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "quoted"


def test_ac_g5_the_first_po_still_advances_a_registered_project_without_a_file(v2):
    from app.services import project_po_service

    project = _at(v2, "registered")
    project_po_service.create_po(
        v2.db,
        project=project,
        actor_user_id=v2.owner,
        payload={"po_source": "contractor_direct", "po_number": f"ZZT-PO-{uuid.uuid4().hex[:8]}"},
    )
    assert _stage_key(v2, project.status_id) == "po_received"


# ------------------------------------------------------------------ G6 back and forward again


def test_ac_g6_spec_in_back_to_registered_then_forward_again_needs_a_file_again(v2):
    project = _at(v2, "registered")
    att = _file(v2, project)
    assert _move(v2, project, "specified").status_code == 200
    assert _move(v2, project, "registered").status_code == 200
    att.is_deleted = True
    v2.db.flush()
    res = _move(v2, project, "specified")
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_requirements_missing"
    assert _status_key(v2, project) == "registered"


def test_ac_g6_without_any_file_the_second_forward_move_is_refused(v2):
    project = _at(v2, "specified")  # arrived before the gate: no file, no block
    assert _move(v2, project, "registered").status_code == 200
    res = _move(v2, project, "specified")
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_requirements_missing"


# ------------------------------------------------------------------ G9 existing projects untouched


def test_ac_g9_a_project_already_past_registered_is_not_blocked_or_rewritten(v2):
    project = _at(v2, "specified")
    res = as_user(v2, v2.owner).get(f"{STAFF}/{project.id}")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "specified"
    assert _move(v2, project, "quoted").status_code == 200


# ------------------------------------------------------------------ G3 the REAL upload path
#
# The Documents tab posts to /api/resource-management/attachments/ with entity_type='project' and
# entity_id=<project id>. The route (attachments.py ~:1129-1130) hands those to
# AttachmentService.create_attachment, which writes them onto the attachments row itself and
# creates NO entity_attachment_links row. Listing filters on the same two columns
# (resources_service.py :840-841). The gate must count what that path writes.


def _real_upload(w, project):
    from app.schemas.resources import AttachmentCreate
    from app.services.resources_service import AttachmentService

    kind = _kind(w.db, DOC_CODE, "Project Document")
    return AttachmentService(w.db).create_attachment(
        AttachmentCreate(
            attachment_type_id=kind.id,
            original_filename="zzt-real.pdf",
            stored_filename=f"zzt-{uuid.uuid4().hex}.pdf",
            file_path="zzt/real.pdf",
            file_size_bytes=10,
            mime_type="application/pdf",
            entity_type="project",
            entity_id=str(project.id),
        ),
        w.owner,
    )


def test_ac_g3_real_upload_document_counts_over_http(v2):
    project = _at(v2, "registered")
    _real_upload(v2, project)
    res = _move(v2, project, "specified")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "specified"


def test_ac_g3_real_upload_document_counts_in_the_service(v2):
    project = _at(v2, "registered")
    _real_upload(v2, project)
    _service_move(v2, project, "specified")
    assert _stage_key(v2, project.status_id) == "specified"


def test_ac_g3_real_upload_document_stops_counting_once_archived(v2):
    """Guard: the Files screen's delete (soft) removes it from the gate again."""
    from app.services.error_handler import AppException
    from app.services.resources_service import AttachmentService

    project = _at(v2, "registered")
    att = _real_upload(v2, project)
    AttachmentService(v2.db).archive_attachment(att.id, v2.owner)
    with pytest.raises(AppException) as exc:
        _service_move(v2, project, "specified")
    assert exc.value.code == "project_requirements_missing"
