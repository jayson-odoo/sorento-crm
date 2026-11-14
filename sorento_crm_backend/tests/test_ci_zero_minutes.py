"""CI-ZERO-MINUTES: GitHub Actions only builds, deploys and rolls back; the PR gate runs in the
lane sandbox through `scripts/pr-gate.sh` and crew posts its result as the `PR gate` status.

Contract: documentation/plans/ci/ci-zero-minutes-acceptance-criteria.md (sections A and B).

The workflow tests read the real `.github/workflows/`. The script tests never touch the real
repo's git state: each builds a throwaway repo in tmp_path, copies `scripts/pr-gate.sh` into it
and stubs the check commands B4 names (`scripts/ci_alembic_heads.py` and friends) with files that
record their own run, so a real run needs no network and no real tool.
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
PR_GATE = REPO / "scripts" / "pr-gate.sh"

ALWAYS = ["alembic-heads", "pii", "ai-coverage", "outline-guides", "gitleaks"]
BACKEND = ["backend-imports", "backend-collect"]
MCP = ["mcp-imports"]
FRONTEND = ["frontend-tsc", "frontend-eslint"]
EVERY = ALWAYS + BACKEND + MCP + FRONTEND


def _load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text())
    # PyYAML reads the bare key `on` as boolean True.
    if True in doc:
        doc["on"] = doc.pop(True)
    return doc


def _triggers(path: Path) -> set[str]:
    on = _load(path)["on"]
    if isinstance(on, str):
        return {on}
    return set(on)


# --- A. workflows ------------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.y*ml")), ids=lambda p: p.name)
def test_a1_every_workflow_triggers_only_on_dispatch_or_merge_group(path):
    triggers = _triggers(path)
    assert triggers <= {"workflow_dispatch", "merge_group"}, (path.name, sorted(triggers))
    for banned in ("pull_request", "pull_request_target", "push", "schedule"):
        assert banned not in triggers, (path.name, banned)


def test_a2_deploy_triggers_are_exactly_merge_group_and_dispatch():
    assert _triggers(DEPLOY) == {"merge_group", "workflow_dispatch"}


def test_a3_deploy_has_no_refuse_ci_full_job():
    assert "refuse-ci-full" not in _load(DEPLOY)["jobs"]


@pytest.mark.parametrize(
    "needle", ["github.event_name == 'pull_request'", "github.event.pull_request", "github.event.label"]
)
def test_a3_deploy_keeps_no_pull_request_branches_as_dead_code(needle):
    assert needle not in DEPLOY.read_text(), needle


def test_a4_lean_gate_name_is_the_static_release_tests():
    assert _load(DEPLOY)["jobs"]["lean-gate"]["name"] == "Release tests"


def test_a5_a_release_still_refuses_two_alembic_heads():
    jobs = _load(DEPLOY)["jobs"]
    assert jobs["check-migration-heads"]["name"] == "Single alembic head (fast gate)"
    needs = jobs["build-and-deploy"]["needs"]
    needs = [needs] if isinstance(needs, str) else needs
    assert "check-migration-heads" in needs, needs


def test_a6_outline_sync_is_manual_only():
    assert _triggers(WORKFLOWS / "outline-user-guides-sync.yml") == {"workflow_dispatch"}


@pytest.mark.parametrize("name", ["rollback.yml", "tests-sharded.yml"])
def test_a7_rollback_and_tests_sharded_keep_dispatch(name):
    assert "workflow_dispatch" in _triggers(WORKFLOWS / name)


# --- B. scripts/pr-gate.sh ---------------------------------------------------------------------

# B4 check commands, stubbed. Each stub appends "<id> <argv/RANGE>" to $GATE_LOG and exits with
# the code named in $GATE_FAIL_<ID> (default 0).
_PY_STUBS = {
    "scripts/ci_alembic_heads.py": "alembic-heads",
    "scripts/pii_guard.py": "pii",
    "scripts/ci_ai_coverage.py": "ai-coverage",
    "scripts/sync_user_guides_outline.py": "outline-guides",
}
_PY_STUB = """import os, sys
cid = {cid!r}
with open(os.environ["GATE_LOG"], "a") as fh:
    fh.write(cid + " " + " ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("GATE_FAIL_" + cid.upper().replace("-", "_"), "0")))
"""
_SH_STUB = """#!/usr/bin/env bash
echo "gitleaks RANGE=${RANGE:-}" >> "$GATE_LOG"
exit "${GATE_FAIL_GITLEAKS:-0}"
"""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
         *args],
        cwd=repo, capture_output=True, text=True, timeout=60,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(repo.parent),
             "GIT_CONFIG_NOSYSTEM": "1"},
    )
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout.strip()


def _commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, body in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, *, merged: bool = True, head_files: dict[str, str] | None = None) -> dict:
    """A repo whose HEAD is one commit past base. origin/main = base when `merged`, else a commit
    on a side branch that HEAD does not contain."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    assert PR_GATE.is_file(), "scripts/pr-gate.sh is missing"
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "lane")
    base_files = {"README.md": "x\n", "scripts/pr-gate.sh": PR_GATE.read_text(), "scripts/ci_gitleaks.sh": _SH_STUB}
    base_files.update({rel: _PY_STUB.format(cid=cid) for rel, cid in _PY_STUBS.items()})
    base = _commit(repo, base_files, "base")
    main = base
    if not merged:
        _git(repo, "checkout", "-q", "-b", "side")
        main = _commit(repo, {"side.md": "main moved\n"}, "main moved")
        _git(repo, "checkout", "-q", "lane")
    head = _commit(repo, head_files or {"documentation/x.md": "doc\n"}, "lane change")
    _git(repo, "update-ref", "refs/remotes/origin/main", main)
    return {"repo": repo, "head": head, "main": main, "log": tmp_path / "gate.log"}


