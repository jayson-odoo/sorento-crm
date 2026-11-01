"""Where the CI jobs run: the self-hosted Mac mini runner, bar the image build and the deploy.

CI-MAC-ONLY (owner, 1 Nov 2026): the repo is private, so GitHub-hosted minutes
bill against a 3,000 min/month quota; "only the build and deploy to server
should be ran on github, others can run on mac mini as the runner".

1. Every deploy.yml job but build-images and build-and-deploy runs on
   `[self-hosted, sorento-mac]`, written literally: no expression, so nothing
   can route it back to `ubuntu-latest` when the Mac is busy or offline (the
   job queues instead).
2. build-images and build-and-deploy run on `ubuntu-latest`: the prod images
   are amd64 and the Mac runner is arm64.
3. The dispatch input `runner` stays declared (a dispatch passing
   `-f runner=github` must still parse) and routes nothing.
4. outline-user-guides-sync and never-stuck-nightly run on the Mac too;
   rollback stays GitHub-hosted (it reaches the server).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "deploy.yml"
MAC_LABELS = ["self-hosted", "sorento-mac"]
GH = "ubuntu-latest"

TEST_JOBS = ["lean-gate", "test-backend", "test-backend-scm", "validate-frontend", "typecheck-frontend"]
FAST_JOBS = ["check-migration-heads", "pii-guard", "changes", "refuse-ci-full", "ci-gate"]
IMAGE_JOBS = ["validate-backend", "validate-mcp"]
MAC_JOBS = TEST_JOBS + FAST_JOBS + IMAGE_JOBS
GITHUB_ONLY_JOBS = ["build-images", "build-and-deploy"]

pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="workflow not present (backend-only checkout)")


def _workflow(path: Path = WORKFLOW) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _jobs() -> dict:
    return _workflow()["jobs"]


# --- the workflow wiring -----------------------------------------------------

@pytest.mark.parametrize("job", MAC_JOBS)
def test_every_gate_and_test_job_runs_on_the_mac_with_no_fallback(job):
    assert _jobs()[job]["runs-on"] == MAC_LABELS, job


@pytest.mark.parametrize("job", GITHUB_ONLY_JOBS)
def test_image_and_deploy_jobs_stay_on_github_hosted(job):
    assert _jobs()[job]["runs-on"] == GH, job


def test_every_job_is_routed_on_purpose():
    assert set(_jobs()) == set(MAC_JOBS) | set(GITHUB_ONLY_JOBS)


def test_no_job_routes_by_expression_or_repo_variable():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "vars.RUNNER_TESTS" not in text and "vars.RUNNER_FAST" not in text
    assert "tests_runner" not in text
    assert "RUNNERS_READ_TOKEN" not in re.sub(r"(?m)^\s*#.*$", "", text)
    for name, body in _jobs().items():
        assert "${{" not in json.dumps(body["runs-on"]), name


def test_the_runner_input_still_parses_and_routes_nothing():
    inputs = _workflow()[True]["workflow_dispatch"]["inputs"]
    runner = inputs["runner"]
    assert runner["type"] == "choice" and runner["default"] == "github", runner
    assert runner["options"] == ["github", "auto", "mac"], runner
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "inputs.runner" not in text


def test_the_image_and_deploy_jobs_need_no_output_of_a_removed_path():
    jobs = _jobs()
    produced = set(jobs["changes"]["outputs"])
    for job in GITHUB_ONLY_JOBS:
        used = set(re.findall(r"needs\.changes\.outputs\.([a-z_]+)", json.dumps(jobs[job])))
        assert used <= produced, (job, used - produced)


@pytest.mark.parametrize("workflow,job", [("outline-user-guides-sync.yml", "sync"), ("never-stuck-nightly.yml", "smoke")])
def test_the_other_ci_workflows_run_on_the_mac(workflow, job):
    path = WORKFLOWS / workflow
    if not path.exists():
        pytest.skip(f"{path} not present")
    assert _workflow(path)["jobs"][job]["runs-on"] == MAC_LABELS


def test_never_stuck_installs_chromium_without_apt():
    path = WORKFLOWS / "never-stuck-nightly.yml"
    if not path.exists():
        pytest.skip(f"{path} not present")
    runs = "\n".join(s.get("run", "") for s in _workflow(path)["jobs"]["smoke"]["steps"])
    runs = re.sub(r"(?m)^\s*#.*$", "", runs)
    assert "playwright install chromium" in runs and "--with-deps" not in runs


def test_rollback_stays_on_github_hosted():
    path = WORKFLOWS / "rollback.yml"
    if not path.exists():
        pytest.skip(f"{path} not present")
    assert {j["runs-on"] for j in _workflow(path)["jobs"].values()} == {GH}


# --- what a job on the Mac can hold -------------------------------------------
# The Mac runner keeps state between jobs, so a job routed there gets the
# least the job needs: read-only contents plus the writes it states (the two
# label-removing jobs), and no secret but the job token. Deploy, registry
# (Docker Hub), SSH and SMTP secrets never.

WRITES_ALLOWED = {"lean-gate": {"pull-requests"}, "refuse-ci-full": {"pull-requests"}}


@pytest.mark.parametrize("job", MAC_JOBS)
def test_mac_routable_jobs_hold_a_least_privilege_token(job):
    perms = _jobs()[job].get("permissions")
    assert isinstance(perms, dict), f"{job}: no permissions block (the repo default is write-all)"
    writes = {scope for scope, level in perms.items() if level == "write"}
    assert writes == WRITES_ALLOWED.get(job, set()), (job, perms)


@pytest.mark.parametrize("job", MAC_JOBS)
def test_mac_routable_jobs_reach_no_secret_but_the_job_token(job):
    body = _jobs()[job]
    for step in body.get("steps", []):
        text = json.dumps(step)
        secrets = set(re.findall(r"secrets\.([A-Za-z_]+)", text))
        allowed = {"GITHUB_TOKEN"}
        assert secrets <= allowed, (job, step.get("name"), secrets - allowed)
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


# --- how many xdist workers a job on the Mac runs -----------------------------
# The Mac runner's VM is 4 CPU, 6 GiB, no swap (scripts/ci-runner/up.sh). `-n
# auto` there is 4 workers at about 1.4 GB each, plus Postgres and Redis: the
# release run 39126899668 lost four workers of shard 5 to the OOM killer and
# shard 7 hung to its cap. Two workers, now that every test job runs there, set
# in the step's env (the PR gate's script is executed by
# test_ci_docs_only_filter.py, and bash cannot run a `${{ }}`).
# `--max-worker-restart 0` ends the session on the first crashed worker, where
# xdist's default (4 x workers) respawned each one into the same pressure, and
# `-p tests._xdist_crash_guard` keeps that exit non-zero when the worker died
# before running a test (tests/test_xdist_crash_guard.py).

XDIST_WORKERS = "2"
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
def test_xdist_on_the_mac_runs_two_workers_and_never_respawns_a_crashed_one(job):
    for step, calls in _xdist_steps(job):
        assert step.get("env", {}).get("XDIST_WORKERS") == XDIST_WORKERS, (job, step.get("name"))
        for line in calls:
            assert '-n "$XDIST_WORKERS"' in line, (job, step.get("name"), line)
            assert "--max-worker-restart 0" in line, (job, step.get("name"), line)
            assert "-p tests._xdist_crash_guard" in line, (job, step.get("name"), line)


@pytest.mark.parametrize("job", TEST_JOBS)
def test_the_test_jobs_run_in_utc_like_prod(job):
    """RELEASE5-FIX: the sorento-mac VM is Asia/Kuala_Lumpur, and naive-time tests moved 8 h on it
    (release run 40680704839). GitHub-hosted runners were UTC, and no tracked image or deploy file sets a
    TZ for prod (image default, UTC), so every test job pins UTC."""
    wf = _workflow()
    spec = wf["jobs"][job]
    assert spec.get("env", {}).get("TZ", wf.get("env", {}).get("TZ")) == "UTC", job
    for step in spec.get("steps", []):
        assert step.get("env", {}).get("TZ", "UTC") == "UTC", (job, step.get("name"))
