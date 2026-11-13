"""One keep-alive `httpx.Client` per process and purpose (CHATBOT-SPEED).

A client built per call pays a fresh DNS + TCP + TLS handshake every time; on the chatbot's turn path that is each
lookup embedding round trip and the respond.io takeover check. `shared_client(name, **kwargs)` builds the client once
and hands the same one back. It is built again:
- after a fork (gunicorn workers, RQ work-horses): a child never uses its parent's sockets;
- when `httpx.Client` itself is no longer the class it was built with (a test that patches the constructor gets its
  own fake, never a real client cached by an earlier caller).
An idle connection is kept `KEEPALIVE_EXPIRY_SECONDS` (httpx's default of 5 s is shorter than the gap between two
turns on a quiet worker); one the server closed while idle is discarded before reuse. Callers never close it.
It keeps no cookies, as the per-call clients kept none past their one call.
"""
from __future__ import annotations

import os
import threading
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

KEEPALIVE_EXPIRY_SECONDS = 30.0
#: The real class and entry points, read once: a patched `httpx.Client` / `httpx.request` / `httpx.post` is a test's
#: stand-in, never a shared client.
_REAL_CLIENT = httpx.Client
_REAL_REQUEST = httpx.request
_REAL_POST = httpx.post

#: name -> (pid, the `httpx.Client` constructor it was built with, the client)
_clients: dict[str, tuple[int, Any, Any]] = {}
_lock = threading.Lock()


def _reset_after_fork() -> None:
    # A fork while another thread held the lock would leave the child's copy locked forever.
    global _lock
    _lock = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)


def shared_client(name: str, **kwargs: Any) -> httpx.Client:
    """The process's client for `name`, built with `kwargs` (plus the keep-alive limits) on first use."""
    pid = os.getpid()
    ctor = httpx.Client
    with _lock:
        held = _clients.get(name)
        if held is not None and held[0] == pid and held[1] is ctor:
            return held[2]
        kwargs.setdefault("limits", httpx.Limits(keepalive_expiry=KEEPALIVE_EXPIRY_SECONDS))
        # A per-call client threw its cookies away; a shared one keeps none, so a Set-Cookie on one call (another
        # workspace's, a WAF's) never rides along on the next.
        kwargs.setdefault("cookies", CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])))
        client = ctor(**kwargs)
        _clients[name] = (pid, ctor, client)
        return client


def request(name: str, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """`httpx.request(method, url, **kwargs)` over the process's shared client for `name`. When `httpx.request` itself
    was replaced (a test's seam), the replacement answers, exactly as the per-call code it replaces would have."""
    if httpx.request is not _REAL_REQUEST:
        return httpx.request(method, url, **kwargs)
    return shared_client(name).request(method, url, **kwargs)


def post(name: str, url: str, **kwargs: Any) -> httpx.Response:
    """`httpx.post(url, **kwargs)` over the process's shared client for `name`; a replaced `httpx.post` answers."""
    if httpx.post is not _REAL_POST:
        return httpx.post(url, **kwargs)
    return shared_client(name).post(url, **kwargs)


def reset() -> None:
    """Forget every client (tests)."""
    with _lock:
        _clients.clear()


class Borrowed:
    """`with Borrowed(client) as c:` lends a shared client without closing it at the end of the block, so a call site
    written for a per-call client (`with httpx.Client(...) as c:`) keeps its shape. Anything that is not a real
    `httpx.Client` (a test's stand-in from a patched constructor) is used as its own context manager, exactly as the
    per-call client was."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._shared = isinstance(client, _REAL_CLIENT)

    def __enter__(self) -> Any:
        return self._client if self._shared else self._client.__enter__()

    def __exit__(self, *exc: Any) -> Any:
        return None if self._shared else self._client.__exit__(*exc)
