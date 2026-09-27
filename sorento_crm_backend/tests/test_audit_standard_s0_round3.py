"""Audit standard S0 (#1281), fix lane round 3: the reviewer pass at cba2b754.

One class per finding (B3, S1-r2, N-a, N-b). Each test failed at cba2b754 for the reviewer's
failing scenario before its repair landed; the closing PR comment lists them. Everything runs
on the blank Postgres schema, rolled back.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.audit import (
    APPEND_ONLY_FUNCTION_SQL,
    ENSURE_MAINTAINER_ROLE_SQL,
    MAINTAINER_ROLE,
    AuditLog,
)
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


# --- S1-r2: a CREATEROLE app login cannot use the maintenance flag ----------------------


class TestS1CreateroleLogin:
    """The shipped DDL with the role name swapped for a scratch one (roles are cluster-wide,
    and the real one already exists on CI's cluster), on a scratch table in the blank schema.
    Everything, roles included, is rolled back with the test."""

    def _setup(self, db):
        tag = uuid.uuid4().hex[:10]
        maint, fn, table = f"s0r3_maint_{tag}", f"s0r3_append_only_{tag}", f"s0r3_probe_{tag}"
        schema = db.execute(text("SELECT current_schema()")).scalar()
        function_sql = (
            APPEND_ONLY_FUNCTION_SQL.format(schema="")
            .replace(MAINTAINER_ROLE, maint)
            .replace("audit_logs_append_only()", f"{fn}()")
        )
        db.execute(text(function_sql))
        db.execute(text(f'CREATE TABLE "{schema}".{table} (id int)'))
        db.execute(text(f'INSERT INTO "{schema}".{table} VALUES (1)'))
        db.execute(
            text(f'CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON "{schema}".{table} '
                 f"FOR EACH ROW EXECUTE FUNCTION {fn}()")
        )
        return schema, maint, table

    def _role(self, db, schema, table, name, *, createrole):
        attrs = "NOSUPERUSER NOLOGIN " + ("CREATEROLE" if createrole else "NOCREATEROLE")
        db.execute(text(f'CREATE ROLE "{name}" {attrs}'))
        db.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{name}"'))
        db.execute(text(f'GRANT SELECT, DELETE ON "{schema}".{table} TO "{name}"'))

    def _delete_with_flag(self, db, schema, table, *switch):
        nested = db.begin_nested()
        try:
            for statement in switch:
                db.execute(text(statement))
            db.execute(text("SET LOCAL sorento.audit_maintenance = 'on'"))
            db.execute(text(f'DELETE FROM "{schema}".{table}'))
            return True
        except DBAPIError as exc:
            assert "append-only" in str(exc)
            return False
        finally:
            nested.rollback()

    def test_s1r2_a_createrole_login_running_the_migration_does_not_become_a_maintainer(self, db):
        """Probe P1: the app login has CREATEROLE and runs the DDL itself. At cba2b754 it
        created the role, PG16 made it a member through the creator's implicit grant, and
        the flag let it DELETE."""
        schema, maint, table = self._setup(db)
        app_login = f"s0r3_app_{uuid.uuid4().hex[:10]}"
        self._role(db, schema, table, app_login, createrole=True)
        ensure = ENSURE_MAINTAINER_ROLE_SQL.replace(MAINTAINER_ROLE, maint)
        assert not self._delete_with_flag(db, schema, table, f'SET LOCAL ROLE "{app_login}"', ensure)

    def test_s1r2_only_a_superuser_creates_the_role(self, db):
        schema, maint, table = self._setup(db)
        app_login = f"s0r3_app_{uuid.uuid4().hex[:10]}"
        self._role(db, schema, table, app_login, createrole=True)
        nested = db.begin_nested()
        try:
            db.execute(text(f'SET LOCAL ROLE "{app_login}"'))
            db.execute(text(ENSURE_MAINTAINER_ROLE_SQL.replace(MAINTAINER_ROLE, maint)))
            created = db.execute(text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": maint}).scalar()
        finally:
            nested.rollback()
        assert created == 0
        # The superuser CI connects as does create it.
        db.execute(text(ENSURE_MAINTAINER_ROLE_SQL.replace(MAINTAINER_ROLE, maint)))
        assert db.execute(text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": maint}).scalar() == 1

    @pytest.mark.parametrize("via", ["set_role", "session_authorization_then_set_role"])
    def test_s1r2_a_createrole_login_that_is_a_member_is_refused(self, db, via):
        """Probe P2, the PG15 shape: a CREATEROLE login may grant itself any non-superuser
        role (here a superuser grants it, which is the same end state). Membership proves
        nothing for such a login, also after SET ROLE to the maintainer role itself."""
        schema, maint, table = self._setup(db)
        db.execute(text(f'CREATE ROLE "{maint}" NOLOGIN'))
        app_login = f"s0r3_app_{uuid.uuid4().hex[:10]}"
        self._role(db, schema, table, app_login, createrole=True)
        db.execute(text(f'GRANT "{maint}" TO "{app_login}"'))
        db.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{maint}"'))
        db.execute(text(f'GRANT SELECT, DELETE ON "{schema}".{table} TO "{maint}"'))
        if via == "set_role":
            switch = (f'SET LOCAL ROLE "{app_login}"',)
        else:
            switch = (f'SET LOCAL SESSION AUTHORIZATION "{app_login}"', f'SET LOCAL ROLE "{maint}"')
        assert not self._delete_with_flag(db, schema, table, *switch)

    def test_s1r2_a_plain_member_without_createrole_still_can(self, db):
        """The retention job's login: granted the role by a DBA, no CREATEROLE."""
        schema, maint, table = self._setup(db)
        db.execute(text(f'CREATE ROLE "{maint}" NOLOGIN'))
        job_login = f"s0r3_job_{uuid.uuid4().hex[:10]}"
        self._role(db, schema, table, job_login, createrole=False)
        db.execute(text(f'GRANT "{maint}" TO "{job_login}"'))
        assert self._delete_with_flag(db, schema, table, f'SET LOCAL ROLE "{job_login}"')


# --- B3: the volume gate. Sync and import paths, and line and link tables, are not default-on


def _brand(db):
    """An untracked class: audited only by default-on."""
    from app.models.product import Brand

    assert not getattr(Brand, "__audit_track__", False)
    brand = Brand(brand_code=unique_code("B")[:50], brand_name="Alpha")
    db.add(brand)
    db.flush()
    return brand


def _customer(db):
    """A class opted in before default-on (``__audit_track__``): audited on every path."""
    from app.models.order import Customer

    assert Customer.__dict__.get("__audit_track__") is True
    customer = Customer(customer_code=unique_code("C")[:50], customer_name="Alpha Trading")
    db.add(customer)
    db.flush()
    return customer


def _bulk_rename(db, brand):
    from app.models.product import Brand

    db.query(Brand).filter(Brand.id == brand.id).update({"brand_name": "Bulk"}, synchronize_session=False)


class TestB3SyncWriterContext:
    """One test per marked path: each fails when its mark is removed (the kill table in the
    closing comment), and each also proves a tracked class is still recorded there."""

    def _assert_default_on_is_off(self, db):
        brand = _brand(db)
        brand.brand_name = "Beta"
        db.flush()
        _bulk_rename(db, brand)
        customer = _customer(db)
        assert _rows(db, brand.id) == []
        assert [r.action for r in _rows(db, customer.id)] == ["CREATE"]

    def test_b3_an_imports_queue_job(self, db):
        from types import SimpleNamespace

        from app.services.queue_service import job_actor_scope

        job = SimpleNamespace(id="job-imports-1", origin="imports", meta={})
        with job_actor_scope(job):
            self._assert_default_on_is_off(db)

    def test_b3_the_autocount_esb_key(self, db):
        from app.audit_context import audit_context_scope, mark_integration_request

        with audit_context_scope():
            mark_integration_request("autocount_esb", "/api/v1/external/grn")
            self._assert_default_on_is_off(db)

    def test_b3_the_ingest_routes_whoever_calls_them(self, db):
        from app.audit_context import audit_context_scope, mark_integration_request

        with audit_context_scope():
            mark_integration_request("automation", "/api/v1/external/ingest/products")
            self._assert_default_on_is_off(db)

    def test_b3_a_scheduler_actor(self, db):
        """Every tick, heartbeat handler and Run now: all stamp a ``scheduler`` actor."""
        from app.audit_context import AuditActor, actor_scope

        with actor_scope(AuditActor(actor_type="scheduler", job_id="spo_container_relink_sweep"), db=db):
            self._assert_default_on_is_off(db)

    def test_b3_the_scheduler_session_helper(self):
        from app.audit_context import get_actor, sync_writer_for, current_audit_context
        from app.scheduler.task_scheduler import scheduler_session

        with scheduler_session("autocount_pull_advance") as session:
            assert sync_writer_for(get_actor(session), current_audit_context()) == "scheduler:autocount_pull_advance"

    def test_b3_an_explicit_sync_writer_scope(self, db):
        from app.audit_context import audit_context_scope, current_audit_context, sync_writer_scope

        with audit_context_scope():
            with sync_writer_scope("supplier_feed"):
                self._assert_default_on_is_off(db)
            assert current_audit_context().sync_writer is None

    def test_b3_explicit_rows_are_still_written_inside_a_sync(self, db):
        from app.audit_context import audit_context_scope, sync_writer_scope
        from app.services.audit_service import record

        eid = str(uuid.uuid4())
        with audit_context_scope(), sync_writer_scope("autocount_pull"):
            record(db, event="integration.autocount.pull", entity_type="import_job", entity_id=eid)
        assert [r.event for r in _rows(db, eid)] == ["integration.autocount.pull"]

    @pytest.mark.parametrize("path", ["staff", "other_worker_queue", "n8n_key"])
    def test_b3_staff_driven_writes_stay_default_on(self, db, path):
        from types import SimpleNamespace

        from app.audit_context import AuditActor, actor_scope, audit_context_scope, mark_integration_request
        from app.services.queue_service import job_actor_scope

        user_id = str(uuid.uuid4())
        if path == "staff":
            scope = actor_scope(AuditActor(actor_type="user", user_id=user_id, real_user_id=user_id), db=db)
        elif path == "other_worker_queue":
            scope = job_actor_scope(SimpleNamespace(id="job-2", origin="respond_io", meta={}))
        else:
            scope = audit_context_scope()
        with scope:
            if path == "n8n_key":
                mark_integration_request("automation", "/api/v1/external/customers")
            brand = _brand(db)
            _bulk_rename(db, brand)
        assert [r.action for r in _rows(db, brand.id)] == ["CREATE", "UPDATE"]


# The pure line, link and sync-mirror tables the measurement names (orchestrator's comment of
# 27 Sep 06:42 MYT), with the lower-bound rows a day (created_at / updated_at over 30 days).
MEASURED_LOWER_BOUND_PER_DAY = {
    "sales_order_lines": 47507.0,
    "integration_references": 13314.6,
    "sales_orders": 10828.7,
    "purchase_order_lines": 5223.5,
    "spo_allocations": 2601.7,
    "scm.order_link_claim": 907.4,
    "orders": 903.5,
    "order_lines": 698.9,
    "projects.sales_order_lines": 679.4,
    "purchase_orders": 553.0,
    "stock": 526.3,
    "products": 517.3,
    "product_specifications": 512.8,
    "projects.order_inquiry_rows": 450.9,
    "scm.reorder_level": 345.5,
    "picking_lines": 268.4,
    "product_suppliers": 264.4,
    "product_attachments": 259.1,
    "certificate_products": 256.1,
    "projects.order_inquiry_links": 230.3,
    "product_spec_flyer_proposals": 180.4,
    "conversation_ticket_comments": 116.3,
    "projects.planning_change_rows": 67.4,
    "scm.supplier_inventory": 56.0,
    "attachment_field_links": 55.1,
}
DEFAULT_ON_LOWER_BOUND_PER_DAY = 87788.3  # all 263 tables, section 3B
TRACKED_BEFORE_PER_DAY = 1601.8  # the 42 pre-S0 classes, section 3B
TODAY_PER_DAY = 480.3  # audit_logs, 30-day average, section 1

EXCLUDED_BY_MODEL = (
    "sales_order_lines", "integration_references", "sales_orders", "purchase_order_lines",
    "order_lines", "spo_allocations", "scm.order_link_claim", "projects.sales_order_lines",
    "stock", "product_specifications", "product_suppliers", "picking_lines",
    "product_attachments", "certificate_products", "attachment_field_links",
    "promotion_products", "projects.order_inquiry_rows", "projects.order_inquiry_links",
    "projects.planning_change_rows",
)


def _classes_by_table():
    from app.database import Base

    return {mapper.local_table.fullname: mapper.class_ for mapper in Base.registry.mappers}


def projected_rows_per_day() -> tuple[float, float]:
    """(ceiling, expected) audit rows a day under default-on with the exclusions in the code.

    Ceiling: every table still default-on writes an audit row for every row it created or
    updated, whoever wrote it (no credit for the sync writer context, which the measurement
    cannot split by writer). Expected: the same, with the tracked classes at today's actual
    volume instead of their raw write volume (they were audited before S0 and still are)."""
    classes = _classes_by_table()
    excluded = sum(
        rows for table, rows in MEASURED_LOWER_BOUND_PER_DAY.items()
        if not audit_service._is_audited_cls(classes[table])
    )
    ceiling = DEFAULT_ON_LOWER_BOUND_PER_DAY - excluded
    return ceiling, ceiling - TRACKED_BEFORE_PER_DAY + TODAY_PER_DAY


class TestB3ModelOptOut:
    @pytest.mark.parametrize("table", EXCLUDED_BY_MODEL)
    def test_b3_the_measured_table_is_not_default_on(self, table):
        cls = _classes_by_table()[table]
        reason = getattr(cls, "__audit_skip__", None)
        assert isinstance(reason, str) and "rows a day" in reason, table
        assert not audit_service._is_audited_cls(cls)
        # Opting out a class that was audited before S0 would shrink today's trail.
        assert not cls.__dict__.get("__audit_track__")

    def test_b3_a_skipped_sync_table_writes_nothing(self, db):
        from app.models.integration_reference import IntegrationReference

        ref = IntegrationReference(entity_type="brands", entity_id=str(uuid.uuid4()), source_ref=unique_code("DK"))
        db.add(ref)
        db.flush()
        ref.source_doc_no = "SO-2"
        db.flush()
        db.query(IntegrationReference).filter(IntegrationReference.id == ref.id).delete(synchronize_session=False)
        assert _rows(db, ref.id) == []

    def test_b3_the_projection_lands_within_a_few_times_today(self):
        ceiling, expected = projected_rows_per_day()
        print(f"projected audit rows a day: ceiling {ceiling:.0f} ({ceiling / TODAY_PER_DAY:.1f}x today), "
              f"expected {expected:.0f} ({expected / TODAY_PER_DAY:.1f}x today)")
        assert round(ceiling) == 3136 and round(expected) == 2015
        assert ceiling < 10 * TODAY_PER_DAY  # the plan's 10x gate


# --- N-a: a combo part belongs to its combo -------------------------------------------


class TestNaComboPart:
    def test_na_the_declared_owner_chain_wins_over_a_direct_hop(self):
        from app.models.product_combo import ProductComboPart

        chain = audit_service._company_chain(ProductComboPart)
        assert [(hop[0], hop[1].name) for hop in chain] == [
            ("combo_id", "product_combos"),
            ("host_product_id", "products"),
        ]
        assert audit_service._parent_of(ProductComboPart)[1] == "combo_id"


# --- N-b: the bulk summary of a chain class needs the whole match in one company -------


class TestNbChainSummary:
    def _fields(self, db, companies):
        from app.models.forms import Form, FormField, FormSection

        fields = []
        for company in companies:
            form = Form(code=unique_code("F")[:100], name="Probe form", company_id=company)
            db.add(form)
            db.flush()
            section = FormSection(form_id=form.id, section_name="S")
            db.add(section)
            db.flush()
            for n in range(2):
                field = FormField(section_id=section.id, field_name=f"f{n}", field_label="F", field_type="text")
                db.add(field)
                fields.append(field)
        db.flush()
        return fields

    def _bulk(self, db, fields, monkeypatch):
        from app.models.forms import FormField

        monkeypatch.setattr(audit_service, "BULK_AUDIT_CAP", 1)
        db.expire_all()
        db.query(FormField).filter(FormField.id.in_([f.id for f in fields])).update(
            {"field_label": "bulk"}, synchronize_session=False
        )
        (summary,) = _rows(db, "*", "UPDATE")
        return summary

    def test_nb_mixed_companies_through_a_chain_keep_the_summary_company_less(self, db, monkeypatch):
        fields = self._fields(db, [str(uuid.uuid4()), str(uuid.uuid4())])
        assert self._bulk(db, fields, monkeypatch).company_id is None

    def test_nb_one_company_through_a_chain_keeps_it(self, db, monkeypatch):
        company = str(uuid.uuid4())
        fields = self._fields(db, [company])
        assert str(self._bulk(db, fields, monkeypatch).company_id) == company
