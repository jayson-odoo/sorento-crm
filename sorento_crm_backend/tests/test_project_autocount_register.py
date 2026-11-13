"""AC-PROJECT-REGISTER Phase 2, RED: register a CRM project in AutoCount.

UAC: `documentation/plans/autocount/ac-project-register-acceptance-criteria.md` (R1-R15 here; the
screen rules R16-R18 are in the vitest file beside `ProjectDetailClient.tsx`).
Plan: `documentation/plans/autocount/PLAN-ac-project-register-13nov.md`, "Design".

    GET  /api/v1/project-sales/{project_id}/autocount-register   (status)
    POST /api/v1/project-sales/{project_id}/autocount-register   (register, no body)

Guard order: permission `projects.autocount.write` -> switch (403 `ac_register_switched_off`, the
Shared Service is never touched) -> project (404) -> write access -> eligibility (409
`ac_not_eligible`) -> SS. The SS is the `FakeSS` transport from `tests/_ac_write_support.py`.

Postgres only; every chain is seeded here (CI's database is empty).
"""
from __future__ import annotations

import json
import re
import uuid

import httpx
import pytest

from tests._ac_write_support import (
    BASE,
    BOOK,
    CAPS_PATH,
    EDIT,
    PROJECTS_CREATE_PATH,
    REGISTER_OFF_CODE,
    REGISTER_SWITCH,
    UNREACHABLE_TEXT,
    VIEW,
    WAITING,
    WRITE,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    offer_projects,
    refused_body,
    register_api_fixture,
    set_register_switch,
)
from tests._pg_fixture import blank_session
from tests.test_project_so_draft import _user

SETTINGS = "/api/v1/user-management/settings/"
APP_CONFIG = "/api/v1/user-management/settings/app-config"
PERMS = [VIEW, EDIT, WRITE]
HEX32 = re.compile(r"[0-9a-f]{32}")
NOT_ELIGIBLE = "Only an approved project that is not lost can be registered in AutoCount."
STATUS_KEYS = ("registered", "project_no", "registered_at", "eligible", "can_register", "reason")
DONE_PREFIX = "Registered in AutoCount as "
NOT_DONE_PREFIX = "AutoCount registration not completed: "


def _url(project_id) -> str:
    return f"{BASE}/{project_id}/autocount-register"


def _status(body: dict) -> dict:
    missing = [k for k in STATUS_KEYS if k not in body]
    assert not missing, f"status answer lacks {missing}: {body}"
    return {k: body[k] for k in STATUS_KEYS}


def _activity(db, project) -> list[str]:
    from app.models.activities import ActivityEvent

    rows = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.entity_type == "project", ActivityEvent.entity_id == str(project.id))
        .all()
    )
    return [
        r.body_text
        for r in rows
        if r.body_text and (r.body_text.startswith(DONE_PREFIX) or r.body_text.startswith(NOT_DONE_PREFIX))
    ]


def _audit(db):
    from app.models.audit import AuditLog

    return db.query(AuditLog).filter(AuditLog.event == "autocount_write").all()


@pytest.fixture
def api(fake_ss):
    yield from register_api_fixture(PERMS, switch=True)


@pytest.fixture
def api_off(fake_ss):
    yield from register_api_fixture(PERMS, switch=False)


@pytest.fixture
def api_no_perm(fake_ss):
    yield from register_api_fixture([VIEW, EDIT], switch=True)


# =========================================================================== R1: the switch


def test_r1_the_register_switch_defaults_off_on_a_fresh_settings_row():
    from app.models.user import SystemSetting

    with blank_session() as db:
        row = SystemSetting(id=str(uuid.uuid4()), name="ZZT Co")
        db.add(row)
        db.flush()
        db.refresh(row)

        assert getattr(row, REGISTER_SWITCH) is False


