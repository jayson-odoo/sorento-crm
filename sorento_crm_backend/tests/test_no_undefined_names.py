"""Source guard: no undefined name anywhere under app/ (COMPLAINT-CREATE-500).

A helper's definition was deleted from complaints.py while two callers stayed; nothing failed
until a staff user pressed Create (500, NameError). pyflakes finds that class of bug
statically, so every module under app/ is checked here. Only "undefined name" is asserted:
unused imports and other style findings are out of scope for this guard.
"""
from __future__ import annotations

from pathlib import Path

from pyflakes import api as pyflakes_api
from pyflakes import messages as pyflakes_messages

APP_DIR = Path(__file__).resolve().parent.parent / "app"


class _Collect:
    def __init__(self) -> None:
        self.hits: list[str] = []

    def flake(self, message) -> None:
        if isinstance(message, pyflakes_messages.UndefinedName):
            self.hits.append(f"{message.filename}:{message.lineno}: {message.message % message.message_args}")

    def unexpectedError(self, filename, msg) -> None:  # noqa: N802 - pyflakes reporter API
        self.hits.append(f"{filename}: {msg}")

    def syntaxError(self, filename, msg, lineno, offset, text) -> None:  # noqa: N802
        self.hits.append(f"{filename}:{lineno}: syntax error: {msg}")


def test_app_has_no_undefined_names():
    collector = _Collect()
    paths = sorted(APP_DIR.rglob("*.py"))
    assert len(paths) > 100, f"guard found only {len(paths)} modules under {APP_DIR}"
    for path in paths:
        pyflakes_api.check(path.read_text(encoding="utf-8"), str(path.relative_to(APP_DIR.parent)), collector)
    assert collector.hits == [], "undefined names:\n" + "\n".join(collector.hits)
