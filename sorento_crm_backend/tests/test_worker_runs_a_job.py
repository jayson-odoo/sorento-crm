"""One real job through `worker.ForkSafeWorker`, forked work-horse and all.

rq 3.0 added an `execution` argument to `Worker.perform_job`. The override dropped it,
so the work-horse raised TypeError and exited 1 before ANY job ran ("Work-horse
terminated unexpectedly; waitpid returned 256"), with no traceback in the worker log.
Every queue died at once. This runs a trivial job through the installed rq's real code
path so the next rq major that changes the signature fails here instead.

Runs in a fresh subprocess (like test_worker_entrypoint.py) because the work-horse is a
fork of the calling process, and a pytest process carries far more state than a worker.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import redis

from app.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_fork_safe_worker_finishes_a_job():
    try:
        redis.from_url(settings.redis_url).ping()
    except redis.exceptions.ConnectionError:
        pytest.skip("Redis not reachable at REDIS_URL")

    # A private queue, so a dev worker sharing this Redis never steals the job.
    queue_name = f"test_worker_runs_a_job_{uuid.uuid4().hex}"
    code = (
        "import worker\n"
        "from rq import Queue\n"
        "from app.services.queue_service import redis_conn\n"
        f"q = Queue({queue_name!r}, connection=redis_conn)\n"
        "job = q.enqueue('builtins.len', [1, 2])\n"
        "worker.ForkSafeWorker([q], connection=redis_conn).work(burst=True)\n"
        "job.refresh()\n"
        "print(job.is_finished, job.return_value())\n"
        "q.delete(delete_jobs=True)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "REDIS_URL": settings.redis_url},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "True 2", out.stderr
