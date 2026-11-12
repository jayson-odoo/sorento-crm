"""OCN-ORDER-CHANGE-NOTICE: the order change notice as a form on the purchase request chain.

Additive and idempotent (`IF NOT EXISTS`, `WHERE NOT EXISTS`, `ON CONFLICT`), so the shared
dev DB, which converges through `create_all`, can take it in any order, and it runs twice
cleanly (tests/test_ocn_migration.py runs `upgrade()` twice on a blank scratch schema).

- `projects.order_change_notices` gains the form and lifecycle columns (the purchase request's
  names and values: status, approval_status, the approval stamp, the void quad, revision_no),
  and `project_id` becomes optional with ON DELETE SET NULL (UAC A3; it was NOT NULL CASCADE).
- `projects.order_change_types` (seeded with four types, risk level and guide text) and
  `projects.order_change_notice_lines` (one catalogue product per line, UUID ids).
- `system_settings.order_change_notice_require_project` (OFF) and
  `system_settings.order_change_notice_default_approver_user_id`.
- The `order_change_notice` numbering rule `OCN{yy}-`, 4 digits, yearly, one per company.
- A partial unique index: one amendment per notice (`so_amendments.ocn_id`).
- Eight permissions, granted to the roles holding the matching purchase request slug and to the
  admin roles (grant ids prefixed `ocn-`, so the downgrade removes only these).
- SLA: policy `ORDER_CHANGE_NOTICE` with the purchase request policy's tiers, and one
  `form_sla_configs` row per purchase request stage (main, approval, customer service), every
  column copied, linked in the same chain. The policy is the one the purchase request stages use
  (one company today; a second company's PR policy would need its own copy). Only when purchase request rows exist; an existing OCN row is kept.
- An enabled `portal_revision_configs` row, which arms the revision fence on every move.
- The form-comment CHECK on `entity_conversation_messages.entity_type` admits the notice (and the
  sample request, which writes the thread too). The downgrade leaves it widened: narrowing it
  would fail on any comment already written.

The table has no rows on the 12 Nov production copy, so nothing is backfilled.

Locks (round 10, the aud_0001_audit_standard_s0 precedent): every step that alters or
references a table other requests use (entity_conversation_messages, every form's Conversation;
system_settings, read on every request; so_amendments; order_change_notices; the users,
customers and products a new foreign key references) runs under `lock_timeout = 5s` and
`statement_timeout = 60s`, transaction-local, in a savepoint retried up to 5 times with a
backoff. A DDL queued behind a long transaction would otherwise queue every read and write of
that table behind itself; now the wait is bounded and the fifth miss fails with a message. The
widened Conversation CHECK is added NOT VALID inside that bounded lock and validated at the end
of the same transaction (the table is small; the migration tests run `upgrade()` inside the
caller's transaction, where alembic's autocommit block cannot run). The timeouts are put back
before returning.

Plan: documentation/plans/procurement/PLAN-ocn-order-change-notice-12nov.md.

Revision ID: ocn_0001_order_change_notice
Revises: prr_0001_si_npa_project
"""
from __future__ import annotations

import time
from typing import Callable

import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "ocn_0001_order_change_notice"
down_revision = "prr_0001_si_npa_project"
branch_labels = None
depends_on = None

KIND = "order_change_notice"
GRANT_ID_PREFIX = "ocn-"

LOCK_TIMEOUT = "5s"
STATEMENT_TIMEOUT = "60s"
LOCK_ATTEMPTS = 5
#: Seconds between attempts, times the attempt number (2, 4, 6, 8).
LOCK_BACKOFF_SECONDS = 2
_ADMIN_ROLES = ("superadmin", "admin")

#: (slug, name, description), as `app/rbac/permission_registry.py` declares them.
PERMISSIONS = (
    ("procurement.order_change_notices.view", "View Order Change Notices",
     "See every order change notice of your companies."),
    ("procurement.order_change_notices.view_own", "View Own Order Change Notices",
     "See only the order change notices you raised or are named on as sales or customer service "
     "in charge. Ignored when View Order Change Notices is also held."),
    ("procurement.order_change_notices.create", "Create Order Change Notices",
     "Raise, edit and submit your own order change notices."),
    ("procurement.order_change_notices.edit", "Edit Order Change Notices",
     "Send an order change notice for approval or back to its raiser, edit, void or revise it. "
     "Includes seeing every notice."),
    ("procurement.order_change_notices.delete", "Delete Order Change Notices",
     "Delete an order change notice."),
    ("procurement.order_change_notices.approve", "Approve Order Change Notices",
     "Approve or reject an order change notice that is pending approval. Includes seeing every notice."),
    ("procurement.order_change_notices.process", "Mark Order Change Notices Done",
     "Customer service: mark an approved order change notice done. Includes seeing every notice."),
    ("procurement.order_change_notices.report", "Order Change Notice Report",
     "Read the order change notice report."),
)

