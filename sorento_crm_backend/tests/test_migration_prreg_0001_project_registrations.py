"""PROJECT-REG-PORTAL migration `prreg_0001_project_registrations` (UAC C2, plus the table,
the profile columns, the two lookup sets and the permission grant; PLAN D3, D6, D10, D12).

The behavioural tests execute the migration's own `upgrade()` inside a transaction that is
always rolled back (the `test_complaint_settled_on_site` precedent): the schema qualifier
`projects.` in its DDL resolves against the real schema, so the blank scratch schema cannot
host it. Every statement is idempotent, and nothing here outlives the rollback.
"""
from __future__ import annotations

import hashlib
import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
REVISION = "prreg_0001_project_registrations"
PERMISSION = "projects.registrations.approve"
TABLE_COLUMNS = {
    "id", "company_id", "status", "contact_id", "sales_agent_id", "applicant_user_id",
    "project_id", "submitted_at", "decided_at", "decided_by", "reject_reason",
    "created_at", "updated_at",
    "title", "distributor_name", "customer_id", "customer_name", "type_of_building",
    "state", "mukim", "your_ref", "developer_name", "main_contractor_name", "architect_name",
}
STATES = {
    "johor", "kedah", "kelantan", "melaka", "negeri sembilan", "pahang", "perak", "perlis",
    "sabah", "sarawak", "selangor", "terengganu", "kuala lumpur", "labuan", "putrajaya",
}


def _module():
    path = ROOT / "alembic" / "versions" / f"{REVISION}.py"
    spec = importlib.util.spec_from_file_location(REVISION, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _downgrade(conn) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _module()
    with Operations.context(MigrationContext.configure(conn)):
        module.downgrade()


def _upgrade(conn) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _module()
    with Operations.context(MigrationContext.configure(conn)):
        module.upgrade()


@pytest.fixture
def conn():
    from app.database import engine

    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _set_project_rule(conn, **cols):
    conn.execute(text("delete from document_numbering_rules where doc_type = 'project'"))
    values = {
        "id": str(uuid.uuid4()), "prefix_template": "PRJ-", "number_digits": 6, "next_value": 123,
        "start_value": 1, "reset_policy": "none", "last_reset_key": None,
    }
    values.update(cols)
    conn.execute(
        text(
            "insert into document_numbering_rules "
            "(id, doc_type, enabled, prefix_template, number_digits, next_value, start_value, "
            " reset_policy, last_reset_key) "
            "values (:id, 'project', true, :prefix_template, :number_digits, :next_value, "
            " :start_value, :reset_policy, :last_reset_key)"
        ),
        values,
    )
    return values["id"]


def _rule(conn, rule_id):
    return tuple(
        conn.execute(
            text(
                "select prefix_template, number_digits, reset_policy, start_value from "
                "document_numbering_rules where id = :i"
            ),
            {"i": rule_id},
        ).one()
    )


def _codes_digest(conn):
    return conn.execute(
        text("select count(*), md5(coalesce(string_agg(project_code, ',' order by project_code), '')) from projects.projects")
    ).one()


# ------------------------------------------------------------------ static


def test_revision_id_fits_chains_on_the_head_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _module()
    assert module.revision == REVISION
    assert len(module.revision) <= 32
    assert module.down_revision  # chained; the head check below survives the next re-parent
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert REVISION in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_migration_creates_every_model_column():
    """bootstrap_env builds CI's schema from the models, so a column the model has and the
    migration lacks would pass CI and fail on the real database."""
    from app.models.project_registration import ProjectRegistration

    source = (ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text()
    for column in ProjectRegistration.__table__.columns:
        assert column.name in source, column.name
    assert ProjectRegistration.__table__.schema == "projects"
    assert ProjectRegistration.__tablename__ == "project_registrations"


def test_the_model_constants():
    from app.models import project_registration as m

    assert (m.STATUS_DRAFT, m.STATUS_PENDING, m.STATUS_APPROVED, m.STATUS_REJECTED) == (
        "draft", "pending", "approved", "rejected",
    )


# ------------------------------------------------------------------ C2 numbering rule


def test_c2_the_shipped_default_rule_becomes_ppf_and_codes_stay(conn):
    rule_id = _set_project_rule(conn)
    before = _codes_digest(conn)
    _upgrade(conn)
    assert _rule(conn, rule_id) == ("PPF{yy}{mm}", 3, "monthly", 1)
    assert _codes_digest(conn) == before


def test_c2_a_customised_rule_is_left_alone(conn):
    rule_id = _set_project_rule(conn, prefix_template="ACME-{year}-", number_digits=5, reset_policy="yearly", next_value=9)
    _upgrade(conn)
    assert _rule(conn, rule_id) == ("ACME-{year}-", 5, "yearly", 1)
    next_value = conn.execute(
        text("select next_value from document_numbering_rules where id = :i"), {"i": rule_id}
    ).scalar()
    assert next_value == 9


def test_c2_running_it_twice_changes_nothing_more(conn):
    rule_id = _set_project_rule(conn)
    _upgrade(conn)
    first = conn.execute(
        text("select next_value, last_reset_key from document_numbering_rules where id = :i"), {"i": rule_id}
    ).one()
    _upgrade(conn)
    assert _rule(conn, rule_id) == ("PPF{yy}{mm}", 3, "monthly", 1)
    assert conn.execute(
        text("select next_value, last_reset_key from document_numbering_rules where id = :i"), {"i": rule_id}
    ).one() == first


def test_c2_the_upgraded_rule_draws_a_ppf_code(conn):
    from sqlalchemy.orm import Session

    from app.services.numbering_service import NumberingService

    _set_project_rule(conn)
    _upgrade(conn)
    session = Session(bind=conn)
    code = NumberingService(session).get_next_number("project", reference_date=date(2026, 5, 7), commit_rule=False)
    assert code.startswith("PPF2605") and len(code) == len("PPF2605") + 3


# ------------------------------------------------------------------ schema and seeds


def test_the_table_and_the_profile_columns_exist(conn):
    _upgrade(conn)
    cols = {
        r[0]
        for r in conn.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_schema = 'projects' and table_name = 'project_registrations'"
            )
        )
    }
    assert TABLE_COLUMNS <= cols, TABLE_COLUMNS - cols
    profile = {
        r[0]
        for r in conn.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_schema = 'projects' and table_name = 'sales_profile'"
            )
        )
    }
    assert {"state", "mukim"} <= profile


