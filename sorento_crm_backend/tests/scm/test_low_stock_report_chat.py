"""S5 (PLAN-low-stock-report.md, low-stock-report-acceptance-criteria.md AC-40..AC-50,
issue #891) - the chat route: a fresh plan, a bounded wait, then either the file in the
turn or the worker pushes it.

Staff type "low stock report" into WhatsApp. The bot ALWAYS runs a fresh plan (owner
ruling 1, 14 Sep), so the route creates a run, a download row, and two queued jobs, then
holds the turn open for `system_settings.low_stock_sync_wait_seconds` waiting for the
workbook. If it arrives, the turn carries it. If it does not, the route hands delivery to
the worker and answers "pending" - and the two conditional UPDATEs make that an exclusive
choice, so a contact never gets the file twice and never gets it zero times (AC-46).

WRITTEN BEFORE THE IMPLEMENTATION EXISTS. `app/api/v1/scm/low_stock_report.py`,
`generate_low_stock_report`'s push tail and `system_settings.low_stock_sync_wait_seconds`
are all named by the plan, not read off code.

Three couplings this file deliberately takes on, because there is no way to test the
behaviour without them, and each is something the plan already commits to:

1. **The wait seam is `_await_download`** (plan S5: "`_await_download(download_id)`
   polling `user_downloads.status` ... bounded by `asyncio.wait_for`"). Tests patch it so
   nothing ever sleeps 40 s, and a lapsed budget is driven by raising
   `asyncio.TimeoutError` - which is what `asyncio.wait_for` itself raises, so the route's
   real handler is the one under test. Rename it and these go red; the docstring on
   `_patch_wait` says so.
2. **The route claims on the REQUEST session** (the one `Depends(get_db)` yields), not a
   freshly opened `SessionLocal`. Under this fixture the request session is the test's own
   rolled-back savepoint, so a second connection would see none of the seeded chain.
3. **The migration has landed.** Per the captain's ruling of 14 Sep the whole migration
   (`requested_via`, `deliver_to_contact_id`, `delivered_at`, `row_count_low`,
   `row_count_all`, `low_stock_sync_wait_seconds`) lands in S3, so these tests assume the
   columns exist and go red on them until it does.

Postgres only, marker-prefixed, rolled back at teardown. Nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.error_handler import AppException
from tests.scm.conftest import (
    SORENTO_COMPANY_ID,
    grant_permission,
    requires_pg,
    seed_user,
)
from tests.scm.test_order_sheet_export_downloads import (  # noqa: F401
    _NoCloseSession,
    _savepoint_session,
)

pytestmark = requires_pg

MARKER = "ZZTLSC"
ROUTE = "/api/v1/scm/low-stock-report"
GRANT_KEY = "scm.low_stock_report"
SUPPLIER_KEY = "purchase_orders.supplier"


def _u() -> str:
    return str(uuid.uuid4())


CDN_HOST = "https://cdn.test.invalid"


class _CdnBackend:
    """A storage backend that mints URLs without credentials.

    `attachment_url` reaches the REAL `r2_service` / `s3_service`, each of which raises
    `ValueError: ... configuration incomplete` when its five env vars are unset. That is
    correct of them and wrong of a test: CI has no cloud credentials, so eleven tests in
    this file passed only on a developer machine whose `.env` happened to hold real ones
    (caught by the lane's first CI run, 14 Sep). Patching `storage_router.get_backend` is
    the house pattern for this - `test_plan_product_images`, `test_chat_attachment_filename`
    and `test_supplier_notice_channels` all do it - and it keeps `attachment_url`'s own
    branch under test (R2 -> CDN URL, S3 -> signed URL), which stubbing `attachment_url`
    itself would not.
    """

    def get_cdn_base_url(self, key: str) -> str:
        return f"{CDN_HOST}/{key}"

    def get_cloudfront_base_url(self, key: str) -> str:
        return f"{CDN_HOST}/{key}"

    def get_signed_url(self, key: str, expires_in: int = 0) -> str:
        return f"{CDN_HOST}/{key}?signed={expires_in}"


@pytest.fixture(autouse=True)
def _no_cloud_credentials_needed(monkeypatch):
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _CdnBackend())


# --------------------------------------------------------------------------- #
# the module, the task - imported per test so a missing file is ONE red test
# rather than a collection error that hides every other test in this file
# --------------------------------------------------------------------------- #

def _route_mod():
    """`app/api/v1/scm/low_stock_report.py` - its own module, mounted in
    `scm/__init__.py`, because this route is the chatbot's and carries a second gate the
    other SCM routes do not."""
    from app.api.v1.scm import low_stock_report

    return low_stock_report


def _task():
    from app.tasks import export_tasks

    fn = getattr(export_tasks, "generate_low_stock_report", None)
    assert fn is not None, (
        "app.tasks.export_tasks.generate_low_stock_report does not exist yet (S3/AC-45)"
    )
    return export_tasks, fn


def _patch_wait(monkeypatch, *, on_wait):
    """Replace the route's own bounded poll.

    The plan names `_await_download(download_id)` as the seam (S5). A test that instead
    let the real 40 s budget run would take 40 s to prove the timeout branch, and could
    not make the READY branch happen at all - the export task never runs here (the queue
    is patched), so nothing would ever flip the row.

    `on_wait(download_id)` is the test's own script: mark the row ready, or raise
    `asyncio.TimeoutError` (exactly what `asyncio.wait_for` raises when the budget lapses,
    so the route's real handler for that case is what runs).
    """
    mod = _route_mod()
    assert hasattr(mod, "_await_download"), (
        "the plan names `_await_download(download_id)` as the wait seam (S5) - rename it "
        "and this test cannot drive the ready/timeout branches"
    )

    async def _fake(download_id, *args, **kwargs):
        return on_wait(str(download_id))

    monkeypatch.setattr(mod, "_await_download", _fake)
    return mod


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #

def _company_scope_only(app, db):
    """Give the request an active company WITHOUT overriding either current-user
    dependency.

    `tests.scm.conftest.as_user` does both, which would bypass the X-API-Key path this
    route's whole auth story is about (AC-40). The company half is still not optional:
    `scm.reorder_run` is `CompanyScopedMixin`, so the auto-stamp refuses an insert with no
    single active company and every run-creating route answers 400 - a failure that reads
    as a bug in the route.
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    scope = frozenset({SORENTO_COMPANY_ID})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope


def _api_key_caller(scm_app):
    """A REAL integration API key whose act-as user holds `scm.reorder.run`.

    Not `as_user`: AC-40 says the route is reached with `X-API-Key` through
    `require_permission_with_api_key`, and an override of `get_current_user_or_api_key`
    would prove nothing about that. Returns `(app, db, key, act_as_user_id)`.
    """
    from app.models.integration import Integration  # noqa: F401
    from app.models.user import User, UserRoleAssignment
    from app.services.integration_key_service import IntegrationKeyService

    app, db, _gcu, _gcuak = scm_app
    grant_permission(db, "purchasing", "scm.reorder.run")

    user = User(id=_u(), email=f"{MARKER}-{_u()[:8]}@integrations.local",
                name=f"{MARKER} act-as", status="ACTIVE", is_integration=True)
    db.add(user)
    db.flush()
    role_id = db.execute(
        text("SELECT id FROM user_roles WHERE slug = 'purchasing'")
    ).scalar()
    assert role_id, "role 'purchasing' not seeded"
    db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
    integration = Integration(name=f"{MARKER}-{_u()[:8]}", type="autocount_esb",
                              act_as_user_id=user.id, is_active=True)
    db.add(integration)
    db.flush()
    key = IntegrationKeyService(db).issue_key(integration)
    db.flush()

    _company_scope_only(app, db)
    return app, db, key, str(user.id)


def _contact(db, *, granted=(GRANT_KEY,), linked_user_id=None):
    """One `respond_contacts` row with `workspace_id` NULL, which is what makes
    `field_access.resolve_contact_with_null_workspace_fallback` resolve it from any
    `space_id` - the same resolution the chatbot head already uses, and the shape 16 live
    contacts are actually in.

    Grants go through `contact_field_reveal_service.set_granted_keys`, the service the
    admin UI writes with, so the test grants the way a human would. It does NOT validate
    against `FIELD_REVEAL_KEYS`, so `scm.low_stock_report` can be granted here before S6
    adds it to that literal.
    """
    from app.models.access import RespondContact
    from app.services.contact_field_reveal_service import set_granted_keys

    respond_io_id = f"{MARKER}-{uuid.uuid4().hex[:8]}"
    contact = RespondContact(
        id=_u(), respond_io_id=respond_io_id,
        phone_number=f"+6010{uuid.uuid4().hex[:7]}",
        name=f"{MARKER} staff", workspace_id=None,
    )
    db.add(contact)
    db.flush()
    if granted:
        set_granted_keys(db, contact.id, list(granted), actor_id=None)
    if linked_user_id:
        db.execute(text("UPDATE users SET respond_contact_id = :c WHERE id = :u"),
                   {"c": contact.id, "u": linked_user_id})
        db.flush()
    return contact


def _params(contact, **extra):
    base = {"contact_id": contact.respond_io_id, "space_id": f"{MARKER}-SPACE"}
    base.update(extra)
    return base


def _counts(db) -> tuple[int, int]:
    runs = db.execute(text("SELECT count(*) FROM scm.reorder_run")).scalar()
    dls = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    return runs, dls


def _fake_queue(monkeypatch):
    """Patch `enqueue_job` at its source and record every call - the same load-bearing
    patch `test_order_sheet_export_downloads` documents: the route resolves it
    function-locally, and an unpatched call reaches the lane's shared Redis for real."""
    from app.services import queue_service

    calls: list[dict] = []

    def _enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})
        return type("J", (), {"id": f"job-{len(calls)}"})()

    monkeypatch.setattr(queue_service, "enqueue_job", _enqueue)
    return calls


