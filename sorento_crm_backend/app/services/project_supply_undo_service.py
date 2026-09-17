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
from sqlalchemy.orm.attributes import get_history, set_committed_value

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


#: The three tables the refusal predicate and the authorisation check both read the
#: journal's OWN entries for (review round, "Undoable" / contracts A-C) - computed
#: once here rather than re-derived per call, and shared so the predicate can never
#: read a different table name than capture actually wrote.
_DECISIONS_TABLE = "projects.so_supply_decisions"
_OI_ROWS_TABLE = "projects.order_inquiry_rows"
_OI_LINKS_TABLE = "projects.order_inquiry_links"


def _journalled(obj: Any) -> bool:
    """Everything except `audit_logs` itself.

    The confirm's own audit CREATE/UPDATE rows are not part of the plan's write-set
    (fifteen tables, none of them `audit_logs`) and must never be replayed away: an
    undo that deleted the original confirm's own audit trail would erase evidence of
    an action that, per R2, is meant to look like it never happened to the DATA -
    never to the record that it happened at all.
    """
    return not isinstance(obj, AuditLog)


def _assert_single_pk(obj: Any) -> None:
    """Contract F (review round): a composite primary key is not safely replayable.

    Replay's own `_pk_column` reads only the FIRST primary key column - a captured
    composite-pk row would replay a delete/insert/update against the wrong half of
    its own identity, silently. Raising here, at CAPTURE, means a table this module
    has never been taught about fails loudly the moment a Confirm ever touches it,
    rather than corrupting a stranger's row the day someone finally undoes it.
    """
    table = obj.__table__
    if len(table.primary_key.columns) != 1:
        raise ValueError(
            f"UndoJournal cannot capture {_table_name(obj)}: composite primary key, "
            "not replayable by a single pk column."
        )


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
        # out of the journal entirely - but ONLY on the clean exit path (Contract J,
        # review round): the route wraps the WHOLE confirm call in `UndoJournal(db):`,
        # and a business-logic refusal leaves the session mid-transaction. Flushing
        # anyway here, in a bare `finally`, could itself raise and turn a clean 409
        # into a 500 - or worse, half-write a confirm the caller meant to abandon.
        try:
            if exc_type is None:
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
            _assert_single_pk(obj)
            entry = {"seq": seq, "op": "insert", "table": _table_name(obj), "pk": None, "old": None}
            self.entries.append(entry)
            self._pending_inserts.append((entry, obj))
        for obj in list(session.dirty):
            if not _journalled(obj):
                continue
            _assert_single_pk(obj)
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
            _assert_single_pk(obj)
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
        """Write the captured journal onto the decision THIS confirm minted, and null
        the journal of the decision it superseded (Contract H, review round).

        Called AFTER the `with` block has exited, never inside it - the listener is
        already detached by then, so writing `undo_journal` does not journal itself.
        The decision's own insert is already in `self.entries` (captured like any
        other row), which is correct: replay deletes it along with everything else.

        Core SQL (review round), not `decision.undo_journal = ...; self.db.flush()`:
        an ORM assignment marks the decision dirty and goes through the SAME
        `before_flush` audit listener every other write in this app does, which by
        default captures every column - exactly the "whole journal copied into
        audit_logs on confirm" finding. `__audit_columns__` now excludes the column
        too (belt and braces), but the write itself should not depend on that.

        The superseded decision's own journal is nulled HERE, at CONFIRM time, not
        only later when an undo reinstates it (R3/AC-UC-22 is the separate, undo-side
        guarantee): a superseded revision's journal replays against a book state THIS
        confirm has already changed underneath it, and is not safely replayable by
        the time a second confirm has landed on top of it.
        """
        journal_payload = list(self.entries)
        table = Base.metadata.tables[_DECISIONS_TABLE]
        self.db.execute(
            table.update()
            .where(table.c.id == decision.id)
            .values(undo_journal=journal_payload)
        )
        if decision.supersedes_id:
            self.db.execute(
                table.update()
                .where(table.c.id == decision.supersedes_id)
                .values(undo_journal=None)
            )
        self.db.flush()
        # Core SQL bypasses the ORM identity map - keep the in-memory object in sync
        # (`set_committed_value`, not a plain attribute assignment: this session's own
        # later reads of `decision.undo_journal` must see the real value, but without
        # marking the object dirty again for a future flush to re-audit).
        set_committed_value(decision, "undo_journal", journal_payload)


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


