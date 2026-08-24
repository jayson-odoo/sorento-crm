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
