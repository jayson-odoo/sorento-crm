"""EVAL-BENCH round 48: a provider that refuses the key (out of credits, 401 / 403) stops the live run.

The stand-ins are the REAL openai SDK exception types (openai 2.32, `.status_code` and `.code` from the body) and
`httpx.HTTPStatusError` for the embeddings endpoint. No network, no model.
"""
from __future__ import annotations

import json

import httpx
import openai
import pytest

from app.services import embedding_worker, llm_provider
from scripts.chatbot_eval import replay as replay_mod
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot_eval.test_replay import ChatbotTurn, recorded, _record, _turn_count  # noqa: F401
from tests.chatbot_eval.test_replay_live import KEY, LAST4, _Keyed, items_for, live_env  # noqa: F401
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401


def _response(status: int, code: str | None):
    body = {"error": {"code": code, "type": code}} if code else {"error": {}}
    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/x"), json=body)


def quota_error():
    return openai.RateLimitError("You have no credits remaining", response=_response(429, "insufficient_quota"),
                                 body={"code": "insufficient_quota", "type": "insufficient_quota"})


def transient_429():
    return openai.RateLimitError("slow down", response=_response(429, "rate_limit_exceeded"),
                                 body={"code": "rate_limit_exceeded", "type": "requests"})


def auth_error(status=401):
    cls = openai.AuthenticationError if status == 401 else openai.PermissionDeniedError
    return cls("bad key", response=_response(status, "invalid_api_key"), body={"code": "invalid_api_key"})


def _total():
    total = replay_mod._new_usage()
    total.update(max_calls=50, max_usd=10.0, stop=None, require_key_last4=LAST4)
    return total


def _raising_chat(exc):
    def chat(self, messages, **kw):
        raise exc
    return chat


def _call_chat(exc, monkeypatch):
    monkeypatch.setattr(llm_provider.OpenAIProvider, "chat", _raising_chat(exc))
    total = _total()
    with replay_mod._metered(replay_mod._new_usage(), total):
        with pytest.raises(type(exc)):
            llm_provider.OpenAIProvider.chat(_Keyed(), [{"role": "user", "content": "x"}], model="gpt-5.4-mini")
    return total


def test_a_quota_refusal_sets_the_stop_and_reraises(monkeypatch):
    total = _call_chat(quota_error(), monkeypatch)
    assert total["stop"] == "provider_refused"
    assert total["stop_kind"] == "insufficient_quota"


@pytest.mark.parametrize("status", [401, 403])
def test_an_auth_refusal_sets_the_stop_and_reraises(monkeypatch, status):
    total = _call_chat(auth_error(status), monkeypatch)
    assert total["stop"] == "provider_refused"
    assert total["stop_kind"] == "auth"


def test_a_transient_429_is_not_a_refusal(monkeypatch):
    total = _call_chat(transient_429(), monkeypatch)
    assert total["stop"] is None


def _embed_refusal(status, code, monkeypatch):
    exc = httpx.HTTPStatusError("refused", request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
                                response=_response(status, code))

    def boom(chunks):
        raise exc

    monkeypatch.setattr(embedding_worker, "_embed_text_chunks", boom)
    monkeypatch.setattr("app.config.settings.openai_api_key", "")
    total = _total()
    with replay_mod._metered(replay_mod._new_usage(), total):
        with pytest.raises(httpx.HTTPStatusError):
            embedding_worker._embed_text_chunks(["x"])
    return total


def test_the_embed_wrapper_stops_on_a_quota_refusal(monkeypatch):
    assert _embed_refusal(429, "insufficient_quota", monkeypatch)["stop"] == "provider_refused"


def test_the_embed_wrapper_stops_on_a_401(monkeypatch):
    assert _embed_refusal(401, "invalid_api_key", monkeypatch)["stop"] == "provider_refused"


def test_the_embed_wrapper_ignores_a_transient_429(monkeypatch):
    assert _embed_refusal(429, "rate_limit_exceeded", monkeypatch)["stop"] is None


