"""OI-DATE-WAS-FIX: `oiod_0002_pending_restore` (UAC 1 to 3,
`documentation/plans/scm/oi-date-was-fix-04nov-acceptance-criteria.md`).

oiod_0001 moved the told date of rows whose SO line move was still pending CS Confirm, so
that Confirm saw no move and sent no DELAY / ADVANCE email. oiod_0002 puts exactly those rows
back on the date purchasing was last told, logs each one, and the downgrade reverses it.

Runs on the real `projects` schema inside a rolled-back transaction (`pg_session`), the same
way `test_migration_oiod_0001_backfill.py` does: oiod_0001's upgrade runs first inside the
transaction so its log holds the seeded rows, then oiod_0002 runs. Every assertion is scoped
to the seeded rows.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.base import company_scope
from app.models.planning_change import (
    PLANNING_CHANGE_KIND_ADVANCED,
    PLANNING_CHANGE_KIND_DELAYED,
    PLANNING_CHANGE_KIND_QTY_UP,
    PLANNING_CHANGE_STATE_APPLIED,
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.project_so import INQUIRY_CANCELLED, IV_DELAY, OrderInquiryRow

from ._oi_one_date_seed import Chain, uid
from ._pg_fixture import pg_session

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
BACKFILL = VERSIONS / "oiod_0001_backfill.py"
RESTORE = VERSIONS / "oiod_0002_pending_restore.py"
LOG = "projects.oi_delivery_date_pending_restore"

OLD = date(2026, 7, 1)  # the date purchasing was last told
NEW = date(2026, 9, 15)  # the SO line date AutoCount moved to (later: a DELAY)
EARLY = date(2026, 6, 1)  # an earlier SO line date (an ADVANCE)
LATER = date(2026, 10, 30)
PRIOR = date(2026, 5, 5)


def _load(path: Path):
    assert path.exists(), f"{path.name} does not exist yet"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, path: Path, direction: str) -> None:
    db.flush()
    module = _load(path)
    with Operations.context(MigrationContext.configure(db.connection())):
        getattr(module, direction)()
    db.expire_all()


def _row(db, row_id):
    return db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()


def _pair(db, row_id):
    row = _row(db, row_id)
    return row.delivery_date, row.previous_delivery_date


def _logged(db, row_ids):
    out = db.execute(
        text(
            f"SELECT row_id, from_delivery_date, from_previous_delivery_date FROM {LOG} "
            "WHERE row_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": list(row_ids)},
    ).all()
    return {str(r[0]): (r[1], r[2]) for r in out}


def _change(
    db, chain, batch, line, kind, state=PLANNING_CHANGE_STATE_PENDING, *, moves=None
):
    """`moves=(from, to)` writes the from/to required_date the way `build_batch` does
    (ISO strings); None writes the from/to of a change that names no date."""
    from_date, to_date = moves if moves else (None, None)
    db.add(
        PlanningChangeRow(
            id=uid(),
            company_id=chain.company_id,
            batch_id=batch.id,
            project_sales_order_id=chain.pso.id,
            project_line_id=line.id,
            kind=kind,
            from_json={"required_date": from_date.isoformat() if from_date else None},
            to_json={"required_date": to_date.isoformat() if to_date else None},
            facts_json={},
            applied_state=state,
        )
    )
    db.flush()


@pytest.fixture()
def seeded():
    with pg_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            batch = PlanningChangeBatch(id=uid(), company_id=company_id)
            db.add(batch)
            db.flush()
            rows = {}

            # Moved later, the DELAY still waits for CS Confirm: swallowed.
            _c, delayed = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["delayed"] = chain.add_row(delayed, told=OLD)
            rows["delayed_with_previous"] = chain.add_row(delayed, told=OLD, previous=PRIOR)
            _change(db, chain, batch, delayed, PLANNING_CHANGE_KIND_DELAYED, moves=(OLD, NEW))
            # An old DELAY notice row on the same line: a Confirm never stamps it, leave it.
            rows["notice_verb"] = chain.add_row(delayed, told=OLD)
            rows["notice_verb"].verb = IV_DELAY

            # Moved earlier, the ADVANCE still pending: swallowed.
            _c, advanced = chain.add_line(core_date=EARLY, mirror_date=EARLY)
            rows["advanced"] = chain.add_row(advanced, told=OLD)
            _change(db, chain, batch, advanced, PLANNING_CHANGE_KIND_ADVANCED, moves=(OLD, EARLY))
            # A superseded row beside the pending one changes nothing.
            _change(
                db, chain, batch, advanced, PLANNING_CHANGE_KIND_ADVANCED,
                state=PLANNING_CHANGE_STATE_SUPERSEDED, moves=(OLD, EARLY),
            )

            # A DELAY then a qty-only upload before Confirm: the pending row is `qty_up`
            # but carries the original from date forward, so it still moves the date.
            _c, chained = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["qty_up_with_date_move"] = chain.add_row(chained, told=OLD)
            _change(
                db, chain, batch, chained, PLANNING_CHANGE_KIND_DELAYED,
                state=PLANNING_CHANGE_STATE_SUPERSEDED, moves=(OLD, NEW),
            )
            _change(db, chain, batch, chained, PLANNING_CHANGE_KIND_QTY_UP, moves=(OLD, NEW))

            # Moved, but its change was already applied: purchasing was told, leave it.
            _c, applied = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["applied"] = chain.add_row(applied, told=OLD)
            applied_batch = PlanningChangeBatch(
                id=uid(), company_id=company_id, applied_at=datetime(2026, 11, 4, 9, 0)
            )
            db.add(applied_batch)
            db.flush()
            _change(
                db, chain, applied_batch, applied, PLANNING_CHANGE_KIND_DELAYED,
                state=PLANNING_CHANGE_STATE_APPLIED, moves=(OLD, NEW),
            )

            # Moved, the pending change is a quantity change that names no date move.
            _c, qty_only = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["qty_change"] = chain.add_row(qty_only, told=OLD)
            # `build_batch` writes both dates on every row; a qty-only change has from == to.
            _change(db, chain, batch, qty_only, PLANNING_CHANGE_KIND_QTY_UP, moves=(NEW, NEW))

            # Pending DELAY, but the buy row was redirected to the pool: Confirm never
            # stamps it, so leave it.
            _c, pooled = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["redirected"] = chain.add_row(pooled, told=OLD, redirected_to_pool=True)
            _change(db, chain, batch, pooled, PLANNING_CHANGE_KIND_DELAYED, moves=(OLD, NEW))

            # Statement 3 negatives, both in the applied batch: a SUPERSEDED date move, and
            # an applied move to a date the row does not carry.
            _c, superseded = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["superseded_in_applied"] = chain.add_row(superseded, told=OLD)
            _change(
                db, chain, applied_batch, superseded, PLANNING_CHANGE_KIND_DELAYED,
                state=PLANNING_CHANGE_STATE_SUPERSEDED, moves=(OLD, NEW),
            )
            _c, elsewhere = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["applied_elsewhere"] = chain.add_row(elsewhere, told=OLD)
            _change(
                db, chain, applied_batch, elsewhere, PLANNING_CHANGE_KIND_DELAYED,
                state=PLANNING_CHANGE_STATE_APPLIED, moves=(OLD, LATER),
            )

            # Moved, no planning change at all.
            _c, quiet = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["no_change"] = chain.add_row(quiet, told=OLD)

            # Pending DELAY, but the backfill never touched it (already on the line date).
            _c, matched = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["not_backfilled"] = chain.add_row(matched, told=NEW)
            _change(db, chain, batch, matched, PLANNING_CHANGE_KIND_DELAYED, moves=(OLD, NEW))

            # Pending DELAY, backfilled, then confirmed onward before this ran.
            _c, moved_on = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["moved_since"] = chain.add_row(moved_on, told=OLD)
            _change(db, chain, batch, moved_on, PLANNING_CHANGE_KIND_DELAYED, moves=(OLD, NEW))

            # Pending DELAY, backfilled, then cancelled before this ran.
            _c, gone = chain.add_line(core_date=NEW, mirror_date=NEW)
            rows["cancelled_since"] = chain.add_row(gone, told=OLD)
            _change(db, chain, batch, gone, PLANNING_CHANGE_KIND_DELAYED, moves=(OLD, NEW))
            db.flush()

            ids = {k: v.id for k, v in rows.items()}
            _run(db, BACKFILL, "upgrade")
            # What happened between the 4 Nov deploy and this migration.
            moved = _row(db, ids["moved_since"])
            moved.previous_delivery_date, moved.delivery_date = NEW, LATER
            _row(db, ids["cancelled_since"]).state = INQUIRY_CANCELLED
            db.flush()
            yield db, ids


def test_backfill_left_the_swallowed_rows_on_the_new_date(seeded):
    """The shape this lane repairs, as oiod_0001 left it."""
    db, ids = seeded
    assert _pair(db, ids["delayed"]) == (NEW, OLD)
    assert _pair(db, ids["advanced"]) == (EARLY, OLD)


def test_upgrade_puts_pending_delayed_and_advanced_rows_back_on_the_told_date(seeded):
    """UAC 1: the told date and Was are back exactly as before oiod_0001."""
    db, ids = seeded
    _run(db, RESTORE, "upgrade")

    assert _pair(db, ids["delayed"]) == (OLD, None)
    assert _pair(db, ids["delayed_with_previous"]) == (OLD, PRIOR)
    assert _pair(db, ids["advanced"]) == (OLD, None)
    assert _pair(db, ids["qty_up_with_date_move"]) == (OLD, None)


def test_upgrade_leaves_every_other_row_alone(seeded):
    """UAC 3."""
    db, ids = seeded
    _run(db, RESTORE, "upgrade")

    for key, pair in (
        ("applied", (NEW, OLD)),
        ("qty_change", (NEW, OLD)),
        ("no_change", (NEW, OLD)),
        ("not_backfilled", (NEW, None)),
        ("moved_since", (LATER, NEW)),
        ("cancelled_since", (NEW, OLD)),
        ("notice_verb", (NEW, OLD)),
        ("redirected", (NEW, OLD)),
        ("superseded_in_applied", (NEW, OLD)),
        ("applied_elsewhere", (NEW, OLD)),
    ):
        assert _pair(db, ids[key]) == pair, key


def test_upgrade_logs_exactly_the_restored_rows(seeded):
    """UAC 2: each restored row's pre-restore date and Was are logged, nothing else."""
    db, ids = seeded
    _run(db, RESTORE, "upgrade")

    logged = _logged(db, ids.values())
    assert set(logged) == {
        ids["delayed"], ids["delayed_with_previous"], ids["advanced"],
        ids["qty_up_with_date_move"],
    }
    assert logged[ids["delayed"]] == (NEW, OLD)
    assert logged[ids["advanced"]] == (EARLY, OLD)


