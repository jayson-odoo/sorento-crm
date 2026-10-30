"""A file on a project is project work: writing it takes the project edit right.

ATTACH-PROJECT-WRITE (documentation/plans/projects/PLAN-attach-project-write-30oct.md).
Every route that creates, re-points, overwrites, moves, archives, restores or deletes a file
runs one of these, on the attachments router and on the folder routes that cascade into files.

The rule is `project_service.assert_can_edit_project`, the one `change_status` runs, not the
stricter `assert_can_write_project`: a pending registration still takes its documents so the
approver can fix it up before Approve (R8). Every other entity type is unchanged.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy.orm import Session

PROJECT_ENTITY_TYPE = "project"


def normalize_entity_type(entity_type: Optional[str]) -> Optional[str]:
    """The entity_type exactly as upload stores it (lowercased, spaces to underscores)."""
    cleaned = (entity_type or "").strip().lower().replace(" ", "_")
    return cleaned or None


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _assert_can_edit(db: Session, project, current_user: dict) -> None:
    from app.api.v1.projects._common import permission_slugs
    from app.services import project_service

    project_service.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )


def assert_can_write_target(
    db: Session, entity_type: Optional[str], entity_id: Optional[str], current_user: dict
) -> None:
    """The entity a file is being put ONTO (upload, re-point). The project must be one this
    caller can see, so an unknown or hidden one is a 404, as on every staff project route."""
    if normalize_entity_type(entity_type) != PROJECT_ENTITY_TYPE or not entity_id:
        return
    from app.services import project_service
    from app.services.uuid_path_param import validate_uuid_path

    validate_uuid_path(str(entity_id), resource="Project")
    project = project_service.get_project_or_404(db, str(entity_id), current_user["id"])
    _assert_can_edit(db, project, current_user)


def assert_can_write_existing(
    db: Session, entity_type: Optional[str], entity_id: Optional[str], current_user: dict
) -> None:
    """The entity a file already sits on. Read without the staff draft filter: a file on a
    project the caller cannot see (a contact's portal draft) must still be refused, and one on
    a project that no longer exists has no project rule left to apply, so it is not locked."""
    if normalize_entity_type(entity_type) != PROJECT_ENTITY_TYPE or not _is_uuid(entity_id):
        return
    from app.models.projects import Project

    project = db.query(Project).filter(Project.id == str(entity_id)).first()
    if project is None:
        return
    _assert_can_edit(db, project, current_user)


def assert_can_write_attachments(
    db: Session, attachment_ids: Iterable, current_user: dict
) -> None:
    """Every existing row a write touches, archived or not. Ids that are not UUIDs or match no
    row pass through, so the service still answers them with its own 404, 422 or skip."""
    from app.models.resources import Attachment

    ids = [str(i) for i in (attachment_ids or []) if _is_uuid(i)]
    if not ids:
        return
    rows = (
        db.query(Attachment.entity_type, Attachment.entity_id)
        .filter(Attachment.id.in_(ids))
        .distinct()
        .all()
    )
    for entity_type, entity_id in rows:
        assert_can_write_existing(db, entity_type, entity_id, current_user)


def assert_can_write_directory_files(db: Session, directory_id: str, current_user: dict) -> None:
    """A folder delete, restore or permanent delete cascades into every file in its subtree,
    so each of those files needs the same right a direct write would."""
    from app.models.resources import Attachment
    from app.services.resources_service import AttachmentDirectoryService

    dir_ids = AttachmentDirectoryService(db).get_descendant_directory_ids(
        directory_id, include_deleted=True
    )
    if not dir_ids:
        return
    rows = (
        db.query(Attachment.entity_type, Attachment.entity_id)
        .filter(Attachment.directory_id.in_(dir_ids), Attachment.entity_id.isnot(None))
        .distinct()
        .all()
    )
    for entity_type, entity_id in rows:
        assert_can_write_existing(db, entity_type, entity_id, current_user)
