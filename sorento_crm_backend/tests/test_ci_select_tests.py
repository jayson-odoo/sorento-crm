"""scripts/ci_select_tests.py: which backend test files a PR's CI runs (CI-SPEED).

Before this, a PR ran only the test files it changed. #1411 changed
app/services/shipping_order_ingest_service.py and rules/shipping_order_rules.py;
tests/test_ingest_parity_security_fixes.py imports the first (line 42) and broke
in the release, its first execution. The script adds every test file that
imports a changed backend module, directly or through one importing module.

Pure filesystem work, no database: the cases build a scratch backend tree, and
one case runs against this checkout with #1411's real file list.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

import ci_select_tests as sel  # noqa: E402

P = "sorento_crm_backend/"


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "sorento_crm_backend"
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


BASE = {
    "app/__init__.py": "",
    "app/services/__init__.py": "",
    "app/services/foo.py": "def f():\n    return 1\n",
    "app/services/bar.py": "from app.services.foo import f\n",
    "app/services/baz.py": "from . import bar\n",
    "app/services/qux.py": "X = 1\n",
    "tests/__init__.py": "",
    "tests/conftest.py": "",
    "tests/test_direct.py": "from app.services.foo import f\n",
    "tests/test_module_import.py": "import app.services.foo as foo\n",
    "tests/test_from_package.py": "from app.services import foo\n",
    "tests/test_patch_string.py": "def test_x(monkeypatch):\n    monkeypatch.setattr('app.services.foo.f', lambda: 2)\n",
    "tests/test_via_bar.py": "from app.services.bar import f\n",
    "tests/test_via_baz.py": "from app.services import baz\n",
    "tests/test_unrelated.py": "from app.services.qux import X\n",
    "tests/test_prefix_lookalike.py": "import app.services.foobar\n",
    "tests/_helpers.py": "from app.services.foo import f\n",
    "tests/test_via_helper.py": "from tests._helpers import f\n",
    "tests/scm/__init__.py": "",
    "tests/scm/test_scm_direct.py": "from app.services.foo import f\n",
}


def test_direct_and_one_level_importers_are_selected(tmp_path):
    root = _tree(tmp_path, BASE)
    result = sel.select([P + "app/services/foo.py"], root, scm_runs=False)
    assert result.full is False
    assert result.tests == sorted(
        P + "tests/" + name
        for name in (
            "scm/test_scm_direct.py",
            "test_direct.py",
            "test_from_package.py",
            "test_module_import.py",
            "test_patch_string.py",
            "test_via_bar.py",
            "test_via_helper.py",
        )
    )


def test_two_levels_away_is_not_selected(tmp_path):
    """baz imports bar imports foo: transitive one level only."""
    root = _tree(tmp_path, BASE)
    result = sel.select([P + "app/services/foo.py"], root, scm_runs=False)
    assert P + "tests/test_via_baz.py" not in result.tests
    assert P + "tests/test_unrelated.py" not in result.tests
    assert P + "tests/test_prefix_lookalike.py" not in result.tests


def test_relative_import_counts_as_an_importer(tmp_path):
    root = _tree(tmp_path, BASE)
    result = sel.select([P + "app/services/bar.py"], root, scm_runs=False)
    assert P + "tests/test_via_baz.py" in result.tests
    assert P + "tests/test_via_bar.py" in result.tests


def test_scm_tests_are_left_to_the_scm_shards_when_they_run(tmp_path):
    root = _tree(tmp_path, BASE)
    result = sel.select([P + "app/services/foo.py"], root, scm_runs=True)
    assert P + "tests/scm/test_scm_direct.py" not in result.tests
    assert P + "tests/test_direct.py" in result.tests


def test_changed_test_files_are_always_selected(tmp_path):
    root = _tree(tmp_path, BASE)
    result = sel.select(
        [P + "tests/test_unrelated.py", P + "tests/scm/test_scm_direct.py", P + "tests/_helpers.py"],
        root,
        scm_runs=True,
    )
    # A changed helper module selects its importers, a changed scm test is the
    # SCM shards' job, and a non-test file is never a pytest argument.
    assert result.tests == [P + "tests/test_unrelated.py", P + "tests/test_via_helper.py"]


def test_non_python_and_non_backend_paths_select_nothing(tmp_path):
    root = _tree(tmp_path, BASE)
    result = sel.select(
        ["sorento_crm_frontend/app/page.tsx", P + "app/templates/x.html", "documentation/x.md"],
        root,
        scm_runs=False,
    )
    assert result.tests == [] and result.full is False


def test_deleted_module_still_selects_what_imports_it(tmp_path):
    files = dict(BASE)
    del files["app/services/foo.py"]
    root = _tree(tmp_path, files)
    result = sel.select([P + "app/services/foo.py"], root, scm_runs=False)
    assert P + "tests/test_direct.py" in result.tests


def test_above_the_cap_the_full_shards_run_instead(tmp_path):
    files = dict(BASE)
    for i in range(12):
        files[f"tests/test_many_{i:02d}.py"] = "from app.services.qux import X\n"
    root = _tree(tmp_path, files)
    result = sel.select([P + "app/services/qux.py"], root, scm_runs=False, cap=10)
    assert result.full is True and result.count == 13
    under = sel.select([P + "app/services/qux.py"], root, scm_runs=False, cap=13)
    assert under.full is False and len(under.tests) == 13


def test_a_path_a_shell_would_parse_is_never_selected(tmp_path):
    files = dict(BASE)
    files["tests/test_bad name.py"] = "from app.services.foo import f\n"
    root = _tree(tmp_path, files)
    result = sel.select([P + "app/services/foo.py"], root, scm_runs=False)
    assert all(" " not in t for t in result.tests)


def test_cli_above_the_cap_writes_no_list_and_full_true(tmp_path):
    root = _tree(tmp_path, BASE)
    out = tmp_path / "gh_output"
    out.write_text("")
    proc = subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "ci_select_tests.py"), "--root", str(root), "--cap", "2"],
        input=f"{P}app/services/foo.py\n",
        env={"GITHUB_OUTPUT": str(out), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert dict(line.split("=", 1) for line in out.read_text().splitlines()) == {"tests": "", "full": "true"}
    assert "above the cap of 2" in proc.stdout and f"{P}tests/test_direct.py" in proc.stdout


def test_cli_writes_the_outputs_and_logs_the_list(tmp_path):
    root = _tree(tmp_path, BASE)
    out = tmp_path / "gh_output"
    out.write_text("")
    proc = subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "ci_select_tests.py"), "--root", str(root), "--scm", "false"],
        input=f"{P}app/services/qux.py\n{P}tests/test_direct.py\n",
        env={"GITHUB_OUTPUT": str(out), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert outputs == {
        "tests": f"{P}tests/test_direct.py {P}tests/test_unrelated.py",
        "full": "false",
    }
    assert f"{P}tests/test_unrelated.py" in proc.stdout


# #1411 (123d4282c) as GitHub listed it. The test that broke the 1 Oct release
# imports the ingest service at module level; the PR ran only the three test
# files it changed.
PR_1411 = [
    "documentation/plans/autocount/PLAN-spo-xlsx-product-fallback.md",
    "documentation/plans/autocount/spo-xlsx-product-fallback-acceptance-criteria.md",
    P + "app/services/grn_spo_matching.py",
    P + "app/services/incoming_stock_service.py",
    P + "app/services/procurement_service.py",
    P + "app/services/rules/shipping_order_rules.py",
    P + "app/services/shipping_order_ingest_service.py",
    P + "scripts/dedupe_spo_xlsx_superseded.py",
    P + "scripts/oneoff/dedupe_spo_standalone.py",
    P + "tests/test_dedupe_spo_standalone.py",
    P + "tests/test_spo_xlsx_product_fallback.py",
    P + "tests/test_spo_xlsx_supersede.py",
]


@pytest.mark.skipif(not (BACKEND / "app").is_dir(), reason="needs the backend tree")
def test_pr_1411_selects_the_test_that_broke_the_release():
    """#1411 touched procurement_service, which ~60 test files import: above the
    cap, so that PR would have run the full shards, which include the file too."""
    result = sel.select(PR_1411, BACKEND, scm_runs=False)
    assert P + "tests/test_ingest_parity_security_fixes.py" in result.tests
    for changed in PR_1411[-3:]:
        assert changed in result.tests
    assert result.full is True, result.count
    # The ingest service alone stays under the cap and still selects it.
    alone = sel.select([P + "app/services/shipping_order_ingest_service.py"], BACKEND, scm_runs=False)
    assert alone.full is False
    assert P + "tests/test_ingest_parity_security_fixes.py" in alone.tests