#: (purchase request slug its holders have, OCN slug they get).
GRANT_FROM_PR = (
    ("procurement.purchase_requests.view", "procurement.order_change_notices.view"),
    ("procurement.purchase_requests.view_own", "procurement.order_change_notices.view_own"),
    ("procurement.purchase_requests.add", "procurement.order_change_notices.create"),
    # `.edit` only from the purchase request's triage grant (security review M3); customer
    # service's processing grant becomes the notice's own Done grant, nothing more.
    ("procurement.purchase_requests.send_for_approval", "procurement.order_change_notices.edit"),
    ("procurement.purchase_requests.process", "procurement.order_change_notices.process"),
    ("procurement.purchase_requests.delete", "procurement.order_change_notices.delete"),
    ("procurement.purchase_requests.approve", "procurement.order_change_notices.approve"),
)

#: (name, risk level, guide text), in list order (UAC A5).
CHANGE_TYPES = (
    ("Advance", "Low", "Bring a delivery forward: same products and quantities, an earlier date."),
    ("Exchange", "High", "Swap a product for another one: the old line goes out, the new one comes in."),
    ("Cancellation", "Highest", "Cancel all or part of the balance still to deliver."),
    ("Delay", "Low", "Push a delivery back: same products and quantities, a later date."),
)

#: The new `projects.order_change_notices` columns, in add order. Core tables are named
#: unqualified, so they resolve through the search path (public in a real database, the scratch
#: schema in tests).
def _ocn_columns(p: str) -> tuple:
    return (
        ("source", "VARCHAR(16) NOT NULL DEFAULT 'crm'"),
        ("ocn_date", "DATE"),
        ("change_type_id", f'UUID REFERENCES "{p}".order_change_types(id) ON DELETE SET NULL'),
        ("customer_id", "UUID REFERENCES customers(id) ON DELETE SET NULL"),
        ("customer_name", "VARCHAR(255)"),
        ("customer_po_no", "VARCHAR(128)"),
        ("so_no_text", "VARCHAR(128)"),
        ("sales_in_charge_user_id", "VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL"),
        ("cs_in_charge_user_id", "VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL"),
        ("description", "TEXT"),
        ("cs_comment", "TEXT"),
        ("status", "VARCHAR(32) NOT NULL DEFAULT 'draft'"),
        ("approval_status", "VARCHAR(32)"),
        ("approved_by", "VARCHAR(255)"),
        ("approval_comments", "TEXT"),
        ("rejected_by_id", "VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL"),
        ("requested_approval_by_user_id", "VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL"),
        ("submitted_at", "TIMESTAMP"),
        ("voided_by", "VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL"),
        ("voided_at", "TIMESTAMP"),
        ("void_reason", "TEXT"),
        ("revision_no", "INTEGER NOT NULL DEFAULT 0"),
    )


# ------------------------------------------------------------------ bounded locks (aud_0001)


def _is_lock_timeout(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "pgcode", None) == "55P03" or "lock timeout" in str(orig or exc).lower()


def _set_timeouts(bind) -> tuple:
    """Bound this transaction's waits; returns the previous values for ``_restore_timeouts``."""
    previous = tuple(
        bind.execute(sa.text(f"SELECT current_setting('{name}')")).scalar()
        for name in ("lock_timeout", "statement_timeout")
    )
    bind.execute(sa.text(f"SELECT set_config('lock_timeout', '{LOCK_TIMEOUT}', true)"))
    bind.execute(sa.text(f"SELECT set_config('statement_timeout', '{STATEMENT_TIMEOUT}', true)"))
    return previous


def _restore_timeouts(bind, previous: tuple) -> None:
    """Put the session's values back, so no later migration in this transaction inherits them."""
    lock, statement = (value or "0" for value in previous)
    bind.execute(sa.text(f"SELECT set_config('lock_timeout', '{lock}', true)"))
    bind.execute(sa.text(f"SELECT set_config('statement_timeout', '{statement}', true)"))


