"""The report routes and saved views (AC-A1, A3, A7, A8, C3, C4).

The report under test is the SYNTHETIC one from tests/_report_fixture.py, registered by
this file and unregistered afterwards - the sponsorship report lands in S3 and must not be
what proves the kernel.

Two things here are worth more than the rest:

- **Every documented field is asserted on the JSON.** `response_model` drops what it does
  not declare, silently, and the screen then renders a blank where a total should be.
- **Mine vs Shared.** Mine is what the caller OWNS, published ones included (the menu badges
  those); Shared is OTHER people's published views. A published view vanishing from its
  author's own list is how someone loses the view they just made.

Run: pytest tests/test_report_routes.py -q
"""
from __future__ import annotations

import uuid

import pytest

from tests import _report_fixture as fixture
from tests._pg_fixture import blank_session

KEY = "zzt_orders"
BASE = f"/api/v1/reports/{KEY}"
REPORT_PERMISSION = "zzt.reports.orders"
PUBLISH_PERMISSION = "reports.views.publish"

_ME = {"id": str(uuid.uuid4()), "email": "report-caller@zzt.test", "name": "Report Caller"}
_OTHER_ID = str(uuid.uuid4())


def _seed_user(db, user_id: str, email: str, name: str) -> None:
    from app.models.user import User

    db.add(User(id=user_id, email=email, name=name, status="ACTIVE"))
    db.flush()


@pytest.fixture
def db():
    with blank_session() as session:
        fixture.create_table(session)
        _seed_user(session, _ME["id"], _ME["email"], _ME["name"])
        _seed_user(session, _OTHER_ID, "other@zzt.test", "Other Person")
        yield session


@pytest.fixture
def registered():
    from app.services.reports import registry as reg

    definition = reg.register(fixture.definition())
    try:
        yield definition
    finally:
        reg._REGISTRY.pop(KEY, None)


@pytest.fixture
def api(db, registered, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow = {REPORT_PERMISSION}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _ME
    # The module guard resolves its principal through this one; without the override every
    # request 401s before the permission gate under test is reached.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _ME
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)


def _config(**overrides) -> dict:
    config = {
        "params": {
            "date_basis": "booked_on",
            "period": {"kind": "year", "year": 2026},
            "agent": [],
            "region": ["North", "South"],
        },
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "agent", "cols": "month", "measures": ["amount", "fee"]},
    }
    config.update(overrides)
    return config


def _run_body(**overrides) -> dict:
    config = _config()
    body = {"params": config["params"], "view": config}
    body.update(overrides)
    return body


def _create_view(client, name="Mine", config=None):
    return client.post(f"{BASE}/views", json={"name": name, "view": config or _config()})


# --------------------------------------------------------------------- AC-A1 catalog


def test_the_catalog_lists_a_report_the_caller_may_see(api):
    client, _allow = api
    resp = client.get("/api/v1/reports")
    assert resp.status_code == 200, resp.text
    entry = next(r for r in resp.json()["reports"] if r["key"] == KEY)
    assert entry == {"key": KEY, "title": "Scratch orders", "permission": REPORT_PERMISSION}


def test_the_catalog_hides_a_report_the_caller_may_not_see(api):
    client, allow = api
    allow.clear()
    resp = client.get("/api/v1/reports")
    assert resp.status_code == 200
    assert [r for r in resp.json()["reports"] if r["key"] == KEY] == []


def test_meta_is_403_without_the_report_permission(api):
    client, allow = api
    allow.clear()
    assert client.get(BASE).status_code == 403


def test_meta_is_404_for_an_unknown_key(api):
    client, _allow = api
    assert client.get("/api/v1/reports/zzt_no_such_report").status_code == 404


# ------------------------------------------------------------------------ AC-A1 meta