def _download_row(db, download_id):
    return db.execute(text(
        "SELECT status, kind, user_id, deliver_to_contact_id::text AS deliver_to, "
        "       delivered_at, storage_key, storage_provider "
        "FROM user_downloads WHERE id = :id"
    ), {"id": str(download_id)}).mappings().first()


def _clear_in_flight_runs(db) -> None:
    """B2 (Phase 3 security review): the chat route now refuses a second queued/running
    run for the SAME company - `create_run(refuse_if_in_flight=True)` maps its 409 to
    `{"status": "busy"}` (AC-49). A test that fires two SEQUENTIAL asks to compare their
    two outcomes is not exercising concurrency; it just needs the first run finished
    before the next, which a real between-turns gap always provides. Marking every
    in-flight run completed between the asks reproduces that gap. Same session the guard
    reads (`db.query(ReorderRun)` on the injected session), so a flush is enough."""
    db.execute(text(
        "UPDATE scm.reorder_run SET status = 'completed' "
        "WHERE status IN ('queued', 'running')"
    ))
    db.flush()


# =========================================================================== #
# AC-40: the route's own shape
# =========================================================================== #

def test_422_without_contact_or_space(scm_app):
    """AC-40: `contact_id` and `space_id` are REQUIRED - this route exists for the
    chatbot and for nothing else, and without a contact there is nobody to check the
    reveal key against or to push the file to. 422, and nothing written either time.

    GET, not POST (plan S5): the MCP compiler injects `view=render` only on query-param
    tools, so a POST tool would never reach the presenter.
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    db.flush()
    before = _counts(db)

    with TestClient(app) as c:
        no_contact = c.get(ROUTE, headers={"X-API-Key": key},
                           params={"space_id": f"{MARKER}-SPACE"})
        no_space = c.get(ROUTE, headers={"X-API-Key": key},
                         params={"contact_id": f"{MARKER}-WHO"})

    assert no_contact.status_code == 422, no_contact.text
    assert no_space.status_code == 422, no_space.text
    assert _counts(db) == before, "a rejected request created a run or a download row"


# =========================================================================== #
# AC-41: the second gate
# =========================================================================== #

def test_403_without_the_key_writes_nothing(scm_app):
    """AC-41: `require_permission_with_api_key` answers "this integration may run plans",
    which is not the same question as "may THIS CONTACT have the low stock report". The
    second gate is the per-contact reveal key, checked in-route before anything is
    written - the rule `require_permission_with_api_key`'s own docstring lays down for
    anything that writes.

    403 with a machine-readable code (the lane turns it into the literal refusal line,
    AC-64), and - the half that matters most - NO run and NO download row. A refused
    contact must not leave a plan running on the queue.
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db, granted=())
    db.flush()
    before = _counts(db)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "low_stock_report_not_enabled", resp.text
    assert _counts(db) == before, "a refused contact still created a run or a download row"


# =========================================================================== #
# AC-42: what the route creates
# =========================================================================== #

