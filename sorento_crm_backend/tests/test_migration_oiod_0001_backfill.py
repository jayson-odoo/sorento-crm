"""OI-ONE-DELIVERY-DATE: `oiod_0001_backfill` (AC-C3, AC-C4, AC-C5, AC-A10, AC-A12).

TEST-FIRST: the migration file does not exist yet, so a red is the file missing.

Contract (PLAN section 5): revision `oiod_0001_backfill` on main's alembic head;
it creates `projects.oi_delivery_date_backfill(row_id, old_delivery_date,
old_previous_delivery_date)`. Upgrade: for every `order_inquiry_rows` row not cancelled whose
SO line date (core `required_date`, else mirror `delivery_date`) is NOT NULL and differs
from its `delivery_date`, log it, set `previous_delivery_date` = the old `delivery_date` and
`delivery_date` = the SO line date. Everything else is untouched. Downgrade restores exactly
from the log and drops the table.

Runs on the real `projects` schema inside a rolled-back transaction (`pg_session`): the
migration addresses `projects.*` by name, which the blank scratch schema does not translate
for raw SQL. Every row is seeded here and every assertion is scoped to those rows.
"""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.base import company_scope
from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

from ._oi_one_date_seed import NO_CORE, Chain
from ._pg_fixture import pg_session

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "oiod_0001_backfill.py"
)
LOG = "projects.oi_delivery_date_backfill"

OLD = date(2026, 7, 1)
NEW = date(2027, 1, 7)
FAR = date(2030, 1, 1)
PRIOR = date(2026, 5, 5)


def _load():
    assert MIGRATION.exists(), f"{MIGRATION.name} does not exist yet"
    spec = importlib.util.spec_from_file_location("oiod_0001_backfill", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str) -> None:
    db.flush()
    module = _load()
    with Operations.context(MigrationContext.configure(db.connection())):
        getattr(module, direction)()
    db.expire_all()


def _row(db, row_id):
    return db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()


def _logged(db, row_ids):
    out = db.execute(
        text(
            f"SELECT row_id, old_delivery_date, old_previous_delivery_date FROM {LOG} "
            "WHERE row_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": list(row_ids)},
    ).all()
    return {str(r[0]): (r[1], r[2]) for r in out}


@pytest.fixture()
def seeded():
    with pg_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            rows = {}

            _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["differs"] = chain.add_row(line, told=OLD)
            rows["differs_with_previous"] = chain.add_row(line, told=OLD, previous=PRIOR)
            rows["cancelled"] = chain.add_row(line, told=OLD, state=INQUIRY_CANCELLED)

            _c, same = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["matches"] = chain.add_row(same, told=NEW)
            rows["matches_with_previous"] = chain.add_row(same, told=NEW, previous=PRIOR)

            rows["no_line"] = chain.add_row(None, told=OLD)

            _c, undated = chain.add_line(core_date=None, mirror_date=None)
            rows["line_without_date"] = chain.add_row(undated, told=OLD)

            # AC-A12: the mirror lags the core line, the core date wins.
            _c, lag = chain.add_line(core_date=FAR, mirror_date=date(2026, 6, 1))
            rows["mirror_lags_core"] = chain.add_row(lag, told=date(2026, 6, 1))

            # No core line linked: the mirror's date is the SO line date.
            _c, mirror_only = chain.add_line(core_date=NO_CORE, mirror_date=date(2027, 3, 3))
            rows["mirror_only"] = chain.add_row(mirror_only, told=OLD)

            # AC-C5: SO369829 L27 shape, three rows at different dates on one line.
            line_date = date(2027, 12, 30)
            _c, shared = chain.add_line(core_date=line_date, mirror_date=line_date)
            told = [date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]
            for index, when in enumerate(told):
                rows[f"shared_{index}"] = chain.add_row(shared, told=when, qty="5")
            db.flush()
            yield db, {k: v.id for k, v in rows.items()}, told