def _replay(
    db: Session, journal: List[Dict[str, Any]], *, company_id: Optional[str]
) -> None:
    """The three passes (plan "Replay"). Reversing the whole list once and filtering
    by op is capture order reversed for each population; within each population,
    `_run_with_retries` settles the FK-dependency order capture order does not
    promise.

    Every delete and update ANDs `company_id == company_id` when the table carries
    that column (review round: "no table allowlist" was declined - one writer of the
    column today - but a company predicate costs nothing and core SQL bypasses the
    ORM's own scope filter entirely, so this is the one guard replay keeps for itself).
    """
    reversed_entries = list(reversed(journal))
    inserted_keys = {(e["table"], e["pk"]) for e in journal if e["op"] == "insert"}

    def _scoped(stmt, table):
        if company_id is not None and "company_id" in table.c:
            return stmt.where(table.c.company_id == company_id)
        return stmt

    # Pass 1: delete every row this confirm inserted.
    delete_jobs = []
    for entry in reversed_entries:
        if entry["op"] != "insert":
            continue
        table = Base.metadata.tables[entry["table"]]
        pk = entry["pk"]
        stmt = _scoped(table.delete().where(_pk_column(table) == pk), table)

        def _delete(stmt=stmt):
            db.execute(stmt)

        delete_jobs.append(_delete)
    _run_with_retries(db, delete_jobs)

    # Pass 2: re-insert every row this confirm deleted, skipping a pk this SAME
    # confirm both inserted and later deleted (Contract E, review round) - a link
    # drafted and removed inside one confirm never existed before it at all, and
    # re-inserting it would bring back a row nothing before this confirm ever had.
    insert_jobs = []
    for entry in reversed_entries:
        if entry["op"] != "delete":
            continue
        if (entry["table"], entry["pk"]) in inserted_keys:
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

        stmt = _scoped(table.update().where(_pk_column(table) == pk), table).values(**values)

        def _update(stmt=stmt):
            db.execute(stmt)

        update_jobs.append(_update)
    _run_with_retries(db, update_jobs)


# --------------------------------------------------------------------------- refusal

_REFUSAL_MESSAGES = {
    "no_journal": "This confirm cannot be undone.",
    "linked": "Purchasing has linked a PO line to this order since it was confirmed.",
    "actioned": "Purchasing has marked a row on this order actioned since it was confirmed.",
    "superseded": "A newer confirm has already replaced this one.",
}


def _journal_pk_set(journal, table: str, ops: Tuple[str, ...]) -> set:
    return {e["pk"] for e in journal if e["table"] == table and e["op"] in ops}


def _journal_entry_for_pk(journal, table: str, pk: str) -> Optional[Dict[str, Any]]:
    for entry in journal:
        if entry["table"] == table and entry["pk"] == pk:
            return entry
    return None


def touched_project_sales_order_ids(db: Session, decision: SOSupplyDecision) -> set:
    """Every project sales order THIS decision's own journal names (review round,
    "Undoable"): the order confirmed, plus any donor order a cross-project borrow
    re-issued in the same transaction. The journal, not the caller's own idea of
    "this order", says what the confirm actually touched - `undo_last_confirm`'s
    own authorisation check and the refusal predicate both read this same set, so a
    donor's row purchasing has since acted on is never missed (Contract B).

    Falls back to the decision's own order when the journal carries no
    `so_supply_decisions` entry naming one (should not happen for a real journal -
    the decision's own insert is always in it - but a hand-built one, as the
    "cascade restamp" kill test constructs, may name only the row it is about).
    """
    journal = decision.undo_journal or []
    pks = _journal_pk_set(journal, _DECISIONS_TABLE, ("insert", "update"))
    if not pks:
        return {decision.project_sales_order_id}
    rows = (
        db.query(SOSupplyDecision.id, SOSupplyDecision.project_sales_order_id)
        .filter(SOSupplyDecision.id.in_(pks))
        .all()
    )
    resolved = {pso_id for _id, pso_id in rows if pso_id}
    return resolved or {decision.project_sales_order_id}


