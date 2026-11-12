"""One keep-alive `httpx.Client` per process and purpose (CHATBOT-SPEED).

A client built per call pays a fresh DNS + TCP + TLS handshake every time; on the chatbot's turn path that is each
lookup embedding round trip and the respond.io takeover check. `shared_client(name, **kwargs)` builds the client once
and hands the same one back. It is built again:
- after a fork (gunicorn workers, RQ work-horses): a child never uses its parent's sockets;
- when `httpx.Client` itself is no longer the class it was built with (a test that patches the constructor gets its
  own fake, never a real client cached by an earlier caller).
An idle connection is kept `KEEPALIVE_EXPIRY_SECONDS` (httpx's default of 5 s is shorter than the gap between two
turns on a quiet worker); one the server closed while idle is discarded before reuse. Callers never close it.
"""
from __future__ import annotations

import os
import threading
from typing import Any

import httpx

KEEPALIVE_EXPIRY_SECONDS = 30.0

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
        client = ctor(**kwargs)
        _clients[name] = (pid, ctor, client)
        return client


def reset() -> None:
    """Forget every client (tests)."""
    with _lock:
        _clients.clear()


class Borrowed:
    """`with Borrowed(client) as c:` hands out a shared client without closing it at the end of the block, so a call
    site written for a per-call client (`with httpx.Client(...) as c:`) keeps its shape."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def __enter__(self) -> Any:
        return self._client

    def __exit__(self, *exc: Any) -> None:
        return None