@pytest.fixture
def settings_api(monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    caller = {"id": str(uuid.uuid4()), "email": "acreg-settings@zzt.test"}
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    with blank_session() as db:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: caller
        try:
            set_register_switch(db, False)
            db.commit()
            yield TestClient(app), db
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


def test_r1_the_switch_rides_the_admin_get_put_and_app_config(settings_api):
    client, _db = settings_api
    from app.api.v1.user_management.settings import SystemSettingUpdate

    assert REGISTER_SWITCH in SystemSettingUpdate.model_fields
    assert client.get(SETTINGS).json()["settings"][REGISTER_SWITCH] is False
    assert client.get(APP_CONFIG).json()[REGISTER_SWITCH] is False

    put = client.put(SETTINGS + "general", json={REGISTER_SWITCH: True})
    assert put.status_code == 200, put.text

    assert client.get(SETTINGS).json()["settings"][REGISTER_SWITCH] is True
    assert client.get(APP_CONFIG).json()[REGISTER_SWITCH] is True


def test_r1_a_null_on_put_stores_false(settings_api):
    client, _db = settings_api
    assert client.put(SETTINGS + "general", json={REGISTER_SWITCH: True}).status_code == 200

    put = client.put(SETTINGS + "general", json={REGISTER_SWITCH: None})

    assert put.status_code == 200, put.text
    assert client.get(SETTINGS).json()["settings"][REGISTER_SWITCH] is False


# =========================================================================== R2 / R3 / R4: guards


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_r2_switch_off_answers_403_and_the_ss_sees_zero_requests(api_off, fake_ss, method):
    client, _db, world = api_off
    offer_projects(fake_ss)

    response = client.request(method, _url(world.project.id))

    assert response.status_code == 403, response.text
    assert response.json()["code"] == REGISTER_OFF_CODE
    assert fake_ss.calls == [], "not even the capability read while the switch is off"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_r3_without_the_permission_both_routes_answer_403(api_no_perm, fake_ss, method):
    client, _db, world = api_no_perm
    offer_projects(fake_ss)

    response = client.request(method, _url(world.project.id))

    assert response.status_code == 403, response.text
    assert WRITE in response.text
    assert response.json().get("code") != REGISTER_OFF_CODE
    assert fake_ss.calls == []


def test_r3_a_user_without_write_access_to_the_project_is_refused_on_post(api, fake_ss):
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    client, db, world = api
    offer_projects(fake_ss)
    stranger = {"id": _user(db, "zzt-acreg stranger"), "role": "user"}
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: dict(stranger)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(stranger)

    response = client.post(_url(world.project.id))

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "project_not_editable"
    assert fake_ss.calls == []


def test_r4_unknown_malformed_and_foreign_ids(api, fake_ss):
    from app.models.base import company_scope
    from app.models.company import Company

    client, db, world = api
    offer_projects(fake_ss)

    absent = client.post(_url(uuid.uuid4()))
    assert absent.status_code == 404, absent.text
    assert absent.json()["code"] == "project_not_found"
    assert client.get(_url(uuid.uuid4())).json().get("code") == "project_not_found"

    malformed = client.post(_url("not-a-uuid"))
    assert malformed.status_code in (404, 422), malformed.text

    other = Company(
        id=str(uuid.uuid4()), name="ZZT Other", code=f"ZZT{uuid.uuid4().hex[:6]}".upper(), is_active=True
    )
    db.add(other)
    db.commit()
    with company_scope(db, frozenset({other.id})):
        foreign = client.post(_url(world.project.id))
    assert foreign.status_code == 404, foreign.text
    assert foreign.json()["code"] == absent.json()["code"]
    assert fake_ss.writes() == []


# =========================================================================== R5: eligibility


def test_r5_a_lost_project_is_not_eligible_and_ss_is_not_called(api, fake_ss):
    client, db, world = api
    offer_projects(fake_ss)
    world.project.outcome = "lost"
    db.commit()

    response = client.post(_url(world.project.id))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ac_not_eligible"
    assert response.json()["message"] == NOT_ELIGIBLE
    assert fake_ss.calls == []

    status = client.get(_url(world.project.id))
    assert status.status_code == 200, status.text
    got = _status(status.json())
    assert got["eligible"] is False and got["can_register"] is False and got["reason"] is None


def test_r5_a_project_awaiting_approval_is_refused_with_409_and_ss_is_not_called(api, fake_ss):
    """UAC R5 says `ac_not_eligible`; the shared write guard (`assert_can_write_project`, R3) answers
    `project_not_approved` first for the same project. Either 409 keeps the SS untouched."""
    from app.services.project_service import APPROVAL_PENDING

    client, db, world = api
    offer_projects(fake_ss)
    world.project.approval_state = APPROVAL_PENDING
    db.commit()

    response = client.post(_url(world.project.id))

    assert response.status_code == 409, response.text
    assert response.json()["code"] in ("ac_not_eligible", "project_not_approved")
    assert fake_ss.calls == []


# =========================================================================== R6 / R7: status read


def test_r6_status_of_an_eligible_project_when_ss_offers_projects_and_a_book(api, fake_ss):
    client, _db, world = api
    offer_projects(fake_ss)

    response = client.get(_url(world.project.id))

    assert response.status_code == 200, response.text
    assert _status(response.json()) == {
        "registered": False,
        "project_no": None,
        "registered_at": None,
        "eligible": True,
        "can_register": True,
        "reason": None,
    }
    assert fake_ss.writes() == [], "a status read sends no write"


def test_r6_no_book_named_means_waiting(api, fake_ss):
    client, _db, world = api
    offer_projects(fake_ss, book=None)

    got = _status(client.get(_url(world.project.id)).json())

    assert got["can_register"] is False
    assert got["reason"] == WAITING


def test_r6_an_unreachable_ss_is_said_plainly(api, fake_ss):
    client, _db, world = api
    fake_ss.transport_error = httpx.ConnectError("down")

    response = client.get(_url(world.project.id))

    assert response.status_code == 200, response.text
    got = _status(response.json())
    assert got["can_register"] is False
    assert got["reason"] == UNREACHABLE_TEXT


def test_r7_no_projects_capability_today_is_waiting_and_post_sends_nothing(api, fake_ss):
    """The UAT state: the SS feed has no `projects` entry at all (the default fake feed)."""
    client, _db, world = api

    got = _status(client.get(_url(world.project.id)).json())
    assert got["eligible"] is True
    assert got["can_register"] is False
    assert got["reason"] == WAITING

    pressed = client.post(_url(world.project.id))
    assert pressed.status_code == 200, pressed.text
    assert pressed.json()["outcome"] != "done"
    assert pressed.json()["message"] == WAITING
    assert fake_ss.writes() == []


# =========================================================================== R8: the body


@pytest.mark.parametrize(
    "location,address,desc2",
    [
        ("Jalan Ujian 7, Shah Alam " + "x" * 120, "Lot 4401", ("Jalan Ujian 7, Shah Alam " + "x" * 120)[:100]),
        (None, "Lot 4401, Mukim Ujian", "Lot 4401, Mukim Ujian"),
        (None, None, None),
    ],
    ids=["location", "address-fallback", "omitted"],
)
def test_r8_the_body_key_and_trace_headers(fake_ss, location, address, desc2):
    gen = register_api_fixture(PERMS, switch=True, location=location, address=address)
    client, _db, world = next(gen)
    try:
        offer_projects(fake_ss)
        fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, done_body(doc_no="PJ-0001", doc_key=555))

        response = client.post(_url(world.project.id))

        assert response.status_code == 200, response.text
        [sent] = fake_ss.to("POST", PROJECTS_CREATE_PATH)
        project = world.project
        expected = {"projNo": project.project_code, "description": project.title[:100], "isActive": True}
        if desc2 is not None:
            expected["desc2"] = desc2
        assert json.loads(sent.content) == {"companyCode": "SRT", "project": expected}
        assert sent.headers["Idempotency-Key"].startswith(f"crm-proj-{project.id}-create")
        assert HEX32.fullmatch(sent.headers.get("X-Request-ID") or ""), sent.headers
        assert sent.headers.get("X-Acting-User-Id") == world.owner
    finally:
        gen.close()