def test_creates_run_marked_chat_and_download_row_then_enqueues_run_then_export(
        scm_app, monkeypatch):
    """AC-42: a fresh run stamped `requested_via = "chat"` (so the buyer opening Reorder
    Planning can see WHY a plan they did not ask for exists - AC-4), a `low_stock_xlsx`
    download row against it, and TWO jobs: the run, then the export with `depends_on` the
    run's job, so the workbook is rendered from a completed plan rather than a half-frozen
    one.
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    calls = _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=lambda _id: (_ for _ in ()).throw(asyncio.TimeoutError()))

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    run_id = body["run_id"]

    assert db.execute(text(
        "SELECT requested_via FROM scm.reorder_run WHERE id = :r"
    ), {"r": run_id}).scalar() == "chat", "the run must say it came from chat"

    dl = db.execute(text(
        "SELECT id::text AS id, kind, source_entity_type, source_entity_id::text AS src "
        "FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": run_id}).mappings().first()
    assert dl is not None, "no download row was created for the run"
    assert dl["kind"] == "low_stock_xlsx"
    assert dl["source_entity_type"] == "reorder_run"

    assert len(calls) == 2, f"expected the run job then the export job, got {calls}"
    run_job, export_job = calls
    assert run_job["kwargs"].get("queue_name") == "imports", run_job["kwargs"]
    assert export_job["kwargs"].get("queue_name") == "imports", export_job["kwargs"]
    assert export_job["kwargs"].get("job_timeout") == 600, export_job["kwargs"]
    assert export_job["kwargs"].get("depends_on") is not None, (
        "the export must wait for the run - otherwise it renders an empty plan"
    )


def test_owner_is_the_user_linked_to_the_contact(scm_app, monkeypatch):
    """AC-42: the run and the file belong to the CRM user whose `users.respond_contact_id`
    is the chatting contact (18 users carry the link on the prod copy), so the workbook
    lands in THEIR My Downloads and the plan says who asked for it. An unlinked contact
    falls back to the act-as principal - the file still reaches them over chat, it simply
    has no personal drawer to sit in.
    """
    app, db, key, act_as_id = _api_key_caller(scm_app)
    linked_user = seed_user(db, "purchasing")
    linked = _contact(db, linked_user_id=linked_user)
    unlinked = _contact(db)
    db.flush()
    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=lambda _id: (_ for _ in ()).throw(asyncio.TimeoutError()))

    with TestClient(app) as c:
        linked_resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(linked))
        _clear_in_flight_runs(db)  # B2: the two asks are sequential, not concurrent
        unlinked_resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(unlinked))

    assert linked_resp.status_code == 200, linked_resp.text
    assert unlinked_resp.status_code == 200, unlinked_resp.text

    def _owner(run_id):
        created_by = db.execute(text(
            "SELECT created_by::text FROM scm.reorder_run WHERE id = :r"
        ), {"r": run_id}).scalar()
        user_id = db.execute(text(
            "SELECT user_id FROM user_downloads WHERE source_entity_id = :r"
        ), {"r": run_id}).scalar()
        return created_by, user_id

    assert _owner(linked_resp.json()["run_id"]) == (str(linked_user), str(linked_user)), (
        "a linked contact's plan and file belong to their own CRM user"
    )
    assert _owner(unlinked_resp.json()["run_id"]) == (act_as_id, act_as_id), (
        "an unlinked contact falls back to the act-as principal"
    )


# =========================================================================== #
# AC-43: ready inside the budget
# =========================================================================== #

def _mark_ready_with_counts(db, download_id, *, low=12, total=340,
                            key="exports/low-stock/x/low-stock-10092026.xlsx"):
    """What the export task does at the end of a successful render: the file is stored and
    the two COUNTS are written onto the row, so the route can say "Low: 12 of 340" without
    opening the workbook on the request thread (AC-43)."""
    from app.services.download_service import DownloadService

    DownloadService(db).mark_ready(
        str(download_id), storage_provider="r2", storage_key=key,
        filename="low-stock-10092026.xlsx",
    )
    db.execute(text(
        "UPDATE user_downloads SET row_count_low = :l, row_count_all = :a WHERE id = :id"
    ), {"l": low, "a": total, "id": str(download_id)})
    db.flush()


def test_ready_within_budget_returns_attachments(scm_app, monkeypatch):
    """AC-43: when the workbook lands inside the wait, the TURN carries it - one summary
    line and one attachment, in the shape Respond.io's `send_attachments` action takes.

    `low_count`/`all_count` come off the download row's own columns, never from reopening
    the file: the route is holding a chat turn open and has no business parsing a workbook
    on the request thread.
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch,
                on_wait=lambda download_id: _mark_ready_with_counts(db, download_id))

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready", body
    assert body["run_id"]
    assert "as_of" in body, body
    assert body["low_count"] == 12, body
    assert body["all_count"] == 340, body

    attachments = body["attachments"]
    assert len(attachments) == 1, attachments
    att = attachments[0]
    assert att["filename"] == "low-stock-10092026.xlsx", (
        "the filename is the storage key's last segment"
    )
    assert att["mimeType"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ), att
    assert att["attachmentType"] == "file", att
    assert att["url"], "no URL was handed to the bot"


def test_wait_budget_comes_from_system_settings(scm_app, monkeypatch):
    """AC-43: how long the turn is held open is a System Setting the owner can move, read
    LIVE per request - not a constant, and not cached. 40 s is the default because it sits
    under the chatbot's own 45 s queue-wait budget.

    `asyncio.wait_for` is spied on rather than replaced, so the real machinery still runs
    and only the budget is observed.
    """
    from app.models.user import SystemSetting

    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_u(), name=f"{MARKER} settings")
        db.add(row)
    row.low_stock_sync_wait_seconds = 7
    db.flush()

    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch,
                on_wait=lambda download_id: _mark_ready_with_counts(db, download_id))

    budgets: list[float] = []
    real_wait_for = asyncio.wait_for

    async def _spy(awaitable, timeout=None, **kwargs):
        budgets.append(timeout)
        return await real_wait_for(awaitable, timeout, **kwargs)

    monkeypatch.setattr(asyncio, "wait_for", _spy)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    assert 7 in budgets, (
        f"the route must wait system_settings.low_stock_sync_wait_seconds, saw {budgets}"
    )


