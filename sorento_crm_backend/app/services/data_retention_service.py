"""Data retention rules (PLAN-db-retention-12nov, sections 2 and 7).

Every rule deletes (or blanks) in keyset batches: one commit per batch, an optional
sleep between batches, and a time budget checked BETWEEN batches, so a run always
completes at least one batch and a run that runs out of time stops cleanly with
``finished: False`` (the next run carries on). With ``dry_run`` a rule only counts what
a live run would do and writes nothing.

Every rule returns a dict holding ``dry_run``, ``finished`` and its counts; that dict is
the scheduled task's run summary, and the same line goes to the log.

The two shared helpers are :func:`batched_delete` (also :func:`batched_update`) and
:func:`two_stage_prune`; ``prune_import_job_rows`` and ``prune_api_call_log`` call them too.
No VACUUM anywhere: the owner reclaims disk by hand (runbook db-retention-and-disk.md).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import String, and_, cast, delete, exists, func, null, or_, select, union, update
from sqlalchemy.orm import Session, aliased

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5000

# system_settings knobs shared by every rule, with their defaults (plan section 2).
DRY_RUN_SETTING = ("data_retention_dry_run", False)
BATCH_SIZE_SETTING = ("data_retention_batch_size", 5000)
SLEEP_MS_SETTING = ("data_retention_batch_sleep_ms", 200)
MAX_RUN_MINUTES_SETTING = ("data_retention_max_run_minutes", 30)


# --------------------------------------------------------------------------- #
# shared machinery
# --------------------------------------------------------------------------- #

class Budget:
    """The clock and batch count of ONE rule run, shared by every stage of it."""

    def __init__(self, *, sleep_ms: int = 0, max_seconds: Optional[float] = None):
        self.started = time.monotonic()
        self.sleep_ms = int(sleep_ms or 0)
        self.max_seconds = max_seconds
        self.batches = 0

    def next_batch(self) -> bool:
        """Call right before a batch that has work. The first batch always runs; after
        that False means the time is up, otherwise sleep and go."""
        if self.batches:
            if self.max_seconds is not None and time.monotonic() - self.started >= self.max_seconds:
                return False
            if self.sleep_ms > 0:
                time.sleep(self.sleep_ms / 1000.0)
        self.batches += 1
        return True


def _pk(model):
    return model.__mapper__.primary_key[0]


def _rowcount(result) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


def _count(db: Session, model, conditions: Iterable) -> int:
    return int(db.execute(select(func.count(_pk(model))).where(*conditions)).scalar() or 0)


def _keyset_batches(
    db: Session,
    model,
    conditions: list,
    apply: Callable[[list], Any],
    *,
    batch_size: int,
    budget: Budget,
) -> tuple[int, bool]:
    """Walk the matching primary keys in key order, ``batch_size`` at a time, and run
    ``apply`` (a statement over those keys) per batch, one commit each. The statement
    re-asserts ``conditions`` so a row that stopped matching meanwhile is left alone."""
    pk = _pk(model)
    done = 0
    last = None
    while True:
        q = select(pk).where(*conditions)
        if last is not None:
            q = q.where(pk > last)
        ids = [row[0] for row in db.execute(q.order_by(pk).limit(max(int(batch_size), 1)))]
        if not ids:
            return done, True
        if not budget.next_batch():
            return done, False
        stmt = apply(ids).where(pk.in_(ids), *conditions).execution_options(synchronize_session=False)
        done += _rowcount(db.execute(stmt))
        db.commit()
        last = ids[-1]


def batched_delete(
    db: Session,
    model,
    *conditions,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
    budget: Optional[Budget] = None,
) -> tuple[int, bool]:
    """Delete the rows of ``model`` matching ``conditions`` in keyset batches.
    Returns ``(rows, finished)``; dry-run counts and writes nothing."""
    conditions = list(conditions)
    if dry_run:
        return _count(db, model, conditions), True
    budget = budget or Budget(sleep_ms=sleep_ms, max_seconds=max_seconds)
    return _keyset_batches(
        db, model, conditions, lambda _ids: delete(model), batch_size=batch_size, budget=budget
    )


def batched_update(
    db: Session,
    model,
    conditions: list,
    values: dict,
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
    budget: Optional[Budget] = None,
) -> tuple[int, bool]:
    """Set ``values`` on the rows matching ``conditions`` in keyset batches. The
    conditions must stop matching once updated (e.g. ``col IS NOT NULL`` when blanking)."""
    conditions = list(conditions)
    if dry_run:
        return _count(db, model, conditions), True
    budget = budget or Budget(sleep_ms=sleep_ms, max_seconds=max_seconds)
    return _keyset_batches(
        db, model, conditions, lambda _ids: update(model).values(values),
        batch_size=batch_size, budget=budget,
    )


def rule_result(rule: str, *, dry_run: bool, finished: bool, **counts) -> dict:
    """The rule's run summary, also written as one log line."""
    result = {**counts, "dry_run": bool(dry_run), "finished": bool(finished)}
    logger.info("data retention %s: %s", rule, result)
    return result