def test_r8_the_route_ignores_any_body_and_the_service_constant_names_the_path(api, fake_ss):
    from app.services.project_autocount_register_service import PROJECTS_PATH

    assert PROJECTS_PATH == "documents/projects"
    client, _db, world = api
    offer_projects(fake_ss)
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, done_body(doc_no="PJ-0001", doc_key=555))

    client.post(_url(world.project.id), json={"companyCode": "EVIL", "project": {"projNo": "X"}})

    [sent] = fake_ss.to("POST", PROJECTS_CREATE_PATH)
    body = json.loads(sent.content)
    assert body["companyCode"] == "SRT"
    assert body["project"]["projNo"] == world.project.project_code


# =========================================================================== R9: waiting, no write


def test_r9_no_book_or_unreachable_answers_200_not_done_and_sends_no_write(api, fake_ss):
    client, _db, world = api
    offer_projects(fake_ss, book=None)

    waiting = client.post(_url(world.project.id))
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["outcome"] != "done"
    assert waiting.json()["message"] == WAITING

    fake_ss.transport_error = httpx.ConnectError("down")
    down = client.post(_url(world.project.id))
    assert down.status_code == 200, down.text
    assert down.json()["outcome"] != "done"
    assert down.json()["message"] == UNREACHABLE_TEXT

    assert fake_ss.to("POST", PROJECTS_CREATE_PATH) == []


