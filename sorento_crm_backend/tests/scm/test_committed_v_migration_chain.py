"""The committed_v migration chain must replay from history, not from today's code.

Production's first replay of the SCM chain died at migration 340: it imported the LIVE
`COMMITTED_V_SQL`, which by then carried the S13b `demand_origin` clause, referencing a
column only migration 346 adds. Dev never saw it because dev had already passed 340 with
the old body. Two invariants pin the fix:

1. REPLAY: on a schema shaped like the world at 339 (no `demand_origin` column), 340's
   `upgrade()` must succeed, and 346's must succeed after it - the exact sequence that
   failed in production.
2. DRIFT GUARD: the newest view-freezing migration's body must equal the live
   `COMMITTED_V_SQL`. When someone edits the live SQL, this goes red and the fix is a NEW
   migration freezing the new body - never editing an old migration, never importing live
   code from one.
"""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.services.scm.demand import COMMITTED_V_SQL
from tests._migration_imports import app_imports
from tests._pg_fixture import blank_session
from tests.scm.conftest import requires_pg

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _normalize(sql: str) -> str:
    return " ".join(
        line.strip()
        for line in sql.strip().splitlines()
        if line.strip() and not line.strip().startswith("--")
    )


@requires_pg
def test_migration_bodies_are_frozen_not_imported():
    """No migration may import the live application code - that import IS the outage.

    Wider than the view chain the file is named for: `374_uom_decimal_places` adds
    `units_of_measure.decimal_places` and BACKFILLS it, and it originally called
    `app.services.uom_decimal_places.backfill_uom_decimal_places` - the same shape as the
    340/346 failure, with the same replay hazard. Its name lists and observed-scale SQL are
    frozen in the migration now, and the service keeps the live copy for admin re-runs.

    The list is the union of both SCM lanes: Stage 1C's `374_so_supply_decisions` and
    Stage 2's `374_uom_decimal_places` / `376_scm_channel_read_model`. Two different
    revisions numbered 374 is not a typo - they are siblings off `373_merge_scm_stage0_1a`.
    """
    for name in (
        "340_scm_committed_reads_the_decision",
        "346_scm_demand_origin_split",
        "374_so_supply_decisions",
        "374_uom_decimal_places",
        "376_scm_channel_read_model",
        "384_committed_v_line_decision",
    ):
        imported = app_imports(_VERSIONS / f"{name}.py")
        assert imported == [], (
            f"{name} imports live application code ({', '.join(imported)}); freeze the "
            "SQL in the migration instead - a migration describes a point in history."
        )


@requires_pg
def test_newest_view_migration_matches_the_live_body():
    """Edit COMMITTED_V_SQL -> this goes red -> write a NEW migration with the new body.

    The newest one is `422_committed_v_link_netting` (the confirmed leg nets a row's
    UNLINKED remainder instead of testing its state), which replaces the body
    `384_committed_v_line_decision` installed. Every superseded freeze stays exactly as it
    shipped, which is the whole point of the guard, so 384's, 376's and 374's are checked
    below rather than updated here.
    """
    m422 = _load("422_committed_v_link_netting")
    assert _normalize(m422._AS_OF_422) == _normalize(COMMITTED_V_SQL), (
        "app.services.scm.demand.COMMITTED_V_SQL changed. Do not edit migration 422; "
        "add a new migration that freezes the new body (422's pattern), so a from-zero "
        "replay stays true to history."
    )


@requires_pg
def test_376_still_freezes_the_body_it_shipped_with():
    """The channel split's body is history now, and history does not move.

    Pinned by its distinguishing feature in both directions: 376 excludes a whole ORDER
    the moment any decision exists, which is exactly what 384 replaces, and it must not
    quietly acquire the line-level rule.
    """
    m376 = _load("376_scm_channel_read_model")
    assert "dd.sales_order_id = so.id" in m376._AS_OF_376
    assert "core_line_id" not in m376._AS_OF_376


@requires_pg
def test_346_still_freezes_the_body_it_shipped_with():
    """A superseded freeze is history and must stay verbatim.

    346's body is what a database at that revision holds; editing it to match today's rule
    would change the replay without changing any existing database, which is the same
    mistake in the other direction from importing live code.
    """
    m346 = _load("346_scm_demand_origin_split")
    assert "demand_origin = 'scm_order_inquiry'" in m346._AS_OF_346
    assert "project_committed" not in m346._AS_OF_346


@requires_pg
def test_every_downgrade_copy_matches_the_revision_it_restores():
    """A downgrade restores the body of the revision BELOW it, copied verbatim.

    Each view migration keeps its own frozen copy of the body it replaced, so the copies
    have to be pinned equal to the originals or a downgrade quietly installs a body nobody
    wrote. Three links in the chain now: 374 restores 346, 376 restores 374 (`depends_on`
    puts 374 directly beneath it, so 346 would be a step too far back), and 384 restores
    376 for the same reason.
    """
    m346 = _load("346_scm_demand_origin_split")
    m374 = _load("374_so_supply_decisions")
    m376 = _load("376_scm_channel_read_model")
    m384 = _load("384_committed_v_line_decision")
    m422 = _load("422_committed_v_link_netting")

    assert _normalize(m374._AS_OF_346) == _normalize(m346._AS_OF_346)
    assert _normalize(m376._AS_OF_374) == _normalize(m374._AS_OF_374)
    assert _normalize(m384._AS_OF_376) == _normalize(m376._AS_OF_376)
    assert _normalize(m422._AS_OF_384) == _normalize(m384._AS_OF_384)


@requires_pg
def test_384_installs_the_line_rule_and_its_downgrade_puts_376_back():
    """Both directions, against a real database, inside a rolled-back transaction.

    A downgrade that leaves the newer body in place is worse than one that fails: the
    database would then be stamped at 376 while answering 384's question.
    """
    with blank_session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        db.execute(text("DROP VIEW IF EXISTS scm.committed_v CASCADE"))

        m376 = _load("376_scm_channel_read_model")
        m384 = _load("384_committed_v_line_decision")
        db.execute(text(m376._AS_OF_376))

        conn = db.connection()
        ops = Operations(MigrationContext.configure(conn))
        import alembic.op as op_module

        op_module._proxy = ops
        m384.upgrade()
        definition = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert definition and "core_line_id" in definition

        m384.downgrade()
        restored = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert restored and "core_line_id" not in restored
        assert "dd.sales_order_id = so.id" in restored


@requires_pg
def test_replaying_340_then_346_on_a_339_shaped_schema():
    """The exact production failure path: 340 before demand_origin exists, then 346."""
    with blank_session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        # blank_session built today's model schema; put it back to the world as
        # migration 339 left it: the column 346 adds must not exist yet.
        db.execute(text("ALTER TABLE sales_orders DROP COLUMN IF EXISTS demand_origin"))
        # `scm` is schema-qualified in the view DDL, so the replay lands on the REAL view
        # (inside this rolled-back transaction). It has since grown the channel columns,
        # and Postgres refuses a CREATE OR REPLACE that DROPS columns - so the world 339
        # left needs the view genuinely absent, not merely out of date.
        db.execute(text("DROP VIEW IF EXISTS scm.committed_v CASCADE"))

        conn = db.connection()
        ops = Operations(MigrationContext.configure(conn))
        import alembic.op as op_module

        op_module._proxy = ops
        _load("340_scm_committed_reads_the_decision").upgrade()

        # 346 adds demand_origin itself, then re-emits the view with the S13b clause.
        _load("346_scm_demand_origin_split").upgrade()

        definition = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert definition and "demand_origin" in definition
