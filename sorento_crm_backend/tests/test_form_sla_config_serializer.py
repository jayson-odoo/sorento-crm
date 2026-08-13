"""The form-SLA config serializer must carry every column the dialog edits.

The dialog seeds its state from GET responses and always sends the full field set
back on save. A column missing from the manual `_serialize` dict therefore reads as
null in the dialog and is written back as null on ANY unrelated edit - which is how
a configured stage grace (the undo feature's on-switch) silently turned itself off.
Same family as the get_user / system_settings manual-builder rule in CLAUDE.md.

Postgres only, scratch schema.
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import blank_session, unique_code


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def test_serialize_round_trips_every_dialog_field(db):
    from app.api.v1.sla.form_sla_config import _serialize
    from app.models.sla import FormSLAConfig, SLAPolicy

    policy = SLAPolicy(code=unique_code("grace"), name="grace probe")
    db.add(policy)
    db.flush()
    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="stock_inquiry",
        stage_code=unique_code("stage"),
        policy_id=policy.id,
        agent_code=unique_code("agent"),
        team_set_code=unique_code("team"),
        start_event="submit",
        resolve_event="purchasing_decide",
        is_active=True,
        grace_seconds=25,
        notify_assignee=False,
        notify_on_escalation=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    payload = _serialize(config)

    # The dialog's editable surface. A field missing here nulls itself on save.
    assert payload["grace_seconds"] == 25
    assert payload["notify_assignee"] is False
    assert payload["notify_on_escalation"] is True
    assert payload["start_event"] == "submit"
    assert payload["resolve_event"] == "purchasing_decide"
    assert payload["is_active"] is True
