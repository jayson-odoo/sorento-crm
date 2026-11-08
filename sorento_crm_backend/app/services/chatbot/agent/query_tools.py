"""`crm_query` and `crm_describe`: the agent's general read over the assistant registry (AI-QUERY-CORE).

Two `UserRead`s, run in process as the user (`writes.run_as_user`), on the panel and on a WhatsApp turn whose
contact has a linked active user; never for a contact principal (`writes.permitted_user_reads`). The read needs no
slug of its own beyond holding one registered entity's view or own slug: each entity's screen slug, own-row
rule, field slugs and module switch are checked inside (`assistant_registry.query`). Linked-only: when a console operator acts for someone else, a group total cannot be
cut down to what both people may see, so the tools are not offered then.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from app.services.assistant_registry import ENTITIES
from app.services.assistant_registry.query import MAX_GROUPS, MAX_ROWS, QueryRefused, describe, run_query
from app.services.chatbot import principal as staff_principal
from app.services.chatbot.agent import writes
from app.services.chatbot.agent.tools import TOOL_LABELS, ToolResult, cap_result

QUERY = "crm_query"
DESCRIBE = "crm_describe"

_REFUSAL_STATUS = {
    "no_access": "denied",
    "restricted": "denied",
    "own_only_unsupported": "denied",
    "module_disabled": "denied",
    "timeout": "timeout",
}


def _available(db, ctx) -> bool:
    """Off the panel, a contact narrowed to its linked customers (no office access type) keeps that narrowing
    today on every WhatsApp read; these tools run as the linked user and cannot narrow by customer, so they
    are not offered to it. Fail closed: a lookup that fails offers nothing."""
    from app.services.chatbot import principal as staff_principal

    if staff_principal.current() is not None:
        return True
    from app.services.contact_customer_scope import contact_customer_scope

    # A savepoint, so a failed lookup does not leave the turn's transaction aborted for every later call.
    savepoint = db.begin_nested()
    try:
        enforced = contact_customer_scope(db, str(ctx.contact_pk)).enforced
    except Exception:  # noqa: BLE001
        savepoint.rollback()
        return False
    savepoint.commit()
    return not enforced


def _refused(exc: QueryRefused) -> ToolResult:
    return ToolResult(_REFUSAL_STATUS.get(exc.code, "invalid"), message=exc.message)


def _as_user(db, ctx, name: str, fn, *, cap: bool = True) -> ToolResult:
    if getattr(ctx, "principal", "user") == "contact" or not ctx.user_id:
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    try:
        data = writes.run_as_user(db, ctx, lambda user: fn(str(user["id"])), tool_name=name)
    except QueryRefused as exc:
        return _refused(exc)
    except Exception as exc:  # noqa: BLE001
        return writes._route_failure(exc)
    if not cap:
        return ToolResult("ok", data=data)
    shaped, more = cap_result(data)
    return ToolResult("ok", data=shaped, more=more)


def query_result(data: Any, *, panel: bool) -> ToolResult:
    """A crm_query result: the code-rendered table from EVERY row the query returned (crew live round 6: the size
    cap for the model cut 50 rows to 49 before the table was drawn, "Top 49 of 88"), else the result capped."""
    if isinstance(data, dict):
        card = as_card(data, panel=panel)
        if card is not None:
            return card
    shaped, more = cap_result(data)
    return ToolResult("ok", data=shaped, more=more)


def _query(db, ctx, args: dict) -> ToolResult:
    out = _as_user(db, ctx, QUERY, lambda user_id: run_query(db, user_id, args), cap=False)
    if out.status == "ok":
        return query_result(out.data, panel=staff_principal.current() is not None)
    return out


# ------------------------------------------------------------------ the table block (crew pass on 56d774bd)

#: More rows or groups than this and the table is rendered by code and shown to the user under the model's one
#: line; the model gets totals and a sample, never the rows to retype (it cut 68 lines to 20, dropped the note,
#: and its output ran the turn out of time). The same rule as the report card of AGENT-REPORTS (#2201,
#: `report_state.with_cards`): a code-rendered block passed to the user verbatim.
CARD_MIN_ROWS = 10
SAMPLE_ROWS = 3
CARD_INSTRUCTION = (
    "The full table is shown to the user under your reply by the system. Write ONE short line (the headline "
    "figure from totals), do not list or repeat the rows, and do not repeat the period or note."
)


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}"
    return " ".join(str(value).split()).replace("|", "/")


def render_card(data: dict, *, title: str, panel: bool) -> str:
    """The rows or groups as the user reads them: a heading with the period, the table (markdown on the panel,
    one line per row on WhatsApp), the totals, then the scope note and what was cut off."""
    columns = data.get("columns") or []
    items = data.get("groups") if "groups" in data else data.get("rows")
    items = items or []
    # No bold markers: the reply's formatting pass rewrites them, and a table needs none.
    heading = title
    if data.get("period_display"):
        heading += f", {data['period_display']}"
    lines = [heading]
    totals = data.get("totals") or {}
    if panel:
        # A blank line before and after the table, or markdown renders it as raw "|" text (crew pass, 5 Nov).
        lines.append("")
        lines.append("| " + " | ".join(c["label"] for c in columns) + " |")
        lines.append("|" + "|".join("---" for _ in columns) + "|")
        for item in items:
            lines.append("| " + " | ".join(_cell(item.get(c["key"])) for c in columns) + " |")
        if totals:
            cells = [_cell(totals[c["key"]]) if c["key"] in totals else "" for c in columns]
            cells[0] = cells[0] or "Total"
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    else:
        first, rest = (columns[0], columns[1:]) if columns else ({"key": ""}, [])
        for item in items:
            values = ", ".join(f"{c['label']} {_cell(item.get(c['key']))}" for c in rest)
            lines.append(f"- {_cell(item.get(first['key']))}: {values}" if values else f"- {_cell(item.get(first['key']))}")
        if totals:
            lines.append("Total: " + ", ".join(f"{c['label']} {_cell(totals[c['key']])}" for c in columns if c["key"] in totals))
    shown, whole = len(items), data.get("total_groups", data.get("total"))
    if data.get("truncated") and whole:
        if data.get("ranked_by"):
            lines.append(f"Top {shown:,} of {int(whole):,} by {str(data['ranked_by']).lower()}.")
        else:
            lines.append(f"Showing {shown:,} of {int(whole):,}.")
    if data.get("scope_note"):
        lines.append(data["scope_note"])
    return "\n".join(lines)


def as_card(data: dict, *, panel: bool) -> ToolResult | None:
    """A result over CARD_MIN_ROWS as a code-rendered block for the user plus a summary for the model; None
    for a short result, which the model reads whole."""
    items = data.get("groups") if "groups" in data else data.get("rows")
    entity = ENTITIES.get(str(data.get("entity")))
    least = entity.card_min_rows if entity is not None and entity.card_min_rows else CARD_MIN_ROWS + 1
    distance = _is_distance(data)
    if distance:
        # One subject is a table too (crew live x3 W4: one row was left to the model, "were not retrieved").
        least = 1
    if not isinstance(items, list) or len(items) < least:
        return None
    title = DISTANCE_TITLE if distance else (entity.label if entity is not None else "Results")
    if "groups" in data:
        keys = [c["label"] for c in data.get("columns") or [] if c.get("group")]
        title = f"{title} by {', '.join(k.lower() for k in keys)}" if keys else title
    summary = {
        "entity": data.get("entity"),
        "shown_to_user": True,
        "instruction": CARD_INSTRUCTION,
        "period_display": data.get("period_display"),
        "scope_note": data.get("scope_note"),
        "truncated": data.get("truncated"),
        "sample": items[:SAMPLE_ROWS],
    }
    for key in ("total", "total_groups", "totals", "restricted", "ranked_by"):
        if key in data:
            summary[key] = data[key]
    return ToolResult("ok", data=summary, display=render_card(data, title=title, panel=panel))


def _describe(db, ctx, args: dict) -> ToolResult:
    unknown = sorted(str(k) for k in args if k != "entity")
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(unknown)}.")
    entity: Any = args.get("entity") or None
    return _as_user(db, ctx, DESCRIBE, lambda user_id: describe(db, user_id, entity))


# Every array names its items and every object its properties: Gemini refuses a schema that does not (400),
# and the turn then fails as a whole (`tests/chatbot/agent/test_agent_tool_schemas_gemini.py`).
_TEXT = {"type": "string"}

#: Money fields per entity whose total is a SALES figure on that entity's basis (crew pass on 74b6b751).
MONEY_FIELDS = {
    "billing_document": {"sales_amount", "net_total", "total"},
    "order": {"subtotal_amount", "total_amount"},
}
#: The sales basis each source counts: `crm_query` entities and `crm_report_ask`'s own `basis` values.
ENTITY_BASIS = {"billing_document": "invoiced", "order": "delivered"}
REPORT_BASES = frozenset({"invoiced", "delivered", "ordered"})
BASIS_LABELS = {
    "invoiced": "invoiced (billing documents)", "delivered": "delivered (delivery orders)", "ordered": "ordered (sales orders)",
}


def money_basis(args: Any, name: str = QUERY) -> str | None:
    """The sales basis a call's money figures are on: a `crm_query` sum / avg / min / max of a money field
    (invoiced on billing documents, delivered on delivery orders), or a `crm_report_ask` on a sales basis.
    None for anything else (counts, targets, outstanding)."""
    if not isinstance(args, dict):
        return None
    if name == "crm_report_ask":
        basis = str(args.get("basis") or "").strip().lower()
        dataset = str(args.get("dataset") or "").strip().lower()
        return basis if basis in REPORT_BASES and dataset != "chat" else None
    if name != QUERY or args.get("entity") not in MONEY_FIELDS:
        return None
    money = MONEY_FIELDS[args["entity"]]
    for item in args.get("aggregates") or []:
        if isinstance(item, dict) and item.get("fn") in ("sum", "avg", "min", "max") and item.get("field") in money:
            return ENTITY_BASIS[args["entity"]]
    return None


def mixed_basis_refusal(first: str, now: str) -> ToolResult:
    """One answer, one sales basis: the turn already has sales on `first` (crew pass on ffdd7f87: "sales last
    month per agent" came back on invoiced, delivered and ordered at once)."""
    return ToolResult(
        "denied",
        message=(
            f"This answer's sales figures are already on the {BASIS_LABELS[first]} basis; {BASIS_LABELS[now]} "
            "figures would mix two bases in one answer. Answer from the first result only, and offer the other "
            "basis in one line if the user may want it."
        ),
    )


def entity_index() -> str:
    """The compact index in `crm_query`'s description: each queryable entity's hint, fields and relations, so most
    questions are one `crm_query` call with no `crm_describe` round first (crew pass on d430fe3c, 5 Nov: the extra
    round took list turns from ~49k to ~77k prompt tokens). Notes stay in `crm_describe`."""
    lines = []
    for e in ENTITIES.values():
        if e.view_permission is None or not e.in_index:
            continue
        # A relation shows the fields it is named by (all a lookup may read; crm_describe lists the rest).
        rel = [
            f"{name}.{{{','.join(ENTITIES[target].name_by or tuple(ENTITIES[target].fields))}}}"
            for name, (target, _fk) in e.relations.items()
        ]
        lines.append(f"{e.key} ({e.hint}): {','.join([*e.fields, *rel])}")
    return "\n".join(lines)


_SCALARS = [_TEXT, {"type": "number"}, {"type": "boolean"}]

QUERY_SCHEMA = {
    "type": "function",
    "function": {
        "name": QUERY,
        "description": (
            "Read CRM records as their screens show them: rows, or totals with group_by. SALES with no basis named "
            "are invoiced: billing_document, one query for the table and its total (owner rule: invoiced first; if "
            "the user's basis is unclear, ask). Delivery order (DO) counts and totals per agent, customer or month are "
            "entity order, not the sales report, and only when DOs are asked, never as sales; never mix the two in "
            "one answer. "
            "Call it directly with the entities and fields below (a relation field is customer.code); call "
            "crm_describe only when a field's meaning is unclear. In the reply, show each row by its label exactly "
            "and say the result's period_display and scope_note. "
            "filters: [{field, op, value}], op one of eq ne in not_in lt lte gt gte between contains starts_with "
            "is_null is_not_null. group_by: [field or {field, bucket: day|week|month|quarter|year}]. "
            "aggregates: [{fn: count|count_distinct|sum|avg|min|max, field}]. sort: [{field, dir}] (a group "
            f"sorts by its key or an aggregate alias such as sum_total_amount). At most {MAX_ROWS} rows or "
            f"{MAX_GROUPS} groups; total and truncated say if there are more. Dates are Malaysian and dd/mm/yyyy. "
            "A person or agent named by the user: pass it as `agent` exactly as said (no crm_resolve, no ids). "
            "A time window: `period` (no crm_describe needed); a date filter may also name its window.\n"
            "Entities:\n" + entity_index()
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": _TEXT,
                "agent": {"type": "string", "description": "Sales agent code or name as the user said it; matched "
                          "exactly first, inside the tool."},
                "period": {"anyOf": [_TEXT, {"type": "array", "items": _TEXT}], "description": "last_month, "
                           "this_month, this_quarter, last_quarter, this_year, 2026-10, Q3 2026, 2026, or [from, to] "
                           "where to may be today (since July = [2026-07, today])."},
                "fields": {"type": "array", "items": _TEXT},
                "filters": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"field": _TEXT, "op": _TEXT, "value": {"anyOf": [*_SCALARS, {"type": "array", "items": {"anyOf": _SCALARS}}]}},
                    "required": ["field", "op"],
                }},
                "group_by": {"type": "array", "items": {"anyOf": [
                    _TEXT, {"type": "object", "properties": {"field": _TEXT, "bucket": _TEXT}, "required": ["field"]},
                ]}},
                "aggregates": {"type": "array", "items": {
                    "type": "object", "properties": {"fn": _TEXT, "field": _TEXT}, "required": ["fn"],
                }},
                "sort": {"type": "array", "items": {
                    "type": "object", "properties": {"field": _TEXT, "dir": _TEXT}, "required": ["field"],
                }},
                "limit": {"type": "integer"},
            },
            "required": ["entity"],
        },
    },
}

