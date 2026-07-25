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
