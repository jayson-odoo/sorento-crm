"""Who changed this customer, and from what.

`customers` was never opted into the audit system, so no path answered that question:
not the edit form, not the importer. Two halves are under test here.

* **The UI path is per-row.** `CustomerService` create/update go through the ORM, so the
  flush listener writes a CREATE row and an UPDATE row carrying old and new values.
* **The import path is per-JOB.** A debtor listing is routinely 4,000+ rows and runs on a
  worker with no request actor, so per-row auditing would write thousands of rows all
  reading "System". The task suppresses the per-row audit by entity type and writes ONE
  coarse row instead, naming the file, the job, the real user who pressed Confirm and what
  the run did. The per-row detail already exists in `import_job_rows`, and the coarse row
  carries the id that reaches it.

The suppression is keyed by an entity-type STRING, and a typo there is invisible until it
happens at volume (4,000 rows, wrongly attributed, in production). So the string the task
suppresses is asserted equal to the string the listener actually writes.

Every test seeds its own chain on a blank schema, so it says the same thing on CI's empty
database as on the local prod copy.
"""
from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import patch

import openpyxl
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit_context import set_audit_context
from app.models.audit import AuditLog
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.job import ImportJob, ImportJobRow, JobStatus
from app.models.order import Customer
from app.schemas.order import CustomerCreate, CustomerUpdate
from app.services.audit_service import _audit_entity_type, register_audit_listeners
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.order_service import CustomerService
from app.tasks.import_tasks import _CUSTOMER_ENTITY_TYPE, process_customer_import

from ._pg_fixture import blank_session, unique_code

HEADERS = ["Debtor Code", "Debtor Name", "Email", "Phone No"]


@pytest.fixture(autouse=True)
def _listeners():
    """Both global listener sets, exactly as the app registers them at startup."""
    register_company_scope_listeners()
    register_audit_listeners()


@pytest.fixture(autouse=True)
def _no_leaked_actor():
    yield
    set_audit_context(None, None)


def _aliases(session) -> None:
    """Seed the `customer` doc type's aliases the way migration 353 does.

    Alias rows are migration-body data, so a create_all schema has none of them and every
    column of the workbook would read as unmapped. Replayed from the migration itself so
    this cannot drift from what ships.
    """
    import importlib.util
    from pathlib import Path

    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "_customer_aliases_353", versions / "353_customer_import_aliases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session.connection())


def _workbook(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["DEBTOR LISTING 2026"])
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _audit_rows(session, entity_id: str) -> list[AuditLog]:
    return (
        session.query(AuditLog)
        .filter(AuditLog.entity_id == entity_id)
        .order_by(AuditLog.changed_at)
        .all()
    )


# ------------------------------------------------------------------ the UI path


def test_an_edit_records_the_value_it_moved_from_and_the_value_it_moved_to():
    """The question the defect made unanswerable: who changed the phone number, from what."""
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        editor = str(uuid.uuid4())
        code = unique_code("C")[:50]
        service = CustomerService(session)
        customer = service.create_customer(
            CustomerCreate(
                customer_code=code, customer_name="Alpha Trading", phone_number="03-1111111"
            )
        )
        customer_id = str(customer.id)

        set_audit_context(editor, "10.0.0.9")
        service.update_customer(customer_id, CustomerUpdate(phone_number="03-2222222"))

        updates = [r for r in _audit_rows(session, customer_id) if r.action == "UPDATE"]
        assert len(updates) == 1, [r.action for r in _audit_rows(session, customer_id)]
        row = updates[0]
        assert row.entity_type == _audit_entity_type(Customer)
        assert row.old_values["phone_number"] == "03-1111111"
        assert row.new_values["phone_number"] == "03-2222222"
        assert row.user_id == editor, "the edit names the person who made it"
        assert row.company_id == DEFAULT_COMPANY_ID


