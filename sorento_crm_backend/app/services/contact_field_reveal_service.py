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

WHICH KEYS EXIST is a frozen literal here, not a read of `mcp_tools.restricted_fields`
at request time. `mcp_tool_registry_service.sync_catalog` still writes that column at
startup by importing `sorento_crm_mcp.catalog` - but the deployed backend image is built
from `context: ./sorento_crm_backend` only (see `sorento_crm/docker-compose.yml` and
`.github/workflows/deploy.yml`), `sorento_crm_mcp` is not in `requirements.txt`, and no
volume mounts it in, so that import raises `ModuleNotFoundError` in every container and
the startup sync never runs - the column stays at its migration-488 default of `[]`
forever on prod, and this checklist read "No restricted field exists yet" even though the
catalogue declares three. A local checkout works because the dev venv happens to have the
MCP package installed, which is exactly what hid the bug. The precedent is
`app/services/chatbot/lanes/business/fetch.py::CHATBOT_READ_ONLY_TOOLS`: a frozen set the
container CAN read, kept honest by a CI test (`tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py`)
that imports the catalogue - which CI and a checkout both can - and asserts the two agree.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.access import ContactFieldReveal

#: Every restricted key the catalogue declares, sorted by key, source of truth for the
#: Contacts > Access > Field reveals checklist. Mirrors `ToolSpec.restricted_fields` on
#: `crm_inventory_stock_balance_list` and `crm_procurement_po_placed_list` in
#: `sorento_crm_mcp/sorento_crm_mcp/catalog.py`. A test pins this literal to the catalogue
#: (see the module docstring above), so a new `restricted=` field on a presenter fails
#: here until this tuple is updated to match, rather than silently missing the checklist.
FIELD_REVEAL_KEYS: tuple[tuple[str, str], ...] = (
    ("inventory.sellable", "Outstanding SO on stock answers"),
    ("purchase_orders.placed", "PO placed (on order) on stock answers"),
    ("purchase_orders.supplier", "PO supplier"),
    ("purchase_orders.cost", "Last purchase cost"),
    ("sales_orders.outstanding", "Sales order outstanding"),
)


def field_reveal_keys() -> list[dict[str, str]]:
    """Every restricted key that exists, with its label, sorted by key.

    Sourced from the `FIELD_REVEAL_KEYS` literal above, not from `mcp_tools` - see the
    module docstring for why a live query cannot be used here.
    """
    return [{"key": key, "label": label} for key, label in sorted(FIELD_REVEAL_KEYS)]


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
            # `updated_at`'s own `onupdate=func.now()` fires from this write; an
            # explicit UTC value here landed 9 hours BEFORE `created_at` on a
            # server in a positive-UTC-offset timezone (both columns are naive,
            # so one is `now()` in local time and the other was UTC).
            row.granted = True

    for key, row in existing.items():
        if key not in wanted and row.granted:
            row.granted = False

    db.commit()
    return granted_keys(db, respond_contact_id)
