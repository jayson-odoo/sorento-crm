"""WA-COMPLAINT-INTAKE section D red tests (core): dealers file as their own CRM user.

UAC: documentation/plans/chatbot/wa-complaint-intake-acceptance-criteria.md rows D-1..D-7
(D-8 lives in tests/chatbot/agent/test_agent_dealer_user_principal.py: this file must not import
app.services.chatbot).

Contract these tests pin (names fixed so the coder can match them):

* Permission slug `ideation.ideas.submit` ("Submit ideas and issues") in PERMISSION_REGISTRY, and
  `ideation_capture_service.SUBMIT_PERMISSION == "ideation.ideas.submit"`.
* ONE migration under alembic/versions mentions `ideation.ideas.submit`; its `upgrade()` grants it to
  role `portal_user` and grants `ideation.board.view` to role `salesperson` (portal_user does NOT get
  board.view), idempotent, revision id <= 32 chars, on the single head, no `app.*` import.
* `ideation_capture_service._access_user` accepts a linked active user holding board.view OR submit.
  Every `/api/v1/ideation/*` route still needs board.view: a submit-only user gets 403.
* `ideation_capture_service.ensure_dealer_user(db, contact) -> User | None` (contact = the
  `RespondContact` ORM row): for an eligible contact (AI access on, exactly one row for its respond.io
  id, a respond.io id at all) with no linked user it creates one through `UserService.create_user`
  (roles exactly {portal_user}, ACTIVE, no password, name + phone from the contact, linked by
  `respond_contact_id`); an existing linked user is returned, never a second; None when ineligible.
  A lost race on `uq_users_respond_contact_id` returns the winner's user.
* `handle_capture_turn` calls it only on a LIVE turn that will file (extraction has the required
  field); a test turn by an unlinked dealer answers "Test turn: nothing was sent." and writes nothing.
* `phone_signin_service`: a user whose roles are all non-staff (`portal_user`, `guest`) is not
  eligible (`find_eligible` / `eligible_user_for_contact` -> None); any staff role keeps it eligible.

Postgres only (blank schema via tests/_pg_fixture.py); every test seeds its own chain. Names that do not
exist yet are reached at call time, so a missing name fails its test and never the collection.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import RespondContact
from app.models.respond_workspace import RespondWorkspace
from app.models.user import User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from app.rbac.permission_registry import PERMISSION_REGISTRY
from app.services import reference_seed
from app.services.ideation_extractor import IdeateExtraction
from app.services.phone_utils import normalize_msisdn
from tests._migration_imports import app_imports
from tests._pg_fixture import blank_session, unique_code
from tests.test_ideation_capture_turn import MSG, PROBLEM, TITLE, Env, env  # noqa: F401  (fixture)

SUBMIT = "ideation.ideas.submit"
VIEW = "ideation.board.view"
IDEA_NUMBER = "IDEA-0184"
ISSUE_MSG = "the stock page shows a blank screen when I open it on my phone"
TEST_NOTE = "Test turn: nothing was sent."
VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


# --------------------------------------------------------------------------- #
# Shared seeding                                                              #
# --------------------------------------------------------------------------- #
def _perm(db, slug: str) -> UserPermission:
    perm = db.query(UserPermission).filter(UserPermission.slug == slug).first()
    if perm is None:
        perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(perm)
        db.flush()
    return perm


def _role(db, slug: str, *grants: str) -> UserRole:
    """The base role `slug` (reference seed), holding `grants` (as the D-1 migration leaves it)."""
    reference_seed.seed_roles(db)
    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(role)
        db.flush()
    for g in grants:
        perm = _perm(db, g)
        held = (
            db.query(UserRolePermission)
            .filter(UserRolePermission.role_id == role.id, UserRolePermission.permission_id == perm.id)
            .first()
        )
        if held is None:
            db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
    db.flush()
    return role


def _assign(db, user: User, *role_slugs: str) -> None:
    for slug in role_slugs:
        role = db.query(UserRole).filter(UserRole.slug == slug).first()
        assert role is not None, f"fixture: role {slug} not seeded"
        db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
    db.flush()


def _linked_users(db, contact_id: str) -> list[User]:
    db.expire_all()
    return db.query(User).filter(User.respond_contact_id == contact_id).all()


def _role_slugs(db, user_id: str) -> set[str]:
    rows = (
        db.query(UserRole.slug)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == UserRole.id)
        .filter(UserRoleAssignment.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows}


def _svc():
    import app.services.ideation_capture_service as svc

    return svc


def _dealer(e: Env, *, allowed: bool = True, session_vars: dict | None = None) -> RespondContact:
    """Workspace + an eligible WhatsApp contact (AI access on, agent switch on, one row) with NO user,
    and the `portal_user` role holding the submit slug (as D-1 leaves it)."""
    e.seed_workspace()
    contact = e.seed_contact(session_vars)
    contact.chatbot_allowed = allowed
    contact.chatbot_agent_enabled = True
    e.db.flush()
    _role(e.db, "portal_user", SUBMIT)
    return contact


def _issue(e: Env, text: str = ISSUE_MSG) -> str:
    e.idea_message(text, language="en")
    e.extractions[text].type = "issue"
    return text


def _lines(reply: str) -> list[str]:
    return [line.strip() for line in reply.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# D-1: the slug and the migration                                             #
# --------------------------------------------------------------------------- #
def test_D1_submit_slug_is_registered_once_with_its_name():
    entries = [e for e in PERMISSION_REGISTRY if e["slug"] == SUBMIT]
    assert len(entries) == 1, f"{SUBMIT} must be registered exactly once"
    assert entries[0]["name"] == "Submit ideas and issues"
    assert (entries[0].get("description") or "").strip()


def test_D1_capture_service_names_the_submit_slug():
    assert _svc().SUBMIT_PERMISSION == SUBMIT


def _submit_migration_path() -> Path:
    hits = [
        p
        for p in sorted(VERSIONS.glob("*.py"))
        if SUBMIT in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert len(hits) == 1, f"exactly one migration must seed {SUBMIT}; found {[p.name for p in hits]}"
    return hits[0]


def _load_migration():
    path = _submit_migration_path()
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()


def _granted(db, slug: str) -> set[str]:
    rows = db.execute(
        text(
            "SELECT r.slug FROM user_role_permissions rp "
            "JOIN user_roles r ON r.id = rp.role_id "
            "JOIN user_permissions p ON p.id = rp.permission_id WHERE p.slug = :s"
        ),
        {"s": slug},
    ).all()
    return {r[0] for r in rows}


def test_D1_migration_revision_fits_sits_on_the_single_head_and_imports_no_app_code():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    path = _submit_migration_path()
    module = _load_migration()
    assert len(module.revision) <= 32
    assert not app_imports(path), "a migration must not import live app code"
    script = ScriptDirectory.from_config(Config(str(VERSIONS.parent.parent / "alembic.ini")))
    heads = list(script.get_heads())
    assert len(heads) == 1, heads
    assert module.revision in {r.revision for r in script.walk_revisions(base="base", head=heads[0])}


def test_D1_upgrade_grants_submit_to_portal_user_and_view_to_salesperson():
    with blank_session() as db:
        reference_seed.seed_roles(db)
        _perm(db, VIEW)  # seeded by 411 on every real database; the submit slug is not
        assert db.query(UserPermission).filter(UserPermission.slug == SUBMIT).first() is None
        _upgrade(db)
        assert "portal_user" in _granted(db, SUBMIT)
        assert "salesperson" in _granted(db, VIEW)
        # Submit opens nothing else: portal_user is not given the board.
        assert "portal_user" not in _granted(db, VIEW)


def test_D1_upgrade_twice_changes_nothing():
    with blank_session() as db:
        reference_seed.seed_roles(db)
        _perm(db, VIEW)
        _upgrade(db)

        def counts():
            return (
                db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": SUBMIT}).scalar(),
                db.execute(text("SELECT count(*) FROM user_role_permissions")).scalar(),
            )

        first = counts()
        _upgrade(db)
        assert counts() == first
        assert first[0] == 1


# --------------------------------------------------------------------------- #
# D-2: the capture gate accepts either slug; the board routes do not         #
# --------------------------------------------------------------------------- #
def _linked_user_with(e: Env, *slugs: str) -> User:
    user = e.seed_user(with_perm=False)
    role = UserRole(
        id=str(uuid.uuid4()), slug=unique_code("role").lower(), name=unique_code("Role"), description=""
    )
    e.db.add(role)
    e.db.flush()
    for slug in slugs:
        e.db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=_perm(e.db, slug).id))
    e.db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
    e.db.flush()
    return user


def test_D2_access_user_accepts_a_submit_only_user(env):
    env.seed_workspace()
    env.seed_contact()
    user = _linked_user_with(env, SUBMIT)
    got = env.svc._access_user(env.db, env.rio)
    assert got is not None and str(got.id) == str(user.id)


def test_D2_a_submit_only_user_files_through_the_bot_lane(env):
    env.seed_workspace()
    env.seed_contact()
    user = _linked_user_with(env, SUBMIT)
    env.idea_message()
    env.created()
    out = env.turn(MSG)
    assert out["status"] == "complete"
    (payload,) = env.create_calls
    assert payload["submitter_crm_user_id"] == user.id


def test_D2_access_user_still_accepts_a_view_only_user_and_refuses_neither(env):
    env.seed_workspace()
    env.seed_contact()
    _linked_user_with(env, VIEW)
    assert env.svc._access_user(env.db, env.rio) is not None
    other = Env(env.db, env.svc, env.mp)
    other.seed_contact()
    _linked_user_with(other, "inventory.stock.view")
    assert env.svc._access_user(env.db, other.rio) is None


@pytest.fixture
def ideas_route(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api.v1.ideation.ideas as ideas_mod
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db

    monkeypatch.setattr(ideas_mod, "_forward", lambda *a, **kw: {"items": []})
    with blank_session() as db:

        def user_with(*slugs: str) -> dict:
            e = Env(db, None, monkeypatch)
            e.seed_contact()
            user = _linked_user_with(e, *slugs)
            db.commit()
            return {"id": user.id, "email": user.email, "name": user.name}

        def get(user: dict):
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_current_user] = lambda: dict(user)
            app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(user)
            try:
                return TestClient(app).get("/api/v1/ideation/ideas")
            finally:
                app.dependency_overrides.clear()

        yield user_with, get


def test_D2_a_submit_only_user_gets_403_on_the_ideas_list(ideas_route):
    user_with, get = ideas_route
    assert get(user_with(SUBMIT)).status_code == 403
    # Control: the same route opens for the board slug, so the 403 is the permission and nothing else.
    assert get(user_with(VIEW)).status_code == 200


# --------------------------------------------------------------------------- #
# D-3: an eligible unlinked dealer files as its own new CRM user              #
# --------------------------------------------------------------------------- #
def _assert_dealer_user(db, user: User, contact: RespondContact) -> None:
    assert user.respond_contact_id == contact.id
    assert _role_slugs(db, user.id) == {"portal_user"}
    assert str(user.status).upper() == "ACTIVE"
    assert not user.password
    assert user.name == contact.name
    assert user.contact_number == normalize_msisdn(contact.phone_number)


def test_D3_ensure_dealer_user_creates_the_contacts_own_portal_user(env):
    contact = _dealer(env)
    user = env.svc.ensure_dealer_user(env.db, contact)
    assert user is not None
    (only,) = _linked_users(env.db, contact.id)
    assert only.id == user.id
    _assert_dealer_user(env.db, only, contact)


def test_D3_ensure_dealer_user_goes_through_user_service_create_user(env, monkeypatch):
    from app.services.user_service import UserService

    contact = _dealer(env)
    calls: list = []
    real = UserService.create_user

    def spy(self, user_data):
        calls.append(user_data)
        return real(self, user_data)

    monkeypatch.setattr(UserService, "create_user", spy)
    env.svc.ensure_dealer_user(env.db, contact)
    assert len(calls) == 1
    assert calls[0].respond_contact_id == contact.id


def test_D3_an_unlinked_dealer_filing_an_issue_gets_a_user_and_files_as_it(env):
    contact = _dealer(env)
    env.created()
    out = env.turn(_issue(env))
    assert out["status"] == "complete"
    (user,) = _linked_users(env.db, contact.id)
    _assert_dealer_user(env.db, user, contact)
    (payload,) = env.create_calls
    assert payload["submitter_crm_user_id"] == user.id
    assert payload["type"] == "issue"
    assert all(c["submitter_crm_user_id"] == user.id for c in env.similar_calls)
    assert f"Logged as issue {IDEA_NUMBER}" in _lines(out["reply_text"])


def test_D3_a_contact_with_a_linked_staff_user_gets_no_new_user(env):
    env.ready()
    env.created()
    out = env.turn(env.idea_message())
    assert out["status"] == "complete"
    assert [u.id for u in _linked_users(env.db, env.contact.id)] == [env.user.id]


# --------------------------------------------------------------------------- #
# D-4: no user unless a live turn really files                                #
# --------------------------------------------------------------------------- #
def _real_filing_creates_one_user(e: Env, contact: RespondContact) -> None:
    """Positive control: a live idea on the same contact now creates exactly one user."""
    text_ = "the delivery screen should show the lorry plate number"
    e.idea_message(text_)
    e.created()
    out = e.turn(text_)
    assert out["status"] == "complete", out["status"]
    assert len(_linked_users(e.db, contact.id)) == 1


def _case_ask_back(e: Env, contact: RespondContact) -> None:
    e.extraction("I want to report a problem", fields={}, title="")
    out = e.turn("I want to report a problem")
    assert out["status"] != "complete"


def _case_held_list_answer(e: Env, contact: RespondContact) -> None:
    held = e.pointer(e.sim(2))
    out = e.turn("1", session_vars_in=held)
    assert out["status"] != "complete"
    assert e.create_calls == []


def _case_read_failure(e: Env, contact: RespondContact) -> None:
    e.extractions["something about the stock page"] = RuntimeError("provider down")
    out = e.turn("something about the stock page")
    assert out["status"] != "complete"


def _case_unknown_respond_id(e: Env, contact: RespondContact) -> None:
    e.idea_message()
    real_rio = e.rio
    e.rio = unique_code("rio-unknown")
    try:
        try:
            out = e.turn(MSG)
            assert out["status"] != "complete"
        except HTTPException:
            pass
    finally:
        e.rio = real_rio
    assert e.create_calls == []


D4_TURN_CASES = {
    "ask_back_with_no_idea_yet": _case_ask_back,
    "held_similar_list_answer": _case_held_list_answer,
    "read_failure": _case_read_failure,
    "unknown_respond_io_id": _case_unknown_respond_id,
}


@pytest.mark.parametrize("case", sorted(D4_TURN_CASES))
def test_D4_no_user_on_a_turn_that_does_not_file(env, case):
    contact = _dealer(env)
    D4_TURN_CASES[case](env, contact)
    assert _linked_users(env.db, contact.id) == [], f"{case} created a user"
    _real_filing_creates_one_user(env, contact)


def test_D4_no_user_on_an_unconfigured_workspace(env):
    env.seed_workspace(product_id=None)
    contact = env.seed_contact()
    contact.chatbot_allowed = True
    contact.chatbot_agent_enabled = True
    _role(env.db, "portal_user", SUBMIT)
    env.db.flush()
    out = env.turn(env.idea_message())
    assert out["status"] == "unconfigured"
    assert _linked_users(env.db, contact.id) == []
    ws = env.db.query(RespondWorkspace).filter(RespondWorkspace.is_default.is_(True)).one()
    ws.ideation_product_id = "prod-1"
    env.db.flush()
    _real_filing_creates_one_user(env, contact)


def test_D4_a_test_turn_by_an_unlinked_dealer_sends_nothing_and_writes_nothing(env):
    contact = _dealer(env, session_vars={"keep": "me"})
    env.created()
    out = env.turn(env.idea_message(), is_test=True)
    assert TEST_NOTE in out["reply_text"]
    assert env.similar_calls == [] and env.create_calls == []
    assert _linked_users(env.db, contact.id) == []
    assert env.persisted() == {"keep": "me"}
    _real_filing_creates_one_user(env, contact)


def test_D4_ai_access_off_is_ineligible(env):
    contact = _dealer(env, allowed=False)
    env.created()
    out = env.turn(env.idea_message())
    assert out["status"] == "no_access"
    assert env.create_calls == []
    assert _linked_users(env.db, contact.id) == []
    assert env.svc.ensure_dealer_user(env.db, contact) is None
    assert _linked_users(env.db, contact.id) == []


def test_D4_duplicate_contact_rows_are_ineligible(env):
    contact = _dealer(env)
    twin = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6013{uuid.uuid4().int % 10**8:08d}",
        name="CONTACT A TWIN",
        respond_io_id=env.rio,
        session_vars={},
        chatbot_allowed=True,
        chatbot_agent_enabled=True,
    )
    env.db.add(twin)
    env.db.flush()
    env.created()
    out = env.turn(env.idea_message())
    assert out["status"] == "no_access"
    assert env.create_calls == []
    assert env.svc.ensure_dealer_user(env.db, contact) is None
    assert env.svc.ensure_dealer_user(env.db, twin) is None
    assert _linked_users(env.db, contact.id) == [] and _linked_users(env.db, twin.id) == []


def test_D4_a_contact_with_no_respond_io_id_is_ineligible(env):
    contact = _dealer(env)
    contact.respond_io_id = None
    env.db.flush()
    assert env.svc.ensure_dealer_user(env.db, contact) is None
    assert _linked_users(env.db, contact.id) == []


# --------------------------------------------------------------------------- #
# D-5 / D-6: one user per contact, ever                                       #
# --------------------------------------------------------------------------- #
def test_D5_ensure_dealer_user_twice_returns_the_same_one_user(env):
    contact = _dealer(env)
    first = env.svc.ensure_dealer_user(env.db, contact)
    second = env.svc.ensure_dealer_user(env.db, contact)
    assert first is not None and second is not None
    assert first.id == second.id
    assert len(_linked_users(env.db, contact.id)) == 1


def _competitor(db, contact: RespondContact) -> str:
    """The user the OTHER message's session created and committed meanwhile."""
    other = User(
        id=str(uuid.uuid4()),
        email=f"zzt-race-{uuid.uuid4().hex[:8]}@test.com",
        name=contact.name,
        status="ACTIVE",
        respond_contact_id=contact.id,
    )
    db.add(other)
    db.flush()
    _assign(db, other, "portal_user")
    db.commit()
    return other.id


