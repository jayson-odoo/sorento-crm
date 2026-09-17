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

from sqlalchemy import (
    Date,
    DateTime,
    Numeric,
    and_,
    bindparam,
    case,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
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


def _journalled_decision_clause():
    """The SQL predicate for "this decision carries a real, replayable journal"
    (review round, follow-up): a non-null, NON-EMPTY `undo_journal` array, and a
    real `confirmed_at` - a decision minted with no `confirmed_at` (a script, a
    hand-built kill test) is not something the refusal predicate's own clock test
    can reason about either, so it is not undoable.

    `board_undo_map`'s own read filter uses this directly; `_decision_is_journalled`
    below is the exact same three conditions, evaluated in Python for
    `undo_last_confirm`'s already-loaded decision - one predicate, spelled once, so
    a board read and the undo it links to can never disagree about what "undoable"
    means at the edge (a NULL `confirmed_at`, or a journal that is present but
    empty).

    `CASE WHEN jsonb_typeof(...) = 'array' THEN jsonb_array_length(...) ELSE 0 END > 0`
    (hotfix, undo_0003), not `isnot(None)` + a bare `jsonb_array_length(...) > 0`: a
    JSON literal `null` (a legacy row a pre-fix build wrote via Core
    `.values(undo_journal=None)` before the model carried `none_as_null=True`) is
    not a SQL NULL, so `isnot(None)` was true for it and `jsonb_array_length` then
    threw (`InvalidParameterValue: cannot get array length of a scalar`). A plain
    `and_(jsonb_typeof(...) == 'array', jsonb_array_length(...) > 0)` does NOT fix
    this: Postgres does not guarantee left-to-right evaluation of an `AND`'s
    branches, so it can (and here, does) still evaluate `jsonb_array_length` on a
    JSON-null row even though the `jsonb_typeof` branch is false. A `CASE` IS
    guaranteed to evaluate its branches in order and skip the ones it does not
    take, so the array-length call never runs on anything that is not already
    known to be a JSON array - not undoable, no crash - for a JSON null, a JSON
    scalar, or a real SQL NULL alike.
    """
    return and_(
        case(
            (
                func.jsonb_typeof(SOSupplyDecision.undo_journal) == "array",
                func.jsonb_array_length(SOSupplyDecision.undo_journal),
            ),
            else_=0,
        )
        > 0,
        SOSupplyDecision.confirmed_at.isnot(None),
    )


def _decision_is_journalled(decision: Any) -> bool:
    """`_journalled_decision_clause`'s own three conditions, read off a decision
    already loaded in Python rather than issued as a fresh query.

    `isinstance(journal, list) and len(journal) > 0` (hotfix, undo_0003
    follow-up), not a bare `bool(decision.undo_journal)`, to match the SQL
    clause's own shape test (`jsonb_typeof(...) == 'array'` before the length
    check): the ORM deserialises a JSON `null` back to Python `None` either way,
    so `bool(...)` already agreed there, but spelling the same shape test on both
    sides keeps this predicate from silently drifting from the SQL one if the
    journal is ever something other than a list/None (a dict, a scalar) - `bool`
    on a non-empty dict or `1` would read journalled where the SQL side would not.
    """
    journal = decision.undo_journal
    return isinstance(journal, list) and len(journal) > 0 and decision.confirmed_at is not None


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


def _stale_column_values(obj: Any, keys: List[str]) -> Dict[str, Any]:
    """The columns `_changed_old_values` found a real CHANGE for but no baseline
    to report it against - `get_history` returns neither `deleted` nor
    `unchanged` for an attribute that was EXPIRED (a `commit()` earlier in the
    same request cleared SQLAlchemy's own cached "committed value") before this
    write set a new one on it, even under `get_history`'s own default
    `passive=PASSIVE_OFF` (confirmed empirically: this is a scalar-column
    expiry gap, not a relationship-loading one `passive` flags address).

    Read straight off Postgres instead, mid-flush: this row's own UPDATE for
    the current flush has not executed yet, so its CURRENT stored value on the
    actual connection IS the true old one.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import object_session

    table = obj.__table__
    pk_col = _pk_column(table)
    pk_val = _entity_id_str(obj)
    session = object_session(obj)
    if session is None:
        return {}
    row = session.connection().execute(
        select(*[table.c[k] for k in keys]).where(pk_col == pk_val)
    ).first()
    if row is None:
        return {}
    return {key: _json_serial(value) for key, value in zip(keys, row)}


def _changed_old_values(obj: Any) -> Dict[str, Any]:
    """Only the columns that actually changed, old side (plan "Capture")."""
    mapper = inspect(obj).mapper
    old: Dict[str, Any] = {}
    stale_keys: List[str] = []
    for prop in mapper.column_attrs:
        hist = get_history(obj, prop.key)
        if not hist.has_changes():
            continue
        if hist.deleted:
            old[prop.key] = _json_serial(hist.deleted[0])
        elif hist.unchanged:
            old[prop.key] = _json_serial(hist.unchanged[0])
        else:
            stale_keys.append(prop.key)
    if stale_keys:
        old.update(_stale_column_values(obj, stale_keys))
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
        #: (entry, obj, keys) for an "update" entry touched in the flush about to run -
        #: AC-R2-23 (S4): `new` is read from the object's live attributes in
        #: `_after_flush`, POST-flush, so a Python-side onupdate/default that only
        #: resolves during the flush is the real written value, not a guess taken
        #: before it ran. Re-queued on every flush the same row is touched in (the
        #: merge case below), so a row updated across two flushes ends with `new`
        #: covering every column EITHER flush changed, same as `old` already does.
        self._pending_updates: List[Tuple[Dict[str, Any], Any, List[str]]] = []
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
                self._pending_updates.append(
                    (self.entries[existing_index], obj, list(old.keys()))
                )
            else:
                entry = {"seq": seq, "op": "update", "table": table, "pk": pk, "old": old}
                self.entries.append(entry)
                self._update_index[key] = len(self.entries) - 1
                self._pending_updates.append((entry, obj, list(old.keys())))
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
        # AC-R2-23: `new` for an update entry, read from the object's own attributes
        # now that the flush that wrote them has run - a Python-side onupdate/default
        # (e.g. `updated_at`) only resolves during the flush, so reading it before
        # would have captured a stale value.
        while self._pending_updates:
            entry, obj, keys = self._pending_updates.pop(0)
            new_values = entry.setdefault("new", {})
            for key in keys:
                new_values[key] = _json_serial(getattr(obj, key, None))

    def attach(self, decision: SOSupplyDecision) -> None:
        """Write the captured journal onto the decision THIS confirm minted.

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

        AC-R2-20 (`PLAN-scm-oi-handover-r2-undo.md` S4, reverses ruling 3 of `PLAN-
        board-undo-last-confirm.md` and this method's own former Contract H): the
        superseded decision's own journal is LEFT AS IT WAS, never nulled here. Depth-N
        undo needs it: undoing revision 2 reinstates revision 1's post-image, and a
        SECOND undo has to be able to replay revision 1's own journal in turn - which a
        journal this confirm nulled at write time could never do. `changed`
        (`_grouped_refusals` below) is what stops a stale journal from ever being
        replayed against a book state it no longer matches, so nulling it here is no
        longer the safety net it once was.
        """
        journal_payload = list(self.entries)
        table = Base.metadata.tables[_DECISIONS_TABLE]
        self.db.execute(
            table.update()
            .where(table.c.id == decision.id)
            .values(undo_journal=journal_payload)
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
    #
    # `ON CONFLICT DO NOTHING` on the pk (follow-up review round): a delete-journal
    # entry whose row still exists at undo time - a savepoint that rolled the
    # delete back after the journal had already captured it, or any other reason
    # the row survived - must not raise a duplicate-key error `_run_with_retries`
    # cannot resolve (a genuine unique-constraint violation, not an FK-ordering
    # one). Idempotent re-insert: the row that is already there wins, undo still
    # succeeds, and nothing is duplicated.
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
            db.execute(
                pg_insert(table)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[_pk_column(table)])
            )

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
    "changed": "A row changed since this confirm.",
}


def _journal_pk_set(journal, table: str, ops: Tuple[str, ...]) -> set:
    return {e["pk"] for e in journal if e["table"] == table and e["op"] in ops}


def _journal_entry_for_pk(journal, table: str, pk: str) -> Optional[Dict[str, Any]]:
    for entry in journal:
        if entry["table"] == table and entry["pk"] == pk:
            return entry
    return None


def _pso_ids_by_decision(db: Session, decisions: List[Any]) -> Dict[str, set]:
    """Every project sales order EACH decision's own journal names (review round,
    "Undoable"): the order confirmed, plus any donor order a cross-project borrow
    re-issued in the same transaction. The journal, not the caller's own idea of
    "this order", says what the confirm actually touched - `undo_last_confirm`'s
    own authorisation check and the refusal predicate both read this same set, so a
    donor's row purchasing has since acted on is never missed (Contract B).

    ONE combined query resolves every decision pk any of the passed decisions'
    journals reference, whether there is one decision to ask about or fifty -
    `touched_project_sales_order_ids` (single decision) and `_grouped_refusals`
    (a whole board) both read THIS, so the derivation exists in exactly one place
    (review round, follow-up).

    A decision falls back to its own order when its journal carries no
    `so_supply_decisions` entry naming one (should not happen for a real journal -
    the decision's own insert is always in it - but a hand-built one, as the
    "cascade restamp" kill test constructs, may name only the row it is about).
    """
    journal_by_decision = {d.id: (d.undo_journal or []) for d in decisions}
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

    out: Dict[str, set] = {}
    for d in decisions:
        journal = journal_by_decision[d.id]
        touched = {
            pso_by_decision_pk[pk]
            for pk in _journal_pk_set(journal, _DECISIONS_TABLE, ("insert", "update"))
            if pk in pso_by_decision_pk
        }
        out[d.id] = touched or {d.project_sales_order_id}
    return out


def touched_project_sales_order_ids(db: Session, decision: SOSupplyDecision) -> set:
    """`_pso_ids_by_decision`'s own rule, for a single decision - `undo_last_confirm`
    and its own authorisation check ask about exactly one."""
    return _pso_ids_by_decision(db, [decision])[decision.id]


def _grouped_refusals(db: Session, decisions: List[Any]) -> Dict[str, Optional[str]]:
    """R1's refusal, computed for every decision passed at once (review round: the
    N+1 finding) - a fixed small number of queries regardless of how many decisions
    are asked about, rather than `_refusal_reason`'s own shape run once per decision.

    `decisions` needs only `.id`, `.project_sales_order_id`, `.confirmed_at` and
    `.undo_journal` - a real `SOSupplyDecision` or a lightweight stand-in both work
    (`board_undo_map` passes stand-ins carrying only the journal ENTRIES the
    predicate below actually reads, not the whole journal - see its own docstring).

    `linked`: an `order_inquiry_links` row on one of the touched orders' rows whose
    id is NOT in the journal's own insert set for that table, and whose `linked_at`
    is after `confirmed_at`. `auto` is irrelevant (review round: an AutoCount pairing
    is purchasing's placement as much as a hand click) - membership in the journal's
    own insert set, not a raw flag, is what tells the confirm's OWN step-3 link
    apart from one purchasing placed afterward (the clock-mismatch finding this
    replaces: `confirmed_at` is a Python `datetime.utcnow()`, `linked_at` is
    Postgres `now()` resolved microseconds later in the very same transaction).

    `actioned`: a row currently `state = 'actioned'` refuses UNLESS the journal
    carries an entry for that row whose own captured `old` dict has a `state` key
    equal to `"actioned"` - meaning the row was already actioned before this
    confirm ran, and the confirm's own cascade merely re-touched it (a different
    column, or a re-stamped `actioned_at`) without itself being the one that
    actioned it. When there is no `state` key but the journal's own `old` DOES
    carry an `actioned_at` (some other column changed under the confirm's write
    and `actioned_at` happened to be one of them), THAT stored value is compared
    against `confirmed_at`, never the live column - the live column can be
    re-stamped by a later, unrelated write between the confirm and this check
    (follow-up review round, the same clock-mismatch shape `linked` already
    guards against by insert-set membership rather than a raw timestamp). Only
    when the journal has NEITHER key for the row - absent entirely, present only
    as an INSERT (a freshly-raised row has no `old` at all), or present for some
    other column with neither `state` nor `actioned_at` touched - does the LIVE
    `actioned_at` stand in, compared the same way against `confirmed_at`.
    """
    journal_by_decision = {d.id: (d.undo_journal or []) for d in decisions}
    confirmed_at_by_decision = {d.id: d.confirmed_at for d in decisions}
    pso_ids_by_decision = _pso_ids_by_decision(db, decisions)

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
            # No `state` key. If the journal captured an `actioned_at` for this
            # row anyway (some OTHER column changed under the confirm's own
            # write, and `actioned_at` happened to be one of them), compare THAT
            # stored value against `confirmed_at` - not the live column, which can
            # be re-stamped by a later, unrelated write between the confirm and
            # this check (follow-up review round: the same clock-mismatch shape
            # `linked` already guards against by insert-set membership).
            stored_actioned_at = old.get("actioned_at")
            if stored_actioned_at is not None:
                if isinstance(stored_actioned_at, str):
                    stored_actioned_at = datetime.fromisoformat(stored_actioned_at)
                if stored_actioned_at > confirmed_at:
                    refusal = "actioned"
                    break
                continue
            # The journal has neither key for this row - either it was never
            # touched by the confirm at all, or it was touched for some column
            # that tells us nothing about when it became actioned. The live
            # column is all that is left.
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


def _changed_refusal(db: Session, decision: SOSupplyDecision) -> Optional[Dict[str, str]]:
    """AC-R2-24 (S4, `PLAN-scm-oi-handover-r2-undo.md`): refuse when a journalled
    `update` entry's `new` no longer matches the row's CURRENT value - another
    writer touched the same column since this confirm, so replaying the journal's
    own `old` would silently discard that write. An entry with no `new` at all is a
    LEGACY one (written before this lane) and is skipped outright (AC-R2-25).

    One `SELECT ... WHERE pk IN (...)` per table (review round shape, `_grouped_
    refusals`'s own batching precedent), never per row. Returns `{"table", "pk"}`
    for the FIRST mismatch found - enough to name it in the refusal message - or
    `None` when every journalled value still matches.

    Deliberately NOT folded into `_grouped_refusals`: that predicate also serves
    `board_undo_map`'s own multi-order read off a TRIMMED journal (three table
    kinds only, no `new` guarantee needed there - AC-R2-27's "no full-journal
    deserialisation added"), and this check needs the FULL journal plus a live
    read of every touched row. It runs only where an undo is actually about to
    happen: at park (`refusal_for_order`) and at execute, just before `_replay`.
    """
    from sqlalchemy import select

    journal = decision.undo_journal or []
    by_table: Dict[str, List[Dict[str, Any]]] = {}
    for entry in journal:
        if entry.get("op") != "update" or not entry.get("new"):
            continue
        by_table.setdefault(entry["table"], []).append(entry)
    for table_name, entries in by_table.items():
        table = Base.metadata.tables.get(table_name)
        if table is None:
            continue
        pk_col = _pk_column(table)
        keys_needed = sorted({key for entry in entries for key in entry["new"]})
        cols = [table.c[key] for key in keys_needed if key in table.c]
        if not cols:
            continue
        # `Base.metadata.tables[...]` (via `table`/`pk_col`/`cols` above), never a
        # schema-qualified `text()` literal: a raw string like `"projects.order_
        # inquiry_rows"` bypasses `blank_session()`'s own `schema_translate_map`
        # AND its pinned `search_path` (schema-qualified names never consult
        # `search_path` at all), silently landing on the real, empty schema
        # instead of the test's scratch one - see that fixture's own docstring.
        rows = db.execute(
            select(pk_col, *cols).where(pk_col.in_([entry["pk"] for entry in entries]))
        ).all()
        # RAW, typed values here - NOT `_json_serial`'d: a `Numeric(15, 4)` column
        # reads back `Decimal("15.0000")` where the journalled `new` (captured via
        # `_json_serial` on the ORM's own in-memory value right after assignment)
        # holds the string `"15"` - equal numerically, not string-equal. Coercing
        # the journalled STRING back through `_coerce_value` onto the column's own
        # type (the same helper replay uses) and comparing typed-to-typed is what
        # makes `Decimal("15") == Decimal("15.0000")` (True) the comparison that
        # runs, instead of a spurious mismatch on formatting alone.
        current_by_pk = {
            str(row[0]): {col.name: value for col, value in zip(cols, row[1:])} for row in rows
        }
        for entry in entries:
            current = current_by_pk.get(entry["pk"])
            if current is None:
                continue
            for key, new_value in entry["new"].items():
                if key not in current:
                    continue
                column = table.c.get(key)
                coerced_new = _coerce_value(column, new_value) if column is not None else new_value
                if current[key] != coerced_new:
                    return {"table": table_name, "pk": entry["pk"]}
    return None


def _refusal_reason_with_detail(
    db: Session, decision: SOSupplyDecision
) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
    """`_grouped_refusals`'s own `linked`/`actioned` rule for a single decision, then
    the `changed` check (AC-R2-24) - in that order, so a `linked`/`actioned` row
    still reports the refusal purchasing's own work earned, not a `changed` one a
    slower query happened to find first. `detail` (`{"table", "pk"}`) is only ever
    set alongside `"changed"` - every other code's message is the static one in
    `_REFUSAL_MESSAGES`."""
    reason = _grouped_refusals(db, [decision]).get(decision.id)
    if reason:
        return reason, None
    detail = _changed_refusal(db, decision)
    return ("changed", detail) if detail else (None, None)


def _refusal_reason(db: Session, decision: SOSupplyDecision) -> Optional[str]:
    """`_refusal_reason_with_detail`'s own code, for callers that never render the
    detail (`undo_last_confirm`'s existing test suite reads this bare)."""
    return _refusal_reason_with_detail(db, decision)[0]


def refusal_for_order_with_detail(
    db: Session, pso_id: str
) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
    """The SAME `linked`/`actioned`/`changed` predicate `undo_last_confirm` checks at
    commit time, run early - at PARK time (review round, follow-up) - so
    `POST /pending-actions` gives a raw caller the same synchronous 409 the
    disabled gear entry already implies, instead of a 202 followed by a failure
    several seconds later when the countdown lapses.

    `(None, None)` when the order has no active, journalled decision at all - that
    is the commit-time `no_journal` refusal's own job (`undo_last_confirm`),
    unchanged.
    """
    decision = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == pso_id,
            SOSupplyDecision.state == DECISION_ACTIVE,
        )
        .first()
    )
    if decision is None or not _decision_is_journalled(decision):
        return None, None
    return _refusal_reason_with_detail(db, decision)