def test_low_stock_sync_wait_seconds_validates_5_to_90_on_the_settings_route(scm_app):
    """AC-43 / AC-48: the new column is validated 5..90 on PUT exactly the way
    `media_sync_wait_seconds` beside it is, and it reaches the FE through BOTH manual dict
    builders - a new column that is not added to the GET builder never reaches the screen,
    which is the single most repeated defect in this codebase's lessons log.
    """
    from app.models.user import SystemSetting
    from tests.scm.conftest import as_user

    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, "admin")
    as_user(app, gcu, gcuak, uid)
    grant_permission(db, "admin", "user_management.settings.view")
    grant_permission(db, "admin", "user_management.settings.edit")
    # The settings singleton is created when absent: CI's database has none, and the PUT
    # answers 404 "Settings not found" rather than validating anything without it.
    if db.query(SystemSetting).first() is None:
        db.add(SystemSetting(id=_u(), name=f"{MARKER} settings"))
    db.flush()

    with TestClient(app) as c:
        too_small = c.put("/api/v1/user-management/settings/general",
                          json={"low_stock_sync_wait_seconds": 4})
        too_big = c.put("/api/v1/user-management/settings/general",
                        json={"low_stock_sync_wait_seconds": 91})
        ok = c.put("/api/v1/user-management/settings/general",
                   json={"low_stock_sync_wait_seconds": 60})
        echoed = c.get("/api/v1/user-management/settings/")

    assert too_small.status_code == 422, too_small.text
    assert too_big.status_code == 422, too_big.text
    assert ok.status_code == 200, ok.text
    assert echoed.status_code == 200, echoed.text
    assert echoed.json()["settings"].get("low_stock_sync_wait_seconds") == 60, (
        "the new column must be in the settings GET dict builder too"
    )


# =========================================================================== #
# AC-44: the budget lapses
# =========================================================================== #

def _timeout(_download_id):
    raise asyncio.TimeoutError()


def test_timeout_claims_delivery_and_returns_pending(scm_app, monkeypatch):
    """AC-44: when the budget lapses the route hands delivery to the worker with ONE
    conditional UPDATE, then tells the bot to say the file is on its way. The claim is the
    handover: it is what the export task later reads to decide whether to push.
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending", body
    assert body["run_id"]
    assert body["download_id"]

    row = _download_row(db, body["download_id"])
    assert row["deliver_to"] == contact.id, (
        "the claim must name the RESOLVED respond_contacts row, not the Respond.io id"
    )


def test_timeout_but_row_already_ready_returns_ready(scm_app, monkeypatch):
    """AC-44, the race: the budget lapses and the row turns `ready` in the same breath.
    The claim's `WHERE status <> 'ready'` touches 0 rows, and a 0-row claim is the route
    finding out it lost the race - so it answers with the file rather than telling the
    contact to wait for a push that will never fire (the task's own claim would find
    `deliver_to_contact_id IS NULL`).
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _fake_queue(monkeypatch)

    def _ready_then_timeout(download_id):
        _mark_ready_with_counts(db, download_id)
        raise asyncio.TimeoutError()

    _patch_wait(monkeypatch, on_wait=_ready_then_timeout)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready", body
    assert body["attachments"], body

    dl_id = db.execute(text(
        "SELECT id::text FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": body["run_id"]}).scalar()
    assert _download_row(db, dl_id)["deliver_to"] is None, (
        "a lost claim must leave deliver_to_contact_id NULL, or the worker pushes it twice"
    )


def test_claim_update_refuses_a_row_that_turned_ready_inside_the_window(
        scm_app, monkeypatch):
    """AC-44/AC-46: the `AND status <> 'ready'` half of the claim, on its own.

    Reviewer kill test B1 (Phase 3): the test above never reaches the UPDATE. The route
    reads `_ready_payload` BEFORE claiming, so a row that is already ready returns there
    and the predicate is never exercised - delete `AND status <> 'ready'` and that test
    stays green.

    The window the predicate actually guards is narrower: the row turns `ready` BETWEEN
    the route's pre-claim read and the UPDATE itself. That is a real interleaving - the
    export task runs on the worker, on its own connection, while this request is between
    two statements - and it is the one where getting it wrong sends the contact the same
    workbook twice (the turn answers `pending`, AND the task's claim finds a
    `deliver_to_contact_id` to push to).

    Driven by blinding the FIRST `_ready_payload` call while marking the row ready
    underneath it: the route then arrives at the UPDATE believing the row is not ready,
    which is exactly the state the predicate exists for. Its second call (after a 0-row
    claim) is the real function again, so the ready shape this asserts is the route's own,
    not the fake's.
    """
    mod = _route_mod()
    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    real_ready_payload = mod._ready_payload
    seen: list[str] = []

    def _blind_on_the_first_read(db_, *, run_id, download_id):
        seen.append(str(download_id))
        if len(seen) == 1:
            # The worker finishes HERE - after the route's pre-claim read has begun and
            # before its UPDATE. Marking it ready and answering None is that instant.
            _mark_ready_with_counts(db, download_id)
            return None
        return real_ready_payload(db_, run_id=run_id, download_id=download_id)

    monkeypatch.setattr(mod, "_ready_payload", _blind_on_the_first_read)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(seen) >= 2, (
        "the route must re-read the row after a 0-row claim - otherwise it answers "
        f"pending for a file that exists: {seen}"
    )
    assert body["status"] == "ready", (
        "the claim touched 0 rows because the row was already ready, so this turn LOST "
        f"the race and must answer with the file: {body}"
    )
    assert body["attachments"], body

    dl_id = db.execute(text(
        "SELECT id::text FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": body["run_id"]}).scalar()
    assert _download_row(db, dl_id)["deliver_to"] is None, (
        "without `AND status <> 'ready'` the UPDATE claims a ready row and the worker "
        "pushes a workbook this turn already delivered"
    )


# =========================================================================== #
# AC-45 / AC-46: the worker's push, and the exclusivity of the two claims
# =========================================================================== #

def _seed_claimed_download(db, contact, *, claimed: bool):
    """A run and a `low_stock_xlsx` download row, claimed for chat delivery or not."""
    from app.services.download_service import DownloadService

    run_id = str(db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now()) RETURNING id"
    ), {"id": _u(), "co": SORENTO_COMPANY_ID}).scalar())
    user_id = seed_user(db, "purchasing")
    dl = DownloadService(db).create(
        user_id=user_id, kind="low_stock_xlsx", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="low-stock-10092026.xlsx",
    )
    if claimed:
        db.execute(text(
            "UPDATE user_downloads SET deliver_to_contact_id = :c WHERE id = :id"
        ), {"c": contact.id, "id": str(dl.id)})
        db.flush()
    return run_id, str(dl.id)


def _patch_task_render(monkeypatch, export_tasks):
    """Everything the task does before its push tail, stubbed: render, storage, session."""
    from app.services.scm import low_stock_report_service

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "r2")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())
    monkeypatch.setattr(
        low_stock_report_service, "export_low_stock",
        # Four values since reviewer item 4: the builder returns the counts it already
        # has, so the task no longer re-reads the run to count rows.
        lambda db_, *, run_id, include_supplier=True: (
            b"fake-workbook",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "low-stock-10092026.xlsx",
            {"low": 12, "all": 340},
        ),
    )


