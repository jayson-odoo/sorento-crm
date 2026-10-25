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
    assert module.down_revision == "or_r4b_top_selling_off"
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


def test_the_permission_is_granted_to_admin_roles_and_project_sales_admins_only(conn):
    from sqlalchemy.orm import Session

    from app.models.user import UserRole

    session = Session(bind=conn)
    existing = {r[0] for r in conn.execute(text("select slug from user_roles"))}
    wanted = [("zzt-psa-a", "Project Sales Admin"), ("zzt-psa-b", "PROJECT sales ADMIN"),
              ("zzt-plain", "Sales Executive"), ("superadmin", "superadmin"), ("admin", "admin")]
    for slug, name in wanted:
        if slug not in existing:
            session.add(UserRole(id=str(uuid.uuid4()), slug=slug, name=name))
    session.flush()
    _upgrade(conn)
    assert conn.execute(text("select count(*) from user_permissions where slug = :s"), {"s": PERMISSION}).scalar() == 1
    holders = {
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
    assert {"zzt-psa-a", "zzt-psa-b", "superadmin", "admin"} <= holders
    assert "zzt-plain" not in holders