# =========================================================================== R10 / R13 / R14: done


def test_r10_r14_done_stores_the_number_and_logs_audit_and_activity(api, fake_ss):
    client, db, world = api
    offer_projects(fake_ss)
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, done_body(doc_no="PJ-0001", doc_key=555))

    response = client.post(_url(world.project.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "done"
    assert body["message"] == "PJ-0001 registered in AutoCount"
    assert body["doc_no"] == "PJ-0001"

    db.refresh(world.project)
    project = world.project
    assert project.autocount_doc_no == "PJ-0001"
    assert project.autocount_doc_key == "555"
    assert project.autocount_book == BOOK
    assert project.autocount_registered_at is not None
    assert project.autocount_pending_create is None

    [sent] = fake_ss.to("POST", PROJECTS_CREATE_PATH)
    [row] = _audit(db)
    assert row.user_id == world.owner
    assert row.new_values["idempotency_key"] == sent.headers["Idempotency-Key"]
    assert row.new_values["outcome"] == "done"
    assert _activity(db, project) == ["Registered in AutoCount as PJ-0001"]

    detail = client.get(f"{BASE}/projects/{project.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["autocount_project_no"] == "PJ-0001"
    assert detail.json()["autocount_registered_at"]

    after = _status(client.get(_url(project.id)).json())
    assert after["registered"] is True
    assert after["project_no"] == "PJ-0001"
    assert after["registered_at"]
    assert after["can_register"] is False
    assert after["reason"] is None


@pytest.mark.parametrize(
    "answer_doc_no,document,doc_key,expect_no,expect_key",
    [
        (None, {"ProjNo": "AC-P9", "DocKey": 901}, None, "AC-P9", "901"),
        (None, {}, None, "<code>", "<code>"),
    ],
    ids=["document-projno", "sent-projno"],
)
def test_r10_the_number_falls_back_to_the_document_then_to_what_was_sent(
    api, fake_ss, answer_doc_no, document, doc_key, expect_no, expect_key
):
    client, db, world = api
    offer_projects(fake_ss)
    answer = done_body(doc_no="unused", doc_key=0)
    answer.update({"docNo": answer_doc_no, "docKey": doc_key, "document": document})
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, answer)

    body = client.post(_url(world.project.id)).json()

    code = world.project.project_code
    expect_no = code if expect_no == "<code>" else expect_no
    expect_key = code if expect_key == "<code>" else expect_key
    assert body["outcome"] == "done", body
    assert body["doc_no"] == expect_no
    db.refresh(world.project)
    assert world.project.autocount_doc_no == expect_no
    assert world.project.autocount_doc_key == expect_key


def test_r13_a_press_on_a_registered_project_sends_nothing(api, fake_ss):
    client, db, world = api
    offer_projects(fake_ss)
    world.project.autocount_doc_no = "PJ-0009"
    world.project.autocount_doc_key = "77"
    world.project.autocount_book = BOOK
    db.commit()

    response = client.post(_url(world.project.id))

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "done"
    assert response.json()["doc_no"] == "PJ-0009"
    assert response.json()["message"] == "PJ-0009 is already in AutoCount."
    assert fake_ss.calls == []


# =========================================================================== R11 / R12: retry rules


@pytest.mark.parametrize(
    "refusal",
    [
        (422, refused_body("FIELD_REQUIRED", "projNo is too long")),
        (502, refused_body("VENDOR_REFUSED", "project exists", outcome="vendor_error")),
    ],
    ids=["refused", "vendor-refused"],
)
def test_r11_a_refusal_releases_the_key_and_the_next_press_sends_the_current_body(api, fake_ss, refusal):
    client, db, world = api
    offer_projects(fake_ss)
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = refusal

    first = client.post(_url(world.project.id))
    assert first.status_code == 200, first.text
    assert first.json()["outcome"] == "refused"
    db.refresh(world.project)
    assert world.project.autocount_pending_create is None
    assert world.project.autocount_doc_no is None
    assert _activity(db, world.project) == [NOT_DONE_PREFIX + first.json()["message"]]

    world.project.title = f"{world.project.title[:40]} Fixed"
    db.commit()
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, done_body(doc_no="PJ-0002", doc_key=556))

    second = client.post(_url(world.project.id))

    assert second.json()["outcome"] == "done", second.json()
    one, two = fake_ss.to("POST", PROJECTS_CREATE_PATH)
    assert one.headers["Idempotency-Key"] != two.headers["Idempotency-Key"], "a refusal releases the key"
    assert json.loads(two.content)["project"]["description"] == world.project.title[:100]
    assert len(_audit(db)) == 2


def _timeout(_request):
    raise httpx.ReadTimeout("answer lost")


@pytest.mark.parametrize(
    "unknown",
    [
        _timeout,
        (500, {"code": "INTERNAL", "message": "boom"}),
        (202, {**done_body(doc_key=None, doc_no=None), "outcome": "pending_verification"}),
    ],
    ids=["timeout", "5xx", "pending_verification"],
)
def test_r12_an_unknown_outcome_keeps_the_key_and_the_next_press_resends_it(api, fake_ss, unknown):
    client, db, world = api
    offer_projects(fake_ss)
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = unknown

    first = client.post(_url(world.project.id))
    assert first.status_code == 200, first.text
    assert first.json()["outcome"] != "done"
    db.refresh(world.project)
    held = world.project.autocount_pending_create
    assert held and held["key"].startswith(f"crm-proj-{world.project.id}-create")

    # The project is edited meanwhile: the earlier press is still asked for exactly as sent.
    world.project.title = f"{world.project.title[:40]} Edited"
    db.commit()
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, done_body(doc_no="PJ-0003", doc_key=557))

    second = client.post(_url(world.project.id))

    assert second.json()["outcome"] == "done", second.json()
    one, two = fake_ss.to("POST", PROJECTS_CREATE_PATH)
    assert one.headers["Idempotency-Key"] == two.headers["Idempotency-Key"] == held["key"]
    assert json.loads(one.content) == json.loads(two.content)
    db.refresh(world.project)
    assert world.project.autocount_doc_no == "PJ-0003"
    assert world.project.autocount_pending_create is None

    third = client.post(_url(world.project.id))
    assert third.json()["message"] == "PJ-0003 is already in AutoCount."
    assert len(fake_ss.to("POST", PROJECTS_CREATE_PATH)) == 2, "nothing is created twice"
    # R14: both presses reached the SS, so each left one Activity row; the third sent nothing.
    assert sorted(_activity(db, world.project)) == sorted(
        [NOT_DONE_PREFIX + first.json()["message"], DONE_PREFIX + "PJ-0003"]
    )


# =========================================================================== R15: one-shot


def test_r15_editing_a_registered_project_sends_nothing_to_autocount(api, fake_ss):
    client, db, world = api
    offer_projects(fake_ss)
    fake_ss.answers[("POST", PROJECTS_CREATE_PATH)] = (200, done_body(doc_no="PJ-0004", doc_key=558))
    fields = ("title", "project_code", "outcome", "status_id", "approval_state", "owner_user_id")
    before = {f: getattr(world.project, f) for f in fields}
    assert client.post(_url(world.project.id)).json()["outcome"] == "done"
    calls = len(fake_ss.calls)
    db.refresh(world.project)
    assert {f: getattr(world.project, f) for f in fields} == before, "registering changes nothing else"

    edit = client.put(f"{BASE}/projects/{world.project.id}", json={"title": "ZZT renamed development"})

    assert edit.status_code == 200, edit.text
    assert len(fake_ss.calls) == calls, "an edit never reaches AutoCount (Q5)"
    db.refresh(world.project)
    assert world.project.autocount_doc_no == "PJ-0004"
