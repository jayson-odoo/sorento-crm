"""AC-002: nothing outside the module's own doorways imports `app.services.chatbot`.

The package is module-private with ONE public entry point. It may import core services
freely; core must never import it. That asymmetry is the entire "liftable later" story -
the day the named trigger fires, the package moves behind an HTTP boundary and only the
files listed here have to change.

The check is a source scan, not an import graph walk: an importer that is never executed
by the suite is still an importer, and the failure message has to name the file so the
fix is obvious.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# The only files allowed to reach into the package.
ALLOWED = {
    "app/api/v1/external/chat.py",
    "app/tasks/chat_turns.py",
}
ALLOWED_PREFIXES = (
    "app/services/chatbot/",
    "app/modules/chatbot/",
    "tests/chatbot/",
)

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+app\.services\.chatbot\b|import\s+app\.services\.chatbot\b)",
    re.MULTILINE,
)


def _scanned_files() -> list[Path]:
    roots = [BACKEND_ROOT / "app", BACKEND_ROOT / "tests", BACKEND_ROOT / "scripts"]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py") if "venv" not in p.parts)
    return files


def test_no_module_outside_the_boundary_imports_the_chatbot_package() -> None:
    offenders = []
    for path in _scanned_files():
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel in ALLOWED or rel.startswith(ALLOWED_PREFIXES):
            continue
        if _IMPORT_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, (
        "these files import app.services.chatbot from outside the module boundary: "
        + ", ".join(sorted(offenders))
        + " - route through app/api/v1/external/chat.py or app/tasks/chat_turns.py instead"
    )


def test_the_package_exports_only_its_public_entry_points() -> None:
    import app.services.chatbot as pkg

    assert set(pkg.__all__) <= {"run_turn", "complete_turn"}, (
        "app/services/chatbot/__init__.py must export run_turn / complete_turn only; "
        f"found {sorted(pkg.__all__)}"
    )
