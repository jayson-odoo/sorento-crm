"""Pre-route regression guard for the bubble record-context feature.

Covers UAC §3 (pre-route discipline) + §4.7 (session-var isolation) for
``PLAN-bubble-record-context-and-guides``.

Two kinds of test, deliberately separated (see memory feedback_no_overfit_llm_nlp):

  * **Routing tests** (offline, deterministic) — stub the classifier verdict and
    the assembler so we test the FORK LOGIC only: record-class+entity bypasses
    the agent loop; everything else reaches it. This is the regression firewall
    and must run in CI.
  * **Classifier-quality eval** (live LLM, opt-in) — paraphrase robustness for
    ``intent_is_record_class`` itself. Because the classifier is a GENERAL
    semantic judgment (an LLM call), not a keyword whitelist, its quality can
    only be tested against a real model. Gated behind ``RUN_LLM_EVALS`` so CI
    stays offline/deterministic; run on demand against a real key.

Mirrors the stub wiring in ``test_ai_assistant_usage.py``.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.ai_assistant import (
    AIAssistantConfig,
    AIAssistantConversation,
    AIAssistantGovernanceEvent,
    AIAssistantMessage,
    AIAssistantUnansweredQuery,
    AIAssistantUsageLog,
    AIAssistantWishlistCluster,
)
from app.models.lookup import LookupBinding
from app.models.user import User
from app.schemas.ai_assistant import (
    AIAssistantAuthContext,
    PageEntityRef,
    PageSnapshotPayload,
)
from app.services.ai_assistant_service import AIAssistantChatService
from app.services.entity_resolver import ResolutionResult


@compiles(JSONB, "sqlite")  # type: ignore[misc]
def _jsonb_sqlite(_type_, _compiler, **_kw):  # noqa: D401, ANN001
    return "TEXT"


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    tables = [
        User.__table__,
        AIAssistantConfig.__table__,
        AIAssistantConversation.__table__,
        AIAssistantMessage.__table__,
        AIAssistantGovernanceEvent.__table__,
        AIAssistantUsageLog.__table__,
        AIAssistantWishlistCluster.__table__,
        AIAssistantUnansweredQuery.__table__,
        LookupBinding.__table__,  # global lookup-write listener queries this on insert
    ]
    Base.metadata.create_all(engine, tables=tables)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_user(db_session: Session) -> str:
    user = User(id="u-1", email="u1@test.com", name="User One", status="ACTIVE")
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture(autouse=True)
def _stub_rate_limit_clause(monkeypatch):
    import app.services.ai_assistant_service as svc_module
    from sqlalchemy import literal

    monkeypatch.setattr(svc_module, "text", lambda _expr: literal(0))


class _Spy:
    """Records whether it was invoked and with what kwargs."""

    def __init__(self, ret):
        self.called = False
        self.kwargs = None
        self._ret = ret

    def __call__(self, **kwargs):
        self.called = True
        self.kwargs = kwargs
        return self._ret


_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


@pytest.fixture
def chat_service(db_session: Session, monkeypatch) -> AIAssistantChatService:
    """Chat service with every external dependency stubbed OFFLINE.

    The record-class branch (classifier verdict, RBAC check, assembler, prose
    render) is stubbed so routing tests are deterministic and make no network
    calls. Individual tests override ``intent_is_record_class`` to drive the
    fork either way.
    """
    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()

    svc.gov.build_auth_context = lambda user_id: AIAssistantAuthContext(  # type: ignore[assignment]
        user_id=user_id,
        role_ids=["r1"],
        permission_slugs=["system.ai_assistant_chat.use"],
        enabled_modules=[],
    )
    svc._reformulate_query = lambda *, config, history, user_message: user_message  # type: ignore[assignment]
    svc._rag_select_tools = lambda *, standalone_query, enabled_tools, top_k: ([], [])  # type: ignore[assignment]
    svc._generate_suggestions = lambda **_k: []  # type: ignore[assignment]

    import app.services.ai_assistant_service as svc_module

    svc_module.resolve_references = lambda _db, _q: ResolutionResult(  # type: ignore[assignment]
        tokens=[], resolutions=[], elapsed_ms=0.0
    )

    # RBAC check inside the pre-route → allow by default (override per test).
    class _AllowPerm:
        def __init__(self, *_a, **_k):
            pass

        def check_user_has_permission(self, *_a, **_k):
            return True

    monkeypatch.setattr(svc_module, "UserPermissionService", _AllowPerm)

    # Assembler → return a synthetic complaint bundle, no DB/network.
    import app.services.record_context_service as rc_module

    class _FakeAssembler:
        def __init__(self, *_a, **_k):
            pass

        def assemble(self, entity_type, entity_id):
            return {
                "entity_type": entity_type,
                "id": entity_id,
                "display_ref": "CMP-2026-0142",
                "current_state": {"status": "rejected", "reason": "Out of warranty"},
            }

    monkeypatch.setattr(rc_module, "RecordContextService", _FakeAssembler)

    return svc


def _complaint_snapshot() -> PageSnapshotPayload:
    return PageSnapshotPayload(
        path="/complaint-management/complaints/c-1",
        search="",
        title="Complaint CMP-2026-0142",
        visible_text="complaint detail",
        entity=PageEntityRef(entity_type="complaint", id="c-1"),
    )


def _no_entity_snapshot() -> PageSnapshotPayload:
    return PageSnapshotPayload(
        path="/dashboard", search="", title="Home", visible_text="home"
    )


# ===========================================================================
# Routing tests (offline, deterministic) — the regression firewall
# ===========================================================================

# --- §3.1 — entity + record-class → assembler, agent loop bypassed ----------
def test_record_class_with_entity_bypasses_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service.intent_is_record_class = lambda _m: True  # type: ignore[assignment]
    agent = _Spy(("should-not-run", [], _USAGE))
    render = _Spy(("grounded answer from facts", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was this complaint rejected and who approved it?",
        page_snapshot=_complaint_snapshot(),
    )

    assert render.called is True, "record-class+entity must use the assembler render path"
    assert agent.called is False, (
        "record-class question on an entity page must take the deterministic "
        "assembler pre-route, not the MCP agent loop"
    )


# --- §3.2 — entity present but catalog question → agent loop (no theft) ------
def test_catalog_question_with_entity_uses_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service.intent_is_record_class = lambda _m: False  # type: ignore[assignment]
    agent = _Spy(("active promos: ...", [], _USAGE))
    render = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="What promotions are active right now?",
        page_snapshot=_complaint_snapshot(),
    )

    assert agent.called is True, (
        "a catalog question must reach the MCP agent loop even when an entity "
        "is on screen — the pre-route must not steal §1 operational questions"
    )
    assert render.called is False


# --- §3.4 — record phrasing but NO entity → agent loop, never assembler ------
def test_record_phrasing_without_entity_uses_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService
):
    # Even if the classifier would say record-class, no entity → no assembler.
    chat_service.intent_is_record_class = lambda _m: True  # type: ignore[assignment]
    agent = _Spy(("...", [], _USAGE))
    render = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was it rejected?",
        page_snapshot=_no_entity_snapshot(),
    )

    assert agent.called is True, (
        "without page_snapshot.entity the assembler has no id; must fall back "
        "to the agent loop / clarify, never call the assembler"
    )
    assert render.called is False


# --- §3.5 — RBAC denial → degrade to agent loop, no record facts leaked ------
def test_rbac_denied_degrades_to_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService, monkeypatch
):
    import app.services.ai_assistant_service as svc_module

    class _DenyPerm:
        def __init__(self, *_a, **_k):
            pass

        def check_user_has_permission(self, *_a, **_k):
            return False

    monkeypatch.setattr(svc_module, "UserPermissionService", _DenyPerm)
    chat_service.intent_is_record_class = lambda _m: True  # type: ignore[assignment]
    agent = _Spy(("...", [], _USAGE))
    render = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was this complaint rejected?",
        page_snapshot=_complaint_snapshot(),
    )

    assert render.called is False, "no assembler render when the user lacks the view permission"
    assert agent.called is True, "RBAC denial degrades to the agent loop, not a crash"


# --- §4.7 — bubble path must never touch respond_contacts.session_vars ------
def test_bubble_path_never_writes_contact_session_vars(
    seeded_user: str, chat_service: AIAssistantChatService
):
    """The n8n WhatsApp brain owns ``respond_contacts.session_vars`` (keyed by
    respond_io_id). The bubble (keyed by user_id+conversation_id) must keep its
    state in ai_assistant_* tables only — never cross into the contact blob.
    """
    import app.services.ai_assistant_service as svc_module

    assert not hasattr(svc_module, "overwrite_for_contact"), (
        "bubble service imported the n8n session-var writer — isolation breach"
    )

    chat_service.intent_is_record_class = lambda _m: True  # type: ignore[assignment]
    chat_service._render_record_answer = _Spy(("ans", [], _USAGE))  # type: ignore[assignment]
    chat_service._run_agent_loop = _Spy(("ans", [], _USAGE))  # type: ignore[assignment]

    # No respond_contacts table exists in this fixture; any write would raise.
    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was this complaint rejected?",
        page_snapshot=_complaint_snapshot(),
    )


# --- A6 fusion: "what should I do now" must be state-grounded ----------------
# Routing-only assertion: a next-step question on an entity page must NOT be
# answered by the bare agent loop — it must take the assembler render path
# (which is permitted one user_guides_read call to fuse guide steps with the
# record's current state). Classifier verdict stubbed; the live verdict for
# this phrasing is covered by the opt-in eval below.
def test_what_should_i_do_now_takes_record_path(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service.intent_is_record_class = lambda _m: True  # type: ignore[assignment]
    agent = _Spy(("generic advice", [], _USAGE))
    render = _Spy(("state-grounded next step", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="What should I do now?",
        page_snapshot=_complaint_snapshot(),
    )

    assert render.called is True
    assert agent.called is False, (
        "'what should I do now' must be grounded by the complaint's current "
        "state (assembler render + guide), not the generic agent loop alone"
    )


# ===========================================================================
# Classifier-quality eval (live LLM, opt-in) — paraphrase robustness
# ===========================================================================
# NOTE (anti-overfit — see memory feedback_no_overfit_llm_nlp):
# intent_is_record_class is a GENERAL semantic judgment, NOT a keyword
# whitelist. These cases are ILLUSTRATIVE of a general capability, not an
# allowlist to match literally — each concept appears in multiple paraphrases
# plus near-miss negatives, so passing requires genuine generalization. This
# can only be exercised against a real model, so it is gated behind
# RUN_LLM_EVALS to keep CI offline. Do NOT make a case pass by special-casing.

_RUN_LLM_EVALS = os.getenv("RUN_LLM_EVALS") == "1"


@pytest.mark.skipif(
    not _RUN_LLM_EVALS,
    reason="live-LLM classifier eval; set RUN_LLM_EVALS=1 with a configured provider key",
)
@pytest.mark.parametrize(
    "message, expected",
    [
        # --- record-fact intent, many phrasings (A1-A4 + taxonomy) ---
        ("What is this complaint about?", True),
        ("Give me a summary of this case", True),
        ("Who approved this complaint?", True),
        ("Who signed off on it?", True),
        ("Which manager cleared this one?", True),
        ("How long did one person take to approve this complaint?", True),
        ("What was the turnaround time on the approval?", True),
        ("Why was this rejected?", True),
        ("What's the reason it got knocked back?", True),
        ("Where does this stand on the SLA?", True),
        ("What should I do now?", True),
        # --- generic procedural (process flow) — NOT this record ---
        ("What's the process flow for a complaint?", False),
        ("Walk me through how complaints move through the system", False),
        # --- catalog / data lookups — NOT record-class ---
        ("What promotions are active?", False),
        ("Any deals running right now?", False),
        ("Show me products from brand X", False),
        ("When is product ABC arriving?", False),
        ("How do I upload an attachment?", False),
        # --- near-miss negatives: record-ish words, not about THIS record ---
        ("How do I approve a complaint in general?", False),
        ("What does 'rejected' status mean?", False),
        ("Can I reject orders in bulk?", False),
    ],
)
def test_intent_is_record_class_generalizes(
    chat_service: AIAssistantChatService, message: str, expected: bool
):
    assert bool(chat_service.intent_is_record_class(message)) is expected
