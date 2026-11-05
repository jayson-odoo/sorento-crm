"""CI-PARALLEL-ACTIONS (owner, 5 Nov 2026): release delta and nightly sweep sharded on GitHub
Actions; the reorder-planning tests run in the nightly full sweep only.

Plan: documentation/plans/ci/PLAN-ci-parallel-actions-05nov.md. No database.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
WORKFLOW = REPO / ".github" / "workflows" / "tests-sharded.yml"
sys.path.insert(0, str(BACKEND / "scripts"))
import release_delta_select as rds  # noqa: E402
import sharded_tests_plan as stp  # noqa: E402
import sharded_tests_summary as sts  # noqa: E402

B = "sorento_crm_backend/"


def _entries(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]


# --- the nightly-only list ------------------------------------------------------------------

def test_nightly_only_lists_existing_reorder_planning_test_files():
    entries = _entries(BACKEND / "tests" / "nightly_only.txt")
    assert len(entries) == len(set(entries))
    for e in entries:
        assert (BACKEND / e).is_file(), e
        assert re.match(r"^tests/([\w.-]+/)*test_[\w.-]*\.py$", e), e
        # Migration tests run on every alembic/ or app/models/ change; never nightly-only.
        assert not Path(e).name.startswith("test_migration_"), e
    for must in ("tests/scm/test_m3_engine.py", "tests/scm/test_reorder_replan.py",
                 "tests/test_reorder_plan_demand_scope.py"):
        assert must in entries, must
    # Order promising and the fulfilment board are in use: they stay in every run.
    assert not [e for e in entries if "front_planning" in e or "fulfilment" in e]


def _tree(tmp_path: Path) -> Path:
    files = {
        B + "app/__init__.py": "",
        B + "app/models/__init__.py": "",
        B + "app/models/user.py": "class User: ...\n",
        B + "app/services/__init__.py": "",
        B + "app/services/reorder.py": "from app.models.user import User\n",
        B + "tests/__init__.py": "",
        B + "tests/ci_excluded.txt": "tests/test_excluded.py\n",
        B + "tests/nightly_only.txt": "# reorder\ntests/scm/test_reorder.py\n",
        B + "tests/test_user.py": "from app.models.user import User\n",
        B + "tests/test_excluded.py": "from app.models.user import User\n",
        B + "tests/test_lessons_learnt_regressions.py": "import re\n",
        B + "tests/test_migration_001_x.py": "import json\n",
        B + "tests/scm/__init__.py": "",
        B + "tests/scm/test_reorder.py": "from app.services.reorder import User\n",
        B + "tests/scm/test_scm_user.py": "from app.models.user import User\n",
        B + ".test_durations": json.dumps({
            "tests/test_user.py::a": 10.0, "tests/test_lessons_learnt_regressions.py::a": 10.0,
            "tests/scm/test_reorder.py::a": 50.0, "tests/scm/test_scm_user.py::a": 50.0,
        }),
        "sorento_crm_frontend/lib/a.ts": "export const a = 1\n",
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path / "sorento_crm_backend"


def test_the_delta_selector_never_picks_a_nightly_only_test(tmp_path):
    root = _tree(tmp_path)
    res = rds.select([B + "app/services/reorder.py", B + "tests/scm/test_reorder.py"], root)
    assert "tests/scm/test_reorder.py" not in res.tests
    # Not even on a full-suite fallback.
    res = rds.select([B + "tests/conftest.py"], _tree(tmp_path / "b"))
    assert res.backend == "full"
    assert "tests/scm/test_reorder.py" not in res.tests and "tests/scm/test_scm_user.py" in res.tests


# --- the shard planner ----------------------------------------------------------------------

def test_a_full_plan_runs_every_test_with_the_nightly_only_ones(tmp_path):
    p = stp.plan("full", _tree(tmp_path), main_shards=5, scm_shards=3, vitest_shards=4)
    assert "tests/scm/test_reorder.py" in p["scm"]
    assert "tests/test_excluded.py" not in p["main"]
    assert p["migrations"] == ["tests/test_migration_001_x.py"]
    assert (p["main_n"], p["scm_n"], p["vitest_n"], p["vitest"]) == (5, 3, 4, "full")
    assert p["serial"]


def test_a_delta_plan_sizes_each_pool_by_its_share_of_the_full_durations(tmp_path):
    p = stp.plan("delta", _tree(tmp_path), changed=[B + "app/models/user.py"], main_shards=10, scm_shards=4)
    assert "tests/scm/test_reorder.py" not in p["scm"]
    assert p["scm"] == ["tests/scm/test_scm_user.py"]
    # 50 of the scm pool's 100 recorded seconds on a 4-runner full pool: 2 runners.
    assert p["scm_n"] == 2
    assert p["vitest"] == "none" and p["vitest_n"] == 0
    assert p["migrations"] == ["tests/test_migration_001_x.py"]


def test_a_docs_only_delta_gets_no_runner(tmp_path):
    p = stp.plan("delta", _tree(tmp_path), changed=["documentation/x.md"])
    assert (p["main_n"], p["scm_n"], p["vitest_n"], p["serial"]) == (0, 0, 0, False)


def test_a_frontend_delta_gets_one_related_vitest_runner(tmp_path):
    p = stp.plan("delta", _tree(tmp_path), changed=["sorento_crm_frontend/lib/a.ts"])
    assert p["vitest"] == "related" and p["vitest_n"] == 1 and p["vitest_related"] == ["lib/a.ts"]


def test_the_planner_cli_writes_the_pool_files_and_outputs(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    assert stp.main(["--mode", "full", "--backend", str(root), "--out", str(tmp_path / "plan"),
                     "--main-shards", "2"]) == 0
    out = dict(l.split("=", 1) for l in gh_out.read_text().splitlines())
    assert json.loads(out["main_shards"]) == [1, 2] and out["serial"] == "true"
    assert "tests/test_user.py" in (tmp_path / "plan" / "main.txt").read_text().split()


# --- the summary ----------------------------------------------------------------------------

def _junit(path: Path, cases: list[tuple[str, str | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f'<testcase classname="c" name="{n}">{"<" + k + "/>" if k else ""}</testcase>' for n, k in cases)
    path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")


def _job(name, conclusion="success", minutes=10.5):
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "started_at": "2026-11-05T10:00:00Z", "completed_at": f"2026-11-05T10:{int(minutes):02d}:30Z"}


def _summary(tmp_path, jobs):
    return sts.summarise(tmp_path / "junit", jobs, "2026-11-05T09:59:00Z",
                         datetime(2026, 11, 5, 10, 20, tzinfo=timezone.utc),
                         head="abc", mode="delta", base="def", reason="r", run_url="u")


def test_a_green_run_reads_as_a_pass_with_minutes(tmp_path):
    _junit(tmp_path / "junit/junit-backend-main-1/main-1.xml", [("a", None), ("b", "skipped")])
    _junit(tmp_path / "junit/junit-vitest-1/vitest-1.xml", [("v", None)])
    text = _summary(tmp_path, [_job("backend main 1/1"), _job("vitest 1/1"), _job("Select and shard", minutes=1)])
    first = text.splitlines()[0]
    assert first == "crew-tests: abc delta since nightly def backend 1 passed/0 failed, vitest 1/0"
    assert "wall clock: 21 min" in text and "billable runner minutes: 24" in text


def test_a_failed_test_or_a_lost_shard_reads_as_failed(tmp_path):
    _junit(tmp_path / "junit/junit-backend-main-1/main-1.xml", [("a", "failure")])
    text = _summary(tmp_path, [_job("backend main 1/2", "failure"), _job("backend main 2/2", "cancelled")])
    first = text.splitlines()[0]
    assert first.startswith("crew-tests: abc delta since nightly def backend 0 passed/1 failed")
    assert "FAILED (backend main 1/2: 1 failed; backend main 2/2: job cancelled)" in first
    assert "c::a" in text


def test_a_green_job_without_junit_is_not_a_pass(tmp_path):
    assert "FAILED (backend scm 1/1: no junit)" in _summary(tmp_path, [_job("backend scm 1/1")])


# --- the workflow ---------------------------------------------------------------------------

pytestmark_wf = pytest.mark.skipif(not WORKFLOW.is_file(), reason="workflow not present")


@pytestmark_wf
def test_the_workflow_dispatches_full_or_delta_and_the_nightly_is_switched_by_a_variable():
    wf = yaml.safe_load(WORKFLOW.read_text())
    on = wf[True]
    inputs = on["workflow_dispatch"]["inputs"]
    assert set(inputs) >= {"mode", "base", "head", "comment_on"}
    assert inputs["mode"]["options"] == ["delta", "full"]
    assert on["schedule"][0]["cron"]
    assert "vars.TESTS_SHARDED_NIGHTLY == 'on'" in wf["jobs"]["select"]["if"]
    assert "'full'" in wf["env"]["MODE"], "a scheduled run is the full sweep"


@pytestmark_wf
def test_the_backend_shards_run_on_postgres_and_redis_with_deploys_flags():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    backend = jobs["backend"]
    assert backend["services"]["postgres"]["image"] == "pgvector/pgvector:pg16"
    assert backend["services"]["redis"]["image"].startswith("redis:")
    assert backend["strategy"]["fail-fast"] is False
    run = "\n".join(str(s.get("run", "")) for s in backend["steps"])
    for flag in ("--max-worker-restart 0", "tests._xdist_crash_guard", "--splits", "-m serial_ddl",
                 "scripts.bootstrap_env", "max_locks_per_transaction"):
        assert flag in run, flag
    vrun = "\n".join(str(s.get("run", "")) for s in jobs["vitest"]["steps"])
    assert '--shard="$SHARD/$OF"' in vrun and "source-guard-tests.sh" in vrun


@pytestmark_wf
def test_the_summary_posts_on_the_nightly_issue_or_the_dispatch_target_and_fails_red():
    summary = yaml.safe_load(WORKFLOW.read_text())["jobs"]["summary"]
    assert summary["if"].startswith("always()")
    text = json.dumps(summary)
    assert "'2176'" in text and "inputs.comment_on" in text
    assert "FAILED" in summary["steps"][-1]["run"]


@pytestmark_wf
def test_the_workflow_never_deploys():
    text = WORKFLOW.read_text()
    for word in ("blue_green_deploy", "environment: production", "docker push", "ssh "):
        assert word not in text, word


# --- crew-tests.sh --------------------------------------------------------------------------

@pytest.mark.skipif(not (REPO / "scripts" / "crew-tests.sh").is_file(), reason="repo scripts not present")
def test_crew_tests_drops_the_nightly_only_tests():
    entry = _entries(BACKEND / "tests" / "nightly_only.txt")[0]
    env = dict(os.environ, CREW_CHANGED_FILES=f"sorento_crm_backend/{entry}")
    res = subprocess.run(["bash", "scripts/crew-tests.sh", "--plan"], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    plan = dict(l.split("=", 1) for l in res.stdout.splitlines() if l.startswith("plan."))
    assert entry not in plan["plan.backend"].split()
    assert "nightly_only.txt" in res.stderr


def test_the_refreshed_durations_merge_every_shards_fresh_timings_over_the_base(tmp_path):
    (tmp_path / "junit-backend-main-1").mkdir()
    (tmp_path / "junit-backend-main-1" / "durations-main-1.json").write_text('{"t::a": 2.0, "t::new": 1.0}')
    (tmp_path / "junit-backend-scm-1").mkdir()
    (tmp_path / "junit-backend-scm-1" / "durations-scm-1.json").write_text('{"s::b": 3.0}')
    merged, fresh = sts.merge_durations({"t::a": 9.0, "s::b": 9.0, "old::c": 4.0}, tmp_path)
    assert merged == {"old::c": 4.0, "s::b": 3.0, "t::a": 2.0, "t::new": 1.0} and fresh == 3
