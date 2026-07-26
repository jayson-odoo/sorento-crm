"""One-shot lazy core registration.

Several code-side registries (rule facts, status entities, rule sites) each want
a "register the core entries exactly once, on first read" guard. Without a shared
helper each one hand-rolls a ``_core_registered`` module global plus an
``_ensure_core()`` wrapper, and they drift.

    ensure_core = lazy_once(_register_core)   # module level
    ...
    def get_thing(key):
        ensure_core()
        return _REGISTRY.get(key)

``done`` is set BEFORE calling ``register`` on purpose: registration builds
in-memory dataclasses and never transiently fails, so a raising registrar is a
programming error. Flipping the flag first turns that into one loud failure
instead of re-running a half-finished registration on every subsequent read.
"""
from typing import Callable


def lazy_once(register: Callable[[], None]) -> Callable[[], None]:
    done = False

    def ensure() -> None:
        nonlocal done
        if done:
            return
        done = True
        register()

    return ensure
