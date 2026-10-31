"""The agent's tool registry and its dispatch permission layer (AGENTIC-P1 card sections 2, 3).

An explicit table of the read-only MCP tools the agent may call, each with the permission
slug the linked user must hold. The model-facing schema comes from the MCP catalogue with the
server-injected `contact_id` / `space_id` removed. `dispatch` re-checks everything at call
time, because showing a tool to the model is not a guard.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from app.services.ai_assistant_service import mcp_schema_to_openai_tool

logger = logging.getLogger(__name__)

#: Server-injected, never model-chosen.
GUARD_PARAMS = ("contact_id", "space_id")
#: Characters of JSON one tool result may carry back to the model.
RESULT_CHAR_CAP = 12_000


@dataclass(frozen=True)
class ToolDef:
    name: str
    user_permission: str
    #: The reveal the contact must hold before today's bot calls this tool's domain
    #: (`turn/policy_rows.py`, `answer.DOMAIN_GRANT_REQUIRED`, `turn/sub_asks.GRANT`); None
    #: where today's bot requires none.
    contact_grant: str | None = None
    #: True for a presenter tool (`sorento_crm_mcp.presenters.PRESENTER_TOOLS`): it is called
    #: with `view=render`, its answer is a render envelope carrying `restricted_fields`, and
    #: anything else is refused. The two non-presenter tools answer the route's raw JSON.
    #: Both were checked in the MCP catalogue: neither declares `restricted_fields`, so there
    #: is no field-level drop to lose by skipping the render view for them.
    render: bool = True


def _defs(*rows: tuple[str, str, str | None]) -> dict[str, ToolDef]:
    return {
        name: ToolDef(name, slug, grant, render=name not in NON_RENDER_TOOLS)
        for name, slug, grant in rows
    }


#: `crm_resolve` is local (the bot's resolver, in process); the GRN summary is a plain route.
NON_RENDER_TOOLS = frozenset(
    {"crm_resolve", "crm_products_find", "crm_procurement_grn_summary", "crm_knowledge_search", "user_guides_read"}
)
RESOLVE = "crm_resolve"
FIND = "crm_products_find"
#: AGENTIC-KNOWLEDGE: local, in process with the turn's user (the MCP cannot see the user).
KNOWLEDGE = "crm_knowledge_search"
#: The Outline guide reader. Open to every linked user; its call carries only `query`.
GUIDES = "user_guides_read"
PLAN = "plan"
ANSWER = "answer"


# crm_report_ask: the sales / outstanding reveal is decided by the route itself from the
# contact id (salesperson book and open pending delivery are exceptions it already knows),
# so the tool carries none; the chat dataset is gated below in ARG_CONTACT_GRANTS.
REGISTRY: dict[str, ToolDef] = _defs(
    ("crm_report_ask", "order_management.orders.view", None),
    ("crm_inventory_stock_balance_list", "inventory.stock.view", None),
    ("crm_incoming_stock_by_product", "procurement.packing_lists.view", None),
    ("crm_incoming_stock_shipments", "procurement.packing_lists.view", None),
    ("crm_procurement_grn_summary", "procurement.grn.view", "purchase_orders.placed"),
    ("crm_procurement_po_last_cost_list", "scm.purchase_orders.view", "purchase_orders.cost"),
    ("crm_procurement_po_placed_list", "scm.purchase_orders.view", "purchase_orders.placed"),
    ("crm_procurement_spo_allocations_last_receipt_list", "procurement.spo_allocations.view", "purchase_orders.placed"),
    ("crm_order_management_orders_by_product_list", "order_management.orders.view", None),
    # No single slug: each kind it searches has its own (KIND_SLUGS), checked per call.
    ("crm_resolve", "", None),
    # Local: the product list behind a brand / category, under the contact's scopes.
    ("crm_products_find", "master_data.products.view", None),
    # Local: passages of uploaded documents the user may open in Resources.
    ("crm_knowledge_search", "resource.attachments.view", None),
    # No slug: guides are for any signed-in staff user (every agent caller is an active CRM user).
    ("user_guides_read", "", None),
)

#: Tools that read stock: today's bot refuses them for a contact with `chatbot_stock_allowed` off.
STOCK_TOOLS = frozenset({"crm_inventory_stock_balance_list"})

#: Argument values that need more than the tool's own slug, on `crm_report_ask`
#: (`order_management/report_ask.py`: unpaid needs `finance.billing_documents.view` on the
#: act-as user; the chat dataset is the analytics screen's data).
ARG_PERMISSIONS: dict[tuple[str, str], str] = {
    ("basis", "unpaid"): "finance.billing_documents.view",
    ("dataset", "chat"): "chatbot.analytics.view",
}
ARG_CONTACT_GRANTS: dict[tuple[str, str], str] = {
    ("dataset", "chat"): "chatbot.analytics",
}
#: `view=render` is what makes the MCP attach `restricted_fields`; it is never the model's choice.
VIEW_PARAM = "view"
SELLABLE_PARAM = "include_sellable"
SELLABLE_GRANT = "inventory.sellable"
#: Keys the presenter envelope always carries one of; a raw route payload carries none.
ENVELOPE_KEYS = ("has_result", "result_type", "items", "answers", "response")
#: Keys whose content makes an envelope non-empty.
ROW_KEYS = ("items", "answers", "response", "groups", "summary_items", "drill_rows", "attachments", "action_links")
FIXED_ERROR = "The tool failed."
FIXED_TIMEOUT = "The tool did not answer in time."
#: What `crm_resolve` may search, the slug the user needs for each kind, and the contact reveal
#: a kind also needs.
KIND_SLUGS: dict[str, str] = {
    "product": "master_data.products.view",
    "supplier": "procurement.suppliers.view",
    "brand": "master_data.brands.view",
    "customer": "order_management.customers.view",
    "category": "master_data.product_categories.view",
    "sales_agent": "master_data.sales_agents.view",
}
KIND_CONTACT_GRANTS: dict[str, str] = {"supplier": "purchase_orders.supplier"}
#: Resolver entity types that stand for one of our kinds.
_KIND_OF_ENTITY: dict[str, str] = {**{k: k for k in KIND_SLUGS}, "product_set": "product"}
#: Kinds with no probe in the entity resolver. They are read from the bot's own closed lists
#: (`head/lookup_lists` rows scored by `head/list_resolver`): our kind -> the list's name.
LIST_KINDS: dict[str, str] = {"brand": "brand", "category": "category", "sales_agent": "salesperson"}
MAX_TERMS = 10
MAX_MATCHES = 5
MAX_PRODUCTS = 50
MAX_DETAIL_CHARS = 200
NO_ROWS_MESSAGE = "No rows matched these filters."

#: Plain labels for a tool, for sentences the user reads.
TOOL_LABELS: dict[str, str] = {
    "crm_report_ask": "sales and outstanding figures",
    "crm_inventory_stock_balance_list": "stock on hand",
    "crm_incoming_stock_by_product": "incoming stock",
    "crm_incoming_stock_shipments": "incoming shipments",
    "crm_procurement_grn_summary": "goods received",
    "crm_procurement_po_last_cost_list": "last purchase cost",
    "crm_procurement_po_placed_list": "purchase orders placed",
    "crm_procurement_spo_allocations_last_receipt_list": "last receipt",
    "crm_order_management_orders_by_product_list": "orders by product",
    "crm_resolve": "finding names and codes",
    "crm_products_find": "finding products",
    "crm_knowledge_search": "searching company documents",
    "user_guides_read": "reading the CRM user guides",
    "crm_customer_asks_list": "your customer asks",
    "crm_customer_ask_update": "change a customer ask",
    "crm_opportunities_list": "your sales opportunities",
    "crm_opportunity_meta": "opportunity stages",
    "crm_opportunity_create": "create an opportunity",
    "crm_opportunity_update": "change an opportunity",
    "crm_contacts_find": "finding dealer contacts",
    "crm_contact_access_update": "change a dealer contact",
    "crm_purchase_requests_list": "purchase requests and sponsorship forms",
    "crm_purchase_request_decide": "approve or reject a purchase request",
    "crm_purchase_request_action_undo": "take back a purchase request action",
    "crm_agent_actions_recent": "recent changes",
    "confirm_action": "confirm the waiting change",
    "cancel_action": "cancel the waiting change",
}
FIXED_NOT_ENVELOPE = "The tool returned an unexpected shape, so its data was not used."


@dataclass
class ToolResult:
    status: str  # "ok" | "denied" | "invalid" | "error" | "timeout"
    data: Any = None
    more: int = 0
    message: str = ""

    def to_json(self, call_id: str | None = None) -> str:
        body: dict[str, Any] = {"status": self.status, "data": self.data, "more": self.more, "message": self.message}
        if call_id:
            body["call_id"] = call_id  # the model cites this in the answer tool
        return json.dumps(body, default=str)


def tool_schemas(tools: list[ToolDef], catalog: dict[str, dict]) -> list[dict]:
    """OpenAI-style function tools for `tools`, from the MCP catalogue, guards stripped."""
    out: list[dict] = []
    for tool in tools:
        if tool.name == RESOLVE:
            out.append(copy.deepcopy(RESOLVE_SCHEMA))
            continue
        if tool.name == FIND:
            out.append(copy.deepcopy(FIND_SCHEMA))
            continue
        if tool.name == KNOWLEDGE:
            out.append(copy.deepcopy(KNOWLEDGE_SCHEMA))
            continue
        meta = catalog.get(tool.name)
        if not isinstance(meta, dict):
            continue
        schema = mcp_schema_to_openai_tool(tool.name, meta)
        params = schema["function"]["parameters"]
        if tool.name == GUIDES:
            # Only the question: the contact and space are never part of a guide search.
            params["properties"] = {k: v for k, v in params["properties"].items() if k == "query"}
            params["required"] = ["query"]
        # The model never chooses the view: dispatch always sends render.
        params["properties"] = {k: v for k, v in params["properties"].items() if k != VIEW_PARAM}
        params["required"] = [r for r in params.get("required") or [] if r != VIEW_PARAM]
        out.append(schema)
    return out


RESOLVE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RESOLVE,
        "description": (
            "Turn names and codes (product codes, suppliers, brands, customers, categories, sales "
            "agents) into ids. Call this before any tool that takes an id, and pass only the ids it "
            "returns. A term comes back found, ambiguous (ask which one) or not_found."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "terms": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_TERMS},
                "kinds": {"type": "array", "items": {"type": "string", "enum": list(KIND_SLUGS)}},
            },
            "required": ["terms"],
        },
    },
}

FIND_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": FIND,
        "description": (
            "List products of a brand and/or category (and/or whose code or name contains a query). "
            "brand_ids and category_ids must be ids from crm_resolve. Returns at most 50 products with "
            "their ids, so you can pass those ids to the stock and incoming tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "brand_ids": {"type": "array", "items": {"type": "string"}},
                "category_ids": {"type": "array", "items": {"type": "string"}},
                "query": {"type": "string"},
                "active_only": {"type": "boolean"},
            },
        },
    },
}

KNOWLEDGE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": KNOWLEDGE,
        "description": (
            "Search the company's uploaded documents (policies, handbooks, product documents) for "
            "passages that answer a question. Returns passages with their document, page and text, and "
            "the team to refer the user to when nothing matches."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The question, in the user's words."}},
            "required": ["query"],
        },
    },
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": PLAN,
        "description": (
            "For a question with more than one part, call this first with each part as a short "
            "string. Calling it again replaces the plan. It does not read anything."
        ),
        "parameters": {
            "type": "object",
            "properties": {"parts": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10}},
            "required": ["parts"],
        },
    },
}

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": ANSWER,
        "description": (
            "Finish the turn with the reply for the user. Every number in text must appear in a tool "
            "result of this turn (list it in figures with the call_id when you can). Anything you could "
            "not find goes in not_found with the call_id that showed it, the parts of your plan you "
            "answered go in answered, and anything you did not check goes in not_checked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "figures": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}, "call_id": {"type": "string"}},
                        "required": ["value", "call_id"],
                    },
                },
                "not_found": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"what": {"type": "string"}, "call_id": {"type": "string"}},
                        "required": ["what", "call_id"],
                    },
                },
                "not_checked": {"type": "array", "items": {"type": "string"}},
                "answered": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text"],
        },
    },
}


def user_may_use(db: Any, ctx: Any, tool: ToolDef) -> bool:
    """Does the linked user hold what the tool needs (for `crm_resolve`: any searchable kind)."""
    if tool.name == RESOLVE:
        return bool(searchable_kinds(db, ctx, list(KIND_SLUGS))[0])
    if tool.name == GUIDES:
        return True
    if not _permitted(db, ctx.user_id, tool.user_permission):
        return False
    if tool.name == KNOWLEDGE:
        return _operator_may_read(db, ctx, tool.user_permission)
    return True


def _operator_may_read(db: Any, ctx: Any, slug: str) -> bool:
    """The console operator acting for the linked user must hold the slug too (when there is one)."""
    operator = getattr(ctx, "operator_user_id", None)
    return not operator or _permitted(db, operator, slug)


def trace_safe(name: str, data: Any) -> Any:
    """`data` in the form a stored trace may keep: `crm_knowledge_search` passages lose their text
    (company documents), keeping document, page and heading. Other tools are returned unchanged.
    The live result the model reads is never mutated."""
    if name != KNOWLEDGE or not isinstance(data, dict):
        return data
    out = dict(data)
    out["passages"] = [
        {k: v for k, v in p.items() if k != "text"} if isinstance(p, dict) else p
        for p in data.get("passages") or []
    ]
    return out


def searchable_kinds(db: Any, ctx: Any, requested: list[str]) -> tuple[list[str], list[str]]:
    """(kinds that may be searched, kinds left out): the user's slug now, and the contact's reveal."""
    allowed, skipped = [], []
    for kind in requested:
        grant = KIND_CONTACT_GRANTS.get(kind)
        if _permitted(db, ctx.user_id, KIND_SLUGS[kind]) and (grant is None or grant in ctx.grants):
            allowed.append(kind)
        else:
            skipped.append(kind)
    return allowed, skipped


def contact_allows(ctx: Any, tool: ToolDef) -> bool:
    """The contact side of a tool: its reveal grant, and the stock switch for stock tools."""
    if tool.contact_grant and tool.contact_grant not in ctx.grants:
        return False
    if tool.name in STOCK_TOOLS and not getattr(ctx, "stock_allowed", True):
        return False
    return True


def _arg_value(args: dict, key: str) -> str:
    value = args.get(key)
    return value.strip().lower() if isinstance(value, str) else ""


def _gated_keys() -> set[str]:
    return {k for k, _ in ARG_PERMISSIONS} | {k for k, _ in ARG_CONTACT_GRANTS}


def _plain_string(value: Any) -> bool:
    """A gated argument must be one plain string: a list, a number or a JSON-looking string
    could carry the gated value past the comparison."""
    return isinstance(value, str) and not value.strip().startswith(("[", "{"))


def clip_args(args: Any, limit: int = 500) -> Any:
    """`args` as stored in the digest and the trace: at most `limit` characters of JSON."""
    try:
        raw = json.dumps(args, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"_unreadable": True}
    return args if len(raw) <= limit else {"_clipped": raw[:limit]}

def _permitted(db: Any, user_id: str, slug: str) -> bool:
    from app.services.user_service import UserPermissionService

    try:
        return bool(UserPermissionService(db).check_user_has_permission(user_id, slug))
    except Exception:  # noqa: BLE001 - a failed check is a refusal, never a pass
        logger.warning("agent: permission check failed for %s", slug, exc_info=True)
        return False


def _as_data(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return copy.deepcopy(raw)


def _size(data: Any) -> int:
    return len(json.dumps(data, default=str))


def cap_result(data: Any, limit: int = RESULT_CHAR_CAP) -> tuple[Any, int]:
    """`data` under `limit` characters of JSON. List values are cut by whole items from the
    back, largest list first; the second value counts the items cut."""
    if _size(data) <= limit:
        return data, 0
    more = 0
    if isinstance(data, list):
        holder: dict[str, Any] = {"v": data}
        shaped, more = cap_result(holder, limit)
        return shaped["v"], more
    if isinstance(data, dict):
        lists = sorted(
            (k for k, v in data.items() if isinstance(v, list) and v),
            key=lambda k: -len(data[k]),
        )
        for key in lists:
            if _size(data) <= limit:
                break
            rows = data[key]
            lo, hi = 0, len(rows)  # largest k with rows[:k] fitting
            while lo < hi:
                mid = (lo + hi + 1) // 2
                data[key] = rows[:mid]
                if _size(data) <= limit:
                    lo = mid
                else:
                    hi = mid - 1
            data[key] = rows[:lo]
            more += len(rows) - lo
    if _size(data) > limit:
        # Nothing left to cut by whole items: say so rather than cut a row in half.
        return {"truncated": True, "note": "result too large to show"}, more
    return data, more


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_URL = re.compile(r"\bhttps?://\S+", re.I)
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
_HOST = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+){2,}\b", re.I)
_HOST_PORT = re.compile(r"\b[\w.-]*[A-Za-z_][\w.-]*:\d{2,5}\b")
_PATH = re.compile(r"\S*/api/v\d\S*")
_HTTP_ERR = re.compile(r"returned HTTP (\d{3})\s*:?\s*(.*)", re.S)


def _id_args(args: dict) -> dict[str, list[Any]]:
    """The arguments that carry ids (`*_id` / `*_ids`, not the injected guards), as lists of values."""
    out: dict[str, list[Any]] = {}
    for key, value in args.items():
        if key in GUARD_PARAMS or not (key.endswith("_id") or key.endswith("_ids")):
            continue
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",")]
        elif not isinstance(value, list):
            value = [value]
        out[key] = [v for v in value if v not in (None, "")]
    return out


def _collect_uuids(data: Any, seen: set[str]) -> None:
    """Every UUID value in an ok result (not keys) is an id the model has been shown this turn."""
    if isinstance(data, dict):
        for v in data.values():
            _collect_uuids(v, seen)
    elif isinstance(data, list):
        for v in data:
            _collect_uuids(v, seen)
    elif isinstance(data, str) and _UUID.match(data.strip()):
        seen.add(data.strip().lower())


def _check_ids(args: dict, seen: set[str]) -> ToolResult | None:
    for key, values in _id_args(args).items():
        for value in values:
            if not (isinstance(value, str) and _UUID.match(value.strip())):
                return ToolResult(
                    "invalid", message=f"`{key}` takes ids from crm_resolve, not codes or names (`{value}`)."
                )
            if value.strip().lower() not in seen:
                return ToolResult("invalid", message=f"Unknown id in `{key}`; get ids from crm_resolve first.")
    return None


def clean_detail(text: Any) -> str:
    """A route's own detail text with URLs, hosts and paths removed, at most 200 characters."""
    out = str(text or "")
    for pattern in (_URL, _PATH, _IPV4, _HOST_PORT, _HOST):
        out = pattern.sub("", out)
    return re.sub(r"\s+", " ", out).strip()[:MAX_DETAIL_CHARS]