def _bounded(bind, label: str, work: Callable[[], None]) -> None:
    """Run ``work`` (which takes its table lock first) in a savepoint, each attempt bounded by
    ``lock_timeout``; a lock timeout rolls the savepoint back, waits, and tries again. The last
    miss raises a message that says what to do."""
    for attempt in range(1, LOCK_ATTEMPTS + 1):
        bind.execute(sa.text("SAVEPOINT ocn_0001_lock"))
        try:
            work()
        except sa.exc.OperationalError as exc:
            if not _is_lock_timeout(exc):
                raise
            bind.execute(sa.text("ROLLBACK TO SAVEPOINT ocn_0001_lock"))
            if attempt < LOCK_ATTEMPTS:
                time.sleep(LOCK_BACKOFF_SECONDS * attempt)
            continue
        bind.execute(sa.text("RELEASE SAVEPOINT ocn_0001_lock"))
        return
    raise RuntimeError(
        f"ocn_0001_order_change_notice: could not lock {label} in {LOCK_ATTEMPTS} attempts of "
        f"lock_timeout {LOCK_TIMEOUT}; a long-running transaction holds it. Find it in "
        "pg_stat_activity (wait_event_type = 'Lock' or state = 'idle in transaction'), end it, "
        "and rerun the upgrade."
    )


def _run(bind, *statements: str) -> None:
    for statement in statements:
        bind.execute(sa.text(statement))


def _schema(bind, module: str) -> str:
    """Where a module's tables live, for RAW SQL, under BOTH substrates (see
    `prreg_0001_project_registrations`)."""
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _tables(bind, p: str) -> None:
    for statement in (
        f'CREATE SCHEMA IF NOT EXISTS "{p}"',
        f"""
        CREATE TABLE IF NOT EXISTS "{p}".order_change_types (
            id UUID PRIMARY KEY,
            name VARCHAR(64) NOT NULL,
            risk_level VARCHAR(16) NOT NULL,
            guide_text TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            position INTEGER NOT NULL DEFAULT 0
        )
        """,
    ):
        bind.execute(sa.text(statement))
    # The new foreign keys also lock users and customers (SHARE ROW EXCLUSIVE): one bounded step.
    _bounded(bind, f'"{p}".order_change_notices', lambda: _run(
        bind,
        f'LOCK TABLE "{p}".order_change_notices IN ACCESS EXCLUSIVE MODE',
        *(
            f'ALTER TABLE "{p}".order_change_notices ADD COLUMN IF NOT EXISTS {name} {ddl}'
            for name, ddl in _ocn_columns(p)
        ),
    ))
    _bounded(bind, f'"{p}".order_change_notice_lines (it references products)', lambda: _run(
        bind,
        f"""
        CREATE TABLE IF NOT EXISTS "{p}".order_change_notice_lines (
            id UUID PRIMARY KEY,
            ocn_id UUID NOT NULL REFERENCES "{p}".order_change_notices(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            qty_before NUMERIC(18, 4),
            qty_after NUMERIC(18, 4),
            date_before DATE,
            date_after DATE,
            delivered_qty NUMERIC(18, 4),
            remark TEXT
        )
        """,
        f'CREATE INDEX IF NOT EXISTS ix_order_change_notice_lines_ocn ON "{p}".order_change_notice_lines (ocn_id)',
    ))
    # system_settings is read on every request.
    _bounded(bind, "system_settings", lambda: _run(
        bind,
        "LOCK TABLE system_settings IN ACCESS EXCLUSIVE MODE",
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "order_change_notice_require_project BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "order_change_notice_default_approver_user_id VARCHAR REFERENCES users(id) ON DELETE SET NULL",
    ))


def _project_optional(bind, p: str) -> None:
    """UAC A3: whatever the project foreign key is called today, it becomes SET NULL, and the
    column nullable. Dropped and re-created on every run, so a second run is the same."""
    _bounded(bind, f'"{p}".order_change_notices', lambda: _project_fk(bind, p))


