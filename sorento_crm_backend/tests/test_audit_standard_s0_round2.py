"""Audit standard S0 (#1281), fix lane round 2: the reviewer pass at 7a56073f.

One class per finding (B1, S1, S2, S3, N1 to N6). Each test failed at 7a56073f for the
reviewer's failing scenario before its repair landed; the closing PR comment lists them.
Everything runs on the blank Postgres schema, rolled back.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.database import Base
from app.models.audit import AuditLog
from app.services import audit_service
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners

from ._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _rows(db, entity_id, action=None):
    q = db.query(AuditLog).filter(AuditLog.entity_id == str(entity_id))
    if action:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.changed_at, AuditLog.id).all()


# --- B1: a grandchild takes its owning company, however many hops away -----------------


def _reaches_company(table, seen: frozenset, depth: int) -> bool:
    """Independent of the implementation: does a NOT NULL foreign-key chain from ``table``
    reach a table that carries ``company_id`` (or ``companies`` itself)?"""
    if table.name == "companies" or "company_id" in table.c:
        return True
    if depth == 0:
        return False
    for column in table.columns:
        if not column.foreign_keys or column.nullable:
            continue
        for fk in column.foreign_keys:
            target = fk.column.table
            if target.name not in seen and _reaches_company(target, seen | {target.name}, depth - 1):
                return True
    return False


class TestB1Grandchildren:
    def _form_tree(self, db):
        from app.models.forms import Form, FormField, FormSection

        company = str(uuid.uuid4())
        form = Form(code=unique_code("F")[:100], name="Probe form", company_id=company)
        db.add(form)
        db.flush()
        section = FormSection(form_id=form.id, section_name="S")
        db.add(section)
        db.flush()
        field = FormField(section_id=section.id, field_name="f", field_label="F", field_type="text")
        db.add(field)
        db.flush()
        return company, form, section, field

    def test_b1_form_field_rows_carry_the_forms_company(self, db):
        from app.models.forms import FormField

        company, form, section, field = self._form_tree(db)
        field.field_label = "G"
        db.flush()
        db.query(FormField).filter(FormField.id == field.id).update({"field_label": "H"}, synchronize_session=False)
        rows = _rows(db, field.id)
        assert [r.action for r in rows] == ["CREATE", "UPDATE", "UPDATE"]
        assert {str(r.company_id) for r in rows} == {company}
        assert {str(r.company_id) for r in _rows(db, section.id)} == {company}

    def test_b1_the_chain_is_read_from_the_database_when_nothing_is_loaded(self, db):
        from app.models.forms import FormField

        company, form, section, field = self._form_tree(db)
        field_id = field.id
        db.expunge_all()  # the form and the section are no longer in the identity map
        db.query(FormField).filter(FormField.id == field_id).delete(synchronize_session=False)
        (row,) = _rows(db, field_id, "DELETE")
        assert str(row.company_id) == company

    @pytest.mark.parametrize(
        "module,name,owner",
        [
            ("app.models.forms", "FormField", "forms"),
            ("app.models.price_tag", "PriceTagRequestLinePart", "price_tag_requests"),
            ("app.models.price_tag", "PriceTagRequestTag", "price_tag_requests"),
        ],
    )
    def test_b1_the_three_grandchildren_resolve_to_their_owner(self, module, name, owner):
        import importlib

        cls = getattr(importlib.import_module(module), name)
        chain = audit_service._company_chain(cls)
        assert chain, f"{name} resolves to no company"
        assert chain[-1][1].name == owner

    def test_b1_guard_every_audited_class_that_can_reach_a_company_does(self):
        missed = []
        for mapper in Base.registry.mappers:
            cls = mapper.class_
            if cls is AuditLog or getattr(cls, "__audit_skip__", None):
                continue
            table = mapper.local_table
            if "company_id" in table.c or table.name == "companies":
                continue
            if _reaches_company(table, frozenset({table.name}), 4) and audit_service._company_fk(cls) is None:
                missed.append(table.name)
        assert missed == []


# --- S1: the maintenance flag has no effect for the app role ---------------------------


class TestS1FlagNotForTheAppRole:
    """Probed as a NOSUPERUSER role with plain DML grants on audit_logs: the shape of the
    application's own login. At 7a56073f it could set the flag itself and rewrite history."""

    def _as_app_role(self, db):
        from sqlalchemy import text

        role = f"s0_app_probe_{uuid.uuid4().hex[:10]}"
        schema = db.execute(text("SELECT current_schema()")).scalar()
        db.execute(text(f'CREATE ROLE "{role}" NOSUPERUSER NOLOGIN'))  # rolled back with the test
        db.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
        db.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON "{schema}".audit_logs TO "{role}"'))
        row_id = str(uuid.uuid4())
        db.execute(
            text("INSERT INTO audit_logs (id, entity_type, entity_id, action) VALUES (:i, 'probe', :e, 'EVENT')"),
            {"i": row_id, "e": row_id},
        )
        return role, row_id

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE audit_logs SET description = 'rewritten' WHERE id = :i",
            "DELETE FROM audit_logs WHERE id = :i",
        ],
    )
    @pytest.mark.parametrize("scope", ["LOCAL", "SESSION"])
    def test_s1_the_app_role_cannot_use_the_flag(self, db, statement, scope):
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError

        role, row_id = self._as_app_role(db)
        nested = db.begin_nested()
        try:
            db.execute(text(f'SET LOCAL ROLE "{role}"'))
            db.execute(text(f"SET {scope} sorento.audit_maintenance = 'on'"))
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement), {"i": row_id})
        finally:
            nested.rollback()
            db.execute(text("RESET sorento.audit_maintenance"))
        (row,) = db.execute(text("SELECT description FROM audit_logs WHERE id = :i"), {"i": row_id}).all()
        assert row.description is None

    def test_s1_a_maintainer_still_can(self, db):
        """A member of the maintenance role (here the superuser CI connects as) with the flag
        set is the one way through: the retention job and scrub migrations."""
        from sqlalchemy import text

        _role, row_id = self._as_app_role(db)
        db.execute(text("SET LOCAL sorento.audit_maintenance = 'on'"))
        db.execute(text("DELETE FROM audit_logs WHERE id = :i"), {"i": row_id})
        assert db.execute(text("SELECT count(*) FROM audit_logs WHERE id = :i"), {"i": row_id}).scalar() == 0