def refusal_for_order(db: Session, pso_id: str) -> Optional[str]:
    """`refusal_for_order_with_detail`'s own code, for callers that never render the
    detail."""
    return refusal_for_order_with_detail(db, pso_id)[0]


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
        # `pso_ids` names real orders - `touched_project_sales_order_ids` only ever
        # resolves ids off the journal's own `so_supply_decisions` entries (real rows
        # that just existed) or the decision's own order. Finding NONE of them here
        # is not "nothing to authorise", it is company scope or the journal itself
        # disagreeing with reality - a silent `return` would let undo proceed as
        # though it had already been authorised (review round, follow-up).
        raise AssertionError(
            f"undo authorisation found no ProjectSalesOrder rows for {sorted(pso_ids)!r}"
        )
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
    if decision is None or not _decision_is_journalled(decision):
        raise AppException(
            status_code=409, message=_REFUSAL_MESSAGES["no_journal"], code="no_journal"
        )

    if expected_decision_id is not None and str(decision.id) != str(expected_decision_id):
        raise AppException(
            status_code=409, message=_REFUSAL_MESSAGES["superseded"], code="superseded"
        )

    pso_ids = touched_project_sales_order_ids(db, decision)
    _assert_actor_can_undo(db, actor_user_id, pso_ids)

    refusal, refusal_detail = _refusal_reason_with_detail(db, decision)
    if refusal:
        message = _REFUSAL_MESSAGES[refusal]
        if refusal == "changed" and refusal_detail:
            message = f"{message} ({refusal_detail['table']} pk={refusal_detail['pk']})"
        raise AppException(status_code=409, message=message, code=refusal)

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

    # AC-R2-21 (S4, reverses R3 "one revision back, once"): the reinstated
    # decision's own journal is left exactly as it is - depth-N undo needs it alive
    # so a SECOND undo can replay revision 1's own journal in turn (AC-R2-22). The
    # `changed` guard above is what now stops a stale journal from ever being
    # replayed against a book state it no longer matches, so there is nothing left
    # for this null-out to protect against.
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