def test_meta_declares_every_field_the_screen_reads(api):
    client, _allow = api
    meta = client.get(BASE).json()

    assert meta["key"] == KEY
    assert meta["title"] == "Scratch orders"
    assert meta["permission"] == REPORT_PERMISSION
    assert meta["can_publish"] is False  # the publish grant is not in `allow`

    kinds = {p["kind"]: p for p in meta["params"]}
    assert kinds["date_basis"]["default"] == "booked_on"
    assert {o["value"] for o in kinds["date_basis"]["options"]} == {"booked_on", "shipped_on"}
    assert kinds["period"]["default"] == {"kind": "year", "year": 2026}
    assert isinstance(kinds["period"]["years"], list)
    agent = next(p for p in meta["params"] if p.get("key") == "agent")
    assert agent["multi"] is True and agent["clearable"] is True
    assert agent["default"] == []
    assert {o["value"] for o in agent["options"]} == {"Alice", "Bob", "Carol"}

    catalog = {c["key"]: c for c in meta["catalog"]}
    assert catalog["amount"]["tag"] == "measure"
    assert catalog["amount"]["type"] == "money"
    assert catalog["agent"]["size"] == 140
    assert meta["default_view"]["pivot"] == {
        "rows": "agent",
        "cols": "month",
        "measures": ["amount", "fee"],
    }


