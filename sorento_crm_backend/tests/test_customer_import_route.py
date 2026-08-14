"""POST /api/v1/order-management/customers/import.

Happy path, dry run, the company-scope refusal, input validation and auth denial. The queue
and the source-file store are stubbed: what is under test is the route's own decisions.

The refusal is the one worth spelling out. `customers` is an owned table (ADR 0007), so a
session with no single active company cannot answer "whose customer book is this?". The
generic worker path would run system-scoped, which for an owned table means either failing
closed on row 4,000 or writing across the partition - both after the operator was told the
import was queued. So it is a 400 at the route, before anything queues (AC-2.3).
"""
from __future__ import annotations

import importlib.util
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.user import UserPermission, UserRole, UserRolePermission
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

from ._pg_fixture import blank_session

ENDPOINT = "/api/v1/order-management/customers/import"
PERMISSION = "order_management.customers.import"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MIGRATION_354 = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "354_customer_import_permission.py"
)


def _workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["DEBTOR LISTING 2026"])
    sheet.append(["Debtor Code", "Debtor Name", "Email"])
    sheet.append(["301-C001", "CASH (SRT) - AISAH SHAMSUDIN", "a@example.com"])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _client(*, permitted: bool, scope, monkeypatch) -> TestClient:
    user = {"id": str(uuid.uuid4())}

    def _db():
        session = MagicMock()
        # A REAL dict, so `get_company_scope` reads the four-state scope the way it does
        # on a request session rather than getting a truthy MagicMock back.
        session.info = {} if scope is _ABSENT else {"company_scope": scope}
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    # The router-level resolver re-stamps the scope on every request and lands on UNSET
    # without a real Bearer token, so overriding it is what makes the scope under test the
    # scope the route sees. Without this every case here reads as "no active company".
    app.dependency_overrides[apply_company_scope] = lambda: scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: permitted,
    )
    return TestClient(app)


_ABSENT = object()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def stub_queue(monkeypatch):
    """Capture what the route would enqueue and retain, without doing either."""
    captured: dict = {"enqueued": [], "retained": [], "jobs": []}

    class _Job:
        def __init__(self):
            self.id = uuid.uuid4()
            self.job_id = str(uuid.uuid4())

    class _JobService:
        def __init__(self, db):
            pass

        def create_job(self, **kwargs):
            captured["jobs"].append(kwargs)
            return _Job()

        def update_job_with_rq_id(self, job, rq_id):
            captured.setdefault("rq_ids", []).append(rq_id)

    def _enqueue(func, *args, **kwargs):
        captured["enqueued"].append({"func": func.__name__, "args": args, "kwargs": kwargs})
        return MagicMock(id=str(uuid.uuid4()))

    def _store(job, data, name, ctype):
        captured["retained"].append({"bytes": data, "name": name, "content_type": ctype})

    # Patched where the route BOUND them (module-level imports), not where they live.
    monkeypatch.setattr("app.api.v1.order_management.customers.JobService", _JobService)
    monkeypatch.setattr("app.api.v1.order_management.customers.enqueue_job", _enqueue)
    monkeypatch.setattr(
        "app.services.import_source_store.store_import_source_file", _store
    )
    return captured


# ------------------------------------------------------------------ happy path


def test_queues_an_import_job_and_returns_202(stub_queue, monkeypatch):
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    response = client.post(
        ENDPOINT, files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] and body["id"]
    assert len(stub_queue["enqueued"]) == 1
    enqueued = stub_queue["enqueued"][0]
    assert enqueued["func"] == "process_customer_import"
    assert enqueued["kwargs"]["queue_name"] == "imports"
    assert stub_queue["jobs"][0]["job_type"] == "customer_import"


def test_the_job_snapshots_the_active_company(stub_queue, monkeypatch):
    """AC-2.1: the worker re-establishes exactly this company, so owned writes stamp and
    scoped reads isolate. A NULL snapshot would run system-scoped."""
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    client.post(ENDPOINT, files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)})

    assert stub_queue["jobs"][0]["company_id"] == DEFAULT_COMPANY_ID


def test_retains_the_original_bytes_for_tracing(stub_queue, monkeypatch):
    """AC-5.5: the file the route keeps is the file that arrived, pre macro-strip."""
    payload = _workbook_bytes()
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    client.post(ENDPOINT, files={"file": ("Debtor Listing.xlsx", payload, XLSX)})

    assert len(stub_queue["retained"]) == 1
    assert stub_queue["retained"][0]["bytes"] == payload
    assert stub_queue["retained"][0]["name"] == "Debtor Listing.xlsx"


