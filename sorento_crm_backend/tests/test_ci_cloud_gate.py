"""CI-CLOUD-GATE (owner, 4 Nov 2026: "yes cloud CI"): GitHub runs fast checks and the release
build/deploy; tests run in Claude Code cloud sandboxes.

1. A `ci`-labelled pull request bills only fast checks on GitHub: no step that runs on a pull
   request executes pytest (`--collect-only` is an import check, not a run) or vitest, and the
   Postgres / Redis service containers do not start.
2. No job in any workflow runs on the Mac (`sorento-mac`) or any self-hosted runner: the Mac ran
   the release suite in 5-6 h (2 Nov) and stays free.
3. A release dispatch builds and deploys without a test matrix by default (`skip_tests` defaults
   to true; the cloud sweep tested the candidate). `full_suite=true` is the emergency full suite
   on GitHub and wins over `skip_tests`.
4. `scripts/crew-tests.sh` is what a lane runs in its sandbox instead: it picks what the old PR
   gate ran (import-selected backend tests, the forms chains on a forms change, the regression
   guards, the MCP suite, vitest --changed plus the source-scanning guards). Its `--plan` mode
   prints the selection without running anything, which is what these tests read.

Plan: documentation/plans/ci/PLAN-ci-cloud-gate-04nov.md.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy.yml"
CREW_TESTS = REPO / "scripts" / "crew-tests.sh"

pytestmark = pytest.mark.skipif(not DEPLOY.is_file(), reason="workflow not present (backend-only checkout)")

# What a pull_request run looks like to a step's `if`: the `ci` label, every area changed, a tree
# not yet validated. Step outputs (`steps.x.outputs.y`) are unknown, so they are treated as
# "could be anything": a step counts as running on a PR unless its `if` excludes the
# pull_request event outright.
PR_EXCLUDED = re.compile(r"^\s*github\.event_name\s*!=\s*'pull_request'\s*(&&|$)")

# pytest that executes tests: any pytest call without --collect-only. vitest: any `vitest` call.
_PYTEST = re.compile(r"\bpytest\b")
_VITEST = re.compile(r"\bvitest\b")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _deploy_jobs() -> dict:
    return _load(DEPLOY)["jobs"]


def _executing_lines(run: str) -> list[str]:
    hits = []
    for line in run.replace("\\\n", " ").splitlines():
        code = line.split("#", 1)[0]
        if _PYTEST.search(code) and "--collect-only" not in code and "pip install" not in code:
            hits.append(line.strip())
        if _VITEST.search(code):
            hits.append(line.strip())
    return hits


@pytest.mark.parametrize("job_id", ["changes", "lean-gate"])
def test_no_step_that_runs_on_a_pull_request_executes_pytest_or_vitest(job_id):
    bad = []
    for step in _deploy_jobs()[job_id]["steps"]:
        lines = _executing_lines(str(step.get("run", "")))
        if not lines:
            continue
        if PR_EXCLUDED.search(str(step.get("if", ""))):
            continue
        bad.append((step.get("name"), lines))
    assert not bad, f"{job_id}: these steps would execute tests on a pull request: {bad}"


def test_the_pr_gate_still_imports_every_test_file_and_type_checks():
    steps = {s.get("name"): s for s in _deploy_jobs()["lean-gate"]["steps"]}
    collect = steps["Pytest collect-only (catches import errors in tests)"]
    assert "pull_request" not in str(collect.get("if", "")), "the collect runs on a PR too now"
    joined = "\n".join(str(s.get("run", "")) for s in steps.values())
    assert "from app.main import app" in joined and "import worker" in joined
    assert "npm run typecheck" in joined
    assert "npx eslint" in joined, "the frontend lint runs on a PR"
    assert "create_mcp_app" in joined, "the MCP import check runs on a PR"


def test_the_service_containers_do_not_start_on_a_pull_request():
    services = _deploy_jobs()["lean-gate"]["services"]
    for name in ("postgres", "redis"):
        image = services[name]["image"]
        assert image.startswith("${{") and "github.event_name != 'pull_request'" in image, (name, image)
        assert image.rstrip("} ").endswith("|| ''"), (name, image)


def _every_job():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for jid, job in (_load(path).get("jobs") or {}).items():
            yield path.name, jid, job


def test_no_job_runs_on_the_mac_or_any_self_hosted_runner():
    for wf, jid, job in _every_job():
        runs_on = job.get("runs-on")
        assert runs_on == "ubuntu-latest", (wf, jid, runs_on)
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "sorento-mac" not in text and "self-hosted" not in text, path.name


def test_the_runner_override_and_its_token_are_gone():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "inputs.runner" not in text and "RUNNERS_READ_TOKEN" not in text and "tests_runner" not in text
    assert "runner" not in _load(DEPLOY)[True]["workflow_dispatch"]["inputs"]


def test_a_release_skips_the_tests_by_default_and_full_suite_is_off_by_default():
    inputs = _load(DEPLOY)[True]["workflow_dispatch"]["inputs"]
    assert inputs["skip_tests"]["default"] is True, inputs["skip_tests"]
    assert inputs["full_suite"]["default"] is False, inputs["full_suite"]


# --- scripts/crew-tests.sh --------------------------------------------------------------------


def _plan(tmp_path: Path, changed: list[str]) -> dict[str, str]:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    assert CREW_TESTS.is_file(), "scripts/crew-tests.sh is missing"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "CREW_CHANGED_FILES": "\n".join(changed),
    }
    result = subprocess.run(
        ["bash", str(CREW_TESTS), "--plan"], cwd=REPO, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = {}
    for line in result.stdout.splitlines():
        m = re.match(r"^plan\.(\w+)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def test_crew_tests_selects_backend_tests_by_import(tmp_path):
    """#1411: a change to the ingest service selects the test that imports it."""
    plan = _plan(tmp_path, ["sorento_crm_backend/app/services/shipping_order_ingest_service.py"])
    assert "tests/test_ingest_parity_security_fixes.py" in plan["backend"].split(), plan
    assert "tests/test_lessons_learnt_regressions.py" in plan["backend"].split(), "the guards always run"
    assert plan["vitest"] == "false" and plan["mcp"] == "false", plan


