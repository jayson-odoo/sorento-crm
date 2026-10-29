"""Where the CI jobs run: GitHub-hosted, or the self-hosted Mac mini runners on request.

CI-HOSTED-RUNNERS (owner, 29 Oct 2026): the repo is public again, so
GitHub-hosted minutes are free and run in parallel, where the one Mac runner
queued PR runs for hours. Everything runs on `ubuntu-latest` unless a release
dispatch asks otherwise:

1. The repo variables `RUNNER_TESTS` / `RUNNER_FAST` route nothing any more,
   and a PR run has no inputs, so a PR gate is always GitHub-hosted.
2. The workflow_dispatch input `runner`: `github` (the default), `auto`,
   `mac`. `mac` sends the test and fast-gate jobs to the Mac (label
   `sorento-mac`); `auto` sends the test jobs there when a `sorento-mac`
   runner is online and idle, else GitHub-hosted, decided inside
   `Changed areas` from the runners API with the `RUNNERS_READ_TOKEN` secret;
   no secret, or a failed call, means GitHub-hosted. Anything unknown lands
   on GitHub-hosted.
3. build-images and build-and-deploy always run on GitHub-hosted: the prod
   images are amd64 and the Mac runners are arm64.

The picker step is extracted from the workflow and executed with a stub `gh`,
as in test_ci_docs_only_filter.py, so nothing here can drift from the file.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
MAC = "sorento-mac"
GH = "ubuntu-latest"
PICK_STEP = "Pick the test runner"

TEST_JOBS = ["lean-gate", "test-backend", "test-backend-scm", "validate-frontend", "typecheck-frontend"]
FAST_JOBS = ["check-migration-heads", "pii-guard", "changes", "refuse-ci-full", "ci-gate"]
GITHUB_ONLY_JOBS = ["build-images", "build-and-deploy", "validate-backend", "validate-mcp"]

pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="workflow not present (backend-only checkout)")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _jobs() -> dict:
    return _workflow()["jobs"]


def _pick_script() -> str:
    steps = _jobs()["changes"]["steps"]
    step = next(s for s in steps if s.get("name") == PICK_STEP)
    return textwrap.dedent(step["run"])


GH_STUB = """\
#!/usr/bin/env bash
if [ "${GH_STUB_FAIL:-0}" = "1" ]; then echo "stub gh: failing on purpose" >&2; exit 1; fi
expr=""
while [ $# -gt 0 ]; do
  case "$1" in
    --jq) expr="$2"; shift ;;
  esac
  shift
