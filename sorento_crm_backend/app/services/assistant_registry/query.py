"""`crm_query` and `crm_describe` over the registry (PLAN-ai-tools-standard-5nov.md section 2.2).

One ORM SELECT per call, built only from registered fields: no free SQL. Company isolation comes from the
session (`do_orm_execute`, stamped by the caller's `run_as_user`); this module adds what the registry states:
the view slug, own-row narrowing, the field allowlist, field slugs, the module switch and the screen's own
always-on clauses. Every refusal is a `QueryRefused` the caller turns into a plain tool result.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, cast, distinct, func, or_, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import DBAPIError

from app.services.assistant_registry import ENTITIES
from app.services.assistant_registry.types import EntityDef, FieldDef

MAX_ROWS = 50
MAX_GROUPS = 200
DEFAULT_ROWS = 20
STATEMENT_TIMEOUT_MS = 5000
MAX_HOPS = 2
MAX_GROUP_FIELDS = 4
MAX_FILTERS = 20
MAX_AGGREGATES = 8
MAX_IN_VALUES = 100
MAX_TEXT_CHARS = 200
#: The most columns a row result carries besides the record's name (crew pass on 74b6b751: a below-target answer
#: asked for 15). The rest are named in `columns_dropped`.
MAX_COLUMNS = 8
#: Naive timestamps are stored UTC; dates the user names are Malaysian dates.
LOCAL_TZ = "Asia/Kuala_Lumpur"

OPS = (
    "eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "between", "contains", "starts_with", "is_null", "is_not_null",
)
BUCKETS = ("day", "week", "month", "quarter", "year")
FNS = ("count", "count_distinct", "sum", "avg", "min", "max")
SPEC_KEYS = ("entity", "agent", "period", "fields", "filters", "group_by", "aggregates", "sort", "limit")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: A date as the answers write it (dd/mm/yyyy), accepted in a filter too.
_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MYT = dt.timezone(dt.timedelta(hours=8))
#: Postgres `query_canceled`: the statement timeout fired.
_QUERY_CANCELED = "57014"
#: Postgres class 22, data exception: a value that does not fit its field ("abc" for a number).
_DATA_EXCEPTION = "22"


class QueryRefused(Exception):
    """`code`: unknown_entity, unknown_field, restricted, no_access, own_only_unsupported, module_disabled,
    invalid, too_deep, timeout."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------ named date windows (crew pass on ffdd7f87)

#: Window names a date filter may carry instead of a date: the model passed "last_month" or "2026-10" as the
#: value and the call was refused ("needs a date"), a wasted round on every payout question.
WINDOW_NAMES = (
    "today", "yesterday", "this_week", "last_week", "this_month", "last_month",
    "this_quarter", "last_quarter", "this_year", "last_year",
)
_YEAR_MONTH = re.compile(r"^(\d{4})-(\d{1,2})$")
_MONTH_YEAR = re.compile(r"^(\d{1,2})/(\d{4})$")
_YEAR = re.compile(r"^(\d{4})$")
_QUARTER = re.compile(r"^(?:q([1-4])[\s_/-]*(\d{4})|(\d{4})[\s_/-]*q([1-4]))$")


def local_today() -> dt.date:
    """Today in Malaysia (the target service's own `_today`, so `USE_REMOTE_TIME` applies alike)."""
    from app.services.sales.team_service import _today

    return _today()