# -------------------------------------------------------------- company refusal


@pytest.mark.parametrize(
    "scope, label",
    [
        (None, "all companies"),
        (_ABSENT, "unresolved"),
        (frozenset(), "empty"),
        (frozenset({DEFAULT_COMPANY_ID, "00000000-0000-0000-0000-000000000002"}), "two"),
    ],
)
def test_no_single_company_is_refused_before_anything_queues(
    scope, label, stub_queue, monkeypatch
):
    client = _client(permitted=True, scope=scope, monkeypatch=monkeypatch)

    response = client.post(
        ENDPOINT, files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)}
    )

    assert response.status_code == 400, label
    assert "single company" in response.text
    assert stub_queue["jobs"] == [], "no job row for a refused import"
    assert stub_queue["enqueued"] == []
    assert stub_queue["retained"] == []


# --------------------------------------------------------------------- dry run


def test_the_dry_run_returns_the_summary_and_queues_nothing(stub_queue, monkeypatch):
    monkeypatch.setattr(
        "app.tasks.import_tasks.validate_customer_import",
        lambda data, company_scope=None: {
            "valid": True,
            "errors": [],
            "warnings": ["Row 14: no customer name"],
            "summary": {
                "total_rows": 900,
                "would_create": 612,
                "would_update": 240,
                "would_unchanged": 45,
                "would_skip": 3,
                "needs_review": 2,
                "unmapped_headers": ["SALESMAN"],
                "missing_columns": [],
                "problems": [{"row": 14, "reason": "no customer name"}],
            },
        },
    )
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    response = client.post(
        f"{ENDPOINT}?validate_only=true",
        files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    # Exactly the keys the dialog renders.
    assert set(body["summary"]) == {
        "total_rows",
        "would_create",
        "would_update",
        "would_unchanged",
        "would_skip",
        "needs_review",
        "unmapped_headers",
        "missing_columns",
        "problems",
    }
    assert stub_queue["enqueued"] == [], "a dry run must not queue an import"
    assert stub_queue["retained"] == [], "a dry run must not retain a source file"


def test_the_dry_run_runs_at_the_callers_company_scope(stub_queue, monkeypatch):
    """Preview and import must disagree about nothing, and which customers we already
    hold is exactly what decides create vs update."""
    seen: dict = {}

    def _validate(data, company_scope=None):
        seen["scope"] = company_scope
        return {"valid": True, "errors": [], "warnings": [], "summary": {}}

    monkeypatch.setattr("app.tasks.import_tasks.validate_customer_import", _validate)
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    client.post(
        f"{ENDPOINT}?validate_only=true",
        files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)},
    )

    assert seen["scope"] == frozenset({DEFAULT_COMPANY_ID})


def test_a_dry_run_is_refused_without_a_company_scope(stub_queue, monkeypatch):
    """Decision D2: reading across companies is not a harmless read.

    884 code+name pairs are held by BOTH Sorento and Mocha, so an all-companies preview
    answers "0 new, 884 unchanged" about a book that is not the one the import would
    write, and Confirm then 400s anyway. A preview that cannot be trusted is worse than
    no preview, so the refusal is above the validate_only branch.
    """
    called: list = []
    monkeypatch.setattr(
        "app.tasks.import_tasks.validate_customer_import",
        lambda data, company_scope=None: called.append(company_scope)
        or {"valid": True, "errors": [], "warnings": [], "summary": {}},
    )
    client = _client(permitted=True, scope=None, monkeypatch=monkeypatch)

    response = client.post(
        f"{ENDPOINT}?validate_only=true",
        files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)},
    )

    assert response.status_code == 400
    assert "single company" in response.text
    assert called == [], "the file is not even read at the wrong scope"


# ------------------------------------------------------------------ validation


def test_rejects_a_non_excel_file(stub_queue, monkeypatch):
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    response = client.post(ENDPOINT, files={"file": ("notes.txt", b"hello", "text/plain")})

    assert response.status_code == 400
    assert "Excel file" in response.text
    assert stub_queue["enqueued"] == []


def test_rejects_an_empty_upload(stub_queue, monkeypatch):
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    response = client.post(ENDPOINT, files={"file": ("Debtor Listing.xlsx", b"", XLSX)})

    assert response.status_code == 400
    assert "empty" in response.text.lower()
    assert stub_queue["enqueued"] == []


