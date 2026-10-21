"""CHAT-COMPOSER: one reply composer per answer type, behind `enabled()` (the stored
switch on Settings > Chatbot, or `CHAT_COMPOSER_ENABLED` when set).

Imports only `jsc`, `app.config`, `app.database` and `app.models.user` (lazily) and its own
modules: never engine, head, tail, dialogue, `turn.compose` or lanes, so `turn/` can import it without a cycle
(`tests/chatbot/test_composers_s0.py`).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.chatbot.turn.pending import Pending

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reply:
    """A composed sentence plus the question or offer it carries, as data."""

    text: str
    question: "Pending | None" = None
    offer: Any = None


# CHAT-RELEASE-1021: the stored switch is read at most once per window per process, so a
# turn that asks the gate dozens of times costs one query; a save clears it in its process.
_CACHE_SECONDS = 5.0
_cache: dict[str, tuple[float, bool]] = {}


def enabled(db: "Session | None" = None) -> bool:
    """The lane's one gate, read at call time so a monkeypatch takes effect. Off = main's text.

    `CHAT_COMPOSER_ENABLED`, when set, wins; unset, the stored switch
    `system_settings.chatbot_composer_enabled` decides. Given a session it is read through it,
    uncached; without one, through the process cache.
    """
    from app.config import settings

    override = getattr(settings, "chat_composer_enabled", None)
    if override is not None:
        return bool(override)
    if db is not None:
        return _read_stored(db)
    now = time.monotonic()
    hit = _cache.get("stored")
    if hit is not None and now - hit[0] < _CACHE_SECONDS:
        return hit[1]
    value = _read_stored()
    _cache["stored"] = (now, value)
    return value


def clear_cache() -> None:
    """Drop this process's cached switch (a settings save calls it)."""
    _cache.clear()


def _read_stored(db: "Session | None" = None) -> bool:
    """The stored switch; no row, or a failed read, is off."""
    from app.models.user import SystemSetting

    try:
        if db is not None:
            row = db.query(SystemSetting.chatbot_composer_enabled).first()
        else:
            from app.database import SessionLocal

            with SessionLocal() as own:
                row = own.query(SystemSetting.chatbot_composer_enabled).first()
    except Exception:
        _log.warning("chat composer switch read failed; reading it as off", exc_info=True)
        return False
    return bool(row[0]) if row is not None else False
