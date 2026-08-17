"""Run what an SCM upload route ENQUEUES, on the test's own session.

The five SCM upload channels stopped writing inside the request: `apply` now creates an
import job, retains the file and hands the work to the `imports` queue. That is the point of
the slice, and it puts the write on the far side of a queue no test may start (an RQ worker
is shared across worktrees, so a sibling worker would steal the job).

So the wire and the work are proved separately, and this is the seam between them:

* `stub_queue(monkeypatch, ...)` captures what the route would enqueue and what it would
  retain, without doing either. Route tests assert on the capture.
* `run_enqueued(captured, db, monkeypatch)` then calls that task function directly, with
  `SessionLocal` pointing at the test's savepoint-backed session, so the write itself is
  exercised end to end and rolled back with everything else.

Calling the task rather than mocking it is deliberate: the task is where the company scope is
re-established, where per-row outcomes are recorded and where the job is terminated, and every
one of those is a thing that can silently stop working.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional
from unittest.mock import MagicMock

#: Route modules that enqueue. Patched where they BOUND `enqueue_job`, not where it lives.
_ROUTE_MODULES = (
    "app.api.v1.scm.outstanding_import",
    "app.api.v1.scm.purchase_history",
)


def stub_queue(monkeypatch) -> dict:
    """Capture the enqueue and the source-file retention; perform neither."""
    captured: dict[str, Any] = {"enqueued": [], "retained": []}

    def _enqueue(func, *args, **kwargs):
        captured["enqueued"].append({"func": func, "name": func.__name__,
                                     "args": args, "kwargs": kwargs})
        return MagicMock(id=str(uuid.uuid4()))

    def _store(job, data, name, ctype):
        captured["retained"].append({"job_id": str(job.id), "bytes": data, "name": name,
                                     "content_type": ctype})
        return True

    for module in _ROUTE_MODULES:
        monkeypatch.setattr(f"{module}.enqueue_job", _enqueue)
    # Patched at its source: the routes import it inside the function body, so there is no
    # module-level name to replace.
    monkeypatch.setattr("app.services.import_source_store.store_import_source_file", _store)
    return captured


def run_enqueued(captured: dict, db, monkeypatch, index: int = -1) -> None:
    """Run the captured task the way the worker would: on a session of its OWN.

    Its own session, joined to the test's connection with `join_transaction_mode=
    "create_savepoint"`, rather than the fixture's session handed straight over. The task
    rolls back on the failure paths, and a shared session's `rollback()` unwinds the whole
    outer transaction - taking the job row the route had already committed with it, so the
    test then reads no job at all and the failure looks like "the task never ran". A joined
    session's rollback stops at its own savepoint, which is exactly the isolation a real
    worker session has.
    """
    from sqlalchemy.orm import Session

    job = captured["enqueued"][index]
    connection = db.connection()

    def _session_factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    monkeypatch.setattr("app.tasks.import_tasks.SessionLocal", _session_factory)
    try:
        job["func"](*job["args"])
    finally:
        # The task committed on another session over the same connection; the fixture's
        # session is still holding the pre-task identity map.
        db.expire_all()


def queued_job_id(captured: dict, index: int = -1) -> Optional[str]:
    """The DB job id the route passed to the task: its first positional argument."""
    args = captured["enqueued"][index]["args"]
    return str(args[0]) if args else None