DESCRIBE_SCHEMA = {
    "type": "function",
    "function": {
        "name": DESCRIBE,
        "description": (
            "Without entity: the CRM entities this user may read with crm_query. With entity: its fields "
            "(type, restricted), relations, filter ops, date buckets, aggregates and limits."
        ),
        "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}},
    },
}

#: Offered to a user who may read at least one registered entity (its view or own slug); each entity's own
#: slugs are checked again inside every call.
ANY_ENTITY = tuple(sorted({
    slug for e in ENTITIES.values() for slug in (e.view_permission, e.own_permission) if slug
}))

writes.USER_READS[QUERY] = writes.UserRead(
    name=QUERY, user_permission=ANY_ENTITY, schema=QUERY_SCHEMA, run=_query, linked_only=True, available=_available,
)
writes.USER_READS[DESCRIBE] = writes.UserRead(
    name=DESCRIBE, user_permission=ANY_ENTITY, schema=DESCRIBE_SCHEMA, run=_describe, linked_only=True, available=_available,
)
TOOL_LABELS.setdefault(QUERY, "reading CRM records, totals and groupings")
TOOL_LABELS.setdefault(DESCRIBE, "listing the CRM records you can read")


#: The model's line kept above a table block.
MAX_LINE_CHARS = 300
_ISO_DATE = re.compile(r"(?<![\w-])(\d{4})-(\d{2})-(\d{2})(?![\w-])")


