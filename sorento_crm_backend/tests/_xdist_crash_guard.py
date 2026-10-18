"""A crashed xdist worker fails the session (CI-MAC-CAP, 18 Oct 2026).

CI runs xdist with `--max-worker-restart 0` (deploy.yml) so a worker the OOM
killer takes ends the run instead of being respawned into the same memory
pressure. Killed mid-test, its test is reported failed. Killed before it reports
its collection, xdist 3.8 ends the session "no tests ran" with exit 0, and the
PR gate's `run()` also passes exit 5. A worker that went down with an error is
never a green run. Loaded by tests/conftest.py; pinned by
tests/test_xdist_crash_guard.py.
"""
import pytest

_CRASHED: list[str] = []


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    if error:
        _CRASHED.append(node.gateway.id)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if _CRASHED and session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