def _http_failure(status: int, detail: Any) -> ToolResult:
    if status == 403:
        # The route refused this contact or user: a denial, not a bad request.
        return ToolResult("denied", message=clean_detail(detail) or "The route refused this request.")
    if 400 <= status < 500:
        return ToolResult("invalid", message=clean_detail(detail) or "The request was rejected.")
    return ToolResult("error", message=FIXED_ERROR)


def _body_failure(data: Any) -> ToolResult | None:
    """A route's non-2xx answer carried back as data (`status_code` on the body)."""
    if not (isinstance(data, dict) and isinstance(data.get("status_code"), int) and data["status_code"] >= 400):
        return None
    detail = data.get("detail")
    if isinstance(detail, dict):
        detail = detail.get("detail") or detail.get("message")
    if not isinstance(detail, str) or not detail.strip():
        match = _HTTP_ERR.search(str(data.get("http_error") or data.get("error") or ""))
        detail = match.group(2) if match else ""
    return _http_failure(int(data["status_code"]), detail)


def _has_rows(data: dict) -> bool:
    return any(bool(data.get(k)) for k in ROW_KEYS)


def _is_empty(data: Any, render: bool) -> bool:
    if not isinstance(data, dict):
        return False
    if render:
        return data.get("has_result") is False or not _has_rows(data)
    return data.get("empty") is True or (isinstance(data.get("data"), list) and not data["data"])


