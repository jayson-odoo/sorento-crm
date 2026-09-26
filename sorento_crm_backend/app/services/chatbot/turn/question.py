# Issue #1293: the open question object (red-first scaffold; filled in by the next commit).
from __future__ import annotations

from typing import Any

QUESTION_KINDS: tuple[str, ...] = ()


def open_question(pending: Any, tasks: Any) -> dict[str, Any] | None:
    return None
