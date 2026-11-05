"""RELEASE-DELTA-AFFECTED (owner, 5 Nov 2026): the release delta runs only the tests that are
affected, dependent, or depended by. These pin scripts/release_delta_select.py's rules on small
fake backend trees (no database), plus one guard that release-delta.sh uses the selector.

Plan: documentation/plans/ci/PLAN-release-delta-affected-05nov.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))
import release_delta_select as rds  # noqa: E402

B = "sorento_crm_backend/"
F = "sorento_crm_frontend/"


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    """A repo at tmp_path with the backend at sorento_crm_backend/; paths are repo-relative."""
    base = {
        B + "app/__init__.py": "",
        B + "app/models/__init__.py": "from .user import User\nfrom .order import Order\n",
        B + "app/models/user.py": "class User: ...\n",
        B + "app/models/order.py": "from app.models.user import User\nclass Order: ...\n",
        B + "app/services/__init__.py": "",
        B + "app/services/pricing.py": "from app.models import Order\ndef price(): ...\n",
        B + "app/services/ingest.py": "def run():\n    from app.services import pricing\n    return pricing.price()\n",
        B + "app/api/__init__.py": "",
        B + "app/api/ingest_route.py": "from app.services.ingest import run\n",
        B + "app/main.py": "from app.api import ingest_route\n",
        B + "tests/__init__.py": "",
        B + "tests/ci_excluded.txt": "# excluded\ntests/test_excluded.py\n",
        B + "tests/test_user.py": "from app.models import User\n",
        B + "tests/test_pricing.py": "from app.services.pricing import price\n",
        B + "tests/test_ingest.py": "from app.services.ingest import run\n",
        B + "tests/test_api.py": "from app.main import app\n",
        B + "tests/test_unrelated.py": "import os\n",
        B + "tests/test_excluded.py": "from app.models.user import User\n",
        B + "tests/test_lessons_learnt_regressions.py": "import re\n",
        B + "tests/scm/__init__.py": "",
        B + "tests/scm/test_scm_orders.py": "from app.models.order import Order\n",
        B + "tests/scm/test_scm_other.py": "import json\n",
        B + "tests/test_migration_001_x.py": "import json\n",
        F + "lib/a.ts": "export const a = 1\n",
        F + "lib/a.test.ts": "import { a } from './a'\n",
    }
    base.update(files)
    for rel, text in base.items():
        if text is None:
            continue
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path / "sorento_crm_backend"


def _select(tmp_path, changed, files=None, **kw):
    root = _tree(tmp_path, files or {})
    return rds.select(changed, root, **kw)


def test_dependents_are_transitive_through_module_level_imports(tmp_path):
    res = _select(tmp_path, [B + "app/models/user.py"])
    assert res.backend == "selected"
    # order.py imports user at module level, pricing imports Order (re-exported), test_pricing
    # imports pricing: all three hops followed.
    for t in ("tests/test_user.py", "tests/test_pricing.py", "tests/scm/test_scm_orders.py"):
        assert t in res.tests, t
    assert "tests/test_unrelated.py" not in res.tests
    assert "tests/scm/test_scm_other.py" not in res.tests


def test_scm_runs_only_when_the_graph_reaches_it(tmp_path):
    res = _select(tmp_path, [B + "app/services/ingest.py"])
    assert not [t for t in res.tests if t.startswith("tests/scm/")]


def test_lazy_import_is_one_hop_not_propagated(tmp_path):
    # ingest.py imports pricing inside a function: ingest's tests run, but app/main.py (which
    # imports ingest at module level through the route) does not drag in every API test.
    res = _select(tmp_path, [B + "app/services/pricing.py"])
    assert "tests/test_pricing.py" in res.tests
    assert "tests/test_ingest.py" in res.tests
    assert "tests/test_api.py" not in res.tests


def test_module_level_chain_reaches_api_tests_through_main(tmp_path):
    res = _select(tmp_path, [B + "app/services/ingest.py"])
    assert {"tests/test_ingest.py", "tests/test_api.py"} <= set(res.tests)


def test_depended_by_selects_the_named_tests_of_a_direct_import(tmp_path):
    # ingest.py calls pricing: a change to ingest runs test_pricing (the test of its callee)
    # even though nothing about test_pricing imports ingest.
    res = _select(tmp_path, [B + "app/services/ingest.py"])
    assert "tests/test_pricing.py" in res.tests
    assert res.why["tests/test_pricing.py"].startswith("tests app/services/pricing.py")


def test_depended_by_needs_the_name_and_the_import(tmp_path):
    files = {B + "tests/test_pricing_extra.py": "import os\n"}  # named like pricing, imports nothing
    res = _select(tmp_path, [B + "app/services/ingest.py"], files)
    assert "tests/test_pricing_extra.py" not in res.tests


def test_reexport_points_at_the_defining_module_not_the_package(tmp_path):
    # test_account imports `from app.models import User`; a change to order.py must not select
    # it through app/models/__init__.py (which imports .order at module level).
    files = {B + "tests/test_account.py": "from app.models import User\n"}
    res = _select(tmp_path, [B + "app/models/order.py"], files)
    assert "tests/test_account.py" not in res.tests
    assert "tests/test_pricing.py" in res.tests


def test_relative_imports_resolve(tmp_path):
    files = {
        B + "app/services/helper.py": "X = 1\n",
        B + "app/services/user_rel.py": "from .helper import X\n",
        B + "tests/test_user_rel.py": "from app.services.user_rel import X\n",
    }
    res = _select(tmp_path, [B + "app/services/helper.py"], files)
    assert "tests/test_user_rel.py" in res.tests


def test_patch_target_string_in_a_test_counts(tmp_path):
    files = {B + "tests/test_patches.py": "def test_x(monkeypatch):\n    monkeypatch.setattr('app.services.pricing.price', None)\n"}
    res = _select(tmp_path, [B + "app/services/pricing.py"], files)
    assert "tests/test_patches.py" in res.tests


def test_dotted_string_in_app_code_is_not_an_edge(tmp_path):
    files = {B + "app/services/doc.py": '"""See app.services.pricing for the rules."""\n',
             B + "tests/test_doc.py": "from app.services.doc import *\n"}
    res = _select(tmp_path, [B + "app/services/pricing.py"], files)
    assert "tests/test_doc.py" not in res.tests


def test_changed_test_file_selects_itself_and_excluded_never_runs(tmp_path):
    res = _select(tmp_path, [B + "tests/test_unrelated.py", B + "app/models/user.py"])
    assert "tests/test_unrelated.py" in res.tests
    assert "tests/test_excluded.py" not in res.tests


def test_migration_tests_only_on_alembic_or_models(tmp_path):
    assert "tests/test_migration_001_x.py" not in _select(tmp_path / "a", [B + "app/services/pricing.py"]).tests
    res = _select(tmp_path / "b", [B + "alembic/versions/x_0001.py"])
    assert res.migrations and "tests/test_migration_001_x.py" in res.tests
    res = _select(tmp_path / "c", [B + "app/models/user.py"])
    assert res.migrations and "tests/test_migration_001_x.py" in res.tests


def test_regression_guards_run_on_any_backend_change(tmp_path):
    assert "tests/test_lessons_learnt_regressions.py" in _select(tmp_path, [B + "start.sh"]).tests


def test_non_module_file_selects_the_tests_that_name_it(tmp_path):
    files = {B + "tests/test_workflow.py": "WF = '.github/workflows/deploy.yml'\n",
             B + "app/services/mirror.py": "# mirrors lib/a.ts on the frontend\n",
             B + "tests/test_mirror.py": "from app.services.mirror import *\n"}
    res = _select(tmp_path, [".github/workflows/deploy.yml", F + "lib/a.ts"], files)
    assert "tests/test_workflow.py" in res.tests
    # A comment in app code naming a frontend file is not a load.
    assert "tests/test_mirror.py" not in res.tests


def test_app_template_counts_through_the_module_that_names_it(tmp_path):
    files = {B + "app/templates/mail.html": "<p/>",
             B + "app/services/mailer.py": "TEMPLATE = 'mail.html'\n",
             B + "tests/test_mailer.py": "from app.services.mailer import TEMPLATE\n"}
    res = _select(tmp_path, [B + "app/templates/mail.html"], files)
    assert "tests/test_mailer.py" in res.tests


def test_deleted_module_selects_tests_naming_it(tmp_path):
    files = {B + "tests/test_gone.py": "PATCH = 'app.services.gone.fn'\n"}
    res = _select(tmp_path, [B + "app/services/gone.py"], files)
    assert "tests/test_gone.py" in res.tests


@pytest.mark.parametrize("path, reason", [
    (B + "tests/conftest.py", "conftest"),
    (B + "tests/scm/conftest.py", "conftest"),
    (B + "requirements.txt", "dependency"),
    (B + "pytest.ini", "pytest"),
    (B + "tests/ci_excluded.txt", "test infrastructure"),
    (B + "scripts/bootstrap_env.py", "env bootstrap"),
    ("scripts/cloud-env-setup.sh", "env bootstrap"),
])
def test_full_fallbacks(tmp_path, path, reason):
    res = _select(tmp_path, [path])
    assert res.backend == "full" and reason in res.backend_reason
    assert len(res.tests) == res.total
    assert "tests/test_excluded.py" not in res.tests
    assert res.migrations


def test_graph_build_failure_is_a_full_run(tmp_path):
    res = _select(tmp_path, [B + "app/services/pricing.py"], {B + "app/services/broken.py": "def (:\n"})
    assert res.backend == "full" and "import graph build failed" in res.backend_reason
    assert "app/services/broken.py" in res.backend_reason


def test_no_backend_change_selects_nothing(tmp_path):
    res = _select(tmp_path, ["documentation/x.md"])
    assert res.backend == "none" and res.tests == [] and not res.migrations
    assert res.total > 0


def test_frontend_related_and_full(tmp_path):
    res = _select(tmp_path / "a", [F + "lib/a.ts", F + "lib/deleted.ts"])
    assert res.vitest == "related" and res.vitest_files == ["lib/a.ts"]
    for path in ("package.json", "package-lock.json", "vitest.config.ts", "vitest.setup.ts",
                 "tsconfig.json", "test-mocks/ui-tooltip.tsx", "lib/__mocks__/x.ts"):
        res = _select(tmp_path / path.replace("/", "_"), [F + path])
        assert res.vitest == "full", path
    assert _select(tmp_path / "none", [B + "app/main.py"]).vitest == "none"


def test_graph_is_cached_per_key(tmp_path):
    root = _tree(tmp_path, {})
    cache = tmp_path / "cache"
    first = rds.select([B + "app/models/user.py"], root, cache_dir=cache, cache_key="k1")
    second = rds.select([B + "app/models/user.py"], root, cache_dir=cache, cache_key="k1")
    assert (first.graph_source, second.graph_source) == ("built", "cache")
    assert first.tests == second.tests
    # A cache whose files differ from the tree is rebuilt, never trusted.
    (root / "tests" / "test_new.py").write_text("from app.models.user import User\n")
    third = rds.select([B + "app/models/user.py"], root, cache_dir=cache, cache_key="k1")
    assert third.graph_source == "built" and "tests/test_new.py" in third.tests


def test_cli_writes_the_lists_and_counts(tmp_path, capsys, monkeypatch):
    import io
    root = _tree(tmp_path, {})
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{B}app/models/user.py\n{F}lib/a.ts\n"))
    rc = rds.main(["--changed-from", "-", "--backend", str(root), "--out", str(tmp_path / "out"), "--cache-dir", ""])
    assert rc == 0
    kv = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    selected = (tmp_path / "out" / "selected.txt").read_text().split()
    assert kv["backend"] == "selected" and int(kv["backend_selected"]) == len(selected)
    assert int(kv["backend_total"]) >= len(selected) and kv["vitest"] == "related"
    assert (tmp_path / "out" / "vitest_related.txt").read_text().split() == ["lib/a.ts"]


def test_release_delta_uses_the_selector():
    script = (BACKEND.parent / "scripts" / "release-delta.sh")
    if not script.is_file():
        pytest.skip("repo scripts not present (backend-only checkout)")
    text = script.read_text()
    assert "release_delta_select.py" in text
    assert "vitest related" in text
    assert "selected $" in text or "selected ${" in text  # the crew-tests line carries "selected N of M"