def test_upgrade_moves_only_the_rows_that_differ(seeded):
    """AC-C3."""
    db, ids, _told = seeded
    _run(db, "upgrade")

    differs = _row(db, ids["differs"])
    assert (differs.delivery_date, differs.previous_delivery_date) == (NEW, OLD)
    with_previous = _row(db, ids["differs_with_previous"])
    assert (with_previous.delivery_date, with_previous.previous_delivery_date) == (NEW, OLD)

    for key, told, previous in (
        ("matches", NEW, None),
        ("matches_with_previous", NEW, PRIOR),
        ("no_line", OLD, None),
        ("line_without_date", OLD, None),
        ("cancelled", OLD, None),
    ):
        row = _row(db, ids[key])
        assert (row.delivery_date, row.previous_delivery_date) == (told, previous), key


def test_upgrade_core_date_wins_mirror_is_the_fallback_and_2030_is_kept(seeded):
    """AC-A10, AC-A12."""
    db, ids, _told = seeded
    _run(db, "upgrade")

    lag = _row(db, ids["mirror_lags_core"])
    assert lag.delivery_date == FAR, "no TBA special case"
    assert lag.previous_delivery_date == date(2026, 6, 1)
    mirror_only = _row(db, ids["mirror_only"])
    assert mirror_only.delivery_date == date(2027, 3, 3)
    assert mirror_only.previous_delivery_date == OLD


def test_upgrade_several_rows_on_one_line_each_get_the_line_date_and_their_own_was(seeded):
    """AC-C5."""
    db, ids, told = seeded
    _run(db, "upgrade")

    for index, was in enumerate(told):
        row = _row(db, ids[f"shared_{index}"])
        assert row.delivery_date == date(2027, 12, 30)
        assert row.previous_delivery_date == was


def test_upgrade_logs_exactly_the_changed_rows_and_nothing_else(seeded):
    """AC-C4: each changed row is recorded (id, old told date, old previous date)."""
    db, ids, _told = seeded
    _run(db, "upgrade")

    logged = _logged(db, ids.values())
    changed = {
        ids[k]
        for k in (
            "differs", "differs_with_previous", "mirror_lags_core", "mirror_only",
            "shared_0", "shared_1", "shared_2",
        )
    }
    assert set(logged) == changed
    assert logged[ids["differs"]] == (OLD, None)
    assert logged[ids["differs_with_previous"]] == (OLD, PRIOR)


def test_upgrade_writes_no_audit_or_planning_change_rows(seeded):
    """AC-C4: no planning change, ack change or audit row of its own."""
    db, ids, _told = seeded
    _load()  # the file must exist before anything below can mean anything
    before = db.execute(text("select count(*) from audit_logs")).scalar()
    batches = db.execute(text("select count(*) from projects.planning_change_batches")).scalar()

    _run(db, "upgrade")

    assert db.execute(text("select count(*) from audit_logs")).scalar() == before
    assert db.execute(text("select count(*) from projects.planning_change_batches")).scalar() == batches
    for key in ("differs", "shared_0"):
        assert _row(db, ids[key]).changed_at is None
        assert _row(db, ids[key]).ack_state == "awaiting"


def test_downgrade_restores_every_row_exactly_and_drops_the_log(seeded):
    """AC-C4."""
    db, ids, told = seeded
    _run(db, "upgrade")
    _run(db, "downgrade")

    expected = {
        "differs": (OLD, None),
        "differs_with_previous": (OLD, PRIOR),
        "cancelled": (OLD, None),
        "matches": (NEW, None),
        "matches_with_previous": (NEW, PRIOR),
        "no_line": (OLD, None),
        "line_without_date": (OLD, None),
        "mirror_lags_core": (date(2026, 6, 1), None),
        "mirror_only": (OLD, None),
        "shared_0": (told[0], None),
        "shared_1": (told[1], None),
        "shared_2": (told[2], None),
    }
    for key, pair in expected.items():
        row = _row(db, ids[key])
        assert (row.delivery_date, row.previous_delivery_date) == pair, key
    assert db.execute(text(f"select to_regclass('{LOG}')")).scalar() is None