def _grouped_refusals(db: Session, decisions: List[Any]) -> Dict[str, Optional[str]]:
    """R1's refusal, computed for every decision passed at once (review round: the
    N+1 finding) - a fixed small number of queries regardless of how many decisions
    are asked about, rather than `_refusal_reason`'s own shape run once per decision.

    `decisions` needs only `.id`, `.project_sales_order_id`, `.confirmed_at` and
    `.undo_journal` - a real `SOSupplyDecision` or a lightweight stand-in both work.

    `linked`: an `order_inquiry_links` row on one of the touched orders' rows whose
    id is NOT in the journal's own insert set for that table, and whose `linked_at`
    is after `confirmed_at`. `auto` is irrelevant (review round: an AutoCount pairing
    is purchasing's placement as much as a hand click) - membership in the journal's
    own insert set, not a raw flag, is what tells the confirm's OWN step-3 link
    apart from one purchasing placed afterward (the clock-mismatch finding this
    replaces: `confirmed_at` is a Python `datetime.utcnow()`, `linked_at` is
    Postgres `now()` resolved microseconds later in the very same transaction).

    `actioned`: a row currently `state = 'actioned'` that was not ALREADY actioned
    when the confirm ran - read off the journal's own old value for that row's
    `state` when the row is IN the journal (present but the key absent means the
    column never changed, so the old value is the current one - still `actioned`,
    not a fresh transition); a row the journal never touched counts only when its
    own `actioned_at` is after `confirmed_at`.
    """
    journal_by_decision = {d.id: (d.undo_journal or []) for d in decisions}
    confirmed_at_by_decision = {d.id: d.confirmed_at for d in decisions}

    all_decision_pks: set = set()
    for journal in journal_by_decision.values():
        all_decision_pks |= _journal_pk_set(journal, _DECISIONS_TABLE, ("insert", "update"))
    pso_by_decision_pk: Dict[str, str] = {}
    if all_decision_pks:
        pso_by_decision_pk = dict(
            db.query(SOSupplyDecision.id, SOSupplyDecision.project_sales_order_id)
            .filter(SOSupplyDecision.id.in_(all_decision_pks))
            .all()
        )

    pso_ids_by_decision: Dict[str, set] = {}
    for d in decisions:
        journal = journal_by_decision[d.id]
        touched = {
            pso_by_decision_pk[pk]
            for pk in _journal_pk_set(journal, _DECISIONS_TABLE, ("insert", "update"))
            if pk in pso_by_decision_pk
        }
        pso_ids_by_decision[d.id] = touched or {d.project_sales_order_id}

    all_pso_ids: set = set()
    for pso_ids in pso_ids_by_decision.values():
        all_pso_ids |= pso_ids

    pso_by_line: Dict[str, str] = {}
    if all_pso_ids:
        pso_by_line = dict(
            db.query(ProjectSalesOrderLine.id, ProjectSalesOrderLine.project_sales_order_id)
            .filter(ProjectSalesOrderLine.project_sales_order_id.in_(all_pso_ids))
            .all()
        )

    row_ids_by_pso: Dict[str, set] = {}
    pso_by_row: Dict[str, str] = {}
    if pso_by_line:
        for row_id, line_id in (
            db.query(OrderInquiryRow.id, OrderInquiryRow.so_line_id)
            .filter(OrderInquiryRow.so_line_id.in_(list(pso_by_line.keys())))
            .all()
        ):
            pso_id = pso_by_line.get(line_id)
            if not pso_id:
                continue
            pso_by_row[row_id] = pso_id
            row_ids_by_pso.setdefault(pso_id, set()).add(row_id)

    all_row_ids = list(pso_by_row.keys())
    actioned_rows = (
        db.query(OrderInquiryRow.id, OrderInquiryRow.actioned_at)
        .filter(OrderInquiryRow.id.in_(all_row_ids), OrderInquiryRow.state == INQUIRY_ACTIONED)
        .all()
        if all_row_ids
        else []
    )
    links_by_row: Dict[str, list] = {}
    if all_row_ids:
        for link_id, row_id, linked_at in (
            db.query(OrderInquiryLink.id, OrderInquiryLink.row_id, OrderInquiryLink.linked_at)
            .filter(
                OrderInquiryLink.row_id.in_(all_row_ids),
                OrderInquiryLink.linked_at.isnot(None),
            )
            .all()
        ):
            links_by_row.setdefault(row_id, []).append((link_id, linked_at))

    out: Dict[str, Optional[str]] = {}
    for d in decisions:
        confirmed_at = confirmed_at_by_decision[d.id]
        out[d.id] = None
        if not confirmed_at:
            continue
        journal = journal_by_decision[d.id]
        own_row_ids: set = set()
        for pso_id in pso_ids_by_decision[d.id]:
            own_row_ids |= row_ids_by_pso.get(pso_id, set())
        if not own_row_ids:
            continue

        refusal: Optional[str] = None
        for row_id, actioned_at in actioned_rows:
            if row_id not in own_row_ids:
                continue
            entry = _journal_entry_for_pk(journal, _OI_ROWS_TABLE, row_id)
            old = (entry.get("old") or {}) if entry is not None else {}
            if "state" in old:
                # The confirm's OWN write is what changed `state` (or left it, if
                # this is a merged multi-flush entry whose oldest capture already
                # read "actioned" - the cascade re-stamp case, AC-UC unchanged).
                # Present and not "actioned" means the confirm itself was the one
                # that actioned it - "not already actioned when the confirm ran".
                if old["state"] != "actioned":
                    refusal = "actioned"
                    break
                continue
            # The journal says nothing about `state` for this row - either it was
            # never touched by the confirm at all, or it was touched for OTHER
            # columns only, which tells us nothing about when it became actioned.
            # Fall back to the same clock test an untouched row gets.
            if actioned_at is not None and actioned_at > confirmed_at:
                refusal = "actioned"
                break

        if refusal is None:
            insert_link_pks = _journal_pk_set(journal, _OI_LINKS_TABLE, ("insert",))
            for row_id in own_row_ids:
                found = False
                for link_id, linked_at in links_by_row.get(row_id, ()):
                    if link_id in insert_link_pks:
                        continue
                    if linked_at and linked_at > confirmed_at:
                        refusal = "linked"
                        found = True
                        break
                if found:
                    break

        out[d.id] = refusal
    return out


