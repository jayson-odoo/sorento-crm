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


# --- DOCS-SYNC-AUTO (PLAN-docs-sync-auto-31oct): validation + resilient push ---


def _fake_guides(mod, monkeypatch, tmp_path, pages):
    """Point the module at a temp guides dir holding `pages` {relpath: text}."""
    root = tmp_path / "user-guides"
    root.mkdir()
    (root / "README.md").write_text("# Overview\n\nhi\n")
    for rel, text in pages.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    monkeypatch.setattr(mod, "GUIDES_DIR", root)
    monkeypatch.setattr(mod, "STATE_FILE", root / ".outline-sync.json")
    return root


def test_repo_guides_validate_clean():
    mod = _load_module()
    assert mod.validate_guides() == []


def test_every_published_title_fits_outline_limit():
    mod = _load_module()
    for md in mod.discover_files():
        rel = mod.relpath(md)
        if rel.split("/")[0] in mod.HELD_FOLDERS:
            continue
        title = mod.first_h1_or_filename(md)
        assert len(title) <= mod.MAX_TITLE_LEN, (rel, len(title))


def test_check_fails_on_long_title(monkeypatch, tmp_path):
    mod = _load_module()
    _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/x.md": "# " + "a" * 101 + "\n"})
    problems = mod.validate_guides()
    assert any("warehouse/x.md" in p and "101 characters" in p for p in problems)
    with pytest.raises(SystemExit):
        mod.check(None)


def test_check_fails_on_unmapped_folder_and_bad_layout(monkeypatch, tmp_path):
    mod = _load_module()
    _fake_guides(
        mod,
        monkeypatch,
        tmp_path,
        {"brand-new/x.md": "# X\n", "warehouse/deep/y.md": "# Y\n"},
    )
    problems = "\n".join(mod.validate_guides())
    assert "brand-new/: guide folder is not mapped" in problems
    assert "warehouse/deep/y.md: unexpected layout" in problems


def test_check_ignores_held_folder(monkeypatch, tmp_path):
    mod = _load_module()
    _fake_guides(mod, monkeypatch, tmp_path, {"commercial/x.md": "# " + "a" * 150 + "\n"})
    assert mod.validate_guides() == []


def test_check_runs_without_requests_installed():
    """The PR gate runs `check` on a bare python3: no third-party import at module load."""
    import subprocess

    code = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name.split('.')[0] in ('requests', 'dotenv'):\n"
        "        raise ImportError(name)\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        f"sys.argv = ['x', 'check']\n"
        f"exec(compile(open({str(_SCRIPT)!r}).read(), 'script', 'exec'), {{'__name__': '__main__', '__file__': {str(_SCRIPT)!r}}})\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK:" in proc.stdout


class _FakeOutline:
    def __init__(self, existing=(), fail_titles=()):
        self.docs = [dict(d) for d in existing]
        self.fail_titles = set(fail_titles)
        self.n = 0

    def _maybe_fail(self, title):
        if title in self.fail_titles:
            raise RuntimeError("documents.update -> 400 Document title must be 100 characters or less")

    def list_documents(self, _cid):
        return list(self.docs)

    def create_document(self, title, text, collection_id, parent_id=None, publish=True):
        self._maybe_fail(title)
        self.n += 1
        doc = {"id": f"id-{self.n}", "title": title, "parentDocumentId": parent_id}
        self.docs.append(doc)
        return doc

    def update_document(self, doc_id, title, text):
        self._maybe_fail(title)
        return {"id": doc_id, "title": title}

    def get_document(self, doc_id):
        return next(d for d in self.docs if d["id"] == doc_id)

    def current_user_id(self):
        return "bot"


