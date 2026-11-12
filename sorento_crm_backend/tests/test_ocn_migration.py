"""OCN-ORDER-CHANGE-NOTICE red tests: the one migration, `ocn_0001_order_change_notice`.

UAC A3 (project optional, ON DELETE SET NULL), C1 / C2 (SLA policy + three stage rows copied
from the purchase request, idempotent, a no-op without PR rows), D1 (seven slugs, grants copied
from the matching PR slug holders + admin / superadmin, `ocn-` ids), the `order_change_notice`
numbering rule, the four change types, the enabled revision config, the settings columns.

The migration's `upgrade()` runs for real, TWICE, on the blank scratch schema
(tests/_pg_fixture.py) through an alembic `Operations` context inside the session's
rolled-back transaction (pattern: tests/test_appeal_wording.py). That only works when the
migration's raw SQL resolves the `projects` schema the way `prreg_0001_project_registrations`
does (`_schema(bind, "projects")`): a hard-coded `projects.` would write the real schema while
this test reads the scratch one. It is scratch-schema DDL only, so it stays in the xdist pool.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from ._pg_fixture import blank_session

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "ocn_0001_order_change_notice"
KIND = "order_change_notice"
SORENTO = "00000000-0000-0000-0000-000000000001"
OCN_SLUGS = tuple(
    f"procurement.order_change_notices.{s}"
    for s in ("view", "view_own", "create", "edit", "delete", "approve", "report")
)


def uid() -> str:
    return str(uuid.uuid4())


def _module():
    path = ROOT / "alembic" / "versions" / f"{MIGRATION}.py"
    spec = importlib.util.spec_from_file_location(f"zzt_{MIGRATION}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(db, times: int = 1) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _module()
    for _ in range(times):
        context = MigrationContext.configure(connection=db.connection())
        with Operations.context(context):
            module.upgrade()
        db.flush()


def _p(db) -> str:
    """The scratch copy of the `projects` schema (blank_session's search_path)."""
    return f"{db.execute(text('select current_schema()')).scalar()}_projects"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ the revision itself


def test_the_revision_fits_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _module()
    assert module.revision == MIGRATION and len(module.revision) <= 32
    assert module.down_revision
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert MIGRATION in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_the_upgrade_runs_twice_on_a_blank_schema(db):
    _upgrade(db, times=2)


# ------------------------------------------------------------------ A3 + the new tables and columns


def _project_fk(db):
    p = _p(db)
    return db.execute(
        text(
            "SELECT c.conname, c.confdeltype, a.attnotnull "
            "FROM pg_constraint c JOIN pg_attribute a "
            "  ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
            f"WHERE c.conrelid = to_regclass('\"{p}\".order_change_notices') "
            "AND c.contype = 'f' AND a.attname = 'project_id'"
        )
    ).all()


def _as_before_the_lane(db):
    """`project_id` NOT NULL with ON DELETE CASCADE, as main has it today."""
    p = _p(db)
    for conname, _rule, _nn in _project_fk(db):
        db.execute(text(f'ALTER TABLE "{p}".order_change_notices DROP CONSTRAINT "{conname}"'))
    db.execute(text(
        f'ALTER TABLE "{p}".order_change_notices ADD CONSTRAINT order_change_notices_project_id_fkey '
        f'FOREIGN KEY (project_id) REFERENCES "{p}".projects (id) ON DELETE CASCADE'
    ))
    db.execute(text(f'ALTER TABLE "{p}".order_change_notices ALTER COLUMN project_id SET NOT NULL'))
    db.flush()


def test_a3_the_model_makes_project_optional_and_set_null():
    from app.models.project_so import OrderChangeNotice

    column = OrderChangeNotice.__table__.c.project_id
    assert column.nullable is True
    (fk,) = column.foreign_keys
    assert fk.ondelete == "SET NULL"


def test_a3_the_migration_turns_cascade_into_set_null_and_drops_not_null(db):
    _as_before_the_lane(db)
    assert {(rule, nn) for _n, rule, nn in _project_fk(db)} == {("c", True)}
    _upgrade(db, times=2)
    assert {(rule, nn) for _n, rule, nn in _project_fk(db)} == {("n", False)}


def test_a3_deleting_a_project_leaves_its_ocn_with_no_project(db):
    from app.models.base import company_scope
    from app.models.project_so import OrderChangeNotice
    from app.models.projects import Project

    _upgrade(db)
    with company_scope(db, frozenset({SORENTO})):
        project = Project(id=uid(), title="ZZT Project Gone", normalised_title="zzt project gone",
                          company_id=SORENTO)
        db.add(project)
        db.flush()
        row = OrderChangeNotice(id=uid(), company_id=SORENTO, ocn_number="OCN26-0001",
                                project_id=project.id, status="draft", source="crm")
        db.add(row)
        db.flush()
        db.execute(text(f'DELETE FROM "{_p(db)}".projects WHERE id = :i'), {"i": project.id})
        db.expire_all()
        survivor = db.query(OrderChangeNotice).filter(OrderChangeNotice.id == row.id).one()
        assert survivor.project_id is None


def _columns(db, schema: str, table: str) -> dict:
    rows = db.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t"
        ),
        {"s": schema, "t": table},
    ).all()
    return {name: kind for name, kind in rows}


