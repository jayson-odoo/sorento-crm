"""Per-row outcome recording for import jobs.

Why this exists
---------------
Import jobs used to move their counters inline (``skipped += 1; continue``), so a
job could finish green reporting 4,028 skipped rows while naming only 10 of them.
This recorder is the ONLY way to move a counter, which makes "a skip without a
reason" impossible to write rather than merely discouraged.

Design constraints, all load-bearing:

* **Never one INSERT per row.** Rows accumulate in a list and are written with a
  single ``bulk_insert_mappings`` per buffer, so a 4k-row import costs a handful
  of round trips. (UAC AC-A8.)
* **Its own session.** Row detail must survive an import that rolls back, and must
  not interfere with the importer's transaction or savepoints. (UAC AC-A6.)
* **In-memory aggregation.** The breakdown is computed from counters held here,
  never re-read from the table, so counts stay exact even when row persistence is
  capped by ``max_rows``. (UAC AC-A9.)
* **Best effort.** Any recorder failure is logged and swallowed: observability must
  never break the import it is observing. (UAC AC-A7.)
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services import import_outcome_codes as codes

logger = logging.getLogger(__name__)


def _scope_session(session) -> None:
    """Mark the recorder's own session as unscoped, where company scoping exists.

    ``import_job_rows`` is job-tracking infrastructure like ``import_jobs`` - never
    company-partitioned. This is a deliberately soft dependency: the multi-company
    layer is optional, and a missing module must not silently swallow every row
    write (the whole point of this recorder is that nothing disappears quietly).
    """
    try:
        from app.services.company_scope import set_company_scope
    except ImportError:
        return  # no company scoping in this deployment - nothing to do
    try:
        set_company_scope(session, None)
    except Exception:
        logger.debug("Could not set company scope on the outcome session", exc_info=True)

#: Rows buffered before a bulk insert is issued.
DEFAULT_BUFFER_SIZE = 1000
#: Runaway backstop. Beyond this many rows we stop persisting detail (counts and
#: the breakdown stay exact) and flag `rows_truncated`.
DEFAULT_MAX_ROWS = 200_000
#: Distinct values tracked per code for `top_values`. Bounded so a column of
#: 200k unique ids cannot balloon the aggregation.
MAX_TRACKED_VALUES_PER_CODE = 1000
#: Distinct values emitted per code in the breakdown.
TOP_VALUES_EMITTED = 10


class ImportOutcome:
    """Records what an import did with each source row.

    Usage::

        outcome = ImportOutcome(import_job_id)
        outcome.skip(row=12, code=codes.PRODUCT_NOT_FOUND,
                     message="Product not found: ABC", value="ABC",
                     identity={"doc_no": "DO-1", "item_code": "ABC"})
        ...
        outcome.flush()
        job_service.complete_job(..., **outcome.completion_counts(),
                                 result=outcome.finalize("Import completed"))
    """

    def __init__(
        self,
        import_job_id: Optional[Any],
        *,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        max_rows: int = DEFAULT_MAX_ROWS,
        persist: bool = True,
        session_factory=None,
    ) -> None:
        self.import_job_id = import_job_id
        self.buffer_size = max(1, buffer_size)
        self.max_rows = max(0, max_rows)
        # `persist=False` powers the validation previews: aggregate only, write nothing.
        self.persist = bool(persist and import_job_id is not None)
        self._session_factory = session_factory

        self._buffer: List[Dict[str, Any]] = []
        self._persisted = 0
        self._rows_truncated = False

        # (outcome, code) -> count. The single source of truth for every number
        # this class reports.
        self._counter: Counter = Counter()
        # code -> Counter(value -> count)
        self._values: Dict[str, Counter] = defaultdict(Counter)
        self._labels: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def success(
        self,
        *,
        row: Optional[int] = None,
        code: str = codes.CREATED,
        message: Optional[str] = None,
        value: Optional[str] = None,
        identity: Optional[Dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
        outcome: str = codes.OUTCOME_CREATED,
    ) -> None:
        self._record(
            outcome=outcome,
            code=code,
            row=row,
            message=message,
            value=value,
            identity=identity,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def updated(self, **kwargs) -> None:
        kwargs.setdefault("code", codes.UPDATED)
        self.success(outcome=codes.OUTCOME_UPDATED, **kwargs)

    def unchanged(self, **kwargs) -> None:
        kwargs.setdefault("code", codes.UNCHANGED)
        self.success(outcome=codes.OUTCOME_UNCHANGED, **kwargs)

    def skip(
        self,
        *,
        code: str,
        row: Optional[int] = None,
        message: Optional[str] = None,
        value: Optional[str] = None,
        identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._record(
            outcome=codes.OUTCOME_SKIPPED,
            code=code,
            row=row,
            message=message,
            value=value,
            identity=identity,
        )

    def fail(
        self,
        *,
        code: str = codes.ROW_ERROR,
        row: Optional[int] = None,
        message: Optional[str] = None,
        value: Optional[str] = None,
        identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._record(
            outcome=codes.OUTCOME_FAILED,
            code=code,
            row=row,
            message=message,
            value=value,
            identity=identity,
        )

    def _record(
        self,
        *,
        outcome: str,
        code: str,
        row: Optional[int],
        message: Optional[str],
        value: Optional[str],
        identity: Optional[Dict[str, Any]],
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
    ) -> None:
        try:
            code = code or codes.ROW_ERROR
            label = codes.label_for(code)
            self._labels.setdefault(code, label)
            self._counter[(outcome, code)] += 1

            if value:
                tracked = self._values[code]
                # Only start NEW keys while under the cap; existing keys keep counting
                # so the values already surfaced stay accurate.
                if len(tracked) < MAX_TRACKED_VALUES_PER_CODE or value in tracked:
                    tracked[str(value)[:255]] += 1

            if not self.persist:
                return
            if self._persisted + len(self._buffer) >= self.max_rows:
                self._rows_truncated = True
                return

            self._buffer.append(
                {
                    "id": uuid.uuid4(),
                    "import_job_id": self.import_job_id,
                    "row_number": row,
                    "outcome": outcome,
                    "code": code,
                    "message": (message or label)[:4000] if (message or label) else None,
                    "value": str(value)[:255] if value else None,
                    "identity": _json_safe_identity(identity),
                    "entity_type": entity_type,
                    "entity_id": str(entity_id) if entity_id is not None else None,
                    "created_at": datetime.utcnow(),
                }
            )
            if len(self._buffer) >= self.buffer_size:
                self.flush()
        except Exception:  # never break the import being observed
            logger.warning(
                "ImportOutcome record failed (job=%s, code=%s)",
                self.import_job_id,
                code,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def flush(self) -> None:
        """Write buffered rows in ONE bulk insert on a session of our own.

        Also bumps `import_jobs.processed_rows` to `self.processed` - the exact count
        recorded so far, independent of what gets persisted below - in the SAME commit.
        Generic on purpose (S5): every importer that buffers through this class inherits a
        LIVE activity card for free, rather than the card sitting at 0 until the job's own
        `complete_job` call writes the final figure. `self.processed` is a plain counter sum
        (`_counter`), so this is exact even when row detail itself is capped by `max_rows`.

        The bump is its own inner try/except, deliberately: this class's whole point is that
        observability never breaks the import it is observing, and letting a progress-bump
        defect (a stub session in a test, a stale `import_job_id`) abort the row insert too
        would fail AC-A7 on a feature this file did not have before.
        """
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []
        if not self.persist:
            return
        session = None
        try:
            from app.models.job import ImportJobRow

            factory = self._session_factory
            if factory is None:
                from app.database import SessionLocal as factory  # type: ignore

            session = factory()
            _scope_session(session)
            session.bulk_insert_mappings(ImportJobRow, batch)
            try:
                from app.models.job import ImportJob

                session.query(ImportJob).filter(ImportJob.id == self.import_job_id).update(
                    {"processed_rows": self.processed}, synchronize_session=False
                )
            except Exception:
                logger.debug(
                    "ImportOutcome could not bump processed_rows for job %s",
                    self.import_job_id,
                    exc_info=True,
                )
            session.commit()
            self._persisted += len(batch)
        except Exception:
            logger.warning(
                "ImportOutcome flush failed for job %s (%s rows dropped)",
                self.import_job_id,
                len(batch),
                exc_info=True,
            )
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    pass
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    @property
    def successful(self) -> int:
        return sum(
            count
            for (outcome, _code), count in self._counter.items()
            if outcome in codes.SUCCESS_OUTCOMES
        )

    @property
    def failed(self) -> int:
        return sum(
            count
            for (outcome, _code), count in self._counter.items()
            if outcome == codes.OUTCOME_FAILED
        )

    @property
    def skipped(self) -> int:
        return sum(
            count
            for (outcome, _code), count in self._counter.items()
            if outcome == codes.OUTCOME_SKIPPED
        )

    @property
    def processed(self) -> int:
        return sum(self._counter.values())

    @property
    def rows_truncated(self) -> bool:
        return self._rows_truncated

    def count_of(self, code: str) -> int:
        """How many rows carry this code, across outcomes."""
        return sum(c for (_o, k), c in self._counter.items() if k == code)

    def completion_counts(self, total_rows: Optional[int] = None) -> Dict[str, int]:
        """kwargs for ``JobService.complete_job`` / ``update_job_progress``."""
        out = {
            "successful_rows": self.successful,
            "failed_rows": self.failed,
            "skipped_rows": self.skipped,
            "processed_rows": self.processed,
        }
        if total_rows is not None:
            out["total_rows"] = total_rows
        return out

    def breakdown(self) -> Dict[str, List[Dict[str, Any]]]:
        """Complete, exact reason breakdown. Never truncated."""
        grouped: Dict[str, List[Dict[str, Any]]] = {
            "successful": [],
            "skipped": [],
            "failed": [],
        }
        for (outcome, code), count in self._counter.items():
            if outcome in codes.SUCCESS_OUTCOMES:
                group = "successful"
            elif outcome == codes.OUTCOME_SKIPPED:
                group = "skipped"
            else:
                group = "failed"
            top_values = [
                {"value": value, "count": vcount}
                for value, vcount in self._values.get(code, Counter()).most_common(
                    TOP_VALUES_EMITTED
                )
            ]
            grouped[group].append(
                {
                    "code": code,
                    "label": self._labels.get(code, codes.label_for(code)),
                    "count": count,
                    "top_values": top_values,
                }
            )
        for group in grouped:
            grouped[group].sort(key=lambda e: (-e["count"], e["code"]))
        return grouped

    def finalize(
        self, message: str, total_rows: Optional[int] = None, **extra: Any
    ) -> Dict[str, Any]:
        """Flush remaining rows and build the uniform ``import_jobs.result`` envelope."""
        self.flush()
        total = total_rows if total_rows is not None else self.processed
        envelope: Dict[str, Any] = {
            "message": message,
            "counts": {
                "total": total,
                "processed": self.processed,
                "successful": self.successful,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "breakdown": self.breakdown(),
            "rows_truncated": self._rows_truncated,
            "rows_total": self._persisted,
        }
        envelope.update(extra)
        return envelope


def prune_import_job_rows(db, *, retention_days: int, batch_size: int = 5000) -> dict:
    """Delete per-row import detail older than the retention window.

    Keyset-batched: a full-history sweep of millions of rows must not be one
    unbounded DELETE holding a lock for minutes. Counts and the aggregated
    breakdown live on ``import_jobs.result`` and are untouched.
    """
    from datetime import timedelta

    from app.models.job import ImportJobRow

    cutoff = datetime.utcnow() - timedelta(days=int(retention_days))
    total_deleted = 0
    while True:
        ids = [
            row_id
            for (row_id,) in db.query(ImportJobRow.id)
            .filter(ImportJobRow.created_at < cutoff)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            break
        deleted = (
            db.query(ImportJobRow)
            .filter(ImportJobRow.id.in_(ids))
            .delete(synchronize_session=False)
        )
        db.commit()
        total_deleted += deleted
        if deleted == 0:  # defensive: never spin
            break
    return {"rows_deleted": total_deleted, "retention_days": int(retention_days)}


def _json_safe_identity(identity: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Identity is printed in the UI, so keep it small, flat and JSON-safe.

    Only the row's mapped business columns belong here - not the whole source row
    (UAC decision 4) and never raw UUIDs.
    """
    if not identity:
        return None
    safe: Dict[str, Any] = {}
    for key, value in identity.items():
        if value is None or value == "":
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[str(key)] = value if not isinstance(value, str) else value[:255]
        else:
            safe[str(key)] = str(value)[:255]
    return safe or None
