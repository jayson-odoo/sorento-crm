"""AGENTIC-IDEATE R2 (AC-R2-1 to AC-R2-13): three idea tools on the agent.

Red tests, written before the tools exist. The shared service (ss) is `tests/_ideation_ss_fake.FakeSS`
installed at the httpx boundary: the intake calls (`call_similar_own`, `call_create_idea`, both sync
`httpx.Client`) and the embed gateway calls (list, get, PATCH) are all served by it, so no real
network is possible. Postgres only (blank schema); every test seeds its own chain.

Names that do not exist yet (`writes.CREATE_IDEA`, ...) are reached at call time, the tool names are
local literals, so a missing name fails one test and never the collection.

Recognisable fakes seeded so an absence can be asserted: the ss base URL host `shared.test`, the intake
key `ZZTINTAKEKEY7788` and every uuid (`UUID_RE`) must never appear in a failure text.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
import uuid

import httpx
import pytest
from jose import jwt
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.respond_workspace import RespondWorkspace
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.utils.field_encryption import encrypt_secret
from tests._ideation_ss_fake import SIGNING_SECRET, SS_BASE, FakeSS, blank_embed_settings, configure_embed_settings
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user
from tests.chatbot.agent.test_agent_writes import action_row, answer_, round_of, tc, tool_names
from tests.chatbot.agent.test_agent_writes_round1 import Prov, _no_mcp, go, operator_with

CREATE = "crm_idea_create"
UPDATE = "crm_idea_update"
LIST = "crm_ideas_list"
BOARD_VIEW = "ideation.board.view"
MANAGE = "ideation.ideas.manage"
INTAKE_KEY = "ZZTINTAKEKEY7788"
PRODUCT = "prod-zzt-ideas"
CRM = "https://crm.zzt.example"
SIMILAR_PATH = "/ideation/intake/ideas/similar-own"
CREATE_PATH = "/ideation/intake/ideas"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
OWN_ONLY_MSG = "You can only edit your own ideas."

PROBLEM = "The stock list is too long to scroll on my phone"
FIELDS = {
    "problem": PROBLEM,
    "title": "Shorter stock list on phones",
    "desired_outcome": "Nearest warehouse first",
    "use_cases": ["Checking stock at a showroom", "Quoting from the car"],
    "current_workaround": "Scroll for a long time",
}


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture(autouse=True)
def _fresh_token_cache():
    from app.services import ideation_gateway_service

    ideation_gateway_service.clear_token_cache()
    yield
    ideation_gateway_service.clear_token_cache()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def ss(monkeypatch):
    from app.config import settings

    configure_embed_settings(monkeypatch)
    monkeypatch.setattr(settings, "frontend_base_url", CRM)
    fake = FakeSS().install(monkeypatch)
    ids = iter(str(uuid.uuid4()) for _ in range(50))
    numbers = iter(f"IDEA-{n:04d}" for n in range(184, 400))

    def created(request):
        return httpx.Response(
            200,
            json={"idea_id": next(ids), "idea_number": next(numbers), "status": "captured", "title": "x"},
            request=request,
        )

    fake.route("POST", SIMILAR_PATH, json_body={"matches": []})
    fake.routes[("POST", CREATE_PATH)] = created
    fake.route("GET", "/embed/ideas", json_body=[])
    return fake


class World:
    def __init__(self, contact, user_id):
        self.contact = contact
        self.user_id = user_id

    @property
    def respond_id(self):
        return self.contact["respond_id"]


def seed_workspace(db, *, configured=True):
    db.add(
        RespondWorkspace(
            id=str(uuid.uuid4()),
            space_id=unique_code("zzt-space"),
            api_key_ciphertext=encrypt_secret("respond-key"),
            is_default=True,
            ideation_product_id=PRODUCT if configured else None,
            ideation_shared_service_url=SS_BASE if configured else None,
            ideation_intake_api_key_ciphertext=encrypt_secret(INTAKE_KEY) if configured else None,
        )
    )
    db.flush()


def make_world(db, *, slugs=(BOARD_VIEW,), configured=True, workspace=True) -> World:
    if workspace:
        seed_workspace(db, configured=configured)
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    db.commit()
    return World(contact, user_id)


def another_world(db, *, slugs=(BOARD_VIEW,)) -> World:
    """A second contact and user on the same workspace."""
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    db.commit()
    return World(contact, user_id)


def ctx_of(db, w, operator=None):
    from app.services.chatbot.agent.access import build_context

    ctx = build_context(db, w.respond_id)
    return dataclasses.replace(ctx, operator_user_id=operator) if operator else ctx


def propose(db, w, name, args, *, seen=(), operator=None):
    from app.services.chatbot.agent import writes

    return writes.propose_step(
        db, ctx_of(db, w, operator), name, args, seen_ids={str(s).lower() for s in seen}
    )


def store(db, w, calls, *, seen=(), operator=None):
    """propose_step for each (name, args), then one stored proposal. Returns (steps, action row)."""
    from app.services.chatbot.agent import actions, writes

    ctx = ctx_of(db, w, operator)
    steps = []
    for name, args in calls:
        res, step = writes.propose_step(db, ctx, name, args, seen_ids={str(s).lower() for s in seen})
        assert res.status == "proposed", f"{name}: {res.status} {res.message}"
        steps.append(step)
    row = actions.store_proposal(
        db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=steps
    )
    return steps, row


def confirm(db, w, row, *, operator=None):
    from app.services.chatbot.agent import actions

    return actions.confirm(db, w.respond_id, str(row.id), via="console", operator_user_id=operator)


def posts(fake, path):
    return [c for c in fake.calls if c["method"] == "POST" and c["path"] == path]


def patches(fake):
    return [c for c in fake.calls if c["method"] == "PATCH"]


def phone_of(db, w):
    return db.execute(
        text("SELECT phone_number FROM respond_contacts WHERE id = :id"), {"id": w.contact["pk"]}
    ).scalar()


def similar_matches(n):
    return [
        {
            "idea_id": str(uuid.uuid4()),
            "idea_number": f"IDEA-01{i}0",
            "title": f"Existing zzt idea {i}",
            "problem": "p",
            "status": "new",
            "similarity": 0.8,
        }
        for i in range(1, n + 1)
    ]


def leaks(*texts) -> list[str]:
    """Anything a user must never read in a failure: a URL, the key, the host, a uuid."""
    found = []
    for t in texts:
        t = t or ""
        if "http" in t.lower():
            found.append(f"url in {t!r}")
        if INTAKE_KEY in t:
            found.append(f"key in {t!r}")
        if "shared.test" in t:
            found.append(f"host in {t!r}")
        if UUID_RE.search(t):
            found.append(f"uuid in {t!r}")
    return found


# ------------------------------------------------------------------ constants


def test_the_registry_names_and_the_test_flag():
    from app.services.chatbot.agent import tools, writes

    assert writes.CREATE_IDEA == CREATE and writes.UPDATE_IDEA == UPDATE and writes.LIST_IDEAS == LIST
    assert writes.IDEA_IS_TEST is True
    assert CREATE in writes.WRITES and UPDATE in writes.WRITES and LIST in writes.USER_READS
    for name in (CREATE, UPDATE, LIST):
        entry = writes.WRITES.get(name) or writes.USER_READS.get(name)
        assert entry.user_permission == BOARD_VIEW
    assert tools.TOOL_LABELS[CREATE] == "submit a new idea or feature request"
    assert tools.TOOL_LABELS[UPDATE] == "change one of your ideas"
    assert tools.TOOL_LABELS[LIST] == "your ideas"


# ------------------------------------------------------------------ AC-R2-1 exposure


def test_AC_R2_1_a_user_with_the_slug_is_offered_all_three(db, ss):
    from app.services.chatbot.agent import writes

    w = make_world(db)
    ctx = ctx_of(db, w)
    assert {CREATE, UPDATE} <= {d.name for d in writes.permitted_writes(db, ctx)}
    assert LIST in {r.name for r in writes.permitted_user_reads(db, ctx)}


def test_AC_R2_1_a_user_without_the_slug_is_offered_none_and_is_refused(db, ss):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=("inventory.stock.view",))
    ctx = ctx_of(db, w)
    assert not ({CREATE, UPDATE} & {d.name for d in writes.permitted_writes(db, ctx)})
    assert LIST not in {r.name for r in writes.permitted_user_reads(db, ctx)}
    for name, args in ((CREATE, {"problem": PROBLEM}), (UPDATE, {"idea_id": str(uuid.uuid4()), "title": "x"})):
        res, step = propose(db, w, name, args, seen=[args.get("idea_id", "")])
        assert res.status == "denied" and step is None
    assert writes.run_user_read(db, ctx, LIST, {}, set()).status == "denied"
    assert ss.calls == []


def test_AC_R2_1_the_model_is_shown_the_tools_only_with_the_slug(db, ss):
    holder = make_world(db)
    stranger = another_world(db, slugs=("inventory.stock.view",))
    _, seen_by_holder = go(db, holder, [answer_("Hi.")])
    _, seen_by_stranger = go(db, stranger, [answer_("Hi.")])
    assert {CREATE, UPDATE, LIST} <= tool_names(seen_by_holder)
    assert not ({CREATE, UPDATE, LIST} & tool_names(seen_by_stranger))


def test_AC_R2_1_a_contact_with_no_linked_user_never_reaches_them(db, ss):
    from app.services.chatbot.agent.access import AgentRefused, build_context

    contact = seed_contact(db)
    db.commit()
    with pytest.raises(AgentRefused) as exc:
        build_context(db, contact["respond_id"])
    assert exc.value.reason == "no_linked_user"


# ------------------------------------------------------------------ AC-R2-2 propose creates nothing


def test_AC_R2_2_a_create_is_proposed_and_sends_no_create(db, ss):
    w = make_world(db)
    res, step = propose(db, w, CREATE, dict(FIELDS))
    assert res.status == "proposed" and step is not None
    assert FIELDS["title"] in step["summary"]
    assert posts(ss, CREATE_PATH) == []


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"title": "No problem given"},
        {"problem": PROBLEM, "colour": "red"},
        {"problem": PROBLEM, "is_test": False},
        {"problem": PROBLEM, "is_test": True},
        {"problem": PROBLEM, "submitter_crm_user_id": str(uuid.uuid4())},
        {"problem": PROBLEM, "product_id": "someone-elses-product"},
    ],
    ids=["empty", "missing_problem", "unknown_arg", "is_test_false", "is_test_true", "submitter", "product"],
)
def test_AC_R2_2_bad_or_forbidden_arguments_are_invalid(db, ss, args):
    w = make_world(db)
    res, step = propose(db, w, CREATE, args)
    assert res.status == "invalid" and step is None
    assert ss.calls == []


def test_AC_R2_2_the_list_takes_only_search(db, ss):
    from app.services.chatbot.agent import writes

    w = make_world(db)
    ctx = ctx_of(db, w)
    assert writes.run_user_read(db, ctx, LIST, {"is_test": False}, set()).status == "invalid"
    assert writes.run_user_read(db, ctx, LIST, {"mine": False}, set()).status == "invalid"
    assert writes.run_user_read(db, ctx, LIST, {"search": "stock"}, set()).status == "ok"


# ------------------------------------------------------------------ AC-R2-3 similar ideas


def test_AC_R2_3_the_summary_names_up_to_three_similar_ideas(db, ss):
    w = make_world(db)
    found = similar_matches(5)
    ss.route("POST", SIMILAR_PATH, json_body={"matches": found})
    res, step = propose(db, w, CREATE, dict(FIELDS))
    assert res.status == "proposed"
    for m in found[:3]:
        assert m["idea_number"] in step["summary"] and m["title"] in step["summary"]
    for m in found[3:]:
        assert m["idea_number"] not in step["summary"]
    assert not UUID_RE.search(step["summary"])


@pytest.mark.parametrize("operator_case", [False, True])
def test_AC_R2_3_the_lookup_sends_the_linked_user_and_the_test_flag(db, ss, operator_case):
    w = make_world(db)
    op = operator_with(db, BOARD_VIEW) if operator_case else None
    res, _ = propose(db, w, CREATE, dict(FIELDS), operator=op)
    assert res.status == "proposed"
    (call,) = posts(ss, SIMILAR_PATH)
    assert call["json"]["submitter_crm_user_id"] == w.user_id
    assert call["json"]["is_test"] is True
    assert call["json"]["product_id"] == PRODUCT
    assert call["headers"]["authorization"] == f"Bearer {INTAKE_KEY}"


# ------------------------------------------------------------------ AC-R2-4 best effort lookup


def test_AC_R2_4_ss_not_configured_still_proposes_with_no_similar_line(db, ss, monkeypatch):
    blank_embed_settings(monkeypatch)
    w = make_world(db, configured=False)
    res, step = propose(db, w, CREATE, dict(FIELDS))
    assert res.status == "proposed" and step is not None
    assert "similar" not in step["summary"].lower()
    assert ss.calls == []


@pytest.mark.parametrize("failure", ["http_500", "transport"])
def test_AC_R2_4_a_failing_lookup_still_proposes_with_no_similar_line(db, ss, failure):
    w = make_world(db)
    if failure == "http_500":
        ss.route("POST", SIMILAR_PATH, status=500, json_body={"error": {"code": "boom", "message": "down"}})
    else:
        ss.call_raises = httpx.ConnectError("cannot reach shared.test")
    res, step = propose(db, w, CREATE, dict(FIELDS))
    assert res.status == "proposed" and step is not None
    assert "similar" not in step["summary"].lower()
    assert not leaks(step["summary"], res.message)


# ------------------------------------------------------------------ AC-R2-5 / 6 confirm creates


def test_AC_R2_5_confirm_sends_exactly_one_create_with_the_linked_users_fields(db, ss):
    w = make_world(db)
    _, row = store(db, w, [(CREATE, dict(FIELDS))])
    assert posts(ss, CREATE_PATH) == []

    outcome = confirm(db, w, row)

    assert [s["status"] for s in outcome.steps] == ["done"]
    (call,) = posts(ss, CREATE_PATH)
    body = call["json"]
    assert body["problem"] == FIELDS["problem"]
    assert body["title"] == FIELDS["title"]
    assert body["desired_outcome"] == FIELDS["desired_outcome"]
    assert body["use_cases"] == FIELDS["use_cases"]
    assert body["current_workaround"] == FIELDS["current_workaround"]
    assert body["submitter_crm_user_id"] == w.user_id
    assert body["submitter_phone"] == phone_of(db, w)
    assert body["product_id"] == PRODUCT
    assert body["is_test"] is True
    assert str(uuid.UUID(body["intake_ref"])) == body["intake_ref"]
    assert call["headers"]["authorization"] == f"Bearer {INTAKE_KEY}"
    assert action_row(db, row.id).steps[0]["status"] == "done"


def test_AC_R2_5_an_operator_confirming_still_creates_as_the_linked_user(db, ss):
    w = make_world(db)
    op = operator_with(db, BOARD_VIEW)
    _, row = store(db, w, [(CREATE, dict(FIELDS))], operator=op)
    confirm(db, w, row, operator=op)
    (call,) = posts(ss, CREATE_PATH)
    assert call["json"]["submitter_crm_user_id"] == w.user_id
    assert call["json"]["submitter_crm_user_id"] != op
    assert call["json"]["submitter_phone"] == phone_of(db, w)


def test_AC_R2_5_intake_ref_is_stable_for_the_same_text_and_differs_for_other_text(db, ss):
    w = make_world(db)
    for fields in (dict(FIELDS), dict(FIELDS), {**FIELDS, "problem": "A different problem entirely"}):
        _, row = store(db, w, [(CREATE, fields)])
        confirm(db, w, row)
    refs = [c["json"]["intake_ref"] for c in posts(ss, CREATE_PATH)]
    assert len(refs) == 3
    assert refs[0] == refs[1] != refs[2]


def test_AC_R2_5_two_ideas_in_one_proposal_make_two_creates(db, ss):
    w = make_world(db)
    other = {**FIELDS, "problem": "Prices should show the promo in red", "title": "Promo in red"}
    _, row = store(db, w, [(CREATE, dict(FIELDS)), (CREATE, other)])
    outcome = confirm(db, w, row)
    assert [s["status"] for s in outcome.steps] == ["done", "done"]
    calls = posts(ss, CREATE_PATH)
    assert len(calls) == 2
    assert calls[0]["json"]["intake_ref"] != calls[1]["json"]["intake_ref"]


def test_AC_R2_6_the_reply_names_the_number_the_link_the_gaps_and_that_it_is_a_test(db, ss):
    w = make_world(db)
    idea_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": idea_id, "idea_number": "IDEA-0184", "status": "captured", "title": "t"},
    )
    _, row = store(db, w, [(CREATE, {"problem": PROBLEM})])  # only the required field given
    outcome = confirm(db, w, row)
    assert outcome.steps[0]["status"] == "done"
    assert action_row(db, row.id).steps[0]["result_id"] == idea_id
    assert "result_id" not in outcome.steps[0]  # an id never reaches the API shape
    reply = outcome.reply_text
    assert "IDEA-0184" in reply
    assert f"{CRM}/ideas/{idea_id}" in reply
    for label in ("Desired outcome", "Use cases", "Current workaround"):
        assert label in reply
    assert "test" in reply.lower()


def test_AC_R2_6_a_create_with_no_idea_number_never_says_none(db, ss):
    w = make_world(db)
    idea_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": idea_id, "idea_number": None, "status": "captured", "title": "t"},
    )
    _, row = store(db, w, [(CREATE, {"problem": PROBLEM})])
    outcome = confirm(db, w, row)
    assert outcome.steps[0]["status"] == "done"
    assert "None" not in outcome.reply_text, outcome.reply_text
    assert f"{CRM}/ideas/{idea_id}" in outcome.reply_text


# ------------------------------------------------------------------ AC-R2-7 failure at confirm


def failure_texts(outcome):
    return [outcome.reply_text, *[(s.get("error") or "") for s in outcome.steps]]


def says_not_created(reply):
    low = reply.lower()
    return "created" in low and ("not" in low or "n't" in low)


@pytest.mark.parametrize("how", ["transport", "http_500", "bad_body"])
def test_AC_R2_7_ss_down_at_confirm_fails_the_step_plainly_with_no_url_key_or_id(db, ss, how):
    w = make_world(db)
    _, row = store(db, w, [(CREATE, dict(FIELDS))])
    detail = f"{SS_BASE} {INTAKE_KEY} {uuid.uuid4()}"
    if how == "transport":
        ss.call_raises = httpx.ConnectError(f"cannot reach {detail}")
    elif how == "http_500":
        ss.route("POST", CREATE_PATH, status=500, json_body={"error": {"code": "boom", "message": detail}})
    else:
        ss.route("POST", CREATE_PATH, json_body={"status": "captured", "idea_id": "not-a-uuid"})
    outcome = confirm(db, w, row)
    assert [s["status"] for s in outcome.steps] == ["failed"]
    assert says_not_created(outcome.reply_text), outcome.reply_text
    assert not leaks(*failure_texts(outcome))


def test_AC_R2_7_ss_not_configured_at_confirm_fails_the_step_plainly(db, ss, monkeypatch):
    blank_embed_settings(monkeypatch)
    w = make_world(db, configured=False)
    _, row = store(db, w, [(CREATE, dict(FIELDS))])
    outcome = confirm(db, w, row)
    assert [s["status"] for s in outcome.steps] == ["failed"]
    assert says_not_created(outcome.reply_text), outcome.reply_text
    assert not leaks(*failure_texts(outcome))
    assert ss.calls == []


# ------------------------------------------------------------------ AC-R2-8 cancel


def test_AC_R2_8_cancelling_sends_no_create(db, ss):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, row = store(db, w, [(CREATE, dict(FIELDS))])
    outcome = actions.cancel(db, w.respond_id, str(row.id))
    assert outcome.status == "cancelled"
    assert posts(ss, CREATE_PATH) == []
    assert action_row(db, row.id).status == "cancelled"


# ------------------------------------------------------------------ AC-R2-9 the list


def list_ideas(db, w, args=None, *, seen=None, operator=None):
    from app.services.chatbot.agent import writes

    seen = set() if seen is None else seen
    return writes.run_user_read(db, ctx_of(db, w, operator), LIST, args or {}, seen), seen


def create_through(db, w, ss, *, title, number, idea_id, ok=True, cancel=False):
    """Propose and confirm (or cancel) one create whose ss answer is scripted. Returns the idea id."""
    from app.services.chatbot.agent import actions

    if ok:
        ss.route(
            "POST", CREATE_PATH,
            json_body={"idea_id": idea_id, "idea_number": number, "status": "captured", "title": title},
        )
    else:
        ss.route("POST", CREATE_PATH, status=500, json_body={"error": {"code": "boom", "message": "x"}})
    _, row = store(db, w, [(CREATE, {**FIELDS, "title": title})])
    if cancel:
        actions.cancel(db, w.respond_id, str(row.id))
    else:
        confirm(db, w, row)
    return idea_id


def test_AC_R2_9_the_list_merges_ss_mine_with_this_contacts_executed_creates(db, ss):
    w = make_world(db)
    ss_id = str(uuid.uuid4())
    ss.route(
        "GET", "/embed/ideas",
        json_body=[{"id": ss_id, "ideaNumber": "IDEA-0007", "title": "From the board zzt", "isMine": True}],
    )
    made = create_through(db, w, ss, title="Made by the agent zzt", number="IDEA-0184", idea_id=str(uuid.uuid4()))

    out, seen = list_ideas(db, w)

    assert out.status == "ok"
    body = json.dumps(out.data, default=str)
    assert "From the board zzt" in body and ss_id in body
    assert "Made by the agent zzt" in body and made in body
    assert {ss_id.lower(), made.lower()} <= seen
    (listing,) = [c for c in ss.calls if c["method"] == "GET" and c["path"] == "/embed/ideas"]
    assert listing["query"].get("mine") == "true"


def test_AC_R2_9_one_row_per_idea_id_when_ss_also_returns_the_test_idea(db, ss):
    w = make_world(db)
    made = create_through(db, w, ss, title="Dup check zzt", number="IDEA-0555", idea_id=str(uuid.uuid4()))
    ss.route(
        "GET", "/embed/ideas",
        json_body=[{"id": made, "ideaNumber": "IDEA-0555", "title": "Dup check zzt", "isMine": True}],
    )
    out, _ = list_ideas(db, w)
    assert json.dumps(out.data, default=str).count("IDEA-0555") == 1


def test_AC_R2_9_failed_cancelled_and_other_contacts_creates_are_not_listed(db, ss):
    w = make_world(db)
    other = another_world(db)
    kept = create_through(db, w, ss, title="Kept idea zzt", number="IDEA-0201", idea_id=str(uuid.uuid4()))
    create_through(db, w, ss, title="Failed idea zzt", number="IDEA-0202", idea_id=str(uuid.uuid4()), ok=False)
    cancelled_id = str(uuid.uuid4())
    create_through(
        db, w, ss, title="Cancelled idea zzt", number="IDEA-0203", idea_id=cancelled_id, cancel=True
    )
    foreign_id = create_through(
        db, other, ss, title="Foreign idea zzt", number="IDEA-0204", idea_id=str(uuid.uuid4())
    )
    ss.route("GET", "/embed/ideas", json_body=[])

    out, seen = list_ideas(db, w)

    body = json.dumps(out.data, default=str)
    assert "Kept idea zzt" in body and kept in body
    for absent in ("Failed idea zzt", "Cancelled idea zzt", "Foreign idea zzt", cancelled_id, foreign_id):
        assert absent not in body, absent
    assert foreign_id.lower() not in seen and cancelled_id.lower() not in seen


def test_AC_R2_9_another_users_steps_on_this_contact_are_not_listed(db, ss):
    w = make_world(db)
    old_user = seed_user(db, contact_pk=None)  # the contact's linked user before it changed
    mine = create_through(db, w, ss, title="Current user idea zzt", number="IDEA-0301", idea_id=str(uuid.uuid4()))
    theirs = create_through(db, w, ss, title="Former user idea zzt", number="IDEA-0302", idea_id=str(uuid.uuid4()))
    db.execute(
        text("UPDATE agent_actions SET user_id = :u WHERE steps::text LIKE :like"),
        {"u": old_user, "like": f"%{theirs}%"},
    )
    db.commit()
    ss.route("GET", "/embed/ideas", json_body=[])

    out, seen = list_ideas(db, w)

    body = json.dumps(out.data, default=str)
    assert "Current user idea zzt" in body and mine in body
    assert "Former user idea zzt" not in body and theirs not in body
    assert theirs.lower() not in seen


def test_AC_R2_9_an_ss_failure_is_a_typed_error_with_no_url_or_key(db, ss):
    w = make_world(db)
    ss.call_raises = httpx.ConnectError(f"cannot reach {SS_BASE} {INTAKE_KEY}")
    out, _ = list_ideas(db, w)
    assert out.status == "error"
    assert not leaks(out.message, json.dumps(out.data, default=str))


# ------------------------------------------------------------------ AC-R2-10 / 11 / 12 update

IDEA = "7c1d0b7e-0000-4000-8000-00000000b001"
IDEA_PATH = f"/embed/ideas/{IDEA}"


def idea_body(**over):
    body = {
        "id": IDEA, "ideaNumber": "IDEA-0042", "isMine": True, "title": "Old title", "problem": "Old problem",
        "desiredOutcome": "Old outcome", "useCases": ["Old use"], "currentWorkaround": "Old workaround",
    }
    body.update(over)
    return body


class Idea:
    """A mutable ss idea the fake serves, so a test can change it between proposal and confirm."""

    def __init__(self, ss, **over):
        self.state = idea_body(**over)
        ss.routes[("GET", IDEA_PATH)] = self.serve
        ss.routes[("PATCH", IDEA_PATH)] = self.patch

    def serve(self, request):
        return httpx.Response(200, json=copy.deepcopy(self.state), request=request)

    def patch(self, request):
        return httpx.Response(200, json=copy.deepcopy(self.state), request=request)


def test_AC_R2_10_an_unseen_idea_id_is_invalid(db, ss):
    w = make_world(db)
    Idea(ss)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "title": "New title"}, seen=[])
    assert res.status == "invalid" and step is None
    assert patches(ss) == []


def test_AC_R2_10_no_field_given_is_invalid(db, ss):
    w = make_world(db)
    Idea(ss)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA}, seen=[IDEA])
    assert res.status == "invalid" and step is None


@pytest.mark.parametrize("extra", [{"is_test": True}, {"submitter_crm_user_id": "x"}, {"colour": "red"}])
def test_AC_R2_10_unknown_or_forbidden_arguments_are_invalid(db, ss, extra):
    w = make_world(db)
    Idea(ss)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "title": "New title", **extra}, seen=[IDEA])
    assert res.status == "invalid" and step is None


def test_AC_R2_10_an_own_idea_is_proposed_and_the_summary_names_the_field(db, ss):
    w = make_world(db)
    Idea(ss)
    res, step = propose(
        db, w, UPDATE, {"idea_id": IDEA, "title": "New title", "desired_outcome": "New outcome"}, seen=[IDEA]
    )
    assert res.status == "proposed" and step is not None
    low = step["summary"].lower()
    assert "title" in low and "outcome" in low
    assert "problem" not in low
    assert not UUID_RE.search(step["summary"])
    assert patches(ss) == []


@pytest.mark.parametrize("slugs", [(BOARD_VIEW,), (BOARD_VIEW, MANAGE)], ids=["view_only", "holds_manage"])
def test_AC_R2_10_an_idea_that_is_not_theirs_is_refused_even_with_manage(db, ss, slugs):
    w = make_world(db, slugs=slugs)
    Idea(ss, isMine=False)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "title": "New title"}, seen=[IDEA])
    assert res.status in ("denied", "invalid") and step is None
    assert OWN_ONLY_MSG in res.message
    assert patches(ss) == []


def test_AC_R2_11_an_operator_without_manage_is_refused_with_no_patch_and_no_operator_session(db, ss):
    w = make_world(db)
    op = operator_with(db, BOARD_VIEW)
    Idea(ss)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "title": "New title"}, seen=[IDEA], operator=op)
    assert res.status in ("denied", "invalid") and step is None
    assert patches(ss) == []
    # a read as the linked user is allowed; no embed session may ever be minted for the operator
    subjects = [
        jwt.decode(c["assertion"], SIGNING_SECRET, algorithms=["HS256"], audience="ideation-embed")["sub"]
        for c in ss.session_calls
    ]
    assert op not in subjects
    assert all(sub == w.user_id for sub in subjects)


def test_AC_R2_11_an_operator_with_manage_proposes_and_the_patch_runs_as_the_linked_user(db, ss):
    w = make_world(db)
    op = operator_with(db, BOARD_VIEW, MANAGE)
    Idea(ss)
    _, row = store(db, w, [(UPDATE, {"idea_id": IDEA, "title": "New title"})], seen=[IDEA], operator=op)

    outcome = confirm(db, w, row, operator=op)

    assert [s["status"] for s in outcome.steps] == ["done"]
    (patch_call,) = patches(ss)
    token = patch_call["headers"]["authorization"].removeprefix("Bearer ")
    assertion = ss.session_calls[ss.tokens.index(token)]["assertion"]
    claims = jwt.decode(assertion, SIGNING_SECRET, algorithms=["HS256"], audience="ideation-embed")
    assert claims["sub"] == w.user_id and claims["sub"] != op
    # every token used for this update belongs to the linked user, never the operator
    assert all(
        jwt.decode(s["assertion"], SIGNING_SECRET, algorithms=["HS256"], audience="ideation-embed")["sub"]
        == w.user_id
        for s in ss.session_calls
    )


def test_AC_R2_11_an_operator_with_manage_still_cannot_edit_an_idea_that_is_not_the_linked_users(db, ss):
    w = make_world(db)
    op = operator_with(db, BOARD_VIEW, MANAGE)
    Idea(ss, isMine=False)
    res, step = propose(db, w, UPDATE, {"idea_id": IDEA, "title": "New title"}, seen=[IDEA], operator=op)
    assert res.status in ("denied", "invalid") and step is None
    assert patches(ss) == []


@pytest.mark.parametrize(
    "linked, operator, expect",
    [
        ((BOARD_VIEW,), (BOARD_VIEW,), "proposed"),
        ((BOARD_VIEW,), ("inventory.stock.view",), "refused"),
        (("inventory.stock.view",), (BOARD_VIEW,), "refused"),
    ],
    ids=["both_hold_it", "operator_lacks_it", "linked_lacks_it"],
)
def test_AC_R2_11_a_create_needs_board_view_on_both(db, ss, linked, operator, expect):
    w = make_world(db, slugs=linked)
    op = operator_with(db, *operator)
    res, step = propose(db, w, CREATE, dict(FIELDS), operator=op)
    if expect == "proposed":
        assert res.status == "proposed"
    else:
        assert res.status in ("denied", "invalid") and step is None
        assert posts(ss, CREATE_PATH) == []


def test_AC_R2_12_confirm_sends_one_patch_with_only_the_changed_fields_in_ss_names(db, ss):
    w = make_world(db)
    Idea(ss)
    args = {
        "idea_id": IDEA, "title": "New title", "desired_outcome": "New outcome",
        "use_cases": ["One", "Two"], "current_workaround": "New workaround",
    }
    _, row = store(db, w, [(UPDATE, args)], seen=[IDEA])
    assert patches(ss) == []

    outcome = confirm(db, w, row)

    assert [s["status"] for s in outcome.steps] == ["done"]
    (call,) = patches(ss)
    assert call["path"] == IDEA_PATH
    assert call["json"] == {
        "title": "New title", "desiredOutcome": "New outcome", "useCases": ["One", "Two"],
        "currentWorkaround": "New workaround",
    }


def test_AC_R2_12_only_the_fields_given_are_sent(db, ss):
    w = make_world(db)
    Idea(ss)
    _, row = store(db, w, [(UPDATE, {"idea_id": IDEA, "desired_outcome": "Only this"})], seen=[IDEA])
    confirm(db, w, row)
    (call,) = patches(ss)
    assert call["json"] == {"desiredOutcome": "Only this"}


def test_AC_R2_12_the_change_lines_read_before_and_after_in_words(db, ss):
    w = make_world(db)
    Idea(ss)
    _, row = store(db, w, [(UPDATE, {"idea_id": IDEA, "title": "New title"})], seen=[IDEA])
    outcome = confirm(db, w, row)
    changes = outcome.steps[0]["changes"]
    assert any(c.get("before") == "Old title" and c.get("after") == "New title" for c in changes), changes
    assert not any(UUID_RE.search(json.dumps(c)) for c in changes)


def test_AC_R2_12_an_idea_changed_since_the_proposal_is_refused_and_no_patch_is_sent(db, ss):
    w = make_world(db)
    idea = Idea(ss)
    _, row = store(db, w, [(UPDATE, {"idea_id": IDEA, "title": "New title"})], seen=[IDEA])
    idea.state["title"] = "Edited on the board meanwhile"

    outcome = confirm(db, w, row)

    assert outcome.status == "rejected"
    assert patches(ss) == []


# ------------------------------------------------------------------ AC-R2-13 end to end


def test_AC_R2_13_propose_confirm_list_propose_update_confirm_through_a_turn(db, ss):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    made_id = str(uuid.uuid4())
    ss.route(
        "POST", CREATE_PATH,
        json_body={"idea_id": made_id, "idea_number": "IDEA-0184", "status": "captured", "title": "t"},
    )
    ss.route("GET", "/embed/ideas", json_body=[])  # ss's list omits the new test idea
    idea_path = f"/embed/ideas/{made_id}"
    ss.route("GET", idea_path, json_body={**idea_body(id=made_id), "isMine": True})
    ss.route("PATCH", idea_path, json_body=idea_body(id=made_id, title="Nearest warehouse first"))

    # turn 1: the model proposes the idea, nothing is created yet
    first, prov1 = go(
        db, w, [round_of(tc(CREATE, dict(FIELDS), "c1")), answer_("I have prepared the idea.")],
        text_="I have an idea: the stock list is too long on my phone",
    )
    assert {CREATE, UPDATE, LIST} <= tool_names(prov1)
    assert first.pending_action is not None
    assert posts(ss, CREATE_PATH) == []
    pending = actions.pending_action(db, w.respond_id)
    outcome = confirm(db, w, pending)
    assert outcome.steps[0]["status"] == "done"
    assert action_row(db, pending.id).steps[0]["result_id"] == made_id
    assert "result_id" not in outcome.steps[0]
    assert len(posts(ss, CREATE_PATH)) == 1

    # turn 2: list finds the test idea although ss's list omits it, then propose the edit
    second, _ = go(
        db, w,
        [
            round_of(tc(LIST, {}, "l1")),
            round_of(tc(UPDATE, {"idea_id": made_id, "title": "Nearest warehouse first"}, "u1")),
            answer_("I have prepared the change."),
        ],
        text_="change that idea's title to Nearest warehouse first",
    )
    assert second.pending_action is not None
    assert patches(ss) == []
    pending = actions.pending_action(db, w.respond_id)
    outcome = confirm(db, w, pending)
    assert outcome.steps[0]["status"] == "done"

    assert len(posts(ss, CREATE_PATH)) == 1
    (call,) = patches(ss)
    assert call["path"] == idea_path and call["json"] == {"title": "Nearest warehouse first"}