def _project_fk(bind, p: str) -> None:
    bind.execute(sa.text(f'LOCK TABLE "{p}".order_change_notices IN ACCESS EXCLUSIVE MODE'))
    names = bind.execute(
        sa.text(
            "SELECT c.conname FROM pg_constraint c JOIN pg_attribute a "
            "  ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
            "WHERE c.conrelid = to_regclass(:t) AND c.contype = 'f' AND a.attname = 'project_id'"
        ),
        {"t": f'"{p}".order_change_notices'},
    ).scalars().all()
    for name in names:
        bind.execute(sa.text(f'ALTER TABLE "{p}".order_change_notices DROP CONSTRAINT "{name}"'))
    bind.execute(
        sa.text(
            f'ALTER TABLE "{p}".order_change_notices ADD CONSTRAINT order_change_notices_project_id_fkey '
            f'FOREIGN KEY (project_id) REFERENCES "{p}".projects (id) ON DELETE SET NULL'
        )
    )
    bind.execute(sa.text(f'ALTER TABLE "{p}".order_change_notices ALTER COLUMN project_id DROP NOT NULL'))


def _seeds(bind, p: str) -> None:
    for position, (name, risk, guide) in enumerate(CHANGE_TYPES):
        bind.execute(
            sa.text(
                f"""
                INSERT INTO "{p}".order_change_types (id, name, risk_level, guide_text, is_active, position)
                SELECT gen_random_uuid(), :n, :r, :g, true, :pos
                WHERE NOT EXISTS (SELECT 1 FROM "{p}".order_change_types WHERE lower(name) = lower(:n))
                """
            ),
            {"n": name, "r": risk, "g": guide, "pos": position},
        )
    # One rule per company (each its own counter, UAC A2), as the purchase request's numbering
    # is; no runtime copying. A company with none (one added later) uses the unscoped rule, which
    # is seeded only where no OCN rule exists at all.
    bind.execute(
        sa.text(
            """
            INSERT INTO document_numbering_rules (id, company_id, doc_type, enabled, prefix_template,
                number_digits, next_value, start_value, reset_policy, created_at, updated_at)
            SELECT gen_random_uuid()::text, c.id, :k, true, 'OCN{yy}-', 4, 1, 1, 'yearly', now(), now()
              FROM companies c
             WHERE NOT EXISTS (SELECT 1 FROM document_numbering_rules r
                                WHERE r.doc_type = :k AND r.company_id = c.id)
            """
        ),
        {"k": KIND},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO document_numbering_rules (id, company_id, doc_type, enabled, prefix_template,
                number_digits, next_value, start_value, reset_policy, created_at, updated_at)
            SELECT gen_random_uuid()::text, NULL, :k, true, 'OCN{yy}-', 4, 1, 1, 'yearly', now(), now()
            WHERE NOT EXISTS (SELECT 1 FROM document_numbering_rules WHERE doc_type = :k)
            """
        ),
        {"k": KIND},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO portal_revision_configs (id, source_entity_type, is_enabled, allowed_statuses,
                created_at, updated_at)
            VALUES (gen_random_uuid(), :k, true, '["approved", "rejected"]'::jsonb, now(), now())
            ON CONFLICT (source_entity_type) DO NOTHING
            """
        ),
        {"k": KIND},
    )


def _permissions(bind) -> None:
    for slug, name, descr in PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": name, "descr": descr},
        )
    # Deterministic ids: a role reached by two source slugs (send for approval AND process)
    # draws the same id twice, which ON CONFLICT folds into one grant.
    for src, tgt in GRANT_FROM_PR:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT DISTINCT '{GRANT_ID_PREFIX}' || md5(urp.role_id || ':' || tgt.id), urp.role_id, tgt.id, now()
                  FROM user_role_permissions urp
                  JOIN user_permissions src ON src.id = urp.permission_id
                 CROSS JOIN user_permissions tgt
                 WHERE src.slug = :src AND tgt.slug = :tgt
                   AND NOT EXISTS (SELECT 1 FROM user_role_permissions existing
                                    WHERE existing.role_id = urp.role_id AND existing.permission_id = tgt.id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"src": src, "tgt": tgt},
        )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT '{GRANT_ID_PREFIX}' || md5(r.id || ':' || tgt.id), r.id, tgt.id, now()
              FROM user_roles r
             CROSS JOIN user_permissions tgt
             WHERE r.slug = ANY(:roles) AND tgt.slug = ANY(:slugs)
               AND NOT EXISTS (SELECT 1 FROM user_role_permissions existing
                                WHERE existing.role_id = r.id AND existing.permission_id = tgt.id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"roles": list(_ADMIN_ROLES), "slugs": [s for s, _n, _d in PERMISSIONS]},
    )


