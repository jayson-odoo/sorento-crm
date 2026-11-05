"""`crm_query` over a computed entity: rows a module's own service computes (a target period's achievement and
commission, which no table holds), then the same spec as `query.run_query` (filters, group_by with buckets,
aggregates, sort, limit) applied in code. The result has the SQL path's shape, so `query_tools` renders it alike.

The figures are never computed here: `EntityDef.compute` is the module's service. This module only picks the
date window, filters, groups and sums what that service returned.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from app.services.assistant_registry.query import (
    BUCKETS,
    DEFAULT_ROWS,
    FNS,
    MAX_AGGREGATES,
    MAX_FILTERS,
    MAX_GROUP_FIELDS,
    MAX_GROUPS,
    MAX_IN_VALUES,
    MAX_ROWS,
    MAX_TEXT_CHARS,
    OPS,
    QueryRefused,
    _FN_WORDS,
    _display_date,
    _limit,
    _list,
    _plain,
    _scalar,
    _sort_dir,
    _sort_items,
)
from app.services.assistant_registry.types import EntityDef, FieldDef

#: The most periods one call reads before its filters: past it the window is too wide to compute in a turn.
MAX_COMPUTED_ROWS = 2000
#: The widest date window one call computes (security review, wave 2: "all payouts ever" is not a chat question).
MAX_WINDOW_DAYS = 731


def _today() -> dt.date:
    from app.services.sales.team_service import _today as today

    return today()


def _field(entity: EntityDef, slugs: set[str], path: Any) -> tuple[str, FieldDef]:
    if not isinstance(path, str) or not path.strip():
        raise QueryRefused("invalid", "A field must be a name such as `agent`.")
    if "." in path:
        raise QueryRefused("unknown_field", f"{entity.label} have no relations; use their own fields.")
    field = entity.fields.get(path)
    if field is None:
        raise QueryRefused(
            "unknown_field", f"`{path}` is not a readable field. Fields of {entity.label.lower()}: {', '.join(entity.fields)}."
        )
    if field.permission and field.permission not in slugs:
        raise QueryRefused("restricted", f"`{path}` is restricted for this user.")
    return path, field


def _date(value: Any, path: str) -> dt.date:
    iso = _scalar(value, path, "date")
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(iso))
    except ValueError:
        raise QueryRefused("invalid", f"`{path}` needs a date (dd/mm/yyyy or YYYY-MM-DD).") from None


def _window(entity: EntityDef, asked: list) -> tuple[dt.date, dt.date, list, str | None]:
    """(date_from, date_to, the other filters, the period as said). A filter on the window field sets the window
    (the periods overlapping it); everything else is a row filter."""
    key = entity.window_field
    label = entity.fields[key].label if key else ""
    low = high = None
    rest = []
    for item in asked:
        if not isinstance(item, dict) or set(item) - {"field", "op", "value"}:
            raise QueryRefused("invalid", "Each filter is {field, op, value}.")
        if key is None or item.get("field") != key:
            rest.append(item)
            continue
        op, value = item.get("op"), item.get("value")
        if op == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise QueryRefused("invalid", f"`between` on `{key}` needs [from, to].")
            low, high = _date(value[0], key), _date(value[1], key)
        elif op == "eq":
            low = high = _date(value, key)
        elif op in ("gte", "gt"):
            low = _date(value, key) + dt.timedelta(days=1 if op == "gt" else 0)
        elif op in ("lte", "lt"):
            high = _date(value, key) - dt.timedelta(days=1 if op == "lt" else 0)
        else:
            raise QueryRefused("invalid", f"`{key}` takes eq, between, gte, gt, lte or lt (a date window).")
    if low is None and high is None:
        today = _today()
        return today, today, rest, None
    low = low or high
    high = high or low
    if low > high:
        raise QueryRefused("invalid", f"The `{key}` window ends before it starts.")
    if (high - low).days >= MAX_WINDOW_DAYS:
        raise QueryRefused("invalid", f"The `{key}` window is longer than two years; ask for a shorter one.")
    shown = _display_date(low.isoformat(), "date"), _display_date(high.isoformat(), "date")
    period = f"{label} {shown[0]}" if low == high else f"{label} {shown[0]} to {shown[1]}"
    return low, high, rest, period


def _coerce(value: Any, kind: str, path: str) -> Any:
    value = _scalar(value, path, kind)
    if value is None:
        return None
    if kind == "date":
        return _date(value, path)
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise QueryRefused("invalid", f"`{path}` needs a number.")
        try:
            return float(value)
        except ValueError:
            raise QueryRefused("invalid", f"`{path}` needs a number.") from None
    if kind == "boolean":
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        if not isinstance(value, bool):
            raise QueryRefused("invalid", f"`{path}` is true or false.")
    return value


def _cmp(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "number":
        return float(value)
    return value


def _predicate(entity: EntityDef, slugs: set[str], item: dict):
    path, field = _field(entity, slugs, item.get("field"))
    kind = field.kind or "text"
    op = item.get("op")
    if op not in OPS:
        raise QueryRefused("invalid", f"Unknown op {op!r}. Ops: {', '.join(OPS)}.")
    value = item.get("value")
    if op == "is_null":
        return lambda row: row.get(path) in (None, "")
    if op == "is_not_null":
        return lambda row: row.get(path) not in (None, "")
    if op in ("contains", "starts_with"):
        if kind != "text":
            raise QueryRefused("invalid", f"`{op}` works on text fields; `{path}` is {kind}.")
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_CHARS:
            raise QueryRefused("invalid", f"`contains` and `starts_with` on `{path}` need text.")
        needle = value.strip().lower()
        if op == "contains":
            return lambda row: needle in str(row.get(path) or "").lower()
        return lambda row: str(row.get(path) or "").lower().startswith(needle)
    if op in ("in", "not_in"):
        if not isinstance(value, list) or not value or len(value) > MAX_IN_VALUES:
            raise QueryRefused("invalid", f"`{op}` on `{path}` needs a list of 1 to {MAX_IN_VALUES} values.")
        values = {_coerce(v, kind, path) for v in value}
        if op == "in":
            return lambda row: _cmp(row.get(path), kind) in values
        return lambda row: row.get(path) is not None and _cmp(row.get(path), kind) not in values
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise QueryRefused("invalid", f"`between` on `{path}` needs [from, to].")
        low, high = (_coerce(v, kind, path) for v in value)
        return lambda row: row.get(path) is not None and low <= _cmp(row.get(path), kind) <= high
    want = _coerce(value, kind, path)
    if want is None:
        raise QueryRefused("invalid", f"`{op}` on `{path}` needs a value; use is_null for an empty one.")
    tests = {
        "eq": lambda got: got == want,
        "ne": lambda got: got != want,
        "lt": lambda got: got < want,
        "lte": lambda got: got <= want,
        "gt": lambda got: got > want,
        "gte": lambda got: got >= want,
    }
    test = tests[op]
    if op == "ne":
        return lambda row: row.get(path) is None or test(_cmp(row.get(path), kind))
    return lambda row: row.get(path) is not None and test(_cmp(row.get(path), kind))


def _bucket(value: Any, bucket: str) -> dt.date | None:
    if not isinstance(value, dt.date):
        return None
    if bucket == "day":
        return value
    if bucket == "week":
        return value - dt.timedelta(days=value.weekday())
    if bucket == "month":
        return value.replace(day=1)
    if bucket == "quarter":
        return value.replace(month=(value.month - 1) // 3 * 3 + 1, day=1)
    return value.replace(month=1, day=1)


def _group_key(entity: EntityDef, slugs: set[str], item: Any):
    """(name, row -> key value, column label)."""
    if isinstance(item, str):
        path, field = _field(entity, slugs, item)
        return path, (lambda row: row.get(path)), field.label
    if isinstance(item, dict) and not (set(item) - {"field", "bucket"}):
        path, field = _field(entity, slugs, item.get("field"))
        bucket = item.get("bucket")
        if bucket is None:
            return path, (lambda row: row.get(path)), field.label
        if bucket not in BUCKETS:
            raise QueryRefused("invalid", f"Unknown bucket {bucket!r}. Buckets: {', '.join(BUCKETS)}.")
        if field.kind != "date":
            raise QueryRefused("invalid", f"A bucket needs a date field; `{path}` is {field.kind}.")
        return f"{path}_{bucket}", (lambda row: _bucket(row.get(path), bucket)), f"{field.label} ({bucket} starting)"
    raise QueryRefused("invalid", "Each group_by item is a field name or {field, bucket}.")


def _aggregate(entity: EntityDef, slugs: set[str], item: Any):
    """(alias, rows -> value, column label)."""
    if not isinstance(item, dict) or set(item) - {"fn", "field"}:
        raise QueryRefused("invalid", "Each aggregate is {fn, field}.")
    fn, path = item.get("fn"), item.get("field")
    if fn not in FNS:
        raise QueryRefused("invalid", f"Unknown fn {fn!r}. Fns: {', '.join(FNS)}.")
    if fn == "count" and path is None:
        return "count", len, entity.label
    path, field = _field(entity, slugs, path)
    kind = field.kind or "text"
    if fn in ("sum", "avg") and kind != "number":
        raise QueryRefused("invalid", f"`{fn}` needs a number field; `{path}` is {kind}.")
    label = f"{_FN_WORDS[fn]} {field.label.lower()}"

    def present(rows):
        return [r.get(path) for r in rows if r.get(path) is not None]

    def run(rows):
        values = present(rows)
        if fn == "count":
            return len(values)
        if fn == "count_distinct":
            return len(set(values))
        if not values:
            return None
        if fn == "sum":
            return round(sum(float(v) for v in values), 2)
        if fn == "avg":
            return round(sum(float(v) for v in values) / len(values), 2)
        return min(values) if fn == "min" else max(values)

    return f"{fn}_{path}", run, label


def _sort_key(value: Any):
    # None last whatever the direction, so the sort never compares None with a value.
    if isinstance(value, Decimal):
        value = float(value)
    return value


def _sorted(items: list[dict], order: list[tuple[str, str]]) -> list[dict]:
    for key, direction in reversed(order):
        present = [i for i in items if i.get(key) is not None]
        missing = [i for i in items if i.get(key) is None]
        present.sort(key=lambda i: _sort_key(i.get(key)), reverse=direction == "desc")
        items = present + missing
    return items


def run_computed(db, user_id: str, entity: EntityDef, own_only: bool, slugs: set[str], spec: dict) -> dict:
    asked = _list(spec, "filters", MAX_FILTERS)
    date_from, date_to, rest, period = _window(entity, asked)
    named = {f.get("field") for f in rest}
    notes = []
    for field, op, value, note in entity.default_filters:
        if field not in named:
            rest.append({"field": field, "op": op, "value": value})
            notes.append(note)
    if period is None and entity.window_field:
        notes.insert(0, f"Periods containing today ({_display_date(date_from.isoformat(), 'date')}).")
    tests = [_predicate(entity, slugs, item) for item in rest]
    group_by = _list(spec, "group_by", MAX_GROUP_FIELDS)
    aggregates = _list(spec, "aggregates", MAX_AGGREGATES)
    if (group_by or aggregates) and _list(spec, "fields"):
        raise QueryRefused("invalid", "`fields` lists rows; with group_by or aggregates leave it out.")
    # Every name in the spec is checked before the service runs, so a refusal costs no computation.
    key_rows = [_group_key(entity, slugs, g) for g in group_by]
    agg_rows = [_aggregate(entity, slugs, a) for a in (aggregates or ([{"fn": "count"}] if group_by else []))]
    sort = _sort_items(spec)

    from app.services.assistant_registry.query import timed

    # The service runs under the same statement timeout as a SQL query; it refuses a window over the cap itself,
    # BEFORE computing (a count first).
    computed = timed(db, lambda: entity.compute(db, user_id, own_only, date_from, date_to, limit=MAX_COMPUTED_ROWS))
    rows = [r for r in computed if all(t(r) for t in tests)]

    if key_rows or agg_rows:
        out = _groups(entity, rows, key_rows, agg_rows, sort, spec)
    else:
        out = _rows(entity, slugs, rows, sort, spec)
    out["period_display"] = period
    out["scope_note"] = " ".join(notes) or None
    return out


def _rows(entity: EntityDef, slugs: set[str], rows: list[dict], sort: list[dict], spec: dict) -> dict:
    asked = _list(spec, "fields", 30)
    if any(not isinstance(f, str) for f in asked):
        raise QueryRefused("invalid", "`fields` is a list of field names.")
    for name in asked:
        if name not in entity.fields:
            _field(entity, slugs, name)  # raises unknown_field (a restricted one is dropped below, as in SQL)
    wanted = list(dict.fromkeys([*entity.name_by, *(asked or list(entity.fields))]))
    shown = [f for f in wanted if not entity.fields[f].permission or entity.fields[f].permission in slugs]
    restricted = [f for f in wanted if f not in shown]
    order = []
    for item in sort:
        path, _f = _field(entity, slugs, item["field"])
        order.append((path, _sort_dir(item)))
    rows = _sorted(list(rows), order) if order else rows
    limit = _limit(spec, MAX_ROWS, DEFAULT_ROWS)
    out_rows = []
    for row in rows[:limit]:
        item = {"id": str(row.get("id"))}
        if entity.screen_path:
            item["link"] = entity.screen_path.format(**row)
        parts = [str(_plain(row.get(f))) for f in entity.name_by if f in shown and row.get(f) not in (None, "")]
        if parts:
            item["label"] = parts[0] if len(parts) == 1 else f"{parts[0]}: {' '.join(parts[1:])}"
        item.update({f: _plain(row.get(f)) for f in shown if f not in entity.name_by})
        out_rows.append(item)
    columns = ([{"key": "label", "label": entity.label}] if any(f in shown for f in entity.name_by) else []) + [
        {"key": f, "label": entity.fields[f].label} for f in shown if f not in entity.name_by
    ]
    return {
        "entity": entity.key, "rows": out_rows, "total": len(rows), "truncated": len(rows) > len(out_rows),
        "restricted": restricted, "columns": columns,
    }


def _groups(entity: EntityDef, rows: list[dict], key_rows, agg_rows, sort: list[dict], spec: dict) -> dict:
    names = [k for k, _f, _l in key_rows] + [a for a, _f, _l in agg_rows]
    if len(set(names)) != len(names):
        raise QueryRefused("invalid", "Two groups or aggregates share a name; name each once.")
    buckets: dict[tuple, list[dict]] = {}
    for row in rows:
        buckets.setdefault(tuple(fn(row) for _n, fn, _l in key_rows), []).append(row)
    if not key_rows:
        buckets = {(): rows}
    groups = []
    for key, members in buckets.items():
        group = {name: value for (name, _fn, _l), value in zip(key_rows, key)}
        group.update({alias: fn(members) for alias, fn, _l in agg_rows})
        groups.append(group)
    order = []
    for item in sort:
        if item["field"] not in names:
            raise QueryRefused("invalid", f"Sort by a group or aggregate: {', '.join(names)}.")
        order.append((item["field"], _sort_dir(item)))
    order += [(name, "asc") for name, _fn, _l in key_rows if name not in {o[0] for o in order}]
    groups = _sorted(groups, order)
    total_groups = len(groups)
    groups = groups[: _limit(spec, MAX_GROUPS, MAX_GROUPS)]
    truncated = total_groups > len(groups)
    totals = {}
    if key_rows and not truncated:
        for alias, _fn, _label in agg_rows:
            if alias == "count" or alias.startswith(("count_", "sum_")):
                totals[alias] = round(sum(float(g[alias] or 0) for g in groups), 2)
                if alias == "count" or alias.startswith("count_"):
                    totals[alias] = int(totals[alias])
    return {
        "entity": entity.key,
        "groups": [{k: _plain(v) for k, v in g.items()} for g in groups],
        "total_groups": total_groups,
        "truncated": truncated,
        "columns": [{"key": name, "label": label, "group": True} for name, _fn, label in key_rows]
        + [{"key": alias, "label": label} for alias, _fn, label in agg_rows],
        "totals": totals,
    }