def _month_end(year: int, month: int) -> dt.date:
    first_next = dt.date(year + month // 12, month % 12 + 1, 1)
    return first_next - dt.timedelta(days=1)


def _quarter(year: int, quarter: int) -> tuple[dt.date, dt.date]:
    first = 3 * (quarter - 1) + 1
    return dt.date(year, first, 1), _month_end(year, first + 2)


def named_window(value: Any, today: dt.date | None = None) -> tuple[dt.date, dt.date] | None:
    """(first day, last day) of a window named by `value`: one of WINDOW_NAMES, a month ("2026-10", "10/2026"),
    a quarter ("Q3 2026", "2026-Q3") or a year ("2026"); None for anything else (a plain date included)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1900 <= value <= 2200:
        return dt.date(value, 1, 1), dt.date(value, 12, 31)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    words = re.sub(r"[\s-]+", "_", text)
    today = today or local_today()
    if words in WINDOW_NAMES:
        if words == "today":
            return today, today
        if words == "yesterday":
            day = today - dt.timedelta(days=1)
            return day, day
        if words in ("this_week", "last_week"):
            monday = today - dt.timedelta(days=today.weekday() + (7 if words == "last_week" else 0))
            return monday, monday + dt.timedelta(days=6)
        if words in ("this_month", "last_month"):
            first = today.replace(day=1)
            if words == "last_month":
                first = (first - dt.timedelta(days=1)).replace(day=1)
            return first, _month_end(first.year, first.month)
        if words in ("this_quarter", "last_quarter"):
            year, quarter = today.year, (today.month - 1) // 3 + 1
            if words == "last_quarter":
                year, quarter = (year - 1, 4) if quarter == 1 else (year, quarter - 1)
            return _quarter(year, quarter)
        year = today.year - (1 if words == "last_year" else 0)
        return dt.date(year, 1, 1), dt.date(year, 12, 31)
    found = _YEAR_MONTH.match(text) or _MONTH_YEAR.match(text)
    if found:
        year, month = (int(found.group(1)), int(found.group(2))) if found.re is _YEAR_MONTH else (
            int(found.group(2)), int(found.group(1))
        )
        if 1 <= month <= 12:
            return dt.date(year, month, 1), _month_end(year, month)
        return None
    found = _QUARTER.match(text)
    if found:
        quarter, year = (found.group(1), found.group(2)) if found.group(1) else (found.group(4), found.group(3))
        return _quarter(int(year), int(quarter))
    if _YEAR.match(text):
        return dt.date(int(text), 1, 1), dt.date(int(text), 12, 31)
    return None


def expand_window(item: Any, today: dt.date | None = None) -> Any:
    """A date filter whose value names a window, rewritten as dates: `eq last_month` is `between [first, last]`,
    `gte 2026-07` is from the first of July, `lte Q3 2026` to its last day. Anything else comes back as it was."""
    if not isinstance(item, dict):
        return item
    op, value = item.get("op"), item.get("value")
    if op == "between" and isinstance(value, list) and len(value) == 2:
        low, high = named_window(value[0], today), named_window(value[1], today)
        if low is None and high is None:
            return item
        return {**item, "value": [
            low[0].isoformat() if low else value[0], high[1].isoformat() if high else value[1],
        ]}
    window = named_window(value, today) if op in ("eq", "gte", "gt", "lte", "lt") else None
    if window is None:
        return item
    first, last = window
    if op == "eq":
        return {**item, "op": "between", "value": [first.isoformat(), last.isoformat()]}
    if op in ("gte", "lt"):
        return {**item, "value": first.isoformat()}
    return {**item, "op": "lte" if op == "lte" else "gt", "value": last.isoformat()}


# ------------------------------------------------------------------ an agent named in a filter (crew pass on ffdd7f87)

def _plain_text(value: Any) -> str:
    return " ".join(str(value or "").split()).lower()


def agent_exact(label: Any, needle: Any) -> bool:
    """Does `needle` name the agent printed as `label` ("CODE - Name") exactly: the code, the name or the label?
    "Agent B" names "AB - Agent B" and not "AB4 - Agent B IV", which `contains` also matched."""
    text, want = _plain_text(label), _plain_text(needle)
    if not text or not want:
        return False
    code, _sep, name = text.partition(" - ")
    return want in (text, code.strip(), name.strip())


def match_agents(db, value: str, op: str) -> list:
    """The sales agents a filter value names: exactly (code, name or "CODE - Name") when any agent is named
    exactly, else every agent whose code or name contains it (starts with it, for `starts_with`). Agents of the
    session's companies and the shared masters only, as `team_service._visible_agents` reads them."""
    from sqlalchemy import or_ as any_of

    from app.models.base import get_company_scope
    from app.models.sales_agent import SalesAgent
    from app.services.sales.team_service import agent_label

    q = db.query(SalesAgent)
    scope = get_company_scope(db)
    if scope is not None:
        companies = list(scope) if isinstance(scope, frozenset) else []
        q = q.filter(any_of(SalesAgent.company_id.is_(None), SalesAgent.company_id.in_(companies)))
    needle = _plain_text(value)
    pattern = f"%{_like(value, 'agent')}%" if op != "starts_with" else f"{_like(value, 'agent')}%"
    candidates = q.filter(
        any_of(SalesAgent.sales_agent.ilike(pattern, escape="\\"), SalesAgent.description.ilike(pattern, escape="\\"),
               (SalesAgent.sales_agent + " - " + func.coalesce(SalesAgent.description, "")).ilike(pattern, escape="\\"))
    ).order_by(SalesAgent.sales_agent).all()
    exact = [a for a in candidates if agent_exact(agent_label(a), needle)]
    return exact if exact or op == "eq" else candidates


# ------------------------------------------------------------------ access


#: A field or aggregate gated by a reveal key, not a slug: `reveal:sales_orders.sales_report`.
REVEAL = "reveal:"
SALES_REPORT = REVEAL + "sales_orders.sales_report"
OUTSTANDING = REVEAL + "sales_orders.outstanding"


def _slugs(db, user_id: str) -> set[str]:
    """The user's slugs, plus `reveal:<key>` for every reveal key their slugs answer (`staff_reveal_keys`, the
    sales report route's staff gate, `api/v1/order_management/report_ask.py`)."""
    from app.services.contact_field_reveal_service import staff_reveal_keys
    from app.services.user_service import UserPermissionService

    held = set(UserPermissionService(db).get_user_permission_slugs(str(user_id)))
    return held | {REVEAL + key for key in staff_reveal_keys(db, str(user_id))}


def require_aggregate(entity: EntityDef, slugs: set[str], grouped: bool) -> None:
    """Totals and rankings follow the sales report's gate (`EntityDef.aggregate_permission`)."""
    if grouped and entity.aggregate_permission and entity.aggregate_permission not in slugs:
        raise QueryRefused(
            "restricted",
            f"Totals of {entity.label.lower()} need the sales report, which is not enabled for this user; "
            "list the records instead.",
        )


def _module_blocked(db, user_id: str, module: str) -> bool:
    from app.modules.runtime import guards

    return guards.module_blocked(db, str(user_id), module)


def _readable(entity: EntityDef, slugs: set[str]) -> str | None:
    """"all", "own" or None: how much of the entity this holder of `slugs` may read."""
    if entity.view_permission is None:
        return None
    if entity.view_permission in slugs:
        return "all"
    if entity.own_permission and entity.own_permission in slugs:
        return "own"
    return None


def _entity_for(db, user_id: str, key: Any, slugs: set[str], panel: bool) -> tuple[EntityDef, bool]:
    """The entity and whether only the user's own rows are readable, after every entity-level refusal."""
    entity = ENTITIES.get(key) if isinstance(key, str) else None
    if entity is None or entity.view_permission is None:
        known = ", ".join(sorted(k for k, e in ENTITIES.items() if _readable(e, slugs)))
        raise QueryRefused("unknown_entity", f"Unknown entity {key!r}. Entities you may read: {known or 'none'}.")
    reach = _readable(entity, slugs)
    if reach is None:
        raise QueryRefused("no_access", f"{entity.label} are outside this user's access.")
    if reach == "own" and entity.own_clause is None:
        raise QueryRefused(
            "own_only_unsupported", f"This user may see only their own {entity.label.lower()}, which this tool cannot narrow to."
        )
    if entity.panel_only and not panel:
        raise QueryRefused("restricted", entity.panel_only)
    if _module_blocked(db, user_id, entity.module):
        raise QueryRefused("module_disabled", f"The {entity.label} module is not enabled.")
    if entity.brand_blind and _brand_scoped(db):
        raise QueryRefused(
            "restricted", f"{entity.label} cover every brand, so they are not shown for this contact's brands."
        )
    return entity, reach == "own"


def _brand_scoped(db) -> bool:
    from app.models.base import get_brand_scope

    return bool(get_brand_scope(db))


# ------------------------------------------------------------------ fields and paths


def _kind(column) -> str:
    kind = column.type
    if isinstance(kind, Boolean):
        return "boolean"
    if isinstance(kind, DateTime):
        return "datetime"
    if isinstance(kind, Date):
        return "date"
    if isinstance(kind, (Numeric, Float, Integer)):
        return "number"
    if isinstance(kind, (String, Text)):
        return "text"
    return "other"


def _company_clause(db, model, table):
    """The session's company predicate for `model`, written against `table` (the model's table or an alias of
    it); None for a model that is not company scoped or a session scoped to every company. Stated explicitly
    because the session's automatic criterion is not adapted to a table alias inside a join, and is not
    attached at all when no column of the root entity is selected (a group on a relation field only)."""
    from sqlalchemy.sql.util import ClauseAdapter

    from app.models.base import CompanyScopedMixin, get_company_scope
    from app.services.company_scope import build_company_predicate

    if not (isinstance(model, type) and issubclass(model, CompanyScopedMixin)):
        return None
    predicate = build_company_predicate(model, get_company_scope(db))
    if predicate is None or table is model.__table__:
        return predicate
    return ClauseAdapter(table).traverse(predicate)


class _Paths:
    """Turns dotted field paths into columns, joining each declared relation once (outer join, on a plain
    table alias carrying the company predicate in its ON clause)."""

    def __init__(self, db, user_id: str, entity: EntityDef, slugs: set[str]) -> None:
        from app.models.base import get_brand_scope

        self.db = db
        self.user_id = user_id
        self.entity = entity
        self.slugs = slugs
        self.brand_scoped = bool(get_brand_scope(db))
        self._aliases: dict[str, Any] = {}
        self.joins: list[tuple[Any, Any]] = []
        #: Said with the result: which agents a filter named (`match_agents`).
        self.notes: list[str] = []

    def _target(self, path: Any) -> tuple[EntityDef, Any, str]:
        if not isinstance(path, str) or not path.strip():
            raise QueryRefused("invalid", "A field must be a name such as `status` or `supplier.name`.")
        parts = path.strip().split(".")
        if len(parts) - 1 > MAX_HOPS:
            raise QueryRefused("too_deep", f"`{path}` goes through {len(parts) - 1} relations; at most {MAX_HOPS}.")
        entity, table, prefix = self.entity, self.entity.model.__table__, ""
        self.lookup_only = False
        for name in parts[:-1]:
            if self.lookup_only:
                raise QueryRefused("restricted", f"`{path}` goes through {entity.label.lower()}, which this user may not list.")
            if name not in entity.relations:
                raise QueryRefused(
                    "unknown_field",
                    f"`{name}` is not a relation of {entity.label.lower()}. Relations: {', '.join(entity.relations) or 'none'}.",
                )
            target_key, fk = entity.relations[name]
            target = ENTITIES[target_key]
            prefix = f"{prefix}.{name}" if prefix else name
            if prefix not in self._aliases:
                if _module_blocked(self.db, self.user_id, target.module):
                    raise QueryRefused("module_disabled", f"The {target.label} module is not enabled.")
                alias = target.model.__table__.alias()
                onclause = alias.c.id == table.c[fk]
                company = _company_clause(self.db, target.model, alias)
                if company is not None:
                    onclause = onclause & company
                self._aliases[prefix] = alias
                self.joins.append((alias, onclause))
            entity, table = target, self._aliases[prefix]
            # A related record with a list screen of its own (customers) is a lookup to someone without that
            # screen's slug: the fields it is named by, and nothing past it (security review, wave 2).
            self.lookup_only = target.view_permission is not None and _readable(target, self.slugs) is None
        return entity, table, parts[-1]

    def resolve(self, path: Any) -> tuple[Any, FieldDef, str]:
        """(column expression, field, kind). Raises for an unknown or restricted field."""
        entity, table, name = self._target(path)
        field = entity.fields.get(name)
        if field is None:
            raise QueryRefused(
                "unknown_field", f"`{path}` is not a readable field. Fields of {entity.label.lower()}: {', '.join(entity.fields)}."
            )
        if field.permission and field.permission not in self.slugs:
            raise QueryRefused("restricted", f"`{path}` is restricted for this user.")
        if self.lookup_only and name not in entity.name_by:
            raise QueryRefused("restricted", f"`{path}` is restricted for this user.")
        if field.whole_document and self.brand_scoped:
            raise QueryRefused(
                "restricted", f"`{path}` covers lines of brands outside this contact's brands, so it is not shown here."
            )
        if field.expr is not None:
            if table is not entity.model.__table__:
                # The service's expression correlates to the model itself, not to a join alias.
                raise QueryRefused("invalid", f"`{path}` is read on {entity.label.lower()} itself, not through a relation.")
            column = field.expr()
            return column, field, _kind(column)
        column = table.c[field.column or name]
        return column, field, _kind(column)

    def allowed(self, path: str) -> bool:
        """Is the (known) field readable by this user? Unknown fields still raise."""
        try:
            self.resolve(path)
        except QueryRefused as exc:
            if exc.code == "restricted":
                return False
            raise
        return True


def _local(column, kind: str):
    """A timestamp as Malaysian wall time; a date as it is."""
    if kind == "datetime":
        return func.timezone(LOCAL_TZ, func.timezone("UTC", column))
    return column


# ------------------------------------------------------------------ filters


def _scalar(value: Any, path: str, kind: str = "") -> Any:
    if isinstance(value, str) and kind in ("date", "datetime"):
        found = _DMY.match(value.strip())
        if found:
            day, month, year = found.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise QueryRefused("invalid", f"The value for `{path}` must be text, a number, true/false or a list of those.")


def _next_day(value: Any) -> dt.date | None:
    if isinstance(value, str) and _DATE_ONLY.match(value):
        try:
            return dt.date.fromisoformat(value) + dt.timedelta(days=1)
        except ValueError:
            return None
    return None


def _like(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryRefused("invalid", f"`contains` and `starts_with` on `{path}` need text.")
    if len(value) > MAX_TEXT_CHARS:
        raise QueryRefused("invalid", f"The text for `{path}` is longer than {MAX_TEXT_CHARS} characters.")
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filter(paths: _Paths, item: Any):
    if not isinstance(item, dict) or set(item) - {"field", "op", "value"}:
        raise QueryRefused("invalid", "Each filter is {field, op, value}.")
    path, op = item.get("field"), item.get("op")
    column, field, kind = paths.resolve(path)
    if op not in OPS:
        raise QueryRefused("invalid", f"Unknown op {op!r}. Ops: {', '.join(OPS)}.")
    value = item.get("value")
    if op == "is_null":
        return column.is_(None)
    if op == "is_not_null":
        return column.is_not(None)
    if callable(field.agent_id) and op in ("eq", "contains", "starts_with") and isinstance(value, str) and value.strip():
        # The agent the value names, by the record's own agent link (the agent's Customers tab is
        # `Customer.sales_agent_id ==`): exactly when one is named exactly, so "Agent B" is not also "Agent B IV".
        agents = match_agents(paths.db, value, op)
        if agents:
            from app.services.sales.team_service import agent_label

            labels = [agent_label(a) for a in agents]
            shown = ", ".join(labels[:5]) + (f" and {len(labels) - 5} more" if len(labels) > 5 else "")
            paths.notes.append(f"Agent{'s' if len(labels) > 1 else ''}: {shown}.")
            return field.agent_id().in_([a.id for a in agents])
        # No agent master matches (a code as AutoCount sent it): the text itself, as before.
    if op in ("contains", "starts_with"):
        if kind != "text":
            raise QueryRefused("invalid", f"`{op}` works on text fields; `{path}` is {kind}.")
        needle = _like(value, path)
        pattern = f"%{needle}%" if op == "contains" else f"{needle}%"
        return column.ilike(pattern, escape="\\")
    # A timestamp is compared as Malaysian wall time; a date-only value on it names the whole Malaysian day.
    local = _local(column, kind)
    day = kind == "datetime"
    if op in ("in", "not_in"):
        if not isinstance(value, list) or not value or len(value) > MAX_IN_VALUES:
            raise QueryRefused("invalid", f"`{op}` on `{path}` needs a list of 1 to {MAX_IN_VALUES} values.")
        values = [_scalar(v, path, kind) for v in value]
        if day and all(_next_day(v) for v in values):
            matched = or_(*((local >= v) & (local < _next_day(v)) for v in values))
            return matched if op == "in" else ~matched
        return local.in_(values) if op == "in" else local.not_in(values)
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise QueryRefused("invalid", f"`between` on `{path}` needs [from, to].")
        low, high = (_scalar(v, path, kind) for v in value)
        upper = _next_day(high) if day else None
        return (local >= low) & (local < upper if upper is not None else local <= high)
    value = _scalar(value, path, kind)
    if value is None:
        raise QueryRefused("invalid", f"`{op}` on `{path}` needs a value; use is_null for an empty one.")
    after = _next_day(value) if day else None
    if op == "eq":
        return (local >= value) & (local < after) if after is not None else local == value
    if op == "ne":
        return ~((local >= value) & (local < after)) if after is not None else local != value
    if op == "lt":
        return local < value
    if op == "lte":
        return local < after if after is not None else local <= value
    if op == "gt":
        return local >= after if after is not None else local > value
    return local >= value  # gte


# ------------------------------------------------------------------ spec


def _list(spec: dict, key: str, cap: int | None = None) -> list:
    value = spec.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise QueryRefused("invalid", f"`{key}` must be a list.")
    if cap is not None and len(value) > cap:
        raise QueryRefused("invalid", f"`{key}` takes at most {cap} items.")
    return value


def _limit(spec: dict, cap: int, default: int) -> int:
    raw = spec.get("limit")
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise QueryRefused("invalid", "`limit` must be a whole number from 1.")
    return min(raw, cap)


def _plain(value: Any) -> Any:
    """A value as the answer shows it: a date as dd/mm/yyyy, a stored (naive UTC) timestamp as Malaysian
    dd/mm/yyyy hh:mm (owner ruling, 5 Nov)."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(_MYT).strftime("%d/%m/%Y %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%d/%m/%Y")
    return value


def _sort_dir(item: dict) -> str:
    direction = (item.get("dir") or "asc").lower() if isinstance(item.get("dir") or "asc", str) else None
    if direction not in ("asc", "desc"):
        raise QueryRefused("invalid", "A sort's dir is asc or desc.")
    return direction


def _sort_items(spec: dict) -> list[dict]:
    items = _list(spec, "sort", 4)
    for item in items:
        if not isinstance(item, dict) or set(item) - {"field", "dir"} or not isinstance(item.get("field"), str):
            raise QueryRefused("invalid", "Each sort is {field, dir}.")
    return items


# ------------------------------------------------------------------ running


def _execute(db, stmt):
    return db.execute(stmt).all()


def _run(db, stmt) -> list:
    """`stmt` under the statement timeout (`timed`)."""
    return timed(db, lambda: _execute(db, stmt))


def timed(db, work):
    """`work()` under the statement timeout, inside a savepoint: a timeout rolls back to it (and with it the
    `SET LOCAL`), so the caller's transaction stays usable. Also wraps a computed entity's service call."""
    savepoint = db.begin_nested()
    try:
        previous = db.execute(text("SHOW statement_timeout")).scalar() or "0"
        db.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
        rows = work()
        db.execute(text("SELECT set_config('statement_timeout', :v, true)"), {"v": str(previous)})
    except DBAPIError as exc:
        savepoint.rollback()
        if getattr(getattr(exc, "orig", None), "pgcode", None) == _QUERY_CANCELED:
            raise QueryRefused(
                "timeout", "The question took too long to answer. Narrow it with a filter (a date range, a status)."
            ) from exc
        if str(getattr(getattr(exc, "orig", None), "pgcode", "") or "").startswith(_DATA_EXCEPTION):
            raise QueryRefused("invalid", "A filter value does not fit its field (a date is YYYY-MM-DD).") from exc
        raise
    except BaseException:
        if savepoint.is_active:
            savepoint.rollback()
        raise
    savepoint.commit()
    return rows


def _base(db, user_id: str, entity: EntityDef, own_only: bool, stmt, paths: _Paths):
    root = entity.model
    for alias, onclause in paths.joins:
        stmt = stmt.outerjoin(alias, onclause)
    company = _company_clause(db, root, root.__table__)
    if company is not None:
        stmt = stmt.where(company)
    brands = _brand_clause(db, root)
    if brands is not None:
        stmt = stmt.where(brands)
    if entity.scope is not None:
        for clause in entity.scope(db, user_id):
            stmt = stmt.where(clause)
    if own_only:
        from app.services.own_scope import me

        stmt = stmt.where(entity.own_clause(me(db, user_id)))
    return stmt


def _brand_clause(db, root):
    """A brand-scoped contact's products (`contact_brand_scope.brand_predicate`), stated for the root as the
    company predicate is."""
    from app.models.base import get_brand_scope
    from app.models.product import Product

    scope = get_brand_scope(db)
    if not scope or root is not Product:
        return None
    from app.services.contact_brand_scope import brand_predicate

    return brand_predicate(scope, Product.brand_id, Product.company_id, Product.item_class_id)


def run_query(db, user_id: str, spec: Any, *, panel: bool = False) -> dict:
    """Rows or groups of one registered entity, as `user_id` may see them. The session's company scope must
    already be the user's (`run_as_user`). `panel`: a staff panel turn (`EntityDef.panel_only`); fails closed."""
    if not isinstance(spec, dict):
        raise QueryRefused("invalid", "The query must be an object.")
    unknown = sorted(str(k) for k in spec if k not in SPEC_KEYS)
    if unknown:
        raise QueryRefused("invalid", f"Unknown key(s): {', '.join(unknown)}. Keys: {', '.join(SPEC_KEYS)}.")
    slugs = _slugs(db, user_id)
    entity, own_only = _entity_for(db, user_id, spec.get("entity"), slugs, panel)
    spec = shorthands(entity, spec)
    if entity.compute is not None:
        from app.services.assistant_registry.computed import run_computed

        return run_computed(db, user_id, entity, own_only, slugs, spec)
    paths = _Paths(db, user_id, entity, slugs)
    today = local_today()
    asked = [_named_dates(paths, f, today) for f in _list(spec, "filters", MAX_FILTERS)]
    filters = [_filter(paths, f) for f in asked]
    named = {f.get("field") for f in asked if isinstance(f, dict)}
    notes = []
    for field, op, value, note in entity.default_filters:
        if field not in named:
            filters.append(_filter(paths, {"field": field, "op": op, "value": value}))
            notes.append(note)
        elif any(isinstance(f, dict) and f.get("field") == field and f.get("op") == op and f.get("value") == value
                 for f in asked):
            notes.append(note)  # the query asked for the same exclusion itself: it is still said
    period = _period_display(paths, asked)
    group_by = _list(spec, "group_by", MAX_GROUP_FIELDS)
    aggregates = _list(spec, "aggregates", MAX_AGGREGATES)
    require_aggregate(entity, slugs, bool(group_by or aggregates))
    if group_by or aggregates:
        if _list(spec, "fields"):
            raise QueryRefused("invalid", "`fields` lists rows; with group_by or aggregates leave it out.")
        out = _groups(db, user_id, entity, own_only, paths, filters, group_by, aggregates, spec)
    else:
        out = _rows(db, user_id, entity, own_only, paths, filters, spec)
    # Display facts decided here, not by the model (crew pass, 5 Nov): the period in dd/mm/yyyy and what the
    # result leaves out. `loop.final_reply` puts the scope note in the reply when the model does not.
    if (group_by or aggregates) and entity.aggregate_note:
        notes.insert(0, entity.aggregate_note)
    notes = [*paths.notes, *notes]
    out["period_display"] = period
    out["scope_note"] = " ".join(notes) or None
    return out


def _display_date(value: Any, kind: str) -> str:
    iso = _scalar(value, "", kind)
    if isinstance(iso, str) and _DATE_ONLY.match(iso):
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    return str(value)


def shorthands(entity: EntityDef, spec: dict) -> dict:
    """`agent` and `period` as their filters (crew live x3 on 3c6924bf: the model resolved the agent's name with
    crm_resolve first and read crm_describe for the window, one or two extra model calls of ~20k tokens each).

    `agent`: the agent as the user named it, on the entity's agent field (`FieldDef.agent_id`), matched exactly
    first (`match_agents`, `computed._exact_agents`), so no id and no resolve round. `period`: a window name
    (last_month, this_quarter, 2026-10, Q3 2026, 2026) or [from, to] (either end may be a name or "today"), on the
    entity's own date (`window_field`, else `date_field`)."""
    if "agent" not in spec and "period" not in spec:
        return spec
    spec = dict(spec)
    filters = list(_list(spec, "filters", MAX_FILTERS))
    agent = spec.pop("agent", None)
    if agent is not None:
        field = next((key for key, f in entity.fields.items() if f.agent_id), None)
        if field is None:
            raise QueryRefused("invalid", f"`agent` does not apply to {entity.label.lower()}; use filters.")
        if not isinstance(agent, str) or not agent.strip():
            raise QueryRefused("invalid", "`agent` is the agent's code or name as text.")
        # A computed field holds teams and dealers too (`target_list.subject`): exactly that agent, or nothing and
        # the values that do exist (`computed._no_match`), never a team whose name contains it (review round 9).
        op = "contains" if callable(entity.fields[field].agent_id) else "eq"
        filters.append({"field": field, "op": op, "value": agent.strip()})
    period = spec.pop("period", None)
    if period is not None:
        field = entity.window_field or entity.date_field
        if field is None:
            raise QueryRefused("invalid", f"`period` does not apply to {entity.label.lower()}; use filters.")
        if isinstance(period, list) and len(period) == 2:
            filters.append({"field": field, "op": "between", "value": period})
        elif isinstance(period, (str, int)) and not isinstance(period, bool):
            filters.append({"field": field, "op": "eq", "value": period})
        else:
            raise QueryRefused("invalid", "`period` is a window name (last_month, 2026-10, Q3 2026) or [from, to].")
    if len(filters) > MAX_FILTERS:
        raise QueryRefused("invalid", f"`filters` takes at most {MAX_FILTERS} items.")
    spec["filters"] = filters
    return spec


def _named_dates(paths: _Paths, item: Any, today: dt.date) -> Any:
    """A filter on a date field whose value names a window (`named_window`) as dates; anything else as it was."""
    if not isinstance(item, dict) or not isinstance(item.get("field"), str):
        return item
    expanded = expand_window(item, today)
    if expanded is item:
        return item
    _column, _field, kind = paths.resolve(item["field"])
    return expanded if kind in ("date", "datetime") else item


def _period_display(paths: _Paths, asked: list) -> str | None:
    """The date window the query's own filters set, as a person reads it: "Order date 01/10/2026 to 31/10/2026"."""
    windows: dict[str, dict[str, str]] = {}
    for item in asked:
        if not isinstance(item, dict) or item.get("op") not in ("between", "eq", "gte", "gt", "lte", "lt"):
            continue
        _column, field, kind = paths.resolve(item.get("field"))
        if kind not in ("date", "datetime"):
            continue
        window = windows.setdefault(field.label, {})
        value, op = item.get("value"), item["op"]
        if op == "between" and isinstance(value, list) and len(value) == 2:
            window["from"], window["to"] = _display_date(value[0], kind), _display_date(value[1], kind)
        elif op == "eq":
            window["from"] = window["to"] = _display_date(value, kind)
        elif op in ("gte", "gt"):
            window["from"] = _display_date(value, kind) + (" (after)" if op == "gt" else "")
        else:
            window["to"] = _display_date(value, kind) + (" (before)" if op == "lt" else "")
    parts = []
    for label, window in windows.items():
        low, high = window.get("from"), window.get("to")
        if low and high:
            parts.append(f"{label} {low}" if low == high else f"{label} {low} to {high}")
        elif low:
            parts.append(f"{label} from {low}")
        elif high:
            parts.append(f"{label} up to {high}")
    return "; ".join(parts) or None


def _rows(db, user_id, entity, own_only, paths, filters, spec) -> dict:
    asked = _list(spec, "fields", 30)
    if any(not isinstance(f, str) for f in asked):
        raise QueryRefused("invalid", "`fields` is a list of field names.")
    picked = list(dict.fromkeys(asked or entity.list_fields or list(entity.fields)))
    dropped = picked[MAX_COLUMNS:] if asked else []
    wanted = list(dict.fromkeys([*entity.name_by, *(picked[:MAX_COLUMNS] if asked else picked)]))
    shown = [f for f in wanted if paths.allowed(f)]
    restricted = [f for f in wanted if f not in shown]
    root = entity.model
    columns = [root.id.label("id")] + [paths.resolve(f)[0].label(f) for f in shown]
    # Every path is resolved before the joins are added, so a relation named only in `sort` is joined too.
    order = []
    for item in _sort_items(spec):
        column = paths.resolve(item["field"])[0]
        order.append(column.desc().nulls_last() if _sort_dir(item) == "desc" else column.asc().nulls_last())
    if not order and hasattr(root, "created_at"):
        order.append(root.created_at.desc())
    order.append(root.id.asc())
    total = func.count().over().label("__total")
    stmt = select(*columns, total).select_from(root)
    stmt = _base(db, user_id, entity, own_only, stmt, paths)
    for clause in filters:
        stmt = stmt.where(clause)
    limit = _limit(spec, MAX_ROWS, DEFAULT_ROWS)
    rows = _run(db, stmt.order_by(*order).limit(limit))
    total_rows = int(rows[0]._mapping["__total"]) if rows else 0
    out_rows = []
    for row in rows:
        data = row._mapping
        item = {"id": str(data["id"])}
        if entity.screen_path:
            item["link"] = entity.screen_path.format(id=data["id"])
        # One display field per record, "CODE: Name", in place of the separate code and name (crew pass, 5 Nov:
        # the model showed the code and dropped the name). The name_by fields still filter and sort.
        parts = [str(_plain(data[f])) for f in entity.name_by if f in shown and data[f] not in (None, "")]
        if parts:
            item["label"] = parts[0] if len(parts) == 1 else f"{parts[0]}: {' '.join(parts[1:])}"
        item.update({f: _plain(data[f]) for f in shown if f not in entity.name_by})
        out_rows.append(item)
    columns = ([{"key": "label", "label": entity.label}] if any(f in shown for f in entity.name_by) else []) + [
        {"key": f, "label": paths.resolve(f)[1].label} for f in shown if f not in entity.name_by
    ]
    out = {
        "entity": entity.key, "rows": out_rows, "total": total_rows, "truncated": total_rows > len(out_rows),
        "restricted": restricted, "columns": columns,
    }
    if dropped:
        out["columns_dropped"] = dropped
    return out


def _group_key(paths: _Paths, item: Any) -> tuple[str, Any, str]:
    """(name, expression, column label)."""
    if isinstance(item, str):
        column, field, _kind = paths.resolve(item)
        return item, column, field.label
    if isinstance(item, dict) and not (set(item) - {"field", "bucket"}):
        path, bucket = item.get("field"), item.get("bucket")
        column, field, kind = paths.resolve(path)
        if bucket is None:
            return path, column, field.label
        if bucket not in BUCKETS:
            raise QueryRefused("invalid", f"Unknown bucket {bucket!r}. Buckets: {', '.join(BUCKETS)}.")
        if kind not in ("date", "datetime"):
            raise QueryRefused("invalid", f"A bucket needs a date field; `{path}` is {kind}.")
        expr = cast(func.date_trunc(bucket, _local(column, kind)), Date)
        return f"{path}_{bucket}", expr, f"{field.label} ({bucket} starting)"
    raise QueryRefused("invalid", "Each group_by item is a field name or {field, bucket}.")


_FN_WORDS = {"count": "Count of", "count_distinct": "Distinct", "sum": "Total", "avg": "Average", "min": "Lowest", "max": "Highest"}


def _aggregate(paths: _Paths, item: Any, entity: EntityDef) -> tuple[str, Any, str]:
    """(alias, expression, column label)."""
    if not isinstance(item, dict) or set(item) - {"fn", "field"}:
        raise QueryRefused("invalid", "Each aggregate is {fn, field}.")
    fn, path = item.get("fn"), item.get("field")
    if fn not in FNS:
        raise QueryRefused("invalid", f"Unknown fn {fn!r}. Fns: {', '.join(FNS)}.")
    if fn == "count" and path is None:
        return "count", func.count(), entity.label
    column, field, kind = paths.resolve(path)
    alias = f"{fn}_{path.replace('.', '_')}"
    label = f"{_FN_WORDS[fn]} {field.label.lower()}"
    if fn == "sum" and field.label.lower().startswith("total"):
        label = field.label  # "Total", not "Total total"
    if fn in ("sum", "avg") and kind != "number":
        raise QueryRefused("invalid", f"`{fn}` needs a number field; `{path}` is {kind}.")
    if fn == "count":
        return alias, func.count(column), label
    if fn == "count_distinct":
        return alias, func.count(distinct(column)), label
    return alias, getattr(func, fn)(column), label


def _groups(db, user_id, entity, own_only, paths, filters, group_by, aggregates, spec) -> dict:
    key_rows = [_group_key(paths, g) for g in group_by]
    agg_rows = [_aggregate(paths, a, entity) for a in (aggregates or [{"fn": "count"}])]
    keys = [(name, expr) for name, expr, _label in key_rows]
    names = [k for k, _ in keys] + [a for a, _e, _l in agg_rows]
    if len(set(names)) != len(names):
        raise QueryRefused("invalid", "Two groups or aggregates share a name; name each once.")
    root = entity.model
    labelled = {name: expr for name, expr, _label in [*key_rows, *agg_rows]}
    total = func.count().over().label("__total")
    stmt = select(*(expr.label(name) for name, expr in labelled.items()), total).select_from(root)
    stmt = _base(db, user_id, entity, own_only, stmt, paths)
    for clause in filters:
        stmt = stmt.where(clause)
    if keys:
        stmt = stmt.group_by(*(expr for _, expr in keys))
    order = []
    for item in _sort_items(spec):
        if item["field"] not in labelled:
            raise QueryRefused("invalid", f"Sort by a group or aggregate: {', '.join(labelled)}.")
        expr = labelled[item["field"]]
        order.append(expr.desc().nulls_last() if _sort_dir(item) == "desc" else expr.asc().nulls_last())
    order += [expr.asc().nulls_last() for _, expr in keys]
    if order:
        stmt = stmt.order_by(*order)
    limit = _limit(spec, MAX_GROUPS, MAX_GROUPS)
    rows = _run(db, stmt.limit(limit))
    total_groups = int(rows[0]._mapping["__total"]) if rows and keys else len(rows)
    groups = [{name: _plain(row._mapping[name]) for name in labelled} for row in rows]
    truncated = total_groups > len(groups)
    # Column totals of the counts and sums, over every group (only when none was cut off).
    totals = {}
    if keys and not truncated:
        for alias, _expr, _label in agg_rows:
            if alias == "count" or alias.startswith(("count_", "sum_")):
                totals[alias] = round(sum(float(g[alias] or 0) for g in groups), 2)
                if alias == "count" or alias.startswith("count_"):
                    totals[alias] = int(totals[alias])
    return {
        "entity": entity.key, "groups": groups, "total_groups": total_groups, "truncated": truncated,
        "columns": [{"key": name, "label": label, "group": True} for name, _expr, label in key_rows]
        + [{"key": alias, "label": label} for alias, _expr, label in agg_rows],
        "totals": totals,
    }


# ------------------------------------------------------------------ describe


def _field_rows(entity: EntityDef, slugs: set[str], brand_scoped: bool) -> list[dict]:
    columns = sa_inspect(entity.model).columns
    out = []
    for key, field in entity.fields.items():
        if field.kind:
            kind = field.kind
        elif field.expr is not None:
            kind = _kind(field.expr())
        else:
            kind = _kind(columns[field.column or key])
        row = {"field": key, "label": field.label, "type": kind}
        if field.note:
            row["note"] = field.note
        if (field.permission and field.permission not in slugs) or (field.whole_document and brand_scoped):
            row["restricted"] = True
        out.append(row)
    return out


def describe(db, user_id: str, entity: Any = None, *, panel: bool = False) -> dict:
    """With no entity: the entities this user may query. With one: its fields, relations, ops and limits."""
    slugs = _slugs(db, user_id)
    if entity is None:
        listed = [
            {"entity": e.key, "label": e.label, "module": e.module}
            for e in ENTITIES.values()
            if _readable(e, slugs) == "all" or (_readable(e, slugs) == "own" and e.own_clause is not None)
            if not _module_blocked(db, user_id, e.module)
            if not (e.brand_blind and _brand_scoped(db))
            if panel or not e.panel_only
        ]
        return {"entities": listed}
    from app.models.base import get_brand_scope

    found, own_only = _entity_for(db, user_id, entity, slugs, panel)
    brand_scoped = bool(get_brand_scope(db))
    relations = {}
    for name, (target_key, _fk) in found.relations.items():
        target = ENTITIES[target_key]
        if _module_blocked(db, user_id, target.module):
            continue
        if target.view_permission is not None and _readable(target, slugs) is None:
            # A lookup to this user: the fields it is named by, nothing past it (`_Paths._target`).
            fields = [r for r in _field_rows(target, slugs, brand_scoped) if r["field"] in target.name_by]
            relations[name] = {"label": target.label, "fields": fields, "relations": []}
            continue
        relations[name] = {
            "label": target.label, "fields": _field_rows(target, slugs, brand_scoped), "relations": list(target.relations),
        }
    out = {
        "entity": found.key,
        "label": found.label,
        "only_own_rows": own_only,
        "fields": _field_rows(found, slugs, brand_scoped),
        "relations": relations,
        "ops": list(OPS),
        "buckets": list(BUCKETS),
        "aggregates": list(FNS),
        "limits": {"rows": MAX_ROWS, "groups": MAX_GROUPS, "group_by_fields": MAX_GROUP_FIELDS, "relation_hops": MAX_HOPS},
    }
    if found.window_field:
        out["window"] = (
            f"`{found.window_field}` picks the periods read: between [from, to] keeps every period overlapping it, "
            f"eq a date the period containing it; without it, the periods containing today."
        )
    return out
