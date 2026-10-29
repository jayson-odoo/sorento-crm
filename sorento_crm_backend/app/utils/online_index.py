"""Build an index without ever stalling live work (GOODSCHAIN-INDEX-QUERY, BILLING-FROM-DOC-INDEX).

`documentation/plans/scm/PLAN-goodschain-index-query-27oct.md`. Owner requirement, 27 Oct 2026,
after slow migrations held deploys and the chatbot before (13 Oct, runbook
`documentation/runbooks/memory-and-deploy-guards.md` section 9):

* only `CREATE INDEX CONCURRENTLY`, outside a transaction: it never blocks reads or writes;
* the repo's migration limits (`app/utils/migration_timeouts.py`: lock_timeout 5s,
  statement_timeout 180s, MIGRATION_LOCK_TIMEOUT / MIGRATION_STATEMENT_TIMEOUT override), so
  the build gives up instead of queueing behind a long transaction or running past
  blue/green's 4-minute health wait;
* a build that times out or fails is NOT an error: the INVALID leftover is dropped
  (CONCURRENTLY, under the same limits), a WARNING is logged, and the caller carries on. A
  missing index is only today's speed.

Retry: `scripts/ensure_goods_chain_indexes.py`, which `start.sh` runs in the background on
every backend start, so the next deploy builds whatever the last one could not. It is a
catalog lookup and nothing else once every index here is VALID.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional, Sequence, Tuple

import sqlalchemy as sa

from app.utils.migration_timeouts import migration_timeouts

log = logging.getLogger(__name__)

#: (table, index, columns): both halves of the PO -> SPO key `goods_chain` joins on. Names and
#: shapes are prod's: `ix_spo_allocations_from_po_key` was built there by hand on 27 Oct.
GOODS_CHAIN_KEY_INDEXES: Tuple[Tuple[str, str, str], ...] = (
    (
        "spo_allocations",
        "ix_spo_allocations_from_po_key",
        "(from_po_number, btrim(from_po_line_ref), product_id, company_id)",
    ),
    (
        "purchase_order_lines",
        "ix_purchase_order_lines_src_key",
        "(btrim(source_ref), product_id, company_id)",
    ),
)

#: BILLING-FROM-DOC-INDEX: DOC-RELATIONS finds an SO's / DO's billing documents by the raw
#: `from_doc_no` (`app/services/document_relations.py` billing_ids_for_*); the company filter
#: there is on the joined header, so a plain single-column index. Schema-qualified table.
BILLING_FROM_DOC_INDEXES: Tuple[Tuple[str, str, str], ...] = (
    (
        "finance.billing_document_lines",
        "ix_finance_billing_document_lines_from_doc_no",
        "(from_doc_no)",
    ),
)

#: pg_try_advisory_lock key `ensure_indexes_online` takes, so two builders (the migration, the
#: retry, blue and green starting together) never build the same index at once.
ADVISORY_LOCK_KEY = 0x6763_6964_7830  # "gcidx0"


def index_valid(bind, table: str, name: str):
    """pg_index.indisvalid for the index on `table` (True / False), or None when there is none.
    Through the table, not to_regclass(name): an unqualified index name resolves along the
    search_path, so a same-named index in a later schema would answer for it."""
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = CAST(:table AS regclass) AND c.relname = :name"
        ),
        {"table": table, "name": name},
    ).scalar()


#: The least statement_timeout the leftover drop gets, however little of the budget is left.
DROP_FLOOR_MS = 5000
_UNIT_MS = {"ms": 1, "s": 1000, "min": 60_000, "h": 3_600_000, "": 1}


def duration_ms(value: str) -> int:
    """A `migration_timeouts` duration (5s, 2500ms, 30min, 0) in milliseconds; 0 = no limit."""
    number, unit = re.fullmatch(r"(\d+)(ms|s|min|h)?", value).groups()
    return int(number) * _UNIT_MS[unit or ""]


def _qualified(table: str, name: str) -> str:
    """`name` in `table`'s schema: an index lives in its table's schema, and an unqualified
    drop resolves along search_path, so it would miss one under `finance.`."""
    return f"{table.rsplit('.', 1)[0]}.{name}" if "." in table else name


def _set_limits(bind, lock: str, statement: str) -> None:
    bind.execute(sa.text(f"SET lock_timeout = '{lock}'"))
    bind.execute(sa.text(f"SET statement_timeout = '{statement}'"))


def ensure_index_online(
    bind, table: str, name: str, columns: str, *, budget_ms: Optional[int] = None
) -> bool:
    """True when a VALID `name` exists on `table` afterwards. `bind` must be in autocommit
    (an alembic `autocommit_block()`, or `isolation_level="AUTOCOMMIT"`): CONCURRENTLY refuses
    to run in a transaction. A VALID index is kept as it is; an INVALID one (an interrupted
    CONCURRENTLY build) is dropped and rebuilt. Any failure is logged and returns False.

    `budget_ms` (from `ensure_indexes_online`) caps the build's statement_timeout below the
    migration default, so several builds together still fit inside one default."""
    if index_valid(bind, table, name) is True:
        return True
    previous = (
        bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar(),
        bind.execute(sa.text("SELECT current_setting('statement_timeout')")).scalar(),
    )
    lock, statement = migration_timeouts()
    if budget_ms is not None:
        statement = f"{max(budget_ms, 1)}ms"
    _set_limits(bind, lock, statement)
    try:
        try:
            if index_valid(bind, table, name) is False:
                bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_qualified(table, name)}"))
            bind.execute(sa.text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {columns}"))
            if index_valid(bind, table, name) is True:
                return True
            reason = "the build finished but left it INVALID"
        except sa.exc.DBAPIError as exc:
            reason = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
        log.warning(
            "index %s on %s not built (%s); carrying on without it, at today's speed. "
            "The next backend start retries it (scripts/ensure_goods_chain_indexes.py).",
            name, table, reason,
        )
        if index_valid(bind, table, name) is False:
            try:
                if duration_ms(statement) and duration_ms(statement) < DROP_FLOOR_MS:
                    _set_limits(bind, lock, f"{DROP_FLOOR_MS}ms")
                bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_qualified(table, name)}"))
            except sa.exc.DBAPIError as exc:
                log.warning(
                    "INVALID index %s left in place (%s); the next retry drops it first.",
                    name, str(getattr(exc, "orig", exc)).strip().splitlines()[0],
                )
        return False
    finally:
        _set_limits(bind, *previous)


def ensure_indexes_online(bind, indexes: Sequence[Tuple[str, str, str]]) -> bool:
    """`ensure_index_online` for each, under `ADVISORY_LOCK_KEY`: the migration and the retry
    script, from any number of backends starting at once, never build at the same time (one
    would see the other's in-progress build as INVALID and drop it). A caller that does not
    get the lock skips with a WARNING; whoever holds it builds.

    All builds share ONE migration statement_timeout (180s by default): blue/green waits 4
    minutes for health, so two builds may not each take a full 180s. Each lock wait is still
    bounded by lock_timeout on top. An index the budget no longer reaches is skipped with a
    WARNING, for the retry. True when all are VALID afterwards."""
    if all(index_valid(bind, t, n) is True for t, n, _c in indexes):
        return True
    if not bind.execute(sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar():
        log.warning(
            "another backend is building the online indexes; leaving them to it "
            "(the next backend start retries whatever it does not finish)."
        )
        return False
    try:
        return _ensure_within_budget(bind, indexes)
    finally:
        bind.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


def _ensure_within_budget(bind, indexes: Sequence[Tuple[str, str, str]]) -> bool:
    total_ms = duration_ms(migration_timeouts()[1])
    deadline = time.monotonic() + total_ms / 1000 if total_ms else None
    results = []
    for table, name, columns in indexes:
        if deadline is None:
            results.append(ensure_index_online(bind, table, name, columns))
            continue
        left_ms = int((deadline - time.monotonic()) * 1000)
        if left_ms <= 0 and index_valid(bind, table, name) is not True:
            log.warning(
                "index %s on %s not built (the build budget is spent); the next backend "
                "start retries it (scripts/ensure_goods_chain_indexes.py).", name, table,
            )
            results.append(False)
            continue
        results.append(ensure_index_online(bind, table, name, columns, budget_ms=left_ms))
    return all(results)
