"""RFQ-GATE-REMOVE: Registered -> Spec In follows the status graph alone.

The PS-REGISTER-CHECK-FIRST document gate (422 `project_requirements_missing`) is gone (owner,
10 Nov 2026): a Registered project with no document moves to Spec In like any other graph edge,
through the HTTP route and the service. Every row is seeded here (Postgres, isolated schema).
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
        entity_id=str(project.id),
        is_deleted=deleted,
    )
    w.db.add(att)
    w.db.flush()
    return att


def _at(w, key: str):
    project = approved_project(w)
    project.status_id = _stage(w.db, key).id
    w.db.flush()
    return project


def _move(w, project, to_key: str):
    body = {"to_status_id": _stage(w.db, to_key).id}
    if to_key == "lost":
        body["loss_reason"] = "price"  # BE1: the Lost rung needs a reason
    return as_user(w, w.owner).post(f"{STAFF}/{project.id}/status", json=body)


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


# ------------------------------------------------------------------ AC-3 no document needed


def test_ac3_registered_to_spec_in_without_a_document_moves_over_http(v2):
    project = _at(v2, "registered")
    v2.db.commit()
    res = _move(v2, project, "specified")
    assert res.status_code == 200, res.text
    assert "project_requirements_missing" not in res.text
    assert _status_key(v2, project) == "specified"


def test_ac3_service_moves_registered_to_spec_in_without_a_document(v2):
    project = _at(v2, "registered")
    _service_move(v2, project, "specified")
    assert _stage_key(v2, project.status_id) == "specified"


def test_ac3_a_deleted_document_alone_does_not_block_either(v2):
    project = _at(v2, "registered")
    _file(v2, project, deleted=True)
    _service_move(v2, project, "specified")
    assert _stage_key(v2, project.status_id) == "specified"


def test_ac3_with_a_live_document_the_move_still_works(v2):
    project = _at(v2, "registered")
    _file(v2, project)
    res = _move(v2, project, "specified")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "specified"


def test_ac3_spec_in_back_to_registered_and_forward_again_needs_no_file(v2):
    project = _at(v2, "registered")
    assert _move(v2, project, "specified").status_code == 200
    assert _move(v2, project, "registered").status_code == 200
    res = _move(v2, project, "specified")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "specified"


def test_ac3_a_move_the_graph_does_not_allow_is_still_refused(v2):
    """Guard: removing the document gate does not open edges the graph lacks."""
    project = _at(v2, "registered")
    res = _move(v2, project, "quoted")
    assert res.status_code in (400, 409, 422), res.text
    assert _status_key(v2, project) == "registered"


# ------------------------------------------------------------------ other moves (regression guards)


@pytest.mark.parametrize("to_key", ["lost", "dormant", "po_received", "identified"])
def test_other_moves_out_of_registered_need_no_file(v2, to_key):
    project = _at(v2, "registered")
    res = _move(v2, project, to_key)
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == to_key


def test_a_move_not_starting_at_registered_needs_no_file(v2):
    project = _at(v2, "specified")
    res = _move(v2, project, "quoted")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "quoted"


def test_the_first_po_still_advances_a_registered_project_without_a_file(v2):
    from app.services import project_po_service

    project = _at(v2, "registered")
    project_po_service.create_po(
        v2.db,
        project=project,
        actor_user_id=v2.owner,
        payload={"po_source": "contractor_direct", "po_number": f"ZZT-PO-{uuid.uuid4().hex[:8]}"},
    )
    assert _stage_key(v2, project.status_id) == "po_received"


# ------------------------------------------------------------------ existing projects untouched


def test_a_project_already_past_registered_is_not_blocked_or_rewritten(v2):
    project = _at(v2, "specified")
    res = as_user(v2, v2.owner).get(f"{STAFF}/{project.id}")
    assert res.status_code == 200, res.text
    assert _status_key(v2, project) == "specified"
    assert _move(v2, project, "quoted").status_code == 200
