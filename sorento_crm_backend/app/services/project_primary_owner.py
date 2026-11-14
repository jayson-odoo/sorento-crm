"""The primary lead backfill (PROJECT-LEADS-REASSIGN UAC A6), shared by the migration and
`project_service.backfill_primary_owner`.

Built from private `Table` stubs (only the columns the rules touch) rather than a `text()`
literal or the ORM models: the migration must not import the model graph, and a
schema-qualified raw string, like a lightweight `table()` clause, skips the test fixture's
`schema_translate_map` and lands on the real `projects` schema.

Only NULL primaries are filled, so a second run changes nothing. For each project, in order:

1. `from_user_id` of its EARLIEST `owner_reassigned` activity row (who held it before the first
   recorded hand-over), else
2. the linked lead's `owner_user_id`, when the project came from a lead, else
3. the project's current owner.

`created_by` is never read: an importer and a salesperson cannot be told apart on a project.
"""
from __future__ import annotations

from typing import Dict

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    cast,
    exists,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

OWNER_REASSIGNED_TEMPLATE = "owner_reassigned"
PROJECT_ENTITY_TYPE = "project"

_meta = MetaData()
_projects = Table(
    "projects",
    _meta,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("owner_user_id", String(100)),
    Column("primary_owner_user_id", String(100)),
    Column("lead_id", UUID(as_uuid=False)),
    schema="projects",
)
_leads = Table(
    "leads",
    _meta,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("owner_user_id", String(100)),
    schema="projects",
)
_events = Table(
    "activity_events",
    _meta,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("entity_type", String(50)),
    Column("entity_id", String(100)),
    Column("system_template", String(100)),
    Column("system_payload", JSONB),
    Column("created_at", DateTime),
)
_users = Table("users", _meta, Column("id", String(100), primary_key=True))


def _known_user(user_id_expr):
    """The column carries a users FK: a name that no longer resolves is skipped, not raised."""
    return exists(select(_users.c.id).where(_users.c.id == user_id_expr))


def _rule_earliest_reassign():
    earliest = (
        select(
            _events.c.entity_id.label("entity_id"),
            _events.c.system_payload["from_user_id"].astext.label("from_user_id"),
        )
        .where(
            _events.c.entity_type == PROJECT_ENTITY_TYPE,
            _events.c.system_template == OWNER_REASSIGNED_TEMPLATE,
        )
        .distinct(_events.c.entity_id)
        .order_by(_events.c.entity_id, _events.c.created_at, _events.c.id)
        .subquery("earliest")
    )
    return (
        update(_projects)
        .where(
            _projects.c.primary_owner_user_id.is_(None),
            cast(_projects.c.id, Text) == earliest.c.entity_id,
            earliest.c.from_user_id.isnot(None),
            _known_user(earliest.c.from_user_id),
        )
        .values(primary_owner_user_id=earliest.c.from_user_id)
    )


def _rule_lead_owner():
    return (
        update(_projects)
        .where(
            _projects.c.primary_owner_user_id.is_(None),
            _projects.c.lead_id == _leads.c.id,
            _leads.c.owner_user_id.isnot(None),
            _known_user(_leads.c.owner_user_id),
        )
        .values(primary_owner_user_id=_leads.c.owner_user_id)
    )


def _rule_current_owner():
    return (
        update(_projects)
        .where(
            _projects.c.primary_owner_user_id.is_(None),
            _projects.c.owner_user_id.isnot(None),
        )
        .values(primary_owner_user_id=_projects.c.owner_user_id)
    )


def backfill(bind) -> Dict[str, int]:
    """Run the three rules in order on a Session or Connection. Returns rows filled per rule."""
    counts: Dict[str, int] = {}
    for key, statement in (
        ("earliest_reassign", _rule_earliest_reassign()),
        ("lead_owner", _rule_lead_owner()),
        ("current_owner", _rule_current_owner()),
    ):
        counts[key] = bind.execute(statement).rowcount or 0
    return counts