def test_a_new_customer_records_a_create_row():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code("C")[:50]

        customer = CustomerService(session).create_customer(
            CustomerCreate(
                customer_code=code, customer_name="Beta Supplies", email="b@example.com"
            )
        )
        customer_id = str(customer.id)

        creates = [r for r in _audit_rows(session, customer_id) if r.action == "CREATE"]
        assert len(creates) == 1
        assert creates[0].new_values["customer_code"] == code
        assert creates[0].new_values["customer_name"] == "Beta Supplies"
        # The company stamp lands in `before_insert`, AFTER the audit listener has
        # snapshotted the row - so a CREATE row can read null here while the customer
        # itself belongs to Sorento. Null is not a blank in this table: the admin
        # listing shows company-less audit rows to EVERY company, so the leak is the
        # created customer's name, email and phone.
        assert creates[0].company_id == DEFAULT_COMPANY_ID
        assert creates[0].company_id == str(customer.company_id)


def test_a_create_row_belongs_to_the_company_that_made_it():
    """A customer created in one company must not be readable from another.

    Same defect as the assertion above, said in the terms that matter: with the
    CREATE row's company null, `admin_listing_company_filter` hands it to every
    company's audit list, name and contact details included.
    """
    with blank_session() as session:
        other_company_id = str(uuid.uuid4())
        session.add(
            Company(id=other_company_id, name="ZZT Other", code=unique_code("CO")[:50])
        )
        session.flush()
        set_company_scope(session, frozenset({other_company_id}))

        customer = CustomerService(session).create_customer(
            CustomerCreate(customer_code=unique_code("C")[:50], customer_name="Gamma Sdn Bhd")
        )

        creates = [
            r for r in _audit_rows(session, str(customer.id)) if r.action == "CREATE"
        ]
        assert len(creates) == 1
        assert creates[0].company_id == other_company_id
        assert creates[0].company_id != DEFAULT_COMPANY_ID


def test_the_audited_columns_are_the_ones_worth_asking_about():
    """Business fields are captured; row bookkeeping the audit row already carries is not.

    `id` is the audit row's own entity_id, `company_id` its own column, and who/when is
    `user_id` + `changed_at` - repeating them inside every diff is noise, not history.
    """
    columns = set(Customer.__audit_columns__)
    assert {"phone_number", "email", "customer_name", "customer_code", "is_active"} <= columns
    assert columns.isdisjoint({"id", "company_id", "created_at", "created_by", "updated_at"})


# -------------------------------------------------------------- the import path


def _run_import(session, rows: int = 3) -> dict:
    """Run the real `process_customer_import` over a listing of `rows` debtors.

    The task opens its own session (and `ImportOutcome` another), so both are pointed at
    this test's connection, exactly as the GRN end-to-end test does.
    """
    _aliases(session)
    set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
    confirmer = str(uuid.uuid4())
    codes = [unique_code(f"C{i}")[:50] for i in range(rows)]
    job_db_id = uuid.uuid4()
    session.add(
        ImportJob(
            id=job_db_id,
            job_id=unique_code("job"),
            job_type="customer_import",
            user_id=confirmer,
            company_id=uuid.UUID(DEFAULT_COMPANY_ID),
            filename="debtor_listing.xlsx",
        )
    )
    session.commit()

    bind = session.get_bind()

    def _session_on_this_connection():
        db = Session(bind=bind, join_transaction_mode="create_savepoint")
        db.execute(text("SELECT 1"))
        return db

    data = _workbook(
        [[code, f"Debtor {i}", f"d{i}@example.com", "03-999"] for i, code in enumerate(codes)]
    )
    with patch("app.tasks.import_tasks.SessionLocal", _session_on_this_connection):
        process_customer_import(str(job_db_id), data, "debtor_listing.xlsx", confirmer)

    # The task wrote through its own session on this connection; expire ours so the
    # job's final status is read from the database, not from our identity map.
    session.expire_all()
    return {
        "session": session,
        "job_db_id": job_db_id,
        "job_id": session.get(ImportJob, job_db_id).job_id,
        "confirmer": confirmer,
        "codes": codes,
    }


