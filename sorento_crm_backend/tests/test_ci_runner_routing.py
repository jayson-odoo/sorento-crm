"""Where the CI jobs run: GitHub-hosted, every job (CI-CLOUD-GATE, owner 4 Nov 2026).

The Mac mini's self-hosted runner ran the release suite in 5-6 h (2 Nov, 28 jobs one at a time)
and stays free; tests run in Claude Code cloud sandboxes instead
(documentation/plans/ci/PLAN-ci-cloud-gate-04nov.md). So:

1. Every job of deploy.yml is `ubuntu-latest`; the `runner` dispatch input, the runner picker
   step and its runners-API token are gone (test_ci_cloud_gate.py pins every workflow file).
2. Every job that runs tests or gates holds a least-privilege token and no secret but the job
   token: the repo default is write-all.
3. xdist runs `auto` workers and never respawns a crashed worker; the test jobs run in UTC.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
GH = "ubuntu-latest"

TEST_JOBS = ["lean-gate", "test-backend", "test-backend-scm", "validate-frontend", "typecheck-frontend"]
FAST_JOBS = ["check-migration-heads", "pii-guard", "changes", "refuse-ci-full", "ci-gate"]
IMAGE_JOBS = ["build-images", "build-and-deploy", "validate-backend", "validate-mcp"]

pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="workflow not present (backend-only checkout)")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _jobs() -> dict:
    return _workflow()["jobs"]


# --- the workflow wiring -----------------------------------------------------

def test_no_job_reads_a_runner_repo_variable():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "vars.RUNNER_TESTS" not in text and "vars.RUNNER_FAST" not in text


def test_dispatch_has_no_runner_choice():
    assert "runner" not in _workflow()[True]["workflow_dispatch"]["inputs"]


@pytest.mark.parametrize("job", TEST_JOBS + FAST_JOBS + IMAGE_JOBS)
def test_every_job_is_github_hosted(job):
    assert _jobs()[job]["runs-on"] == GH, job


def test_every_job_is_routed_on_purpose():
    assert set(_jobs()) == set(TEST_JOBS) | set(FAST_JOBS) | set(IMAGE_JOBS)


# --- what a test or gate job can hold -------------------------------------------
# Read-only contents plus the writes it states (the two label-removing jobs), and no secret
# but the job token. Deploy, registry, SSH and SMTP secrets never.

WRITES_ALLOWED = {"lean-gate": {"pull-requests"}, "refuse-ci-full": {"pull-requests"}}


@pytest.mark.parametrize("job", TEST_JOBS + FAST_JOBS)
def test_test_and_gate_jobs_hold_a_least_privilege_token(job):
    perms = _jobs()[job].get("permissions")
    assert isinstance(perms, dict), f"{job}: no permissions block (the repo default is write-all)"
    writes = {scope for scope, level in perms.items() if level == "write"}
    assert writes == WRITES_ALLOWED.get(job, set()), (job, perms)


@pytest.mark.parametrize("job", TEST_JOBS + FAST_JOBS)
def test_test_and_gate_jobs_reach_no_secret_but_the_job_token(job):
    body = _jobs()[job]
    for step in body.get("steps", []):
        secrets = set(re.findall(r"secrets\.([A-Za-z_]+)", json.dumps(step)))
        assert secrets <= {"GITHUB_TOKEN"}, (job, step.get("name"), secrets)
    rest = json.dumps({k: v for k, v in body.items() if k != "steps"})
    assert set(re.findall(r"secrets\.([A-Za-z_]+)", rest)) <= {"GITHUB_TOKEN"}, job


@pytest.mark.parametrize("machine,expected", [("aarch64", "linux_arm64"), ("arm64", "linux_arm64"), ("x86_64", "linux_x64")])
def test_the_gitleaks_cli_matches_the_runner_architecture(tmp_path, machine, expected):
    script = (ROOT / "scripts" / "ci_gitleaks.sh").read_text(encoding="utf-8")
    block = re.search(r'^case "\$\(uname -m\)" in\n.*?^esac$', script, re.S | re.M)
    assert block, "ci_gitleaks.sh no longer picks the CLI by uname -m"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "uname").write_text(f"#!/bin/sh\necho {machine}\n")
    (bindir / "uname").chmod(0o755)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", block.group(0) + '\necho "$arch"'],
        env={"PATH": f"{bindir}:/usr/bin:/bin"}, capture_output=True, text=True,
    )
    assert result.stdout.strip() == expected, result.stdout + result.stderr


# --- xdist ----------------------------------------------------------------------
# `auto` workers, set in the step's env (the release tests' script is executed by
# test_ci_docs_only_filter.py with the same env). `--max-worker-restart 0` ends the session on
# the first crashed worker, where xdist's default (4 x workers) respawned each one into the same
# pressure (release run 39126899668 lost four workers of shard 5 to the OOM killer), and
# `-p tests._xdist_crash_guard` keeps that exit non-zero when the worker died before running a
# test (tests/test_xdist_crash_guard.py).

XDIST_WORKERS = "auto"
XDIST_JOBS = ["lean-gate", "test-backend", "test-backend-scm"]
# An xdist call: `--dist`, or a worker count (not `[ -n "$x" ]` or `echo -n`).
_XDIST_CALL = re.compile(r"\s--dist[\s=]|\s(-n|--numprocesses)[\s=]+(auto|logical|\d+|\$\{\{)")


def _xdist_steps(job: str) -> list[tuple[dict, list[str]]]:
    found = []
    for step in _jobs()[job].get("steps", []):
        run = (step.get("run") or "").replace("\\\n", " ")
        calls = [line.strip() for line in run.splitlines() if _XDIST_CALL.search(line)]
        if calls:
            found.append((step, calls))
    return found


@pytest.mark.parametrize("job", XDIST_JOBS)
def test_the_backend_test_jobs_run_xdist(job):
    assert _xdist_steps(job), f"{job}: no xdist call found, XDIST_JOBS is stale"


@pytest.mark.parametrize("job", TEST_JOBS)
def test_xdist_runs_auto_workers_and_never_respawns_a_crashed_one(job):
    for step, calls in _xdist_steps(job):
        assert step.get("env", {}).get("XDIST_WORKERS") == XDIST_WORKERS, (job, step.get("name"))
        for line in calls:
            assert '-n "$XDIST_WORKERS"' in line, (job, step.get("name"), line)
            assert "--max-worker-restart 0" in line, (job, step.get("name"), line)
            assert "-p tests._xdist_crash_guard" in line, (job, step.get("name"), line)


@pytest.mark.parametrize("job", TEST_JOBS)
def test_the_test_jobs_run_in_utc_like_prod(job):
    """RELEASE5-FIX: a runner VM in Asia/Kuala_Lumpur moved naive-time tests 8 h (release run
    40680704839). No tracked image or deploy file sets a TZ for prod (image default, UTC), so every
    test job pins UTC whatever runner it lands on."""
    wf = _workflow()
    spec = wf["jobs"][job]
    assert spec.get("env", {}).get("TZ", wf.get("env", {}).get("TZ")) == "UTC", job
    for step in spec.get("steps", []):
        assert step.get("env", {}).get("TZ", "UTC") == "UTC", (job, step.get("name"))
