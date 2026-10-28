"""API-NONBLOCKING guard: no mounted route is `async def` without an await (AN-4).

FastAPI runs an `async def` handler ON the worker's event loop and a plain `def` handler in the
threadpool. An `async def` handler with no `await` / `async for` / `async with` in its own body
does all its work (queries, file builds, HTTP calls) on the loop, so every other request on
that worker waits behind it (`documentation/plans/ops/PLAN-api-nonblocking-28oct.md`). On
main on 28 Oct 2026 there were 943 of them; this test keeps the count at zero.

Fix a failure by declaring the handler plain `def`. If the handler genuinely belongs on the
loop (it only builds an async stream), add it to ALLOWED with the reason.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

# "<module>.<function>": why it stays on the event loop.
ALLOWED = {
    "app.api.v1.sla.conversation_events.stream_conversation_events": (
        "builds and returns an async SSE stream; the handler itself does no blocking work"
    ),
}


def _awaits(fn: ast.AsyncFunctionDef) -> bool:
    """An await / async for / async with in the function's OWN body (nested defs excluded:
    an inner async generator does not put the handler on the loop for good reason)."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return False


def _blocking_async_endpoints() -> dict[str, str]:
    found: dict[str, str] = {}
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or not inspect.iscoroutinefunction(endpoint):
            continue
        if not endpoint.__module__.startswith("app."):
            continue  # FastAPI's own /docs, /redoc, /openapi.json: not ours to change
        tree = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))
        fn = tree.body[0]
        assert isinstance(fn, ast.AsyncFunctionDef), endpoint
        if not _awaits(fn):
            key = f"{endpoint.__module__}.{endpoint.__qualname__}"
            found[key] = f"{inspect.getsourcefile(endpoint)}:{fn.lineno + endpoint.__code__.co_firstlineno - 1}"
    return found


def test_no_route_is_async_def_without_an_await():
    offenders = {k: v for k, v in _blocking_async_endpoints().items() if k not in ALLOWED}
    assert not offenders, (
        "async def route handlers that never await hold the worker's event loop for their whole "
        "run; declare them plain `def` (FastAPI then runs them in the threadpool):\n"
        + "\n".join(f"  {where}  {name}" for name, where in sorted(offenders.items()))
    )


def test_the_allow_list_has_no_stale_entries():
    """An allow-listed handler that was converted, renamed or removed comes off the list, so
    the list never silently covers a different function."""
    stale = set(ALLOWED) - set(_blocking_async_endpoints())
    assert not stale, f"no longer an async def route without an await: {sorted(stale)}"


def test_the_guard_sees_a_blocking_handler():
    """The detector itself: a no-await coroutine is flagged, an awaiting one and one whose
    only async code is a nested generator are told apart."""

    def parse(src: str) -> ast.AsyncFunctionDef:
        return ast.parse(textwrap.dedent(src)).body[0]

    assert not _awaits(parse("async def h(db):\n    return db.query(1).all()\n"))
    assert _awaits(parse("async def h(f):\n    return await f.read()\n"))
    assert _awaits(parse("async def h(r):\n    async with r as x:\n        return x\n"))
    assert not _awaits(
        parse("async def h():\n    async def gen():\n        await x()\n    return gen()\n")
    )