@pytest.mark.parametrize("how", ["real_unique_index", "raw_integrity_error"])
def test_D5_a_lost_race_reuses_the_winners_user(env, monkeypatch, how):
    from app.services.user_service import UserService

    contact = _dealer(env)
    env.db.commit()
    won: dict[str, str] = {}

    if how == "real_unique_index":
        # The pre-check passes, then the other session commits, then our INSERT hits
        # uq_users_respond_contact_id inside the real create_user.
        real_check = UserService._check_contact_free

        def racing_check(self, respond_contact_id, exclude_user_id):
            if not won:
                won["id"] = _competitor(self.db, contact)
                return None
            return real_check(self, respond_contact_id, exclude_user_id)

        monkeypatch.setattr(UserService, "_check_contact_free", racing_check)
    else:
        real_create = UserService.create_user

        def racing_create(self, user_data):
            if not won:
                won["id"] = _competitor(self.db, contact)
                raise IntegrityError(
                    "INSERT INTO users ...",
                    {},
                    Exception('duplicate key value violates unique constraint "uq_users_respond_contact_id"'),
                )
            return real_create(self, user_data)

        monkeypatch.setattr(UserService, "create_user", racing_create)

    got = env.svc.ensure_dealer_user(env.db, contact)
    assert won, "the race was never entered: ensure_dealer_user did not create through UserService"
    assert got is not None and got.id == won["id"]
    assert [u.id for u in _linked_users(env.db, contact.id)] == [won["id"]]