# --- S2: the migration does not block audited writes while it builds ------------------


class _Recorder:
    """Stands in for alembic's ``op``: records every SQL string and whether it ran inside
    ``autocommit_block()`` (outside the migration's transaction)."""

    def __init__(self):
        self.statements: list[tuple[str, bool]] = []
        self._autocommit = False
        outer = self

        class _Bind:
            def execute(self, clause, *a, **k):
                outer.statements.append((str(clause), outer._autocommit))

                class _R:
                    def scalar(self_inner):
                        return None

                return _R()

        class _Ctx:
            from contextlib import contextmanager

            @contextmanager
            def autocommit_block(self):
                outer._autocommit = True
                try:
                    yield
                finally:
                    outer._autocommit = False

        self._bind, self._ctx = _Bind(), _Ctx()

    def get_bind(self):
        return self._bind

    def get_context(self):
        return self._ctx

    def execute(self, sql, *a, **k):
        self.statements.append((str(sql), self._autocommit))

    def add_column(self, table, column, *a, **k):
        self.statements.append((f"ADD COLUMN {table}.{column.name}", self._autocommit))

    def create_index(self, name, table, cols, **kw):
        concurrently = " CONCURRENTLY" if kw.get("postgresql_concurrently") else ""
        self.statements.append((f"CREATE INDEX{concurrently} {name}", self._autocommit))


def _load_aud_0001():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "aud_0001_audit_standard_s0.py"
    spec = importlib.util.spec_from_file_location("m_aud_0001_round2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestS2MigrationLocks:
    def _record_upgrade(self):
        module = _load_aud_0001()
        rec = _Recorder()
        module.op = rec
        module.upgrade()
        return rec.statements

    def test_s2_every_index_is_built_concurrently_outside_the_transaction(self):
        statements = self._record_upgrade()
        indexes = [(sql, auto) for sql, auto in statements if "CREATE INDEX" in sql.upper()]
        assert len(indexes) == 3, indexes
        for sql, autocommit in indexes:
            assert "CONCURRENTLY" in sql.upper(), sql
            assert autocommit, f"CREATE INDEX CONCURRENTLY cannot run in a transaction: {sql}"

    def test_s2_the_check_is_added_not_valid_then_validated_on_its_own(self):
        statements = self._record_upgrade()
        adds = [(s, a) for s, a in statements if "ADD CONSTRAINT AUDIT_LOGS_ACTION_CHECK" in s.upper()]
        assert adds and all("NOT VALID" in s.upper() and not a for s, a in adds), adds
        validates = [(s, a) for s, a in statements if "VALIDATE CONSTRAINT AUDIT_LOGS_ACTION_CHECK" in s.upper()]
        # VALIDATE takes only SHARE UPDATE EXCLUSIVE, but inside the migration's transaction the
        # ADD's ACCESS EXCLUSIVE is still held; it must run after that transaction commits.
        assert len(validates) == 1 and validates[0][1], validates

    def test_s2_an_invalid_index_left_by_an_interrupted_build_is_rebuilt(self):
        """A failed CREATE INDEX CONCURRENTLY leaves an INVALID index that IF NOT EXISTS would
        keep forever; the upgrade drops and rebuilds it."""
        import os

        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        from app.database import engine

        module = _load_aud_0001()
        scratch = f"zzs_s2_{os.getpid()}_{uuid.uuid4().hex[:6]}"
        with engine.connect() as raw:
            outer = raw.begin()
            try:
                raw.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
                raw.exec_driver_sql(
                    f'CREATE TABLE "{scratch}".audit_logs ('
                    "id uuid PRIMARY KEY, entity_type varchar(100) NOT NULL, "
                    "entity_id varchar(100) NOT NULL, action varchar(20) NOT NULL, "
                    "changed_at timestamp NOT NULL DEFAULT now(), "
                    "CONSTRAINT audit_logs_action_check CHECK (action IN "
                    "('CREATE','READ','UPDATE','DELETE','IMPORT')))"
                )
                raw.exec_driver_sql(f'SET LOCAL search_path TO "{scratch}"')
                raw.exec_driver_sql(f'ALTER TABLE "{scratch}".audit_logs ADD COLUMN event varchar(100)')
                raw.exec_driver_sql(f'CREATE INDEX ix_audit_logs_event ON "{scratch}".audit_logs (event)')
                raw.exec_driver_sql(
                    "UPDATE pg_index SET indisvalid = false "
                    f"WHERE indexrelid = '\"{scratch}\".ix_audit_logs_event'::regclass"
                )
                ctx = MigrationContext.configure(raw.execution_options(schema_translate_map={None: scratch}))
                with Operations.context(ctx):
                    module._upgrade(concurrently=False)
                valid = raw.execute(
                    sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:n)"),
                    {"n": f'"{scratch}".ix_audit_logs_event'},
                ).scalar()
                assert valid is True
            finally:
                outer.rollback()