done
exec jq -r "$expr" "$GH_STUB_FILE"
"""


def _runner(name: str, status: str, busy: bool, labels=("self-hosted", "Linux", "ARM64", MAC)) -> dict:
    return {"name": name, "status": status, "busy": busy, "labels": [{"name": n} for n in labels]}


def pick(tmp_path: Path, *, override: str = "", token: str = "", runners=None, gh_fails=False):
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed (the CI runner has it)")
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "gh").write_text(GH_STUB)
    (bindir / "gh").chmod(0o755)
    payload = tmp_path / "runners.json"
    payload.write_text(json.dumps({"total_count": len(runners or []), "runners": runners or []}))
    output = tmp_path / "output.txt"
    output.write_text("")
    env = {
        "PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "GITHUB_OUTPUT": str(output),
        "REPO": "jayson-odoo/sorento-crm",
        "OVERRIDE": override,
        "GH_TOKEN": token,
        "GH_STUB_FILE": str(payload),
        "GH_STUB_FAIL": "1" if gh_fails else "0",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _pick_script()],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
    assert set(out) == {"runner"}, out
    return out["runner"]


# --- the picker ------------------------------------------------------------

@pytest.mark.parametrize(
    "override,expected",
    [
        ("", GH),
        ("github", GH),
        ("mac", MAC),
        ("vars", GH),
        ("something-else", GH),
        ("self-hosted", GH),
    ],
)
def test_only_an_explicit_mac_override_leaves_github_hosted(tmp_path, override, expected):
    assert pick(tmp_path, override=override) == expected


def test_a_pr_run_stays_on_github_even_with_an_idle_mac(tmp_path):
    # A pull_request event has no inputs: OVERRIDE is empty whatever the repo variables say.
    idle = [_runner("mac-1", "online", False)]
    assert pick(tmp_path, override="", token="t", runners=idle) == GH


def test_auto_without_the_token_secret_stays_on_github(tmp_path):
    idle = [_runner("mac-1", "online", False)]
    assert pick(tmp_path, override="auto", token="", runners=idle) == GH


def test_auto_takes_the_mac_when_a_mac_runner_is_online_and_idle(tmp_path):
    runners = [_runner("mac-1", "online", True), _runner("mac-2", "online", False)]
    assert pick(tmp_path, override="auto", token="t", runners=runners) == MAC


def test_auto_overflows_to_github_when_every_mac_runner_is_busy(tmp_path):
    runners = [_runner("mac-1", "online", True), _runner("mac-2", "online", True)]
    assert pick(tmp_path, override="auto", token="t", runners=runners) == GH


def test_auto_falls_back_to_github_when_the_mac_is_offline(tmp_path):
    runners = [_runner("mac-1", "offline", False), _runner("mac-2", "offline", False)]
    assert pick(tmp_path, override="auto", token="t", runners=runners) == GH


def test_auto_ignores_idle_runners_without_the_mac_label(tmp_path):
    runners = [_runner("other", "online", False, labels=("self-hosted", "Linux", "X64"))]
    assert pick(tmp_path, override="auto", token="t", runners=runners) == GH


def test_auto_falls_back_to_github_when_the_runners_api_fails(tmp_path):
    assert pick(tmp_path, override="auto", token="t", gh_fails=True) == GH


# --- the workflow wiring -----------------------------------------------------

def test_dispatch_has_a_runner_choice_defaulting_to_github():
    inputs = _workflow()[True]["workflow_dispatch"]["inputs"]
    runner = inputs["runner"]
    assert runner["type"] == "choice" and runner["default"] == "github", runner
    assert runner["options"] == ["github", "auto", "mac"], runner


def test_no_job_reads_a_runner_repo_variable():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "vars.RUNNER_TESTS" not in text and "vars.RUNNER_FAST" not in text


def test_the_picker_is_the_first_step_of_changed_areas_and_feeds_its_output():
    changes = _jobs()["changes"]
    assert changes["steps"][0]["name"] == PICK_STEP
    step = changes["steps"][0]
    assert step["id"] == "runner"
    env = step["env"]
    assert env["OVERRIDE"] == "${{ inputs.runner }}"
    assert "SETTING" not in env
    # The token is only this step's, never the job's or the workflow's.
    assert env["GH_TOKEN"] == "${{ secrets.RUNNERS_READ_TOKEN }}"
    assert "RUNNERS_READ_TOKEN" not in json.dumps(changes.get("env", {}))
    assert "RUNNERS_READ_TOKEN" not in json.dumps(_workflow().get("env", {}))
    assert changes["outputs"]["tests_runner"] == "${{ steps.runner.outputs.runner }}"


@pytest.mark.parametrize("job", TEST_JOBS)
def test_test_jobs_run_where_the_picker_says(job):
    jobs = _jobs()
    assert "changes" in jobs[job]["needs"], job
    assert jobs[job]["runs-on"] == "${{ needs.changes.outputs.tests_runner || 'ubuntu-latest' }}", job


FAST_EXPR = "${{ inputs.runner == 'mac' && 'sorento-mac' || 'ubuntu-latest' }}"


@pytest.mark.parametrize("job", FAST_JOBS)
def test_fast_jobs_leave_github_hosted_only_on_a_mac_dispatch(job):
    assert _jobs()[job]["runs-on"] == FAST_EXPR, job


@pytest.mark.parametrize("job", GITHUB_ONLY_JOBS)
def test_image_and_deploy_jobs_stay_on_github_hosted(job):
    assert _jobs()[job]["runs-on"] == GH, job


def test_every_job_is_routed_on_purpose():
    assert set(_jobs()) == set(TEST_JOBS) | set(FAST_JOBS) | set(GITHUB_ONLY_JOBS)


# --- what a job on the Mac can hold -------------------------------------------
# The Mac runner keeps state between jobs, so a job routed there gets the
# least the job needs: read-only contents plus the writes it states (the two
# label-removing jobs), and no secret but the job token and, in the picker
# step only, RUNNERS_READ_TOKEN. Deploy, registry, SSH and SMTP secrets never.

WRITES_ALLOWED = {"lean-gate": {"pull-requests"}, "refuse-ci-full": {"pull-requests"}}


@pytest.mark.parametrize("job", TEST_JOBS + FAST_JOBS)
def test_mac_routable_jobs_hold_a_least_privilege_token(job):
    perms = _jobs()[job].get("permissions")
    assert isinstance(perms, dict), f"{job}: no permissions block (the repo default is write-all)"
    writes = {scope for scope, level in perms.items() if level == "write"}
    assert writes == WRITES_ALLOWED.get(job, set()), (job, perms)


@pytest.mark.parametrize("job", TEST_JOBS + FAST_JOBS)
def test_mac_routable_jobs_reach_no_secret_but_the_job_token(job):
    body = _jobs()[job]
    for step in body.get("steps", []):
        text = json.dumps(step)
        secrets = set(re.findall(r"secrets\.([A-Za-z_]+)", text))
        allowed = {"GITHUB_TOKEN"} | ({"RUNNERS_READ_TOKEN"} if step.get("name") == PICK_STEP else set())
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
# shard 7 hung to its cap. Two workers on the Mac, `auto` on GitHub-hosted, set
# in the step's env (the PR gate's script is executed by
# test_ci_docs_only_filter.py, and bash cannot run a `${{ }}`).
# `--max-worker-restart 0` ends the session on the first crashed worker, where
# xdist's default (4 x workers) respawned each one into the same pressure, and
# `-p tests._xdist_crash_guard` keeps that exit non-zero when the worker died
# before running a test (tests/test_xdist_crash_guard.py).

XDIST_WORKERS = "${{ needs.changes.outputs.tests_runner == 'sorento-mac' && 2 || 'auto' }}"
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