def test_the_ocn_gains_its_lifecycle_columns(db):
    _upgrade(db)
    cols = _columns(db, _p(db), "order_change_notices")
    assert {
        "status", "approval_status", "change_type_id", "customer_id", "customer_name",
        "customer_po_no", "so_no_text", "cs_in_charge_user_id", "sales_in_charge_user_id",
        "description", "cs_comment", "approved_by", "approval_comments", "rejected_by_id",
        "requested_approval_by_user_id", "submitted_at", "voided_by", "voided_at", "void_reason",
        "revision_no", "source", "ocn_date", "approver_id", "approved_at",
    } <= set(cols)


def test_the_lines_and_change_type_tables_have_uuid_ids(db):
    _upgrade(db)
    lines = _columns(db, _p(db), "order_change_notice_lines")
    assert {"id", "ocn_id", "product_id", "qty_before", "qty_after", "date_before", "date_after",
            "delivered_qty", "remark", "position"} <= set(lines)
    assert lines["id"] == "uuid"
    types = _columns(db, _p(db), "order_change_types")
    assert {"id", "name", "risk_level", "guide_text", "is_active", "position"} <= set(types)
    assert types["id"] == "uuid"
    nullable = db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns WHERE table_schema = :s "
            "AND table_name = 'order_change_notice_lines' AND column_name = 'product_id'"
        ),
        {"s": _p(db)},
    ).scalar()
    assert nullable == "NO", "a line always names a catalogue product"


def test_the_settings_columns_exist_and_default_off(db):
    from app.models.user import SystemSetting

    _upgrade(db)
    current = db.execute(text("select current_schema()")).scalar()
    cols = _columns(db, current, "system_settings")
    assert "order_change_notice_require_project" in cols
    assert "order_change_notice_default_approver_user_id" in cols
    row = SystemSetting(id=uid())
    db.add(row)
    db.flush()
    db.refresh(row)
    assert row.order_change_notice_require_project is False
    assert row.order_change_notice_default_approver_user_id is None


# ------------------------------------------------------------------ seeds: types, numbering, revision config


def test_the_four_change_types_are_seeded_once(db):
    _upgrade(db, times=2)
    rows = db.execute(
        text(f'SELECT name, risk_level, guide_text, is_active FROM "{_p(db)}".order_change_types')
    ).all()
    assert {(n, r.lower()) for n, r, _g, _a in rows} == {
        ("Advance", "low"), ("Exchange", "high"), ("Cancellation", "highest"), ("Delay", "low"),
    }
    assert len(rows) == 4
    assert all(g and g.strip() for _n, _r, g, _a in rows)
    assert all(a for *_x, a in rows)


def test_the_numbering_rule_is_seeded_once_yearly_four_digits(db):
    _upgrade(db, times=2)
    rows = db.execute(
        text(
            "SELECT prefix_template, number_digits, reset_policy, enabled FROM document_numbering_rules "
            "WHERE doc_type = :k"
        ),
        {"k": KIND},
    ).all()
    assert rows, "no order_change_notice numbering rule"
    assert len(rows) == len({tuple(r) for r in rows}) and len(rows) <= 2
    for prefix, digits, reset, enabled in rows:
        assert (prefix, digits, reset, enabled) == ("OCN{yy}-", 4, "yearly", True)


