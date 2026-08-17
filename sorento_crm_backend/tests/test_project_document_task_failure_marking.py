"""The last-resort failure write must land on the row, now that the tables moved schema.

``app.tasks.project_document_tasks._mark_failed`` used to build a string:

    f"UPDATE {table} SET extraction_state = 'failed' ..."

with ``table`` a bare literal (``project_po_versions`` / ``delivery_schedule_versions``).
After ADR-0011 both tables live in the ``projects`` schema under new names, and that shape
has two ways to be wrong with no way to complain about either, because the whole body is
wrapped in ``except Exception: logger.exception(...)``:

1. **The stale legacy name** - ``UPDATE project_po_versions`` no longer resolves at all.
   The statement raises ``UndefinedTable``, the handler swallows it, and the row keeps
   saying ``running``.
2. **Hardcoded ``projects.``** - reaches PAST a test's scratch schema into the REAL
   ``projects`` tables (hazard H5 in the schema-move plan). Nothing raises: the UPDATE
   matches zero rows in the real schema and the task returns "failed" while the row the
   user is watching stays on ``running`` for ever - which is the exact bug S20 was
   written to fix, reintroduced by a table move.

Both were run against these assertions before the file was kept, and both leave the row
on ``running``. (A third shape, the unqualified stripped name ``UPDATE po_versions``,
does happen to work here, because ``po_versions`` is not one of the seven module names
that collide with a core table and the fixture's ``search_path`` reaches the scratch
projects schema. It is still the wrong thing to write - the seven colliding names would
silently hit core - but this file does not claim to catch it.)

So the assertion that matters is not "it did not raise" (it never raises). It is that the
state on the ROW actually changed, read back through the fixture's own schema.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.project_so import (
    DeliverySchedule,
    DeliveryScheduleVersion,
    ProjectPOVersion,
)
from app.models.user import User
from app.services import project_seed_service
from app.tasks.project_document_tasks import _mark_failed

from ._pg_fixture import blank_session

MARKER = "zzt-doc-task-failure"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} owner"))
    db.flush()
    return user_id


@pytest.fixture()
def seeded():
    """A real PO version and a real schedule version, both mid-read.

    Seeds its own chain (company -> user -> project -> PO -> version) rather than
    borrowing a row: CI's database is empty.
    """
    from app.services import project_po_service as po_svc
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=None,
            title=f"{MARKER} {_uid()[:6]}",
        )
        po = po_svc.create_po(
            db,
            project=project,
            actor_user_id=owner,
            payload={"po_number": f"ZZT/{_uid()[:8]}", "po_source": "contractor_direct"},
        )
        po_version = ProjectPOVersion(
            company_id=company_id,
            purchase_order_id=po.id,
            version_no=1,
            source_filename=f"{MARKER}.pdf",
            page_count=10,
            extraction_state="running",
            extraction_job_id="zzt-job",
        )
        schedule = DeliverySchedule(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            purchase_order_id=po.id,
            label=f"{MARKER} programme",
        )
        db.add_all([po_version, schedule])
        db.flush()
        schedule_version = DeliveryScheduleVersion(
            company_id=company_id,
            delivery_schedule_id=schedule.id,
            version_no=1,
            source_filename=f"{MARKER}-schedule.pdf",
            extraction_state="running",
            extraction_job_id="zzt-schedule-job",
        )
        db.add(schedule_version)
        db.commit()
        yield db, po_version, schedule_version


def test_a_failed_po_read_leaves_the_version_row_saying_failed(seeded):
    db, po_version, _schedule_version = seeded
    row_id = po_version.id

    _mark_failed(db, ProjectPOVersion, row_id, RuntimeError("page 3 would not render"))

    db.expire_all()
    reread = db.query(ProjectPOVersion).filter(ProjectPOVersion.id == row_id).one()
    assert reread.extraction_state == "failed"
    assert "page 3 would not render" in (reread.extraction_error or "")


def test_a_failed_schedule_read_leaves_the_version_row_saying_failed(seeded):
    db, _po_version, schedule_version = seeded
    row_id = schedule_version.id

    _mark_failed(
        db, DeliveryScheduleVersion, row_id, RuntimeError("no programme grid found")
    )

    db.expire_all()
    reread = (
        db.query(DeliveryScheduleVersion)
        .filter(DeliveryScheduleVersion.id == row_id)
        .one()
    )
    assert reread.extraction_state == "failed"
    assert "no programme grid found" in (reread.extraction_error or "")


def test_it_still_writes_when_the_caller_left_the_transaction_broken(seeded):
    """The real call site is an ``except`` block, so the session is often unusable.

    ``_mark_failed`` opens with ``db.rollback()`` for exactly this. Without it every
    statement in the aborted transaction fails with ``InFailedSqlTransaction`` and the
    row keeps saying ``running``, silently, because the handler swallows.
    """
    db, po_version, _schedule = seeded
    row_id = po_version.id

    with pytest.raises(Exception):
        db.execute(text("select * from a_table_that_is_not_there"))

    _mark_failed(db, ProjectPOVersion, row_id, RuntimeError("died mid-read"))

    db.expire_all()
    reread = db.query(ProjectPOVersion).filter(ProjectPOVersion.id == row_id).one()
    assert reread.extraction_state == "failed"


def test_the_write_lands_in_the_schema_under_test_not_the_real_projects_one(seeded):
    """Hazard H5: a hardcoded ``projects.`` would reach past the scratch schema.

    Asserted from the catalog rather than by trusting the ORM: the row is found by a
    fully qualified read against the fixture's OWN projects schema, which is where a
    schema-honouring write puts it and where a hardcoded one never would.
    """
    db, po_version, _schedule = seeded
    row_id = po_version.id

    _mark_failed(db, ProjectPOVersion, row_id, RuntimeError("boom"))

    scratch = db.get_bind().get_execution_options()["schema_translate_map"]["projects"]
    assert scratch.startswith("zzt_"), scratch
    state = db.execute(
        text(f'select extraction_state from "{scratch}".po_versions where id = :i'),
        {"i": row_id},
    ).scalar()
    assert state == "failed"
