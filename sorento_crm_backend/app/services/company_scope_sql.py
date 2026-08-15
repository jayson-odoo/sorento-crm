"""Raw-SQL company-scope helper (multi-company data isolation).

The central ``do_orm_execute`` filter in ``app.services.company_scope`` only
covers ORM SELECTs — a raw ``text()`` statement bypasses it entirely. Any raw
query that touches an owned (``CompanyScopedMixin``) table must reproduce the
same four-state predicate by hand; this helper builds that WHERE fragment from
the session scope so the two enforcement paths can't drift.

Four-state (mirrors ``build_company_predicate``):
  None                     -> ("", {})                 no predicate (all companies)
  frozenset({ids})         -> ("company_id IN (:c0)", {"c0": id})
  UNSET / empty frozenset  -> ("1=0", {})              fail-closed (0 rows)

``shared=True`` mirrors ``__company_shared__`` (attachments): a NULL company_id
is always allowed, so UNSET/empty renders ``company_id IS NULL`` and a frozenset
renders ``(company_id IS NULL OR company_id IN (...))``.

SECOND IMPLEMENTATION, ON PURPOSE. This is NOT the only raw-SQL scope helper.
``app/services/entity_resolver.py`` defines a local ``_company_scope_sql`` and
applies it to its trigram / phrase probes. It is not a duplicate by accident and
it is not interchangeable with this one: it emits a LEADING-``AND`` fragment
(`` AND col::text = ANY(...)``, `` AND FALSE``) to splice onto an existing WHERE,
where this helper deliberately emits a bare boolean, and it has no ``shared=``
mode. Do not "unify" them without checking every splice site.

Recorded here because the split has already cost real time: a peer session
grepped for ``company_sql_predicate``, found no hit in ``entity_resolver.py``,
and reported a live cross-company leak in the resolver that had already been
fixed (709ef9910, 2026-08-07). Searching for THIS name does not prove a file is
unscoped. Grep for ``get_company_scope`` to find every enforcement path.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from app.models.base import get_company_scope


def company_sql_predicate(
    db,
    column: str = "company_id",
    *,
    shared: bool = False,
    param_prefix: str = "cscope",
) -> Tuple[str, Dict[str, Any]]:
    """Return an ``(sql_fragment, params)`` pair for the session's company scope.

    The fragment is a bare boolean expression (no leading ``AND``/``WHERE``) so
    callers splice it wherever they need. ``params`` are bind values to merge into
    the statement's parameter dict. An empty fragment (``""``) means "add nothing"
    (scope is None / all companies).
    """
    scope = get_company_scope(db)
    if scope is None:
        return "", {}
    # UNSET or an empty frozenset -> fail-closed. Shared tables keep NULL rows.
    if not isinstance(scope, frozenset) or not scope:
        return (f"{column} IS NULL", {}) if shared else ("1=0", {})

    ids = list(scope)
    names = [f"{param_prefix}{i}" for i in range(len(ids))]
    params: Dict[str, Any] = {name: value for name, value in zip(names, ids)}
    placeholders = ", ".join(f":{name}" for name in names)
    fragment = f"{column} IN ({placeholders})"
    if shared:
        fragment = f"({column} IS NULL OR {fragment})"
    return fragment, params