def test_the_revision_config_is_seeded_enabled_once(db):
    _upgrade(db, times=2)
    rows = db.execute(
        text("SELECT is_enabled FROM portal_revision_configs WHERE source_entity_type = :k"), {"k": KIND}
    ).all()
    assert [r[0] for r in rows] == [True]


# ------------------------------------------------------------------ C1 / C2 SLA


PR_STAGES = (
    # team set, start, resolve, advance, notify_assignee, notify_on_escalation, active
    ("project_sales", "submit", "send_for_approval,reject_submitted,voided", "send_for_approval", True, True, True),
    ("project_sales_manager", "send_for_approval", "approved,approval_rejected,voided", "approved", True, False, True),
    ("customer_service", "approved", "resolved,voided", None, False, True, True),
)
PR_TIERS = ((1, "Tier 1", 4, 24), (2, "Tier 2", 8, 72), (3, "Tier 3", 2, 24))


def _seed_pr_sla(db):
    from app.models.sla import FormSLAConfig, SLAPolicy, SLAPolicyTier

    policy = SLAPolicy(id=uid(), code="PURCHASE_REQUEST", name="Purchase Request", company_id=SORENTO)
    db.add(policy)
    for level, name, respond, resolve in PR_TIERS:
        db.add(SLAPolicyTier(id=uid(), policy_id=policy.id, tier_level=level, tier_name=name,
                             response_hours=respond, resolution_hours=resolve))
    db.flush()
    rows = []
    for i, (team_set, start, resolve, advance, notify, notify_esc, active) in enumerate(PR_STAGES):
        row = FormSLAConfig(
            id=uid(), source_entity_type="purchase_request", stage_code=f"pr_stage_{i}",
            policy_id=policy.id, agent_code="zzt_pr_agent", team_set_code=team_set,
            start_event=start, resolve_event=resolve, advance_on_event=advance,
            is_active=active, notify_assignee=notify, notify_on_escalation=notify_esc,
        )
        db.add(row)
        db.flush()
        rows.append(row)
    for here, nxt in zip(rows, rows[1:]):
        here.next_config_id = nxt.id
    db.flush()
    return policy, rows


def _configs(db, kind):
    return db.execute(
        text(
            "SELECT id, team_set_code, policy_id, agent_code, start_event, respond_event, resolve_event, "
            "advance_on_event, is_active, notify_assignee, notify_on_escalation, next_config_id "
            "FROM form_sla_configs WHERE source_entity_type = :k ORDER BY team_set_code"
        ),
        {"k": kind},
    ).mappings().all()


def _policy(db, code):
    return db.execute(
        text("SELECT id, company_id FROM sla_policies WHERE code = :c"), {"c": code}
    ).mappings().all()


def test_c1_the_ocn_policy_copies_the_pr_tiers(db):
    _seed_pr_sla(db)
    _upgrade(db, times=2)
    (policy,) = _policy(db, "ORDER_CHANGE_NOTICE")
    assert str(policy["company_id"]) == SORENTO
    tiers = db.execute(
        text(
            "SELECT tier_level, tier_name, response_hours, resolution_hours FROM sla_policy_tiers "
            "WHERE policy_id = :p ORDER BY tier_level"
        ),
        {"p": policy["id"]},
    ).all()
    assert [(l, n, float(r), float(s)) for l, n, r, s in tiers] == [
        (l, n, float(r), float(s)) for l, n, r, s in PR_TIERS
    ]


def test_c1_three_stage_rows_copy_the_pr_rows(db):
    _pr_policy, _pr_rows = _seed_pr_sla(db)
    _upgrade(db, times=2)
    pr = {r["team_set_code"]: r for r in _configs(db, "purchase_request")}
    ocn = _configs(db, KIND)
    assert [r["team_set_code"] for r in ocn] == ["customer_service", "project_sales", "project_sales_manager"]
    (policy,) = _policy(db, "ORDER_CHANGE_NOTICE")
    ocn_ids = {r["id"] for r in ocn}
    for row in ocn:
        src = pr[row["team_set_code"]]
        for key in ("agent_code", "start_event", "respond_event", "resolve_event", "advance_on_event",
                    "is_active", "notify_assignee", "notify_on_escalation"):
            assert row[key] == src[key], (row["team_set_code"], key)
        assert row["policy_id"] == policy["id"]
        # a link, if copied, points at an OCN row, never back into the PR chain
        assert row["next_config_id"] is None or row["next_config_id"] in ocn_ids


