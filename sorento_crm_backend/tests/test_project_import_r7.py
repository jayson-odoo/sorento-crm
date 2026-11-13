"""Project import, fix round 7: the pending-action History text (browser pass 2, N3 / D7) (RED).

The shared pending-action audit text is produced in `app/services/form_action_service.py`
(`dispatch` writes the "requested" line, `cancel` the "withdrawn" line). The History renders
both the description AND the value diff, so neither may carry the action slug, the internal
`action_key` / `commit_at` fields, or an ISO timestamp:

- requested: "<label> requested ..." with the commit time as dd/mm/yyyy, h:mm am/pm
  (`app/utils/date_format.fmt_datetime`), no slug, no "Action key", no ISO time;
- withdrawn: "<label> withdrawn ..." with no slug.

Tested with this lane's key and one existing record action (`sales_team.delete`).
"""
from __future__ import annotations

import json
import re
import uuid

import pytest

from ._project_import_support import memory_storage, world  # noqa: F401  fixtures

ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
PLAIN_TIME = re.compile(r"\b\d{2}/\d{2}/\d{4}, \d{1,2}:\d{2} (am|pm)\b")

ACTIONS = [
    ("project_import_run.revert", "project_import_run", "Revert import"),
    ("sales_team.delete", "sales_team", "Delete sales team"),
]


def _entries(db, entity_type, entity_id):
    from app.models.audit import AuditLog

    db.flush()
    return (db.query(AuditLog)
            .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.changed_at.asc())
            .all())


def _shown(entry) -> str:
    """Everything the History can print for an entry: description plus the value diff."""
    return " ".join([
        entry.description or "",
        json.dumps(entry.old_values or {}, default=str),
        json.dumps(entry.new_values or {}, default=str),
    ])


def _park(w, key, entity_type):
    import app.services.record_actions  # noqa: F401  registers every action
    from app.models.sla import FORM_ACTION_CHANNEL_UI, SlaFormAction
    from app.services.form_action_service import FormActionService

    entity_id = str(uuid.uuid4())
    FormActionService(w.db).dispatch(
        action_key=key, entity_type=entity_type, entity_id=entity_id,
        payload={"entity_id": entity_id}, actor_id=w.admin_id,
        channel=FORM_ACTION_CHANNEL_UI, grace_seconds=10,
    )
    row = (w.db.query(SlaFormAction)
           .filter(SlaFormAction.action_key == key, SlaFormAction.source_entity_id == entity_id)
           .one())
    return entity_id, row


@pytest.mark.parametrize("key,entity_type,label", ACTIONS)
def test_r7_n3_the_requested_entry_reads_in_plain_words(world, key, entity_type, label):
    from app.utils.date_format import fmt_datetime

    w = world
    entity_id, row = _park(w, key, entity_type)

    requested = [e for e in _entries(w.db, entity_type, entity_id)
                 if re.search(r"\brequested\b", e.description or "", re.I)]

    assert len(requested) == 1, [e.description for e in _entries(w.db, entity_type, entity_id)]
    entry = requested[0]
    shown = _shown(entry)
    assert entry.description.startswith(f"{label} requested"), entry.description
    assert fmt_datetime(row.commit_at) in entry.description, entry.description
    assert PLAIN_TIME.search(entry.description), entry.description
    assert key not in shown, shown
    assert "action_key" not in shown and "Action key" not in shown, shown
    assert "commit_at" not in shown, shown
    assert not ISO_TIME.search(shown), shown


@pytest.mark.parametrize("key,entity_type,label", ACTIONS)
def test_r7_n3_the_withdrawn_entry_reads_label_withdrawn(world, key, entity_type, label):
    from app.services.form_action_service import FormActionService

    w = world
    entity_id, row = _park(w, key, entity_type)

    FormActionService(w.db).cancel(row.id, actor_id=w.admin_id)

    withdrawn = [e for e in _entries(w.db, entity_type, entity_id)
                 if re.search(r"\bwithdrawn\b", e.description or "", re.I)]
    assert len(withdrawn) == 1, [e.description for e in _entries(w.db, entity_type, entity_id)]
    entry = withdrawn[0]
    shown = _shown(entry)
    assert entry.description.startswith(f"{label} withdrawn"), entry.description
    assert key not in shown, shown
    assert not ISO_TIME.search(shown), shown