def _dmy(found: "re.Match") -> str:
    year, month, day = found.groups()
    try:
        dt.date(int(year), int(month), int(day))
    except ValueError:
        return found.group(0)
    return f"{day}/{month}/{year}"


def _sentences(note: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=\.)\s+(?=[A-Z])", note) if part.strip()]


def _year_as_range(text: str, entries: list[dict]) -> str:
    """"for 2026" as the window the result covered ("from 01/01/2026 to 31/12/2026"), when a whole calendar year
    was read (crew live round 4: the first line said "for 2026" where the owner wants the date range)."""
    for e in entries:
        found = re.fullmatch(r"Period 01/01/(\d{4}) to 31/12/\1", str((e.get("data") or {}).get("period_display") or ""))
        if found:
            year = found.group(1)
            text = re.sub(rf"\b(?:for|in|during) (?:the year )?{year}\b", f"from 01/01/{year} to 31/12/{year}", text)
    return text


def _user_named(args: dict, user_text: str | None) -> bool:
    said = " ".join(str(user_text or "").split()).lower()
    if not said:
        return False
    values = [args.get("agent")] + [f.get("value") for f in args.get("filters") or [] if isinstance(f, dict)]
    return any(isinstance(v, str) and v.strip() and " ".join(v.split()).lower() in said for v in values)