def _fold_code(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def redact_ids(text: str, ids: tuple[str, ...]) -> str:
    """`text` without the given ids (the contact's own): each becomes "(id)"."""
    for ident in ids:
        ident = str(ident or "").strip()
        if len(ident) >= 6:  # a shorter value is as likely a quantity as an id
            text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(ident)}(?![A-Za-z0-9])", "(id)", text)
    return text


def _strip_echo(data: Any, ids: tuple[str, ...], space_id: str | None) -> Any:
    """Drop the echoes of the injected guard values from a result before the model sees it."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if k in ("contact_id", "contact_respond_id") and isinstance(v, (str, int)) and str(v) in ids:
                continue
            if k == "space_id" and space_id is not None and str(v) == str(space_id):
                continue
            out[k] = _strip_echo(v, ids, space_id)
        return out
    if isinstance(data, list):
        return [_strip_echo(v, ids, space_id) for v in data]
    if isinstance(data, str):
        return redact_ids(data, ids)
    return data


def _sees_salespeople(db: Any, ctx: Any) -> bool:
    """The Salesperson list is the contact's only when the sales ranking lets it ask by agent
    (the rule today's lookup block uses)."""
    from app.services import contact_asker

    try:
        granted = "sales_orders.sales_report" in ctx.grants
        return contact_asker.may_ask_sales_ranking(db, str(ctx.contact_pk), granted=granted)[0] != "not_granted"
    except Exception:  # noqa: BLE001 - fail closed
        logger.warning("agent: salesperson visibility check failed", exc_info=True)
        return False


def _list_matches(db: Any, ctx: Any, terms: list[str], kinds: list[str]) -> dict[str, list[dict]]:
    """Brand, category and sales agent matches per term: the contact's visible rows of those
    closed lists (company scope from the session, brand scope from the context), each term
    scored the way the bot scores a span (exact, spelling, partial; no embedder)."""
    from app.services.chatbot.head import list_resolver, lookup_lists

    names = {LIST_KINDS[k]: k for k in kinds}
    rows = [
        r for r in lookup_lists.load_rows(db, include_salespeople="sales_agent" in kinds)
        if r.list_name in names and not str(r.key).startswith("type:")
    ]
    if ctx.brand_scope is not None:
        from app.services.contact_brand_scope import scope_brand_ids

        # A scope holding only item class tokens limits classes, not brands: every brand stays.
        brands = scope_brand_ids(ctx.brand_scope)
        if brands:
            rows = [r for r in rows if r.list_name != "brand" or str(r.key) in brands]
    out: dict[str, list[dict]] = {t: [] for t in terms}
    if not rows:
        return out
    resolutions = list_resolver.resolve([list_resolver.Span(t) for t in terms], rows, embed=None)
    for term, res in zip(terms, resolutions):
        if res.status not in ("resolved", "ambiguous"):
            continue
        for cand in res.candidates:
            row = cand.row
            homes = row.homes or ()
            texts = row.texts or ()
            label = next((t for t, h in zip(texts, homes) if h == "label"), None) or row.label
            code = next((t for t, h in zip(texts, homes) if h == "code"), None)
            out[term].append({"id": str(row.key), "kind": names[row.list_name], "code": code, "name": label})
    return out


def _resolve(db: Any, ctx: Any, args: dict, seen: set[str]) -> ToolResult:
    """`crm_resolve`: the bot's own resolver, in process, under the contact's scope."""
    from app.models.base import get_company_scope
    from app.services.chatbot.lanes.business import services as business_services

    unknown = sorted(k for k in args if k not in ("terms", "kinds") and k not in GUARD_PARAMS and k != VIEW_PARAM)
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    terms = args.get("terms")
    if not (isinstance(terms, list) and 1 <= len(terms) <= MAX_TERMS and all(isinstance(t, str) and t.strip() for t in terms)):
        return ToolResult("invalid", message=f"terms must be 1 to {MAX_TERMS} non-empty strings.")
    kinds = args.get("kinds")
    if kinds is None:
        requested = list(KIND_SLUGS)
    elif isinstance(kinds, list) and kinds and all(isinstance(k, str) and k in KIND_SLUGS for k in kinds):
        requested = list(dict.fromkeys(kinds))
    else:
        return ToolResult("invalid", message=f"kinds must be some of: {', '.join(KIND_SLUGS)}.")
    terms = [t.strip() for t in terms]

    allowed, skipped = searchable_kinds(db, ctx, requested)
    if "sales_agent" in allowed and not _sees_salespeople(db, ctx):
        allowed.remove("sales_agent")
        skipped.append("sales_agent")
    if not allowed:
        return ToolResult(
            "denied",
            data={"skipped_kinds": skipped},
            message=f"None of the requested kinds may be searched: {', '.join(skipped)}.",
        )
    entity_kinds = [k for k in allowed if k not in LIST_KINDS]
    list_kinds = [k for k in allowed if k in LIST_KINDS]
    by_token: dict[str, dict] = {}
    if entity_kinds:
        body = {"tokens": terms, "raw_tokens": terms, "allowed_entity_types": entity_kinds,
                "dry_run": True, "semantic_fallback": False}  # the code reader's LLM calls are not tracked
        try:
            raw = business_services._resolve_entity(db)(body)
        except Exception:  # noqa: BLE001
            logger.warning("agent: crm_resolve failed", exc_info=True)
            return ToolResult("error", message=FIXED_ERROR)
        resolutions = [r for r in (raw or {}).get("resolutions") or [] if isinstance(r, dict)]
        for index, term in enumerate(terms):
            match = next((r for r in resolutions if r.get("token") == term), None)
            by_token[term] = match if match is not None else (resolutions[index] if index < len(resolutions) else {})
    listed: dict[str, list[dict]] = {t: [] for t in terms}
    if list_kinds:
        try:
            listed = _list_matches(db, ctx, terms, list_kinds)
        except Exception:  # noqa: BLE001
            logger.warning("agent: crm_resolve list lookup failed", exc_info=True)
            return ToolResult("error", message=FIXED_ERROR)

    scope = get_company_scope(db) if db is not None else None
    has_company_scope = isinstance(scope, (set, frozenset)) and bool(scope)
    results = []
    for term in terms:
        res = by_token.get(term, {})
        matches = []
        for m in res.get("matches") or []:
            kind = _KIND_OF_ENTITY.get(str(m.get("entity_type") or ""))
            ident = m.get("uuid")
            if kind not in entity_kinds or not ident:
                continue
            display = m.get("display") if isinstance(m.get("display"), dict) else {}
            matches.append(
                {"id": str(ident), "kind": kind, "code": m.get("canonical_code"), "name": display.get("name")}
            )
        before = len(matches)
        customers = [m for m in matches if m["kind"] == "customer"]
        if customers:
            kept = business_services.readable_customers(
                db, [{"uuid": m["id"], "canonical_code": m["code"], "name": m["name"]} for m in customers],
                ctx.contact_respond_id, has_company_scope,
            )
            readable = {str(r.get("uuid")) for r in kept if isinstance(r, dict)}
            matches = [m for m in matches if m["kind"] != "customer" or m["id"] in readable]
        trusted = res.get("resolved") is True and res.get("ambiguous") is False and len(matches) == before
        matches = matches + listed.get(term, [])
        variants: list[dict] = []
        folded_term = _fold_code(term)
        exact = [m for m in matches if m.get("code") and _fold_code(str(m["code"])) == folded_term]
        if not matches:
            status = "not_found"
        elif len(exact) == 1:
            # The typed code is one product's own code: that one, and its variants beside it.
            status = "found"
            variants = [m for m in matches if m is not exact[0]][:MAX_MATCHES]
            matches = exact
        elif len(matches) == 1 or (trusted and len(listed.get(term, [])) == 0):
            status, matches = "found", matches[:1] if trusted else matches
        else:
            status = "ambiguous"
        matches = matches[:MAX_MATCHES]
        seen.update(m["id"].lower() for m in [*matches, *variants])
        row = {"term": term, "status": status, "matches": matches}
        if variants:
            row["variants"] = variants
        results.append(row)
    return ToolResult("ok", data={"results": results, "skipped_kinds": skipped})


def _find_products(db: Any, args: dict, seen: set[str]) -> ToolResult:
    """`crm_products_find`: products of the given brands / categories (one level of child
    categories) and/or a code or name query, on the agent session, so company scope and brand scope
    apply, under the chat visibility rule. At most 50 rows, ordered by code."""
    from sqlalchemy import case, func, or_, select

    from app.models.product import Brand, Product, ProductCategory, chat_searchable_products

    unknown = sorted(
        k for k in args
        if k not in ("brand_ids", "category_ids", "query", "active_only") and k not in GUARD_PARAMS and k != VIEW_PARAM
    )
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    lists: dict[str, list[str]] = {}
    for key in ("brand_ids", "category_ids"):
        value = args.get(key)
        if value is None:
            value = []
        if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            return ToolResult("invalid", message=f"{key} must be a list of ids from crm_resolve.")
        lists[key] = [v.strip() for v in value if v.strip()]
    query = args.get("query")
    if query is not None and not isinstance(query, str):
        return ToolResult("invalid", message="query must be text.")
    query = (query or "").strip()
    active_only = args.get("active_only", True)
    if not isinstance(active_only, bool):
        return ToolResult("invalid", message="active_only must be true or false.")
    if not (lists["brand_ids"] or lists["category_ids"] or query):
        return ToolResult("invalid", message="Give at least one of brand_ids, category_ids or query.")
    bad_id = _check_ids({k: v for k, v in lists.items() if v}, seen)
    if bad_id is not None:
        return bad_id

    q = db.query(Product).filter(chat_searchable_products())
    if active_only:
        q = q.filter(Product.is_active.is_(True))
    if lists["brand_ids"]:
        q = q.filter(Product.brand_id.in_(lists["brand_ids"]))
    if lists["category_ids"]:
        cats = ProductCategory.__table__
        children = select(cats.c.id).where(cats.c.parent_category_id.in_(lists["category_ids"]))
        q = q.filter(or_(Product.category_id.in_(lists["category_ids"]), Product.category_id.in_(children)))
    def _escaped(text: str) -> str:
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    for word in query.split():
        like = "%" + _escaped(word) + "%"
        # Every word must match somewhere: code, name or description (not the internal remark).
        q = q.filter(
            or_(
                Product.product_code.ilike(like, escape="\\"),
                Product.product_name.ilike(like, escape="\\"),
                Product.description.ilike(like, escape="\\"),
            )
        )
    total = q.count()
    order = [Product.product_code]
    if query:
        # Exact code first, then codes that start with the query, then the rest by code.
        order.insert(
            0,
            case(
                (func.lower(Product.product_code) == query.lower(), 0),
                (Product.product_code.ilike(_escaped(query) + "%", escape="\\"), 1),
                else_=2,
            ),
        )
    rows = q.order_by(*order).limit(MAX_PRODUCTS).all()
    if not rows:
        filters = {k: v for k, v in {**lists, "query": query, "active_only": active_only}.items() if v not in ([], "")}
        return ToolResult("empty", data={"applied_filters": filters}, message=NO_ROWS_MESSAGE)
    brand_names = {
        str(b.id): b.brand_name
        for b in db.query(Brand).filter(Brand.id.in_({r.brand_id for r in rows if r.brand_id})).all()
    }
    cats = ProductCategory.__table__
    category_names = {
        str(i): n
        for i, n in db.execute(select(cats.c.id, cats.c.category_name).where(cats.c.id.in_({r.category_id for r in rows})))
    }
    products = [
        {
            "id": str(r.id),
            "code": r.product_code,
            "name": r.product_name,
            "brand": brand_names.get(str(r.brand_id)) if r.brand_id else None,
            "category": category_names.get(str(r.category_id)),
        }
        for r in rows
    ]
    seen.update(p["id"].lower() for p in products)
    return ToolResult("ok", data={"products": products, "more": total - len(products)}, more=total - len(products))


def _search_in_scope(db: Any, ctx: Any, query: str) -> dict:
    """The knowledge search under the contact's company scope (already on the session) narrowed by
    the own scope of the linked user and of the console operator, so a person never reads a
    company their own session could not. The session scope comes back afterwards."""
    from app.models.base import UNSET, get_company_scope, set_company_scope
    from app.services import company_scope_resolver, knowledge_service
    from app.services.chatbot.agent import writes

    previous = get_company_scope(db)
    scope = previous
    for person in writes.people(ctx):
        own = company_scope_resolver._scope_for_user(db, person, None)
        if scope is None:  # the contact is unrestricted: the person's scope is the bound
            scope = own
        elif own is None:
            pass
        elif scope is UNSET or own is UNSET:
            scope = UNSET
        else:
            scope = frozenset(scope) & frozenset(own)
    set_company_scope(db, scope)
    try:
        return knowledge_service.search(db, user_id=ctx.user_id, query=query)
    finally:
        set_company_scope(db, previous)


def _knowledge_search(db: Any, ctx: Any, args: dict) -> ToolResult:
    """`crm_knowledge_search`: passages of uploaded documents for the turn's linked user, in process."""
    from app.services import knowledge_service

    unknown = sorted(k for k in args if k != "query" and k not in GUARD_PARAMS and k != VIEW_PARAM)
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult("invalid", message="query must be the question, as text.")
    if not _operator_may_read(db, ctx, REGISTRY[KNOWLEDGE].user_permission):
        return ToolResult("denied", message=f"{KNOWLEDGE} is outside this operator's access.")
    try:
        found = _search_in_scope(db, ctx, query.strip())
    except Exception:  # noqa: BLE001 - a tool failure is a result the model can work around
        logger.warning("agent: %s failed", KNOWLEDGE, exc_info=True)
        return ToolResult("error", message=FIXED_ERROR)
    status = found.get("status")
    if status == "denied":
        return ToolResult("denied", message=f"{KNOWLEDGE} is outside this user's access.")
    if status != "ok":
        return ToolResult("error", message=FIXED_ERROR)
    data = {"passages": found.get("passages", []), "handoff_teams": found.get("handoff_teams", [])}
    return ToolResult("ok", data=data)


DENIED_TAIL = "Do not get this information another way."
SALES_BASIS_MESSAGE = (
    "Say which sales basis: ask the user (invoiced is the usual one) or call once per basis "
    "(invoiced, delivered, ordered) and label each."
)
#: Bases that are not sales figures: they need no sales basis, and are their own data domain.
OUTSTANDING_BASES = frozenset({"outstanding", "pending_delivery", "unpaid"})


def data_domain(name: Any, args: Any) -> str | None:
    """The data domain a call reads, for "refused stays refused": the sales figures (the report on a
    sales basis, and the orders-by-product totals), receivables / outstanding, and the chat analytics."""
    if name == "crm_report_ask" and isinstance(args, dict):
        if _arg_value(args, "dataset") == "chat":
            return "chat"
        if _arg_value(args, "basis") in OUTSTANDING_BASES:
            return "outstanding"
        return "sales"
    if name == "crm_order_management_orders_by_product_list":
        return "sales"
    return None


def dispatch(
    db: Any,
    ctx: Any,
    name: str,
    args: Any,
    *,
    call: Callable[[str, dict], Any],
    catalog: dict[str, dict],
    timeout: float,
    seen_ids: set[str] | None = None,
    denied_domains: set[str] | None = None,
) -> ToolResult:
    """`_dispatch_inner`, plus the turn's memory of what was refused: once a data domain is denied,
    a later call to the same domain is denied too, and a denial tells the model not to go around it.
    `denied_domains` is kept by the caller for the whole turn."""
    domains = denied_domains if denied_domains is not None else set()
    domain = data_domain(name, args)
    if domain is not None and domain in domains:
        return ToolResult("denied", message=f"This data was refused earlier in this turn. {DENIED_TAIL}")
    out = _dispatch_inner(db, ctx, name, args, call=call, catalog=catalog, timeout=timeout, seen_ids=seen_ids)
    if out.status == "denied":
        if domain is not None:
            domains.add(domain)
        if DENIED_TAIL not in out.message:
            out.message = f"{out.message.rstrip()} {DENIED_TAIL}".strip()
    return out


def _dispatch_inner(
    db: Any,
    ctx: Any,
    name: str,
    args: Any,
    *,
    call: Callable[[str, dict], Any],
    catalog: dict[str, dict],
    timeout: float,
    seen_ids: set[str] | None = None,
) -> ToolResult:
    """One tool call, checked in the order the contract names. Never raises.

    `seen_ids` is the set of ids this turn's `crm_resolve` results produced (lower case); the
    caller keeps it for the whole turn. Left out, no id is known and every id argument is refused."""
    from app.services.chatbot.lanes.business.fetch import ToolNotAllowed, drop_restricted_fields
    from app.services.llm_provider import is_timeout

    seen = seen_ids if seen_ids is not None else set()
    tool = REGISTRY.get(name) if isinstance(name, str) else None
    if tool is None:
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    if tool.name not in (RESOLVE, GUIDES) and not _permitted(db, ctx.user_id, tool.user_permission):
        return ToolResult("denied", message=f"{name} is outside this user's access.")
    if not contact_allows(ctx, tool):
        return ToolResult("denied", message=f"{name} is outside this contact's access.")
    if not isinstance(args, dict):
        return ToolResult("invalid", message="Arguments must be an object of named values.")
    if tool.name == RESOLVE:
        return _resolve(db, ctx, args, seen)
    if tool.name == FIND:
        return _find_products(db, args, seen)
    if tool.name == KNOWLEDGE:
        return _knowledge_search(db, ctx, args)
    meta = catalog.get(name)
    if not isinstance(meta, dict):
        return ToolResult("error", message=f"{name} is not available right now.")
    schema = meta.get("inputSchema") if isinstance(meta.get("inputSchema"), dict) else {}
    allowed = set((schema.get("properties") or {}).keys()) | set(GUARD_PARAMS) | {VIEW_PARAM}
    if tool.name == GUIDES:
        # A model-supplied contact or space is dropped, never forwarded.
        args = {k: v for k, v in args.items() if k not in GUARD_PARAMS and k != VIEW_PARAM}
        allowed = {"query"}
    unknown = sorted(k for k in args if k not in allowed)
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")

    if name == "crm_report_ask":
        args = {k: v for k, v in args.items() if not (k in _gated_keys() and v is None)}
        for key in _gated_keys():
            if key in args and not _plain_string(args[key]):
                return ToolResult("invalid", message=f"{key} must be a single plain value.")
        for (key, value), slug in ARG_PERMISSIONS.items():
            if _arg_value(args, key) == value and not _permitted(db, ctx.user_id, slug):
                return ToolResult("denied", message=f"{key}={value} is outside this user's access.")
        for (key, value), grant in ARG_CONTACT_GRANTS.items():
            if _arg_value(args, key) == value and grant not in ctx.grants:
                return ToolResult("denied", message=f"{key}={value} is outside this contact's access.")

    if name == "crm_report_ask" and _arg_value(args, "dataset") != "chat" and not _arg_value(args, "basis"):
        # Owner rule: the sales basis is never defaulted (an outstanding kind is a basis of its own).
        return ToolResult("invalid", message=SALES_BASIS_MESSAGE)

    bad_id = _check_ids(args, seen)
    if bad_id is not None:
        return bad_id

    clean = {k: v for k, v in args.items() if k not in GUARD_PARAMS and k != VIEW_PARAM}
    if SELLABLE_GRANT not in ctx.grants:
        clean.pop(SELLABLE_PARAM, None)
    filters = dict(clean)
    if tool.name != GUIDES:
        clean["contact_id"] = ctx.contact_respond_id
        if ctx.space_id is not None:
            clean["space_id"] = ctx.space_id
    # Only the render view carries `restricted_fields`, which the field drop below relies on.
    if tool.render:
        clean[VIEW_PARAM] = "render"

    try:
        raw = call(name, clean)
    except ToolNotAllowed as exc:
        return ToolResult("denied", message=str(exc) or f"{name} is not allowed for this contact.")
    except TimeoutError:
        return ToolResult("timeout", message=FIXED_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - a tool failure is a result the model can work around
        if is_timeout(exc):
            return ToolResult("timeout", message=FIXED_TIMEOUT)
        logger.warning("agent: tool %s failed", name, exc_info=True)
        match = _HTTP_ERR.search(str(exc))
        if match and match.group(1).startswith("4"):
            return _http_failure(int(match.group(1)), match.group(2))
        return ToolResult("error", message=FIXED_ERROR)

    data = _strip_echo(_as_data(raw), (str(ctx.contact_respond_id), str(ctx.contact_pk)), ctx.space_id)
    failure = _body_failure(data)
    if failure is not None:
        return failure
    if tool.render:
        # Fail closed: a presenter tool's result that is not a render envelope has not been
        # through the presenter, so nothing in it can be trusted to be field-scoped.
        if not (isinstance(data, dict) and any(k in data for k in ENVELOPE_KEYS)):
            logger.warning("agent: %s returned a non-envelope result", name)
            return ToolResult("error", message=FIXED_NOT_ENVELOPE)
        axis = clean.get("group_by")
        drop_restricted_fields(data, set(ctx.grants), axis if isinstance(axis, str) else None)
    if _is_empty(data, tool.render):
        return ToolResult("empty", data={"applied_filters": filters}, message=NO_ROWS_MESSAGE)
    data, more = cap_result(data)
    _collect_uuids(data, seen)
    return ToolResult("ok", data=data, more=more)