def test_push_continues_past_a_bad_page_and_fails_at_the_end(monkeypatch, tmp_path, capsys):
    import json

    mod = _load_module()
    root = _fake_guides(
        mod,
        monkeypatch,
        tmp_path,
        {"warehouse/a.md": "# Bad\n", "warehouse/b.md": "# Good\n", "sla/c.md": "# Also good\n"},
    )
    fake = _FakeOutline(fail_titles={"Bad"})
    monkeypatch.setattr(mod, "load_env", lambda: ("http://x", "t", "cid"))
    monkeypatch.setattr(mod, "Outline", lambda **_k: fake)

    with pytest.raises(SystemExit) as exc:
        mod.push(None)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "1 page(s) FAILED" in out and "warehouse/a.md" in out
    state = json.loads((root / ".outline-sync.json").read_text())
    # The pages after the bad one still published and their ids were saved.
    assert "warehouse/b.md" in state and "sla/c.md" in state
    assert "warehouse/a.md" not in state


def test_push_skips_children_of_a_failed_parent(monkeypatch, tmp_path, capsys):
    mod = _load_module()
    _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/a.md": "# A\n", "sla/c.md": "# C\n"})
    fake = _FakeOutline(fail_titles={mod.PARENT_TITLES["warehouse"]})
    monkeypatch.setattr(mod, "load_env", lambda: ("http://x", "t", "cid"))
    monkeypatch.setattr(mod, "Outline", lambda **_k: fake)
    with pytest.raises(SystemExit):
        mod.push(None)
    out = capsys.readouterr().out
    assert "warehouse/__parent__" in out
    assert "warehouse/a.md: not pushed, its parent" in out
    assert any(d["title"] == "C" for d in fake.docs)


def test_pull_learns_ids_by_title_instead_of_duplicating(monkeypatch, tmp_path):
    mod = _load_module()
    _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/a.md": "# Page A\n"})
    parent = mod.PARENT_TITLES["warehouse"]
    docs = [
        {"id": "p1", "title": parent, "parentDocumentId": None},
        {"id": "c1", "title": "Page A", "parentDocumentId": "p1"},
        {"id": "c2", "title": "Only in Outline", "parentDocumentId": "p1"},
    ]
    state = {}
    learnt = mod.learn_state_by_title(state, docs)
    assert state == {"warehouse/__parent__": "p1", "warehouse/a.md": "c1"}
    assert sorted(learnt) == ["warehouse/__parent__", "warehouse/a.md"]
    # A saved id is never overridden.
    state2 = {"warehouse/a.md": "other"}
    mod.learn_state_by_title(state2, docs)
    assert state2["warehouse/a.md"] == "other"


def test_push_keeps_an_outline_edit_not_yet_pulled(monkeypatch, tmp_path, capsys):
    from datetime import datetime, timezone

    mod = _load_module()
    _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/a.md": "# A\n\nrepo text\n", "warehouse/b.md": "# B\n\nnew\n"})
    committed = datetime(2026, 10, 31, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: committed)
    parent = mod.PARENT_TITLES["warehouse"]
    later = "2026-10-31T06:00:00.000Z"
    fake = _FakeOutline(
        existing=[
            {"id": "p1", "title": parent, "parentDocumentId": None, "text": "Department guides for **%s**.\n" % parent},
            # A person edited A in Outline after the repo commit: keep it.
            {"id": "a1", "title": "A", "parentDocumentId": "p1", "text": "outline edit", "updatedAt": later, "updatedBy": {"id": "human"}},
            # B was last written by the sync itself: push the repo copy.
            {"id": "b1", "title": "B", "parentDocumentId": "p1", "text": "old", "updatedAt": later, "updatedBy": {"id": "bot"}},
        ]
    )
    fake.updated = []
    real_update = fake.update_document

    def spy(doc_id, title, text):
        fake.updated.append(doc_id)
        return real_update(doc_id, title, text)

    fake.update_document = spy
    fake.current_user_id = lambda: "bot"
    monkeypatch.setattr(mod, "load_env", lambda: ("http://x", "t", "cid"))
    monkeypatch.setattr(mod, "Outline", lambda **_k: fake)
    monkeypatch.delenv("OUTLINE_SYNC_FORCE", raising=False)
    mod.push(None)
    out = capsys.readouterr().out
    assert "[keep] warehouse/a.md" in out
    assert "[same] warehouse/__parent__" in out
    assert fake.updated == ["b1"]

    monkeypatch.setenv("OUTLINE_SYNC_FORCE", "1")
    fake.updated.clear()
    mod.push(None)
    assert "a1" in fake.updated
