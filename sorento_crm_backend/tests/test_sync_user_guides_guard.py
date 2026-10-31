"""Item 4c (PLAN-post-security-batch) - Outline publish safeguard.

`commercial` (and any HELD folder) MUST NEVER be published. The sync script
enforces this with a HARD assertion that RAISES if a held folder ever leaks
into the publish allowlist (`PARENT_TITLES`) - discipline / a passive skip is
not enough (UAC4.5).

The script lives at repo-root `scripts/sync_user_guides_outline.py`; it is
loaded here by path so these tests run from the backend test suite.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "sync_user_guides_outline.py"
_MOD_NAME = "sync_user_guides_outline_test"


def _load_module():
    spec = importlib.util.spec_from_file_location(_MOD_NAME, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so module-level @dataclass can resolve __module__.
    sys.modules[_MOD_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_commercial_absent_ready_folders_present():
    mod = _load_module()
    assert "commercial" not in mod.PARENT_TITLES
    assert "commercial" in mod.HELD_FOLDERS
    for ready in ("inventory", "delivery-orders", "product", "sla"):
        assert ready in mod.PARENT_TITLES, ready
    # The new getting-started guide lives under `_shared`, which is published.
    assert "_shared" in mod.PARENT_TITLES


def test_guard_passes_with_current_allowlist():
    mod = _load_module()
    # Must not raise as shipped.
    mod._assert_no_held_folders()


def test_guard_raises_when_commercial_added():
    mod = _load_module()
    mod.PARENT_TITLES["commercial"] = "X-Commercial"
    try:
        with pytest.raises(RuntimeError) as exc:
            mod._assert_no_held_folders()
        assert "commercial" in str(exc.value)
    finally:
        mod.PARENT_TITLES.pop("commercial", None)


def test_dry_run_plan_excludes_commercial_includes_getting_started():
    mod = _load_module()
    plan, skipped = mod.plan_push()
    plan_blob = "\n".join(plan)
    # Held folder docs are skipped, never planned for publish.
    assert all("commercial/" not in line for line in plan)
    assert any(s.startswith("commercial/") for s in skipped)
    # Ready guides + the new getting-started ARE in the publish plan.
    assert "_shared/getting-started-for-new-users.md" in plan_blob
    assert "inventory/data-analysis.md" in plan_blob
    assert "sla/data-analysis.md" in plan_blob


def test_plan_push_raises_when_commercial_added():
    mod = _load_module()
    mod.PARENT_TITLES["commercial"] = "X-Commercial"
    try:
        with pytest.raises(RuntimeError):
            mod.plan_push()
    finally:
        mod.PARENT_TITLES.pop("commercial", None)


def test_guides_dir_is_the_real_guides_folder():
    mod = _load_module()
    assert mod.GUIDES_DIR == _REPO_ROOT / "documentation" / "user-guides"
    assert (mod.GUIDES_DIR / "README.md").exists()


def test_every_guide_folder_is_published_or_held():
    mod = _load_module()
    folders = {p.name for p in mod.GUIDES_DIR.iterdir() if p.is_dir()}
    unlisted = folders - set(mod.PARENT_TITLES) - set(mod.HELD_FOLDERS)
    assert not unlisted, f"guide folders that would never reach Outline: {sorted(unlisted)}"
    _, skipped = mod.plan_push()
    assert all(s.split("/")[0] in mod.HELD_FOLDERS for s in skipped), skipped


def test_pull_keeps_a_repo_page_newer_than_its_outline_copy(monkeypatch):
    from datetime import datetime, timezone

    mod = _load_module()
    page = mod.GUIDES_DIR / "README.md"
    committed = datetime(2026, 10, 31, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: committed)

    older = {"updatedAt": "2026-10-31T03:39:29.000Z"}
    newer = {"updatedAt": "2026-10-31T06:00:00.000Z"}
    assert mod.repo_is_newer(page, older) is True
    assert mod.repo_is_newer(page, newer) is False
    # A page that is not in the repo yet is always pulled.
    assert mod.repo_is_newer(mod.GUIDES_DIR / "no-such-page.md", older) is False
    # No Outline timestamp or no git history: fall back to pulling.
    assert mod.repo_is_newer(page, {}) is False
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: None)
    assert mod.repo_is_newer(page, older) is False


def test_repo_committed_at_reads_git_history():
    mod = _load_module()
    when = mod._repo_committed_at(mod.GUIDES_DIR / "README.md")
    # Shallow CI checkouts still have the HEAD commit, so this is never None in a clone.
    assert when is not None and when.tzinfo is not None
