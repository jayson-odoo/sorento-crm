"""Service-level tests for the M2.5 role-split nodes (PLAN §9 S4).

Covers the three ``AIAssistantChatService`` methods added for the explicit
planner / semantic-compressor decomposition:

- ``_role_split_enabled`` — reads the ``ai_assistant_role_split_enabled`` flag
  off the ``system_settings`` singleton (default / missing-row → False).
- ``_run_planner`` — one LLM call producing an ordered tool plan, with a
  ``planner`` trace span; provider failure → None + error span, never raises.
- ``_compress_tool_output`` — semantic compression of sizeable tool JSON, with
  a ``semantic_compressor <tool>`` span; skipped for ``user_guides_read`` (link
  preservation) and for < 400-char payloads; provider failure → raw unchanged +
  error span, never raises.

Everything runs against a blank copy of the real Postgres schema, so JSONB
columns on ``SystemSetting`` are genuine JSONB. Prompt resolution rides the
registry's hardcoded fallback (no prompt rows seeded → ``version=None``), so no
prompt rows need seeding.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy.orm import Session

from app.models.ai_assistant import AIAssistantConfig
from app.models.user import SystemSetting
from app.services.ai_assistant_service import AIAssistantChatService
from app.services.ai_trace import KIND_LLM, TurnTrace
from tests._pg_fixture import blank_session


@pytest.fixture
def db() -> Session:
    """A blank Postgres schema, rolled back after the test.

    Was an in-memory sqlite engine over a hand-listed subset of tables with
    JSONB/ARRAY compiled to TEXT. The blank schema carries every table, so the
    defensive listener-table list is no longer needed.
    """
    with blank_session() as session:
        yield session


@pytest.fixture
def service(db: Session) -> AIAssistantChatService:
    return AIAssistantChatService(db)


# --- fakes ------------------------------------------------------------------ #


@dataclass
class _FakeChatResult:
    """ChatResult-shaped payload the trace collector reads token counts off."""

    content: str = "step 1: call stock_balance"
    prompt_tokens: int = 12
    completion_tokens: int = 7
    total_tokens: int = 19
    tool_calls: list = field(default_factory=list)
    raw: object | None = None


class _FakeProvider:
    """Minimal LLMProvider stand-in. ``.chat`` returns a fixed ChatResult and
    records the calls it received so tests can assert it was (or wasn't) hit."""

    def __init__(self, *, content: str = "compressed sentences", raise_exc: Exception | None = None):
        self._content = content
        self._raise = raise_exc
        self.calls: list[dict] = []

    def chat(self, messages, **kw):  # noqa: ANN001
        self.calls.append({"messages": messages, "kw": kw})
        if self._raise is not None:
            raise self._raise
        return _FakeChatResult(content=self._content)


def _cfg() -> AIAssistantConfig:
    """A config object exposing only what the nodes touch (``.model``)."""
    return AIAssistantConfig(model="gpt-4o")


def _trace() -> TurnTrace:
    return TurnTrace(user_id="u-1", conversation_id=None, session_id="s-1", env="test")


def _spans_named(trace: TurnTrace, name: str) -> list:
    return [s for s in trace._spans if s.name == name]


# --------------------------------------------------------------------------- #
# _role_split_enabled                                                         #
# --------------------------------------------------------------------------- #


def test_role_split_enabled_true_when_setting_true(db: Session, service: AIAssistantChatService):
    db.add(SystemSetting(id="ss-1", ai_assistant_role_split_enabled=True))
    db.commit()
    assert service._role_split_enabled() is True


def test_role_split_enabled_false_when_setting_false(db: Session, service: AIAssistantChatService):
    db.add(SystemSetting(id="ss-1", ai_assistant_role_split_enabled=False))
    db.commit()
    assert service._role_split_enabled() is False


def test_role_split_enabled_false_when_no_settings_row(service: AIAssistantChatService):
    # Empty table → row is None → default False (opt-in behavior).
    assert service._role_split_enabled() is False


# --------------------------------------------------------------------------- #
# _run_planner                                                                #
# --------------------------------------------------------------------------- #


def test_run_planner_returns_plan_and_records_span(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(content="1. stock_balance_list\n2. order_list")

    plan = service._run_planner(
        config=_cfg(),
        provider=provider,
        user_message="how much widget stock and any open orders?",
        standalone_query="widget stock level and open orders",
        source_context="crm_inventory_stock_balance_list, crm_order_list",
    )

    assert plan == "1. stock_balance_list\n2. order_list"
    assert len(provider.calls) == 1

    spans = _spans_named(service._turn_trace, "planner")
    assert len(spans) == 1
    span = spans[0]
    assert span.span_kind == KIND_LLM
    assert span.prompt_name == "planner"
    assert span.status == "ok"


def test_run_planner_provider_failure_returns_none_and_error_span(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(raise_exc=RuntimeError("llm down"))

    plan = service._run_planner(
        config=_cfg(),
        provider=provider,
        user_message="anything",
        standalone_query="anything",
        source_context="",
    )

    assert plan is None  # swallowed, not raised
    spans = _spans_named(service._turn_trace, "planner")
    assert len(spans) == 1
    assert spans[0].status == "error"
    assert spans[0].prompt_name == "planner"


def test_run_planner_empty_content_returns_none(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(content="   ")  # whitespace → treated as empty

    plan = service._run_planner(
        config=_cfg(),
        provider=provider,
        user_message="x",
        standalone_query="x",
        source_context="",
    )

    assert plan is None
    # Still records the (successful) LLM span for observability.
    assert len(_spans_named(service._turn_trace, "planner")) == 1


def test_run_planner_without_trace_does_not_crash(service: AIAssistantChatService):
    # No _turn_trace set → span recording guarded, still returns the plan.
    assert service._turn_trace is None
    provider = _FakeProvider(content="the plan")
    plan = service._run_planner(
        config=_cfg(),
        provider=provider,
        user_message="x",
        standalone_query="x",
        source_context="",
    )
    assert plan == "the plan"


# --------------------------------------------------------------------------- #
# _compress_tool_output                                                       #
# --------------------------------------------------------------------------- #


def test_compress_skips_user_guides_read_verbatim(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(content="SHOULD NOT BE USED")
    raw = "x" * 5000  # well over the size threshold, but a guide payload

    out = service._compress_tool_output(
        config=_cfg(),
        provider=provider,
        tool_name="user_guides_read",
        raw_output=raw,
    )

    # Link-preservation rule: guide markdown must reach the model unchanged.
    assert out == raw
    assert provider.calls == []  # provider never invoked
    assert _spans_named(service._turn_trace, "semantic_compressor user_guides_read") == []


def test_compress_skips_small_payload(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(content="SHOULD NOT BE USED")
    raw = '{"rows": 3}'  # < 400 chars

    out = service._compress_tool_output(
        config=_cfg(),
        provider=provider,
        tool_name="crm_inventory_stock_balance_list",
        raw_output=raw,
    )

    assert out == raw
    assert provider.calls == []
    assert not [s for s in service._turn_trace._spans if s.name.startswith("semantic_compressor")]


def test_compress_large_payload_returns_compressed_and_records_span(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(content="Widget: 42 units across 2 warehouses.")
    raw = "y" * 600  # >= 400 chars, non-guide → compress

    out = service._compress_tool_output(
        config=_cfg(),
        provider=provider,
        tool_name="crm_inventory_stock_balance_list",
        raw_output=raw,
    )

    assert out == "Widget: 42 units across 2 warehouses."
    assert len(provider.calls) == 1

    spans = _spans_named(service._turn_trace, "semantic_compressor crm_inventory_stock_balance_list")
    assert len(spans) == 1
    span = spans[0]
    assert span.span_kind == KIND_LLM
    assert span.prompt_name == "semantic_compressor"
    assert span.status == "ok"


def test_compress_provider_failure_returns_raw_and_error_span(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(raise_exc=RuntimeError("llm down"))
    raw = "z" * 600

    out = service._compress_tool_output(
        config=_cfg(),
        provider=provider,
        tool_name="crm_order_list",
        raw_output=raw,
    )

    assert out == raw  # falls back to raw, never raises
    spans = _spans_named(service._turn_trace, "semantic_compressor crm_order_list")
    assert len(spans) == 1
    assert spans[0].status == "error"
    assert spans[0].prompt_name == "semantic_compressor"


def test_compress_empty_content_falls_back_to_raw(service: AIAssistantChatService):
    service._turn_trace = _trace()
    provider = _FakeProvider(content="   ")  # whitespace → empty compression
    raw = "w" * 600

    out = service._compress_tool_output(
        config=_cfg(),
        provider=provider,
        tool_name="crm_order_list",
        raw_output=raw,
    )

    # Empty/failed compression must not lose the tool data.
    assert out == raw
    # A successful LLM span is still recorded.
    assert len(_spans_named(service._turn_trace, "semantic_compressor crm_order_list")) == 1