def strip_self_agent(args: dict, user_name: str | None, user_text: str) -> tuple[dict, str | None]:
    """The asking user's own name is not an agent filter unless they said "my" (or named themselves): crew live
    round 4, "payout per dealer" was first filtered by the asker's own name and found nothing."""
    own = " ".join(str(user_name or "").split()).lower()
    said = " ".join(str(user_text or "").split()).lower()
    if not own or re.search(r"\b(my|me|mine|myself|saya)\b", said):
        return args, None

    words = set(own.split())

    def is_self(value: Any) -> bool:
        # The asker's name, or part of it, in any order ("Teh", "teh jayson"); never one naming someone else too.
        v = " ".join(str(value or "").split()).lower()
        return bool(v) and set(v.split()) <= words and v not in said

    out, dropped = dict(args), []
    if is_self(out.get("agent")):
        dropped.append(str(out.pop("agent")))
    entity = ENTITIES.get(str(out.get("entity")))
    if entity is not None and isinstance(out.get("filters"), list):
        keep = []
        for f in out["filters"]:
            field = entity.fields.get(str(f.get("field"))) if isinstance(f, dict) else None
            if field is not None and (f.get("field") in entity.name_by or field.agent_id) and is_self(f.get("value")):
                dropped.append(str(f.get("value")))
                continue
            keep.append(f)
        out["filters"] = keep
    if not dropped:
        return args, None
    return out, f"Left out {', '.join(dropped)}: that is your own name and the question did not name it or say 'my'."


