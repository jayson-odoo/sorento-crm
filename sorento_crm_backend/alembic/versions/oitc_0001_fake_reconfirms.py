"""Remove the fake "Reconfirmed" raise rows the 20 Sep 2026 OI sheet import left behind,
and move that import's +8 h shifted stamps back to the real instant
(`documentation/plans/scm/PLAN-oi-trail-cleanup-27oct.md`, lane OI-TRAIL-CLEANUP; owner
approved deleting exactly these rows, 27 Oct 2026).

How the rows came to exist, in order:

1. The sheet import of 20 Sep 2026 (`project_order_inquiry_import_service.py` at baad8defc7,
   `now = _now()`) stamped every header it created (`raised_at`, since corrected by 523
   itself, below) and every row it raised
   (`acknowledged_at`, and `actioned_at` / `changed_at` where it closed or settled one) with
   a Malaysia wall clock stored as if it were naive UTC: eight hours ahead of the row's own
   `created_at` (server `now()`, real UTC).
2. `523_oi_monthly_no_raises.backfill_raises` then read the header's shifted `raised_at` as
   "re-stamped more than a minute after its first row" and wrote a `reconfirmed` raise row in
   the uploader's name AT that shifted stamp, blanking the `raised` row's `raised_by` because
   it believed the header's name was the last reconfirmer's. It also moved the header's
   `raised_at` back to that first row's `created_at`. The decision trail
   (`decision_trail_service._raise_entries`, "later events" pass) shows it as a reconfirm.

Identified by provenance, never by a timestamp list. A `reconfirmed` row is fake when, on
the same inquiry, a row the sheet migrated (note starts with the sheet stamp, the same test
the trail itself uses) carries exactly that `acknowledged_at` - microsecond for microsecond -
from exactly that `acknowledged_by`, about eight hours after the row's own `created_at`. The
import's `now` was ONE Python value shared by the header and every row of that upload; a
genuine reconfirm is stamped by `_record_raise`'s own `datetime.utcnow()` and cannot land on
it. Each such `(stamp, uploader)` pair names one affected upload; every `reconfirmed` row at
that pair is then fake, including one whose inquiry's rows have since been re-acknowledged.

An upload that created no header left no fake reconfirm to anchor on, yet its rows carry the
same +8 h stamp (2 rows at a third stamp on the 20 Oct copy; crew ruling 27 Oct: same root
cause, fix them too). Its stamp is read off its own `import_jobs` row instead: a sheet row
acknowledged by the uploader, ~8 h after its birth, where the stamp minus 8 h and the row's
birth both fall inside that uploader's `order_inquiry_import` job (`created_at` to
`completed_at`, both real UTC, `job_service.py`). It shifts timestamps only; with no
reconfirm at that stamp there is nothing to delete.

Steps, one transaction: shift every `order_inquiry_rows.acknowledged_at` / `actioned_at` /
`changed_at` equal to an affected stamp back eight hours (that includes rows born later that
carried the acknowledgement forward with its stamp, e.g. a split or a revision:
`project_order_inquiry_service.py:7364`); give the `raised` row back the uploader's name
where 523 blanked it only because of the fake reconfirm; delete the fake `reconfirmed` rows.
The header's own `raised_at` needs no step: 523 already moved it to its earliest row's
`created_at`, the real instant (measured on the 20 Oct prod copy: all 699 headers).

Idempotent by construction: the stamps are read off the fake rows this same revision deletes
and off rows it moves out of the ~8 h window, so a second run finds none and touches
nothing. Exposed as module-level functions (precedent: `523_oi_monthly_no_raises.py`) so a
test drives the same code on a scratch schema.

Nothing re-creates them: 523 is a past revision and alembic never reruns it, and its own
`backfill_raises` skips every header that already holds a raise row (the `raised` row this
revision keeps). The current import converts its clock at the write site
(`project_order_inquiry_import_service.py:3044`, `now = _now() - timedelta(hours=8)`) and
`_record_raise` stamps `datetime.utcnow()`.

Downgrade is a no-op by design: the deleted rows carried no fact, and re-adding eight hours
would re-create the defect. The real rollback is restoring the pre-migrate database dump.

Revision ID: oitc_0001_fake_reconfirms
Revises: eem_0003_span_meaning
Create Date: 2026-10-27
"""
from __future__ import annotations

import logging
from typing import Dict

revision = "oitc_0001_fake_reconfirms"
down_revision = "eem_0003_span_meaning"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.oitc_0001_fake_reconfirms")

#: `decision_trail_service._SHEET_MIGRATION_NOTE_PREFIX`, frozen here: a migration must not
#: read app code that can move under it.
_SHEET_NOTE_PREFIX = "Migrated from order inquiry sheet"