def _refuse(live_env, monkeypatch, exc):
    monkeypatch.setattr(llm_provider.OpenAIProvider, "chat", _raising_chat(exc))


def _run(session_factory, recorded, n=3):
    return replay_mod.live_rows(items_for(recorded, n), [recorded], session_factory=session_factory,
                                max_calls=50, max_usd=10.0, require_key_last4=LAST4)


@pytest.mark.parametrize("exc_factory", [quota_error, auth_error])
def test_the_current_and_every_later_item_are_stopped_and_no_later_call_goes_out(
        session_factory, recorded, live_env, monkeypatch, exc_factory):
    _refuse(live_env, monkeypatch, exc_factory())
    out = _run(session_factory, recorded)
    assert [r.get("stopped") for r in out] == ["provider_refused"] * 3, out
    assert all("turn" not in r for r in out)
    assert len(live_env["parse_calls"]) == 1, "a later item reached the provider after the refusal"


def test_a_transient_429_leaves_the_run_going(session_factory, recorded, live_env, monkeypatch):
    _refuse(live_env, monkeypatch, transient_429())
    out = _run(session_factory, recorded, n=2)
    assert not any(r.get("stopped") == "provider_refused" for r in out)
    assert len(live_env["parse_calls"]) == 2


def test_cli_exits_non_zero_on_a_provider_refusal(tmp_path, session_factory, recorded, live_env, monkeypatch, capsys):
    import app.database

    _refuse(live_env, monkeypatch, quota_error())
    monkeypatch.setattr(app.database, "SessionLocal", session_factory)
    items = tmp_path / "items.jsonl"
    items.write_text("".join(json.dumps(i) + "\n" for i in items_for(recorded, n=2)))
    rec = tmp_path / "recorded.jsonl"
    rec.write_text(json.dumps(recorded) + "\n")
    out = tmp_path / "out.jsonl"
    rc = replay_mod.main(["live", "--items", str(items), "--recorded", str(rec), "--out", str(out),
                          "--max-calls", "10", "--max-usd", "5", "--require-key-last4", LAST4])
    cap = capsys.readouterr()
    assert rc == 4
    assert "provider_refused" in cap.out
    assert "no credits" not in (cap.out + cap.err)


def test_every_stopped_row_names_the_refusal_kind(session_factory, recorded, live_env, monkeypatch):
    _refuse(live_env, monkeypatch, quota_error())
    out = _run(session_factory, recorded)
    assert [r.get("kind") for r in out] == ["insufficient_quota"] * 3


def test_a_second_call_in_the_refused_turn_stops_with_the_kind(session_factory, recorded, live_env, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot.test_engine import _parser_output

    def parse_swallowing(config, user_block):
        for _ in range(2):
            try:
                llm_provider.OpenAIProvider.chat(_Keyed(), [{"role": "user", "content": "x"}], model="gpt-5.4-mini")
            except Exception:  # noqa: BLE001 - the engine swallows a provider error the same way
                pass
        return _parser_output()

    monkeypatch.setattr(parser_mod, "parse", parse_swallowing)
    _refuse(live_env, monkeypatch, quota_error())
    out = _run(session_factory, recorded, n=1)
    assert out[0].get("stopped") == "provider_refused" and out[0].get("kind") == "insufficient_quota", out


def test_an_embed_call_after_a_refusal_never_reaches_the_original(monkeypatch):
    reached = []
    monkeypatch.setattr(embedding_worker, "_embed_text_chunks", lambda chunks: reached.append(1) or [[0.0]])
    monkeypatch.setattr("app.config.settings.openai_api_key", "")
    total = _total()
    total.update(stop="provider_refused", stop_kind="auth")
    with replay_mod._metered(replay_mod._new_usage(), total):
        with pytest.raises(BaseException) as info:
            embedding_worker._embed_text_chunks(["x"])
    assert not reached and getattr(info.value, "reason", None) == "provider_refused"
