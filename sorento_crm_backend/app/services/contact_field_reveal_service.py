"""Which RESTRICTED chatbot fields a contact may be told, and the keys that exist.

One mechanism for two owner requirements (chatbot growth r1, Slice C): sellable
stock defaults off for every contact (D3), and a PO's supplier must never reach a
dealer by default (D4). A presenter marks a field `restricted=<key>` in
`field_vocabulary`; `contact_field_reveals` is the grant, keyed directly on the
contact - unlike `agent_field_access`, there is no owning agent to route a PO
supplier's reveal through.

Default is HIDDEN: a contact with no row for a key never sees that field. A full
list PUT does not delete non-listed rows - it flips them to `granted=False` - so
the table keeps who granted or revoked a key and when, rather than losing that
history on the next save.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.access import ContactFieldReveal, McpTool


def field_reveal_keys(db: Session) -> list[dict[str, str]]:
    """Every restricted key declared on an active tool, deduped, with its label.

    Sourced from `mcp_tools.restricted_fields` (written by
    `mcp_tool_registry_service.sync_catalog`), never hardcoded here - a new
    `restricted=` field on a presenter reaches this list, and the checklist it
    feeds, after the next sync with no FE or backend change.
    """
    rows = (
        db.query(McpTool.restricted_fields)
        .filter(McpTool.is_active.is_(True))
        .order_by(McpTool.tool_name)
        .all()
    )
    seen: dict[str, str] = {}
    for (fields,) in rows:
        for entry in fields or []:
            key = entry.get("key") if isinstance(entry, dict) else None
            if not key or key in seen:
                continue
            seen[key] = entry.get("label") or key
    return [{"key": key, "label": label} for key, label in sorted(seen.items())]


def granted_keys(db: Session, respond_contact_id: str) -> list[str]:
    """The keys this contact currently holds. `[]` when no row has ever been granted."""
    rows = (
        db.query(ContactFieldReveal.field_key)
        .filter(
            ContactFieldReveal.respond_contact_id == respond_contact_id,
            ContactFieldReveal.granted.is_(True),
        )
        .all()
    )
    return sorted(key for (key,) in rows)


def set_granted_keys(
    db: Session,
    respond_contact_id: str,
    keys: list[str],
    *,
    actor_id: str | None,
) -> list[str]:
    """Full-list replace: exactly `keys` end up granted, every other row revoked.

    Upserts rather than delete-then-insert, so a key toggled off and back on
    keeps its original `created_at` / `created_by` rather than looking newly
    granted.
    """
    wanted = set(keys)
    existing = {
        row.field_key: row
        for row in db.query(ContactFieldReveal)
        .filter(ContactFieldReveal.respond_contact_id == respond_contact_id)
        .all()
    }
    now = datetime.now(timezone.utc)

    for key in wanted:
        row = existing.get(key)
        if row is None:
            db.add(
                ContactFieldReveal(
                    respond_contact_id=respond_contact_id,
                    field_key=key,
                    granted=True,
                    created_by=actor_id,
                )
            )
        elif not row.granted:
            row.granted = True
            row.updated_at = now

    for key, row in existing.items():
        if key not in wanted and row.granted:
            row.granted = False
            row.updated_at = now

    db.commit()
    return granted_keys(db, respond_contact_id)
