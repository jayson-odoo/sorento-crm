"""Reporting document reads that were killed, and starting them again (S20).

The bug, reproduced on real data on 2026-08-08: a customer PO sat on screen as "Waiting to
be read", 10 pages, 0 lines, with a progress bar, indefinitely. The RQ work-horse had been
killed (signal 15) and RQ had correctly moved the job to its FailedJobRegistry, but
``project_po_versions.extraction_state`` still said ``running``, because
``app.tasks.project_document_tasks`` writes its failure inside an ``except`` block and **an
``except`` block never runs when the process is killed**. So the row is stranded for ever:
no error, no retry, and a screen claiming work is in progress when nothing is running.

Same family as the export-download stranding fixed in ``export_tasks._record_failure``
(36afeaa59), different mechanism. There the handler RAN and could not write, because the
transaction was aborted; the fix was to roll back first. Here the handler never runs at all,
so no amount of care inside it can help. Something outside the dying process has to notice.

Why this and not an RQ ``on_failure`` callback
----------------------------------------------
That was the obvious mechanism, and in rq 2.6.1 it does not fire for this case. Read the
installed source: ``Job.execute_failure_callback`` is called from ``Worker.perform_job``,
which runs INSIDE the work-horse, and from ``StartedJobRegistry.cleanup``.
``Worker.monitor_work_horse`` - the path that actually handles a horse killed by a signal -
calls ``handle_work_horse_killed`` then ``handle_job_failure``, and ``handle_job_failure``
never touches the callback. A failure callback would have had exactly the same blind spot
as the ``except`` block it was replacing.

So: reconcile against what RQ knows, keyed on the job id the row records. Direct sibling of
``_reconcile_orphan_import_jobs`` in ``app.scheduler.task_scheduler``, which does the same
thing for ``import_jobs`` and for the same reason.

The rule that keeps this safe
-----------------------------
**Never decide from the clock while there is a job to ask about.** Extraction is one vision
call per page, sequentially: ten pages measured at 166 seconds, so a forty page PO
legitimately runs for over ten minutes. A reconciler that calls a live job dead is a worse
bug than the one it fixes. RQ's answer wins, always; time is consulted only when there is
no job id at all, and then only well past the point RQ would itself have killed the horse.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from app.models.project_so import DeliveryScheduleVersion, ProjectPOVersion
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

# States a read can still be sitting in. Anything else has a verdict already, and a verdict
# somebody wrote is never overwritten by a generic one: "Pages 4, 5 could not be read" is
# more useful than anything this module could say.
PENDING_STATES = ("queued", "running")

# A row whose job id we hold, but which Redis no longer knows about, is dead: a live job
# keeps its own hash alive. The grace only exists so the moment between "row committed" and
# "job enqueued" - the upload commits first on purpose, so a worker cannot start on a row
# that does not exist yet - is never mistaken for a death.
GRACE_WITHOUT_A_JOB = timedelta(minutes=3)

# The only place time gets a vote: a row carrying no job id at all, which means either an
# enqueue that never landed or a document uploaded before this fix. The floor is past the
# RQ job timeout (1800s), after which RQ kills the horse itself, so a read still legitimately
# in flight can never reach it.
GIVE_UP_WITHOUT_A_JOB_ID = timedelta(minutes=40)

# Every reason this module writes opens with this, and no other reason in the extraction
# path does. It is what lets a person tell "the reader was stopped" from "page 4 came back
# blank": the second wants a better scan, the first wants the same document read again, and
# telling somebody to re-scan a PDF that scans fine is advice that cannot help them.
INTERRUPTED_PREFIX = "The read was interrupted"

_SIGNAL = re.compile(r"signal (\d+)")


@dataclass(frozen=True)
class JobView:
    """What RQ says about one job. Deliberately tiny: the status and the words."""

    status: Optional[str]
    exc_info: Optional[str]


# RQ statuses that mean the job is alive or about to be. Nothing in this set is ever
# touched, whatever the clock says. `created` is the moment between instantiating a job and
# enqueueing it: listed explicitly rather than left to the fall-through, so that branch
# stays unreachable for every status RQ can actually report and a NEW one is a test failure
# instead of a silently stranded row.
_ALIVE = {"created", "queued", "started", "deferred", "scheduled"}
# Terminal-but-unrecorded: RQ finished with it, the row never heard.
_DEAD = {"failed", "stopped", "canceled", "cancelled"}


def look_up_job(job_id: str) -> Optional[JobView]:
    """Ask RQ about a job. ``None`` means Redis has never heard of it.

    A seam as much as a helper: the tests replace this so the decision table can be
    exercised without a Redis, and a Redis that is merely unreachable must not be read as
    "the job is gone" - that would fail every in-flight read during a blip, so the
    connection error is re-raised as "alive" by returning a started view.
    """
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    from app.services.queue_service import redis_conn

    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except NoSuchJobError:
        return None
    except Exception:  # noqa: BLE001 - a Redis we cannot reach says nothing about the job
        logger.warning("could not ask RQ about job %s; treating the read as alive", job_id)
        return JobView(status="started", exc_info=None)

    try:
        status = job.get_status()
    except Exception:  # noqa: BLE001
        status = None

    # `.value` FIRST, and never bare `str()`. RQ's JobStatus is a `(str, Enum)`, and for a
    # mixin enum `__str__` is Enum's, so `str(JobStatus.FAILED)` is "JobStatus.FAILED", not
    # "failed". Lowercased that is "jobstatus.failed", which matches neither _ALIVE nor
    # _DEAD, so every killed read took the "unrecognised status" branch and was left alone -
    # this module's whole purpose, silently defeated. Measured on 2026-08-09 by killing a
    # real work-horse: RQ logged "moving job to FailedJobRegistry (signal 15)" and the row
    # still said `running` a minute later. The unit tests could not catch it because they
    # replace `look_up_job` itself, so no real JobStatus ever reached this line.
    status = getattr(status, "value", status)
    return JobView(status=str(status) if status else None, exc_info=job.exc_info)


# --------------------------------------------------------------- reconciliation


def reconcile_one(db, version) -> bool:
    """Give one version a verdict if its read died. Returns whether anything changed.

    Called from the read path - the screens that poll a version while it is being read are
    exactly where somebody is waiting to be told - so it must be cheap and it must be
    silent when there is nothing wrong.
    """
    if version is None or version.extraction_state not in PENDING_STATES:
        return False

    reason = _verdict(version)
    if reason is None:
        return False

    version.extraction_state = "failed"
    version.extraction_error = reason[:500]
    try:
        db.commit()
    except Exception:  # noqa: BLE001 - a verdict we cannot write is not worth a 500
        logger.exception("could not record the interrupted read on version %s", version.id)
        db.rollback()
        return False
    logger.info("version %s marked failed by reconciliation: %s", version.id, reason)
    return True


def reconcile(db, versions: Iterable[Any]) -> int:
    """The same for a list. Rows already holding a verdict cost nothing."""
    return sum(1 for version in versions if reconcile_one(db, version))


def _verdict(version) -> Optional[str]:
    """The sentence to write, or ``None`` to leave this read alone.

    Read top to bottom: every branch that leaves a read alone comes before every branch
    that gives up on one.
    """
    job_id = (version.extraction_job_id or "").strip()
    age = _age(version)

    if not job_id:
        # Nothing to ask about. Time is the only evidence, and it is weak evidence, so the
        # bar is deliberately high.
        if age is None or age < GIVE_UP_WITHOUT_A_JOB_ID:
            return None
        minutes = int(age.total_seconds() // 60)
        return (
            f"{INTERRUPTED_PREFIX}: nothing has been recorded for {minutes} minutes, past "
            "the point a read of this document should have ended. The document is still "
            "stored. Read it again."
        )

    view = look_up_job(job_id)

    if view is None:
        if age is not None and age < GRACE_WITHOUT_A_JOB:
            return None
        return (
            f"{INTERRUPTED_PREFIX}: its job is no longer on the queue and nothing was "
            "recorded from this document. It is still stored. Read it again."
        )

    status = (view.status or "").lower()
    if status in _ALIVE:
        return None

    if status in _DEAD:
        return _death_reason(view.exc_info)

    if status == "finished":
        return (
            f"{INTERRUPTED_PREFIX}: the reader ended without recording anything for this "
            "document. It is still stored. Read it again."
        )

    # An unrecognised status is not evidence of death. New RQ versions add states, and
    # guessing wrong here is the failure mode this whole module exists to avoid.
    return None


def _death_reason(exc_info: Optional[str]) -> str:
    """What RQ recorded, said in a sentence somebody can act on.

    A killed work-horse gets RQ's own words, which carry the signal: "Work-horse terminated
    unexpectedly; waitpid returned 15 (signal 15)". The signal is worth surfacing because
    15 (a deploy, a restart, a stop) and 9 (an out-of-memory kill) call for different
    answers from whoever is looking after the box.
    """
    text = (exc_info or "").strip()
    signal = _SIGNAL.search(text)

    if "work-horse terminated" in text.lower() or signal:
        detail = f" (signal {signal.group(1)})" if signal else ""
        return (
            f"{INTERRUPTED_PREFIX}: the background worker was terminated{detail}, so "
            "nothing was recorded from this document. It is still stored. Read it again."
        )

    if text:
        # A real traceback. Its LAST line is the exception; the rest is frames nobody
        # reading a PO needs.
        last = [line.strip() for line in text.splitlines() if line.strip()][-1]
        return (
            f"{INTERRUPTED_PREFIX} and the queue reported: {last[:200]} "
            "The document is still stored. Read it again."
        )

    return (
        f"{INTERRUPTED_PREFIX}: the queue reported the read as failed without a reason, and "
        "nothing was recorded from this document. It is still stored. Read it again."
    )


def _age(version) -> Optional[timedelta]:
    """How long this read has had. From when it started, or failing that from when the
    document was uploaded - a row that never started still has a created_at."""
    reference = version.extraction_started_at or version.created_at
    if reference is None:
        return None
    return datetime.utcnow() - reference


# ------------------------------------------------------------- starting a read


def start_job(db, version) -> Optional[str]:
    """Hand a version to the reader and record WHICH job is reading it.

    The one place a job id is written, so the reconciler can trust what it finds. Called
    after the commit that creates or resets the row, because a worker that starts on an
    uncommitted row reads nothing and marks a perfectly good document as failed.

    A failure to enqueue is reported on the row rather than raised: the document is stored
    either way, and the alternative is a version that says "queued" for ever, which is the
    exact stranding this module exists to remove.
    """
    from app.tasks import project_document_tasks

    enqueue = (
        project_document_tasks.enqueue_po_extraction
        if isinstance(version, ProjectPOVersion)
        else project_document_tasks.enqueue_schedule_extraction
    )

    try:
        job = enqueue(str(version.id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not queue a read for version %s", version.id)
        version.extraction_state = "failed"
        version.extraction_error = (
            "The document is stored but the reader could not be started "
            f"({str(exc)[:200]}). Read it again, or fill the lines in by hand."
        )[:500]
        _commit_quietly(db, version)
        return None

    job_id = getattr(job, "id", None)
    version.extraction_job_id = str(job_id)[:64] if job_id else None
    # Post-commit side effect: best effort. Losing the job id costs the reconciler its
    # precise answer, not its correctness - it falls back to the age floor.
    _commit_quietly(db, version)
    return job_id


def retry(db, version):
    """Read the same version again. Raises 409 when there is nothing to retry.

    Reconciles FIRST, so a stranded row still saying "running" can be retried the moment
    somebody presses the button rather than only after a poll has flipped it.
    """
    reconcile_one(db, version)

    if version.confirmed_at is not None:
        raise AppException(
            status_code=409,
            message=(
                "This document has already been confirmed. Reading it again would rewrite "
                "what was agreed. Upload the document again if it needs to be read afresh."
            ),
            code="extraction_retry_confirmed",
        )

    state = version.extraction_state
    if state not in PENDING_STATES and state != "failed":
        raise AppException(
            status_code=409,
            message=(
                "This document has already been read. Upload it again if you need a fresh "
                "read: re-reading it here would discard any line that has been corrected "
                "by hand."
            ),
            code="extraction_retry_already_read",
        )

    if state in PENDING_STATES:
        # It survived the reconcile, so it is genuinely in flight. Two work-horses reading
        # one document would both write lines onto it.
        raise AppException(
            status_code=409,
            message=(
                "This document is still being read. A read of a long document takes a few "
                "minutes; wait for it to finish before starting another one."
            ),
            code="extraction_retry_in_flight",
        )

    version.extraction_state = "queued"
    version.extraction_error = None
    version.extraction_started_at = None
    version.extraction_job_id = None
    db.commit()

    start_job(db, version)
    return version


def mark_started(db, version) -> None:
    """Stamp the moment the reader actually picked this document up.

    Called by the reader itself as it flips the row to `running`, which is the only place
    that knows. Without it a wait can only be drawn as a spinner, and a spinner with no
    number behind it is exactly what let a killed job sit on screen looking busy.
    """
    version.extraction_started_at = datetime.utcnow()


def _commit_quietly(db, version) -> None:
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not record the queued read on version %s", version.id)
        db.rollback()


# Kept so a caller can be explicit about which document kind it holds without importing the
# models: both are handled identically everywhere above, and that is the point.
DOCUMENT_MODELS = (ProjectPOVersion, DeliveryScheduleVersion)