#: The purchase request stage each OCN stage copies: one per team set, the active and oldest.
_PR_STAGES = """
    SELECT DISTINCT ON (pr.team_set_code) pr.*
      FROM form_sla_configs pr
     WHERE pr.source_entity_type = 'purchase_request'
     ORDER BY pr.team_set_code, pr.is_active DESC, pr.created_at ASC
"""


def _sla(bind) -> None:
    """C1 / C2: nothing without purchase request rows; an OCN row that exists is kept."""
    source_policy = bind.execute(
        sa.text(
            "SELECT policy_id FROM form_sla_configs WHERE source_entity_type = 'purchase_request' "
            "ORDER BY is_active DESC, created_at ASC LIMIT 1"
        )
    ).scalar()
    if source_policy is None:
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO sla_policies (id, code, company_id, name, description, is_active,
                max_extension_days_per_request, max_extension_count, max_extension_days_total,
                created_at, updated_at)
            SELECT gen_random_uuid(), 'ORDER_CHANGE_NOTICE', s.company_id, 'Order Change Notice',
                   s.description, s.is_active, s.max_extension_days_per_request,
                   s.max_extension_count, s.max_extension_days_total, now(), now()
              FROM sla_policies s
             WHERE s.id = :src
               AND NOT EXISTS (SELECT 1 FROM sla_policies WHERE code = 'ORDER_CHANGE_NOTICE'
                                AND company_id IS NOT DISTINCT FROM s.company_id)
            """
        ),
        {"src": source_policy},
    )
    policy = bind.execute(
        sa.text(
            "SELECT o.id FROM sla_policies o JOIN sla_policies s ON s.id = :src "
            "WHERE o.code = 'ORDER_CHANGE_NOTICE' AND o.company_id IS NOT DISTINCT FROM s.company_id "
            "ORDER BY o.created_at LIMIT 1"
        ),
        {"src": source_policy},
    ).scalar()
    bind.execute(
        sa.text(
            """
            INSERT INTO sla_policy_tiers (id, policy_id, tier_level, tier_name, response_hours,
                resolution_hours, created_at, updated_at)
            SELECT gen_random_uuid(), :p, t.tier_level, t.tier_name, t.response_hours,
                   t.resolution_hours, now(), now()
              FROM sla_policy_tiers t
             WHERE t.policy_id = :src
               AND NOT EXISTS (SELECT 1 FROM sla_policy_tiers o WHERE o.policy_id = :p
                                AND o.tier_level = t.tier_level)
            """
        ),
        {"p": policy, "src": source_policy},
    )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO form_sla_configs (id, source_entity_type, stage_code, policy_id, agent_code,
                team_set_code, start_event, respond_event, resolve_event, advance_on_event,
                grace_seconds, skip_event, skip_terminal_status, skip_action_label,
                is_active, notify_assignee, notify_on_escalation, created_at, updated_at)
            SELECT gen_random_uuid(), :k, 'ocn_' || COALESCE(pr.team_set_code, 'main'), :p,
                   pr.agent_code, pr.team_set_code, pr.start_event, pr.respond_event,
                   pr.resolve_event, pr.advance_on_event,
                   pr.grace_seconds, pr.skip_event, pr.skip_terminal_status, pr.skip_action_label,
                   pr.is_active, pr.notify_assignee, pr.notify_on_escalation, now(), now()
              FROM ({_PR_STAGES}) pr
             WHERE NOT EXISTS (SELECT 1 FROM form_sla_configs o WHERE o.source_entity_type = :k
                                AND o.team_set_code IS NOT DISTINCT FROM pr.team_set_code)
            """
        ),
        {"k": KIND, "p": policy},
    )
    # The chain: an OCN stage this revision wrote follows the OCN copy of the stage its purchase
    # request source follows, never a purchase request row.
    bind.execute(
        sa.text(
            f"""
            UPDATE form_sla_configs o
               SET next_config_id = nxt.id
              FROM ({_PR_STAGES}) pr
              JOIN form_sla_configs pr_next ON pr_next.id = pr.next_config_id
              JOIN form_sla_configs nxt ON nxt.source_entity_type = :k
                                       AND nxt.team_set_code IS NOT DISTINCT FROM pr_next.team_set_code
             WHERE o.source_entity_type = :k
               AND o.stage_code = 'ocn_' || COALESCE(o.team_set_code, 'main')
               AND o.team_set_code IS NOT DISTINCT FROM pr.team_set_code
               AND o.next_config_id IS NULL
            """
        ),
        {"k": KIND},
    )


