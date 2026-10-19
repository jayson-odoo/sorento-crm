"""CHAT-STATE round 6, S6 (red): one UserTurn at ingress replaces the first-line reads (AC-S6-1..3).

CONTRACT (names are the contract):
  * `app.services.chatbot.user_turn.UserTurn`, a frozen dataclass:
      own_text    : str   the customer's own typed line = the first line of the turn's latest user message
                          (exactly what `latest_user_message.split("\\n", 1)[0]` gave);
      quoted_text : str   everything after the first newline ("" when none), i.e. the `reply to: ...` block;
      media       : tuple the attachment reads of the message (descriptions), () when none.
  * `app.services.chatbot.user_turn.from_envelope(envelope, session_block=None) -> UserTurn`, the ONE builder.
    It reads the same text `engine.build_latest_user_message` builds, so the webhook path
    (`/chat/turn`) and #1766's direct ingress (`direct_ingress.envelope_for`) give equal UserTurns.
  * The engine builds it once per turn and the readers below take it instead of re-splitting.

THE FIRST-LINE READS today (grep `split("\\n"...)[0]` / `lines[0]` over the user message):
  1. engine.py ~1096   `_candidate_lines`           latest_user_message.split("\\n", 1)[0]
  2. engine.py ~5007   grounding.ground(message=)   latest_user_message.split("\\n", 1)[0]
  3. engine.py ~10177  fallback language            _ctx_message_text(ctx).split("\\n")[0]
  4. engine.py ~10194  `_turn_language`             (latest_user_message or "").split("\\n")[0]
  5. turn_runtime.with_set_count_from_text   (~1352)  message.strip().splitlines() -> lines[0]
  6. turn_runtime.with_clarify_answer        (~1436)  lines[0]
  7. turn_runtime.set_continue_count         (~1515)  lines[0]
  8. turn_runtime.with_brand_from_offer      (~4570)  lines[0]
(Eight sites read the user message; the UAC says seven. The non-message ones, engine ~9429 comment body,
business ~2352 range line, compose ~734 and refer_asks, are not user-message reads and stay.)
"""
from __future__ import annotations

import inspect

import pytest

from tests.chatbot.test_engine import _envelope


def _mod():
    import importlib

    try:
        return importlib.import_module("app.services.chatbot.user_turn")
    except ModuleNotFoundError:  # noqa: PERF203
        pytest.fail("app.services.chatbot.user_turn does not exist yet (no UserTurn)")


def _env(text=None, *, quoted=None, attachment=None):
    inner = {"type": "text", "text": text} if text is not None else {"type": "attachment"}
    if attachment:
        inner["attachment"] = attachment
    msg = {"messageId": "ZZT-s6", "contactId": "900000008", "channelId": "whatsapp", "traffic": "incoming", "message": inner}
    if quoted is not None:
        msg["replyTo"] = {"message": {"text": quoted}}
    env = _envelope()
    env.message["message"] = msg
    return env


def _old_latest(env):
    from app.services.chatbot.engine import build_latest_user_message

    return build_latest_user_message(env, None)


MESSAGES = [
    ("plain-en", dict(text="price for SRTWC8517")),
    ("plain-bm", dict(text="ada stok SRTWC286 tak?")),
    ("plain-zh", dict(text="SRTWC286有货吗")),
    ("quoted-reply", dict(text="how about this one", quoted="SRTWC286-SH 10 pcs\nin stock")),
    ("quoted-reply-bm", dict(text="yang ni?", quoted="Sorento WC")),
    ("media-caption", dict(text=None, attachment={"description": "photo of a basin"})),
    ("blank-own-line-quoted-only", dict(text="", quoted="SRTWC286-SH 10 pcs")),
    ("multi-line-en", dict(text="stock please\nSRTWC286\nand SRTWB1086")),
    ("multi-line-zh", dict(text="有货吗\n马桶\n洗手盆")),
]


@pytest.mark.parametrize("kw", [m[1] for m in MESSAGES], ids=[m[0] for m in MESSAGES])
def test_r6_s6_the_user_turn_equals_what_the_first_line_reads_produced(kw):
    env = _env(**kw)
    latest = _old_latest(env)
    assert latest.strip(), ("the fixture built an empty message text: the identity check would be vacuous", env.message)
    old_own = latest.split("\n", 1)[0]
    old_rest = latest.split("\n", 1)[1] if "\n" in latest else ""
    turn = _mod().from_envelope(env)
    assert turn.own_text == old_own, (turn, latest)
    assert turn.quoted_text == old_rest, (turn, latest)
    assert isinstance(turn.media, tuple)


def test_r6_s6_a_media_message_carries_its_read_in_media():
    env = _env(text=None, attachment={"description": "photo of a basin"})
    assert "photo of a basin" in _old_latest(env), "the fixture did not nest the attachment where the engine reads it"
    turn = _mod().from_envelope(env)
    assert any("photo of a basin" in str(m) for m in turn.media), turn


def test_r6_s6_direct_ingress_and_the_webhook_envelope_give_equal_user_turns():
    from app.services.chatbot import direct_ingress

    env = _env(text="how about this one", quoted="SRTWC286-SH")
    contact = {"id": "900000008", "firstName": "ZZT"}
    assert "SRTWC286-SH" in _old_latest(env), "the fixture built no quoted text"
    direct = direct_ingress.envelope_for(env.message, contact)
    assert _mod().from_envelope(direct) == _mod().from_envelope(env)


# ----------------------------------------------------------------------- static: no first-line re-split remains
def test_r6_s6_the_engine_no_longer_re_splits_the_user_message():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "app/services/chatbot/engine.py").read_text()
    for needle in ('latest_user_message.split("\\n", 1)[0]', '_ctx_message_text(ctx).split("\\n")[0]',
                   '(latest_user_message or "").split("\\n")[0]'):
        assert needle not in src, f"engine.py still re-splits the user message: {needle}"


@pytest.mark.parametrize("name", ["with_set_count_from_text", "with_clarify_answer", "set_continue_count", "with_brand_from_offer"])
def test_r6_s6_the_turn_runtime_readers_take_the_user_turn_not_a_line_split(name):
    from app.services.chatbot import turn_runtime

    src = inspect.getsource(getattr(turn_runtime, name))
    assert "lines[0]" not in src and "splitlines()" not in src, f"{name} still splits the message into lines"


# ----------------------------------------------------------------------- AC-S6-3: grounding reads UserTurn.own_text
def test_r6_s6_grounding_receives_the_user_turns_own_text():
    from app.services.chatbot import engine as engine_mod

    src = inspect.getsource(engine_mod)
    assert 'message=latest_user_message.split("\\n", 1)[0]' not in src and "user_turn.own_text" in src, (
        "grounding is not fed UserTurn.own_text")