def test_the_two_lookup_sets_are_seeded(conn):
    _upgrade(conn)
    for key in ("project_building_type", "my_state"):
        rows = conn.execute(
            text(
                "select o.label, o.is_active from lookup_options o join lookup_sets s on s.id = o.set_id "
                "where s.set_key = :k and s.is_active"
            ),
            {"k": key},
        ).all()
        assert rows, key
        assert all(r[1] for r in rows), key
    labels = [
        r[0]
        for r in conn.execute(
            text(
                "select o.label from lookup_options o join lookup_sets s on s.id = o.set_id "
                "where s.set_key = 'my_state'"
            )
        )
    ]
    assert len(labels) == 16
    assert STATES <= {label.strip().casefold() for label in labels}


def test_the_lookup_seeds_are_idempotent(conn):
    _upgrade(conn)
    _upgrade(conn)
    count = conn.execute(
        text(
            "select count(*) from lookup_options o join lookup_sets s on s.id = o.set_id "
            "where s.set_key = 'my_state'"
        )
    ).scalar()
    assert count == 16
    sets = conn.execute(
        text("select count(*) from lookup_sets where set_key in ('my_state', 'project_building_type')")
    ).scalar()
    assert sets == 2


def _clear_grants(conn):
    conn.execute(
        text(
            "delete from user_role_permissions where permission_id in "
            "(select id from user_permissions where slug = :s)"
        ),
        {"s": PERMISSION},
    )


def _role(session, slug: str, name: str):
    from app.models.user import UserRole

    row = UserRole(id=str(uuid.uuid4()), slug=slug, name=name)
    session.add(row)
    session.flush()
    return row


def _holders(conn) -> set:
    return {
        r[0]
        for r in conn.execute(
            text(
                "select r.slug from user_role_permissions rp "
                "join user_roles r on r.id = rp.role_id "
                "join user_permissions p on p.id = rp.permission_id where p.slug = :s"
            ),
            {"s": PERMISSION},
        )
    }


def test_the_approver_roles_are_both_named_in_one_constant_of_the_migration():
    """Owner ruling 25 Oct 16:35: Project Sales Manager AND Project Sales Coordinator."""
    names = {n.strip().casefold() for n in _module().APPROVER_ROLE_NAMES}
    assert names == {"project sales manager", "project sales coordinator"}


def test_the_permission_goes_to_the_admin_roles_and_every_named_approver_role(conn):
    from sqlalchemy.orm import Session

    names = _module().APPROVER_ROLE_NAMES  # read from the migration, never hard-coded here
    session = Session(bind=conn)
    existing = {r[0] for r in conn.execute(text("select slug from user_roles"))}
    for slug in ("superadmin", "admin"):
        if slug not in existing:
            _role(session, slug, slug)
    named = [_role(session, f"zzt-approver-{i}", n.upper()) for i, n in enumerate(names)]
    other = _role(session, "zzt-other-role", "Sales Executive")
    old_match = _role(session, "zzt-old-psa", "Project Sales Admin")
    _clear_grants(conn)
    _upgrade(conn)
    holders = _holders(conn)
    assert {"superadmin", "admin", *(r.slug for r in named)} <= holders
    assert other.slug not in holders
    # the old "project sales admin" name match is gone: that name is no longer special
    assert old_match.slug not in holders
    assert conn.execute(text("select count(*) from user_permissions where slug = :s"), {"s": PERMISSION}).scalar() == 1