def test_task_pushes_only_when_claimed(scm_app, monkeypatch):
    """AC-45: after `mark_ready` the task claims the PUSH with its own conditional UPDATE,
    and sends only when that update touches a row. An UNCLAIMED row was delivered inside
    the turn, so pushing it would send the contact the same workbook twice.

    `delivered_at` is set exactly once, which is what makes a retried RQ job harmless.
    """
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, _key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    sends: list[dict] = []
    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for",
                        lambda db_, **kw: sends.append(kw) or {"status": "sent"})

    claimed_run, claimed_dl = _seed_claimed_download(db, contact, claimed=True)
    unclaimed_run, unclaimed_dl = _seed_claimed_download(db, contact, claimed=False)

    task_fn(claimed_dl, claimed_run, str(_download_row(db, claimed_dl)["user_id"]))
    task_fn(unclaimed_dl, unclaimed_run,
            str(_download_row(db, unclaimed_dl)["user_id"]))

    assert len(sends) == 1, f"exactly one push, for the claimed row only: {sends}"
    sent = sends[0]
    assert sent["identifier"] == contact.respond_io_id
    assert sent["respond_contact_id"] == contact.id
    assert sent["attachment_type"] == "file"
    assert sent["business_table"] == "user_downloads"
    assert sent["business_id"] == claimed_dl
    assert sent["url"], "no URL was handed to Respond"

    assert _download_row(db, claimed_dl)["delivered_at"] is not None
    assert _download_row(db, unclaimed_dl)["delivered_at"] is None

    # A retry of the same job must not send a second time: `delivered_at IS NULL` is
    # already false, so the claim touches 0 rows.
    task_fn(claimed_dl, claimed_run, str(_download_row(db, claimed_dl)["user_id"]))
    assert len(sends) == 1, "a retried job pushed the same file twice"


def test_push_window_closed_is_logged_not_raised(scm_app, monkeypatch):
    """AC-45: Respond.io has no attachment-carrying template, so a closed 24 h window is a
    hard refusal from `send_chat_attachment_for` (422 `attachment_window_closed`). The
    task swallows it - the send is already logged in the outbox by `log_respond_send`, and
    raising would poison the RQ job for a file that rendered perfectly well.

    The download row stays `ready`: the workbook exists and is still in My Downloads.
    """
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, _key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    def _closed(db_, **kw):
        raise AppException(status_code=422,
                           message="Cannot send an attachment outside the 24h messaging window.",
                           code="attachment_window_closed")

    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for", _closed)

    run_id, dl_id = _seed_claimed_download(db, contact, claimed=True)
    result = task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

    assert result["status"] == "ready", (
        f"a closed window must not fail the export itself: {result}"
    )
    assert _download_row(db, dl_id)["status"] == "ready"


def test_interleaving_worker_ready_before_claim_and_claim_before_ready(
        scm_app, monkeypatch):
    """AC-46: exactly ONE of {the turn returns the file, the worker pushes it} happens, in
    BOTH orders. The two conditional UPDATEs are the whole mechanism - Postgres row locks
    serialise them, so whichever runs second sees the other's write and stands down.

    Order A (worker wins): the row is `ready` before the route's claim -> the claim touches
    0 rows -> the turn carries the file and NOTHING is ever pushed.
    Order B (route wins): the claim lands first -> the turn says pending -> the task's own
    claim touches 1 row -> exactly one push.
    """
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, key, _uid = _api_key_caller(scm_app)
    db.flush()
    _fake_queue(monkeypatch)
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    sends: list[dict] = []
    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for",
                        lambda db_, **kw: sends.append(kw) or {"status": "sent"})

    # --- order A: ready first, then the route's claim ----------------------------
    contact_a = _contact(db)
    db.flush()

    def _ready_then_timeout(download_id):
        _mark_ready_with_counts(db, download_id)
        raise asyncio.TimeoutError()

    _patch_wait(monkeypatch, on_wait=_ready_then_timeout)
    with TestClient(app) as c:
        resp_a = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact_a))
    assert resp_a.json()["status"] == "ready", resp_a.text
    dl_a = db.execute(text(
        "SELECT id::text FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": resp_a.json()["run_id"]}).scalar()
    task_fn(dl_a, resp_a.json()["run_id"], str(_download_row(db, dl_a)["user_id"]))
    assert sends == [], "the worker pushed a file the turn had already delivered"

    # --- order B: the route's claim first, then the task ---------------------------
    _clear_in_flight_runs(db)  # B2: order A's run is finished before order B's ask
    contact_b = _contact(db)
    db.flush()
    _patch_wait(monkeypatch, on_wait=_timeout)
    with TestClient(app) as c:
        resp_b = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact_b))
    assert resp_b.json()["status"] == "pending", resp_b.text
    dl_b = resp_b.json()["download_id"]
    task_fn(dl_b, resp_b.json()["run_id"], str(_download_row(db, dl_b)["user_id"]))
    assert len(sends) == 1, f"the claimed row must be pushed exactly once: {sends}"
    assert sends[0]["respond_contact_id"] == contact_b.id


# =========================================================================== #
# AC-47: the Supplier column follows the contact's own key
# =========================================================================== #

def test_supplier_column_omitted_without_purchase_orders_supplier_key(
        scm_app, monkeypatch):
    """AC-47: a dealer must never read a PO's supplier (D4, the reason
    `purchase_orders.supplier` is a reveal key at all). The route reads the contact's keys
    once and passes `include_supplier` into the task, so the column is never rendered
    rather than rendered and blanked - a blank column still says "there is a supplier and
    you may not see it".

    The plan-view export (AC-30) always includes it; only the chat path narrows.
    """
    app, db, key, _uid = _api_key_caller(scm_app)
    without = _contact(db, granted=(GRANT_KEY,))
    with_key = _contact(db, granted=(GRANT_KEY, SUPPLIER_KEY))
    db.flush()
    calls = _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    with TestClient(app) as c:
        c.get(ROUTE, headers={"X-API-Key": key}, params=_params(without))
        first_export = calls[1]
        _clear_in_flight_runs(db)  # B2: the two asks are sequential, not concurrent
        c.get(ROUTE, headers={"X-API-Key": key}, params=_params(with_key))
        second_export = calls[3]

    assert first_export["kwargs"].get("include_supplier") is False, (
        "a contact without purchase_orders.supplier must get a workbook with no "
        f"Supplier column: {first_export['kwargs']}"
    )
    assert second_export["kwargs"].get("include_supplier") is True, (
        f"a contact holding the key keeps the column: {second_export['kwargs']}"
    )


