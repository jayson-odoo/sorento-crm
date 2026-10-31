"""Item 4c (PLAN-post-security-batch) - Outline publish safeguard.

`commercial` (and any HELD folder) MUST NEVER be published. The sync script
enforces this with a HARD assertion that RAISES if a held folder ever leaks
into the publish allowlist (`PARENT_TITLES`) - discipline / a passive skip is
not enough (UAC4.5).

The script lives at repo-root `scripts/sync_user_guides_outline.py`; it is
loaded here by path so these tests run from the backend test suite.

These tests never read the real documentation/user-guides tree: a guides-only
change is docs-only in deploy.yml (no test job runs for it). The real tree is
checked on every PR by the PR gate's `sync_user_guides_outline.py check` step
(unmapped folder, bad layout, title too long). DOCS-SYNC-AUTO.
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


def test_dry_run_plan_excludes_commercial(monkeypatch, tmp_path):
    mod = _load_module()
    _fake_guides(
        mod,
        monkeypatch,
        tmp_path,
        {
            "commercial/x.md": "# X\n",
            "_shared/getting-started.md": "# Getting started\n",
            "inventory/data-analysis.md": "# Inventory data\n",
        },
    )
    plan, skipped = mod.plan_push()
    plan_blob = "\n".join(plan)
    # Held folder docs are skipped, never planned for publish.
    assert all("commercial/" not in line for line in plan)
    assert skipped == ["commercial/x.md"]
    assert "_shared/getting-started.md" in plan_blob
    assert "inventory/data-analysis.md" in plan_blob


def test_plan_push_raises_when_commercial_added():
    mod = _load_module()
    mod.PARENT_TITLES["commercial"] = "X-Commercial"
    try:
        with pytest.raises(RuntimeError):
            mod.plan_push()
    finally:
        mod.PARENT_TITLES.pop("commercial", None)


def test_pull_keeps_a_repo_page_newer_than_its_outline_copy(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    mod = _load_module()
    root = _fake_guides(mod, monkeypatch, tmp_path, {})
    page = root / "README.md"
    committed = datetime(2026, 10, 31, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: committed)

    older = {"updatedAt": "2026-10-31T03:39:29.000Z"}
    newer = {"updatedAt": "2026-10-31T06:00:00.000Z"}
    assert mod.repo_is_newer(page, older) is True
    assert mod.repo_is_newer(page, newer) is False
    # A page that is not in the repo yet is always pulled.
    assert mod.repo_is_newer(root / "no-such-page.md", older) is False
    # No Outline timestamp or no git history: fall back to pulling.
    assert mod.repo_is_newer(page, {}) is False
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: None)
    assert mod.repo_is_newer(page, older) is False


def test_repo_committed_at_reads_git_history():
    mod = _load_module()
    when = mod._repo_committed_at(_SCRIPT)
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


def test_check_runs_without_requests_installed(tmp_path):
    """The PR gate runs `check` on a bare python3: no third-party import at module load."""
    import subprocess

    (tmp_path / "README.md").write_text("# Overview\n")
    (tmp_path / "warehouse").mkdir()
    (tmp_path / "warehouse" / "a.md").write_text("# A\n")
    code = (
        "import builtins, importlib.util, pathlib, sys\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name.split('.')[0] in ('requests', 'dotenv'):\n"
        "        raise ImportError(name)\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        f"spec = importlib.util.spec_from_file_location('m', {str(_SCRIPT)!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['m'] = m\n"
        "spec.loader.exec_module(m)\n"
        f"m.GUIDES_DIR = pathlib.Path({str(tmp_path)!r}); m.REPO_ROOT = m.GUIDES_DIR.parent\n"
        "m.check(None)\n"
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

    def current_user(self):
        return {"id": "bot", "name": "Sorento Sync Bot"}


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


def test_pull_learns_ids_and_writes_no_duplicate_page(monkeypatch, tmp_path):
    """pull() itself: a doc the push created (id not in state) maps back to its repo page."""
    import json

    mod = _load_module()
    root = _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/a.md": "# Page A\n\nrepo\n"})
    parent = mod.PARENT_TITLES["warehouse"]
    fake = _FakeOutline(
        existing=[
            {"id": "p1", "title": parent, "parentDocumentId": None, "text": "x"},
            {"id": "c1", "title": "Page A", "parentDocumentId": "p1", "text": "edited on outline",
             "updatedAt": "2026-10-31T06:00:00.000Z", "updatedBy": {"id": "human"}},
        ]
    )
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: None)
    monkeypatch.setattr(mod, "load_env", lambda: ("http://x", "t", "cid"))
    monkeypatch.setattr(mod, "Outline", lambda **_k: fake)
    mod.pull(None)
    assert sorted(p.name for p in (root / "warehouse").iterdir()) == ["a.md"]
    assert (root / "warehouse" / "a.md").read_text() == "# Page A\n\nedited on outline\n"
    state = json.loads((root / ".outline-sync.json").read_text())
    assert state["warehouse/a.md"] == "c1" and state["warehouse/__parent__"] == "p1"


def test_pull_keeps_a_page_last_written_by_the_sync(monkeypatch, tmp_path, capsys):
    mod = _load_module()
    root = _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/a.md": "# Page A\n\nnewer repo\n"})
    parent = mod.PARENT_TITLES["warehouse"]
    fake = _FakeOutline(
        existing=[
            {"id": "p1", "title": parent, "parentDocumentId": None, "text": "x"},
            {"id": "c1", "title": "Page A", "parentDocumentId": "p1", "text": "older push",
             "updatedAt": "2026-10-31T06:00:00.000Z", "updatedBy": {"id": "bot"}},
        ]
    )
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: None)
    monkeypatch.setattr(mod, "load_env", lambda: ("http://x", "t", "cid"))
    monkeypatch.setattr(mod, "Outline", lambda **_k: fake)
    mod.pull(None)
    assert (root / "warehouse" / "a.md").read_text() == "# Page A\n\nnewer repo\n"
    assert "last written by the sync" in capsys.readouterr().out


def test_check_ignores_a_folder_without_markdown(monkeypatch, tmp_path):
    mod = _load_module()
    root = _fake_guides(mod, monkeypatch, tmp_path, {})
    (root / "images").mkdir()
    (root / "images" / "x.png").write_bytes(b"png")
    assert mod.validate_guides() == []


def test_sync_user_exemption_only_for_a_dedicated_account(capsys):
    mod = _load_module()

    class _O:
        def __init__(self, user):
            self.user = user

        def current_user(self):
            return self.user

    assert mod.sync_user_id(_O({"id": "b1", "name": "Sorento Sync Bot"})) == "b1"
    assert mod.sync_user_id(_O({"id": "b2", "name": "docs-sync"})) == "b2"
    # A person's token (crew, 31 Oct: the secret is the owner's own account):
    # no exemption, and a loud workflow warning.
    assert mod.sync_user_id(_O({"id": "p1", "name": "Teh Jayson"})) is None
    assert "::warning title=Outline sync runs as a person's account::" in capsys.readouterr().out
    assert mod.sync_user_id(_O(None)) is None


def test_push_with_a_person_token_keeps_that_persons_outline_edit(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    mod = _load_module()
    _fake_guides(mod, monkeypatch, tmp_path, {"warehouse/a.md": "# A\n\nrepo\n"})
    monkeypatch.setattr(mod, "_repo_committed_at", lambda _p: datetime(2026, 10, 31, 5, 0, tzinfo=timezone.utc))
    parent = mod.PARENT_TITLES["warehouse"]
    fake = _FakeOutline(
        existing=[
            {"id": "p1", "title": parent, "parentDocumentId": None, "text": "Department guides for **%s**.\n" % parent},
            {"id": "a1", "title": "A", "parentDocumentId": "p1", "text": "owner edit",
             "updatedAt": "2026-10-31T06:00:00.000Z", "updatedBy": {"id": "owner"}},
        ]
    )
    fake.current_user = lambda: {"id": "owner", "name": "Teh Jayson"}
    fake.updated = []
    real_update = fake.update_document
    fake.update_document = lambda i, t, x: (fake.updated.append(i), real_update(i, t, x))[1]
    monkeypatch.setattr(mod, "load_env", lambda: ("http://x", "t", "cid"))
    monkeypatch.setattr(mod, "Outline", lambda **_k: fake)
    monkeypatch.delenv("OUTLINE_SYNC_FORCE", raising=False)
    mod.push(None)
    assert fake.updated == []