def _one_notice_per_amendment(bind, p: str) -> None:
    """One amendment per notice (security review L1): the pick locks the row, this is the backstop."""
    _bounded(bind, f'"{p}".so_amendments', lambda: _run(
        bind,
        f'LOCK TABLE "{p}".so_amendments IN SHARE MODE',
        f'CREATE UNIQUE INDEX IF NOT EXISTS uq_so_amendments_ocn_id ON "{p}".so_amendments (ocn_id) '
        "WHERE ocn_id IS NOT NULL",
    ))


#: The form-comment thread's allowed kinds (fcom_0002) plus the two form kinds that write it
#: without being listed: the sample request and this notice. A superset of every earlier list.
_CONVERSATION_TYPES = (
    "'commercial_project','commercial_master_quotation','commercial_project_task',"
    "'commercial_master_quotation_task','commercial_lead',"
    "'complaint','stock_inquiry','purchase_request','sponsorship_form',"
    "'sample_request','order_change_notice'"
)


CONVERSATION_CHECK = "ck_entity_conversation_messages_entity_type"


def _conversation_kinds(bind) -> None:
    """The Conversation tab writes entity_type = order_change_notice; the CHECK must admit it.
    Swapped NOT VALID under the bounded lock (no scan while every form's Conversation waits);
    `_validate_conversation_kinds` checks the rows afterwards."""
    ck = CONVERSATION_CHECK
    _bounded(bind, "entity_conversation_messages", lambda: _run(
        bind,
        "LOCK TABLE entity_conversation_messages IN ACCESS EXCLUSIVE MODE",
        f"ALTER TABLE entity_conversation_messages DROP CONSTRAINT IF EXISTS {ck}",
        f"ALTER TABLE entity_conversation_messages ADD CONSTRAINT {ck} "
        f"CHECK (entity_type IN ({_CONVERSATION_TYPES})) NOT VALID",
    ))


def _validate_conversation_kinds(bind) -> None:
    bind.execute(sa.text(f"ALTER TABLE entity_conversation_messages VALIDATE CONSTRAINT {CONVERSATION_CHECK}"))


def upgrade() -> None:
    bind = op.get_bind()
    p = _schema(bind, "projects")
    previous = _set_timeouts(bind)
    _tables(bind, p)
    _one_notice_per_amendment(bind, p)
    _conversation_kinds(bind)
    _project_optional(bind, p)
    _seeds(bind, p)
    _permissions(bind)
    _sla(bind)
    _validate_conversation_kinds(bind)
    _restore_timeouts(bind, previous)


def downgrade() -> None:
    """Removes what this revision seeded and the tables it created. The new columns stay: a
    column drop on a table with rows is held for the owner, and every one is nullable or has a
    default. The project foreign key stays SET NULL (a notice without a project is valid now)."""
    bind = op.get_bind()
    p = _schema(bind, "projects")
    bind.execute(sa.text(f"DELETE FROM user_role_permissions WHERE id LIKE '{GRANT_ID_PREFIX}%'"))
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug LIKE 'procurement.order_change_notices.%')"
        )
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug LIKE 'procurement.order_change_notices.%'"))
    bind.execute(
        sa.text(
            "DELETE FROM form_sla_configs WHERE source_entity_type = :k "
            "AND stage_code = 'ocn_' || COALESCE(team_set_code, 'main')"
        ),
        {"k": KIND},
    )
    bind.execute(sa.text("DELETE FROM portal_revision_configs WHERE source_entity_type = :k"), {"k": KIND})
    bind.execute(
        sa.text("DELETE FROM document_numbering_rules WHERE doc_type = :k AND prefix_template = 'OCN{yy}-'"),
        {"k": KIND},
    )
    previous = _set_timeouts(bind)
    _bounded(bind, f'"{p}".so_amendments', lambda: _run(
        bind,
        f'LOCK TABLE "{p}".so_amendments IN ACCESS EXCLUSIVE MODE',
        f'DROP INDEX IF EXISTS "{p}".uq_so_amendments_ocn_id',
    ))
    _bounded(bind, f'"{p}".order_change_notice_lines', lambda: _run(
        bind,
        f'DROP TABLE IF EXISTS "{p}".order_change_notice_lines',
    ))
    _restore_timeouts(bind, previous)