def test_upgrade_twice_changes_nothing_more(seeded):
    db, ids = seeded
    _run(db, RESTORE, "upgrade")
    first = {key: _pair(db, row_id) for key, row_id in ids.items()}
    _run(db, RESTORE, "upgrade")

    assert {key: _pair(db, row_id) for key, row_id in ids.items()} == first
    assert _logged(db, ids.values())[ids["delayed"]] == (NEW, OLD)


def test_upgrade_writes_no_audit_planning_change_or_ack_change(seeded):
    """UAC 3: no email at migration time, nothing that would trigger one."""
    db, ids = seeded
    audits = db.execute(text("select count(*) from audit_logs")).scalar()
    changes = db.execute(text("select count(*) from projects.planning_change_rows")).scalar()

    _run(db, RESTORE, "upgrade")

    assert db.execute(text("select count(*) from audit_logs")).scalar() == audits
    assert db.execute(text("select count(*) from projects.planning_change_rows")).scalar() == changes
    row = _row(db, ids["delayed"])
    assert row.changed_at is None
    assert row.ack_state == "awaiting"


def test_downgrade_puts_the_backfilled_dates_back_and_drops_the_log(seeded):
    db, ids = seeded
    before = {key: _pair(db, row_id) for key, row_id in ids.items()}
    _run(db, RESTORE, "upgrade")
    _run(db, RESTORE, "downgrade")

    assert {key: _pair(db, row_id) for key, row_id in ids.items()} == before
    assert db.execute(text(f"select to_regclass('{LOG}')")).scalar() is None


