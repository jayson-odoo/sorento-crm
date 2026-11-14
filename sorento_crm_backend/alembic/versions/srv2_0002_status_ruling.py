"""SAMPLE-REQUEST-V2, owner ruling 11 Nov ~19:55: the sample request flow is
Submitted -> Processing -> Delivered (Cancel stays); Delivered comes ONLY from linking the
AutoCount consignment.

Data only, on the default-scope `sample_request` graph:

- every request in `customer_confirmed` moves to `processing`, with one History (audit_logs)
  entry each saying so;
- the manual moves `processing -> customer_confirmed` and `customer_confirmed -> delivered` are
  removed, so no screen offers them. The `customer_confirmed` status row itself is KEPT (no edge
  leads to it any more): old History rows still name it, and nothing is dropped.

`retire_customer_confirmed(conn)` is SQLAlchemy Core so the test suite can run it against its
scratch schema too (tests/test_sample_request_status_ruling.py). Idempotent: a second run finds
nothing to move and no edge to delete.

Revision ID: srv2_0002_status_ruling
Revises: srv2_0001_ship_to_party
"""
import uuid

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql  # noqa: F401
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "srv2_0002_status_ruling"
down_revision = "srv2_0001_ship_to_party"
branch_labels = None
depends_on = None

_meta = sa.MetaData()
# Full Table objects (not sa.table()): a schema translate map applies to them, so the test suite's
# scratch schema is honoured as well as the real `projects` schema.
_statuses = sa.Table(
    "statuses",
    _meta,
    sa.Column("id", sa.String),
    sa.Column("entity_type", sa.String),
    sa.Column("key", sa.String),
    sa.Column("label", sa.String),
    sa.Column("scope_id", sa.String),
)
_transitions = sa.Table(
    "status_transitions",
    _meta,
    sa.Column("id", sa.String),
    sa.Column("entity_type", sa.String),
    sa.Column("from_status_id", sa.String),
    sa.Column("to_status_id", sa.String),
    sa.Column("scope_id", sa.String),
    sa.Column("label", sa.String),
    sa.Column("trigger_mode", sa.String),
)
_requests = sa.Table(
    "sample_requests",
    _meta,
    sa.Column("id", sa.String),
    sa.Column("status_id", sa.String),
    sa.Column("company_id", sa.String),
    sa.Column("consignment_order_id", sa.String),
    sa.Column("consignment_no", sa.String),
    schema="projects",
)
_orders = sa.Table(
    "sales_orders",
    _meta,
    sa.Column("id", sa.String),
    sa.Column("so_number", sa.String),
    sa.Column("status", sa.String),
)
_audit = sa.Table(
    "audit_logs",
    _meta,
    sa.Column("id", sa.String),
    sa.Column("entity_type", sa.String),
    sa.Column("entity_id", sa.String),
    sa.Column("action", sa.String),
    sa.Column("old_values", sa.dialects.postgresql.JSONB),
    sa.Column("new_values", sa.dialects.postgresql.JSONB),
    sa.Column("description", sa.Text),
    sa.Column("company_id", sa.String),
    sa.Column("event", sa.String),
)

#: The audit entity type the sample request's History reads (`SampleRequest.__audit_entity_type__`).
AUDIT_ENTITY = "project_sample_requests"
NOTE = (
    "Customer confirmed was removed (owner, 11 Nov 2026): moved back to Processing. "
    "Delivered now comes only from linking the AutoCount consignment."
)


def _status_ids(conn):
    rows = conn.execute(
        sa.select(_statuses.c.key, _statuses.c.id).where(
            _statuses.c.entity_type == "sample_request", _statuses.c.scope_id.is_(None)
        )
    ).all()
    return {key: sid for key, sid in rows}


def retire_customer_confirmed(conn) -> int:
    """Move every customer_confirmed request to processing (with a History row) and remove the
    manual moves into customer_confirmed and delivered. Returns how many requests moved."""
    ids = _status_ids(conn)
    confirmed, processing, delivered = ids.get("customer_confirmed"), ids.get("processing"), ids.get("delivered")
    moved = 0
    if confirmed and processing:
        rows = conn.execute(
            sa.select(_requests.c.id, _requests.c.company_id).where(_requests.c.status_id == confirmed)
        ).all()
        for rid, company_id in rows:
            conn.execute(
                _requests.update().where(_requests.c.id == rid).values(status_id=processing)
            )
            conn.execute(
                _audit.insert().values(
                    id=str(uuid.uuid4()),
                    entity_type=AUDIT_ENTITY,
                    entity_id=str(rid),
                    action="UPDATE",
                    old_values={"status": "Customer confirmed"},
                    new_values={"status": "Processing"},
                    description=NOTE,
                    company_id=company_id,
                    event="sample_request_status_ruling",
                )
            )
            moved += 1
    # A consignment voided BEFORE this ruling left its link in place (the old rule only undid the
    # delivery), so a later AutoCount restore would deliver the request again. Voided stays voided:
    # let go of it now, with a History row naming it (review of the ruling, SHOULD 1).
    voided = conn.execute(
        sa.select(_requests.c.id, _requests.c.company_id, _orders.c.so_number)
        .select_from(_requests.join(_orders, _orders.c.id == _requests.c.consignment_order_id))
        .where(_orders.c.status == "cancelled")
    ).all()
    for rid, company_id, number in voided:
        conn.execute(
            _requests.update()
            .where(_requests.c.id == rid)
            .values(consignment_order_id=None, consignment_no=None)
        )
        conn.execute(
            _audit.insert().values(
                id=str(uuid.uuid4()),
                entity_type=AUDIT_ENTITY,
                entity_id=str(rid),
                action="UPDATE",
                old_values={"consignment_no": number},
                new_values={"consignment_no": None},
                description=(
                    f"Consignment {number} was voided: unlinked (owner, 11 Nov 2026: a voided "
                    "consignment stays voided). Link a new consignment to deliver."
                ),
                company_id=company_id,
                event="sample_request_status_ruling",
            )
        )

    manual = []
    if confirmed:
        manual.append(
            sa.or_(_transitions.c.from_status_id == confirmed, _transitions.c.to_status_id == confirmed)
        )
    if delivered:
        manual.append(_transitions.c.to_status_id == delivered)
    if manual:
        conn.execute(
            _transitions.delete().where(
                _transitions.c.entity_type == "sample_request",
                _transitions.c.scope_id.is_(None),
                sa.or_(*manual),
            )
        )
    return moved


def upgrade() -> None:
    retire_customer_confirmed(op.get_bind())


def downgrade() -> None:
    # Data ruling: the moved rows are not put back (which ones were confirmed is in History).
    # The two manual edges come back so the old graph is whole again.
    conn = op.get_bind()
    ids = _status_ids(conn)
    pairs = (
        ("processing", "customer_confirmed", "Customer confirmed"),
        ("customer_confirmed", "delivered", "Delivered"),
    )
    for frm, to, label in pairs:
        if not (ids.get(frm) and ids.get(to)):
            continue
        exists = conn.execute(
            sa.select(_transitions.c.id).where(
                _transitions.c.entity_type == "sample_request",
                _transitions.c.scope_id.is_(None),
                _transitions.c.from_status_id == ids[frm],
                _transitions.c.to_status_id == ids[to],
            )
        ).first()
        if not exists:
            conn.execute(
                _transitions.insert().values(
                    id=str(uuid.uuid4()),
                    entity_type="sample_request",
                    scope_id=None,
                    from_status_id=ids[frm],
                    to_status_id=ids[to],
                    label=label,
                    trigger_mode="manual",
                )
            )