def test_c2_the_seed_is_a_no_op_without_pr_rows(db):
    _upgrade(db, times=2)
    assert _configs(db, KIND) == []
    assert _policy(db, "ORDER_CHANGE_NOTICE") == []


def test_c2_an_existing_ocn_stage_row_is_left_alone(db):
    from app.models.sla import FormSLAConfig

    policy, _rows = _seed_pr_sla(db)
    mine = FormSLAConfig(
        id=uid(), source_entity_type=KIND, stage_code="zzt_admin_main", policy_id=policy.id,
        agent_code="zzt_admin_agent", team_set_code="project_sales", start_event="submit",
        resolve_event="send_for_approval", is_active=True, notify_assignee=True,
    )
    db.add(mine)
    db.flush()
    _upgrade(db, times=2)
    rows = _configs(db, KIND)
    main = [r for r in rows if r["team_set_code"] == "project_sales"]
    assert len(main) == 1 and main[0]["agent_code"] == "zzt_admin_agent"
    assert len(rows) == 3


# ------------------------------------------------------------------ D1 permissions and grants


def _role(db, slug, *perm_slugs):
    from app.models.user import UserPermission, UserRole, UserRolePermission

    role = UserRole(id=uid(), slug=slug, name=f"ZZT {slug}")
    db.add(role)
    db.flush()
    for p in perm_slugs:
        perm = db.query(UserPermission).filter(UserPermission.slug == p).first()
        if perm is None:
            perm = UserPermission(id=uid(), slug=p, name=p)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=uid(), role_id=role.id, permission_id=perm.id))
    db.flush()
    return role


def _granted(db, role_id) -> list[str]:
    return [
        r[0]
        for r in db.execute(
            text(
                "SELECT p.slug FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :r AND p.slug LIKE 'procurement.order_change_notices.%'"
            ),
            {"r": role_id},
        ).all()
    ]


def test_d1_the_seven_slugs_exist_once(db):
    _upgrade(db, times=2)
    rows = db.execute(
        text("SELECT slug FROM user_permissions WHERE slug LIKE 'procurement.order_change_notices.%'")
    ).all()
    assert sorted(r[0] for r in rows) == sorted(OCN_SLUGS)


def test_d1_the_slugs_are_in_the_permission_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert set(OCN_SLUGS) <= slugs


def test_d1_grants_follow_the_matching_purchase_request_slug(db):
    viewer = _role(db, "zzt-pr-viewer", "procurement.purchase_requests.view")
    sender = _role(db, "zzt-pr-sender", "procurement.purchase_requests.send_for_approval")
    approver = _role(db, "zzt-pr-approver", "procurement.purchase_requests.approve")
    nobody = _role(db, "zzt-unrelated", "master_data.products.view")
    _upgrade(db, times=2)

    assert "procurement.order_change_notices.view" in _granted(db, viewer.id)
    assert "procurement.order_change_notices.approve" not in _granted(db, viewer.id)
    assert "procurement.order_change_notices.edit" in _granted(db, sender.id)
    assert "procurement.order_change_notices.approve" in _granted(db, approver.id)
    assert _granted(db, nobody.id) == []
    for role in (viewer, sender, approver):
        granted = _granted(db, role.id)
        assert len(granted) == len(set(granted)), f"duplicate grant on {role.slug}: {granted}"


def test_d1_admin_and_superadmin_get_every_slug_with_ocn_ids(db):
    admin = _role(db, "admin")
    superadmin = _role(db, "superadmin")
    _upgrade(db, times=2)
    for role in (admin, superadmin):
        assert sorted(_granted(db, role.id)) == sorted(OCN_SLUGS), role.slug
    ids = db.execute(
        text(
            "SELECT rp.id FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
            "WHERE p.slug LIKE 'procurement.order_change_notices.%'"
        )
    ).all()
    assert ids and all(str(i[0]).startswith("ocn-") for i in ids)
