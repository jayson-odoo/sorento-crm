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

from sqlalchemy import Boolean, Date, DateTime, Numeric, Float, Integer, String, Text, cast, distinct, func, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased

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
#: Naive timestamps are stored UTC; dates the user names are Malaysian dates.
LOCAL_TZ = "Asia/Kuala_Lumpur"

OPS = (
    "eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "between", "contains", "starts_with", "is_null", "is_not_null",
)
BUCKETS = ("day", "week", "month", "quarter", "year")
FNS = ("count", "count_distinct", "sum", "avg", "min", "max")
SPEC_KEYS = ("entity", "fields", "filters", "group_by", "aggregates", "sort", "limit")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Postgres `query_canceled`: the statement timeout fired.
_QUERY_CANCELED = "57014"


class QueryRefused(Exception):
    """`code`: unknown_entity, unknown_field, restricted, no_access, own_only_unsupported, module_disabled,
    invalid, too_deep, timeout."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------ access


def _slugs(db, user_id: str) -> set[str]:
    from app.services.user_service import UserPermissionService

    return set(UserPermissionService(db).get_user_permission_slugs(str(user_id)))


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


def _entity_for(db, user_id: str, key: Any, slugs: set[str]) -> tuple[EntityDef, bool]:
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
    if _module_blocked(db, user_id, entity.module):
        raise QueryRefused("module_disabled", f"The {entity.label} module is not enabled.")
    return entity, reach == "own"


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


class _Paths:
    """Turns dotted field paths into columns, joining each declared relation once (outer join)."""

    def __init__(self, entity: EntityDef, slugs: set[str]) -> None:
        self.entity = entity
        self.slugs = slugs
        self.root = entity.model
        self._aliases: dict[str, Any] = {}
        self.joins: list[tuple[Any, Any]] = []

    def _target(self, path: Any) -> tuple[EntityDef, Any, str]:
        if not isinstance(path, str) or not path.strip():
            raise QueryRefused("invalid", "A field must be a name such as `status` or `supplier.name`.")
        parts = path.strip().split(".")
        if len(parts) - 1 > MAX_HOPS:
            raise QueryRefused("too_deep", f"`{path}` goes through {len(parts) - 1} relations; at most {MAX_HOPS}.")
        entity, holder, prefix = self.entity, self.root, ""
        for name in parts[:-1]:
            if name not in entity.relations:
                raise QueryRefused(
                    "unknown_field",
                    f"`{name}` is not a relation of {entity.label.lower()}. Relations: {', '.join(entity.relations) or 'none'}.",
                )
            target_key, fk = entity.relations[name]
            target = ENTITIES[target_key]
            prefix = f"{prefix}.{name}" if prefix else name
            if prefix not in self._aliases:
                alias = aliased(target.model)
                self._aliases[prefix] = alias
                self.joins.append((alias, alias.id == getattr(holder, fk)))
            entity, holder = target, self._aliases[prefix]
        return entity, holder, parts[-1]

    def resolve(self, path: Any) -> tuple[Any, FieldDef, str]:
        """(column expression, field, kind). Raises for an unknown or restricted field."""
        entity, holder, name = self._target(path)
        field = entity.fields.get(name)
        if field is None:
            raise QueryRefused(
                "unknown_field", f"`{path}` is not a readable field. Fields of {entity.label.lower()}: {', '.join(entity.fields)}."
            )
        if field.permission and field.permission not in self.slugs:
            raise QueryRefused("restricted", f"`{path}` is restricted for this user.")
        column = getattr(holder, field.column or name)
        return column, field, _kind(column.property.columns[0])

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


def _scalar(value: Any, path: str) -> Any:
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
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filter(paths: _Paths, item: Any):
    if not isinstance(item, dict) or set(item) - {"field", "op", "value"}:
        raise QueryRefused("invalid", "Each filter is {field, op, value}.")
    path, op = item.get("field"), item.get("op")
    column, _field, kind = paths.resolve(path)
    if op not in OPS:
        raise QueryRefused("invalid", f"Unknown op {op!r}. Ops: {', '.join(OPS)}.")
    value = item.get("value")
    if op == "is_null":
        return column.is_(None)
    if op == "is_not_null":
        return column.is_not(None)
    if op in ("in", "not_in"):
        if not isinstance(value, list) or not value or len(value) > MAX_IN_VALUES:
            raise QueryRefused("invalid", f"`{op}` on `{path}` needs a list of 1 to {MAX_IN_VALUES} values.")
        values = [_scalar(v, path) for v in value]
        return column.in_(values) if op == "in" else column.not_in(values)
    if op in ("contains", "starts_with"):
        if kind != "text":
            raise QueryRefused("invalid", f"`{op}` works on text fields; `{path}` is {kind}.")
        needle = _like(value, path)
        pattern = f"%{needle}%" if op == "contains" else f"{needle}%"
        return column.ilike(pattern, escape="\\")
    local = _local(column, kind)
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise QueryRefused("invalid", f"`between` on `{path}` needs [from, to].")
        low, high = (_scalar(v, path) for v in value)
        upper = _next_day(high) if kind == "datetime" else None
        return (local >= low) & (local < upper if upper is not None else local <= high)
    value = _scalar(value, path)
    if value is None:
        raise QueryRefused("invalid", f"`{op}` on `{path}` needs a value; use is_null for an empty one.")
    after = _next_day(value) if kind == "datetime" else None
    if op == "eq":
        return (local >= value) & (local < after) if after is not None else column == value
    if op == "ne":
        return ~((local >= value) & (local < after)) if after is not None else column != value
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
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
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
    """`stmt` under the statement timeout, inside a savepoint: a timeout rolls back to it (and with it the
    `SET LOCAL`), so the caller's transaction stays usable."""
    savepoint = db.begin_nested()
    try:
        previous = db.execute(text("SHOW statement_timeout")).scalar() or "0"
        db.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
        rows = _execute(db, stmt)
        db.execute(text("SELECT set_config('statement_timeout', :v, true)"), {"v": str(previous)})
    except DBAPIError as exc:
        savepoint.rollback()
        if getattr(getattr(exc, "orig", None), "pgcode", None) == _QUERY_CANCELED:
            raise QueryRefused(
                "timeout", "The question took too long to answer. Narrow it with a filter (a date range, a status)."
            ) from exc
        raise
    except BaseException:
        if savepoint.is_active:
            savepoint.rollback()
        raise
    savepoint.commit()
    return rows


