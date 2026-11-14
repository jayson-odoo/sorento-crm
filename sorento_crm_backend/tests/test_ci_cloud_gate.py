"""CI-CLOUD-GATE (owner, 4 Nov 2026: "yes cloud CI"): GitHub runs fast checks and the release
build/deploy; tests run in Claude Code cloud sandboxes.

1. A pull request bills nothing on GitHub (CI-ZERO-MINUTES, 14 Nov 2026, pinned by
   tests/test_ci_zero_minutes.py): its fast checks run in the lane sandbox through
   `scripts/pr-gate.sh`, which still imports every test file, type-checks and lints.
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

import json
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
PR_GATE = REPO / "scripts" / "pr-gate.sh"

pytestmark = pytest.mark.skipif(not DEPLOY.is_file(), reason="workflow not present (backend-only checkout)")

def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _deploy_jobs() -> dict:
    return _load(DEPLOY)["jobs"]


def test_the_pr_gate_still_imports_every_test_file_and_type_checks():
    script = PR_GATE.read_text(encoding="utf-8")
    assert "pytest --collect-only" in script, "the collect runs on a PR"
    assert "from app.main import app" in script and "import worker" in script
    assert "npm run typecheck" in script
    assert "npx eslint" in script, "the frontend lint runs on a PR"
    assert "create_mcp_app" in script, "the MCP import check runs on a PR"


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


# --- security review (CI-CLOUD-GATE) -----------------------------------------------------------


def test_the_release_tests_checkout_keeps_no_token_for_repository_code():
    """Every step after the checkout runs repository code (npm install scripts, conftest): the
    checkout keeps no credentials and no step reaches a secret."""
    steps = {s.get("name"): s for s in _deploy_jobs()["lean-gate"]["steps"]}
    assert steps["Checkout"]["with"]["persist-credentials"] is False
    for name, step in steps.items():
        assert "secrets." not in str(step), name


def test_eslint_takes_file_names_as_operands_only():
    script = PR_GATE.read_text(encoding="utf-8")
    assert "git diff -z" in script and "xargs -0 -r npx eslint --no-warn-ignored --" in script


def test_crew_tests_never_inherits_a_database_from_the_shell():
    script = CREW_TESTS.read_text(encoding="utf-8")
    run_part = script.split("# --- run", 1)[1]
    assert "unset DATABASE_URL DIRECT_URL REDIS_URL" in run_part
    assert run_part.index("unset DATABASE_URL") < run_part.index("pytest_pass backend")
    assert ".env.ci-tests is missing" in run_part


# --- the release-sweep check (owner answer b, 4 Nov 2026) ---------------------------------------

SWEEP_STEP = "Release sweep passed on this sha"
SHA = "a" * 40
GH_STUB = """#!/usr/bin/env bash
echo "$@" >> "$GH_CALLS"
if [ "${GH_STUB_FAIL:-0}" = "1" ]; then echo "stub gh: failing" >&2; exit 1; fi
expr=""
while [ $# -gt 0 ]; do case "$1" in --jq) expr="$2"; shift ;; esac; shift; done
exec jq -r "$expr" "$GH_STUB_FILE"
"""


def _sweep(tmp_path: Path, *, statuses=(), skip_tests="true", full_suite="false", allow="false", gh_fails=False):
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed (the runner has it)")
    step = next(s for s in _deploy_jobs()["changes"]["steps"] if s.get("name") == SWEEP_STEP)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "gh").write_text(GH_STUB)
    (bindir / "gh").chmod(0o755)
    payload = tmp_path / "status.json"
    payload.write_text(json.dumps({"state": "pending", "statuses": [{"context": c, "state": s} for c, s in statuses]}))
    summary = tmp_path / "summary.md"
    summary.write_text("")
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    env = {
        "PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "GITHUB_REPOSITORY": "jayson-odoo/sorento-crm", "GITHUB_STEP_SUMMARY": str(summary),
        "SHA": SHA, "SKIP_TESTS": skip_tests, "FULL_SUITE": full_suite, "ALLOW_UNSWEPT": allow,
        "GH_STUB_FILE": str(payload), "GH_STUB_FAIL": "1" if gh_fails else "0", "GH_CALLS": str(calls),
    }
    result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                            env=env, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr, summary.read_text(), calls.read_text()


def test_a_swept_sha_releases(tmp_path):
    rc, out, summary, calls = _sweep(tmp_path, statuses=[("release-sweep", "success"), ("other", "failure")])
    assert rc == 0, out
    assert f"commits/{SHA}/status" in calls
    assert "Release sweep: success" in summary


@pytest.mark.parametrize("statuses", [[], [("release-sweep", "failure")], [("release-sweep", "pending")], [("other", "success")]])
def test_an_unswept_sha_is_refused(tmp_path, statuses):
    rc, out, summary, _ = _sweep(tmp_path, statuses=statuses)
    assert rc == 1, out
    assert "No release sweep" in out and "Release refused" in summary


def test_a_failed_status_lookup_is_refused(tmp_path):
    rc, out, _, _ = _sweep(tmp_path, gh_fails=True)
    assert rc == 1 and "lookup failed" in out, out


def test_allow_unswept_releases_and_says_so_in_the_summary(tmp_path):
    rc, out, summary, _ = _sweep(tmp_path, allow="true")
    assert rc == 0, out
    assert "UNSWEPT RELEASE" in out and "UNSWEPT RELEASE" in summary and "allow_unswept=true" in summary


@pytest.mark.parametrize("skip_tests,full_suite", [("false", "false"), ("true", "true"), ("false", "true")])
def test_a_release_that_tests_on_github_needs_no_sweep(tmp_path, skip_tests, full_suite):
    rc, out, _, calls = _sweep(tmp_path, skip_tests=skip_tests, full_suite=full_suite)
    assert rc == 0, out
    assert calls == "", "no status lookup when GitHub runs the tests"


def test_the_sweep_check_is_wired_first_with_a_read_only_status_scope():
    wf = _load(DEPLOY)
    inputs = wf[True]["workflow_dispatch"]["inputs"]
    assert inputs["allow_unswept"]["type"] == "boolean" and inputs["allow_unswept"]["default"] is False
    changes = wf["jobs"]["changes"]
    step = changes["steps"][0]
    assert step["name"] == SWEEP_STEP and step["if"] == "github.event_name == 'workflow_dispatch'"
    assert step["env"]["SHA"] == "${{ github.sha }}"
    assert step["env"]["ALLOW_UNSWEPT"] == "${{ inputs.allow_unswept }}"
    assert changes["permissions"]["statuses"] == "read"
    # A failed `changes` reaches the deploy job as a failure: it never deploys.
    deploy = wf["jobs"]["build-and-deploy"]
    assert "changes" in deploy["needs"] and "!contains(needs.*.result, 'failure')" in deploy["if"]
    assert wf["jobs"]["build-images"]["needs"] == ["changes"] or "changes" in wf["jobs"]["build-images"]["needs"]


def test_crew_tests_refuses_a_head_behind_main_and_never_prints_a_clean_failed_line():
    script = CREW_TESTS.read_text(encoding="utf-8")
    assert "git merge-base --is-ancestor refs/remotes/origin/main HEAD" in script
    assert "merge origin/main first" in script
    assert "fetch --no-tags --quiet origin +refs/heads/main:refs/remotes/origin/main || true" not in script
    assert 'verdict=" FAILED (exit $rc)"' in script and "$verdict\"" in script