def _cutoff(days: float, *, aware: bool = False) -> datetime:
    if aware:
        return datetime.now(timezone.utc) - timedelta(days=float(days))
    return datetime.utcnow() - timedelta(days=float(days))


def two_stage_prune(
    db: Session,
    model,
    *,
    rule: str,
    created_column,
    payload_columns: list,
    payload_retention_days: int,
    row_retention_days: int,
    extra_conditions: Iterable = (),
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """Delete rows past the row window, then blank the payload columns of rows past the
    payload window. Payloads are the bulk of the bytes and the shortest-lived value; the
    metadata row stays useful for trend analysis long after the body does.

    The two counts describe disjoint sets: the blank stage only takes rows newer than the
    row window (so a dry run does not count a payload the same run deletes), and only rows
    with a payload left (so a re-run reports 0 rather than re-clearing the same rows)."""
    extra = list(extra_conditions)
    row_cutoff = _cutoff(row_retention_days)
    payload_cutoff = _cutoff(payload_retention_days)
    budget = Budget(sleep_ms=sleep_ms, max_seconds=max_seconds)
    knobs = {"dry_run": dry_run, "batch_size": batch_size, "budget": budget}

    rows_deleted, finished = batched_delete(db, model, created_column < row_cutoff, *extra, **knobs)
    payloads_cleared = 0
    if finished:
        payloads_cleared, finished = batched_update(
            db,
            model,
            [
                created_column < payload_cutoff,
                created_column >= row_cutoff,
                or_(*[col.isnot(None) for col in payload_columns]),
                *extra,
            ],
            {col: None for col in payload_columns},
            **knobs,
        )
    return rule_result(
        rule, dry_run=dry_run, finished=finished,
        payloads_cleared=int(payloads_cleared), rows_deleted=int(rows_deleted),
    )


# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #

def prune_plan_exceptions(
    db: Session,
    *,
    grace_days: float = 1,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """R1. A batch that is not the newest of its planning run within its company (batches
    with no run are one group per company) and was generated before the grace loses its undecided rows; a batch left with
    no rows goes too. A decided row (status not open, or a decision time) and its batch
    stay forever. Newest = ``generated_at`` desc, the order ``latest_batch`` reads."""
    from app.models.scm import PlanException, PlanExceptionBatch

    ranked = select(
        PlanExceptionBatch.id.label("id"),
        PlanExceptionBatch.generated_at.label("generated_at"),
        func.row_number()
        .over(
            # Per company: the screen reads the newest batch under a company-scoped
            # session. NULL run ids form one partition per company.
            partition_by=(PlanExceptionBatch.company_id, PlanExceptionBatch.run_id),
            order_by=(PlanExceptionBatch.generated_at.desc(), PlanExceptionBatch.id.desc()),
        )
        .label("rn"),
    ).subquery()
    batch_ids = [
        row[0]
        for row in db.execute(
            select(ranked.c.id).where(ranked.c.rn > 1, ranked.c.generated_at < _cutoff(grace_days))
        )
    ]
    if not batch_ids:
        return rule_result(
            "plan_exception_prune", dry_run=dry_run, finished=True, rows_deleted=0, batches_deleted=0
        )

    undecided = and_(PlanException.status == "open", PlanException.decided_at.is_(None))
    budget = Budget(sleep_ms=sleep_ms, max_seconds=max_seconds)
    knobs = {"dry_run": dry_run, "batch_size": batch_size, "budget": budget}

    rows_deleted, finished = batched_delete(
        db, PlanException, PlanException.batch_id.in_(batch_ids), undecided, **knobs
    )
    batches_deleted = 0
    if finished:
        # Live: only a batch that is now empty. Dry run: the rows are all still there, so
        # count the batches that hold no row the live run would keep.
        left = [PlanException.batch_id == PlanExceptionBatch.id]
        if dry_run:
            left.append(~undecided)
        batches_deleted, finished = batched_delete(
            db, PlanExceptionBatch, PlanExceptionBatch.id.in_(batch_ids), ~exists().where(*left), **knobs
        )
    return rule_result(
        "plan_exception_prune", dry_run=dry_run, finished=finished,
        rows_deleted=int(rows_deleted), batches_deleted=int(batches_deleted),
    )


def prune_integration_log(
    db: Session,
    *,
    payload_retention_days: int,
    row_retention_days: int,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """R2. Payloads and headers blank past the payload window, rows go past the row
    window. A pending or processing row is still work in flight and is never touched, nor
    is a failed-audit record (audit_trail_gaps.integration_log_id points at it)."""
    from app.models.integration import IntegrationLog as L
    from app.services.audit_service import AUDIT_FAILURE_CHANNEL

    return two_stage_prune(
        db,
        L,
        rule="integration_log_prune",
        created_column=L.created_at,
        payload_columns=[L.request_payload, L.response_payload, L.request_headers, L.response_headers],
        payload_retention_days=payload_retention_days,
        row_retention_days=row_retention_days,
        extra_conditions=[
            func.lower(L.status).notin_(("pending", "processing")),
            L.integration_channel != AUDIT_FAILURE_CHANNEL,
        ],
        dry_run=dry_run,
        batch_size=batch_size,
        sleep_ms=sleep_ms,
        max_seconds=max_seconds,
    )


def prune_chatbot_turn_traces(
    db: Session,
    *,
    retention_days: int,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """R3a. An old chat turn loses its trace; the turn itself stays."""
    from app.models.chatbot_turn import ChatbotTurn

    cleared, finished = batched_update(
        db,
        ChatbotTurn,
        [ChatbotTurn.created_at < _cutoff(retention_days, aware=True), ChatbotTurn.trace.isnot(None)],
        # null(), not None: None into JSONB writes JSON 'null', which IS NOT NULL to SQL.
        {ChatbotTurn.trace: null()},
        dry_run=dry_run, batch_size=batch_size, sleep_ms=sleep_ms, max_seconds=max_seconds,
    )
    return rule_result(
        "chatbot_turn_trace_prune", dry_run=dry_run, finished=finished, traces_cleared=int(cleared)
    )


def prune_scheduled_task_runs(
    db: Session,
    *,
    retention_days: int,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """R3b. Old run history goes, except each task's newest run (a task that has not run
    since still shows its last result)."""
    from app.models.scheduled_task import ScheduledTaskRun as R

    newer = aliased(R)
    deleted, finished = batched_delete(
        db,
        R,
        R.started_at < _cutoff(retention_days),
        exists().where(newer.task_id == R.task_id, newer.started_at > R.started_at),
        dry_run=dry_run, batch_size=batch_size, sleep_ms=sleep_ms, max_seconds=max_seconds,
    )
    return rule_result(
        "scheduled_task_runs_prune", dry_run=dry_run, finished=finished, rows_deleted=int(deleted)
    )


def prune_reorder_runs(
    db: Session,
    *,
    retention_days: int,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """R3c. A superseded planning run past the window goes, unless somebody acted on it
    (``_reorder_runs_acted_on``). No long transaction: its children are deleted bottom-up in
    keyset batches (location allocations of its order summary rows, the order summary rows,
    the recommendations), one commit each, then the run row. Oldest run first, so a run is
    never orphaned of its ``superseded_by_run_id`` while it still waits its turn.

    FK children found in pg_constraint: reorder_recommendation and order_summary_row
    (CASCADE), plan_exception_batch.run_id and reorder_run's own supersede links (SET NULL);
    under a recommendation: recommendation_override and plan_row_decision (CASCADE, and
    their presence keeps the run) and order_summary_location_allocation (SET NULL; under
    order_summary_row it CASCADEs)."""
    from app.models.scm import (
        OrderSummaryLocationAllocation,
        OrderSummaryRow,
        ReorderRecommendation,
        ReorderRun,
    )

    base = [ReorderRun.superseded_by_run_id.isnot(None), ReorderRun.created_at < _cutoff(retention_days)]
    old = aliased(ReorderRun)
    old_runs = select(old.id).where(
        old.superseded_by_run_id.isnot(None), old.created_at < _cutoff(retention_days)
    )
    # Candidates: old, superseded, nobody acted on them. Listed ONCE per call (oldest first)
    # for both the live loop and the dry-run prediction.
    ordered = [
        r[0]
        for r in db.execute(
            select(ReorderRun.id)
            .where(*base, ReorderRun.id.notin_(_reorder_runs_acted_on(old_runs)))
            .order_by(ReorderRun.created_at, ReorderRun.id)
        )
    ]
    if dry_run:
        return rule_result(
            "reorder_run_prune", dry_run=True, finished=True,
            runs_deleted=_predict_reorder_runs_deleted(db, ReorderRun, ordered),
        )

    # A run another remaining run names as its superseder stays: the link is ON DELETE SET
    # NULL, so deleting it would turn that run (kept for a decision) back into a current
    # one. Checked per run as the loop goes, so an undecided chain drains in one call; the
    # acted-on trace is re-checked for that one run too (cheap: it is keyed on the run).
    pointer = aliased(ReorderRun)
    budget = Budget(sleep_ms=sleep_ms, max_seconds=max_seconds)
    runs_deleted = 0
    finished = True
    for run_id in ordered:
        still_eligible = base + [
            ReorderRun.id == run_id,
            ~exists().where(pointer.superseded_by_run_id == ReorderRun.id),
            ReorderRun.id.notin_(_reorder_runs_acted_on([run_id])),
        ]
        if db.execute(select(ReorderRun.id).where(*still_eligible)).first() is None:
            continue
        children = [
            (
                OrderSummaryLocationAllocation,
                [OrderSummaryLocationAllocation.order_summary_row_id.in_(
                    select(OrderSummaryRow.id).where(OrderSummaryRow.run_id == run_id)
                )],
            ),
            (OrderSummaryRow, [OrderSummaryRow.run_id == run_id]),
            (ReorderRecommendation, [ReorderRecommendation.run_id == run_id]),
        ]
        for model, conds in children:
            _, finished = batched_delete(db, model, *conds, batch_size=batch_size, budget=budget)
            if not finished:
                break
        if not finished:
            break
        if not budget.next_batch():
            finished = False
            break
        runs_deleted += _rowcount(
            db.execute(
                delete(ReorderRun).where(*still_eligible).execution_options(synchronize_session=False)
            )
        )
        db.commit()
    return rule_result("reorder_run_prune", dry_run=False, finished=finished, runs_deleted=runs_deleted)


def _reorder_runs_acted_on(run_ids):
    """The ids among ``run_ids`` (a select or a list) of planning runs somebody acted on:
    the ONE place the keep rules live. Accepted / adjusted / dismissed or keyed
    recommendations, overrides, plan row decisions, decided or keyed order summary rows,
    and drafted PO lines naming a recommendation (location grain) or
    ``<order summary row id>:<warehouse id>`` (product grain, decision_service).

    Set-based joins rather than EXISTS under an OR: Postgres cannot turn an OR'd EXISTS
    into a join, and the product-grain PO-line probe then scanned purchase_order_lines once
    per summary row (did not finish in 18 min at synthetic prod volume). As one NOT IN it is
    a hashed subplan: 1.7 s for 213 runs / 511k recommendations / 155k PO lines, most of it
    JIT. The location-grain probe can use ix_purchase_order_lines_source_ref_system; the
    product-grain one hash/merge-joins on split_part (no index serves a prefix match)."""
    from app.models.procurement import PurchaseOrderLine as POL
    from app.models.scm import (
        OrderSummaryRow as Row,
        PlanRowDecision,
        RecommendationOverride,
        ReorderRecommendation as Rec,
    )

    rec_in = Rec.run_id.in_(run_ids)
    row_in = Row.run_id.in_(run_ids)
    row_id = cast(Row.id, String)
    return union(
        select(Rec.run_id).where(rec_in, or_(Rec.status != "proposed", Rec.keyed_status != "not_keyed")),
        select(Rec.run_id).join(RecommendationOverride, RecommendationOverride.recommendation_id == Rec.id).where(rec_in),
        select(Rec.run_id).join(PlanRowDecision, PlanRowDecision.recommendation_id == Rec.id).where(rec_in),
        select(Rec.run_id).join(POL, POL.source_ref == cast(Rec.id, String)).where(rec_in),
        select(Row.run_id).where(
            row_in, or_(Row.chosen_qty.isnot(None), Row.decided_at.isnot(None), Row.keyed_status != "not_keyed")
        ),
        select(Row.run_id)
        .join(POL, and_(func.split_part(POL.source_ref, ":", 1) == row_id, POL.source_ref.like(row_id + ":%")))
        .where(row_in),
    )


def _predict_reorder_runs_deleted(db: Session, ReorderRun, ordered: list) -> int:
    """What the live loop deletes, without writing: walk the candidates in its order
    (oldest first) and take one once every run naming it as superseder is already taken."""
    if not ordered:
        return 0
    pointers: dict = {}
    for run_id, target in db.execute(
        select(ReorderRun.id, ReorderRun.superseded_by_run_id).where(
            ReorderRun.superseded_by_run_id.in_(ordered)
        )
    ):
        pointers.setdefault(target, []).append(run_id)
    gone: set = set()
    for run_id in ordered:
        if all(p in gone for p in pointers.get(run_id, ())):
            gone.add(run_id)
    return len(gone)


def prune_superseded_embeddings(
    db: Session,
    *,
    retention_days: int,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_ms: int = 0,
    max_seconds: Optional[float] = None,
) -> dict:
    """R3d. AI search chunks superseded past the window go; a current chunk never does
    (same predicate as dedupe_embedding_chunks_current --delete-superseded, plus an age)."""
    from app.models.embeddings import EmbeddingChunk as C

    deleted, finished = batched_delete(
        db,
        C,
        C.is_current.is_(False),
        C.superseded_at < _cutoff(retention_days),
        dry_run=dry_run, batch_size=batch_size, sleep_ms=sleep_ms, max_seconds=max_seconds,
    )
    return rule_result(
        "embedding_superseded_prune", dry_run=dry_run, finished=finished, rows_deleted=int(deleted)
    )


# --------------------------------------------------------------------------- #
# settings and dispatch (scheduler handlers and the CLI share this)
# --------------------------------------------------------------------------- #

def setting(settings, name: str, default):
    """A system_settings value, or its default when there is no row or the value is NULL."""
    value = getattr(settings, name, None) if settings is not None else None
    return default if value is None else value


def retention_knobs(settings) -> dict:
    """The shared knobs as rule kwargs (max run minutes -> max_seconds)."""
    return {
        "dry_run": bool(setting(settings, *DRY_RUN_SETTING)),
        "batch_size": int(setting(settings, *BATCH_SIZE_SETTING)),
        "sleep_ms": int(setting(settings, *SLEEP_MS_SETTING)),
        "max_seconds": float(setting(settings, *MAX_RUN_MINUTES_SETTING)) * 60.0,
    }


def _days(settings, name: str, default: int) -> int:
    return int(setting(settings, name, default))


def _api_call_log(db, s, **knobs):
    from app.services.api_call_log_service import prune_api_call_log

    return prune_api_call_log(
        db,
        payload_retention_days=_days(s, "api_call_log_payload_retention_days", 30),
        row_retention_days=_days(s, "api_call_log_row_retention_days", 180),
        **knobs,
    )


def _import_job_rows(db, s, **knobs):
    from app.services.import_outcome import prune_import_job_rows

    return prune_import_job_rows(
        db, retention_days=_days(s, "import_job_rows_retention_days", 90), **knobs
    )


RULES: dict[str, Callable[..., dict]] = {
    "plan_exception_prune": lambda db, s, **k: prune_plan_exceptions(
        db, grace_days=_days(s, "plan_exception_superseded_grace_days", 1), **k
    ),
    "integration_log_prune": lambda db, s, **k: prune_integration_log(
        db,
        payload_retention_days=_days(s, "integration_log_payload_retention_days", 30),
        row_retention_days=_days(s, "integration_log_row_retention_days", 180),
        **k,
    ),
    "chatbot_turn_trace_prune": lambda db, s, **k: prune_chatbot_turn_traces(
        db, retention_days=_days(s, "chatbot_turn_trace_retention_days", 90), **k
    ),
    "scheduled_task_runs_prune": lambda db, s, **k: prune_scheduled_task_runs(
        db, retention_days=_days(s, "scheduled_task_run_retention_days", 90), **k
    ),
    "reorder_run_prune": lambda db, s, **k: prune_reorder_runs(
        db, retention_days=_days(s, "reorder_run_retention_days", 90), **k
    ),
    "embedding_superseded_prune": lambda db, s, **k: prune_superseded_embeddings(
        db, retention_days=_days(s, "embedding_superseded_retention_days", 90), **k
    ),
    "api_call_log_prune": _api_call_log,
    "import_job_rows_prune": _import_job_rows,
}


def run_retention_rule(db: Session, key: str, **overrides) -> dict:
    """Run one rule with the system_settings knobs; a non-None override (the CLI's flags)
    wins over the setting."""
    from app.models.user import SystemSetting

    settings = db.query(SystemSetting).first()
    knobs = retention_knobs(settings)
    knobs.update({k: v for k, v in overrides.items() if v is not None})
    return RULES[key](db, settings, **knobs)
