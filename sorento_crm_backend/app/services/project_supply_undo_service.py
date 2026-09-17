"""Undo last confirm on the fulfilment planning board (`PLAN-board-undo-last-confirm.md`).

One seam: every board Confirm runs inside a journal (`UndoJournal`) that records, at
each flush, what the unit of work is about to do. Undo (`undo_last_confirm`) replays
that journal backwards. Nothing here knows a table name in advance - the journal is
built generically off `session.new` / `session.dirty` / `session.deleted`, so a future
write site the plan's own research note never enumerated is still captured and still
undoable, and a table this module has never heard of is still replayed correctly.

Capture wraps the TWO board confirm routes only (`app/api/v1/projects/
fulfilment_planning.py`, `confirm_supply` and `write_one` inside `confirm_all`). A
revision minted anywhere else - `uncover_lines` after a rejection, a script - is never
wrapped and therefore carries no journal (`undo_journal IS NULL`), which is exactly
what makes it not undoable (AC-UC-14, AC-UC-26).

Serialization is the audit listener's own (`audit_service.py`), reused rather than
duplicated so the two can never drift: `_json_serial` for a single value, `_model_to_
audit_dict` for a whole row, `_entity_id_str` for a primary key.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Date, DateTime, Numeric, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from app.database import Base
from app.models.audit import AuditLog
from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_ACTIONED,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.services.audit_service import (
    _entity_id_str,
    _json_serial,
    _model_to_audit_dict,
    log_audit,
)
from app.services.error_handler import AppException
from app.services.project_order_inquiry_service import (
    ProjectOrderInquiryService,
    _dec as _oi_dec,
    _handover_fmt_date,
    _qty_str,
)

# --------------------------------------------------------------------------- capture


def _table_name(obj: Any) -> str:
    """`<schema>.<table>` when the model has one, else the bare table name - exactly
    the keys `Base.metadata.tables` itself uses, so replay can look one up directly."""
    table = obj.__table__
    return f"{table.schema}.{table.name}" if table.schema else table.name


def _journalled(obj: Any) -> bool:
    """Everything except `audit_logs` itself.

    The confirm's own audit CREATE/UPDATE rows are not part of the plan's write-set
    (fifteen tables, none of them `audit_logs`) and must never be replayed away: an
    undo that deleted the original confirm's own audit trail would erase evidence of
    an action that, per R2, is meant to look like it never happened to the DATA -
    never to the record that it happened at all.
    """
    return not isinstance(obj, AuditLog)


def _changed_old_values(obj: Any) -> Dict[str, Any]:
    """Only the columns that actually changed, old side (plan "Capture")."""
    mapper = inspect(obj).mapper
    old: Dict[str, Any] = {}
    for prop in mapper.column_attrs:
        hist = get_history(obj, prop.key)
        if not hist.has_changes():
            continue
        old_val = hist.deleted[0] if hist.deleted else (hist.unchanged[0] if hist.unchanged else None)
        old[prop.key] = _json_serial(old_val)
    return old


class UndoJournal:
    """A context manager that records every insert/update/delete the wrapped code
    performs, so `undo_last_confirm` can replay it backwards.

    Entries are `{"seq": int, "op": "insert"|"update"|"delete", "table": str,
    "pk": str, "old": dict | None}`, in CAPTURE ORDER (the list's own order); `seq` is
    the flush this entry came from, so a caller can also group by flush when it
    matters (replay does not need to - reversing the whole list already reverses both
    within-flush and across-flush order at once).

    An insert's own primary key is not known until the flush that performs it has
    actually run (a Python-side column default is resolved during the flush, after
    `before_flush` fires) - so its `pk` is filled in from `after_flush`, once the row
    is in the database and the object's identity is populated.
    """

    def __init__(self, db: Session):
        self.db = db
        self.entries: List[Dict[str, Any]] = []
        self._seq = 0
        self._pending_inserts: List[Tuple[Dict[str, Any], Any]] = []
        #: (table, pk) -> index into `self.entries`, for an "update" entry only. A row
        #: touched across TWO separate flushes of the same confirm (a common shape:
        #: `set_row_decision` writes `composition_json` in one flush, `apply` writes
        #: `applied_state`/`result_json` in a later one) merges into the ONE entry a
        #: reader expects for that row, rather than splitting across two - each column
        #: keeps the OLDEST old value it was captured with, which is its true value
        #: from before this confirm touched it at all.
        self._update_index: Dict[Tuple[str, str], int] = {}

    def __enter__(self) -> "UndoJournal":
        event.listen(self.db, "before_flush", self._before_flush)
        event.listen(self.db, "after_flush", self._after_flush)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # The unit of work's FINAL writes must be captured before the listener comes
        # off, or a caller that writes and never flushes again would leave that write
        # out of the journal entirely.
        try:
            self.db.flush()
        finally:
            event.remove(self.db, "before_flush", self._before_flush)
            event.remove(self.db, "after_flush", self._after_flush)
        return False

    def _before_flush(self, session: Session, _flush_context: Any, _instances: Any) -> None:
        self._seq += 1
        seq = self._seq
        for obj in list(session.new):
            if not _journalled(obj):
                continue
            entry = {"seq": seq, "op": "insert", "table": _table_name(obj), "pk": None, "old": None}
            self.entries.append(entry)
            self._pending_inserts.append((entry, obj))
        for obj in list(session.dirty):
            if not _journalled(obj):
                continue
            old = _changed_old_values(obj)
            if not old:
                continue
            table = _table_name(obj)
            pk = _entity_id_str(obj)
            key = (table, pk)
            existing_index = self._update_index.get(key)
            if existing_index is not None:
                existing_old = self.entries[existing_index]["old"]
                for column, value in old.items():
                    existing_old.setdefault(column, value)
            else:
                self.entries.append(
                    {"seq": seq, "op": "update", "table": table, "pk": pk, "old": old}
                )
                self._update_index[key] = len(self.entries) - 1
        for obj in list(session.deleted):
            if not _journalled(obj):
                continue
            self.entries.append(
                {
                    "seq": seq,
                    "op": "delete",
                    "table": _table_name(obj),
                    "pk": _entity_id_str(obj),
                    "old": _model_to_audit_dict(obj),
                }
            )

    def _after_flush(self, _session: Session, _flush_context: Any) -> None:
        # The flush just executed: every pending insert's identity is now populated.
        while self._pending_inserts:
            entry, obj = self._pending_inserts.pop(0)
            entry["pk"] = _entity_id_str(obj)

    def attach(self, decision: SOSupplyDecision) -> None:
        """Write the captured journal onto the decision THIS confirm minted.

        Called AFTER the `with` block has exited, never inside it - the listener is
        already detached by then, so writing `undo_journal` does not journal itself.
        The decision's own insert is already in `self.entries` (captured like any
        other row), which is correct: replay deletes it along with everything else.
        """
        decision.undo_journal = list(self.entries)
        self.db.flush()


# --------------------------------------------------------------------------- replay


def _pk_column(table):
    return list(table.primary_key.columns)[0]


def _coerce_value(column, value: Any) -> Any:
    if value is None:
        return None
    col_type = column.type
    if isinstance(col_type, DateTime):
        return value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if isinstance(col_type, Date):
        return value if isinstance(value, date) else date.fromisoformat(value)
    if isinstance(col_type, Numeric):
        return value if isinstance(value, Decimal) else Decimal(str(value))
    return value


def _coerce_row(table, data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in data.items():
        column = table.c.get(key)
        if column is None:
            continue
        out[key] = _coerce_value(column, value)
    return out


def _run_with_retries(db: Session, jobs: List[Any]) -> None:
    """Run every job, retrying the ones that fail on a foreign key until nothing more
    can be done.

    `session.new` / `session.dirty` / `session.deleted` (what `UndoJournal` captures
    from) iterate in NO order related to the sequence the confirm's own code called
    `db.add()` / `db.delete()` in - SQLAlchemy's unit of work sorts INSERT/DELETE
    statements by FK dependency itself, at flush time, using information this
    journal does not keep. So capture order cannot be trusted to already be FK-safe
    for a reinsert or a delete, and each job runs in its own SAVEPOINT: one that
    fails because a row it depends on is not there YET is simply tried again after
    every job that succeeded this round, exactly like a topological sort would.
    """
    remaining = list(jobs)
    while remaining:
        failed: List[Any] = []
        progressed = False
        for job in remaining:
            savepoint = db.begin_nested()
            try:
                job()
            except IntegrityError:
                savepoint.rollback()
                failed.append(job)
            else:
                savepoint.commit()
                progressed = True
        if not progressed:
            # Nothing left can succeed on its own - run the first failure again so
            # its real error surfaces, rather than looping forever or failing silently.
            failed[0]()
            return
        remaining = failed


def _replay(db: Session, journal: List[Dict[str, Any]]) -> None:
    """The three passes (plan "Replay"). Reversing the whole list once and filtering
    by op is capture order reversed for each population; within each population,
    `_run_with_retries` settles the FK-dependency order capture order does not
    promise.
    """
    reversed_entries = list(reversed(journal))
    inserted_keys = {(e["table"], e["pk"]) for e in journal if e["op"] == "insert"}

    # Pass 1: delete every row this confirm inserted.
    delete_jobs = []
    for entry in reversed_entries:
        if entry["op"] != "insert":
            continue
        table = Base.metadata.tables[entry["table"]]
        pk = entry["pk"]

        def _delete(table=table, pk=pk):
            db.execute(table.delete().where(_pk_column(table) == pk))

        delete_jobs.append(_delete)
    _run_with_retries(db, delete_jobs)

    # Pass 2: re-insert every row this confirm deleted.
    insert_jobs = []
    for entry in reversed_entries:
        if entry["op"] != "delete":
            continue
        table = Base.metadata.tables[entry["table"]]
        values = _coerce_row(table, entry["old"] or {})
        if not values:
            continue

        def _insert(table=table, values=values):
            db.execute(table.insert().values(**values))

        insert_jobs.append(_insert)
    _run_with_retries(db, insert_jobs)

    # Pass 3: restore the old values of every row this confirm updated, skipping a
    # pk that this SAME confirm also inserted (already gone - pass 1 took it). Runs
    # AFTER pass 2: a row deleted later in the confirm and updated earlier is
    # re-inserted with its at-delete values first, then this restores the older
    # values on top.
    update_jobs = []
    for entry in reversed_entries:
        if entry["op"] != "update":
            continue
        if (entry["table"], entry["pk"]) in inserted_keys:
            continue
        table = Base.metadata.tables[entry["table"]]
        pk = entry["pk"]
        values = _coerce_row(table, entry["old"] or {})
        if not values:
            continue

        def _update(table=table, pk=pk, values=values):
            db.execute(table.update().where(_pk_column(table) == pk).values(**values))

        update_jobs.append(_update)
    _run_with_retries(db, update_jobs)


# --------------------------------------------------------------------------- refusal

_REFUSAL_MESSAGES = {
    "no_journal": "This confirm cannot be undone.",
    "manual_link": "Purchasing has linked a PO line to this order since it was confirmed.",
    "actioned": "Purchasing has marked a row on this order actioned since it was confirmed.",
    "superseded": "A newer confirm has already replaced this one.",
}


def _refusal_reason(db: Session, pso_id: str, decision: SOSupplyDecision) -> Optional[str]:
    """R1: only a manual link or an actioned row written AFTER the confirm blocks
    undo. Time, not actor, separates purchasing's own work from the confirm's own
    step-3 borrow link, which is `auto=False` but `linked_at` no later than
    `confirmed_at` (written inside the same transaction; Postgres `now()` is constant
    within one)."""
    confirmed_at = decision.confirmed_at
    if not confirmed_at:
        return None
    line_ids = [
        row[0]
        for row in db.query(ProjectSalesOrderLine.id)
        .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
        .all()
    ]
    if not line_ids:
        return None
    row_ids = [
        row[0]
        for row in db.query(OrderInquiryRow.id)
        .filter(OrderInquiryRow.so_line_id.in_(line_ids))
        .all()
    ]
    if not row_ids:
        return None
    actioned = (
        db.query(OrderInquiryRow.id)
        .filter(
            OrderInquiryRow.id.in_(row_ids),
            OrderInquiryRow.state == INQUIRY_ACTIONED,
            OrderInquiryRow.actioned_at.isnot(None),
            OrderInquiryRow.actioned_at > confirmed_at,
        )
        .first()
    )
    if actioned:
        return "actioned"
    manual_link = (
        db.query(OrderInquiryLink.id)
        .filter(
            OrderInquiryLink.row_id.in_(row_ids),
            OrderInquiryLink.auto.is_(False),
            OrderInquiryLink.linked_at.isnot(None),
            OrderInquiryLink.linked_at > confirmed_at,
        )
        .first()
    )
    if manual_link:
        return "manual_link"
    return None


# --------------------------------------------------------------------------- email


def _undo_email_lines(db: Session, journal: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One `{item_code, qty, delivery_date, outcome}` per order inquiry row the
    journal touched (plan "The email"): a row this confirm INSERTED is `removed`
    (undo deletes it); a row it UPDATED goes `back to <qty> on <dd/mm/yyyy>`, from
    the journal's own restored (old) values.

    Reads the rows BEFORE `_replay` runs - by the time replay has deleted or
    overwritten them, this information is gone.
    """
    oi_table = _table_name(OrderInquiryRow)
    pks = [
        entry["pk"]
        for entry in journal
        if entry["table"] == oi_table and entry["op"] in ("insert", "update")
    ]
    if not pks:
        return []
    rows_by_pk = {
        row.id: row
        for row in db.query(OrderInquiryRow).filter(OrderInquiryRow.id.in_(pks)).all()
    }

    lines: List[Dict[str, Any]] = []
    for entry in journal:
        if entry["table"] != oi_table or entry["op"] not in ("insert", "update"):
            continue
        row = rows_by_pk.get(entry["pk"])
        if row is None:
            continue
        if entry["op"] == "insert":
            lines.append(
                {
                    "item_code": row.item_code,
                    "qty": _qty_str(row.qty),
                    "delivery_date": _handover_fmt_date(row.delivery_date),
                    "outcome": "removed",
                }
            )
            continue
        old = entry["old"] or {}
        qty = _oi_dec(old.get("qty", row.qty))
        delivery_date = old.get("delivery_date", row.delivery_date)
        if isinstance(delivery_date, str):
            delivery_date = date.fromisoformat(delivery_date)
        qty_str = _qty_str(qty)
        date_str = _handover_fmt_date(delivery_date)
        lines.append(
            {
                "item_code": row.item_code,
                "qty": qty_str,
                "delivery_date": date_str,
                "outcome": f"back to {qty_str} on {date_str}",
            }
        )
    return lines


