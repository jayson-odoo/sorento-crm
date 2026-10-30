"""AGENTIC-P2 slice 1: `app.services.chatbot.jev_client.choose` (plan "Jev wire format").

HTTP is intercepted at `httpx.HTTPTransport.handle_request`, so the test does not care whether the
client uses `httpx.post` or an `httpx.Client`. No database.
"""
from __future__ import annotations

import json

import httpx
import pytest

KEY = "ZZT-jev-secret-key-7788"

GOOD = {
    "model": "jev-latest",
    "answers": {
        "route": {
            "type": "choice", "choice": "agent", "confidence": 0.91,
            "probabilities": {"chat": 0.09, "agent": 0.91},
        }
    },
    "usage": {"input_tokens": 210, "output_tokens": 4},
}
CRITERIA = {"chat": "a lookup", "agent": "several reads combined"}


@pytest.fixture(autouse=True)
def _no_base_env(monkeypatch):
    monkeypatch.delenv("JEV_BASE_URL", raising=False)


@pytest.fixture()
def wire(monkeypatch):
    """Replace the transport. `wire.reply` is a callable(request) -> httpx.Response (or raises)."""
    seen: list[httpx.Request] = []
    box = {"reply": lambda request: httpx.Response(200, json=GOOD)}

    def handle(self, request):
        request.read()
        seen.append(request)
        return box["reply"](request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)

    class Wire:
        requests = seen

        @staticmethod
        def reply(fn):
            box["reply"] = fn

    return Wire


def _choose(**over):
    from app.services.chatbot import jev_client

    kw = dict(state="Message: compare Q3 and Q4", instructions="route it", criteria=CRITERIA)
    kw.update(over)
    return jev_client.choose(KEY, **kw)


def test_the_request_is_exact(wire):
    _choose()
    assert len(wire.requests) == 1
    req = wire.requests[0]
    assert req.method == "POST"
    assert str(req.url) == "https://api.typesafe.ai/v1/systemone"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["content-type"].startswith("application/json")
    assert json.loads(req.content) == {
        "model": "jev-latest",
        "state": "Message: compare Q3 and Q4",
        "questions": {"route": {"type": "choice", "instructions": "route it", "criteria": CRITERIA}},
    }


def test_the_model_can_be_overridden(wire):
    _choose(model="jev-test")
    assert json.loads(wire.requests[0].content)["model"] == "jev-test"


def test_the_default_timeout_is_one_and_a_half_seconds(wire):
    _choose()
    assert wire.requests[0].extensions["timeout"]["read"] == 1.5


def test_a_timeout_argument_is_honoured(wire):
    _choose(timeout=0.4)
    assert wire.requests[0].extensions["timeout"]["read"] == 0.4


def test_the_response_is_parsed(wire):
    assert _choose() == {
        "choice": "agent",
        "confidence": 0.91,
        "probabilities": {"chat": 0.09, "agent": 0.91},
        "input_tokens": 210,
        "output_tokens": 4,
    }


def test_base_url_comes_from_the_env(wire, monkeypatch):
    monkeypatch.setenv("JEV_BASE_URL", "http://jev.test:9000")
    _choose()
    assert str(wire.requests[0].url) == "http://jev.test:9000/v1/systemone"


def test_a_trailing_slash_on_the_base_url_is_tolerated(wire):
    _choose(base_url="http://jev.test/")
    assert str(wire.requests[0].url) == "http://jev.test/v1/systemone"


def test_the_argument_beats_the_env_base_url(wire, monkeypatch):
    monkeypatch.setenv("JEV_BASE_URL", "http://env.test")
    _choose(base_url="http://arg.test")
    assert str(wire.requests[0].url) == "http://arg.test/v1/systemone"


def _raises(wire, reply):
    from app.services.chatbot import jev_client

    wire.reply(reply)
    with pytest.raises(jev_client.JevError) as exc:
        _choose()
    assert KEY not in str(exc.value)
    assert KEY not in repr(exc.value)
    return exc.value


@pytest.mark.parametrize("code", [400, 401, 403, 404, 429, 500, 503])
def test_an_http_error_is_a_jev_error_that_hides_the_key(wire, code):
    _raises(wire, lambda r: httpx.Response(code, text=f"denied for Bearer {KEY}"))


def test_bad_json_is_a_jev_error(wire):
    _raises(wire, lambda r: httpx.Response(200, text="<html>not json</html>"))


@pytest.mark.parametrize(
    "body",
    [
        {"model": "jev-latest", "answers": {}, "usage": {}},
        {"model": "jev-latest", "usage": {}},
        {"answers": {"route": {"type": "choice"}}},
        {"answers": {"route": {"type": "choice", "choice": "agent", "confidence": 0.9}}},
        {"answers": "nope"},
        ["not", "an", "object"],
    ],
)
def test_a_missing_answer_or_wrong_shape_is_a_jev_error(wire, body):
    _raises(wire, lambda r: httpx.Response(200, json=body))


def test_a_timeout_is_a_jev_error(wire):
    def slow(request):
        raise httpx.ReadTimeout("read timed out", request=request)

    _raises(wire, slow)


def test_a_connection_error_that_echoes_the_key_is_a_jev_error_without_it(wire):
    def down(request):
        raise httpx.ConnectError(f"cannot connect with Bearer {KEY}", request=request)

    _raises(wire, down)


def test_the_error_class_exists_and_is_an_exception():
    from app.services.chatbot import jev_client

    assert issubclass(jev_client.JevError, Exception)