def _names_a_subject(entity_key: str, args: dict) -> bool:
    """Does a crm_query name a record: `agent`, or a filter on the entity's name or agent field."""
    if args.get("agent"):
        return True
    entity = ENTITIES.get(entity_key)
    if entity is None:
        return False
    for f in args.get("filters") or []:
        if not isinstance(f, dict):
            continue
        field = entity.fields.get(str(f.get("field")))
        if field is not None and (f.get("field") in entity.name_by or field.agent_id):
            return True
    return False


# ------------------------------------------------------------------ distance to the next tier (AGENT-COMMISSION-WA)

#: The entity that answers "how far from the next tier" (`assistant_registry.sales`, `NEXT_TIER_FIELDS`).
NEXT_TIER_ENTITY = "agent_target_summary"
#: The columns of every distance answer, whatever the model asked for (crew live x3 on 0c5c7b78: X2 run 3 and W4
#: run 2 dropped them). The always-shown TGT and payout account come with them (`EntityDef.always_fields`).
NEXT_TIER_COLUMNS = (
    "owner_kind", "to_next_tier", "next_tier", "next_tier_at", "next_tier_payout", "next_tier_gain", "payout",
)
DISTANCE_TITLE = "Distance to the next tier"
#: The one line of a distance question nothing in the window can answer (crew live x3, W6).
NO_LADDER_SUFFIX = "has a commission ladder this period."
_NEXT_TIER_SAID = re.compile(
    r"\bnext\s+(?:commission\s+)?tier\b"
    r"|\b(?:how\s+far|closest|nearest|to\s+go)\b.*\btier\b"
    r"|\btier\b.*\b(?:to\s+go|away)\b"
)
_AGENTS_SAID = re.compile(r"\b(?:agents|salespeople|salesmen|salespersons)\b")
_OTHER_KINDS_SAID = re.compile(r"\b(?:dealers?|teams?|customers?)\b")


def next_tier_question(user_text: str | None) -> bool:
    """Is the user asking how far someone is from the next tier, or what it would pay."""
    return bool(_NEXT_TIER_SAID.search(" ".join(str(user_text or "").split()).lower()))


def next_tier_args(args: Any, user_text: str | None) -> Any:
    """A distance question's `agent_target_summary` call, shaped by code before it runs (crew live x3 on 0c5c7b78):
    one row per subject (no regroup), the next-tier columns whatever the model listed, ranked by what is still to
    sell, and only agents when the user asked about agents and named no one. Any other call is returned as it is."""
    if not isinstance(args, dict) or args.get("entity") != NEXT_TIER_ENTITY or not next_tier_question(user_text):
        return args
    out = {k: v for k, v in args.items() if k not in ("group_by", "aggregates", "fields", "sort")}
    out["fields"] = list(NEXT_TIER_COLUMNS)
    out["sort"] = [{"field": "to_next_tier", "dir": "asc"}]
    said = " ".join(str(user_text or "").split()).lower()
    filters = [f for f in out.get("filters") or [] if isinstance(f, dict)]
    if (
        _AGENTS_SAID.search(said) and not _OTHER_KINDS_SAID.search(said) and not _names_a_subject(NEXT_TIER_ENTITY, out)
        and not any(f.get("field") == "owner_kind" for f in filters)
    ):
        out["filters"] = [*filters, {"field": "owner_kind", "op": "eq", "value": "agent"}]
    return out


def _is_distance(data: dict) -> bool:
    return data.get("entity") == NEXT_TIER_ENTITY and any(
        c.get("key") == "to_next_tier" for c in data.get("columns") or []
    )