def test_with_no_role_of_those_names_only_the_admin_roles_hold_the_permission(conn):
    from sqlalchemy.orm import Session

    session = Session(bind=conn)
    for name in _module().APPROVER_ROLE_NAMES:
        conn.execute(text("delete from user_role_permissions where role_id in (select id from user_roles where lower(name) = lower(:n))"), {"n": name})
        conn.execute(text("delete from user_role_assignments where role_id in (select id from user_roles where lower(name) = lower(:n))"), {"n": name})
        conn.execute(text("delete from user_roles where lower(name) = lower(:n)"), {"n": name})
    existing = {r[0] for r in conn.execute(text("select slug from user_roles"))}
    for slug in ("superadmin", "admin"):
        if slug not in existing:
            _role(session, slug, slug)
    _role(session, "zzt-sales-exec", "Sales Executive")
    _role(session, "zzt-old-psa", "Project Sales Admin")
    _clear_grants(conn)
    _upgrade(conn)
    assert _holders(conn) == {"superadmin", "admin"}


# ------------------------------------------------------------------ downgrade (item 7')


def test_downgrade_restores_the_default_project_rule_where_it_is_still_the_ppf_shape(conn):
    rule_id = _set_project_rule(conn)
    _upgrade(conn)
    assert _rule(conn, rule_id) == ("PPF{yy}{mm}", 3, "monthly", 1)
    _downgrade(conn)
    assert _rule(conn, rule_id)[:3] == ("PRJ-", 6, "none")


def test_downgrade_leaves_a_customised_rule_alone(conn):
    rule_id = _set_project_rule(
        conn, prefix_template="ACME-{year}-", number_digits=5, reset_policy="yearly", next_value=9
    )
    _upgrade(conn)
    _downgrade(conn)
    assert _rule(conn, rule_id)[:3] == ("ACME-{year}-", 5, "yearly")


def test_downgrade_leaves_a_ppf_rule_someone_changed_since(conn):
    """Only the exact shape the upgrade wrote is rolled back: PPF with 4 digits is a choice."""
    rule_id = _set_project_rule(conn, prefix_template="PPF{yy}{mm}", number_digits=4, reset_policy="monthly")
    _downgrade(conn)
    assert _rule(conn, rule_id)[:3] == ("PPF{yy}{mm}", 4, "monthly")


def test_downgrade_removes_the_permission_and_the_table(conn):
    _upgrade(conn)
    _downgrade(conn)
    assert conn.execute(text("select count(*) from user_permissions where slug = :s"), {"s": PERMISSION}).scalar() == 0
    assert conn.execute(text("select to_regclass('projects.project_registrations')")).scalar() is None


def test_downgrade_keeps_the_counter_past_every_existing_prj_code(conn):
    """Rolling back must not hand out a PRJ code that already exists (the counter went
    PPF-side while the upgrade ran): 248 after a PRJ-000247, drawn through an upgrade and a
    rollback, still reads PRJ-000248."""
    from datetime import date

    from sqlalchemy.orm import Session

    from app.services.numbering_service import NumberingService

    rule_id = _set_project_rule(conn, next_value=248)
    company_id = conn.execute(text("select id from companies order by code limit 1")).scalar()
    if company_id is None:
        company_id = str(uuid.uuid4())
        conn.execute(
            text("insert into companies (id, code, name, is_active) values (:i, 'ZZTMIG', 'zzt mig', true)"),
            {"i": company_id},
        )
    conn.execute(
        text(
            "insert into projects.projects (id, company_id, project_code, title, normalised_title, outcome) "
            "values (:i, :c, 'PRJ-000247', 'ZZT MIG TOWER', 'zzt mig tower', 'open')"
        ),
        {"i": str(uuid.uuid4()), "c": company_id},
    )
    _upgrade(conn)
    session = Session(bind=conn)
    code = NumberingService(session).get_next_number("project", reference_date=date(2026, 10, 5), commit_rule=False)
    assert code == "PPF2610001"
    session.flush()
    _downgrade(conn)
    assert _rule(conn, rule_id)[:3] == ("PRJ-", 6, "none")
    session.expire_all()
    assert NumberingService(session).get_next_number("project", commit_rule=False) == "PRJ-000248"