# =========================================================================== #
# AC-48: the marker reaches the plans list
# =========================================================================== #

def test_requested_via_reaches_run_list_and_detail(scm_app):
    """AC-48 / AC-4: "the run the chat asked for appears in Reorder Planning marked 'via
    chat', so the buyer knows why it exists". A column that never reaches the serialiser
    reaches no screen - the lesson this codebase has relearned most often - so both the
    list item AND the detail response are asserted, and a manual run is asserted to carry
    null rather than an invented default.
    """
    from tests.scm.conftest import as_user

    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, "purchasing")
    as_user(app, gcu, gcuak, uid)
    grant_permission(db, "purchasing", "scm.dashboard.view")

    chat_run = str(db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, "
        " requested_via, created_at, started_at) "
        "VALUES (:id, 'completed', false, :co, 'chat', now(), now()) RETURNING id"
    ), {"id": _u(), "co": SORENTO_COMPANY_ID}).scalar())
    manual_run = str(db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at, "
        " started_at) VALUES (:id, 'completed', false, :co, now(), now()) RETURNING id"
    ), {"id": _u(), "co": SORENTO_COMPANY_ID}).scalar())
    db.flush()

    with TestClient(app) as c:
        listing = c.get("/api/v1/scm/reorder-runs", params={"limit": 100})
        chat_detail = c.get(f"/api/v1/scm/reorder-runs/{chat_run}")

    assert listing.status_code == 200, listing.text
    by_id = {item["run_id"]: item for item in listing.json()["data"]}
    assert by_id[chat_run].get("requested_via") == "chat", by_id[chat_run]
    assert by_id[manual_run].get("requested_via") is None, by_id[manual_run]

    assert chat_detail.status_code == 200, chat_detail.text
    assert chat_detail.json().get("requested_via") == "chat", chat_detail.text


# =========================================================================== #
# AC-49: a plan is already running
# =========================================================================== #

def test_busy_maps_the_in_flight_run_409_to_status_busy(scm_app, monkeypatch):
    """AC-49: run creation's own one-in-flight refusal is a 409, and a 409 reaching the
    chatbot is an error the bot cannot say anything useful about. The route maps it to
    `{status: "busy"}` so the presenter can answer "a plan is already running - try again
    in a minute" (AC-61).

    `create_run` is made to raise the 409 rather than seeding a real in-flight run: this
    test is about the MAPPING, and driving it through the refusal itself would couple it
    to wherever that guard lives.
    """
    from app.services.scm import reorder_run_service

    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    before = _counts(db)
    calls = _fake_queue(monkeypatch)

    def _busy(*args, **kwargs):
        raise AppException(status_code=409,
                           message="A reorder run is already in progress.",
                           code="run_in_progress")

    monkeypatch.setattr(reorder_run_service, "create_run", _busy)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, (
        f"busy is an ANSWER the bot can say, not an HTTP error: {resp.text}"
    )
    # The `reason` rides along (console round 3, defect C) so the presenter can say WHICH
    # busy this is - an in-flight plan clears in a minute, a rate limit needs the window.
    assert resp.json() == {"status": "busy", "reason": "in_flight"}, resp.text
    assert calls == [], "a busy answer must not enqueue anything"
    # A DELTA against this test's own starting point, not `count(*) == 0`. The absolute
    # form assumed an empty `user_downloads`, which is true on CI and true on a private
    # lane database and false the moment the suite is pointed anywhere else - it cost a
    # false bug report against the route when a stray `low_stock_xlsx` row from another
    # lane's database made it fail. The route's own guarantee is "creates nothing", and a
    # delta is what states that.
    assert _counts(db) == before, (
        "a busy answer must create neither a run nor a download row"
    )


# =========================================================================== #
# Console round 2, finding A - the request carries NO company scope
#
# CODER-AUTHORED (14 Sep 2026). Every test above runs under `_company_scope_only`, which
# pre-sets an active company on the session - so none of them could see that a REAL
# API-key request carries none, and that `scm.reorder_run` is `CompanyScopedMixin`: on the
# lane stack the first insert answered 400 `company_scope_required` and no run, no
# download row and no job were ever created. The route now resolves the company from the
# contact (its own membership when it has exactly one, else the owner user's active
# company) and stamps it BEFORE either write.
# =========================================================================== #

def _contact_company(db, contact, company_id=SORENTO_COMPANY_ID) -> None:
    """The admin-managed `respond_contact_companies` membership - the same M2M the
    API-key READ scope resolves through, so the plan is built for the company whose stock
    the asker can actually see."""
    from app.models.company import RespondContactCompany

    db.add(RespondContactCompany(
        id=_u(), respond_contact_id=contact.id, company_id=company_id,
    ))
    db.flush()


def test_the_run_takes_the_contacts_company_with_no_ambient_scope(scm_app, monkeypatch):
    """The console's own request shape: `X-API-Key`, a contact, and NO company scope on
    the session. The run must be created and stamped with the CONTACT's company.

    `_api_key_caller`'s scope override is removed deliberately - reinstating it would
    reproduce the fixture that hid this defect rather than the request that found it.
    """
    from app.services.company_scope_resolver import apply_company_scope

    app, db, key, _uid = _api_key_caller(scm_app)
    app.dependency_overrides.pop(apply_company_scope, None)
    contact = _contact(db)
    _contact_company(db, contact)
    db.flush()
    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, (
        f"an API-key turn with no ambient company scope must still run: {resp.text}"
    )
    run_id = resp.json()["run_id"]
    company_id = db.execute(text(
        "SELECT company_id::text FROM scm.reorder_run WHERE id = :r"
    ), {"r": run_id}).scalar()
    assert company_id == SORENTO_COMPANY_ID, (
        f"the run must be stamped with the contact's own company: {company_id}"
    )
    assert db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": run_id}).scalar() == 1, "the download row was not created either"


# =========================================================================== #
# Console round 3, defect A - the wait is capped by the TRANSPORT timeout
#
# CODER-AUTHORED. Measured on the stack: a full unscoped run took >10 s, the lane's MCP
# client (`chatbot_mcp_timeout_seconds`, 10 s) gave up first with httpx.ReadTimeout, and
# because this route was still inside its own 40 s budget it never reached the timeout
# branch - so `deliver_to_contact_id` was never set and the worker built a workbook nobody
# delivered. The route must answer `pending` (and claim delivery) BEFORE the lane hangs up.
# =========================================================================== #