def _base(db, user_id: str, entity: EntityDef, own_only: bool, stmt, paths: _Paths):
    for alias, onclause in paths.joins:
        stmt = stmt.outerjoin(alias, onclause)
    if entity.scope is not None:
        for clause in entity.scope(db):
            stmt = stmt.where(clause)
    if own_only:
        from app.services.own_scope import me

        stmt = stmt.where(entity.own_clause(me(db, user_id)))
    return stmt


def run_query(db, user_id: str, spec: Any) -> dict:
    """Rows or groups of one registered entity, as `user_id` may see them. The session's company scope must
    already be the user's (`run_as_user`)."""
    if not isinstance(spec, dict):
        raise QueryRefused("invalid", "The query must be an object.")
    unknown = sorted(str(k) for k in spec if k not in SPEC_KEYS)
    if unknown:
        raise QueryRefused("invalid", f"Unknown key(s): {', '.join(unknown)}. Keys: {', '.join(SPEC_KEYS)}.")
    slugs = _slugs(db, user_id)
    entity, own_only = _entity_for(db, user_id, spec.get("entity"), slugs)
    paths = _Paths(entity, slugs)
    filters = [_filter(paths, f) for f in _list(spec, "filters", MAX_FILTERS)]
    group_by = _list(spec, "group_by", MAX_GROUP_FIELDS)
    aggregates = _list(spec, "aggregates", MAX_AGGREGATES)
    if group_by or aggregates:
        if _list(spec, "fields"):
            raise QueryRefused("invalid", "`fields` lists rows; with group_by or aggregates leave it out.")
        return _groups(db, user_id, entity, own_only, paths, filters, group_by, aggregates, spec)
    return _rows(db, user_id, entity, own_only, paths, filters, spec)


def _rows(db, user_id, entity, own_only, paths, filters, spec) -> dict:
    asked = _list(spec, "fields", 30)
    if any(not isinstance(f, str) for f in asked):
        raise QueryRefused("invalid", "`fields` is a list of field names.")
    wanted = list(dict.fromkeys(asked or list(entity.fields)))
    shown = [f for f in wanted if paths.allowed(f)]
    restricted = [f for f in wanted if f not in shown]
    root = entity.model
    columns = [root.id.label("id")] + [paths.resolve(f)[0].label(f) for f in shown]
    total = func.count().over().label("__total")
    stmt = select(*columns, total).select_from(root)
    stmt = _base(db, user_id, entity, own_only, stmt, paths)
    for clause in filters:
        stmt = stmt.where(clause)
    order = []
    for item in _sort_items(spec):
        column = paths.resolve(item["field"])[0]
        order.append(column.desc().nulls_last() if _sort_dir(item) == "desc" else column.asc().nulls_last())
    if not order and hasattr(root, "created_at"):
        order.append(root.created_at.desc())
    order.append(root.id.asc())
    limit = _limit(spec, MAX_ROWS, DEFAULT_ROWS)
    rows = _run(db, stmt.order_by(*order).limit(limit))
    total_rows = int(rows[0]._mapping["__total"]) if rows else 0
    out_rows = []
    for row in rows:
        data = row._mapping
        item = {"id": str(data["id"])}
        if entity.screen_path:
            item["link"] = entity.screen_path.format(id=data["id"])
        item.update({f: _plain(data[f]) for f in shown})
        out_rows.append(item)
    return {
        "entity": entity.key, "rows": out_rows, "total": total_rows, "truncated": total_rows > len(out_rows),
        "restricted": restricted,
    }