def test_D6_a_second_filing_reuses_the_dealers_user(env):
    contact = _dealer(env)
    env.created()
    first = env.turn(env.idea_message())
    second_text = "the order page should show the promised delivery week"
    env.idea_message(second_text)
    env.created()
    second = env.turn(second_text)
    assert first["status"] == "complete" and second["status"] == "complete"
    (user,) = _linked_users(env.db, contact.id)
    assert [p["submitter_crm_user_id"] for p in env.create_calls] == [user.id, user.id]


# --------------------------------------------------------------------------- #
# D-7: no CRM sign-in for an all-non-staff user                               #
# --------------------------------------------------------------------------- #
def _signin_chain(db, *role_slugs: str) -> tuple[RespondContact, User, str]:
    reference_seed.seed_roles(db)
    digits = "601" + str(uuid.uuid4().int % 10**9).zfill(9)
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=digits, name="ZZT Dealer")
    db.add(contact)
    db.flush()
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('d7').lower()}@x.com",
        name="ZZT Dealer",
        status="ACTIVE",
        contact_number=digits,
        respond_contact_id=contact.id,
    )
    db.add(user)
    db.flush()
    _assign(db, user, *role_slugs)
    db.commit()
    return contact, user, digits


@pytest.mark.parametrize("roles", [("portal_user",), ("guest",), ("portal_user", "guest")])
def test_D7_an_all_non_staff_user_cannot_sign_in(roles):
    from app.services.phone_signin_service import eligible_user_for_contact, find_eligible

    with blank_session() as db:
        contact, _user, digits = _signin_chain(db, *roles)
        assert eligible_user_for_contact(db, contact.id) is None
        assert find_eligible(db, digits) is None


def test_D7_a_user_with_a_staff_role_still_signs_in():
    from app.services.phone_signin_service import eligible_user_for_contact, find_eligible

    with blank_session() as db:
        contact, user, digits = _signin_chain(db, "salesperson", "portal_user")
        got = eligible_user_for_contact(db, contact.id)
        assert got is not None and got.id == user.id
        found = find_eligible(db, digits)
        assert found is not None and found[0].id == user.id


def test_D7_the_dealer_user_the_bot_created_cannot_sign_in(env):
    from app.services.phone_signin_service import eligible_user_for_contact

    contact = _dealer(env)
    user = env.svc.ensure_dealer_user(env.db, contact)
    assert user is not None
    assert eligible_user_for_contact(env.db, contact.id) is None