def test_downgrade_keeps_a_confirm_made_after_the_upgrade(seeded):
    """A row Confirmed onward after the restore is real news; the downgrade leaves it."""
    db, ids = seeded
    _run(db, RESTORE, "upgrade")
    row = _row(db, ids["delayed"])
    row.previous_delivery_date, row.delivery_date = OLD, LATER
    db.flush()
    _run(db, RESTORE, "downgrade")

    assert _pair(db, ids["delayed"]) == (LATER, OLD)
    assert _pair(db, ids["advanced"]) == (EARLY, OLD)


OWNER_SQL = (
    Path(__file__).resolve().parents[2]
    / "documentation" / "plans" / "scm" / "SQL-oi-date-was-fix-count-04nov.sql"
)


def _owner_statements():
    body = "\n".join(
        line for line in OWNER_SQL.read_text().splitlines() if not line.lstrip().startswith("--")
    )
    statements = [s.strip() for s in body.split(";") if s.strip()]
    assert len(statements) == 3, statements
    for statement in statements:
        assert statement.upper().startswith("SELECT"), "read-only: SELECT only"
    return statements


def test_owner_count_query_selects_exactly_what_the_migration_restores(seeded):
    """The read-only DBeaver query lists the same rows the upgrade restores, with the facts
    the owner asked for (OI no, SO no, line, product, old told date, line date, kind)."""
    db, ids = seeded
    count_sql, list_sql, _confirmed_sql = _owner_statements()
    product = _row(db, ids["delayed"]).item_code

    def ours():
        return [r for r in db.execute(text(list_sql)).mappings() if r["product_code"] == product]

    listed = ours()
    assert sorted(r["pending_change_kind"] for r in listed) == [
        "advanced", "delayed", "delayed", "qty_up",
    ]
    for r in listed:
        assert r["old_told_date"] == OLD
        assert r["so_line_date_now"] == r["told_date_now"]
        assert r["oi_no"] and r["so_no"] and r["so_line_no"]

    before = db.execute(text(count_sql)).mappings().one()["affected_rows"]
    _run(db, RESTORE, "upgrade")
    after = db.execute(text(count_sql)).mappings().one()["affected_rows"]
    assert before - after == len(listed) == 4
    assert ours() == []


def test_owner_query_lists_moves_already_confirmed_without_an_email(seeded):
    """Statement 3: the applied date move since 4 Nov whose row still holds the backfilled
    dates, for the owner's resend decision. The migration does not touch it."""
    db, ids = seeded
    _c, _l, confirmed_sql = _owner_statements()
    product = _row(db, ids["delayed"]).item_code

    listed = [
        r for r in db.execute(text(confirmed_sql)).mappings() if r["product_code"] == product
    ]
    assert [(r["old_told_date"], r["confirmed_date"], r["change_kind"]) for r in listed] == [
        (OLD, NEW, "delayed")
    ]