class _JournalStandIn:
    """The four attributes `_grouped_refusals` reads off a decision - `.id`,
    `.project_sales_order_id`, `.confirmed_at`, `.undo_journal` - for a board read
    that never loads the real ORM row (`board_undo_map` only ever needs scalar
    columns plus a TRIMMED journal, never the mapped `SOSupplyDecision` itself)."""

    __slots__ = ("id", "project_sales_order_id", "confirmed_at", "undo_journal")

    def __init__(self, *, id, project_sales_order_id, confirmed_at, undo_journal):
        self.id = id
        self.project_sales_order_id = project_sales_order_id
        self.confirmed_at = confirmed_at
        self.undo_journal = undo_journal


def _trimmed_journal_entries(db: Session, decision_ids: List[str]) -> Dict[str, list]:
    """The ONLY three kinds of journal entry `_grouped_refusals` ever reads, pulled
    straight out of Postgres's own copy of `undo_journal` via `jsonb_path_query_
    array` (review round, follow-up: "board reads only the journal pk sets") -
    `so_supply_decisions` inserts/updates (`_pso_ids_by_decision`'s own need),
    every `order_inquiry_rows` entry (the actioned check needs each one's own `old`,
    not just its pk), and `order_inquiry_links` INSERT entries (the linked check's
    own exemption set). Everything else in the journal - `so_line_allocations`,
    `stock_transfers`, drafts, claims, `planning_change_*` - never leaves Postgres.

    Returns exactly the shape `_grouped_refusals` already reads off a real
    `.undo_journal`: a flat list of `{"table", "op", "pk", "old"}` entries, so it
    needs no change at all to consume this trimmed set instead of the whole thing.
    """
    if not decision_ids:
        return {}
    stmt = text(
        f"""
        SELECT id,
               COALESCE(jsonb_path_query_array(
                   undo_journal,
                   '$[*] ? (@.table == "{_DECISIONS_TABLE}" '
                   '&& (@.op == "insert" || @.op == "update"))'
               ), '[]'::jsonb) AS decision_entries,
               COALESCE(jsonb_path_query_array(
                   undo_journal,
                   '$[*] ? (@.table == "{_OI_ROWS_TABLE}")'
               ), '[]'::jsonb) AS row_entries,
               COALESCE(jsonb_path_query_array(
                   undo_journal,
                   '$[*] ? (@.table == "{_OI_LINKS_TABLE}" && @.op == "insert")'
               ), '[]'::jsonb) AS link_insert_entries
        FROM {_DECISIONS_TABLE}
        WHERE id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    rows = db.execute(stmt, {"ids": decision_ids}).mappings().all()

    out: Dict[str, list] = {}
    for row in rows:
        # `id` comes back as a native `uuid.UUID` here (a raw-SQL read of a real
        # Postgres `uuid` column, never routed through the ORM's `UUID(as_uuid=
        # False)` type) - stringified so it matches the plain `str` keys every
        # other caller in this module uses (`scalar_rows`' own `.id`, every journal
        # entry's own `pk`).
        out[str(row["id"])] = (
            list(row["decision_entries"] or [])
            + list(row["row_entries"] or [])
            + list(row["link_insert_entries"] or [])
        )
    return out


def board_undo_map(
    db: Session, adopted_by_so: Dict[str, Optional[str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """One `undo` per selected order, keyed the same way `adopted_by_so` is - by the
    CORE `sales_orders.id` - so `project_fulfilment_board_service.py` can read it
    straight into each `BoardOrderStanding` (plan "Undoable", AC-UC-15).

    Review round (N+1 finding): the board's own per-order facts (revision, confirmed
    at/by) are read as SCALAR COLUMNS, never the `undo_journal` JSONB - a board of
    fifty orders has no reason to pull fifty replay scripts into Python to answer
    "who confirmed this and when". `_grouped_refusals` needs only THREE kinds of
    entry out of a journal that can carry fifteen tables' worth of rows (`_pso_ids_
    by_decision`'s own `so_supply_decisions` inserts/updates, `_OI_ROWS_TABLE`'s own
    entries for the actioned check, `_OI_LINKS_TABLE`'s own insert set) - a follow-up
    review round has Postgres extract exactly those three, via `jsonb_path_query_
    array`, rather than deserialising the whole journal into Python only to filter
    it there. `undo_last_confirm` still loads the full journal - it replays it.
    """
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
            _journalled_decision_clause(),
        )
        .all()
    )
    if not scalar_rows:
        return {so_id: None for so_id in adopted_by_so}

    decision_ids = [row.id for row in scalar_rows]
    trimmed_journal_by_id = _trimmed_journal_entries(db, decision_ids)
    decision_stand_ins = [
        _JournalStandIn(
            id=row.id,
            project_sales_order_id=row.project_sales_order_id,
            confirmed_at=row.confirmed_at,
            undo_journal=trimmed_journal_by_id.get(row.id, []),
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
            # AC-R2-27: every entry this loop builds carries a real journal (the
            # `_journalled_decision_clause()` filter above), so `mode` is always
            # `journal` here. S5 adds a SECOND pass for journal-less decisions,
            # admin-gated, which sets `reconstructed` instead.
            "mode": "journal",
        }
    return out