def _group_key(paths: _Paths, item: Any) -> tuple[str, Any]:
    if isinstance(item, str):
        column, _f, kind = paths.resolve(item)
        return item, column
    if isinstance(item, dict) and not (set(item) - {"field", "bucket"}):
        path, bucket = item.get("field"), item.get("bucket")
        column, _f, kind = paths.resolve(path)
        if bucket is None:
            return path, column
        if bucket not in BUCKETS:
            raise QueryRefused("invalid", f"Unknown bucket {bucket!r}. Buckets: {', '.join(BUCKETS)}.")
        if kind not in ("date", "datetime"):
            raise QueryRefused("invalid", f"A bucket needs a date field; `{path}` is {kind}.")
        return f"{path}_{bucket}", cast(func.date_trunc(bucket, _local(column, kind)), Date)
    raise QueryRefused("invalid", "Each group_by item is a field name or {field, bucket}.")


def _aggregate(paths: _Paths, item: Any) -> tuple[str, Any]:
    if not isinstance(item, dict) or set(item) - {"fn", "field"}:
        raise QueryRefused("invalid", "Each aggregate is {fn, field}.")
    fn, path = item.get("fn"), item.get("field")
    if fn not in FNS:
        raise QueryRefused("invalid", f"Unknown fn {fn!r}. Fns: {', '.join(FNS)}.")
    if fn == "count" and path is None:
        return "count", func.count()
    column, _f, kind = paths.resolve(path)
    alias = f"{fn}_{path.replace('.', '_')}"
    if fn in ("sum", "avg") and kind != "number":
        raise QueryRefused("invalid", f"`{fn}` needs a number field; `{path}` is {kind}.")
    if fn == "count":
        return alias, func.count(column)
    if fn == "count_distinct":
        return alias, func.count(distinct(column))
    return alias, getattr(func, fn)(column)


def _groups(db, user_id, entity, own_only, paths, filters, group_by, aggregates, spec) -> dict:
    keys = [_group_key(paths, g) for g in group_by]
    aggs = [_aggregate(paths, a) for a in (aggregates or [{"fn": "count"}])]
    names = [k for k, _ in keys] + [a for a, _ in aggs]
    if len(set(names)) != len(names):
        raise QueryRefused("invalid", "Two groups or aggregates share a name; name each once.")
    root = entity.model
    labelled = {name: expr for name, expr in [*keys, *aggs]}
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
    return {"entity": entity.key, "groups": groups, "total_groups": total_groups, "truncated": total_groups > len(groups)}


# ------------------------------------------------------------------ describe


def _field_rows(entity: EntityDef, slugs: set[str]) -> list[dict]:
    columns = sa_inspect(entity.model).columns
    out = []
    for key, field in entity.fields.items():
        row = {"field": key, "label": field.label, "type": _kind(columns[field.column or key])}
        if field.permission and field.permission not in slugs:
            row["restricted"] = True
        out.append(row)
    return out


def describe(db, user_id: str, entity: Any = None) -> dict:
    """With no entity: the entities this user may query. With one: its fields, relations, ops and limits."""
    slugs = _slugs(db, user_id)
    if entity is None:
        listed = [
            {"entity": e.key, "label": e.label, "module": e.module}
            for e in ENTITIES.values()
            if _readable(e, slugs) == "all" or (_readable(e, slugs) == "own" and e.own_clause is not None)
            if not _module_blocked(db, user_id, e.module)
        ]
        return {"entities": listed}
    found, own_only = _entity_for(db, user_id, entity, slugs)
    relations = {}
    for name, (target_key, _fk) in found.relations.items():
        target = ENTITIES[target_key]
        relations[name] = {"label": target.label, "fields": _field_rows(target, slugs), "relations": list(target.relations)}
    return {
        "entity": found.key,
        "label": found.label,
        "only_own_rows": own_only,
        "fields": _field_rows(found, slugs),
        "relations": relations,
        "ops": list(OPS),
        "buckets": list(BUCKETS),
        "aggregates": list(FNS),
        "limits": {"rows": MAX_ROWS, "groups": MAX_GROUPS, "group_by_fields": MAX_GROUP_FIELDS, "relation_hops": MAX_HOPS},
    }