def test_the_wait_is_capped_by_the_mcp_transport_timeout(scm_app, monkeypatch):
    """setting 40 s, transport 10 s -> the route waits 7 (transport minus the 3 s margin it
    needs to build the answer and claim delivery on the wire), never the configured 40."""
    import asyncio as _asyncio

    from app.config import settings as app_settings
    from app.models.user import SystemSetting

    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_u(), name=f"{MARKER} settings")
        db.add(row)
    row.low_stock_sync_wait_seconds = 40
    db.flush()
    monkeypatch.setattr(app_settings, "chatbot_mcp_timeout_seconds", 10, raising=False)

    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    budgets: list[float] = []
    real_wait_for = _asyncio.wait_for

    async def _spy(awaitable, timeout=None, **kwargs):
        budgets.append(timeout)
        return await real_wait_for(awaitable, timeout, **kwargs)

    monkeypatch.setattr(_asyncio, "wait_for", _spy)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    assert 7 in budgets, (
        f"the wait must be min(40, 10 - 3) = 7 so `pending` wins the race: {budgets}"
    )
    assert 40 not in budgets, f"the uncapped setting must never be the budget: {budgets}"


def test_a_short_setting_still_wins_over_the_transport_cap(scm_app, monkeypatch):
    """The cap is a ceiling, not a floor: an owner who sets 5 s gets 5, not 7."""
    import asyncio as _asyncio

    from app.config import settings as app_settings
    from app.models.user import SystemSetting

    app, db, key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_u(), name=f"{MARKER} settings")
        db.add(row)
    row.low_stock_sync_wait_seconds = 5
    db.flush()
    monkeypatch.setattr(app_settings, "chatbot_mcp_timeout_seconds", 10, raising=False)

    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    budgets: list[float] = []
    real_wait_for = _asyncio.wait_for

    async def _spy(awaitable, timeout=None, **kwargs):
        budgets.append(timeout)
        return await real_wait_for(awaitable, timeout, **kwargs)

    monkeypatch.setattr(_asyncio, "wait_for", _spy)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    assert 5 in budgets, f"the configured 5 s is already inside the cap: {budgets}"


# =========================================================================== #
# Console round 4, AC-45a - a swallowed push is never silent
#
# CODER-AUTHORED. Measured on the stack: download 96f3c045 read `status=ready,
# delivered_at set, error empty` with NO integration_log row for it. The 24 h window on
# that copy is stale, so `send_chat_attachment_for` raises its UPFRONT
# AppException(422, attachment_window_closed) BEFORE reaching its own `log_respond_send` -
# and `_push_low_stock_to_chat` swallowed it. The row said delivered, the contact got
# nothing, and nothing anywhere said otherwise. The claim-before-send ordering stays (it is
# what makes delivery exactly-once); what changes is that the failure is now recorded.
# =========================================================================== #

def _integration_logs_for(db, download_id) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT error_message, business_table FROM integration_log "
        "WHERE business_table = 'user_downloads' AND business_id = :id"
    ), {"id": str(download_id)}).mappings().all()]


def test_a_closed_window_push_leaves_an_error_and_an_outbox_row(scm_app, monkeypatch):
    """AC-45a: status stays `ready` (the workbook exists and My Downloads still serves it)
    and `delivered_at` stays set (this worker has taken its one shot), but the REASON is on
    the row and in the outbox - the two places an operator looks."""
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, _key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    def _closed(db_, **kw):
        raise AppException(
            status_code=422,
            message="Cannot send an attachment outside the 24h messaging window.",
            code="attachment_window_closed",
        )

    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for", _closed)

    run_id, dl_id = _seed_claimed_download(db, contact, claimed=True)
    result = task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

    assert result["status"] == "ready", (
        f"a closed window must not fail the export itself: {result}"
    )
    row = _download_row(db, dl_id)
    assert row["status"] == "ready", row["status"]
    assert row["delivered_at"] is not None, (
        "delivered_at stays set - it means this worker took its one shot, which is what "
        "keeps a retried RQ job from sending twice"
    )
    error = db.execute(text(
        "SELECT error FROM user_downloads WHERE id = :id"
    ), {"id": dl_id}).scalar() or ""
    assert error.startswith("chat push failed: attachment_window_closed"), repr(error)

    logs = _integration_logs_for(db, dl_id)
    assert len(logs) == 1, f"exactly one outbox row for the failed push: {logs}"
    assert logs[0]["error_message"], f"the outbox row must carry the reason: {logs[0]}"


def test_a_successful_push_leaves_no_error_on_the_row(scm_app, monkeypatch):
    """The other half: the failure recording must not fire on the happy path, or every
    delivered report would look broken."""
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, _key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for",
                        lambda db_, **kw: {"status": "sent"})

    run_id, dl_id = _seed_claimed_download(db, contact, claimed=True)
    task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

    error = db.execute(text(
        "SELECT error FROM user_downloads WHERE id = :id"
    ), {"id": dl_id}).scalar()
    assert not error, f"a delivered push must leave no error: {error!r}"


# =========================================================================== #
# Reviewer round 5, items 1 and 5. CODER-AUTHORED.
#
# 1: with the wait capped at 7 s a whole-book ask nearly always answers `pending` and
#    claims delivery. If the render THEN fails, `_record_failure` marks the row failed and
#    the push is never reached - the contact was told "it will be sent here when ready" and
#    never hears otherwise. The task now sends one text line through the same one-shot claim.
# 5: `send_chat_attachment_for` writes its own outbox row before raising
#    `respond_send_failed` (502), so logging again there would double-count one send. Only
#    the refusals raised BEFORE that logging (the 24 h window) are logged here.
# =========================================================================== #

def test_a_claimed_row_whose_render_fails_tells_the_contact(monkeypatch):
    """Item 1: the promise is kept or retracted, never left hanging.

    `_savepoint_session` rather than `scm_app`, for the reason the tester's own
    render-failure test records: `_record_failure` calls `db.rollback()` first, which
    against `scm_app` cascades past every nested savepoint and takes the seeded chain with
    it - the claim would then match no row and prove nothing.
    """
    from app.services import respond_chat_template_service
    from app.services.scm import low_stock_report_service

    export_tasks, task_fn = _task()

    with _savepoint_session() as db:
        contact = _contact(db)
        db.flush()
        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

        def _boom(db_, *, run_id, include_supplier=True):
            raise RuntimeError("render exploded")

        monkeypatch.setattr(low_stock_report_service, "export_low_stock", _boom)

        sends: list[dict] = []
        monkeypatch.setattr(respond_chat_template_service, "send_chat_message_for",
                            lambda db_, **kw: sends.append(kw) or {"status": "sent"})

        run_id, dl_id = _seed_claimed_download(db, contact, claimed=True)
        result = task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

        assert result["status"] == "failed", result
        row = _download_row(db, dl_id)
        assert row["status"] == "failed", row["status"]
        assert row["delivered_at"] is not None, (
            "the notice takes the same one-shot claim, so a retried job cannot send twice"
        )
        assert len(sends) == 1, f"exactly one notice: {sends}"
        assert sends[0]["text"] == (
            "Could not build the low stock report - ask again in a minute."
        ), sends[0]
        assert sends[0]["identifier"] == contact.respond_io_id, sends[0]

        # A retry of the same poisoned job must not apologise twice.
        task_fn(dl_id, run_id, str(row["user_id"]))
        assert len(sends) == 1, f"a retried job sent the notice again: {sends}"


