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
