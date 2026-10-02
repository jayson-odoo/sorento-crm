"""Slice C1 red tests - the one-message ideation capture turn.

Contract: documentation/plans/ideation/PLAN-ideation-capture-02oct.md sections 2.1-2.4, 3, 4a.

``app.services.ideation_capture_service.handle_capture_turn`` replaces the multi-turn draft
flow: access gate (linked active CRM user holding ``ideation.board.view``), a held
similar-list pointer (pick a number / NEW / anything else), a fresh message
(extractor -> similar-own lookup -> one-shot create). Reply wording lives in
``ideation_capture_replies`` and is pending the owner, so these tests assert structure and
facts (status, links, titles, numbering, missing-field names), never whole sentences.

Real Postgres on the blank scratch schema; every test seeds its own workspace, contact,
user, role and permission. The three outside seams are patched as module attributes of
the new service: ``extract_ideate_turn``, ``call_similar_own``, ``call_create_idea``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import RespondContact
from app.models.respond_workspace import RespondWorkspace
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.ideation_extractor import IdeateExtraction
from app.services.ideation_turn_service import IdeationServiceError
from app.utils.field_encryption import encrypt_secret
from tests._pg_fixture import blank_session

CRM = "https://crm.example"
PERM = "ideation.board.view"

MSG = "i have an idea, the price tag should show promo price in red"
PROBLEM = "Customers keep asking why the price differs from the sticker"
TITLE = "Promo price in red on price tags"


def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso(delta: timedelta = timedelta(0)) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


# --------------------------------------------------------------------------- #
# Harness                                                                     #
# --------------------------------------------------------------------------- #
class Env:
    def __init__(self, db, svc, monkeypatch):
        self.db = db
        self.svc = svc
        self.mp = monkeypatch
        self.phone = f"+6012{uuid.uuid4().int % 10**8:08d}"
        self.rio = f"rio-{uuid.uuid4().hex[:10]}"
        self.contact: RespondContact | None = None
        self.user: User | None = None
        self.extractor_calls: list[str] = []
        self.similar_calls: list[dict] = []
        self.create_calls: list[dict] = []
        # message_text -> IdeateExtraction; unknown text -> no idea content
        self.extractions: dict[str, IdeateExtraction] = {}
        self.similar_result: dict | Exception = {"ideas": [], "total": 0}
        self.create_result: dict | Exception = {}

    # ---- seeding -------------------------------------------------------- #
    def seed_workspace(self, *, product_id: str | None = "prod-1") -> None:
        self.db.add(
            RespondWorkspace(
                id=_uid(),
                space_id="zzt-space",
                api_key_ciphertext=encrypt_secret("respond-key"),
                is_default=True,
                ideation_product_id=product_id,
                ideation_shared_service_url="https://ss.test",
                ideation_intake_api_key_ciphertext=encrypt_secret("intake-key"),
            )
        )
        self.db.flush()

    def seed_contact(self, session_vars: dict | None = None) -> RespondContact:
        self.contact = RespondContact(
            id=_uid(),
            phone_number=self.phone,
            name="Aisha Rahman",
            respond_io_id=self.rio,
            session_vars=session_vars or {},
        )
        self.db.add(self.contact)
        self.db.flush()
        return self.contact

    def seed_user(self, *, status: str = "ACTIVE", with_perm: bool = True, link: bool = True) -> User:
        user = User(
            id=_uid(),
            email=f"zzt-{uuid.uuid4().hex[:8]}@test.com",
            name="Aisha CRM",
            status=status,
            respond_contact_id=self.contact.id if link else None,
        )
        self.db.add(user)
        self.db.flush()
        if with_perm:
            role_id = _uid()
            self.db.add(
                UserRole(
                    id=role_id,
                    slug=f"zzt_{role_id[:8]}",
                    name=f"zzt_{role_id[:8]}",
                    description="",
                    is_protected=False,
                    is_default=False,
                )
            )
            self.db.flush()
            perm = self.db.query(UserPermission).filter(UserPermission.slug == PERM).first()
            if perm is None:
                perm = UserPermission(id=_uid(), slug=PERM, name=PERM, description="")
                self.db.add(perm)
                self.db.flush()
            self.db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
            self.db.add(UserRolePermission(id=_uid(), role_id=role_id, permission_id=perm.id))
            self.db.flush()
        self.user = user
        return user

    def ready(self, *, session_vars: dict | None = None) -> None:
        """Workspace + contact + active linked user holding the permission."""
        self.seed_workspace()
        self.seed_contact(session_vars)
        self.seed_user()

    # ---- scripting ------------------------------------------------------ #
    def extraction(self, text: str, *, fields: dict | None = None, title: str = "") -> None:
        self.extractions[text] = IdeateExtraction(fields=fields or {}, title=title)

    def idea_message(self, text: str = MSG, *, extra_fields: dict | None = None) -> str:
        fields = {"problem": PROBLEM, **(extra_fields or {})}
        self.extraction(text, fields=fields, title=TITLE)
        return text

    def created(self, *, idea_id: str | None = None, captured: dict | None = None) -> str:
        idea_id = idea_id or _uid()
        self.create_result = {
            "status": "complete",
            "id": idea_id,
            "idea_number": "IDEA-0184",
            "title": TITLE,
            "captured": captured if captured is not None else {"problem": PROBLEM},
        }
        return idea_id

    def sim(self, n: int, *, total: int | None = None) -> list[dict]:
        ideas = [
            {"id": _uid(), "idea_number": f"IDEA-01{i}0", "title": f"Existing idea number {i}"}
            for i in range(1, n + 1)
        ]
        self.similar_result = {"ideas": ideas, "total": total if total is not None else n}
        return ideas

    def pointer(self, similar: list[dict], *, message: str = MSG, age: timedelta = timedelta(0),
                is_test: bool = False) -> dict:
        return {
            "ideation": {
                "status": "similar_offered",
                "message_text": message,
                "similar": similar,
                "updated_at": _now_iso(age),
                "is_test": is_test,
            }
        }

    # ---- act ------------------------------------------------------------ #
    def turn(self, message: str, *, session_vars_in: dict | None = None, is_test: bool = False,
             submitter_name: str | None = None) -> dict:
        return self.svc.handle_capture_turn(
            self.db,
            respond_io_id=self.rio,
            message_text=message,
            submitter_name=submitter_name,
            session_vars_in=session_vars_in,
            is_test=is_test,
        )

    def persisted(self) -> dict:
        self.db.refresh(self.contact)
        return dict(self.contact.session_vars or {})


@pytest.fixture
def env(monkeypatch):
    import app.services.ideation_capture_service as svc

    with blank_session() as db:
        e = Env(db, svc, monkeypatch)

        def _extract(_db, **kw):  # noqa: ANN001
            text = kw["message_text"]
            e.extractor_calls.append(text)
            return e.extractions.get(text, IdeateExtraction())

        def _similar(base_url, api_key, payload):  # noqa: ANN001
            e.similar_calls.append(payload)
            if isinstance(e.similar_result, Exception):
                raise e.similar_result
            return e.similar_result

        def _create(base_url, api_key, payload):  # noqa: ANN001
            e.create_calls.append(payload)
            if isinstance(e.create_result, Exception):
                raise e.create_result
            return e.create_result

        monkeypatch.setattr(svc, "extract_ideate_turn", _extract)
        monkeypatch.setattr(svc, "call_similar_own", _similar)
        monkeypatch.setattr(svc, "call_create_idea", _create)
        monkeypatch.setattr(svc.settings, "frontend_base_url", CRM)
        monkeypatch.setattr(svc.settings, "ideation_shared_service_url", "")
        monkeypatch.setattr(svc.settings, "ideation_intake_api_key", "")
        yield e


def _no_ss(e: Env) -> None:
    assert e.similar_calls == []
    assert e.create_calls == []


# --------------------------------------------------------------------------- #
# A - access gate                                                             #
# --------------------------------------------------------------------------- #
def test_a_contact_without_linked_user_is_no_access(env):
    env.seed_workspace()
    env.seed_contact()
    self_ptr = {"ideation": {"status": "similar_offered", "message_text": "x",
                             "similar": [], "updated_at": _now_iso(), "is_test": False}}
    env.idea_message()
    out = env.turn(MSG, session_vars_in=self_ptr)
    assert out["status"] == "no_access"
    _no_ss(env)
    assert "ideation" not in out["session_vars"]


def test_a_inactive_linked_user_is_no_access(env):
    env.seed_workspace()
    env.seed_contact()
    env.seed_user(status="INACTIVE")
    env.idea_message()
    out = env.turn(MSG)
    assert out["status"] == "no_access"
    _no_ss(env)


def test_a_linked_user_without_permission_is_no_access(env):
    env.seed_workspace()
    env.seed_contact()
    env.seed_user(with_perm=False)
    env.idea_message()
    out = env.turn(MSG)
    assert out["status"] == "no_access"
    _no_ss(env)


def test_a_linked_user_with_permission_proceeds(env):
    env.ready()
    env.idea_message()
    env.created()
    out = env.turn(MSG)
    assert out["status"] == "complete"
    assert len(env.create_calls) == 1


def test_a_unconfigured_workspace_replies_unconfigured(env):
    env.seed_workspace(product_id=None)
    env.seed_contact()
    env.seed_user()
    env.idea_message()
    out = env.turn(MSG)
    assert out["status"] == "unconfigured"
    _no_ss(env)


# --------------------------------------------------------------------------- #
# B - ask-back                                                                #
# --------------------------------------------------------------------------- #
def test_b_no_idea_content_asks_back(env):
    env.ready()
    env.extraction("want to submit idea", fields={})
    out = env.turn("want to submit idea")
    assert out["status"] == "ask_idea"
    assert out["reply_text"]
    _no_ss(env)
    assert "ideation" not in out["session_vars"]


# --------------------------------------------------------------------------- #
# C - no similar: create at once                                              #
# --------------------------------------------------------------------------- #
def test_c_no_similar_creates_one_shot(env):
    env.ready()
    env.idea_message()
    idea_id = env.created(captured={"problem": PROBLEM})
    out = env.turn(MSG, submitter_name="WA Name")

    assert len(env.similar_calls) == 1
    assert len(env.create_calls) == 1
    p = env.create_calls[0]
    assert p["capture_now"] is True
    assert p["crm_user_id"] == env.user.id
    assert p["submitter_contact_id"] == env.phone
    assert p["message_text"] == MSG
    assert p["fields"]["problem"] == PROBLEM
    assert p["title"] == TITLE
    assert p["is_test"] is False

    sp = env.similar_calls[0]
    assert sp["crm_user_id"] == env.user.id
    assert sp["submitter_contact_id"] == env.phone
    assert sp["problem"] == PROBLEM
    assert sp["is_test"] is False

    link = f"{CRM}/ideas/{idea_id}"
    assert out["status"] == "complete"
    assert out["link"] == link
    assert link in out["reply_text"]
    assert TITLE in out["reply_text"]


def test_c_missing_list_names_absent_fields_only(env):
    env.ready()
    env.idea_message()
    env.created(captured={"problem": PROBLEM, "proposed_solution": "Show promo price in red"})
    reply = env.turn(MSG)["reply_text"]
    assert "Proposed solution" not in reply
    assert "Impact" in reply
    assert "Department" in reply
    assert "Photos or files" in reply


def test_c_all_fields_captured_still_lists_photos(env):
    env.ready()
    env.idea_message()
    env.created(
        captured={
            "problem": PROBLEM,
            "proposed_solution": "Show promo price in red",
            "impact": "Fewer repeat questions",
            "department": "Sales",
        }
    )
    reply = env.turn(MSG)["reply_text"]
    assert "Proposed solution" not in reply
    assert "Impact" not in reply
    assert "Department" not in reply
    assert "Photos or files" in reply


def test_c_nothing_captured_beyond_problem_lists_all_three_plus_photos(env):
    env.ready()
    env.idea_message()
    env.created(captured={"problem": PROBLEM})
    reply = env.turn(MSG)["reply_text"]
    for name in ("Proposed solution", "Impact", "Department", "Photos or files"):
        assert name in reply


# --------------------------------------------------------------------------- #
# D - similar found                                                           #
# --------------------------------------------------------------------------- #
def test_d_similar_found_offers_numbered_list_and_holds(env):
    env.ready()
    env.idea_message()
    ideas = env.sim(2)
    out = env.turn(MSG)

    assert env.create_calls == []
    assert out["status"] == "similar_offered"
    reply = out["reply_text"]
    lines = reply.splitlines()
    for n, idea in enumerate(ideas, start=1):
        line = next((ln for ln in lines if ln.lstrip().startswith(f"{n}")), None)
        assert line is not None, f"no line numbered {n}"
        assert idea["title"] in line
        assert f"{CRM}/ideas/{idea['id']}" in line

    held = out["session_vars"]["ideation"]
    assert held["status"] == "similar_offered"
    assert held["message_text"] == MSG
    assert [s["id"] for s in held["similar"]] == [i["id"] for i in ideas]
    assert held["is_test"] is False
    assert env.persisted()["ideation"]["status"] == "similar_offered"


def test_d_is_test_turn_is_not_persisted(env):
    env.ready()
    env.idea_message()
    env.sim(2)
    out = env.turn(MSG, is_test=True)
    assert out["status"] == "similar_offered"
    assert out["session_vars"]["ideation"]["is_test"] is True
    assert env.similar_calls[0]["is_test"] is True
    assert "ideation" not in env.persisted()


def test_d_total_above_shown_adds_see_all_line(env):
    env.ready()
    env.idea_message()
    env.sim(3, total=5)
    reply = env.turn(MSG)["reply_text"]
    assert f"{CRM}/ideas?view=mine" in reply


def test_d_total_equal_shown_has_no_see_all_line(env):
    env.ready()
    env.idea_message()
    env.sim(3, total=3)
    reply = env.turn(MSG)["reply_text"]
    assert "view=mine" not in reply


# --------------------------------------------------------------------------- #
# E - pick a number                                                           #
# --------------------------------------------------------------------------- #
def test_e_pick_number_replies_that_ideas_link(env):
    env.ready()
    similar = [
        {"id": _uid(), "idea_number": "IDEA-0151", "title": "First held idea"},
        {"id": _uid(), "idea_number": "IDEA-0097", "title": "Second held idea"},
    ]
    sv = env.pointer(similar)
    out = env.turn("2", session_vars_in=sv)
    assert out["status"] == "similar_picked"
    assert f"{CRM}/ideas/{similar[1]['id']}" in out["reply_text"]
    assert f"{CRM}/ideas/{similar[0]['id']}" not in out["reply_text"]
    _no_ss(env)
    assert "ideation" not in out["session_vars"]
    assert env.extractor_calls == []


def test_e_out_of_range_number_is_a_fresh_message(env):
    env.ready()
    similar = [{"id": _uid(), "idea_number": "IDEA-0151", "title": "Only held idea"}]
    sv = env.pointer(similar)
    env.extraction("3", fields={})
    out = env.turn("3", session_vars_in=sv)
    assert env.extractor_calls == ["3"]
    assert out["status"] == "ask_idea"
    assert "ideation" not in out["session_vars"]


# --------------------------------------------------------------------------- #
# F - NEW                                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("reply", ["NEW", " new. "])
def test_f_new_creates_from_held_message(env, reply):
    env.ready()
    held = env.idea_message("chatbot should remember what the dealer asked before")
    similar = [{"id": _uid(), "idea_number": "IDEA-0151", "title": "Held similar"}]
    sv = env.pointer(similar, message=held)
    idea_id = env.created()
    out = env.turn(reply, session_vars_in=sv)

    assert env.similar_calls == []
    assert len(env.create_calls) == 1
    p = env.create_calls[0]
    assert p["message_text"] == held
    assert p["capture_now"] is True
    assert p["fields"]["problem"] == PROBLEM
    assert p["crm_user_id"] == env.user.id
    assert out["status"] == "complete"
    assert f"{CRM}/ideas/{idea_id}" in out["reply_text"]
    assert "ideation" not in out["session_vars"]


# --------------------------------------------------------------------------- #
# G - another reply while held                                                #
# --------------------------------------------------------------------------- #
def test_g_other_reply_drops_hold_and_runs_fresh(env):
    env.ready()
    similar = [{"id": _uid(), "idea_number": "IDEA-0151", "title": "Held similar"}]
    sv = env.pointer(similar, message="old held message")
    other = env.idea_message("actually another idea: X should change")
    env.created()
    out = env.turn(other, session_vars_in=sv)

    assert env.extractor_calls == [other]
    assert len(env.similar_calls) == 1
    assert env.similar_calls[0]["problem"] == PROBLEM
    assert out["status"] == "complete"
    assert all(c["message_text"] != "old held message" for c in env.create_calls)


# --------------------------------------------------------------------------- #
# H - stale hold                                                              #
# --------------------------------------------------------------------------- #
def test_h_stale_hold_new_is_a_fresh_message(env):
    env.ready()
    held = env.idea_message("held original idea text")
    sv = env.pointer([{"id": _uid(), "idea_number": "IDEA-0151", "title": "Held"}],
                     message=held, age=timedelta(hours=25))
    env.extraction("new", fields={})
    out = env.turn("new", session_vars_in=sv)
    assert env.extractor_calls == ["new"]
    assert env.create_calls == []
    assert out["status"] == "ask_idea"


# --------------------------------------------------------------------------- #
# I - is_test mismatch                                                        #
# --------------------------------------------------------------------------- #
def test_i_live_hold_not_used_by_test_turn(env):
    env.ready()
    held = env.idea_message("held live idea text")
    sv = env.pointer([{"id": _uid(), "idea_number": "IDEA-0151", "title": "Held"}],
                     message=held, is_test=False)
    env.extraction("new", fields={})
    out = env.turn("new", session_vars_in=sv, is_test=True)
    assert env.extractor_calls == ["new"]
    assert env.create_calls == []
    assert out["status"] == "ask_idea"


# --------------------------------------------------------------------------- #
# J - old draft-shaped pointer                                                #
# --------------------------------------------------------------------------- #
def test_j_old_draft_pointer_is_ignored(env):
    env.ready()
    env.idea_message()
    env.created()
    old = {"ideation": {"draft_id": "d-old", "status": "collecting", "missing": ["module"],
                        "updated_at": _now_iso()}}
    out = env.turn(MSG, session_vars_in=old)
    assert out["status"] == "complete"
    assert env.extractor_calls == [MSG]
    assert "ideation" not in out["session_vars"]
    assert "draft_id" not in env.create_calls[0]


# --------------------------------------------------------------------------- #
# K - ss failure                                                              #
# --------------------------------------------------------------------------- #
def test_k_similar_lookup_failure_is_graceful_error(env):
    env.ready()
    env.idea_message()
    env.similar_result = IdeationServiceError("boom")
    sv = {"keep": "me"}
    out = env.turn(MSG, session_vars_in=sv)
    assert out["status"] == "error"
    assert out["reply_text"]
    assert env.create_calls == []
    assert "ideation" not in out["session_vars"]


def test_k_create_failure_is_graceful_error_and_pointer_untouched(env):
    env.ready()
    held = env.idea_message("held original idea text")
    similar = [{"id": _uid(), "idea_number": "IDEA-0151", "title": "Held"}]
    sv = env.pointer(similar, message=held)
    env.create_result = IdeationServiceError("boom")
    out = env.turn("new", session_vars_in=sv)
    assert out["status"] == "error"
    assert out["reply_text"]
    assert out["session_vars"]["ideation"] == sv["ideation"]


def test_k_create_failure_on_fresh_path_is_error(env):
    env.ready()
    env.idea_message()
    env.create_result = IdeationServiceError("boom")
    out = env.turn(MSG)
    assert out["status"] == "error"
    assert "link" not in out


# --------------------------------------------------------------------------- #
# L - link safety                                                             #
# --------------------------------------------------------------------------- #
def test_l_non_uuid_created_id_builds_no_crm_link(env):
    env.ready()
    env.idea_message()
    env.created(idea_id="not-a-uuid")
    out = env.turn(MSG)
    assert f"{CRM}/ideas/not-a-uuid" not in out["reply_text"]
    assert not out.get("link")


def test_l_non_uuid_similar_ideas_are_dropped(env):
    env.ready()
    env.idea_message()
    good = {"id": _uid(), "idea_number": "IDEA-0151", "title": "Good similar idea"}
    bad = {"id": "../../evil", "idea_number": "IDEA-0152", "title": "Bad similar idea"}
    env.similar_result = {"ideas": [bad, good], "total": 2}
    out = env.turn(MSG)
    assert "evil" not in out["reply_text"]
    assert "Bad similar idea" not in out["reply_text"]
    assert f"{CRM}/ideas/{good['id']}" in out["reply_text"]
    assert [s["id"] for s in out["session_vars"]["ideation"]["similar"]] == [good["id"]]


# --------------------------------------------------------------------------- #
# M - endpoint                                                                #
# --------------------------------------------------------------------------- #
def test_m_endpoint_routes_to_capture_service(monkeypatch):
    from fastapi.testclient import TestClient

    from app.dependencies import get_db, get_external_api_user
    from tests._external_auth import external_permissions_granted

    seen: dict = {}

    def _fake(db, **kw):  # noqa: ANN001
        seen.update(kw)
        return {"status": "ask_idea", "reply_text": "Sure", "session_vars": {}, "offered_media": []}

    monkeypatch.setattr("app.api.v1.external.ideation.handle_capture_turn", _fake)
    monkeypatch.setattr(
        "app.api.v1.external.ideation.IntegrationLogService.create_integration_log",
        lambda self, log_data, request_payload_dict=None: None,
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "system"}
    try:
        with external_permissions_granted():
            resp = TestClient(app).post(
                "/api/v1/external/ideation/turn",
                json={
                    "respond_io_id": "rio-1",
                    "message_text": "an idea",
                    "media_selection": "1",
                    "is_new_idea": True,
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ask_idea"
    assert seen["respond_io_id"] == "rio-1"
    assert seen["message_text"] == "an idea"