def test_an_unclaimed_row_whose_render_fails_tells_nobody(monkeypatch):
    """Item 1's other half: a plan-view export has nobody waiting on WhatsApp, so a render
    failure there must not message a contact at all."""
    from app.services import respond_chat_template_service
    from app.services.scm import low_stock_report_service

    export_tasks, task_fn = _task()

    with _savepoint_session() as db:
        contact = _contact(db)
        db.flush()
        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

        def _boom(db_, *, run_id, include_supplier=True):
            raise RuntimeError("render exploded")

        monkeypatch.setattr(low_stock_report_service, "export_low_stock", _boom)

        sends: list[dict] = []
        monkeypatch.setattr(respond_chat_template_service, "send_chat_message_for",
                            lambda db_, **kw: sends.append(kw) or {"status": "sent"})

        run_id, dl_id = _seed_claimed_download(db, contact, claimed=False)
        task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

        assert sends == [], f"nobody was waiting; nothing may be sent: {sends}"


def test_a_502_push_failure_is_not_logged_twice(scm_app, monkeypatch):
    """Item 5: `respond_send_failed` is raised AFTER `send_chat_attachment_for` has already
    written its outbox row, so this module must not write a second one - one send, one
    outbox row. The reason still goes on the download row."""
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, _key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    def _send_failed(db_, **kw):
        raise AppException(status_code=502, message="Respond.io send failed.",
                           code="respond_send_failed")

    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for",
                        _send_failed)

    run_id, dl_id = _seed_claimed_download(db, contact, claimed=True)
    result = task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

    assert result["status"] == "ready", result
    error = db.execute(text(
        "SELECT error FROM user_downloads WHERE id = :id"
    ), {"id": dl_id}).scalar() or ""
    assert error.startswith("chat push failed: respond_send_failed"), repr(error)
    assert _integration_logs_for(db, dl_id) == [], (
        "the sender already logged this one - a second row would double-count the send"
    )


# =========================================================================== #
# Phase 3 security re-pass, 14 Sep 2026. CODER-AUTHORED.
#
# SF-2: `GET /api/v1/integrations/logs/` serves `request_payload` to any authenticated
#       user with no permission slug (pre-existing, filed separately), and on R2 the
#       workbook URL is unauthenticated and never expires. The outbox row this module
#       writes therefore carries the storage KEY, never the URL.
# N-b:  when a contact maps to SEVERAL companies, the owner's grants are intersected with
#       the contact's own. An empty intersection is a refusal - a contact must never be
#       sent a company book they are not a member of.
# =========================================================================== #

def test_a_refused_push_logs_the_key_not_the_url(scm_app, monkeypatch):
    """SF-2: the reason is still in the outbox, the link is not."""
    from app.services import respond_chat_template_service

    export_tasks, task_fn = _task()
    app, db, _key, _uid = _api_key_caller(scm_app)
    contact = _contact(db)
    db.flush()
    _patch_task_render(monkeypatch, export_tasks)
    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    def _closed(db_, **kw):
        raise AppException(
            status_code=422,
            message="Cannot send an attachment outside the 24h messaging window.",
            code="attachment_window_closed",
        )

    monkeypatch.setattr(respond_chat_template_service, "send_chat_attachment_for", _closed)

    run_id, dl_id = _seed_claimed_download(db, contact, claimed=True)
    task_fn(dl_id, run_id, str(_download_row(db, dl_id)["user_id"]))

    payloads = [str(r) for r in db.execute(text(
        "SELECT request_payload::text FROM integration_log "
        "WHERE business_table = 'user_downloads' AND business_id = :id"
    ), {"id": dl_id}).scalars().all()]
    assert payloads, "the refusal must still leave an outbox row"
    for payload in payloads:
        assert "http" not in payload.lower(), (
            f"the outbox must not carry a fetchable workbook URL: {payload}"
        )
        assert "exports/low-stock/" in payload, (
            f"it must still carry the storage key an operator needs: {payload}"
        )


def _company(db, code_stem: str) -> str:
    from app.models.company import Company

    company_id = _u()
    db.add(Company(id=company_id, name=f"{MARKER} {code_stem}",
                   code=f"{MARKER[:4]}{code_stem}{uuid.uuid4().hex[:4]}", is_active=True))
    db.flush()
    return company_id


def test_a_contact_in_two_companies_never_gets_a_company_it_is_not_in(scm_app, monkeypatch):
    """N-b: the contact belongs to two companies, the act-as principal is granted a THIRD.

    Before the intersection, the owner's lone grant won and the run was stamped with a
    company the contact is not a member of - whose stock, suppliers and dealer outstanding
    would then have been sent to their phone. The intersection is empty here, so the turn
    refuses and writes nothing.
    """
    from app.models.company import UserCompany
    from app.services.company_scope_resolver import apply_company_scope

    app, db, key, act_as_id = _api_key_caller(scm_app)
    app.dependency_overrides.pop(apply_company_scope, None)

    contact = _contact(db)
    _contact_company(db, contact, company_id=_company(db, "A"))
    _contact_company(db, contact, company_id=_company(db, "B"))
    owners_own = _company(db, "C")
    db.add(UserCompany(id=_u(), user_id=act_as_id, company_id=owners_own))
    db.flush()

    runs_before, downloads_before = _counts(db)
    _fake_queue(monkeypatch)
    _patch_wait(monkeypatch, on_wait=_timeout)

    with TestClient(app) as c:
        resp = c.get(ROUTE, headers={"X-API-Key": key}, params=_params(contact))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "error", (
        f"no company both sides may see is an error, never a plan: {body}"
    )
    assert _counts(db) == (runs_before, downloads_before), (
        "nothing may be written when the company cannot be resolved"
    )
