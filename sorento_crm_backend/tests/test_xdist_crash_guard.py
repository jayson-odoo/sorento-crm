"""A crashed xdist worker fails the session (tests/_xdist_crash_guard.py).

CI runs xdist with `--max-worker-restart 0` (deploy.yml, CI-MAC-CAP), so a worker
the OOM killer takes ends the run instead of being respawned. Killed mid-test,
its test is reported failed. Killed before it reports its collection, xdist 3.8
ends the session "no tests ran" with exit 0, and the PR gate's `run()` also
passes exit 5. Each case runs a real `pytest -n 2` session in a scratch
directory, one worker SIGKILLed the way the OOM killer does it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("xdist")

BACKEND = Path(__file__).resolve().parents[1]

CONFTEST = """\
import os
import signal


def pytest_collection_modifyitems(config, items):
    if os.environ.get("KILL_AT") == "collection" and os.environ.get("PYTEST_XDIST_WORKER") == "gw1":
        os.kill(os.getpid(), signal.SIGKILL)
"""

TEST_X = """\
import os
import signal


def test_a():
    pass


def test_b():
    if os.environ.get("KILL_AT") == "test":
        os.kill(os.getpid(), signal.SIGKILL)
"""

TEST_Y = "def test_c():\n    pass\n"


def _session(tmp_path: Path, kill_at: str) -> subprocess.CompletedProcess:
    (tmp_path / "conftest.py").write_text(CONFTEST)
    (tmp_path / "test_x.py").write_text(TEST_X)
    (tmp_path / "test_y.py").write_text(TEST_Y)
    # The outer run's xdist variables would make the inner controller look like a worker.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update(PYTHONPATH=str(BACKEND), KILL_AT=kill_at)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tests._xdist_crash_guard",
         "-n", "2", "--dist", "loadfile", "--max-worker-restart", "0"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )


def test_a_clean_session_still_passes(tmp_path):
    result = _session(tmp_path, kill_at="")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout, result.stdout


def test_a_worker_killed_during_collection_fails_the_session(tmp_path):
    result = _session(tmp_path, kill_at="collection")
    assert "node down" in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


def test_a_worker_killed_mid_test_fails_the_session(tmp_path):
    result = _session(tmp_path, kill_at="test")
    assert "crashed while running 'test_x.py::test_b'" in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


def test_the_suite_conftest_loads_the_guard(request):
    from tests import _xdist_crash_guard as guard

    impls = [impl.function for impl in request.config.hook.pytest_sessionfinish.get_hookimpls()]
    assert guard.pytest_sessionfinish in impls
