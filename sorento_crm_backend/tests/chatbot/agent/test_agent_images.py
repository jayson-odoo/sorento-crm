"""AGENT-PANEL-COMPOSER Phase 2 (red): `run_agent_turn(..., images=)` and the agent's provider name.

UAC: T8 (`_run` passes `images=` to every model call of the turn except the compaction call), T12
(history is text only). T10 (the envelope's `files`) is asserted through the route in
tests/chatbot/test_panel_send_files.py, because `run_agent_turn` is not given file metadata by the pinned
signature; see the report.

Same shape as test_agent_loop.py: blank Postgres schema, a scripted provider, no MCP.
"""
from __future__ import annotations

import base64

from app.models.chatbot_turn import ChatbotTurn
from app.services.llm_provider import ImagePart
from tests.chatbot.agent._turns import seed_turn
from tests.chatbot.agent.test_agent_loop import (  # noqa: F401  (fixtures and helpers)
    CATALOG,
    Mcp,
    ScriptedProvider,
    answer,
    asks,
    call,
    contact,
    db,
    plain,
    run,
)

IMAGE = ImagePart(mime="image/jpeg", data_b64=base64.b64encode(b"\xff\xd8\xffZZT").decode())


class KwProvider(ScriptedProvider):
    """Records the extra keyword arguments of each call (`images`, ...)."""

    def __init__(self, script):
        super().__init__(script)
        self.kwargs: list[dict] = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.kwargs.append(dict(kw))
        return super().chat(messages, tools=tools, reasoning_effort=reasoning_effort, **kw)


def test_images_reach_every_round_of_the_turn(db, contact):
    provider = KwProvider([asks(call()), answer("There are 12 units.", figures=[{"value": "12", "call_id": "call-1"}])])

    run(db, contact, provider, images=[IMAGE])

    assert len(provider.kwargs) == 2
    for kw in provider.kwargs:
        assert kw.get("images") == [IMAGE]


def test_a_turn_without_images_sends_none(db, contact):
    provider = KwProvider([answer("Hello.")])

    run(db, contact, provider)

    assert not provider.kwargs[0].get("images")


def test_the_compaction_call_gets_no_images_but_the_rounds_do(db, contact):
    from app.models.user import SystemSetting
    from app.services.chatbot.agent import memory
    from app.services.chatbot.agent.access import build_context, grants_hash

    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(db, contact["respond_id"], user_id=ctx.user_id, grants_hash=grants_hash(ctx))
    for minute in range(10):
        seed_turn(db, conv, minute=minute, text=f"question {minute} " + "x" * 400, reply="answer " + "y" * 400)
    row = db.query(SystemSetting).first() or SystemSetting()
    row.chatbot_agent_compact_tokens = 100
    db.add(row)
    db.flush()
    provider = KwProvider([plain("Earlier: ten questions."), answer("Hello.")])

    run(db, contact, provider, images=[IMAGE])

    assert [s["effort"] for s in provider.seen] == [None, "low"], "the first call was not the compaction call"
    assert not provider.kwargs[0].get("images"), "the summary call was sent the image"
    assert provider.kwargs[1].get("images") == [IMAGE]


def test_t12_a_later_turn_resends_no_image_bytes(db, contact):
    first = KwProvider([answer("Saw it.")])
    run(db, contact, first, text="what is this error\n\n[image: shot.png]", images=[IMAGE])
    second = KwProvider([answer("Still here.")])

    run(db, contact, second, text="and now?")

    assert not second.kwargs[0].get("images")
    history = "\n".join(str(m.get("content") or "") for m in second.seen[0]["messages"])
    assert "[image: shot.png]" in history
    assert IMAGE.data_b64 not in history


def test_the_turn_text_with_a_sheet_block_is_what_the_envelope_stores(db, contact):
    block = 'Attached file "d.xlsx", sheet "Dealers": 1 rows.\n| Phone |\n| --- |\n| 601 |'
    text = f"grant access to these\n\n{block}"

    result = run(db, contact, KwProvider([answer("ok")]), text=text)

    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
    assert row.envelope["text"] == text


def test_agent_provider_name_defaults_to_the_agents_default_provider(db, contact):
    from app.services.chatbot.agent import loop

    assert loop.agent_provider_name(db) == loop.DEFAULT_PROVIDER == "gemini"


def test_n15_compaction_folds_a_file_turn_as_the_typed_words_and_the_reply_not_the_quoted_files(db, contact):
    from app.models.user import SystemSetting
    from app.services.chatbot.agent import memory
    from app.services.chatbot.agent.access import build_context, grants_hash

    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(db, contact["respond_id"], user_id=ctx.user_id, grants_hash=grants_hash(ctx))
    for minute in range(10):
        turn = seed_turn(db, conv, minute=minute, text=f"question {minute} " + "x" * 400, reply="answer " + "y" * 400)
        if minute == 0:
            turn.envelope = {
                **turn.envelope,
                "text": "grant access to these",
                "file_text": 'Attached file "d.xlsx", sheet "Dealers": 1 rows.\n| Phone |\n| --- |\n| 60123456789 |',
            }
            turn.response = {**turn.response, "reply_text": "ZZT proposed the grant."}
    row = db.query(SystemSetting).first() or SystemSetting()
    row.chatbot_agent_compact_tokens = 100
    db.add(row)
    db.flush()
    provider = KwProvider([plain("Earlier: a grant."), answer("Hello.")])

    run(db, contact, provider)

    prompt = provider.seen[0]["messages"][0]["content"]
    assert "Fold the earlier conversation" in prompt, "the first call was not the compaction call"
    assert "User: grant access to these\nAssistant: ZZT proposed the grant." in prompt
    assert "User: Files the user attached" not in prompt, "the quoted files message was folded as the user's words"
    assert "Assistant: grant access to these" not in prompt