def test_can_publish_is_true_for_a_holder_of_the_publish_permission(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    assert client.get(BASE).json()["can_publish"] is True


# ------------------------------------------------------------------------- AC-A3 run


def test_run_returns_every_field_the_screen_reads(api):
    client, _allow = api
    resp = client.post(f"{BASE}/run", json=_run_body())
    assert resp.status_code == 200, resp.text
    result = resp.json()

    assert result["key"] == KEY
    assert result["period_label"] == "Jan'26 to Dec'26"
    assert result["row_count"] == 5

    detail = result["layouts"]["detail"]
    assert detail["key"] == "detail"
    assert detail["title"] == "Orders"
    assert {"key", "label", "type", "size"} <= set(detail["columns"][0])
    group = detail["column_groups"][0]
    assert group["source"] == "delivery_year"
    assert group["label"] == "Delivery year"
    assert group["keys"]
    assert detail["totals"]["amount"] == "1750.24"
    assert detail["rows"][0]["order_no"] == "Z-001"

    summary = result["layouts"]["summary"]
    assert summary["key"] == "summary"
    assert summary["row_dim"] == {"key": "agent", "label": "Agent"}
    assert summary["col_dim"]["value_labels"]["2026-01"] == "Jan'26"
    assert summary["col_dim"]["values"][0] == "2026-01"
    assert summary["row_values"] == ["Alice", "Bob"]
    assert summary["cells"]["Alice"]["2026-01"]["amount"] == "1250.25"
    assert summary["row_totals"]["Alice"]["amount"] == "1650.25"
    assert summary["col_totals"]["2026-03"]["fee"] == "25.00"
    assert summary["grand_total"]["amount"] == "1750.24"
    assert [m["key"] for m in summary["measures"]] == ["amount", "fee"]


def test_run_without_a_view_falls_back_to_the_report_default(api):
    client, _allow = api
    resp = client.post(f"{BASE}/run", json={"params": _config()["params"], "view": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["layouts"]["summary"]["row_dim"]["key"] == "agent"


def test_a_run_with_no_top_level_params_falls_back_to_the_views_own(api):
    """A saved view carries the params it was saved with. A body that sends only the view
    used to run on the DEFINITION's defaults, so applying a saved view silently changed the
    period back."""
    client, _allow = api
    view = _config(
        params={
            "date_basis": "booked_on",
            "period": {"kind": "year", "year": 2025},
            "agent": [],
            "region": ["North", "South"],
        }
    )
    resp = client.post(f"{BASE}/run", json={"params": {}, "view": view})

    assert resp.status_code == 200, resp.text
    assert resp.json()["period_label"] == "Jan'25 to Dec'25"
    assert resp.json()["row_count"] == 1  # Z-006, the 2025 order


def test_top_level_params_win_over_the_views_own(api):
    """The filter bar is live: what is on screen beats what the view was saved with."""
    client, _allow = api
    view = _config(
        params={
            "date_basis": "booked_on",
            "period": {"kind": "year", "year": 2025},
            "agent": [],
            "region": ["North", "South"],
        }
    )
    body = {"params": _config()["params"], "view": view}

    assert client.post(f"{BASE}/run", json=body).json()["period_label"] == "Jan'26 to Dec'26"


def test_run_is_403_without_the_report_permission(api):
    client, allow = api
    allow.clear()
    assert client.post(f"{BASE}/run", json=_run_body()).status_code == 403


def test_run_names_the_unknown_param(api):
    client, _allow = api
    body = _run_body()
    body["params"]["salesperson"] = ["Alice"]
    resp = client.post(f"{BASE}/run", json=body)
    assert resp.status_code == 422
    assert "salesperson" in resp.json()["message"]


def test_run_over_the_cap_answers_422_capped(api, monkeypatch):
    from app.services.reports import engine

    monkeypatch.setattr(engine, "DETAIL_ROW_CAP", 2)
    client, _allow = api
    resp = client.post(f"{BASE}/run", json=_run_body())
    assert resp.status_code == 422
    # The AppException handler serialises the envelope FLAT, so the flag is top level.
    assert resp.json()["capped"] is True
    assert "export" in resp.json()["message"].lower()


# ---------------------------------------------------------------------- AC-A8 export


def test_export_creates_a_download_row_and_queues_the_render(api, db, monkeypatch):
    from app.models.download import UserDownload
    from app.services import queue_service

    queued = {}

    def _fake_enqueue(func, *args, **kwargs):
        queued["func"] = func
        queued["args"] = args
        queued["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    client, _allow = api
    resp = client.post(f"{BASE}/export", json=_run_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "Scratch orders-2026.xlsx"

    row = db.query(UserDownload).filter(UserDownload.id == body["download_id"]).first()
    assert row is not None
    assert row.kind == "report_xlsx"
    assert row.user_id == _ME["id"]
    assert row.filename == body["filename"]

    assert queued["func"].__name__ == "generate_report_xlsx"
    # The SHIPPED default is the production queue; the live value is whatever this
    # checkout's .env says, and a lane running its own worker sets its own (the test
    # below). Asserting the literal here failed on the very worktree the knob exists for.
    from app.config import Settings, settings

    assert Settings.model_fields["report_export_queue"].default == "imports"
    assert queued["kwargs"]["queue_name"] == settings.report_export_queue
    assert queued["args"][0] == body["download_id"]
    assert queued["args"][1] == KEY


def test_export_goes_on_the_queue_the_settings_name(api, monkeypatch):
    """A lane can run its own worker on a private queue without touching production.

    The default IS "imports" (asserted above), which is the queue the deployed worker
    drains. `REPORT_EXPORT_QUEUE` exists so a developer verifying an export in a worktree
    does not have a sibling checkout's worker steal the job and render it against its own
    code - RQ workers are shared across worktrees on this machine.
    """
    from app.config import settings
    from app.services import queue_service

    queued = {}
    monkeypatch.setattr(
        queue_service, "enqueue_job", lambda func, *a, **kw: queued.update(kw) or object()
    )
    monkeypatch.setattr(settings, "report_export_queue", "zzt_reports_lane")

    client, _allow = api
    assert client.post(f"{BASE}/export", json=_run_body()).status_code == 200
    assert queued["queue_name"] == "zzt_reports_lane"


def test_export_refuses_an_unknown_detail_column_at_the_button(api, db):
    """A bad view used to reach the worker: the user pressed Export, got a download row,
    and it failed a minute later in a drawer. The 422 belongs at the button."""
    from app.models.download import UserDownload

    client, _allow = api
    body = _run_body(view=_config(detail={"columns": ["no_such_column"], "order": []}))
    resp = client.post(f"{BASE}/export", json=body)
    assert resp.status_code == 422, resp.text
    assert "no_such_column" in resp.json()["message"]
    assert db.query(UserDownload).count() == 0


def test_export_refuses_an_unknown_pivot_measure(api, db):
    from app.models.download import UserDownload

    client, _allow = api
    body = _run_body(
        view=_config(pivot={"rows": "agent", "cols": "month", "measures": ["no_such_measure"]})
    )
    resp = client.post(f"{BASE}/export", json=body)
    assert resp.status_code == 422, resp.text
    assert "no_such_measure" in resp.json()["message"]
    assert db.query(UserDownload).count() == 0


def test_export_refuses_a_pivot_grouped_by_a_measure(api):
    client, _allow = api
    body = _run_body(
        view=_config(pivot={"rows": "amount", "cols": "month", "measures": ["amount"]})
    )
    resp = client.post(f"{BASE}/export", json=body)
    assert resp.status_code == 422, resp.text
    assert "amount" in resp.json()["message"]


def test_export_is_403_without_the_report_permission(api):
    client, allow = api
    allow.clear()
    assert client.post(f"{BASE}/export", json=_run_body()).status_code == 403


# ----------------------------------------------------------------------- AC-C3 views


def test_a_saved_view_comes_back_under_mine(api):
    client, _allow = api
    created = _create_view(client, "My pipeline")
    assert created.status_code == 200, created.text
    view = created.json()
    assert view["is_shared"] is False
    assert view["is_default"] is False
    assert view["owner_name"] == "Report Caller"
    assert view["view"]["pivot"]["rows"] == "agent"

    listed = client.get(f"{BASE}/views").json()
    assert [v["name"] for v in listed["mine"]] == ["My pipeline"]
    assert listed["shared"] == []


def test_a_second_view_with_the_same_name_is_refused(api):
    client, _allow = api
    _create_view(client, "Same name")
    again = _create_view(client, "Same name")
    assert again.status_code == 409
    assert "Same name" in again.json()["message"]


def test_another_users_personal_view_is_invisible(api, db):
    client, _allow = api
    _seed_other_view(db, name="Private to them", is_shared=False)
    listed = client.get(f"{BASE}/views").json()
    assert listed["mine"] == []
    assert listed["shared"] == []


def test_another_users_published_view_is_shared_not_mine(api, db):
    client, _allow = api
    _seed_other_view(db, name="Management default", is_shared=True)
    listed = client.get(f"{BASE}/views").json()
    assert listed["mine"] == []
    assert [v["name"] for v in listed["shared"]] == ["Management default"]
    assert listed["shared"][0]["owner_name"] == "Other Person"


def test_my_own_published_view_stays_under_mine(api):
    """Publishing must not take a view out of its author's own list (captain, S2)."""
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "Shared by me").json()["id"]

    published = client.post(f"{BASE}/views/{view_id}/publish", json={"is_shared": True})
    assert published.status_code == 200, published.text
    assert published.json()["is_shared"] is True

    listed = client.get(f"{BASE}/views").json()
    assert [v["name"] for v in listed["mine"]] == ["Shared by me"]
    assert listed["mine"][0]["is_shared"] is True
    assert listed["shared"] == []


def test_a_view_is_hard_deleted(api):
    client, _allow = api
    view_id = _create_view(client, "Temporary").json()["id"]
    assert client.delete(f"{BASE}/views/{view_id}").status_code == 204
    assert client.get(f"{BASE}/views").json()["mine"] == []


def test_another_users_view_cannot_be_deleted(api, db):
    client, _allow = api
    other = _seed_other_view(db, name="Theirs", is_shared=True)
    assert client.delete(f"{BASE}/views/{other}").status_code == 404


# ------------------------------------------------------------- AC-C4 publish/default


def test_publish_is_403_without_the_publish_permission(api):
    client, _allow = api
    view_id = _create_view(client, "Not shareable").json()["id"]
    resp = client.post(f"{BASE}/views/{view_id}/publish", json={"is_shared": True})
    assert resp.status_code == 403
    assert PUBLISH_PERMISSION in resp.json()["message"]


def test_set_default_is_403_without_the_publish_permission(api):
    client, _allow = api
    view_id = _create_view(client, "Not defaultable").json()["id"]
    assert client.post(f"{BASE}/views/{view_id}/set-default").status_code == 403


def test_at_most_one_view_is_the_default_for_a_report(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    first = _create_view(client, "First").json()["id"]
    second = _create_view(client, "Second").json()["id"]

    client.post(f"{BASE}/views/{first}/set-default")
    resp = client.post(f"{BASE}/views/{second}/set-default")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True
    assert resp.json()["is_shared"] is True  # the default is shared by definition

    listed = client.get(f"{BASE}/views").json()
    defaults = [v["name"] for v in listed["mine"] + listed["shared"] if v["is_default"]]
    assert defaults == ["Second"]


def test_another_users_private_view_cannot_be_made_the_default(api, db):
    """Set as default used to publish whatever id it was handed, so a holder of the publish
    grant could expose somebody else's PRIVATE view to everyone by id alone."""
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    other = _seed_other_view(db, name="Private to them", is_shared=False)

    resp = client.post(f"{BASE}/views/{other}/set-default")
    assert resp.status_code == 409, resp.text
    assert "shared" in resp.json()["message"].lower()

    # Still private, still nobody's default.
    listed = client.get(f"{BASE}/views").json()
    assert listed["mine"] == []
    assert listed["shared"] == []
    assert client.get(BASE).json()["default_view"]["pivot"]["rows"] == "agent"


def test_another_users_shared_view_can_be_made_the_default(api, db):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    other = _seed_other_view(db, name="Theirs, published", is_shared=True)

    resp = client.post(f"{BASE}/views/{other}/set-default")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True


def test_the_owner_may_publish_and_default_a_view_in_one_step(api):
    """The screen's own flow: Set as default on a view you own shares it as it defaults it."""
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "Mine to share").json()["id"]

    resp = client.post(f"{BASE}/views/{view_id}/set-default")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_shared"] is True
    assert resp.json()["is_default"] is True


def test_the_shared_default_becomes_the_reports_default_view(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    config = _config(pivot={"rows": "region", "cols": "month", "measures": ["fee"]})
    view_id = _create_view(client, "House view", config).json()["id"]
    client.post(f"{BASE}/views/{view_id}/set-default")

    meta = client.get(BASE).json()
    assert meta["default_view"]["pivot"]["rows"] == "region"


def test_unpublishing_the_default_clears_the_default(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "House view").json()["id"]
    client.post(f"{BASE}/views/{view_id}/set-default")

    resp = client.post(f"{BASE}/views/{view_id}/publish", json={"is_shared": False})
    assert resp.json()["is_default"] is False
    assert client.get(BASE).json()["default_view"]["pivot"]["rows"] == "agent"


def test_views_are_403_without_the_report_permission(api):
    client, allow = api
    allow.clear()
    assert client.get(f"{BASE}/views").status_code == 403
    assert _create_view(client, "Nope").status_code == 403


def test_a_view_for_an_unknown_report_is_404(api):
    client, _allow = api
    assert client.get("/api/v1/reports/zzt_no_such_report/views").status_code == 404


def _seed_other_view(db, *, name: str, is_shared: bool) -> str:
    from app.models.report_view import ReportView

    row = ReportView(
        report_key=KEY,
        owner_user_id=_OTHER_ID,
        name=name,
        view=_config(),
        is_shared=is_shared,
    )
    db.add(row)
    db.flush()
    return str(row.id)
