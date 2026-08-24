"""Worker entrypoint import smoke tests.

The worker container (`python worker.py`) imports modules in a different order
than the API (`app.main`): queue_service first, then app.scheduler.task_scheduler
lazily inside `_maybe_start_scheduler`. Circular imports can be invisible on the
app.main path yet fatal on the worker path - in 2026-06 a user_service <->
integration_service cycle killed APScheduler at startup while the RQ loop kept
running, so the container looked healthy and email_outbox rows sat pending forever.

These tests MUST run the import in a fresh subprocess interpreter: by the time
pytest collects this file, dozens of app modules are already imported in an
order that can mask the cycle.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Dummy env so config/redis client construction succeeds without live services.
# Neither redis-py nor SQLAlchemy connects eagerly at import time.
_DUMMY_ENV = {
    "DATABASE_URL": "postgresql://x:x@localhost:5499/x",
    "DIRECT_URL": "postgresql://x:x@localhost:5499/x",
    "JWT_SECRET": "test-dummy-secret",
    "JWT_ALGORITHM": "HS256",
    "REDIS_URL": "redis://localhost:6399/0",
}


def _run_fresh_import(code: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **_DUMMY_ENV}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def test_worker_entrypoint_import_chain():
    """Replicates worker.py's exact import sequence in a clean interpreter."""
    proc = _run_fresh_import(
        "import worker\n"
        "from app.scheduler.task_scheduler import start_scheduler\n"
        "print('ok')\n"
    )
    assert proc.returncode == 0, (
        "worker entrypoint import chain failed - APScheduler would silently die "
        f"in the worker container:\n{proc.stderr}"
    )


def test_task_scheduler_imports_standalone():
    """task_scheduler must be importable first, with nothing else pre-loaded."""
    proc = _run_fresh_import(
        "from app.scheduler.task_scheduler import start_scheduler\n"
        "print('ok')\n"
    )
    assert proc.returncode == 0, (
        f"app.scheduler.task_scheduler failed standalone import:\n{proc.stderr}"
    )
