"""PROJECT-REG-PORTAL migration `prreg_0001_project_registrations`, REWORKED in place (UAC C2 and
RW11; PLAN R1, R3, R12): a portal registration is a `projects.projects` row, so the migration
ALTERS `projects.projects` (nullable `project_code`, the approval columns, a PARTIAL identity
index) and `projects.sales_profile` (the portal-only legacy fields) instead of creating a
registrations table; it still seeds the two lookup sets, the approve permission and its grants
and the PPF numbering rule.

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
PROJECT_COLUMNS = {"approval_state", "reject_reason", "submitted_at", "decided_at", "decided_by"}
PROFILE_COLUMNS = {
    "contact_id", "sales_agent_id", "distributor_name", "customer_id", "customer_name",
    "your_ref", "type_of_building", "developer_name", "main_contractor_name", "architect_name",
    "state", "mukim",
}
INDEX = "uq_projects_company_developer_title"
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


def test_migration_names_every_new_model_column_and_creates_no_registrations_table():
    """bootstrap_env builds CI's schema from the models, so a column the model has and the
    migration lacks would pass CI and fail on the real database."""
    from app.models.projects import Project, ProjectSalesProfile

    source = (ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text()
    for column in PROJECT_COLUMNS:
        assert column in Project.__table__.columns, column
        assert column in source, column
    for column in PROFILE_COLUMNS:
        assert column in ProjectSalesProfile.__table__.columns, column
        assert column in source, column
    assert "project_registrations (" not in source.split("def downgrade")[0]


def test_the_registration_model_is_gone_and_the_approval_constants_exist():
    import importlib

    from app.models import projects as m

    with pytest.raises(ImportError):
        importlib.import_module("app.models.project_registration")
    assert (m.APPROVAL_DRAFT, m.APPROVAL_PENDING, m.APPROVAL_REJECTED, m.APPROVAL_APPROVED) == (
        "draft", "pending", "rejected", "approved",
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


def _columns(conn, table):
    return {
        r[0]: r[1]
        for r in conn.execute(
            text(
                "select column_name, is_nullable from information_schema.columns "
                "where table_schema = 'projects' and table_name = :t"
            ),
            {"t": table},
        )
    }


def _company(conn) -> str:
    company_id = conn.execute(text("select id from companies order by code limit 1")).scalar()
    if company_id is None:
        company_id = str(uuid.uuid4())
        conn.execute(
            text("insert into companies (id, code, name, is_active) values (:i, 'ZZTMIG', 'zzt mig', true)"),
            {"i": company_id},
        )
    return company_id


def _insert_project(conn, company_id, title, *, code=None, state=None, developer=None) -> str:
    """Raw SQL on purpose: it names only columns the migration is promised to leave."""
    pid = str(uuid.uuid4())
    columns = "id, company_id, project_code, title, normalised_title, outcome, developer_party_id"
    values = ":i, :c, :code, :t, :n, 'open', :d"
    if state is not None:
        columns += ", approval_state"
        values += ", :s"
    conn.execute(
        text(f"insert into projects.projects ({columns}) values ({values})"),
        {"i": pid, "c": company_id, "code": code, "t": title, "n": title.lower(), "s": state, "d": developer},
    )
    return pid


def _party(conn, company_id, name) -> str:
    pid = str(uuid.uuid4())
    conn.execute(
        text(
            "insert into projects.parties (id, company_id, party_type, name) "
            "values (:i, :c, 'developer', :n)"
        ),
        {"i": pid, "c": company_id, "n": name},
    )
    return pid


def _index_def(conn) -> str:
    return conn.execute(
        text("select indexdef from pg_indexes where schemaname = 'projects' and indexname = :n"), {"n": INDEX}
    ).scalar()


def test_rw11_upgrade_adds_the_approval_columns_and_makes_the_code_nullable(conn):
    _upgrade(conn)
    projects = _columns(conn, "projects")
    assert PROJECT_COLUMNS <= set(projects), PROJECT_COLUMNS - set(projects)
    assert projects["project_code"] == "YES"
    assert projects["approval_state"] == "YES"  # NULL is a staff project
    profile = _columns(conn, "sales_profile")
    assert PROFILE_COLUMNS <= set(profile), PROFILE_COLUMNS - set(profile)


def test_rw11_upgrade_creates_no_registrations_table(conn):
    """Captain decision (25 Oct): the rewritten revision never touches
    `projects.project_registrations`. It must not CREATE it on a schema that lacks it;
    dropping the one the first version left on the dev copy is held for the owner."""
    conn.execute(text("drop table if exists projects.project_registrations"))
    _upgrade(conn)
    assert conn.execute(text("select to_regclass('projects.project_registrations')")).scalar() is None


def test_rw11_the_identity_index_becomes_partial(conn):
    _upgrade(conn)
    definition = _index_def(conn)
    assert definition and "UNIQUE" in definition.upper()
    assert "WHERE" in definition.upper()
    assert "approval_state IS NULL" in definition
    assert "approval_state)::text = 'approved'" in definition or "approval_state = 'approved'" in definition
    assert "developer_party_id" in definition and "normalised_title" in definition


def test_rw11_a_full_index_from_before_the_rework_is_replaced_not_kept(conn):
    """A database that already ran the first version of this revision, or built the old
    model, holds the FULL index under the same name; `IF NOT EXISTS` alone would keep it."""
    conn.execute(text(f"drop index if exists projects.{INDEX}"))
    conn.execute(
        text(
            f"create unique index {INDEX} on projects.projects "
            "(company_id, developer_party_id, normalised_title) nulls not distinct"
        )
    )
    assert "WHERE" not in _index_def(conn).upper()
    _upgrade(conn)
    assert "WHERE" in _index_def(conn).upper()


def test_rw11_after_upgrade_unapproved_rows_do_not_collide_but_staff_rows_still_do(conn):
    from sqlalchemy.exc import IntegrityError

    _upgrade(conn)
    company_id = _company(conn)
    dev = _party(conn, company_id, "ZZT MIG DEV")
    _insert_project(conn, company_id, "ZZT TWIN", state="pending", developer=dev)
    _insert_project(conn, company_id, "ZZT TWIN", state="pending", developer=dev)
    _insert_project(conn, company_id, "ZZT TWIN", state="rejected", developer=dev)
    _insert_project(conn, company_id, "ZZT TWIN", state="draft")
    _insert_project(conn, company_id, "ZZT TWIN", state="draft")
    _insert_project(conn, company_id, "ZZT TWIN", code="PRJ-ZZT-MIG1", developer=dev)  # staff
    with pytest.raises(IntegrityError):
        nested = conn.begin_nested()
        try:
            _insert_project(conn, company_id, "ZZT TWIN", code="PRJ-ZZT-MIG2", developer=dev)
        finally:
            nested.rollback()


def test_rw11_upgrade_keeps_staff_projects_intact(conn):
    company_id = _company(conn)
    kept = {
        _insert_project(conn, company_id, f"ZZT KEEP {n}", code=f"PRJ-ZZT-KEEP{n}"): f"PRJ-ZZT-KEEP{n}"
        for n in range(3)
    }
    _upgrade(conn)
    rows = conn.execute(
        text("select id, project_code, approval_state from projects.projects where id::text = any(:ids)"),
        {"ids": list(kept)},
    ).all()
    assert {str(r[0]): r[1] for r in rows} == kept
    assert all(r[2] is None for r in rows)


def test_rw11_running_the_schema_changes_twice_changes_nothing_more(conn):
    _upgrade(conn)
    once = (_columns(conn, "projects"), _columns(conn, "sales_profile"), _index_def(conn))
    _upgrade(conn)
    assert (_columns(conn, "projects"), _columns(conn, "sales_profile"), _index_def(conn)) == once


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


def test_downgrade_removes_the_permission(conn):
    _upgrade(conn)
    _downgrade(conn)
    assert conn.execute(text("select count(*) from user_permissions where slug = :s"), {"s": PERMISSION}).scalar() == 0


def test_rw11_downgrade_deletes_the_code_less_portal_rows_and_keeps_everything_with_a_code(conn):
    _upgrade(conn)
    company_id = _company(conn)
    dev = _party(conn, company_id, "ZZT MIG DEV")
    staff = _insert_project(conn, company_id, "ZZT DOWN STAFF", code="PRJ-ZZT-DOWN1", developer=dev)
    approved = _insert_project(conn, company_id, "ZZT DOWN APPROVED", code="PPF2610001", state="approved")
    gone = [
        _insert_project(conn, company_id, "ZZT DOWN STAFF", state="pending", developer=dev),  # same dev + title as staff
        _insert_project(conn, company_id, "ZZT DOWN PENDING", state="pending"),
        _insert_project(conn, company_id, "ZZT DOWN DRAFT", state="draft"),
        _insert_project(conn, company_id, "ZZT DOWN REJECTED", state="rejected"),
    ]
    for pid in gone + [approved]:
        conn.execute(
            text("insert into projects.sales_profile (project_id, state) values (:i, 'Johor')"), {"i": pid}
        )
    _downgrade(conn)
    left = {
        str(r[0])
        for r in conn.execute(
            text("select id from projects.projects where id::text = any(:ids)"), {"ids": [staff, approved, *gone]}
        )
    }
    assert left == {staff, approved}
    profiles = {
        str(r[0])
        for r in conn.execute(
            text("select project_id from projects.sales_profile where project_id::text = any(:ids)"),
            {"ids": [approved, *gone]},
        )
    }
    assert profiles == {approved}  # the deleted rows took their profiles with them


def test_rw11_downgrade_restores_not_null_and_the_full_index(conn):
    _upgrade(conn)
    assert _columns(conn, "projects")["project_code"] == "YES"  # precondition: the upgrade relaxed it
    assert "WHERE" in _index_def(conn).upper()
    _downgrade(conn)
    assert _columns(conn, "projects")["project_code"] == "NO"
    definition = _index_def(conn)
    assert definition and "UNIQUE" in definition.upper()
    assert "WHERE" not in definition.upper()
    assert "approval_state" not in definition


def test_rw11_downgrade_then_upgrade_again_round_trips(conn):
    _upgrade(conn)
    _downgrade(conn)
    _upgrade(conn)
    assert _columns(conn, "projects")["project_code"] == "YES"
    assert "WHERE" in _index_def(conn).upper()


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