def test_a_missing_file_is_a_422(stub_queue, monkeypatch):
    client = _client(
        permitted=True, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    assert client.post(ENDPOINT).status_code == 422
    assert stub_queue["enqueued"] == []


# -------------------------------- fixtures for the migration-body tests below


def _load_migration_354():
    spec = importlib.util.spec_from_file_location("migration_354", _MIGRATION_354)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db, module) -> None:
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()


def _holds(db, role_id: str, slug: str) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT 1 FROM user_role_permissions urp "
                "JOIN user_permissions p ON p.id = urp.permission_id "
                "WHERE urp.role_id = :r AND p.slug = :slug"
            ),
            {"r": role_id, "slug": slug},
        ).first()
    )


@pytest.fixture()
def seeded_roles():
    """A blank schema holding the source permission, a role that has it, and one that
    does not. Seeded here rather than borrowed: CI's database is empty, so a `LIMIT 1`
    off `user_permissions` resolves to None there and the dependent INSERT dies.
    """
    module = _load_migration_354()
    with blank_session() as db:
        add = UserPermission(
            id=str(uuid.uuid4()), slug=module.ADD_SLUG, name=module.ADD_SLUG
        )
        db.add(add)
        roles = {}
        for key in ("adder", "bystander"):
            role = UserRole(
                id=str(uuid.uuid4()),
                slug=f"zzt-{uuid.uuid4().hex[:10]}",
                name=f"ZZT {key} {uuid.uuid4().hex[:6]}",
                is_trashed=False,
            )
            db.add(role)
            roles[key] = role.id
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=roles["adder"], permission_id=add.id
            )
        )
        db.flush()
        yield db, roles, module


# ---------------------------------------------------------------- auth denial


def test_a_caller_without_the_permission_is_refused(stub_queue, monkeypatch):
    client = _client(
        permitted=False, scope=frozenset({DEFAULT_COMPANY_ID}), monkeypatch=monkeypatch
    )

    response = client.post(
        ENDPOINT, files={"file": ("Debtor Listing.xlsx", _workbook_bytes(), XLSX)}
    )

    assert response.status_code == 403
    assert PERMISSION in response.text
    assert stub_queue["enqueued"] == [], "a refused caller must not queue anything"


def test_the_permission_is_registered_so_it_can_be_granted():
    """A permission that exists only in a route decorator is ungrantable, which is
    indistinguishable from a broken feature."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert PERMISSION in {entry["slug"] for entry in PERMISSION_REGISTRY}


# ------------------------------------------------- the grant path, exercised


def test_the_import_permission_is_granted_to_whoever_can_add_a_customer(seeded_roles):
    """DoD: a new permission needs an existing-role grant path, or the feature silently
    hides - the Import button would be invisible for every role, including the master-data
    staff the importer exists for.

    Migration 354 is that path, so its own ``upgrade()`` runs here against a blank schema
    inside a rolled-back transaction. Asserting two string constants proved only that the
    file spells the slug the same way the route does, which stays true if the grant SQL is
    deleted outright.
    """
    db, roles, module = seeded_roles

    _run_upgrade(db, module)

    assert db.execute(
        text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": PERMISSION}
    ).first(), "the permission row itself was not created"
    assert _holds(db, roles["adder"], PERMISSION), (
        "a role that can already add a customer did not gain the import permission"
    )
    assert not _holds(db, roles["bystander"], PERMISSION), "granted too widely"


def test_replaying_the_grant_sweep_changes_nothing(seeded_roles):
    """The shared dev database gets migrations replayed across worktrees, and a second
    grant row would break the (role, permission) unique constraint on a real deploy."""
    db, roles, module = seeded_roles

    _run_upgrade(db, module)
    _run_upgrade(db, module)

    count = db.execute(
        text(
            "SELECT count(*) FROM user_role_permissions urp "
            "JOIN user_permissions p ON p.id = urp.permission_id "
            "WHERE urp.role_id = :r AND p.slug = :s"
        ),
        {"r": roles["adder"], "s": PERMISSION},
    ).scalar()
    assert count == 1, f"expected one grant, found {count}"


def test_the_migration_grants_from_the_slug_the_registry_declares(seeded_roles):
    """The source slug has to exist to grant from: a typo there sweeps nobody, and the
    sweep is silent about it."""
    _db, _roles, module = seeded_roles

    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert module.IMPORT_SLUG == PERMISSION
    assert module.ADD_SLUG in slugs, "the source slug must exist to grant from"