# --------------------------------------------------------------------------- undo


def undo_last_confirm(
    db: Session,
    order: ProjectSalesOrder,
    *,
    actor_user_id: Optional[str],
    expected_decision_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Replay the order's newest confirm backwards (plan "Undo service").

    `expected_decision_id` is the decision the pending action was created against
    (AC-UC-28): a Confirm written during the countdown makes the newest decision a
    DIFFERENT row by the time the window lapses, and this refuses `superseded` rather
    than undoing the wrong revision.
    """
    decision = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == DECISION_ACTIVE,
        )
        .first()
    )
    if decision is None or not decision.undo_journal:
        raise AppException(
            status_code=409, message=_REFUSAL_MESSAGES["no_journal"], code="no_journal"
        )

    if expected_decision_id is not None and str(decision.id) != str(expected_decision_id):
        raise AppException(
            status_code=409, message=_REFUSAL_MESSAGES["superseded"], code="superseded"
        )

    refusal = _refusal_reason(db, str(order.id), decision)
    if refusal:
        raise AppException(status_code=409, message=_REFUSAL_MESSAGES[refusal], code=refusal)

    revision_no = decision.revision_no
    prior_id = decision.supersedes_id
    decision_id = decision.id
    company_id = decision.company_id
    journal = decision.undo_journal
    pso_id = order.id

    # Read BEFORE replay: `_replay` below deletes or overwrites these very rows.
    undo_lines = _undo_email_lines(db, journal)

    restored_to: Optional[int] = None
    if prior_id:
        restored_to = (
            db.query(SOSupplyDecision.revision_no)
            .filter(SOSupplyDecision.id == prior_id)
            .scalar()
        )

    # AC-UC-29: the undone decision's own audit DELETE, written explicitly - replay
    # below is core SQL throughout (`Base.metadata.tables`, not ORM objects) so no
    # listener re-fires on the way back except this one, deliberate row.
    log_audit(
        db,
        "project_so_supply_decisions",
        str(decision_id),
        "DELETE",
        old_values=_model_to_audit_dict(decision),
        user_id=actor_user_id,
        company_id=company_id,
    )

    _replay(db, journal)

    if prior_id:
        # R3: one revision back, once - the reinstated decision is not itself
        # undoable. Raw SQL, like the rest of replay: an ORM assignment on a row
        # `_replay` just touched via core SQL would be working off a stale in-memory
        # copy if this session had loaded it earlier.
        table = Base.metadata.tables["projects.so_supply_decisions"]
        db.execute(table.update().where(table.c.id == prior_id).values(undo_journal=None))

    ProjectOrderInquiryService(db)._record_undo(
        pso_id=str(pso_id) if pso_id else None,
        decision_id=str(decision_id),
        revision_no=revision_no,
        lines=undo_lines,
        actor_user_id=actor_user_id,
    )

    db.flush()
    return {"revision_no": revision_no, "restored_to": restored_to}


# --------------------------------------------------------------------------- board


def board_undo_map(
    db: Session, adopted_by_so: Dict[str, Optional[str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """One `undo` per selected order, keyed the same way `adopted_by_so` is - by the
    CORE `sales_orders.id` - so `project_fulfilment_board_service.py` can read it
    straight into each `BoardOrderStanding` (plan "Undoable", AC-UC-15).
    """
    from app.models.user import User

    pso_ids = {pso_id for pso_id in adopted_by_so.values() if pso_id}
    if not pso_ids:
        return {so_id: None for so_id in adopted_by_so}

    decisions = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id.in_(pso_ids),
            SOSupplyDecision.state == DECISION_ACTIVE,
            SOSupplyDecision.undo_journal.isnot(None),
        )
        .all()
    )
    by_pso = {d.project_sales_order_id: d for d in decisions}
    user_ids = {d.confirmed_by for d in decisions if d.confirmed_by}
    names: Dict[str, str] = {}
    if user_ids:
        names = dict(db.query(User.id, User.name).filter(User.id.in_(user_ids)).all())

    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for so_id, pso_id in adopted_by_so.items():
        decision = by_pso.get(pso_id) if pso_id else None
        if decision is None:
            out[so_id] = None
            continue
        out[so_id] = {
            "revision_no": decision.revision_no,
            "confirmed_at": decision.confirmed_at,
            "confirmed_by_name": names.get(decision.confirmed_by),
            "refusal": _refusal_reason(db, pso_id, decision),
            "decision_id": str(decision.id),
        }
    return out