def _run(ctx: dict, *args: str, changed: list[str] | None = None, extra_env: dict | None = None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(ctx["repo"].parent),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GATE_LOG": str(ctx["log"]),
    }
    if changed is not None:
        env["CREW_CHANGED_FILES"] = "\n".join(changed)
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "scripts/pr-gate.sh", *args], cwd=ctx["repo"], env=env, capture_output=True, text=True,
        timeout=120,
    )


def _last_line(result) -> str:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, (result.stdout, result.stderr)
    return lines[-1].strip()


def _plan(result) -> dict[str, str]:
    out = {}
    for line in result.stdout.splitlines():
        m = re.match(r"^plan\.(\w+)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _ran(ctx: dict) -> list[str]:
    log = ctx["log"]
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("args", [(), ("--plan",)], ids=["run", "plan"])
def test_b2_main_not_merged_fails_and_runs_nothing(tmp_path, args):
    ctx = _repo(tmp_path, merged=False)
    result = _run(ctx, *args, changed=["documentation/x.md"])
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert _last_line(result) == f"pr-gate: {ctx['head']} FAIL main={ctx['main']} reason=main-not-merged"
    assert _ran(ctx) == [], "no check may run when main is not merged"


def test_b2_merged_main_passes_the_ancestor_check(tmp_path):
    ctx = _repo(tmp_path, merged=True)
    result = _run(ctx, "--plan", changed=["documentation/x.md"])
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "main-not-merged" not in result.stdout


@pytest.mark.parametrize(
    "changed, expected",
    [
        (["documentation/plans/ci/PLAN-x.md"], ALWAYS),
        (["sorento_crm_backend/app/services/inventory_service.py"], ALWAYS + BACKEND),
        (["sorento_crm_frontend/lib/api-client.ts"], ALWAYS + FRONTEND),
        (["sorento_crm_mcp/sorento_crm_mcp/server.py"], ALWAYS + MCP),
        (["sorento_crm_frontend/a.ts", "sorento_crm_mcp/b.py", "sorento_crm_backend/c.py"], EVERY),
        ([".github/workflows/deploy.yml"], EVERY),
    ],
    ids=["docs-only", "backend", "frontend", "mcp", "all-three", "deploy-yml"],
)
def test_b5_plan_lists_the_checks_in_b4_order(tmp_path, changed, expected):
    ctx = _repo(tmp_path)
    result = _run(ctx, "--plan", changed=changed)
    assert result.returncode == 0, (result.stdout, result.stderr)
    plan = _plan(result)
    assert plan.get("checks") == " ".join(expected), plan
    assert plan.get("main") == ctx["main"], plan
    assert _ran(ctx) == [], "--plan runs nothing"


def test_b5_docs_only_plan_line_is_exact(tmp_path):
    ctx = _repo(tmp_path)
    result = _run(ctx, "--plan", changed=["documentation/x.md"])
    assert "plan.checks=alembic-heads pii ai-coverage outline-guides gitleaks" in result.stdout.splitlines()
    assert f"plan.main={ctx['main']}" in result.stdout.splitlines()


def test_b3_without_crew_changed_files_the_git_diff_vs_base_decides(tmp_path):
    ctx = _repo(tmp_path, head_files={"sorento_crm_backend/app/x.py": "x = 1\n"})
    result = _run(ctx, "--plan")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _plan(result).get("checks") == " ".join(ALWAYS + BACKEND), result.stdout


def test_b1_base_flag_overrides_origin_main(tmp_path):
    ctx = _repo(tmp_path, merged=False)
    base = _git(ctx["repo"], "rev-parse", "HEAD~1")
    _git(ctx["repo"], "update-ref", "refs/heads/mybase", base)
    result = _run(ctx, "--plan", "--base", "refs/heads/mybase", changed=["documentation/x.md"])
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _plan(result).get("main") == base, result.stdout


def test_b6_a_green_docs_only_run_prints_the_pass_line(tmp_path):
    ctx = _repo(tmp_path)
    result = _run(ctx)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _last_line(result) == (
        f"pr-gate: {ctx['head']} PASS main={ctx['main']} checks={','.join(ALWAYS)}"
    )
    ran = _ran(ctx)
    assert [line.split()[0] for line in ran] == ALWAYS, ran
    # B4 arguments: ai-coverage gets --base <base sha>, outline-guides `check`, gitleaks the range.
    assert f"ai-coverage --base {ctx['main']}" in ran, ran
    assert "outline-guides check" in ran, ran
    assert f"gitleaks RANGE={ctx['main']}..{ctx['head']}" in ran, ran


def test_b6_a_failing_check_does_not_stop_the_rest(tmp_path):
    ctx = _repo(tmp_path)
    result = _run(ctx, extra_env={"GATE_FAIL_PII": "1", "GATE_FAIL_GITLEAKS": "1"})
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert [line.split()[0] for line in _ran(ctx)] == ALWAYS, "every selected check runs after a failure"
    assert _last_line(result) == (
        f"pr-gate: {ctx['head']} FAIL main={ctx['main']} checks={','.join(ALWAYS)} failed=pii,gitleaks"
    )
