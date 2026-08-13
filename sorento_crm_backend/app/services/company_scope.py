"""Central, fail-closed company-scope enforcement.

Two SQLAlchemy events, registered ONCE at import time (via
``register_company_scope_listeners()`` called from ``app/main.py`` AND the worker
path) so BOTH the API process and the RQ worker enforce isolation — the worker
never runs ``main.py``'s ``startup_event``, so anything registered only there is
absent in the worker (mirrors ``lookup_write_listener``).

1. ``do_orm_execute`` (Session): injects a per-entity company predicate into
   every SELECT touching a ``CompanyScopedMixin`` model, reading the four-state
   scope from ``session.info['company_scope']``.
2. ``before_insert`` (Mapper): auto-stamps ``company_id`` from a single-company
   scope; rejects an owned insert that has no company to stamp (AC-D4).

Four-state scope (PLAN §3 F2):
  UNSET (default / absent) -> false()            -> 0 rows (fail-closed)
  None                     -> no predicate        -> all companies
  frozenset({ids})         -> company_id IN (ids)
  frozenset()  (empty)     -> false()            -> 0 rows (fail-closed)

Attachments (``__company_shared__``) are nullable/shared: under any non-None
scope the predicate is ``company_id IS NULL OR company_id IN (ids)`` and under
UNSET/empty it is ``company_id IS NULL`` — shared (form) attachments stay visible
by definition (AC-H5).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from sqlalchemy import event, false, or_
from sqlalchemy.orm import Mapper, ORMExecuteState, Session, object_session, with_loader_criteria
from sqlalchemy.sql import ColumnElement

from app.database import Base
from app.models.base import (
    UNSET,
    CompanyScope,
    CompanyScopedMixin,
    company_scope,
    get_company_scope,
    set_company_scope,
)
from app.services.error_handler import AppException

# Re-export the state helpers so callers can `from app.services.company_scope import ...`.
__all__ = [
    "UNSET",
    "CompanyScope",
    "CompanyScopedMixin",
    "company_scope",
    "get_company_scope",
    "set_company_scope",
    "register_company_scope_listeners",
    "build_company_predicate",
    "admin_listing_company_filter",
]


_INSTALLED = False
_SCOPED_CLASSES = None

# The incumbent company (Sorento), seeded with this fixed id by migration 302 and
# used as the DB DEFAULT by migration 306. A ``None``-scope (system / all-companies,
# e.g. an n8n X-API-Key call with no contact identity) owned-write is stamped with
# this so backward-compat write flows never hit the AC-D4 rejection.
DEFAULT_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# Test-only escape hatch (default OFF; NEVER set in production). The pre-isolation
# pytest suite seeds owned rows without a company_id and reads them back; those
# inserts would now be rejected by the auto-stamp under a non-single scope. When
# ``tests/conftest.py`` flips this on, an otherwise-rejected owned insert instead
# leaves ``company_id`` NULL (pre-isolation behaviour) so legacy tests behave as
# before. Production keeps this False → AC-D4 rejection stands. The dedicated
# ``test_company_scope`` rejection test clears it so it can still assert the raise.
_TEST_LEAVE_NULL_OWNED_INSERT = False


def _all_scoped_classes():
    """All mapped CompanyScopedMixin classes (cached). Used as the fallback target
    set when a statement hides its entities inside a subquery (e.g. ``.count()``,
    which reports an empty ``all_mappers``)."""
    global _SCOPED_CLASSES
    if _SCOPED_CLASSES is None:
        _SCOPED_CLASSES = [
            m.class_
            for m in Base.registry.mappers
            if isinstance(m.class_, type) and issubclass(m.class_, CompanyScopedMixin)
        ]
    return _SCOPED_CLASSES


def _is_shared(cls) -> bool:
    """Whether ``cls`` keeps a permanently-nullable/shared company_id (attachments)."""
    return bool(getattr(cls, "__company_shared__", False))


def build_company_predicate(cls, scope: CompanyScope) -> Optional[ColumnElement]:
    """Return the WHERE predicate for entity ``cls`` under ``scope`` (or None for
    "no predicate"). Exposed for the four-state unit test (AC-H3).

    Empty scope compiles to ``false()`` — never ``.in_([])`` (that footgun renders
    an always-false ``IN ()`` on some backends but is easy to break)."""
    shared = _is_shared(cls)

    if scope is None:
        return None
    # Everything left is UNSET or a frozenset. UNSET or an empty frozenset is
    # fail-closed: owned -> 0 rows; shared -> only the null (shared) rows.
    if not isinstance(scope, frozenset) or not scope:
        return cls.company_id.is_(None) if shared else false()

    # Non-empty frozenset of company ids.
    ids = list(scope)
    if shared:
        return or_(cls.company_id.is_(None), cls.company_id.in_(ids))
    return cls.company_id.in_(ids)


def admin_listing_company_filter(db, column) -> Optional[ColumnElement]:
    """Manual company filter for the superadmin/admin-only admin listings.

    Used by tables that carry a ``company_id`` but are DELIBERATELY NOT
    ``CompanyScopedMixin`` (``forms``, ``import_logs``, ``audit_logs``,
    ``import_jobs``) — other consumers of those tables (portal / workflow /
    public / worker reads) must keep working under ANY scope, so we never
    globally auto-filter them via ``do_orm_execute``. Instead each staff LISTING
    splices this predicate onto its own query by hand.

    Four-state — intentionally NOT fail-closed (unlike ``build_company_predicate``):
      None                    -> None (no predicate, all companies)
      frozenset({ids})        -> company_id IN (ids) OR company_id IS NULL
      UNSET / empty frozenset -> None (no predicate; role-gated fallback)

    Rationale for the UNSET/empty -> no-filter choice: these listings are already
    gated to superadmin/admin, and a superadmin always resolves to a
    single-company frozenset, so UNSET/empty should not occur here. If it somehow
    does, showing all rows (a role-gated admin can see everything anyway) is safer
    than hiding every row and looking broken. ``company_id IS NULL`` is always
    OR-ed in on the frozenset branch so legacy/unstamped rows stay visible.
    """
    scope = get_company_scope(db)
    if scope is None:
        return None
    # UNSET or an empty frozenset: no filter (superadmin-gated fallback).
    if not isinstance(scope, frozenset) or not scope:
        return None
    return or_(column.in_(list(scope)), column.is_(None))


# Kill-switch for the runtime enforcement (filter + auto-stamp). Default ON.
# ``COMPANY_SCOPE_ENFORCE=0`` disables both listeners — used ONLY to measure the
# pre-multi-company test baseline. The DB schema (NOT NULL + DEFAULT Sorento from
# migrations 305/306) is unaffected, so disabling this just reverts read/write
# behaviour to "all companies / DB-default company". Never set in production.
_ENFORCE = os.getenv("COMPANY_SCOPE_ENFORCE", "1") != "0"


_RAISE_ON_AMBIGUOUS = object()


def resolve_write_company_id(
    scope: CompanyScope, *, ambiguous: Any = _RAISE_ON_AMBIGUOUS
) -> Optional[str]:
    """The company an owned row being written belongs to, from the session scope.

    Extracted so a RAW-SQL insert into an owned table can stamp the same company the
    ORM `before_insert` hook would. Raw SQL bypasses that hook entirely, so an owned
    row inserted by hand lands with a NULL company_id and is then invisible to every
    scoped read - the failure looks like missing data, not like a missing stamp.

    ``ambiguous`` is what an UNSET / empty / multi-company scope resolves to. It raises
    by default, because a request that cannot name one company must not create an owned
    row. A caller that legitimately has no scope at all - a cron handler, which has no
    request and no principal - passes the company it means explicitly, at its own call
    site, where the choice is visible.
    """
    if isinstance(scope, frozenset) and len(scope) == 1:
        return next(iter(scope))
    # ``None`` = the deliberate system / all-companies principal; see the long note in
    # ``_stamp_company_id`` for why that write lands in the incumbent company.
    if scope is None:
        return DEFAULT_COMPANY_ID
    if ambiguous is not _RAISE_ON_AMBIGUOUS:
        return ambiguous
    if _TEST_LEAVE_NULL_OWNED_INSERT:
        return None
    raise AppException(
        status_code=400,
        message=(
            "Cannot create this record without an active company. "
            "A single active company is required to stamp company_id."
        ),
        code="company_scope_required",
    )


def register_company_scope_listeners() -> None:
    """Install the scope SELECT filter + insert auto-stamp. Idempotent."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    if not _ENFORCE:
        return

    @event.listens_for(Session, "do_orm_execute")
    def _apply_company_scope(state: ORMExecuteState) -> None:  # noqa: ANN001
        # Only top-level ORM SELECTs. Skip column/relationship sub-loads: the
        # parent row is already scoped and child tables carry their own
        # company_id, so a direct query on them (the IDOR path) is still covered.
        if not state.is_select or state.is_column_load or state.is_relationship_load:
            return

        scope = state.session.info.get("company_scope", UNSET)
        if scope is None:
            return  # all companies — add nothing

        targets = [
            m.class_
            for m in state.all_mappers
            if isinstance(m.class_, type) and issubclass(m.class_, CompanyScopedMixin)
        ]
        if not targets:
            # ``.count()`` and other subquery-wrapped statements report no
            # top-level mappers. Fall back to every scoped entity — with_loader_criteria
            # is a no-op for entities not present in the statement, so this stays
            # correct (just adds unused options to the less-frequent count path).
            targets = _all_scoped_classes()

        for cls in targets:
            predicate = build_company_predicate(cls, scope)
            if predicate is None:
                continue
            # Pass the CONCRETE predicate (not a lambda). A lambda triggers
            # SQLAlchemy's lambda-statement caching, which bakes the first scope's
            # STRUCTURE (false() vs IN vs IS NULL OR IN) and reuses it for other
            # scopes — silently leaking. A concrete clause becomes part of the
            # statement cache key, so each scope structure caches distinctly.
            # include_aliases still adapts the clause to aliased occurrences.
            state.statement = state.statement.options(
                with_loader_criteria(cls, predicate, include_aliases=True)
            )

    @event.listens_for(Mapper, "before_insert")
    def _stamp_company_id(mapper, connection, target) -> None:  # noqa: ANN001
        if not isinstance(target, CompanyScopedMixin):
            return
        if getattr(target, "company_id", None) is not None:
            return  # explicit company (imports, backfilled paths) — leave as-is
        if _is_shared(type(target)):
            return  # attachments may legitimately be company-less (shared)

        sess = object_session(target)
        scope = get_company_scope(sess) if sess is not None else UNSET

        # ``None`` = the deliberate system / all-companies principal (a valid
        # X-API-Key call with NO contact_id/space_id — the n8n backward-compat
        # path). Such a caller writing an owned row belongs to the INCUMBENT
        # company (Sorento) — this matches migration 306's DB DEFAULT and the
        # pre-multi-company behaviour where every write went to the single
        # company. Without this, n8n owned-writes (SPO / GRN / packing-list
        # creates that come in with no contact identity) would be rejected
        # → a backward-compat break. Reads under ``None`` already return all
        # companies; writes now land in the incumbent. A Mocha n8n flow that
        # must write Mocha data passes contact identity → single-company scope.
        #
        # UNSET (resolver never ran / unresolved contact) / empty / multi-company is
        # genuinely ambiguous, and raises: never insert an owned row with a null
        # company (AC-D4). ``_TEST_LEAVE_NULL_OWNED_INSERT`` is the test-only escape.
        company_id = resolve_write_company_id(scope)
        if company_id is not None:
            target.company_id = company_id