def _refusal_reason(db: Session, decision: SOSupplyDecision) -> Optional[str]:
    """`_grouped_refusals`'s own rule, for a single decision - `undo_last_confirm`
    checks exactly one, so batching buys it nothing; `board_undo_map` is the caller
    that batches, over every decision on the board at once."""
    return _grouped_refusals(db, [decision]).get(decision.id)


# --------------------------------------------------------------------------- email


def _undo_email_lines(
    db: Session, journal: List[Dict[str, Any]], pso_id: str
) -> List[Dict[str, Any]]:
    """One `{item_code, qty, delivery_date, outcome}` per order inquiry row the
    journal touched, belonging to THIS order alone (review round: "the undone email
    lists a donor's rows" - a cross-project borrow's journal can also name the
    donor's own re-issue, and the undone order's own email must never speak for an
    order it did not undo): a row this confirm INSERTED is `removed` (undo deletes
    it); a row it UPDATED goes `back to <qty> on <dd/mm/yyyy>`, from the journal's
    own restored (old) values.

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
        for row in db.query(OrderInquiryRow)
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id,
        )
        .filter(
            OrderInquiryRow.id.in_(pks),
            ProjectSalesOrderLine.project_sales_order_id == pso_id,
        )
        .all()
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


# --------------------------------------------------------------------------- authorisation


def _actor_permission_slugs(db: Session, user_id: Optional[str]) -> set:
    from app.services.user_service import UserPermissionService

    if not user_id:
        return set()
    return set(UserPermissionService(db).get_user_permission_slugs(user_id))


def _assert_actor_can_undo(db: Session, actor_user_id: Optional[str], pso_ids: set) -> None:
    """Contract C (review round): undo re-runs Confirm's own per-project
    authorisation for the REQUESTING user, at EXECUTE time - `projects.projects.edit`
    alone is the park-time gate (checked once, when the pending action is created),
    not the write gate. Same shape `_assert_can_act_on` in `fulfilment_planning.py`
    uses for Confirm itself: no project on the order means the module permission on
    the route is the whole gate (an order adopted from the AutoCount book has none by
    design), so only an order that DOES carry a project is checked here.

    Runs over EVERY order the journal touched (Contract B) - a donor order's own
    project rights matter just as much as the order the planner clicked Undo on.
    """
    if not pso_ids:
        return
    orders = (
        db.query(ProjectSalesOrder.id, ProjectSalesOrder.project_id)
        .filter(ProjectSalesOrder.id.in_(pso_ids))
        .all()
    )
    if not orders:
        return
    from app.services.project_service import assert_can_edit_project, get_project_or_404

    slugs = _actor_permission_slugs(db, actor_user_id)
    for _pso_id, project_id in orders:
        if not project_id:
            continue
        project = get_project_or_404(db, project_id)
        assert_can_edit_project(db, project, actor_user_id, slugs)


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

    pso_ids = touched_project_sales_order_ids(db, decision)
    _assert_actor_can_undo(db, actor_user_id, pso_ids)

    refusal = _refusal_reason(db, decision)
    if refusal:
        raise AppException(status_code=409, message=_REFUSAL_MESSAGES[refusal], code=refusal)

    revision_no = decision.revision_no
    prior_id = decision.supersedes_id
    decision_id = decision.id
    company_id = decision.company_id
    journal = decision.undo_journal
    pso_id = order.id

    # Read BEFORE replay: `_replay` below deletes or overwrites these very rows.
    undo_lines = _undo_email_lines(db, journal, str(pso_id))

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
    # `undo_journal` popped (review round, Contract D): a replay script is not a
    # fact the audit trail names, and it can be large.
    audit_old_values = _model_to_audit_dict(decision)
    audit_old_values.pop("undo_journal", None)
    log_audit(
        db,
        "project_so_supply_decisions",
        str(decision_id),
        "DELETE",
        old_values=audit_old_values,
        user_id=actor_user_id,
        company_id=company_id,
    )

    _replay(db, journal, company_id=company_id)

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

    Review round (N+1 finding): the board's own per-order facts (revision, confirmed
    at/by) are read as SCALAR COLUMNS, never the `undo_journal` JSONB - a board of
    fifty orders has no reason to pull fifty replay scripts into Python to answer
    "who confirmed this and when". The journal itself is fetched separately, scoped
    to just the decisions that are actually undoable, and the refusal for every one
    of them is computed in ONE pass by `_grouped_refusals` rather than once per order.
    """
    from types import SimpleNamespace

    from app.models.user import User

    pso_ids = {pso_id for pso_id in adopted_by_so.values() if pso_id}
    if not pso_ids:
        return {so_id: None for so_id in adopted_by_so}

    scalar_rows = (
        db.query(
            SOSupplyDecision.id,
            SOSupplyDecision.project_sales_order_id,
            SOSupplyDecision.revision_no,
            SOSupplyDecision.confirmed_at,
            SOSupplyDecision.confirmed_by,
        )
        .filter(
            SOSupplyDecision.project_sales_order_id.in_(pso_ids),
            SOSupplyDecision.state == DECISION_ACTIVE,
            SOSupplyDecision.undo_journal.isnot(None),
        )
        .all()
    )
    if not scalar_rows:
        return {so_id: None for so_id in adopted_by_so}

    decision_ids = [row.id for row in scalar_rows]
    journals = dict(
        db.query(SOSupplyDecision.id, SOSupplyDecision.undo_journal)
        .filter(SOSupplyDecision.id.in_(decision_ids))
        .all()
    )
    decision_stand_ins = [
        SimpleNamespace(
            id=row.id,
            project_sales_order_id=row.project_sales_order_id,
            confirmed_at=row.confirmed_at,
            undo_journal=journals.get(row.id) or [],
        )
        for row in scalar_rows
    ]
    refusal_by_decision = _grouped_refusals(db, decision_stand_ins)

    by_pso = {row.project_sales_order_id: row for row in scalar_rows}
    user_ids = {row.confirmed_by for row in scalar_rows if row.confirmed_by}
    names: Dict[str, str] = {}
    if user_ids:
        names = dict(db.query(User.id, User.name).filter(User.id.in_(user_ids)).all())

    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for so_id, pso_id in adopted_by_so.items():
        row = by_pso.get(pso_id) if pso_id else None
        if row is None:
            out[so_id] = None
            continue
        out[so_id] = {
            "revision_no": row.revision_no,
            "confirmed_at": row.confirmed_at,
            "confirmed_by_name": names.get(row.confirmed_by),
            "refusal": refusal_by_decision.get(row.id),
            "decision_id": str(row.id),
        }
    return out