@pytest.fixture
def imported():
    with blank_session() as session:
        yield _run_import(session)


def _imported_customers(seeded) -> list[Customer]:
    return (
        seeded["session"]
        .query(Customer)
        .filter(Customer.customer_code.in_(seeded["codes"]))
        .all()
    )


def _job_audit_rows(seeded) -> list[AuditLog]:
    return (
        seeded["session"]
        .query(AuditLog)
        .filter(AuditLog.entity_id == seeded["job_id"])
        .all()
    )


def test_the_import_writes_no_audit_row_per_customer(imported):
    """4,000 rows must not become 4,000 audit rows, every one of them saying "System".

    The anti-vacuity check comes first: with auditing off there would be nothing to
    suppress, and this test would pass while proving nothing.
    """
    assert Customer.__audit_track__ is True, "nothing to suppress, so this proves nothing"

    customers = _imported_customers(imported)
    assert len(customers) == 3, "the file has to have actually imported"

    session = imported["session"]
    per_row = (
        session.query(AuditLog)
        .filter(AuditLog.entity_id.in_([str(c.id) for c in customers]))
        .all()
    )
    assert per_row == [], [(r.entity_type, r.action) for r in per_row]


def test_the_import_writes_exactly_one_job_row(imported):
    rows = _job_audit_rows(imported)
    assert len(rows) == 1, [(r.action, r.description) for r in rows]
    assert rows[0].action == "IMPORT"
    assert rows[0].entity_type == _CUSTOMER_ENTITY_TYPE
    assert "debtor_listing.xlsx" in (rows[0].description or "")


def test_the_job_row_names_the_person_who_confirmed_it(imported):
    """A worker has no request actor, so an unattributed row would read "System"."""
    row = _job_audit_rows(imported)[0]
    assert row.user_id == imported["confirmer"]


def test_the_job_row_says_what_the_run_changed(imported):
    values = _job_audit_rows(imported)[0].new_values
    assert values["created"] == 3
    assert values["updated"] == 0
    assert values["total_rows"] == 3
    assert values["filename"] == "debtor_listing.xlsx"


def test_the_job_row_reaches_the_per_row_detail(imported):
    """The coarse row is only worth having if it leads to the rows it stands for."""
    values = _job_audit_rows(imported)[0].new_values
    assert values["import_job_id"] == str(imported["job_db_id"])

    detail = (
        imported["session"]
        .query(ImportJobRow)
        .filter(ImportJobRow.import_job_id == uuid.UUID(values["import_job_id"]))
        .all()
    )
    assert len(detail) == 3
    assert {r.entity_id for r in detail} == {
        str(c.id) for c in _imported_customers(imported)
    }


def test_a_broken_audit_row_does_not_fail_an_import_that_worked():
    """The audit row is a footnote to the import; it must never be able to void it.

    The details dict is built inside `_write_import_audit`'s guard for this reason.
    Built at the call site instead, it runs after `complete_job` has committed and
    outside that guard, so a stale read of the (by then expired) job row would land
    in the task's own except clause and mark a finished import FAILED.
    """
    with blank_session() as session:
        with patch(
            "app.tasks.import_tasks._customer_import_details",
            side_effect=RuntimeError("job row expired by the commit"),
        ):
            seeded = _run_import(session)

        job = session.get(ImportJob, seeded["job_db_id"])
        assert job.status == JobStatus.FINISHED.value, job.error_message
        assert len(_imported_customers(seeded)) == 3, "the customers still imported"
        # What we lose is the coarse row itself, and only that.
        assert _job_audit_rows(seeded) == []


def test_the_suppressed_entity_type_is_the_one_the_listener_writes():
    """A mismatch here silently disables the suppression: 4,000 rows, no error.

    Both halves matter. The task suppresses by string, and the listener writes whatever
    `_audit_entity_type` derives from the model - so the two are pinned to each other
    rather than to a literal restated in the test.
    """
    assert _CUSTOMER_ENTITY_TYPE == _audit_entity_type(Customer)