def test_crew_tests_runs_the_forms_chains_on_a_forms_change(tmp_path):
    plan = _plan(tmp_path, ["sorento_crm_backend/app/services/procurement_service.py"])
    assert plan["forms"] == "true", plan
    plan = _plan(tmp_path, ["sorento_crm_backend/app/services/inventory_service.py"])
    assert plan["forms"] == "false", plan


def test_crew_tests_runs_vitest_and_mcp_when_those_trees_change(tmp_path):
    plan = _plan(tmp_path, ["sorento_crm_frontend/lib/api-client.ts", "sorento_crm_mcp/sorento_crm_mcp/server.py"])
    assert plan["vitest"] == "true" and plan["mcp"] == "true", plan
    assert plan["backend"] == "", plan


def test_crew_tests_drops_ci_excluded_and_missing_files(tmp_path):
    excluded = [
        line.strip() for line in (REPO / "sorento_crm_backend" / "tests" / "ci_excluded.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    changed = ["sorento_crm_backend/tests/test_gone_for_good.py"]
    if excluded:
        changed.append(f"sorento_crm_backend/{excluded[0]}")
    plan = _plan(tmp_path, changed)
    assert "tests/test_gone_for_good.py" not in plan["backend"].split()
    if excluded:
        assert excluded[0] not in plan["backend"].split()


def test_crew_tests_on_a_docs_only_change_runs_nothing(tmp_path):
    plan = _plan(tmp_path, ["documentation/plans/ci/PLAN-x.md"])
    assert plan == {"backend": "", "forms": "false", "mcp": "false", "vitest": "false"}, plan
