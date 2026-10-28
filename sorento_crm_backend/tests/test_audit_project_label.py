"""FORMS-PROJECT: the record history shows a linked project as `CODE - Title`, never its UUID
(no UUIDs in the UI). Other fields of the same change are left as they are."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from sqlalchemy import text

from app.models.base import company_scope
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session


def test_project_ids_in_the_trail_read_as_code_and_title():
    from app.api.v1.audit.audit_logs import _label_project_values, _project_labels
    from app.services.project_service import register_project

    with blank_session() as db:
        srt = str(db.execute(text("select id from companies where code = 'SRT'")).scalar())
        project_seed_service.run(db, company_id=srt)
        owner = str(uuid.uuid4())
        db.add(User(id=owner, email=f"{owner}@zzt.test", name="zzt owner"))
        db.flush()
        with company_scope(db, frozenset({srt})):
            project = register_project(
                db, company_id=srt, actor_user_id=owner, developer_party_id=None,
                title="zzt Audit Tower",
            )
            db.flush()
            item = SimpleNamespace(
                old_values={"project_id": None, "remark": "a"},
                new_values={"project_id": str(project.id), "remark": "b"},
            )
            labels = _project_labels(db, [item, SimpleNamespace(old_values={"project_id": "x"}, new_values=None)])
        payload = {"old_values": dict(item.old_values), "new_values": dict(item.new_values)}
        _label_project_values(payload, labels)
    assert payload["new_values"]["project_id"] == f"{project.project_code} - zzt Audit Tower"
    assert payload["old_values"]["project_id"] is None
    assert payload["new_values"]["remark"] == "b"
    hidden = {"old_values": None, "new_values": {"project_id": str(uuid.uuid4())}}
    _label_project_values(hidden, labels)
    assert hidden["new_values"]["project_id"] == "Linked project not visible"


def test_the_record_trail_labels_the_project_and_keeps_children_and_resubmit_values(monkeypatch):
    """Merge with AUDIT-TRAIL-DIFF (#1924): one listing with include_children serves the
    project as `CODE - Title` and still names child rows, while every other field keeps its
    raw value, which the FE field diff and the "Resubmitted" check read."""
    from datetime import datetime

    from fastapi.testclient import TestClient

    import app.main  # noqa: F401  registers every router
    from app.api.v1.audit import audit_logs as audit_routes
    from app.database import get_db
    from app.dependencies import get_current_user_or_api_key
    from app.main import app
    from app.models.audit import AuditLog
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.project_service import register_project

    def _row(db, *, entity_type, entity_id, action, old=None, new=None, root, minute):
        db.add(
            AuditLog(
                id=str(uuid.uuid4()), entity_type=entity_type, entity_id=entity_id,
                action=action, old_values=old, new_values=new,
                root_entity_type=root[0], root_entity_id=root[1], actor_type="contact",
                changed_at=datetime(2026, 9, 1, 9, minute),
            )
        )
        db.flush()

    with blank_session() as db:
        srt = str(db.execute(text("select id from companies where code = 'SRT'")).scalar())
        project_seed_service.run(db, company_id=srt)
        owner = str(uuid.uuid4())
        db.add(User(id=owner, email=f"{owner}@zzt.test", name="zzt owner"))
        db.flush()
        with company_scope(db, frozenset({srt})):
            project = register_project(
                db, company_id=srt, actor_user_id=owner, developer_party_id=None,
                title="zzt Trail Tower",
            )
            db.flush()
            complaint_id, line_id = str(uuid.uuid4()), str(uuid.uuid4())
            root = ("complaint", complaint_id)
            _row(db, entity_type="complaint", entity_id=complaint_id, action="UPDATE",
                 old={"status": "rejected", "product_code": "CWCX604-P-RL-NEW", "project_id": None},
                 new={"status": "submitted", "product_code": "CWCY604", "project_id": str(project.id)},
                 root=root, minute=33)
            _row(db, entity_type="complaint_product_lines", entity_id=line_id, action="INSERT",
                 new={"id": line_id, "complaint_id": complaint_id, "product_code": "CWCX604-P-RL-NEW"},
                 root=root, minute=10)

            monkeypatch.setattr(audit_routes, "_is_audit_admin", lambda db, uid: True)
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": owner}
            # The request carries no token; keep the session's Sorento scope, as a signed-in
            # Sorento user's request would resolve.
            app.dependency_overrides[apply_company_scope] = lambda: frozenset({srt})
            try:
                res = TestClient(app).get(
                    "/api/v1/audit/logs/",
                    params={"entity_type": "complaint", "entity_id": complaint_id, "include_children": "true"},
                )
            finally:
                app.dependency_overrides.pop(get_db, None)
                app.dependency_overrides.pop(get_current_user_or_api_key, None)
                app.dependency_overrides.pop(apply_company_scope, None)
        label = f"{project.project_code} - zzt Trail Tower"

    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert len(rows) == 2
    header = next(r for r in rows if r["entity_type"] == "complaint")
    # This PR: the project reads as code and title, never the UUID.
    assert header["new_values"]["project_id"] == label
    assert header["old_values"]["project_id"] is None
    # #1924: the other fields stay raw for the field diff and the "Resubmitted" check.
    assert (header["old_values"]["status"], header["new_values"]["status"]) == ("rejected", "submitted")
    assert header["new_values"]["product_code"] == "CWCY604"
    assert header["description"] == "status: rejected → submitted"
    # #1924: the child row is still named by its product code.
    child = next(r for r in rows if r["entity_type"] == "complaint_product_lines")
    assert child["entity_label"] == "Product line CWCX604-P-RL-NEW"
