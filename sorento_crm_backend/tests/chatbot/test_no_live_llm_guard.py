"""The suite-wide live-call guard (NO-LIVE-LLM-TESTS, UAC `no-live-llm-tests-03oct`).

`tests/conftest.py` blocks every HTTP request to an LLM or messaging provider in every test,
with no per-module opt-in, and blanks the provider keys the developer's `.env` carries. These
tests prove it from a chatbot test's point of view: an unstubbed parser call fails fast on the
guard instead of reaching the provider.

Every test that could reach a provider if the guard were missing carries its own TRIPWIRE
first: proxies are dropped from the environment and DNS for the provider host raises. So with
the guard gone the test fails red on the tripwire, never on a real request, and with the guard
in place the tripwire is never reached because the guard fires before any connection opens.
Placeholder keys only.
"""
from __future__ import annotations

import os
import socket
import urllib.request

import httpx
import pytest

PLACEHOLDER_KEY = "sk-placeholder-not-a-real-key"

_PROVIDER_HOSTS = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.respond.io",
    "app.respond.io",
    "graph.facebook.com",
)

_PROXY_VARS = (
    "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy",
)


class TripwireReached(AssertionError):
    pass


@pytest.fixture()
def tripwire(monkeypatch):
    """No proxy, and DNS for any provider host raises: the guard must fire before this."""
    for name in _PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    real_getaddrinfo = socket.getaddrinfo

    def _getaddrinfo(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name in _PROVIDER_HOSTS or name.endswith(".respond.io"):
            raise TripwireReached(f"TRIPWIRE: a test reached DNS for {name}; the guard is off")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)


def _chain(exc: BaseException | None) -> list[BaseException]:
    seen: list[BaseException] = []
    while exc is not None and exc not in seen:
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def _assert_guard_fired(exc: BaseException, host: str) -> None:
    chain = _chain(exc)
    assert not any(isinstance(e, TripwireReached) for e in chain), (
        f"the request reached DNS for {host}: {chain!r}"
    )
    assert any(
        type(e).__name__ == "LiveExternalCallBlocked" and host in str(e) for e in chain
    ), f"expected LiveExternalCallBlocked naming {host}, got {chain!r}"


def _forget_blocked_calls() -> None:
    """These tests trip the guard on purpose; clear the record so teardown does not fail."""
    from tests import _live_call_guard

    _live_call_guard.BLOCKED_CALLS.clear()


def test_unstubbed_parser_call_fails_fast_on_the_guard(tripwire):
    from app.services.chatbot.head import parser

    config = parser.ParserConfig(
        system_prompt="placeholder prompt",
        prompt_version=1,
        provider="openai",
        model="gpt-placeholder",
        api_key=PLACEHOLDER_KEY,
    )
    with pytest.raises(parser.ParserError) as info:
        parser.parse(config, "placeholder user block")
    _assert_guard_fired(info.value, "api.openai.com")
    _forget_blocked_calls()


@pytest.mark.parametrize("host", _PROVIDER_HOSTS)
def test_sync_httpx_request_to_a_provider_is_blocked(tripwire, host):
    with httpx.Client() as client, pytest.raises(Exception) as info:
        client.get(f"https://{host}/v1/placeholder")
    _assert_guard_fired(info.value, host)
    _forget_blocked_calls()


async def _async_get(url: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.get(url)


def test_async_httpx_request_to_a_provider_is_blocked(tripwire):
    import asyncio

    with pytest.raises(Exception) as info:
        asyncio.run(_async_get("https://api.anthropic.com/v1/messages"))
    _assert_guard_fired(info.value, "api.anthropic.com")
    _forget_blocked_calls()


def test_urllib_request_to_a_provider_is_blocked(tripwire):
    with pytest.raises(Exception) as info:
        urllib.request.urlopen("https://graph.facebook.com/v19.0/placeholder", timeout=5)
    _assert_guard_fired(info.value, "graph.facebook.com")
    _forget_blocked_calls()


def test_direct_dns_for_a_provider_is_blocked_as_a_backstop():
    """A client none of the transport wrappers know still cannot resolve a provider host."""
    with pytest.raises(Exception) as info:
        socket.getaddrinfo("api.respond.io", 443)
    _assert_guard_fired(info.value, "api.respond.io")
    _forget_blocked_calls()


def test_a_swallowed_blocked_call_is_still_recorded_for_teardown(tripwire):
    """App code that catches the exception must not let the test pass silently."""
    from tests import _live_call_guard

    try:
        httpx.get("https://api.openai.com/v1/models")
    except Exception:  # noqa: BLE001 - the swallow is the point
        pass
    assert any("api.openai.com" in call for call in _live_call_guard.BLOCKED_CALLS)
    _forget_blocked_calls()


def test_provider_keys_from_dotenv_are_blank_during_tests():
    from app.config import settings

    for name in ("openai_api_key", "anthropic_api_key", "gemini_api_key", "respond_api_key"):
        assert not getattr(settings, name), f"settings.{name} is set during a test run"
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "RESPOND_API_KEY"):
        assert not os.environ.get(name), f"os.environ[{name!r}] is set during a test run"


def test_mock_transports_to_a_provider_host_are_untouched():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    with httpx.Client(transport=transport) as client:
        assert client.get("https://api.openai.com/v1/models").json() == {"ok": True}


def test_other_hosts_pass_through_the_guard():
    """A non-provider host reaches the real transport (a refused local port, not the guard)."""
    with httpx.Client(trust_env=False) as client, pytest.raises(httpx.ConnectError):
        client.get("http://127.0.0.1:9/placeholder")


@pytest.mark.live_external
def test_a_live_external_test_only_runs_when_opted_in():
    assert os.environ.get("CHATBOT_LIVE_LLM") == "1", (
        "a @pytest.mark.live_external test ran without CHATBOT_LIVE_LLM=1"
    )