def _distance_reply(kept: list[dict]) -> str | None:
    """A distance question's whole reply, by code: the last distance call's table, alone (no lead line about the
    payout, no other entity's table), or its one "no commission ladder" line. None when there is no distance call
    to answer from (the reply is then shaped as any other)."""
    from app.services.assistant_registry.sales import NEXT_TIER_FIELDS

    calls = [
        e for e in kept
        if (e.get("args") or {}).get("entity") == NEXT_TIER_ENTITY
        and NEXT_TIER_FIELDS.keys() & set((e.get("args") or {}).get("fields") or [])
    ]
    if not calls:
        return None
    last = calls[-1]
    data = last.get("data") or {}
    named_none = data.get("rows") == [] and _names_a_subject(NEXT_TIER_ENTITY, last.get("args") or {})
    for note in _sentences(data.get("scope_note") or ""):
        # A name that matched nothing is answered as not found, not as "no ladder".
        if note.endswith(NO_LADDER_SUFFIX) and not named_none:
            return note
    return last.get("display") or None


def shape_reply(text: str, ledger: dict | None, user_text: str | None = None) -> str:
    """The reply as the owner's rules want it, decided in code whatever the model wrote (crew pass, 5 Nov):
    a `crm_query` row shown by its code (alone, or as "CODE (Name)") is shown by its label "CODE: Name"; the
    result's scope note is in the reply; a date is dd/mm/yyyy, never yyyy-mm-dd."""
    # A code-rendered table (`as_card`): the model's first line, then the tables verbatim, as
    # `report_state.with_cards` does for the report card. One table per entity, in the order first asked: a later
    # query on the same entity corrected the earlier one, so the last stands; a query on another entity is a table of
    # its own, which never replaces the first (crew live x3 on 3c6924bf: "who is below
    # target" lost its target table and its "Not reached = ..." note to a later payout query).
    per_entity: dict[str, str] = {}
    missed: set[str] = set()
    kept: list[dict] = []
    for e in (ledger or {}).values():
        if e.get("name") != QUERY or e.get("status") != "ok":
            continue
        args = e.get("args") or {}
        entity = str((e.get("data") or {}).get("entity") or args.get("entity") or "")
        named = _names_a_subject(entity, args)
        if named and (e.get("data") or {}).get("rows") == [] and not (e.get("data") or {}).get("total") and (
            _user_named(args, user_text)
        ):
            # Only a name the USER asked about: an empty call on a name the model made up (the asker's own, crew
            # live round 6) never hides the table a later call returned.
            missed.add(entity)
        if entity in missed and not named:
            # A whole table nobody asked for, after the named record was not found, is not shown, nor its notes
            # (owner 8 Nov: "payout to fullshun" appended every payout and notes on other agents).
            continue
        kept.append(e)
        if e.get("display"):
            per_entity[entity] = e["display"]
    if next_tier_question(user_text):
        answer = _distance_reply(kept)
        if answer:
            return _ISO_DATE.sub(_dmy, answer)
    text = _year_as_range(text, kept)
    if per_entity:
        cards = list(per_entity.values())
        card = "\n\n".join(cards)
        if not all(c in text for c in cards):
            line = next((part.strip() for part in text.splitlines() if part.strip()), "")
            text = f"{line[:MAX_LINE_CHARS]}\n\n{card}".strip() if line else card
        return _ISO_DATE.sub(_dmy, text)
    lowered = text.lower()
    notes: list[str] = []
    for entry in kept:
        if not isinstance(entry.get("data"), dict):
            continue
        data = entry["data"]
        # Sentence by sentence, each once (crew live round 4: "No period named" twice from two queries).
        for note in _sentences(data.get("scope_note") or ""):
            if note not in notes:
                notes.append(note)
        for row in data.get("rows") or []:
            label = str(row.get("label") or "")
            if ": " not in label or label.lower() in lowered:
                continue
            code, name = label.split(": ", 1)
            shown = re.compile(
                r"(?<![\w-])" + re.escape(code) + r"(?:\s*(?:[:\-]\s*|\(\s*)" + re.escape(name) + r"\)?)?(?![\w-])",
                re.IGNORECASE,
            )
            text, changed = shown.subn(lambda m: label, text, count=1)
            if changed:
                lowered = text.lower()
    for note in notes:
        if note.lower().rstrip(".") not in lowered:
            text = f"{text.rstrip()}\n\n{note}"
            lowered = text.lower()
    return _ISO_DATE.sub(_dmy, text)