# --------------------------------------------------------------------------- schema helpers
#
# Copied from `523_oi_monthly_no_raises.py`, same reason: a hard-coded `projects.` inside a
# statement would reach the REAL schema from a test on `tests/_pg_fixture.py`'s scratch copy.


def _schema(bind, module: str) -> str:
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _table(bind, name: str) -> str:
    return f'"{_schema(bind, "projects")}"."{name}"'


# --------------------------------------------------------------------------- data step


def clean_fake_reconfirms(bind) -> Dict[str, int]:
    inquiries = _table(bind, "order_inquiries")
    rows = _table(bind, "order_inquiry_rows")
    raises = _table(bind, "order_inquiry_raises")

    bind.exec_driver_sql("DROP TABLE IF EXISTS zzt_oitc_stamps")
    bind.exec_driver_sql(
        f"""
        CREATE TEMP TABLE zzt_oitc_stamps AS
        SELECT r.raised_at AS stamp, r.raised_by AS uploader
        FROM {raises} r
        JOIN {rows} w
          ON w.order_inquiry_id = r.order_inquiry_id
         AND w.acknowledged_at = r.raised_at
         AND w.acknowledged_by = r.raised_by
        WHERE r.kind = 'reconfirmed'
          AND w.note LIKE %(prefix)s
          AND r.raised_at - w.created_at BETWEEN interval '7 hours 50 minutes'
                                             AND interval '9 hours'
        UNION
        -- An upload that left no fake reconfirm (it created no header 523 could misread)
        -- is tied to its rows by its own job instead: the uploader's OI-sheet job was
        -- running at the stamp's real instant (stamp minus 8 h), and at the row's birth.
        SELECT w.acknowledged_at, w.acknowledged_by
        FROM {rows} w
        JOIN import_jobs j
          ON j.job_type = 'order_inquiry_import'
         AND j.user_id = w.acknowledged_by
         AND w.acknowledged_at - interval '8 hours'
             BETWEEN j.created_at AND COALESCE(j.completed_at, j.created_at + interval '1 hour')
         AND w.created_at
             BETWEEN j.created_at AND COALESCE(j.completed_at, j.created_at + interval '1 hour')
        WHERE w.note LIKE %(prefix)s
          AND w.acknowledged_at - w.created_at BETWEEN interval '7 hours 50 minutes'
                                                   AND interval '9 hours'
        """,
        {"prefix": _SHEET_NOTE_PREFIX + "%"},
    )
    bind.exec_driver_sql("DROP TABLE IF EXISTS zzt_oitc_fake")
    bind.exec_driver_sql(
        f"""
        CREATE TEMP TABLE zzt_oitc_fake AS
        SELECT r.id, r.order_inquiry_id, r.raised_by
        FROM {raises} r
        JOIN zzt_oitc_stamps s ON s.stamp = r.raised_at AND s.uploader = r.raised_by
        WHERE r.kind = 'reconfirmed'
        """
    )

    def _count(sql: str) -> int:
        return int(bind.exec_driver_sql(sql).rowcount or 0)

    counts: Dict[str, int] = {
        "stamps": int(bind.exec_driver_sql("SELECT COUNT(*) FROM zzt_oitc_stamps").scalar() or 0)
    }
    for column in ("acknowledged_at", "actioned_at", "changed_at"):
        counts[f"rows_{column}"] = _count(
            f"""
            UPDATE {rows} w SET {column} = w.{column} - interval '8 hours'
            WHERE w.{column} IN (SELECT stamp FROM zzt_oitc_stamps)
            """
        )
    # 523 blanked the `raised` row's name only because it believed a later reconfirm had
    # overwritten the header's `raised_by`. With that reconfirm shown fake, the header's name
    # IS the raiser's (the import stamps only a header it creates, `_Raiser`).
    counts["raised_by_restored"] = _count(
        f"""
        UPDATE {raises} r SET raised_by = f.raised_by
        FROM zzt_oitc_fake f, {inquiries} h
        WHERE r.order_inquiry_id = f.order_inquiry_id
          AND h.id = f.order_inquiry_id
          AND h.raised_by = f.raised_by
          AND r.kind = 'raised'
          AND r.raised_by IS NULL
        """
    )
    counts["reconfirms_deleted"] = _count(
        f"DELETE FROM {raises} r USING zzt_oitc_fake f WHERE r.id = f.id"
    )
    bind.exec_driver_sql("DROP TABLE zzt_oitc_fake")
    bind.exec_driver_sql("DROP TABLE zzt_oitc_stamps")
    return counts


def upgrade() -> None:
    from alembic import op

    counts = clean_fake_reconfirms(op.get_bind())
    logger.info("oitc_0001_fake_reconfirms: %s", counts)


def downgrade() -> None:
    # Intentionally nothing: see the module docstring. Restore the pre-migrate dump instead.
    logger.info("oitc_0001_fake_reconfirms: downgrade is a no-op; restore the pre-migrate dump")
