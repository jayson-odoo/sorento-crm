"""The `sales_ranking` ask: sales ranked or totalled by one dimension (REPORT-ENGINE slice 1b).

`documentation/plans/chatbot/PLAN-report-engine.md` section 11. The lane half of
`crm_report_ask` (`GET /api/v1/order-management/report-ask`): every gate (grant, audience,
company, location policy) is the ROUTE's, from `contact_id`; this module only turns the
parser's reading into the route's params, and asks for the two fields the route requires
(the period and how many, then, for a ranking, the metric, and always the basis) through the
shared `required_fields` helper. A ranking never defaults the metric or the basis: it asks
(owner ruling, 4 Oct 2026), through `ranking_ask.next_question`.

* `take_words` (engine seam): a FRESH ask's brand, sales agent and category words come off
  the entity list onto `report_ask_words`, so the generic resolver never reads them as
  customers (it types a brand or a person under `order` as a customer).
* `settle` (lane): words to ids, `group_by` to the catalogue's word, the required fields;
  either a line to send instead of running, or the outcome to build the args from.
* `route_args`: the settled outcome as the route's query params.
* `error_line`: a route refusal (403) or a 404, said as one line.
"""
from __future__ import annotations

from app.utils.date_format import fmt_date, fmt_date_range
from datetime import date
from typing import Any

from app.services.chatbot import contracts, jsc
from app.services.chatbot import principal as staff_principal
from app.services.chatbot import required_fields as rf
from app.services.reports import ask as reports_ask
from app.services.sales_report_service import TOP_SELLING_N_CEILING
from app.services.chatbot.lanes.business import ranking_ask
from app.services.chatbot.lanes.business import services as business_services

ASK_NAME = "sales_ranking"
TOOL = "crm_report_ask"

PERIOD_QUESTION = "Which period? For example this month, September, 2026, or 1 to 15 Sep."
TOP_N_QUESTION = "How many? For example top 5."
#: Said above the ranking that ran with the default count after two unreadable replies.
DEFAULT_TOP_N = 10
DEFAULT_TOP_N_NOTE = "I couldn't read how many, so here is the top 10."
CANCELLED = "Sales ranking cancelled."
GIVE_UP = (
    "I still can't read '{word}'. Ask again in one message, "
    "e.g. top 5 sales agents for Sorento this month by amount, delivered."
)
#: The route's own refusal for a dealer's staff breakdown (`report_ask._DEALER_MESSAGE`).
DEALER_REFUSAL = "That breakdown is not available for your account."
#: An axis the report ask cannot draw (the Yearly comparison, axis year, is the one other tool): said, nothing fetched.
UNSUPPORTED_AXIS_LINE = (
    "I can't break sales down by {axis}. I can break sales down by customer, product, brand, category, sales agent, "
    "location, channel or month."
)
CATALOGUE_LINE = (
    "I can rank sales by customer, product, brand, category, sales agent, location, channel or month."
)

#: The parser's `group_by` -> the route's (`reports.ask.DIMENSIONS`). Anything else, `date`
#: included, is outside the catalogue and is said, never guessed.
GROUP_BY = {
    "customer": "customer",
    "product": "product",
    "brand": "brand",
    "category": "category",
    "sales_agent": "sales_agent",
    "warehouse": "location",
    "location": "location",
    "channel": "channel",
    "account_type": "account_type",
    "month": "month",
    "year": "year",
}

#: The parser's other report types (`order_status`): one that fills no open field of the sales
#: ranking question is a new ask, not its answer (chat fix PR-B S2c, `names_its_own_ask`).
OTHER_REPORTS = frozenset({"top_selling", "sales_report", "sales_analysis", "outstanding"})

#: The entity hints `take_words` moves, and the noun each is said with when it names nothing.
WORD_HINTS = {"brand": "brand", "sales_agent": "sales agent", "category": "category", "account_type": "account type"}

#: One ceiling, shared with the routes (owner, 30 Sep 2026).
TOP_N_MIN, TOP_N_MAX = 1, TOP_SELLING_N_CEILING
#: Said above a ranking whose named N passed the ceiling (owner, 30 Sep 2026: no 100 cap, and
#: no silent clamp either). It promises no count: fewer items than the ceiling may have sold.
CEILING_NOTE = f"I can list at most the top {TOP_N_MAX:,} in one reply."
#: A month breakdown is a trend, never asked "How many?": every month of the period (1b code
#: review S2). This is its own row count, not a second top-N limit.
MONTH_TOP_N = 100
#: The axes that are a run of time: a trend lists every bucket, oldest first, and shows both measures.
TREND_AXES = ("month", "year")

#: The plural each word hint's "matches several" line names (1b code review S3).
SEVERAL_NOUNS = {"brand": "brands", "category": "categories"}

#: REPORT-DRILLDOWN (`documentation/plans/chatbot/PLAN-report-drilldown-08oct.md`): a ranking
#: of the rows the last ranking printed. The nouns each axis is said with, one and several.
AXIS_NOUNS = {
    "customer": ("customer", "customers"),
    "product": ("product", "products"),
    "brand": ("brand", "brands"),
    "category": ("category", "categories"),
    "sales_agent": ("sales agent", "sales agents"),
    "location": ("location", "locations"),
    "channel": ("channel", "channels"),
    "account_type": ("account type", "account types"),
    "month": ("month", "months"),
    "year": ("year", "years"),
}
#: Said when a drill names rows ("these agents") and no ranking is held: never a guess.
NO_RANKING_LINE = (
    "I don't have a ranking to take those from. "
    "Ask the ranking first, for example top 5 sales agents for a product this year."
)
#: A channel or a month list is not a drill source: those are named in words.
NOT_A_SOURCE_LINES = {
    "month": "I can't narrow by the months above. Name the period instead, for example September.",
    "year": "I can't narrow by the years above. Name the period instead, for example 2026.",
    "channel": "I can't narrow by the channels above. Name the channel instead, for example dealer only.",
}
#: The route's per-filter cap (`order_management/report_ask._MAX_VALUES`).
DRILL_MAX_KEYS = 50
TOO_MANY_LINE = "That is more than {max} {plural} to narrow by. Ask for the top {max} or fewer first."
NO_KEYS_LINE = "I can't narrow by {name} above. Ask again naming the {plural} you want."
MIXED_PRODUCTS_LINE = "That matches several different products. Which product do you mean?"
NOT_IN_ROWS_LINE = "{name} is not one of the {plural} above."
SCOPE_GIVE_UP = (
    "I still can't tell which you meant. Ask again in one message, "
    "e.g. top 10 customers of these agents, or top 10 customers overall."
)
#: The route params that filter each axis's own dimension. A drill ranks ACROSS its target axis,
#: so a held filter on that same dimension is not carried (crew decision, 8 Oct 2026: "top 5
#: products these customers buy" after a ranking for one product lists every product).
_AXIS_FILTERS = {
    "product": ("product_code", "product_ids"),
    "customer": ("customer_ids",),
    "sales_agent": ("sales_agent_ids",),
    "brand": ("brand_ids",),
    "category": ("category_ids",),
    "location": ("warehouse_codes",),
    "channel": ("channel",),
    "account_type": ("account_types",),
    # Not an axis: what "every company" widens (`_widened`, owner O-R2), so the refine drops the held company too.
    "company": ("company",),
}
#: The frame keys that are not route params (`names`: the id -> name map of the semantic carry, `arg_names`).
_FRAME_ONLY = ("date_from", "date_to", "top_n", "shown", "stale", "names")


#: CHATBOT-TOTALS-FILTERS HT1-11: the values of the parser's entity key `said_as` (`parser.with_said_as`).
SAID_AS = ("company", "brand", "both")


def kind_was_said(value: Any) -> bool:
    """`kind_said` is the word of the message that says the kind: a non-blank string means said; null, blank or absent
    do not. (A bare true is still read as said.)"""
    return value is True or (isinstance(value, str) and bool(value.strip()))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


# --------------------------------------------------------------------------- #
# The required fields
# --------------------------------------------------------------------------- #


def _day(value: Any) -> date | None:
    text = jsc.js_string(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _label(d: date) -> str:
    return fmt_date(d)


#: REPORT-SMART-1021 step 5: said when the parser wrote the period in words ("SEP 2026"), not
#: as dates: asked, never run over a period nobody can read, never echoed back.
UNREADABLE_PERIOD_LINE = "I couldn't read that period. " + PERIOD_QUESTION


def unreadable_period(parse_output: dict[str, Any]) -> bool:
    """Did the parser fill a date field with something that is not a date?"""
    return any(
        jsc.truthy(parse_output.get(key)) and _day(parse_output.get(key)) is None
        for key in ("date_filter_start", "date_filter_end")
    )


def period_from(start: Any, end: Any) -> rf.Resolved | None:
    """The parser's two dates as the settled period. A start alone ("since September") runs
    to today, Malaysia time; an end alone is no period (1b code review N2: it is asked)."""
    from app.services.reports.registry import today_malaysia

    first, last = _day(start), _day(end)
    if first is None:
        return None
    if last is None:
        last = max(first, today_malaysia())
    if first > last:
        first, last = last, first
    return rf.Resolved(
        "ok", value={"from": first.isoformat(), "to": last.isoformat()}, label=fmt_date_range(first, last)
    )


def _resolve_period(_db: Any, _word: str, extras: dict[str, Any]) -> rf.Resolved:
    """An answering turn's period: the reply's OWN parsed dates (`settle` hands them in as
    `reply_dates`); a reply with no date is a miss."""
    dates = _dict(extras.get("reply_dates"))
    return period_from(dates.get("start"), dates.get("end")) or rf.Resolved("unknown")


def top_n_from(value: Any) -> rf.Resolved:
    if isinstance(value, bool):
        return rf.Resolved("unknown")
    if isinstance(value, (int, float)) and float(value).is_integer() and TOP_N_MIN <= int(value) <= TOP_N_MAX:
        return rf.Resolved("ok", value=int(value), label=str(int(value)))
    if isinstance(value, (int, float)) and float(value).is_integer() and value > TOP_N_MAX:
        return rf.Resolved("unknown", note=CEILING_NOTE)
    return rf.Resolved("unknown")


def _resolve_top_n(_db: Any, _word: str, extras: dict[str, Any]) -> rf.Resolved:
    """An answering turn's count: the PARSER's own `top_n` for the reply (`settle` hands it in
    as `reply_top_n`, as it does `reply_dates`); the reply's words are not looked at."""
    return top_n_from(extras.get("reply_top_n"))


#: The parser's keys for an answer to the metric question: `measure` (qty | amount) or the top
#: selling key `rank_by` (a bare reply under the question parses as a top selling reading).
METRIC_FROM_RANK_BY = {"quantity": "qty", "amount": "amount"}
#: The report ask's bases, in the order the basis question lists them (SALES-UNIFIED: invoiced
#: is the one sales definition, `reports.ask.CATALOGUE["sales"]["invoiced"]`).
BASES = ("invoiced", "delivered", "ordered", "outstanding", "pending_delivery", "unpaid")
#: REPORT-UNIFY (owner ruling Q2): the three things "outstanding" can mean, each a basis of the report ask.
#: Never defaulted: an outstanding ask whose parse names none is asked `KIND_QUESTION`. They take no period
#: (absent = every date).
OUTSTANDING_KINDS = ("outstanding", "pending_delivery", "unpaid")
#: Owner wording ruling (4 Nov, CHATBOT-TOTALS-FILTERS): the kinds by the document each lists.
KIND_QUESTION = "Sales order or delivery order?"
#: Owner 29 Oct (REPORT-OUTSTANDING-SUMMARY): "outstanding" means undelivered orders or pending delivery, never unpaid
#: invoices (only when the user names them). The kind question offers only the kinds the contact may see; a contact
#: that may see one (pending delivery without the Outstanding reveal, as before #1922) gets it with no question.
ASKED_KINDS = ("outstanding", "pending_delivery")
#: A kind never offered but taken when the user names it, a reply to the kind question included ("unpaid invoices").
NAMED_KINDS = ("unpaid",)
#: The parser's outstanding document statuses that already name their kind: a sales order backlog, a delivery
#: order backlog. `outstanding_both` and the bare `outstanding` name none.
STATUS_KIND = {"so_outstanding": "outstanding", "do_outstanding": "pending_delivery"}
OUTSTANDING_STATUSES = frozenset({"outstanding", "outstanding_both", *STATUS_KIND})
#: The measures the parser's `measure` may name: the two sums and (REPORT-SMART-1021) the
#: counts (`reports.ask.COUNT_MEASURES`: customers, orders, products).
METRICS = ("qty", "amount", "customers", "orders", "products")
#: REPORT-SMART-1021 step 4: what the parser's `compare_to` may name (`reports.ask.COMPARE_TO`).
COMPARE_TO = reports_ask.COMPARE_TO
#: Review S1: a month trend is not compared (its months never match the earlier window's).
COMPARE_BY_MONTH_LINE = (
    "I can't compare a month by month breakdown yet. Ask for the total, or split by another dimension."
)


def metric_from(parse_output: dict[str, Any]) -> str | None:
    """The metric the parser read: `measure`, else `rank_by` (quantity is qty); None if neither."""
    if parse_output.get("measure") in METRICS:
        return parse_output["measure"]
    return METRIC_FROM_RANK_BY.get(parse_output.get("rank_by"))


OUTSTANDING_GRANT = "sales_orders.outstanding"


def list_pick_kind(parse_output: dict[str, Any]) -> str | None:
    """The outstanding kind a "Reply 1 for the ... list" pick re-runs (`LIST_PICKS`), off the pick itself: the pick's
    verdict names no basis, so the reveal it is read under comes from here."""
    detail = parse_output.get("ranking_detail") if isinstance(parse_output, dict) else None
    group = detail.get("group_by") if isinstance(detail, dict) else None
    if group == MORE_PAGE:
        # A page of the held summary is read under the held frame's own kind.
        kind = _dict(parse_output.get("sales_ranking_frame")).get("basis")
        return kind if kind in OUTSTANDING_KINDS else None
    return next((kind for kind, pick in LIST_PICKS.items() if pick == group), None)


def outstanding_kinds(*, revealed: bool, decision: str) -> tuple[str, ...]:
    """The outstanding kinds a contact may see (owner 29 Oct, as before #1922): both with the Outstanding reveal or as a
    salesperson on its own book (Q6); pending delivery alone when `sales_figure_decision` opened it without the reveal
    (`pending_delivery_open`: office staff or a linked contact); none otherwise."""
    if revealed or decision == "salesperson_book":
        return ASKED_KINDS
    return ("pending_delivery",) if decision == "pending_delivery_open" else ()
SALES_REPORT_GRANT = "sales_orders.sales_report"


def grant_key(parse_output: dict[str, Any]) -> str:
    """The reveal a report ask is read under (owner Q6): the Outstanding reveal for an outstanding kind
    (or an outstanding ask whose kind is still to be asked), the Sales report reveal for every other basis."""
    if not isinstance(parse_output, dict):
        return SALES_REPORT_GRANT
    if parse_output.get("order_status") != ASK_NAME:
        return SALES_REPORT_GRANT
    if parse_output.get("basis") in OUTSTANDING_KINDS or list_pick_kind(parse_output) or (
        parse_output.get("capability_from") == "outstanding" and not parse_output.get("basis")
    ):
        return OUTSTANDING_GRANT
    return SALES_REPORT_GRANT


OUTSTANDING_NOT_ENABLED = "Outstanding is not enabled for your account."
SALES_REPORT_NOT_ENABLED = "Sales report is not enabled for your account."


def not_enabled_line(parse_output: dict[str, Any]) -> str:
    """The refusal for a contact without the reveal the ask is read under: the route's own words
    (`outstanding_not_enabled` / `sales_report_not_enabled`)."""
    return OUTSTANDING_NOT_ENABLED if grant_key(parse_output) == OUTSTANDING_GRANT else SALES_REPORT_NOT_ENABLED


def basis_from(parse_output: dict[str, Any]) -> str | None:
    basis = parse_output.get("basis")
    return basis if basis in BASES else None


def _resolve_metric(_db: Any, _word: str, extras: dict[str, Any]) -> rf.Resolved:
    """An answering turn's metric: the PARSER's own reading of the reply (`reply_metric`)."""
    metric = extras.get("reply_metric")
    return rf.Resolved("ok", value=metric, label=metric) if metric in METRICS else rf.Resolved("unknown")


def _resolve_basis(_db: Any, _word: str, extras: dict[str, Any]) -> rf.Resolved:
    """An answering turn's basis: the PARSER's own reading of the reply (`reply_basis`); the kind question
    (an outstanding ask) takes one of the three kinds only."""
    basis = extras.get("reply_basis")
    allowed = OUTSTANDING_KINDS if extras.get("kind_ask") else BASES
    return rf.Resolved("ok", value=basis, label=basis) if basis in allowed else rf.Resolved("unknown")


def _metric_question(_extras: dict[str, Any]) -> str:
    asked = ranking_ask.next_question(metric_settled=False, basis_settled=False, basis_line=ranking_ask.RANKING_BASIS_LINE)
    return asked[1] if asked else ranking_ask.METRIC_LINE


def _basis_question(extras: dict[str, Any]) -> str:
    """The basis line; an outstanding ask (`kind_ask`) asks which KIND instead (Q2)."""
    if extras.get("kind_ask"):
        return KIND_QUESTION
    asked = ranking_ask.next_question(metric_settled=True, basis_settled=False, basis_line=ranking_ask.RANKING_BASIS_LINE)
    return asked[1] if asked else ranking_ask.RANKING_BASIS_LINE


PERIOD = rf.FieldSpec(name="period", noun="period", question=PERIOD_QUESTION, resolve=_resolve_period, allow_all=False)
TOP_N = rf.FieldSpec(name="top_n", noun="number", question=TOP_N_QUESTION, resolve=_resolve_top_n, allow_all=False)

METRIC = rf.FieldSpec(name="metric", noun="measure", question=ranking_ask.METRIC_LINE, question_fn=_metric_question, resolve=_resolve_metric, allow_all=False)
#: The kind question's options (the outstanding kinds, in the question's order) and the basis question's, as the
#: pick the parser is shown (`FieldSpec.offered`).
KIND_OPTIONS = (("outstanding", "Sales order"), ("pending_delivery", "Delivery order"))
BASIS_OPTIONS = (("invoiced", "Invoiced"), ("delivered", "Delivered"), ("ordered", "Ordered"), ("outstanding", "Outstanding"))


def _basis_offered(extras: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return KIND_OPTIONS if extras.get("kind_ask") else BASIS_OPTIONS


# The answer is the parser's declared pick of an offered option, or its own `basis` reading when it is one of them,
# never the reply's text. The outstanding KIND question is parser-only (no shape fallback either, crew hand test).
BASIS = rf.FieldSpec(
    name="basis", noun="basis", question=ranking_ask.RANKING_BASIS_LINE, question_fn=_basis_question,
    resolve=_resolve_basis, allow_all=False, offered=_basis_offered, parser_only=lambda extras: bool(extras.get("kind_ask")),
)

#: The scope question's slot (`asking == "scope"`, the drill ask): its words ride on the slot's
#: extras; the spec only lets the parser be shown it as the Open question (REPORT-SMART-L S3-1).
SCOPE = rf.FieldSpec(name="scope", noun="scope", question="", resolve=lambda _db, _word, _extras: rf.Resolved("unknown"), allow_all=False)

#: REPORT-UNIFY slice 3 (H3): a sales agent word that several agent rows answer to is asked as a numbered pick of
#: agents only. Never required: it is a field only when `_word_filters` found the word ambiguous.
SALES_AGENT = rf.FieldSpec(
    name="sales_agent", noun="sales agent", question="Which sales agent?", resolve=lambda _db, _word, _extras: rf.Resolved("unknown"),
    allow_all=False, required=False, pick_head="Which sales agent? Reply with a number:", parser_only=True,
)

#: A company the message named that the contact does not hold: said plainly, nothing runs (never run without it). Owner
#: O-R2 (3 Nov): a company is never asked; an ask naming none runs over every company the contact holds.
COMPANY_FORBIDDEN_LINE = "You do not have access to that company."


def asks_the_retired_company(slot: Any) -> bool:
    """A live session's open question of this ask that is the company question (O-R2 removed it): read as none open."""
    return isinstance(slot, dict) and slot.get("ask") == ASK_NAME and slot.get("asking") == "company"


def _owed_held(extras: dict[str, Any], values: dict[str, Any], held: dict[str, Any]) -> dict[str, Any]:
    """`held` with the word question (last) and the agent pick brought back while still owed (their options ride the
    slot's extras) and no answer has settled them."""
    if extras.get("kind_words") and "kind" not in values and "kind" not in held:
        # The word question is the last field: it stays owed until answered, whatever the earlier answers settled.
        held = {**held, "kind": rf.Resolved("ambiguous", options=_kind_options(extras))}
    agents = extras.get("agent_options")
    if agents and "sales_agent" not in values and "sales_agent" not in held:
        # The agent pick stays owed behind any earlier question.
        held = {**held, "sales_agent": rf.Resolved("ambiguous", options=tuple((str(o[0]), str(o[1])) for o in agents))}
    return held


#: SALES-ACCOUNT-TYPE PR 2: a word that is both a brand and a stored account type is asked once, after every other owed
#: field (the last one). Its options are the pick the parser is shown; the reply to the user is the bare question (`_kind_question`).
WORD_KIND_OPTIONS = (("brand", "Brand"), ("account_type", "Account type"))
#: Crew C6-1 (round 6): a both-table word that is also one of the contact's companies (`kind_company`) is offered the
#: company as a third kind.
COMPANY_KIND_OPTION = ("company", "Company")
#: CHATBOT-TOTALS-FILTERS M2 (owner Q2 c): a bare name that is a brand and one of the contact's companies is asked once,
#: company, brand or both (`kind_both`).
BOTH_KIND_OPTION = ("both", "Both")


def _kind_options(extras: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    if extras.get("kind_both"):
        return (COMPANY_KIND_OPTION, WORD_KIND_OPTIONS[0], BOTH_KIND_OPTION)
    return (*WORD_KIND_OPTIONS, COMPANY_KIND_OPTION) if extras.get("kind_company") else WORD_KIND_OPTIONS


def _kind_question(extras: dict[str, Any]) -> str:
    """"Cabana, sorento: brand or account type?": the first word's first letter upper, the rest as typed. A word that is
    also one of the contact's companies (C6-1) is asked with the three kinds numbered; a name that is a brand and a
    company and no account type (M2) is asked company, brand or both."""
    words = [w for w in (extras.get("kind_words") or []) if isinstance(w, str) and w.strip()]  # printed forms (`_account_plan`)
    head = ", ".join(words)
    head = f"{head[:1].upper()}{head[1:]}: " if head else ""
    if extras.get("kind_both"):
        options = [f"{i}. {label}" for i, (_value, label) in enumerate(_kind_options(extras), start=1)]
        return "\n".join([f"{head}company or brand?" if head else "Company or brand?", *options])
    if extras.get("kind_company"):
        options = [f"{i}. {label}" for i, (_value, label) in enumerate(_kind_options(extras), start=1)]
        return "\n".join([f"{head}brand, account type or company?" if head else "Brand, account type or company?", *options])
    return f"{head}brand or account type?" if head else "Brand or account type?"


KIND = rf.FieldSpec(
    name="kind", noun="kind", question="Brand or account type?", question_fn=_kind_question,
    resolve=lambda _db, _word, _extras: rf.Resolved("unknown"), allow_all=False, required=False,
    pick_head_is_question=True, parser_only=True, offered=_kind_options,
)

SALES_RANKING_ASK = rf.register(rf.AskType(
    name=ASK_NAME,
    fields=(PERIOD, TOP_N, METRIC, BASIS, SALES_AGENT, KIND),  # the required fields first, the word question last
    slot_fields=(SCOPE,),
    # REPORT-SMART-L S3-1: the parser is shown the question (owed fields + held values) and
    # its declared answer (mode fill) runs the ask, as the low stock report's.
    answered_by_parser=True,
    shape_fallback=True,
    reroute={
        "message_type": "business_query",
        "domain_hint": "sales",
        "intent_hint": "check_order",
        "order_status": ASK_NAME,
    },
    cancelled=CANCELLED,
    give_up=GIVE_UP,
    # Chat fix PR-B S2: an answer holds the report type. A "delivered" / "ordered" answer the
    # parser also read as a document status fills the basis; its `status` / `document` never
    # re-route the turn to the order list (`turn_runtime._DOCUMENT_STATUS_TO_ORDER_STATUS`).
    answer_drops=("sales_channel", "report_ask_words", "status", "document"),
    # Chat fix PR-B S1 (owner, 16 Oct 2026): every missing detail in ONE numbered reply.
    ask_all=True,
))


# --------------------------------------------------------------------------- #
# Engine seam
# --------------------------------------------------------------------------- #


#: REPORT-UNIFY (owner ruling Q1): every sales total and breakdown the parser labels `sales_report` or
#: `sales_analysis` is the report ask's, by whatever axis (`GROUP_BY`) and with no axis at all. An axis outside
#: `GROUP_BY` (the Yearly comparison's `year`) stays on `crm_sales_analysis`, its Excel file. (`top_selling` is the
#: report ask's too: `from_top_selling`.)
SALES_STATUSES = frozenset({"sales_analysis", "sales_report"})
#: The entity kinds that are a filter of the report ask (an outstanding ask holding none of these, and no axis, is an
#: order list, not a report).
_FILTER_HINTS = frozenset(
    {"customer", "product", "brand", "category", "sales_agent", "warehouse", "specification", "account_type"}
)
#: A breakdown the parser did not read as a ranking (a sales analysis or report by an axis,
#: "sales for all agents") lists every row, never asked "how many": up to this many.
BREAKDOWN_TOP_N = 100
#: The keys `by_capability` writes; stripped from every verdict first, so no parse sets them.
CAPABILITY_KEYS = ("capability_from", "report_breakdown", "bare_top_selling")
#: The analysis's basis key (`sales_basis`) and the bases the report ask has of it.
_ANALYSIS_BASES = frozenset({"invoiced", "delivered", "ordered"})


def from_top_selling(verdict: dict[str, Any]) -> dict[str, Any]:
    """REPORT-SMART-L R1: the parser's `top_selling` label (an item or category ranking) is a sales
    ranking on the report engine, read whole by `settle`: `rank_group` category (or a `category`
    axis) ranks categories, else the axis the parser named, else products; the count, period,
    measure (`rank_by`), basis, direction and filters ride unchanged. Parser fields only."""
    # A `top_selling` label is the parser's own statement that items are ranked: `by_words` null does not null its axis.
    verdict = {k: v for k, v in verdict.items() if k not in (*CAPABILITY_KEYS, "by_words")}  # no stray parser key survives
    raw_group = jsc.js_string(verdict.get("group_by") or "").strip().lower()
    rank_group = jsc.js_string(verdict.get("rank_group") or "").strip().lower()
    if rank_group == "category" or raw_group == "category":
        group_by = "category"
    elif raw_group in GROUP_BY:
        group_by = raw_group
    else:
        group_by = "product"
    out = {
        **{k: v for k, v in verdict.items() if k not in ("status", "document")},
        **SALES_RANKING_ASK.reroute,
        "group_by": group_by,
        "capability_from": "top_selling",
    }
    if not raw_group and not rank_group:
        # The parser named neither an axis nor a grain ("by amount", "ordered", "top 20"): under a ranking on
        # screen this only changes values of it (`settle`), the axis above is just the default for a fresh ask.
        out["bare_top_selling"] = True
    if basis_from(out) is None and verdict.get("sales_basis") in _ANALYSIS_BASES:
        out["basis"] = verdict["sales_basis"]
    return out


def status_as_basis(verdict: dict[str, Any]) -> dict[str, Any]:
    """Engine seam, before the CHAT-STATE seam (EVAL-BENCH mini 7928e3b7): a sales ranking whose `status` is one of
    the report ask's bases ("by qty, outstanding") has that basis, not a document status to ask a document for.
    The status and document are dropped as `from_top_selling` and `by_capability` drop them. Parser fields only."""
    if jsc.js_string(verdict.get("order_status") or "").strip() not in (ASK_NAME, "top_selling"):
        return verdict
    status = jsc.js_string(verdict.get("status") or "").strip()
    if status not in BASES:
        return verdict
    out = {k: v for k, v in verdict.items() if k not in ("status", "document")}
    if basis_from(out) is None:
        out["basis"] = status
    return out


#: The roster picks whose rows are one kind of subject, and the `group_by` that names that kind.
_PICK_AXIS = {"customer_pick": "customer", "product_pick": "product"}


def without_pick_axis(verdict: dict[str, Any], pending: Any) -> dict[str, Any]:
    """Engine seam, before `by_capability` (CHAT-CUSTOMER-PICK-RESUME, prod v63 25 Oct): a pick of a
    position on an open customer / product roster whose `group_by` names the roster's own kind ("1" over
    "Which one do you mean?", parsed with `group_by` customer) is the pick, not a breakdown: the axis is
    dropped, so the held ask resumes with the picked row instead of becoming a ranking by that kind (and
    a sales total refused as "I can't break sales down by customer"). Any other axis, an "all" answer
    and every other open question are untouched. Parser fields only."""
    answer = verdict.get("open_question_answer") if isinstance(verdict.get("open_question_answer"), dict) else {}
    picked = answer.get("mode") == "pick" and bool(jsc.array(answer.get("picked")))
    ranking = _dict(_dict(getattr(pending, "payload", None)).get("filters")).get("ranking")
    if (
        getattr(pending, "kind", None) == "top_selling_pick"
        and _dict(ranking).get("group_by") in LIST_PICKS.values()
        and (picked or jsc.array(verdict.get("reference_positions")))
    ):
        # The open "Reply 1 for the sales order list" offer is answered before any axis or status check: a position
        # under it is the pick, whatever stale report status or guessed axis the parse also carried.
        # The offer's own status carries the held ranking frame (it rides only on `sales_ranking`).
        return {**verdict, "group_by": None, "order_status": _dict(getattr(pending, "payload", None)).get("status")}
    axis = _PICK_AXIS.get(getattr(pending, "kind", None) or "")
    if axis is None or jsc.js_string(verdict.get("group_by") or "").strip().lower() != axis:
        return verdict
    answer = verdict.get("open_question_answer") if isinstance(verdict.get("open_question_answer"), dict) else {}
    picked = answer.get("mode") == "pick" and bool(jsc.array(answer.get("picked")))
    if not (picked or jsc.array(verdict.get("reference_positions"))):
        return verdict
    return {**verdict, "group_by": None}


def offers_outstanding_basis(open_slot: Any) -> bool:
    """Is the open question one that offers Outstanding as a SALES basis (the sales basis ask, or this ask's basis
    question before its basis is settled, never the kind question)? There "outstanding" is the answer, not a new ask."""
    slot = _dict(open_slot)
    if slot.get("ask") == "sales_basis":
        return True
    return (
        slot.get("ask") == ASK_NAME and not _dict(slot.get("extras")).get("kind_ask")
        and not _dict(_dict(slot.get("values")).get("basis")).get("value")
    )


def outstanding_by_basis(verdict: dict[str, Any]) -> dict[str, Any]:
    """Eval send-back (#b6e9 on the prod prompt v70): a sales report or analysis whose basis word is "outstanding"
    (`sales_basis`) is an outstanding ask, as before #1922 (`sales_basis_ask.as_report_ask`); its kind is still the
    owner's rule (the kinds the contact may see; asked when two, never defaulted). Parser fields only."""
    for key in ("order_status", "status"):
        if jsc.js_string(verdict.get(key) or "").strip() in SALES_STATUSES:
            verdict = {**verdict, key: "outstanding"}
    return {k: v for k, v in verdict.items() if k != "sales_basis"}


def by_capability(
    verdict: dict[str, Any], *, subject: bool = False, seam: bool = True, answering: bool = False
) -> dict[str, Any]:
    """Engine seam, before grounding (REPORT-SMART-1021 step 2, REPORT-UNIFY Q1; `seam=False` is `run_fetch`'s own
    pass over what the seam left, which lets a pick or a document through): every sales figure ask
    (`SALES_STATUSES`, any axis the report ask has or none) and every outstanding ask that holds a filter or an
    axis (`as_outstanding`) is a sales ranking, read whole by `settle`: its filters, period, count, metric and
    basis, with every missing one asked in one numbered reply. A breakdown (no count, no direction, from a kind
    that is not a ranking) lists every row. Parser fields only; anything else is unchanged."""
    # Engine keys only this seam writes: never taken from the parser's own emission.
    verdict = {k: v for k, v in verdict.items() if k not in CAPABILITY_KEYS}
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    replying = answering or _dict(verdict.get("open_question_answer")).get("mode") is not None
    if status in SALES_STATUSES and verdict.get("sales_basis") == "outstanding" and not replying and not basis_from(verdict):
        # A FRESH ask naming no basis of its own. With a question open (`answering`: the engine's own open slot, never
        # the parser's mode alone) "outstanding" is that question's answer (BASIS_OPTIONS' Outstanding), and stays it.
        verdict, status = outstanding_by_basis(verdict), "outstanding"
    if verdict.get("intent_hint") == "low_stock_report" and verdict.get("domain_hint") == "inventory":
        return verdict  # the reorder report is its own ask (`low_stock_ask`), whatever order status the parser also read
    if status == "top_selling":
        return from_top_selling(verdict)
    answer = verdict.get("open_question_answer") if isinstance(verdict.get("open_question_answer"), dict) else {}
    if seam and (
        (answer.get("mode") == "pick" and jsc.array(answer.get("picked"))) or jsc.array(verdict.get("reference_positions"))
    ):
        return verdict  # a pick of a position on an open roster answers it, whatever report type the parser also read
    named_word = any(  # a sales report with its own axis naming an agent / brand / category word is the report ask's even beside a document
        isinstance(e, dict) and e.get("current_message") is not False
        and jsc.js_string(e.get("hint") or "").strip().lower() in WORD_HINTS
        for e in jsc.array(verdict.get("entities"))
    )
    if seam and jsc.array(verdict.get("document")) and not (status in SALES_STATUSES and named_word and jsc.js_string(verdict.get("group_by") or "").strip().lower() in GROUP_BY):
        # The parser read an order DOCUMENT (an SO / DO list ask): the so_status seams decide it from the words; an
        # outstanding or sales report status it carried with it is converted later, at `run_fetch` (`seam=False`),
        # if it stands.
        return verdict
    if status in OUTSTANDING_STATUSES:
        return as_outstanding(verdict, subject=subject)
    if status == ASK_NAME and verdict.get("ranking_refine") is not True:
        # A group_by with no count, no direction and no ranked measure from the parser is a breakdown, not a ranking:
        # every row, never "How many?" (crew hand test, 28 Oct). Parser fields only.
        group = jsc.js_string(typed_group_by(verdict).get("group_by") or "").strip().lower()
        if group in GROUP_BY and group not in TREND_AXES and not any(
            verdict.get(k) not in (None, "") for k in ("rank_direction", "top_n", "rank_by")
        ):
            return {**verdict, "report_breakdown": True}
    if status not in SALES_STATUSES:
        return verdict  # an order / PO list keeps its own grouping; only the report ask's statuses are typed
    verdict = typed_group_by(verdict)  # R6: a null `by_words` names no axis, so the guess routes nothing
    raw_group = jsc.js_string(verdict.get("group_by") or "").strip().lower()
    if raw_group and raw_group not in GROUP_BY:
        return verdict
    out = {
        **{k: v for k, v in verdict.items() if k not in ("status", "document")},
        **SALES_RANKING_ASK.reroute,
        # The kind the parser named: an open question reads it as that kind's new ask.
        "capability_from": status,
    }
    if basis_from(out) is None and verdict.get("sales_basis") in _ANALYSIS_BASES:
        out["basis"] = verdict["sales_basis"]
    if status != "top_selling" and verdict.get("rank_direction") not in ("top", "bottom"):
        # Review B2: a flag, never a count on the verdict. Only a FRESH ask with no count of its
        # own reads it (`settle`); an answer to an open question or a refine never does.
        out["report_breakdown"] = True
    return out


def as_outstanding(verdict: dict[str, Any], *, subject: bool = False) -> dict[str, Any]:
    """REPORT-UNIFY (Q1, Q2): an outstanding ask that holds a filter or an axis is the report ask's, its kind (the
    basis: undelivered orders, pending delivery or unpaid invoices) the parser's `basis` or the one a
    sales / delivery order document status names; none named is asked, never defaulted. A bare "outstanding"
    (no filter, no axis, no document word) is the whole company figure of the kind asked (R4); a kind-named
    document status that holds neither stays the order list. `subject`: the caller resolved a row (a named word, or a linked contact's own accounts).
    Parser fields only."""
    entities = [e for e in jsc.array(verdict.get("entities")) if isinstance(e, dict)]
    held = subject or any(jsc.js_string(e.get("hint") or "").strip().lower() in _FILTER_HINTS for e in entities)
    verdict = typed_group_by(verdict)
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    # R4: a BARE outstanding (no filter, no axis, no document word naming a list) is the whole company figure of a kind,
    # asked, never the order list. The kind-named document statuses (`so_outstanding`, `do_outstanding`) keep their
    # list when they hold nothing.
    bare = status in ("outstanding", "outstanding_both") and not jsc.array(verdict.get("document"))
    if not (held or bare or jsc.js_string(verdict.get("group_by") or "").strip().lower() in GROUP_BY):
        return verdict
    kind = verdict.get("basis") if verdict.get("basis") in OUTSTANDING_KINDS else STATUS_KIND.get(status)
    out = {
        **{k: v for k, v in verdict.items() if k not in ("status", "document", "basis")},
        **SALES_RANKING_ASK.reroute,
        "capability_from": "outstanding",
        "report_breakdown": verdict.get("rank_direction") not in ("top", "bottom"),
    }
    if kind:
        out["basis"] = kind
    return out


def drop_field_words(verdict: dict[str, Any]) -> dict[str, Any]:
    """Engine seam, before the report words, the resolver and any kind pick (REPORT-SMART-L S3-2,
    S3-3): an entity whose raw is a word the parser already put in a field of the SAME verdict is
    that field, never an entity. A word equal to the verdict's own `sales_channel` (whatever its
    hint) is the channel; a product whose raw is the year the parser set as the period (start and
    end both in that year) is the period. No channel, no period, or another year: untouched."""
    entities = verdict.get("entities")
    if not isinstance(entities, list) or not entities:
        return verdict
    channel = jsc.js_string(verdict.get("sales_channel") or "").strip().casefold()
    start, end = jsc.js_string(verdict.get("date_filter_start") or ""), jsc.js_string(verdict.get("date_filter_end") or "")
    year = start[:4] if len(start) >= 4 and start[:4] == end[:4] and start[:4].isdigit() else ""

    def is_field_word(e: Any) -> bool:
        if not isinstance(e, dict):
            return False
        raw = " ".join(jsc.js_string(e.get("raw") or "").split()).casefold()
        if not raw:
            return False
        return raw == channel or (raw == year and jsc.js_string(e.get("hint") or "").strip().lower() == "product")

    kept = [e for e in entities if not is_field_word(e)]
    return verdict if len(kept) == len(entities) else {**verdict, "entities": kept}


def _spec_term(entity: dict[str, Any]) -> str | None:
    """`key:value` of a specification entity the parser read whole (a key and a value), the route's `spec` param;
    None for any other entity. Grounding re-derives specs from the raw words and may drop it, so it is held out."""
    if jsc.js_string(entity.get("hint") or "").strip().lower() != "specification":
        return None
    key, value = jsc.js_string(entity.get("spec_key") or "").strip(), entity.get("spec_value")
    if not key or value in (None, ""):
        return None
    word = "yes" if value is True else "no" if value is False else jsc.js_string(value).strip()
    return f"{key}:{word}{jsc.js_string(entity.get('spec_unit') or '').strip()}" if word else None


def hold_words(verdict: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Engine seam before grounding, a `sales_ranking` verdict: its brand, sales agent and
    category entities, held out of the descriptor grounding and handed back after it."""
    if jsc.js_string(verdict.get("order_status") or "").strip() != ASK_NAME:
        return verdict, []
    entities = verdict.get("entities")
    if not isinstance(entities, list):
        return verdict, []
    held = [
        e for e in entities
        if isinstance(e, dict) and (jsc.js_string(e.get("hint") or "").strip().lower() in WORD_HINTS or _spec_term(e))
    ]
    if not held:
        return verdict, []
    return {**verdict, "entities": [e for e in entities if not any(e is h for h in held)]}, held


def _squash(value: Any) -> str:
    return " ".join(jsc.js_string(value).split()).casefold()


def _kind_word(e: dict[str, Any]) -> bool:
    """A brand or account type entity whose word IS its own `kind_said` ("account type", "brand"): it names the kind,
    not a value. An absent or null `kind_said` never matches."""
    said = e.get("kind_said")
    return (
        jsc.js_string(e.get("hint") or "").strip().lower() in ("brand", "account_type")
        and isinstance(said, str) and bool(_squash(said))
        and _squash(said) == _squash(e.get("raw"))
    )


def take_words(verdict: dict[str, Any], text: str) -> dict[str, Any]:
    """Engine seam, a FRESH `sales_ranking` ask: this message's brand, sales agent and
    category words move off the entity list onto `report_ask_words` (raw words per hint).
    A carried row of those hints is dropped too: it is not this ask's filter, and the
    generic resolver would read it as a customer. `text` is taken for the seam's shape: the
    parser, never the words, decides what the message meant."""
    _ = text
    if jsc.js_string(verdict.get("order_status") or "").strip() != ASK_NAME or verdict.get("required_ask"):
        return verdict
    kept: list[Any] = []
    words: dict[str, list[str]] = {hint: [] for hint in WORD_HINTS if hint != "account_type"}  # that key only when said
    #: SALES-ACCOUNT-TYPE PR 2: per brand / account word, what the message itself said (`kind_said`). An entity
    #: with no such key (a prompt text that does not define it) leaves no entry: no question for that word.
    kinds: list[dict[str, Any]] = []
    specs: list[str] = []
    for e in verdict.get("entities") or []:
        if not isinstance(e, dict):
            continue
        term = _spec_term(e)
        if term:
            if e.get("current_message") is not False and term not in specs:
                specs.append(term)
            continue
        hint = jsc.js_string(e.get("hint") or "").strip().lower()
        raw = " ".join(jsc.js_string(e.get("raw") or "").split())
        typed = raw
        if hint in WORD_HINTS and hint != "account_type":
            # AC-HT8-12, REPORT-UNIFY slice 3 (plan 3.2): the word the parser BOUND the mention to, a candidate's
            # label or its row id, before the verbatim raw; the raw is read only when it bound nothing.
            # (An account type word or number goes exactly as typed.)
            raw = " ".join(jsc.js_string(e.get("canonical_code") or "").split()) or raw
        if hint not in WORD_HINTS:
            kept.append(e)
            continue
        if _kind_word(e):
            continue  # the word is the kind word itself ("account type"): it names no value
        if raw and e.get("current_message") is not False and raw not in words.setdefault(hint, []):
            words[hint].append(raw)
            if hint in ("brand", "account_type") and "kind_said" in e:
                kind = {"hint": hint, "word": raw, "raw": typed, "said": kind_was_said(e.get("kind_said"))}
                if "said_as" in e:
                    # CHATBOT-TOTALS-FILTERS HT1: the parser's read of a name as a company, a brand or both (null: not
                    # said); `_company_or_brand` reads it. No key (a text that does not define it): no entry.
                    kind["as"] = e.get("said_as") if e.get("said_as") in SAID_AS else None
                kinds.append(kind)
    return {
        **verdict, "entities": kept, "report_ask_words": words, "report_ask_spec": specs, "report_ask_kind": kinds,
    }


def typed_group_by(verdict: dict[str, Any]) -> dict[str, Any]:
    """REPORT-SMART-L R6 (ruling A): the parser's `by_words` are the words of the current message that name the ranked
    or grouped axis. A verdict whose key is PRESENT and null names no axis, so the `group_by` it carries is a guess and
    is not taken (a fresh ask is a total, a refine changes no axis). A verdict WITHOUT the key (a prompt version that
    does not define it) is returned untouched. Parser fields only, no word list."""
    if "by_words" not in verdict or jsc.js_string(verdict.get("by_words") or "").strip() or not verdict.get("group_by"):
        return verdict
    return {**verdict, "group_by": None}


def names_its_own_ask(
    verdict: dict[str, Any], open_slot: dict[str, Any] | None = None, *, parser_ops: Any = ()
) -> bool:
    """Engine seam before `required_fields.reply_verdict`: a `sales_ranking` verdict that is not a
    refine is a NEW ask, so an open period / how many question is dropped, not answered by it, when
    it names a current-message filter entity or a `group_by` DIFFERENT from the one the open slot
    holds (the same axis echoed is an answer). Parser fields only.

    Chat fix PR-B S2c: a verdict of ANOTHER report type (`OTHER_REPORTS`) is a new ask too when it
    fills none of the slot's open fields and names something of its own (an axis, a current
    entity, or the ask itself): "i want to see the top customer" under the basis question is
    never read as a failed basis answer. And a parse that FILLS an open field is the answer: its
    `group_by` is not the slot's axis changing (the parser's axis on an answering turn was noise
    12 of 14 live turns, PR-B replay 16 Oct: "top 5" read as sales_agent under a customer ask).

    REPORT-SMART-L: a reply that fills an open field and carries the parser's `answer` op is the
    answer whatever entities it repeats (the held brand echoed under "By quantity or by amount?").
    The applier pops `state_changes` before the engine seam (and rejects an `answer` that has no
    open question), so the engine passes the ops it logged as `parser_ops`."""
    verdict = typed_group_by(verdict)
    status = jsc.js_string(verdict.get("capability_from") or verdict.get("order_status") or "").strip()
    named = any(
        isinstance(e, dict) and e.get("current_message") is not False and jsc.js_string(e.get("hint") or "").strip()
        for e in jsc.array(verdict.get("entities"))
    )
    slot = _dict(open_slot)
    extras = _dict(slot.get("extras"))
    held = {**_given_choices(_dict(extras.get("args"))), **_given_top_n(_dict(extras.get("args")), extras.get("top_n"))}
    filled = _reply_fills(verdict, _dict(slot.get("values")), held)
    fills = bool(filled)
    if status in OTHER_REPORTS:
        # Review M3: a named entity, or a period as all it fills, is a new ask; filling the
        # count, metric or basis is the answer; filling nothing, a new ask if it names its own.
        if named or set(filled) == {"period"}:
            return True
        own = bool(verdict.get("group_by")) or verdict.get("domain_in_message") is True
        return own and not filled
    if status != ASK_NAME:
        return False
    if verdict.get("ranking_refine") is True:
        # REPORT-SMART-1021 (EVAL-BENCH 21 Oct, turn dded3dc7): a refine naming its own entity,
        # or the whole ask typed again (`new_subject`), is never the open question's answer; a
        # bare refine ("ordered") still is.
        # A bare refine naming another axis is not a new ask: `settle` swaps it into the open ask.
        return named or restates_the_ask(verdict)
    if named:
        # The parser's `answer` op on a reply that fills an open field is the answer even when it
        # repeats the held brand or category as current-message entities (live turn, parser v92).
        return not (fills and _carries_answer_op(verdict, parser_ops))
    raw_group =jsc.js_string(verdict.get("group_by") or "").strip().lower()
    # A reply filling only the period and naming another axis is a new ask (review round 8);
    # one filling the count, metric or basis is the answer (16 Oct: its axis is parser noise).
    if not raw_group or set(filled) - {"period"}:
        return False
    if not filled and _swappable(verdict, parser_ops):
        return False  # R5: the axis changing on the open ask (`settle` swaps it in), not a new ask
    return _other_axis(verdict, extras)


def _new_subject(verdict: dict[str, Any], parser_ops: Any = ()) -> bool:
    """The parser's `new_subject` op, read from `state_changes` or from the ops the engine logged."""
    changes = [*jsc.array(verdict.get("state_changes")), *jsc.array(parser_ops)]
    return "new_subject" in {jsc.js_string(c.get("op") or "") for c in changes if isinstance(c, dict)}


def _swappable(verdict: dict[str, Any], parser_ops: Any = ()) -> bool:
    """A reply that may change the open ask's axis: the parser did not say it is a fresh ask
    (`ranking_refine` explicitly false, or a `new_subject` op). Callers check it fills nothing and names no entity."""
    if verdict.get("ranking_refine") is False:
        return False
    return not _new_subject(verdict, parser_ops)


def _other_axis(verdict: dict[str, Any], extras: dict[str, Any]) -> bool:
    """Whether the verdict names an axis other than the open slot's (its scope question names two)."""
    raw_group = jsc.js_string(verdict.get("group_by") or "").strip().lower()
    if not raw_group:
        return False
    axis = GROUP_BY.get(raw_group, raw_group)
    scope = _dict(extras.get("scope"))
    if scope:
        # The scope question names two axes ("customers of the sales agents above"): a reply
        # echoing either is its answer, not a new ask.
        return axis not in (scope.get("source"), _dict(scope.get("scoped")).get("args", {}).get("group_by"))
    return axis != _dict(extras.get("args")).get("group_by")


def _reply_wins(parse_output: dict[str, Any], slot: dict[str, Any], args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """A reply that changes the axis (or says it again) may also type a period, measure, basis or channel: those win
    over the held ones (as a hold does, S6c); whatever the reply does not name stays held. Parser fields only."""
    values = dict(_dict(slot.get("values")))
    args = dict(args)
    period = period_from(parse_output.get("date_filter_start"), parse_output.get("date_filter_end"))
    if period is not None:
        values["period"] = {"value": period.value, "label": period.label}
    if metric_from(parse_output):
        args["measure"] = metric_from(parse_output)
        values.pop("metric", None)
    if basis_from(parse_output):
        args["basis"] = basis_from(parse_output)
        values.pop("basis", None)
    channel = parse_output.get("sales_channel") or parse_output.get("required_ask_channel")  # an answer drops the first
    if channel in ("dealer", "project"):
        args["channel"] = channel
    return {**slot, "values": values}, args


def _echoes_axis(parse_output: dict[str, Any], extras: dict[str, Any]) -> bool:
    """Whether the verdict names exactly the axis the open ask already holds."""
    raw_group = jsc.js_string(parse_output.get("group_by") or "").strip().lower()
    held = _dict(extras.get("args")).get("group_by")
    return bool(raw_group) and bool(held) and GROUP_BY.get(raw_group, raw_group) == held


def _swap_axis(parse_output: dict[str, Any], extras: dict[str, Any]) -> dict[str, Any] | None:
    """The slot's extras with a refine's other axis swapped in (its own filter dropped), or None."""
    if parse_output.get("ranking_refine") is False or not _other_axis(parse_output, extras):
        return None
    axis = GROUP_BY.get(jsc.js_string(parse_output.get("group_by")).strip().lower())
    if axis is None:
        return None
    args = {k: v for k, v in _dict(extras.get("args")).items() if k not in _AXIS_FILTERS.get(axis, ())}
    return {**extras, "args": {**args, "group_by": axis}}


def _carries_answer_op(verdict: dict[str, Any], parser_ops: Any = ()) -> bool:
    """The parser's `answer` state change, read from `state_changes` like `restates_the_ask`, or
    from the ops the engine logged; a `new_subject` or `set` alongside it keeps the reply a new ask."""
    changes = [*jsc.array(verdict.get("state_changes")), *jsc.array(parser_ops)]
    ops = {jsc.js_string(c.get("op") or "") for c in changes if isinstance(c, dict)}
    return "answer" in ops and not ops & {"new_subject", "set"}


def _binds_subject(verdict: dict[str, Any]) -> bool:
    """A filter entity (customer, product, brand ...) the parser bound this turn, not a carried one."""
    return any(
        isinstance(e, dict) and e.get("current_message") is not False
        and jsc.js_string(e.get("hint") or "").strip().lower() in _FILTER_HINTS
        for e in jsc.array(verdict.get("entities"))
    )


def as_basis_answer(verdict: dict[str, Any], slot: Any) -> dict[str, Any]:
    """Engine seam, the basis (or outstanding kind) question open: the parser's own position reading of the reply
    (`reference_positions`, exactly one in range of the offered options) is the pick. Without it the position is read
    against whatever list stands underneath (a customer roster the kind question replaced) and picks the wrong row.
    Parser fields only."""
    if not isinstance(slot, dict) or slot.get("ask") != ASK_NAME or slot.get("asking") != "basis":
        return verdict
    options = slot.get("options") or []
    answer = verdict.get("open_question_answer")
    declared = isinstance(answer, dict) and answer.get("mode") in rf.ANSWER_MODES
    positions = {
        p for p in jsc.array(verdict.get("reference_positions"))
        if isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= len(options)
    }
    if not _dict(slot.get("extras")).get("kind_ask"):
        if declared:
            return verdict
        if len(positions) != 1:
            return verdict
        return {**verdict, "open_question_answer": {"mode": "pick", "picked": sorted(positions), "items": [], "qty_for_all": None}}
    # The kind question: the kind is the parser's declared pick, else its own `basis` naming an offered kind (AC-RU-17c),
    # else exactly one position it read. Any other declared answer (cancel, fill, no or several picks) stands untouched.
    offered = [o[0] for o in options if isinstance(o, (list, tuple)) and o]
    kind = position = None
    if declared:
        picked = {p for p in jsc.array(answer.get("picked")) if isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= len(options)}
        if answer.get("mode") == "fill" and verdict.get("basis") in OUTSTANDING_KINDS and verdict.get("basis") in (*offered, *NAMED_KINDS):
            kind = verdict.get("basis")  # a fill naming an offered kind: the kind, so a subject bound beside it is kept
        elif answer.get("mode") not in ("pick", "cancel") and (
            verdict.get("capability_from") or verdict.get("order_status") or _binds_subject(verdict)
        ):
            # A declared fill that names no offered kind but an ask of its own is that new ask, not the answer.
            return {k: v for k, v in verdict.items() if k != "open_question_answer"}
        elif answer.get("mode") != "pick" or len(picked) != 1:
            return verdict
        else:
            kind = options[next(iter(picked)) - 1][0]
    elif verdict.get("basis") in OUTSTANDING_KINDS and verdict.get("basis") in (*offered, *NAMED_KINDS):
        kind = verdict.get("basis")
    elif len(positions) == 1:
        position = next(iter(positions))
        kind = options[position - 1][0]
    if kind is None:
        own_ask = bool(verdict.get("capability_from") or verdict.get("order_status")) or _binds_subject(verdict)
        if verdict.get("basis") in BASES and not own_ask:  # a bare sales basis is no kind: the kind is asked again
            return {**verdict, "open_question_answer": {"mode": "pick", "picked": [], "items": [], "qty_for_all": None}}
        return verdict
    if _binds_subject(verdict):
        # A subject bound this turn makes it a fresh outstanding ask that names its kind and applies the subject,
        # never a bare pick that drops it.
        return {**{k: v for k, v in verdict.items() if k != "open_question_answer"}, "order_status": "outstanding", "basis": kind}
    if declared:
        return verdict
    if kind not in offered:
        # A named kind that is never offered (unpaid, owner 29 Oct) has no position: it answers as the parser's fill.
        return {**verdict, "open_question_answer": {"mode": "fill", "picked": [], "items": [], "qty_for_all": None}}
    return {**verdict, "open_question_answer": {"mode": "pick", "picked": [position or offered.index(kind) + 1], "items": [], "qty_for_all": None}}


def as_kind_answer(verdict: dict[str, Any], slot: Any) -> tuple[dict[str, Any], bool]:
    """Engine seam beside the basis pick, the word question open. `(verdict, True)` when the reply settles the kind:
    the parser's declared pick of an offered option, a repeat of one of the held words with the parser's `kind_said`
    ("cabana account"), or an account type number or tag (alone or beside the held word), which answers as the account
    type and is carried in `report_ask_kind_reply`. Whatever else such a reply says edits the held ask (`kind_edits`).
    The only exits to a new ask, for the pick and the repeat alike: `domain_in_message` true with a non-sales read, or
    an entity beyond the held words (an `account_type` entity is the held dimension). A reply that exits has any declared
    answer stripped (as `as_basis_answer`), since `reply_verdict` would still honour the pick. An untyped `group_by` is
    a guess and is dropped (the `_typed` rule: `by_words`, a count, a direction or a ranked measure). Parser fields only."""
    from app.services.chatbot import contracts

    if not isinstance(slot, dict) or slot.get("ask") != ASK_NAME or slot.get("asking") != "kind":
        return verdict, False
    options = [o[0] for o in slot.get("options") or [] if isinstance(o, (list, tuple)) and o]
    answer = verdict.get("open_question_answer")
    declared = isinstance(answer, dict) and answer.get("mode") in rf.ANSWER_MODES
    stripped = {k: v for k, v in verdict.items() if k != "open_question_answer"}
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    domain = verdict.get("domain_hint")
    asked = {
        " ".join(jsc.js_string(w).split()).casefold()
        for w in (*_dict(slot.get("extras")).get("kind_words", ()), *_dict(slot.get("extras")).get("kind_match", ()))
    }
    current = [e for e in jsc.array(verdict.get("entities")) if isinstance(e, dict) and e.get("current_message") is not False]

    def hint_of(e: dict[str, Any]) -> str:
        return jsc.js_string(e.get("hint") or "").strip().lower()

    def held_word(e: dict[str, Any]) -> bool:
        return bool({" ".join(jsc.js_string(e.get(k) or "").split()).casefold() for k in ("raw", "canonical_code")} & asked)

    words = [e for e in current if (held_word(e) or _kind_word(e)) and hint_of(e) in options]
    # A question with no account type option (M2's company or brand) takes no number as its answer.
    numbers = [
        e for e in current
        if "account_type" in options and hint_of(e) == "account_type" and not held_word(e) and not _kind_word(e)
    ]
    other_subject = verdict.get("domain_in_message") is True and (
        (status and status not in (*SALES_STATUSES, ASK_NAME)) or (domain and domain not in contracts.ORDER_OR_SALES_DOMAINS)
    )
    if other_subject:
        return (stripped if declared else verdict), False
    if len(words) + len(numbers) != len(current):
        # Another filter word: a new ask. A reply naming no report type of its own, and no other domain, is read as
        # the sales report it continues (`by_capability` types it, as it types every sales ask); a product lookup
        # under the question stays a lookup.
        new_ask = stripped if declared else verdict
        sales_read = domain in (None, "") or domain in contracts.ORDER_OR_SALES_DOMAINS
        return (new_ask if status or not sales_read else by_capability({**new_ask, "order_status": "sales_report"}, seam=False)), False
    typed = bool(jsc.js_string(verdict.get("by_words") or "").strip()) or any(
        verdict.get(k) not in (None, "") for k in ("top_n", "rank_direction", "rank_by")
    )
    base = {**verdict, **({} if typed else {"group_by": None})}
    # The reply's own words and numbers, read exactly as a fresh message's (`take_words`), ride to `kind_edits`.
    taken = take_words({**base, "order_status": ASK_NAME, "required_ask": None}, "")

    def stash(synth: bool) -> dict[str, Any]:
        return {"words": taken["report_ask_words"], "kinds": taken["report_ask_kind"], "synth": synth}

    if declared:
        picked = [p for p in jsc.array(answer.get("picked")) if isinstance(p, int) and not isinstance(p, bool)]
        if answer.get("mode") != "pick" or not picked or not 1 <= picked[0] <= len(options):
            return verdict, False
        return {**base, "report_ask_kind_reply": stash(False)}, True
    said = [e for e in words if kind_was_said(e.get("kind_said"))]
    hints = {hint_of(e) for e in said}
    if numbers:
        position = options.index("account_type") + 1  # the plan decides what the words and numbers mean
    elif len(hints) == 1 and len(said) == len(current):
        position = options.index(next(iter(hints))) + 1
    else:
        return verdict, False  # no word of the question said as a kind
    pick = {"mode": "pick", "picked": [position], "items": [], "qty_for_all": None}
    return {**base, "entities": [], "open_question_answer": pick, "report_ask_kind_reply": stash(True)}, True


def kind_edits(
    db: Any, parse_output: dict[str, Any], slot: dict[str, Any], *, dealer: bool, companies: Any
) -> tuple[dict[str, Any] | None, str | None]:
    """A reply that settled the word question edits the held ask with what else it says: the period, measure, basis and
    channel (`_reply_wins`), a count and direction, a typed axis (`_swap_axis`), a named company among the contact's own.
    Returns `(slot with the edits, None)` or `(None, the line to say)`."""
    extras = _dict(slot.get("extras"))
    slot, args = _reply_wins(parse_output, slot, _dict(extras.get("args")))
    values = dict(_dict(slot.get("values")))
    top_n = extras.get("top_n")
    got = top_n_from(parse_output.get("top_n"))
    if got.status == "ok":
        top_n = got.value
        values["top_n"] = {"value": got.value, "label": got.label}
    if parse_output.get("rank_direction") in ("top", "bottom"):
        args["sort"] = "asc" if parse_output["rank_direction"] == "bottom" else "desc"
    typed = bool(jsc.js_string(parse_output.get("by_words") or "").strip()) or any(
        parse_output.get(k) not in (None, "") for k in ("top_n", "rank_direction", "rank_by")
    )
    swapped = _swap_axis({**parse_output, "ranking_refine": None}, {**extras, "args": args}) if typed else None
    if swapped is not None:
        if dealer and _dealer_outside(parse_output, swapped["args"].get("group_by")):
            return None, DEALER_REFUSAL
        old_axis = args.get("group_by")
        args = swapped["args"]
        if args.get("group_by") != old_axis and old_axis in (None, *TREND_AXES):
            values = _settled_by_its_axis(values, old_axis)  # the new axis owes its own count and metric
    said = " ".join(jsc.js_string(parse_output.get("sales_company") or "").split()).casefold()
    own = [c for c in jsc.array(companies) if isinstance(c, (list, tuple)) and len(c) == 3]
    if said and not dealer:
        named = next((c for c in own if said in (str(c[1]).casefold(), str(c[2]).casefold())), None)
        if named is None:
            return None, COMPANY_FORBIDDEN_LINE
        args["company"] = str(named[0])
    new_extras = {**extras, "args": args, "top_n": top_n}
    reply = _dict(parse_output.get("report_ask_kind_reply"))
    if reply and not dealer:
        # ONE path: the reply's words and numbers, with what the pick says about the held word, go through the plan a
        # fresh message uses. A reply that only says the held word (a plain pick or repeat) keeps the question's own
        # choices; a reply's own new value replaces its own dimension (`route_args` assigns the keys of `final`).
        words = {k: [w for w in jsc.array(v)] for k, v in _dict(reply.get("words")).items()}
        kinds = [k for k in jsc.array(reply.get("kinds")) if isinstance(k, dict)]
        held_forms = {
            " ".join(jsc.js_string(h.get(k)).split()).casefold()
            for h in jsc.array(extras.get("kind_held")) for k in ("word", "raw", "type")
        }

        def own_words(hint: str) -> list[Any]:
            return [w for w in words.get(hint, []) if " ".join(jsc.js_string(w).split()).casefold() not in held_forms]

        plain = not own_words("brand") and not own_words("account_type")
        if not plain and not reply.get("synth"):
            value = rf.picked_option(slot, _dict(parse_output.get("required_ask_answer"))).value
            own = own_words("account_type")
            if value == "brand" or not own:
                hint = "brand" if value == "brand" else "account_type"
                for h in jsc.array(extras.get("kind_held")):
                    word = h["word"] if hint == "brand" else h["type"]
                    if word not in words.setdefault(hint, []):
                        words[hint].append(word)
                        kinds.append({"hint": hint, "word": word, "raw": h["raw"], "said": True})
        read = {**parse_output, "report_ask_words": words, "report_ask_kind": kinds}
        held_company = args.get("company")  # the company the held ask or this reply names
        plan = _account_plan(db, read, companies, ask=True, held_company=held_company) if not plain else None
        found, line = (
            _word_filters(db, {**read, "report_ask_words": {"brand": _brand_words(words, plan)}}, (("brand", "brand_ids"),))
            if plan is not None else ({}, None)
        )
        if found is None:
            # Never the resolver's line: it echoes the parser's word ("I don't know '...'", "matches several ...").
            return None, "I don't know that brand."
        final = (
            {k: v for k, v in (("brand_ids", found.get("brand_ids")), ("account_types", plan["account_types"])) if v}
            if plan is not None else {}
        )
        if final:  # nothing read: the question's own choices stand, never a silent run without the word
            new_extras["kind_choices"] = {"brand": final, "account_type": final}
    return {**slot, "values": values, "extras": new_extras}, None


def restates_the_ask(verdict: dict[str, Any]) -> bool:
    """REPORT-SMART-1021 (#1721 hand test step 7): a verdict flagged `ranking_refine` that the
    parser marked `new_subject` is the whole ask typed again, not a refine: it starts a new
    report frame, so the held basis and measure are not carried. Only the parser's op says so:
    the live parser repeats the held axis, count and measure on most refines (98 of 130 live
    refines carry a `group_by`, EVAL-BENCH 21 Oct), so those fields never mean a restart."""
    if verdict.get("ranking_refine") is not True:
        return False
    ops = {jsc.js_string(c.get("op") or "") for c in jsc.array(verdict.get("state_changes")) if isinstance(c, dict)}
    return "new_subject" in ops


#: The report kinds with no count of their own (a total, or by month). A sales analysis naming a
#: product or customer reads as a sales report before this seam (`turn_runtime`, SALES-COMPANY-PICK round 2).
_COUNTLESS_REPORTS = frozenset({"sales_analysis", "sales_report"})


def as_held_refine(verdict: dict[str, Any], frame: Any) -> dict[str, Any]:
    """Engine seam, chat fix PR-B S3: with a report held (`Focus.sales_ranking_frame`: a ranking or
    a total that ran, from a single ask or a multi-ask), the parser's refine (`ranking_refine`)
    re-runs THAT report whatever report type it named: the verdict goes to this ask, and its
    document status is dropped (it never turns the refine into an order list). The lane applies
    only the keys the parser changed (`_refine`)."""
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    # `by_capability` (before grounding) has already typed these reports as the ask; `capability_from` is the kind.
    kind = jsc.js_string(verdict.get("capability_from") or "").strip() if status == ASK_NAME else status
    if (
        kind in _COUNTLESS_REPORTS
        and verdict.get("top_n") is not None
        and verdict.get("sales_channel") in ("dealer", "project")
        and not jsc.js_string(verdict.get("group_by") or "").strip()
        and isinstance(frame, dict) and _drill_source(frame) and not frame.get("stale")
    ):
        # CHAT-CHANNEL-RANK-ROUTE (PLAN-chat-channel-rank-route-1025.md, ruling AC-CF2): neither report has a count of
        # its own, so a count and one channel with no axis, over a held ranking, is that ranking filtered to the channel
        # ("Project sales top 10 <code>"): a refine, which applies the channel, product and count (`_refine`). Only a
        # population on screen (agents, customers, ...): a month list or a channel ranking keeps today's report.
        verdict = {**verdict, "ranking_refine": True}
    if (
        status == ASK_NAME
        and verdict.get("bare_top_selling") is True
        and verdict.get("top_n") is None
        and isinstance(frame, dict) and frame and not frame.get("group_by") and not frame.get("stale")
    ):
        # R9 (ruling A on v63), REPORT-UNIFY: the top selling label with no grain and no count, over a held TOTAL,
        # answers that total with what it changed (the basis, the measure): a refine, never a fresh product ranking.
        return {**{k: v for k, v in verdict.items() if k not in CAPABILITY_KEYS}, "group_by": None, "ranking_refine": True}
    if verdict.get("ranking_refine") is not True or not isinstance(frame, dict) or not frame or status == ASK_NAME:
        return verdict
    if restates_the_ask(verdict):
        return verdict  # a re-typed ask is its own report type's new ask, never the held one re-run
    return {
        **{k: v for k, v in verdict.items() if k not in ("status", "document")},
        **SALES_RANKING_ASK.reroute,
    }


def _settled_by_its_axis(values: dict[str, Any], group_by: Any) -> dict[str, Any]:
    """A slot's values less what a total or a month trend settled on its own: its count (none, or the month
    default) and a metric settled EMPTY (both measures shown). A new axis owes those afresh, under its own rules;
    a measure the customer typed (R7) is a value, and stays."""
    if group_by not in (None, *TREND_AXES):
        return dict(values)
    return {k: v for k, v in values.items() if k != "top_n" and not (k == "metric" and not _dict(v).get("value"))}


#: REPORT-SMART-L R8: the engine's stamp (`with_held`), frame-shaped (`date_from`, `date_to`, the route params), plus
#: `product` when the held products are the gate's carried rows. Listed in `required_fields.ENGINE_KEYS`.
HELD_KEY = "report_held"
#: The route params of a held total that stay on the ranking its reply becomes: the period and the filters.
_HELD_TOTAL_KEYS = (
    "date_from", "date_to", "product_code", "product_ids", "brand_ids", "category_ids",
    "sales_agent_ids", "customer_agent_ids", "channel", "spec", "warehouse_codes", "company", "account_types",
)
#: A follow-up over a customer that stays (`_customer_stays`) keeps that customer, and the basis and any measure on screen
#: (S6c; the message's own win, and the reply's header names them). A company total is still asked (SALES-TOTAL-ASK).
_HELD_CUSTOMER_KEYS = (*_HELD_TOTAL_KEYS, "customer_ids", "basis", "measure")
#: REPORT-SMART-L R9: the open question a sales report reply arms with its drill offer (`fetch._sales_report_output`),
#: so the engine-held sign that the last answer was a sales report (`contracts.DETAIL_OFFER_KINDS`).
SALES_REPORT_OFFER = "sales_report_detail"
#: The bases `crm_sales_report` answers: delivered only (none named is that report's own figure).
_SALES_REPORT_BASES = (None, "delivered")


def _follows_up(verdict: dict[str, Any], frame: dict[str, Any], replaced: dict[str, Any] | None) -> bool:
    """Is this message a follow-up on the report held, by the parser's own `entity_op`? `reuse` always. Owner ruling, 1 Nov
    2026 (CHATBOT-FOLLOWUP-CARRY): a follow-up over a held customer keeps it unless a new customer is named, and the parser
    reads the same words as `modify` on some runs and `replace_combine` on others (its own table: "a new product keeps the
    held customer"), so those count too when they name no customer. `replace_combine` needs a customer held: over anything
    else it stays what R8 ruled, a message naming its own value. Owner O-R3 (3 Nov): a `replace` that names no subject of
    its own (`_binds_subject`) replaces nothing, so it is a follow-up as `reuse` is; one naming a subject is a restated
    ask and drops what it does not name (17 Sep)."""
    entity_op = verdict.get("entity_op")
    if entity_op == "reuse" or (entity_op == "replace" and not _binds_subject(verdict)):
        return True
    if entity_op not in ("modify", "replace_combine") or "customer" in _current_kinds(verdict):
        return False
    if entity_op == "modify":
        return True
    if replaced is not None:
        return bool(_dict(_dict(_dict(replaced).get("extras")).get("args")).get("customer_ids"))
    return _holds_a_customer(frame)


def _holds_a_customer(frame: dict[str, Any]) -> bool:
    """A report filtered to a customer. On a customer ranking they are its ranked side, not its filter. A `stale` frame counts:
    a turn that said a line and ran nothing is not on the owner's list of what replaces a customer."""
    return bool(frame.get("customer_ids")) and frame.get("group_by") != "customer"


def with_held(
    verdict: dict[str, Any],
    focus: Any,
    *,
    open_ask: dict[str, Any] | None,
    replaced: dict[str, Any] | None,
    parser_ops: Any = (),
    held_domains: Any = None,
    held_offer: str | None = None,
) -> dict[str, Any]:
    """Engine seam, REPORT-SMART-L R8 (crew ruling, EVAL-BENCH v63 gate): when the reply to a held sales report
    total becomes a ranking, what that total showed stays, and only what is still missing is asked.

    On only when the parser keeps the held subject (`_follows_up`, no topic reset, no `new_subject` op), the
    verdict is a ranking (R9: an axis-less one too, which runs the total), no ranking frame is held (a held one
    keeps its own rules: refine, S6b, ruling B, stale; one filtered to a customer is stamped too, and the stamp is the
    only source of a held customer), the last ask was a sales figure, and no open ask is being
    answered. `held_domains`: the domains the focus held before this turn's State applier wrote its own (the engine
    reads them; `Focus.domains` when not given). The source is the open report ask this verdict replaced
    (`names_its_own_ask`), alone, less what a total or month trend settled on its own (`_settled_by_its_axis`: no
    carried count); with none open, the held sales report total: `Focus.date_window` and the products it ran on.
    Engine-held state only, never words.

    R9 (ruling A on v63): right after a sales report (`held_offer`, the pending kind its drill offer armed), a
    ranking parse with no typed axis and no count (an axis-less sales ranking, or the top selling label with no
    grain: `bare_top_selling`) answers THAT total: delivered or no basis re-runs the sales report (the verdict goes
    back to `sales_report`, whose lane reuses the held window and products as it always has); ordered or
    outstanding, which that report has not, runs the report-ask total on the held product and period below."""
    domains = held_domains if held_domains is not None else getattr(focus, "domains", None)
    frame = _dict(getattr(focus, "sales_ranking_frame", None))
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    if (
        # SUPPLIER-ASK fix round 8 (crew turns fe876b64 / 5f7b1567): an outstanding ask IS this report ask under its
        # outstanding kind (`as_outstanding` reroutes it after this seam), so the answer to the open kind question
        # (the delivery order option, parsed as a fresh outstanding ask naming nothing) keeps the held customer as well.
        not (status == ASK_NAME or (status in OUTSTANDING_STATUSES and replaced is not None))
        or not _follows_up(verdict, frame, replaced)
        or verdict.get("topic_reset") is True
        or _new_subject(verdict, parser_ops)
        or (frame.get("group_by") and not _holds_a_customer(frame))
        or not (
            contracts.SALES_DOMAIN in (domains or [])
            # Fix round 8: an outstanding ask's open kind question can sit under `order` (a customer picked over a
            # purchase-side ask moves it there, `turn/apply._side_of_the_parties`); it is the same report ask.
            or (status in OUTSTANDING_STATUSES and "order" in (domains or []))
        )
        or (open_ask is not None and replaced is None)
    ):
        return verdict
    typed_axis = jsc.js_string(typed_group_by(verdict).get("group_by") or "").strip().lower()
    axisless = not typed_axis
    customer_stays = _customer_stays(verdict, GROUP_BY.get(typed_axis, typed_axis))
    if axisless and verdict.get("top_n") is not None:
        # AC-OR9: a typed count keeps the ranking. With no axis there is no total to hold it (a total settles no
        # count), so neither the carry nor the reroute applies: the reply is today's.
        return verdict
    if replaced is None and verdict.get("top_n") is None and verdict.get("bare_top_selling") is True and not frame.get("group_by"):
        # R9 (ruling A on v63), REPORT-UNIFY: the top selling label with no grain and no count, under a held total,
        # answers THAT total (the held window and product, below), like the axis-less ranking it is.
        verdict = {**{k: v for k, v in verdict.items() if k not in CAPABILITY_KEYS}, "group_by": None}
    if replaced is not None:
        if replaced.get("asking") == "scope":
            return verdict  # the drill's scope question holds no ask of its own to carry
        extras = _dict(replaced.get("extras"))
        values = _settled_by_its_axis(_dict(replaced.get("values")), _dict(extras.get("args")).get("group_by"))
        args = route_args(rf.Outcome(values=values, extras=extras))
        held = {k: v for k, v in args.items() if k not in ("group_by", "sort") and v not in (None, "", [])}
        if not customer_stays:
            held.pop("customer_ids", None)
    elif frame:
        # A held report (a total, or a ranking filtered to a customer): its period and filters stay.
        keys = _HELD_CUSTOMER_KEYS if customer_stays and _holds_a_customer(frame) else _HELD_TOTAL_KEYS
        held = {k: v for k, v in frame.items() if k in keys and v not in (None, "", [])}
    else:
        window = _dict(getattr(focus, "date_window", None))
        held = {"date_from": window.get("start"), "date_to": window.get("end"), "product": bool(getattr(focus, "products", None))}
        held = {k: v for k, v in held.items() if v}
    verdict = _kind_answered_by_position(verdict, replaced)
    return {**verdict, HELD_KEY: held} if held else verdict


def _kind_answered_by_position(verdict: dict[str, Any], replaced: dict[str, Any] | None) -> dict[str, Any]:
    """SUPPLIER-ASK fix round 8 (crew turns fe876b64 / 5f7b1567, asked then as "Undelivered orders or pending
    delivery?", now `KIND_QUESTION`): the delivery order option under the open kind question parses as a fresh
    outstanding ask with no `basis` but the position it picked (`reference_positions` [2]). That fresh ask replaces the
    question, so the position is read against the question it answered: its option there is the basis. Parser fields
    and the replaced question only."""
    if verdict.get("basis") or not isinstance(replaced, dict) or replaced.get("asking") != "basis":
        return verdict
    positions = [p for p in jsc.array(verdict.get("reference_positions")) if isinstance(p, int) and not isinstance(p, bool)]
    options = [o for o in jsc.array(replaced.get("options")) if isinstance(o, (list, tuple)) and o]
    if len(positions) != 1 or not 1 <= positions[0] <= len(options):
        return verdict
    basis = options[positions[0] - 1][0]
    return {**verdict, "basis": basis} if basis in OUTSTANDING_KINDS else verdict


def dealer_location_words(parse_output: dict[str, Any]) -> dict[str, Any]:
    """Engine seam, a DEALER's (customer-scoped) fresh `sales_ranking` ask, 1b fix round F1:
    this message's location words come off the resolver's entity list onto
    `report_ask_words["warehouse"]`, so no warehouse code is ever looked up for a dealer;
    the lane refuses the ask off the word alone."""
    if jsc.js_string(parse_output.get("order_status") or "").strip() != ASK_NAME or parse_output.get("required_ask"):
        return parse_output
    if parse_output.get("capability_from") == "outstanding":
        return parse_output  # item 1 (owner 29 Oct, as before #1922): a dealer's outstanding ask takes a location
    moved = [
        " ".join(jsc.js_string(e.get("raw") or e.get("canonical_code") or "").split())
        for e in _current_entities(parse_output, "warehouse")
    ]
    if not moved:
        return parse_output
    words = dict(_dict(parse_output.get("report_ask_words")))
    words["warehouse"] = [w for w in moved if w]
    return {
        **parse_output,
        "entities": [
            e for e in jsc.array(parse_output.get("entities"))
            if not (isinstance(e, dict) and e in _current_entities(parse_output, "warehouse"))
        ],
        "report_ask_words": words,
    }


# --------------------------------------------------------------------------- #
# The lane's call
# --------------------------------------------------------------------------- #


def _resolve_word(db: Any, hint: str, word: str) -> tuple[list[str], list[str]]:
    """`(ids, names)` a word names. The resolvers let an exact name or code win alone."""
    if db is None:
        return [], []
    if hint == "brand":
        rows = [(b[0], b[1]) for b in business_services.resolve_brand_token(db, word)]
    elif hint == "sales_agent":
        rows = [(a[0], a[1]) for a in business_services.resolve_sales_agent_token(db, word)]
    else:
        rows = [(c[0], c[2] or c[1]) for c in business_services.resolve_category_token(db, word)]
    return [i for i, _n in rows], [n for _i, n in rows]


def _current_kinds(parse_output: dict[str, Any]) -> set[str]:
    return {
        jsc.js_string(e.get("hint") or "").strip().lower()
        for e in jsc.array(parse_output.get("entities"))
        if isinstance(e, dict) and e.get("current_message") is not False
    }


def _gate_ids(entities: Any, kind: str) -> list[str]:
    from app.services.chatbot.lanes.business.fetch import is_uuid

    out: list[str] = []
    for e in jsc.array(entities):
        if isinstance(e, dict) and e.get("entity_type") == kind and is_uuid(e.get("uuid")):
            uuid = jsc.js_string(e["uuid"])
            if uuid not in out:
                out.append(uuid)
    return out


def _current_entities(parse_output: dict[str, Any], hint: str) -> list[dict[str, Any]]:
    return [
        e
        for e in jsc.array(parse_output.get("entities"))
        if isinstance(e, dict)
        and e.get("current_message") is not False
        and jsc.js_string(e.get("hint") or "").strip().lower() == hint
    ]


def _dealer_outside(parse_output: dict[str, Any], group_by: str | None) -> bool:
    """1b fix round F1: does a dealer's ask reach past `reports.ask.DEALER_KEYS`? A staff
    dimension, or a sales agent, location or channel filter. Read off the words alone,
    BEFORE any is resolved, so the unknown-word line can never probe agent or location
    names for a dealer (the route refuses the same asks, `report_dimension_not_allowed`)."""
    from app.services.reports.ask import DEALER_KEYS, DEALER_OUTSTANDING_KEYS

    # Item 1 (owner 29 Oct, as before #1922): an outstanding ask also takes a location, over the dealer's own lines.
    located = parse_output.get("capability_from") == "outstanding"
    keys = DEALER_KEYS | DEALER_OUTSTANDING_KEYS if located else DEALER_KEYS
    words = _dict(parse_output.get("report_ask_words"))
    named = any(
        " ".join(jsc.js_string(w).split())
        for hint in ("sales_agent", "account_type") + (() if located else ("warehouse",))
        for w in jsc.array(words.get(hint))
    )
    return (
        (group_by is not None and group_by not in keys)
        or named
        or (not located and bool(_current_entities(parse_output, "warehouse")))
        or parse_output.get("sales_channel") in ("dealer", "project")
    )


_WORD_PARAMS = (("brand", "brand_ids"), ("sales_agent", "sales_agent_ids"), ("category", "category_ids"))


def _bound_by_id(db: Any, hint: str, word: str) -> tuple[list[str], list[str]] | None:
    """`(ids, names)` of the brand / sales agent / category row whose id the parser echoed (the candidate line's
    `[id: ...]`); None when the word is not an id at all (it is a label or a raw word)."""
    from app.services.chatbot.lanes.business.fetch import is_uuid

    if db is None or not is_uuid(word):
        return None
    if hint == "sales_agent" and staff_principal.lacks(db, staff_principal.SALES_AGENTS_VIEW):
        return [], []
    from app.models.product import Brand, ProductCategory
    from app.models.sales_agent import SalesAgent

    model, name_col = {
        "brand": (Brand, "brand_name"), "sales_agent": (SalesAgent, "sales_agent"), "category": (ProductCategory, "category_name"),
    }[hint]
    row = db.query(model).filter(model.id == word).first()
    return ([str(row.id)], [str(getattr(row, name_col) or "")]) if row is not None else ([], [])


def _word_filters(
    db: Any, parse_output: dict[str, Any], pairs: tuple[tuple[str, str], ...] = _WORD_PARAMS, *,
    agent_filter: bool = True, lenient: bool = False, scope: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """The brand / sales agent / category ids the verdict's `report_ask_words` resolve to, or
    the one line to say instead. Shared by a fresh ask and a ranking refine.

    `lenient` (a fresh ask, owner Q4 a): a word that binds to nothing is not the end of the ask. It rides on
    `out["_unbound"]` as `(Not applied text, the line to say)`, and the caller says the line only when the word was the
    sole subject. An id the parser echoed (H2) and an ambiguous word are never lenient.

    `scope` (semantic carry, `_object_scope`): the company the ask names. One rule for every word, typed or carried (the
    Held report line shows each row by a word that resolves back to it, `arg_names`): it is resolved here, through the
    permission-gated resolvers, and kept to the named company's rows (and the shared ones); an echoed id binds only to
    a row of that company; a word with no row there is not applied (said), never dropped."""
    out: dict[str, Any] = {}
    unbound: list[tuple[str, str]] = []
    agent_words: dict[str, list[str]] = {}
    company = jsc.js_string((scope or {}).get("company") or "").strip() or None

    def not_bound(hint: str, word: str, outside: bool = False) -> tuple[str, str]:
        noun = WORD_HINTS[hint]
        if outside:
            name = (scope or {}).get("company_name") or "that company"
            return f"{noun.capitalize()} {word} (not in {name})", f"I don't know '{word}' as a {noun} in {name}."
        return f"{noun.capitalize()} {word} (no such {noun})", f"I don't know '{word}' as a {noun}."

    def in_scope(hint: str, ids: list[str]) -> list[str]:
        return _in_company(db, hint, ids, company) if scope is not None else ids
    words = _dict(parse_output.get("report_ask_words"))
    for hint, param in pairs:
        ids: list[str] = []
        for word in jsc.array(words.get(hint)):
            word = " ".join(jsc.js_string(word).split())
            if not word:
                continue
            bound = _bound_by_id(db, hint, word)
            if bound is not None:
                bound_ids = in_scope(hint, bound[0])
                if not bound_ids:
                    return None, f"I don't know that {WORD_HINTS[hint]}."
                ids.extend(i for i in bound_ids if i not in ids)
                continue
            if hint == "category":
                # One category definition (owner, 4 Oct 2026): code or name, then the class
                # vocabulary ("water closet").
                from app.services.chatbot.lanes import business as business_pkg

                found, _named, ambiguous, unknown = business_pkg._top_selling_category_ids(
                    {"category_words": [word]}, db=db
                )
                if unknown or (not found and not ambiguous):
                    # A word that matched nothing is said, never dropped from the filter.
                    if lenient:
                        unbound.append(not_bound(hint, word))
                        continue
                    return None, f"I don't know '{word}' as a {WORD_HINTS[hint]}."
                if ambiguous:
                    listed = ", ".join(sorted(set(ambiguous)))
                    return None, f"'{word}' matches several {SEVERAL_NOUNS[hint]}: {listed}. Ask again naming one."
                inside = in_scope(hint, [str(i) for i in found])
                if not inside:  # a row of another company only
                    if lenient:
                        unbound.append(not_bound(hint, word, outside=True))
                        continue
                    return None, not_bound(hint, word, outside=True)[1]
                ids.extend(i for i in inside if i not in ids)
                continue
            if hint == "sales_agent" and word.casefold() == jsc.js_string(parse_output.get("sales_channel") or "").casefold():
                continue  # the channel word the verdict already set (`sales_channel`), not a person
            found, names = _resolve_word(db, hint, word)
            if not found:
                if lenient:
                    unbound.append(not_bound(hint, word))
                    continue
                return None, f"I don't know '{word}' as a {WORD_HINTS[hint]}."
            if scope is not None:
                inside = set(in_scope(hint, found))
                if not inside:  # a row of another company only
                    if lenient:
                        unbound.append(not_bound(hint, word, outside=True))
                        continue
                    return None, not_bound(hint, word, outside=True)[1]
                found, names = [i for i in found if i in inside], [n for i, n in zip(found, names) if i in inside]
            distinct = {" ".join(n.split()).casefold(): " ".join(n.split()) for n in reversed(names)}
            if hint == "sales_agent" and len({business_services._code_stem(n) for n in names}) > 1:
                if not agent_filter:
                    return None, DEALER_REFUSAL  # the route refuses this contact the agent dimension: no list of agents
                # H3: several DIFFERENT agents answer to the word (accounts of one person share a code stem and
                # stay one person's union, below): the person picks one, agents only, and nothing runs yet.
                out["sales_agent_pick"] = list(dict(zip(found, names)).items())
                continue
            if len(distinct) > 1 and hint in SEVERAL_NOUNS:
                # 1b code review S3: never a silent widening (the PR #1273 rule). Hits sharing
                # one name (a brand per company) are ONE brand, their ids a union; several
                # sales agent rows for one word stay a union too: one person's accounts.
                listed = ", ".join(sorted(distinct.values()))
                return None, f"'{word}' matches several {SEVERAL_NOUNS[hint]}: {listed}. Ask again naming one."
            ids.extend(i for i in found if i not in ids)
            if hint == "sales_agent" and scope is not None:
                agent_words[word] = [i for i in found if i]  # the word as typed and the rows it resolved to (`arg_names`)
        if ids:
            out[param] = ids
    if unbound:
        out["_unbound"] = unbound
    if agent_words:
        out["_agent_words"] = agent_words
    return out, None


def _is_brand(db: Any, word: str, typed: str = "") -> bool:
    """Does this word name a brand: its row id (the parser echoed the candidate) first; an id that binds nothing, or
    no id, falls back to resolving the typed word."""
    bound = _bound_by_id(db, "brand", word)
    if bound is not None and bound[0]:
        return True
    # Only an id that binds nothing falls back to the typed word; a plain word is resolved as it stands.
    return bool(_resolve_word(db, "brand", (typed or word) if bound is not None else word)[0])


def _account_plan(
    db: Any, parse_output: dict[str, Any], companies: Any = (), *, ask: bool = False, held_company: Any = None
) -> dict[str, Any]:
    """SALES-ACCOUNT-TYPE PR 2: the brand and account type words of a fresh ask, read against the DATA (the stored
    types of the scoped session, the brands the resolver knows), never the user's words. The parser only says which
    kind of word it heard (`hint`) and whether the message itself said it (`kind_said`, key absent = a prompt text
    that does not define it).

    Returns `account_types` (the filter values: a type in its stored spelling, a number or tag as typed), `drop`
    (brand words that are not brand filters after all) and `ask` (words that are both a brand and a stored type, with
    nothing in the message to settle them: asked once). `ask=False` reads such a word as the brand, as before."""
    words = _dict(parse_output.get("report_ask_words"))
    brand_words = [w for w in (" ".join(jsc.js_string(x).split()) for x in jsc.array(words.get("brand"))) if w]
    acct_words = [w for w in (" ".join(jsc.js_string(x).split()) for x in jsc.array(words.get("account_type"))) if w]
    plan: dict[str, Any] = {"account_types": [], "drop": set(), "ask": [], "brand_words": []}
    if db is None or not (brand_words or acct_words):
        return plan
    from app.services.reports.ask_params import account_book, account_type_options, resolve_account_types

    stored = {name.strip().casefold(): name for name, _label in account_type_options(db)}
    entries = {
        (e.get("hint"), e.get("word")): e for e in jsc.array(parse_output.get("report_ask_kind")) if isinstance(e, dict)
    }
    numbers = [w for w in acct_words if w.casefold() not in stored]
    own = [c for c in list(companies or ()) if isinstance(c, (list, tuple)) and len(c) >= 3]
    decided: list[tuple[str, str, str, str]] = []  # (how, hint, word, stored type); how: brand | account | ask
    for hint, word in [("brand", w) for w in brand_words] + [("account_type", w) for w in acct_words]:
        entry = entries.get((hint, word))
        typed = jsc.js_string((entry or {}).get("raw") or word)
        kind = stored.get(word.casefold()) or stored.get(typed.casefold())
        if kind is None:
            continue
        if entry is None:
            how = "brand" if hint == "brand" else "account"
        elif entry.get("said") is True:
            how = "brand" if hint == "brand" else "account"
        elif _is_brand(db, word, typed):
            # REPORT-FILTER-ALL (crew gate R2 / step 15, 1104 holds a SORENTO debtor type): a brand that is also one of
            # the contact's own companies is that company or its brand (owner: a bare Sorento asks company or brand once,
            # `_company_or_brand`), never a third reading as the debtor type of the same name. Read from the data.
            company_name = len(own) > 1 and {_squash(word), _squash(typed)} & {_squash(c[i]) for c in own for i in (1, 2)}
            how = "brand" if company_name else "ask" if ask else "brand"
        else:
            how = "account"
        decided.append((how, hint, word, kind))
    ids = [str(c[0]) for c in own]
    said_company = " ".join(jsc.js_string(parse_output.get("sales_company") or "").split()).casefold()
    if said_company:  # a named company narrows the book to that company
        ids = [str(c[0]) for c in own if said_company in (str(c[1]).casefold(), str(c[2]).casefold())] or ids
    elif held_company and str(held_company) in ids:
        ids = [str(held_company)]  # a refine reads the company the held ask ran for
    per_company: dict[str, set] = {}
    if numbers and ids and decided:
        per_company, _unknown = resolve_account_types(account_book(db, ids), numbers)

    def same_type(kind: str) -> bool:
        """Only the companies that READ the number count: at least one does, and every one that does reads it as this
        type. None reads it: not the same (the brand stays, the route says the number is unknown)."""
        readers = [cid for cid in ids if per_company.get(cid)]
        return bool(readers) and all(
            kind.strip().casefold() in {t.strip().casefold() for t in per_company[cid]} for cid in readers
        )

    account: list[str] = []
    for how, hint, word, kind in decided:
        same = same_type(kind)
        if how == "brand":
            continue  # said as a brand: the brand filter stays beside any number
        if how == "ask" and numbers:
            if same:
                plan["drop"].add(word)  # the number is this word's own type: the account filter alone
            elif hint == "account_type":
                plan["brand_words"].append(word)  # a bare word hinted account type reads as the brand on that account
            continue  # another type: the brand on that account
        if how == "ask":
            typed = " ".join(jsc.js_string((entries.get((hint, word)) or {}).get("raw") or word).split())
            # The typed word is printed only when it IS the stored type's name (case aside); anything else prints the
            # stored name, so nothing a customer typed reaches the reply otherwise.
            shown = typed if typed.casefold() == kind.strip().casefold() else kind
            bound = _bound_by_id(db, "brand", word)
            # The word the brand is resolved by: its row id, or (an id that binds nothing) the typed word.
            plan["ask"].append({
                "hint": hint, "word": typed if bound is not None and not bound[0] else word, "raw": typed, "type": kind,
                "shown": shown,
            })
            plan["drop"].add(word)
            continue
        if hint == "brand":
            plan["drop"].add(word)
        if not same and kind not in account:
            account.append(kind)
    plan["account_types"] = [*account, *[n for n in numbers if n not in account]]
    return plan


def _brand_words(words: dict[str, Any], plan: dict[str, Any]) -> list[Any]:
    """The brand words left to resolve: the ones the plan did not take for the account filter or the question, and a
    bare word hinted account type that a number made the brand."""
    kept = [w for w in jsc.array(words.get("brand")) if " ".join(jsc.js_string(w).split()) not in plan["drop"]]
    return [*kept, *[w for w in plan["brand_words"] if w not in kept]]


def _kind_ask(
    db: Any, parse_output: dict[str, Any], plan: dict[str, Any], args: dict[str, Any], scope: dict[str, Any] | None = None,
    companies: Any = (),
) -> tuple[dict[str, Any] | None, str | None]:
    """The held answer of the word question: the words as printed, the spellings a repeat may carry, and for each choice
    the route params it sets. `args` holds what THIS message settled for the same params; the answer REPLACES any
    held value of them. `companies` (the object path, crew C6-1, SC-19): when every asked word is one of the contact's
    companies (its name or code, from data), that company is a third choice."""
    brand_words = [a["word"] for a in plan["ask"]]
    found, line = _word_filters(
        db, {**parse_output, "report_ask_words": {"brand": brand_words}}, (("brand", "brand_ids"),), scope=scope
    )
    if found is None:
        return None, line
    brand_ids = [*jsc.array(args.get("brand_ids")), *[i for i in found.get("brand_ids", []) if i not in jsc.array(args.get("brand_ids"))]]
    types = [*jsc.array(args.get("account_types")), *[a["type"] for a in plan["ask"] if a["type"] not in jsc.array(args.get("account_types"))]]
    asked = {
        "words": [a["shown"] for a in plan["ask"]],
        "match": [w for a in plan["ask"] for w in (a["raw"], a["type"])],
        "held": [{"word": a["word"], "raw": a["raw"], "type": a["type"]} for a in plan["ask"]],
        "choices": {"brand": {"brand_ids": brand_ids}, "account_type": {"account_types": types}},
    }
    per_word = [
        {(str(c[0]), str(c[1])) for c in _own_companies(companies) if {_squash(a[k]) for k in ("word", "raw", "type")} & {_squash(c[1]), _squash(c[2])}}
        for a in plan["ask"]
    ]
    one = per_word[0] if per_word and len(per_word[0]) == 1 and all(p == per_word[0] for p in per_word) else set()
    if one:
        asked["company"] = list(next(iter(one)))
    return asked, None


def _company_or_brand(db: Any, parse_output: dict[str, Any], plan: dict[str, Any], companies: Any) -> dict[str, Any] | None:
    """M2 (owner Q2 c): the slots say which name is in doubt, the DATA settles it. A name in the object's
    `company_or_brand`, or a brand word left unsaid (`kind_said` null, `report_ask_kind`) that is the very company the
    object also names, is read against the brand catalogue and the contact's companies (its name or code, as `_kind_ask`
    reads it): one of those companies AND a brand is asked (`ask`), company or brand or both; a company and no brand is
    that company; a contact who sees one company gets the brand. None for any other word, and for one the account type
    plan already took.

    HT1-5: a word whose entity carries `said_as` null (`take_words` keeps it as `as`; a non-null one already decided the
    name's slot, `_word_kinds`) with no company named or held is in doubt too: asked when it is a brand, never a silent
    brand filter. An entry with no `as` (a text that does not define the key) keeps the rules above exactly."""
    own = _own_companies(companies)
    if db is None or not own:
        return None
    either = {_squash(w or "") for w in jsc.array(_dict(parse_output.get(OBJECT_KEY)).get("company_or_brand"))} - {""}
    named, _foreign = _company_said(parse_output, own)
    # CP-5: a company the held report already ran for is carried, not new in this message: the same name in brands is
    # this message's new brand, no doubt to ask.
    held_company = {str(i) for i in _dict(_dict(parse_output.get(HELD_IDS_KEY)).get("company"))}
    if named is not None and str(named[0]) in held_company:
        named = None
    for entry in jsc.array(parse_output.get("report_ask_kind")):
        if not isinstance(entry, dict) or entry.get("hint") != "brand" or entry.get("said") is True:
            continue
        word = " ".join(jsc.js_string(entry.get("word") or "").split())
        typed = " ".join(jsc.js_string(entry.get("raw") or word).split())
        if not word or word in plan["drop"]:
            continue
        forms = {_squash(word), _squash(typed)}
        hits = [c for c in own if forms & {_squash(c[1] or ""), _squash(c[2] or "")}]
        unsaid = "as" in entry and entry["as"] is None and named is None and not held_company  # HT1-5
        if len(hits) != 1 or not (forms & either or (named is not None and str(named[0]) == str(hits[0][0])) or unsaid):
            continue
        brand = _is_brand(db, word, typed)
        if brand and len(own) < 2:
            continue  # one company: the brand, nothing to ask
        return {"word": word, "raw": typed, "company": [str(hits[0][0]), str(hits[0][1])], "ask": brand}
    return None


def _company_brand_ask(
    db: Any, parse_output: dict[str, Any], either: dict[str, Any], args: dict[str, Any], scope: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, str | None]:
    """M2: the held answer of the company-or-brand question (`_kind_ask`'s shape): printed by the company's own name, the
    company option is that company (`kind_company`, `from_object`), the brand and both options carry the brand ids."""
    found, line = _word_filters(
        db, {**parse_output, "report_ask_words": {"brand": [either["word"]]}}, (("brand", "brand_ids"),), scope=scope
    )
    if found is None:
        return None, line
    held = jsc.array(args.get("brand_ids"))
    brand_ids = [*held, *[i for i in found.get("brand_ids", []) if i not in held]]
    return {
        "words": [either["company"][1]],
        "match": [either["word"], either["raw"]],
        "held": [{"word": either["word"], "raw": either["raw"], "type": None}],
        "choices": {"brand": {"brand_ids": brand_ids}, BOTH_KIND_OPTION[0]: {"brand_ids": brand_ids}},
        "company": either["company"],
        "both": True,
    }, None


def _product_args(
    entities: Any, *, total: bool = False, exact: bool = False, typed_codes: Any = ()
) -> tuple[dict[str, Any] | None, str | None]:
    """The route's product param for the product entities a message named, or the one line to
    say instead. 1b code review S4: the sales report's PREFIX rule (S19), so "SRT5674" covers
    "SRT5674-N"; several codes travel as the prefix they share. `exact` (an outstanding ask, REPORT-OUTSTANDING-SUMMARY
    item 8, owner 29 Oct): the rows the shared resolver matched, by id, however many and however unrelated, as the
    pre-#1922 outstanding report took the resolved codes; never a prefix the route would widen."""
    from app.services.chatbot.lanes.business.fetch import (
        is_mixed_code_set,
        outstanding_product_codes,
        sales_report_product_code,
    )

    products = [e for e in jsc.array(entities) if isinstance(e, dict) and e.get("entity_type") == "product"]
    if exact:
        # AC-1119, as the pre-#1922 report's seam (`_resolve_report_product_and_location`): a row whose code is the
        # code the customer TYPED is the subject, never its family siblings the resolver also returned.
        typed = [e for e in products if jsc.js_string(e.get("code") or e.get("canonical_code") or "").strip().casefold()
                 in set(typed_codes)]
        ids = _gate_ids(typed or products, "product")
        if len(ids) > DRILL_MAX_KEYS:
            return None, MIXED_PRODUCTS_LINE
        return ({"product_ids": ids} if ids else {}), None
    found = outstanding_product_codes(products, {})
    if is_mixed_code_set(found):
        # A word that fanned out to unrelated codes is never frozen on the first of them. A TOTAL never runs on
        # the whole set either: the product is asked (owner review 22 Oct, item 4). A ranking (it has an axis) takes
        # the whole set as `product_ids` (the substring tier, as it always did); past the cap, or with no resolved
        # row, the product is asked.
        ids = _gate_ids(products, "product")
        if total or not ids or len(ids) > DRILL_MAX_KEYS:
            return None, MIXED_PRODUCTS_LINE
        return {"product_ids": ids}, None
    code = sales_report_product_code(products, {})
    return ({"product_code": code} if code else {}), None


def _without_carried_products(parse_output: dict[str, Any], entities: Any) -> list[Any]:
    """REPORT-UNIFY (P4): a product named in THIS message replaces a carried one. The gate's rows carry no
    `current_message`, so a row whose code a carried product entity says (and no current one does) is dropped."""
    products = [e for e in jsc.array(parse_output.get("entities")) if isinstance(e, dict) and e.get("hint") == "product"]

    def said(entity: dict[str, Any]) -> set[str]:
        return {
            jsc.js_string(entity.get(k) or "").strip().upper() for k in ("raw", "canonical_code") if entity.get(k)
        }

    current = set().union(*(said(e) for e in products if e.get("current_message") is not False))
    carried = set().union(*(said(e) for e in products if e.get("current_message") is False)) - current
    if not current or not carried:
        return jsc.array(entities)
    return [
        e for e in jsc.array(entities)
        if not (isinstance(e, dict) and e.get("entity_type") == "product"
                and jsc.js_string(e.get("code") or "").strip().upper() in carried)
    ]


def _fresh_args(
    db: Any, parse_output: dict[str, Any], entities: Any, *, dealer: bool = False, agent_filter: bool = True,
    companies: Any = (), ask_kind: bool = False, held_company: Any = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """The route params a fresh ask names (every one but the period and top_n), or the one
    line to say instead of running. `dealer`: the turn's contact is customer-scoped."""
    raw_group = jsc.js_string(parse_output.get("group_by") or "").strip().lower()
    group_by = GROUP_BY.get(raw_group) if raw_group else None
    if raw_group and group_by is None:
        return None, CATALOGUE_LINE
    if dealer and _dealer_outside(parse_output, group_by):
        return None, DEALER_REFUSAL

    # Neither the basis nor the metric is defaulted: one the message did not name is asked.
    args: dict[str, Any] = {"sort": "asc" if parse_output.get("rank_direction") == "bottom" else "desc"}
    if basis_from(parse_output):
        args["basis"] = basis_from(parse_output)
    if metric_from(parse_output):
        args["measure"] = metric_from(parse_output)
    if group_by:
        args["group_by"] = group_by
    channel = parse_output.get("sales_channel")
    if channel in ("dealer", "project"):
        args["channel"] = channel
    if parse_output.get("compare_to") in COMPARE_TO:
        args["compare_to"] = parse_output["compare_to"]
    if parse_output.get("self_reference") is True:
        args["mine"] = True

    plan = (
        _account_plan(db, parse_output, companies, ask=ask_kind, held_company=held_company)
        if not dealer else _account_plan(None, {})
    )
    words = _dict(parse_output.get("report_ask_words"))
    scope = _object_scope(parse_output, companies)
    # M2 (owner Q2 c), the object path: a name in doubt (`_company_or_brand`) that is a brand and one of the contact's
    # companies is asked once, company, brand or both; one that is only a company is that company. Neither is a brand
    # filter.
    either = (
        _company_or_brand(db, parse_output, plan, companies)
        if scope is not None and ask_kind and not dealer and not plan["ask"] else None
    )
    if either is not None:
        plan["drop"].add(either["word"])
    read = {**parse_output, "report_ask_words": {**words, "brand": _brand_words(words, plan)}}
    filters, line = _word_filters(db, read, agent_filter=agent_filter, lenient=True, scope=scope)
    if filters is None:
        return None, line
    unbound = filters.pop("_unbound", [])
    agent_words = filters.pop("_agent_words", None)
    args.update(filters)
    if plan["account_types"]:
        args["account_types"] = plan["account_types"]
    if plan["ask"]:
        # The company as a third kind (C6-1) is the object path's (`scope`): the flag-off path keeps its two kinds.
        asked, line = _kind_ask(db, parse_output, plan, args, scope=scope, companies=companies if scope is not None else ())
        if asked is None:
            return None, line
        args["_kind_ask"] = asked  # popped by `settle`; never a route param
    elif either is not None and either["ask"]:
        asked, line = _company_brand_ask(db, parse_output, either, args, scope)
        if asked is None:
            return None, line
        args["_kind_ask"] = asked  # popped by `settle`; never a route param
    elif either is not None:
        args["company"] = either["company"][0]  # M2: a company and no brand is that company

    # The gate's resolved rows, of the kinds THIS message named (a carried subject from an
    # earlier question is not this ask's filter).
    kinds = _current_kinds(parse_output)
    if parse_output.get("ranking_pick") is True:
        # The turn that answered this ranking's customer pick: the picked row is carried, not typed, and is
        # still this ask's customer (the engine marks it; the parser cannot, `required_fields.ENGINE_KEYS`).
        kinds = kinds | {"customer"}
    if _dict(parse_output.get(HELD_KEY)).get("product") is True and _widened(parse_output) != "product":
        # R8: the products the held sales report total ran on are carried, not typed (the plan's own rows, the
        # same ones `crm_sales_report` read its prefix off); the engine marks it, never the parser.
        kinds = kinds | {"product"}
    if parse_output.get("capability_from") == "outstanding" and not kinds & {
        "product", "customer", "brand", "category", "product_type", "specification", "spec"
    } and not jsc.array(parse_output.get("report_ask_spec")):
        # Eval send-back (rpt-010, rpt-009), as before #1922: an outstanding ask that names no product or customer of
        # its own runs on the product in context ("<code> stock", then "outstanding"), never the whole company's list.
        kinds = kinds | {"product"}
    customer_ids = _gate_ids(entities, "customer") if "customer" in kinds else []
    if scope is not None:
        # Semantic carry: a held customer the object names again is the id it ran with when that id is in the named
        # company (or none is named), so a shared name never widens; else the name is looked up again in the named
        # company (`_customer_in`); one with no row there is not applied (said).
        # A dealer's are only among its own linked accounts (the engine's scope rows).
        linked = _gate_ids([e for e in jsc.array(entities) if isinstance(e, dict) and e.get("scope")], "customer") if dealer else None
        for name in jsc.array(_dict(parse_output.get(OBJECT_KEY)).get("customers")):
            name = " ".join(jsc.js_string(name).split())
            held = _held_ids(_dict(scope.get("held")), "customer_ids", name)
            if not held:
                continue  # not held: its entity went to the resolver (`from_object`)
            inside = _in_company(db, "customer", held, scope.get("company")) or _customer_in(db, name, scope.get("company"))
            inside = [i for i in inside if linked is None or i in linked]
            if inside:
                customer_ids.extend(i for i in inside if i not in customer_ids)
            else:
                # The reply a word with no row in the named company gets (`_word_filters`), carried or typed.
                company_name = scope.get("company_name") or "that company"
                unbound.append((f"Customer {name} (not in {company_name})", f"I don't know '{name}' as a customer in {company_name}."))
    if parse_output.get("self_reference") is True and not customer_ids:
        # "my ...": the engine's scope rows, a linked contact's own accounts, whether a dealer or office staff. A
        # dealer's ask naming no customer sends none: the route forces its links itself.
        customer_ids = [
            u for u in _gate_ids([e for e in jsc.array(entities) if isinstance(e, dict) and e.get("scope")], "customer")
        ]
    if "customer" in kinds and not customer_ids and _gate_ids(entities, "product"):
        kinds = kinds | {"product"}  # a word hinted customer that only resolved as a product (the resolver's own fallback)
    if customer_ids:
        args["customer_ids"] = customer_ids
    if "product" in kinds:
        product_args, line = _product_args(
            _without_carried_products(parse_output, entities), total=not group_by,
            # A spec narrows a product FAMILY (owner Q3, prod turn P8): the family keeps its prefix there.
            exact=parse_output.get("capability_from") == "outstanding" and not jsc.array(parse_output.get("report_ask_spec")),
            typed_codes={
                jsc.js_string(e.get("canonical_code") or e.get("raw") or "").strip().casefold()
                for e in _current_entities(parse_output, "product")
            } - {""},
        )
        if product_args is None:
            return None, line
        args.update(product_args)

    if jsc.array(parse_output.get("report_ask_spec")):
        args["spec"] = [jsc.js_string(t) for t in jsc.array(parse_output["report_ask_spec"])]

    codes: list[str] = []
    outstanding_ask = parse_output.get("capability_from") == "outstanding"
    for e in _current_entities(parse_output, "warehouse"):
        token = jsc.js_string(e.get("raw") or e.get("canonical_code") or "").strip()
        if not token:
            continue
        found = business_services.resolve_warehouse_token(db, token) if db is not None else []
        if not found and outstanding_ask:
            # Item 9 (owner 29 Oct, as before #1922): an outstanding ask's unknown location word narrows nothing and is
            # not answered (`_resolve_report_product_and_location`); one location word per turn (D5).
            break
        if not found:
            return None, f"I don't know '{token}' as a location."
        codes.extend(c for c in found if c not in codes)
        if outstanding_ask:
            break
    if codes:
        args["warehouse_codes"] = codes
    if unbound:
        if not set(args) - _NON_FILTER_ARGS - {"date_from", "date_to", "top_n"}:
            return None, unbound[0][1]  # the word was the only subject: said, and the ask
        args["_unbound"] = [text for text, _line in unbound]  # popped by `settle`; never a route param
    if agent_words:
        args["_agent_words"] = agent_words  # popped by `settle`; never a route param
    return args, None


#: The keys `_fresh_args` always sets (or an axis); any other key it sets is a filter.
_NON_FILTER_ARGS = frozenset({"basis", "measure", "sort", "group_by", "compare_to", "mine", "company"})


def _given_top_n(args: dict[str, Any], top_n: Any) -> dict[str, Any]:
    """The number as the helper's `given`: a total needs none (settled as None, never
    asked); a number the first message named is taken, or read as a word (a miss)."""
    if not args.get("group_by"):
        return {"top_n": rf.Resolved("ok", value=None, label="")}
    got = top_n_from(top_n)
    if args.get("group_by") in TREND_AXES and got.status != "ok":
        return {"top_n": rf.Resolved("ok", value=MONTH_TOP_N, label=str(MONTH_TOP_N))}
    if top_n is None:
        return {}
    return {"top_n": got if got.status == "ok" else jsc.js_string(top_n)}


def _given_choices(args: dict[str, Any]) -> dict[str, Any]:
    """The metric and the basis as the helper's `given`, off the args a message named. A total
    and a month trend show both measures, so they are never asked the metric (settled as None);
    the basis is always asked unless named. Anything not named is left out, so it is asked."""
    given: dict[str, Any] = {}
    if not args.get("group_by") or args.get("group_by") in TREND_AXES:
        given["metric"] = rf.Resolved("ok", value=args.get("measure"), label=args.get("measure") or "")
    elif args.get("measure"):
        given["metric"] = rf.Resolved("ok", value=args["measure"], label=args["measure"])
    if args.get("basis"):
        given["basis"] = rf.Resolved("ok", value=args["basis"], label=args["basis"])
    return given


def _choice(value: str | None) -> rf.Resolved | None:
    return rf.Resolved("ok", value=value, label=value) if value else None


def _reply_fills(
    parse_output: dict[str, Any], values: dict[str, Any], held: dict[str, Any]
) -> dict[str, rf.Resolved]:
    """Chat fix PR-B S1 (owner, 16 Oct 2026): every OPEN field an answering turn's parse
    settles, off the parser's own fields (dates, `top_n`, `measure` / `rank_by`, `basis`),
    never the reply's words ("2026, top 10, by quantity delivered" settles all four). A field
    the slot already holds, or the first message settled (`held`), is not open."""

    def is_open(name: str) -> bool:
        got = held.get(name)
        return name not in values and not (isinstance(got, rf.Resolved) and got.status == "ok")

    reading = {
        "period": period_from(parse_output.get("date_filter_start"), parse_output.get("date_filter_end")),
        "top_n": top_n_from(parse_output.get("top_n")),
        "metric": _choice(metric_from(parse_output)),
        "basis": _choice(basis_from(parse_output)),
    }
    filled = {name: got for name, got in reading.items() if got is not None and got.status == "ok" and is_open(name)}
    # R7: a total's / month trend's metric is settled EMPTY (both measures shown); a measure typed in the
    # answer still fills it, so the route and the held frame carry it (never top_n: that stays None). Only
    # a reply that already fills an owed field is the answer; a measure alone is not (swap, fresh ask, compare).
    metric, settled = reading["metric"], held.get("metric")
    if (
        filled and "metric" not in filled and metric is not None and metric.status == "ok"
        and isinstance(settled, rf.Resolved) and settled.status == "ok" and settled.value is None
        and _dict(values.get("metric")).get("value") is None
    ):
        filled["metric"] = metric
    return filled


#: R5 B: the ranking a row pick opens: (the detail's group_by, the filter key carrying the picked row's keys).
_DETAIL_OF = {
    "product": ("customer", "product_ids"),
    "category": ("product", "category_ids"),
    "sales_agent": ("customer", "sales_agent_ids"),
    "customer": ("product", "customer_ids"),
}


def _detail_outcome(db: Any, frame: dict[str, Any], detail: dict[str, Any]) -> rf.Outcome:
    """REPORT-SMART-L R3c (owner Q2 b): the row a rank number picked, opened on the report engine under the
    ranking's own period, basis, measure and filters. An item: its customers (and, second, its months); a
    category: its items. The row's keys are the pick's own resolved ids, never a word."""
    keys = [str(k) for k in detail.get("keys") or []]
    base = {k: v for k, v in frame.items() if k not in _FRAME_ONLY and k != "group_by"}
    for key in _AXIS_FILTERS.get(frame.get("group_by") or "", ()):
        base.pop(key, None)
    group_by, key = _DETAIL_OF[frame["group_by"]]
    args = {**base, "group_by": group_by, key: keys}
    top_n = frame.get("top_n") if frame.get("group_by") == "category" else BREAKDOWN_TOP_N
    given = {**_given_choices(args), **_given_top_n(args, top_n)}
    period = period_from(frame.get("date_from"), frame.get("date_to"))
    if period is not None:
        given["period"] = period
    outcome = rf.collect(db, SALES_RANKING_ASK, given=given, extras={"args": args, "top_n": top_n})
    if frame.get("group_by") != "category":
        outcome.extras["detail_second"] = "month"
    outcome.extras["detail"] = True
    return outcome


#: Owner 28 Oct 09:30 (AC-RU-17a): the pick an undelivered-orders total arms ("Reply 1 for the sales order list.").
SO_LIST = "sales_order_list"
#: REPORT-OUTSTANDING-SUMMARY: the pick a pending-delivery summary arms ("Reply 1 for the delivery order list.").
DO_LIST = "delivery_order_list"
#: Item 6 (owner 29 Oct): a "more" under a cut outstanding summary (`turn/apply._answer_top_selling_pick`): the held
#: summary's next page, `ranking_detail = {"group_by": MORE_PAGE, "offset": n}`.
MORE_PAGE = "summary_more"
#: Outstanding kind -> the pick its list offer arms, and the pick -> the document grouping it runs.
LIST_PICKS = {"outstanding": SO_LIST, "pending_delivery": DO_LIST}
_LIST_GROUP = {SO_LIST: "sales_order", DO_LIST: "delivery_order"}


def so_list_outcome(db: Any, frame: dict[str, Any], pick: str = SO_LIST, *, offset: Any = None) -> rf.Outcome:
    """The documents behind an outstanding total: the SAME held ask (basis, filters, company, period) grouped by the
    definition's document dimension (`sales_order` for undelivered orders, `delivery_order` for pending delivery), so
    the list is the figure's own population."""
    args = {k: v for k, v in frame.items() if k not in _FRAME_ONLY}
    args["group_by"] = _LIST_GROUP[pick]
    if isinstance(offset, int) and not isinstance(offset, bool) and offset > 0:
        args["group_offset"] = offset  # a "more" under the list: its next page
    args.setdefault("measure", "amount")  # the list prints both figures; the order is by RM
    given = {**_given_choices(args), **_given_top_n(args, BREAKDOWN_TOP_N)}
    period = period_from(frame.get("date_from"), frame.get("date_to"))
    given["period"] = period if period is not None else rf.Resolved("ok", value={"from": None, "to": None}, label="all dates")
    outcome = rf.collect(db, SALES_RANKING_ASK, given=given, extras={"args": args, "top_n": BREAKDOWN_TOP_N})
    outcome.extras["detail"] = True  # a list on screen never replaces the held total
    return outcome


def more_outcome(db: Any, frame: dict[str, Any], offset: Any) -> rf.Outcome:
    """Item 6: the held outstanding ask again, unchanged but for the page of its long breakdown (`group_offset`)."""
    args = {k: v for k, v in frame.items() if k not in _FRAME_ONLY}
    args["group_offset"] = offset if isinstance(offset, int) and not isinstance(offset, bool) and offset > 0 else 0
    given = {**_given_choices(args), **_given_top_n(args, args.get("top_n"))}
    period = period_from(frame.get("date_from"), frame.get("date_to"))
    given["period"] = period if period is not None else rf.Resolved("ok", value={"from": None, "to": None}, label="all dates")
    given.setdefault("metric", rf.Resolved("ok", value=args.get("measure"), label=args.get("measure") or ""))
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras={"args": args, "top_n": args.get("top_n")})


def settle(
    db: Any, parse_output: dict[str, Any], entities: Any, *, dealer: bool = False, agent_filter: bool = True,
    companies: Any = (), kinds: tuple[str, ...] = ASKED_KINDS,
) -> tuple[rf.Outcome | None, str | None]:
    """`_settle`, with the word question asked as its own bare line (`_kind_question`); the slot keeps its options, and
    the parser's declared pick of one of them is the only answer (`required_fields.picked_option`: the kind and sales
    agent fields are `parser_only`). `kinds`: the outstanding kinds the contact may see (`outstanding_kinds`); with one,
    an outstanding ask naming none is that kind, unasked."""
    if (
        len(kinds) == 1 and parse_output.get("capability_from") == "outstanding"
        and parse_output.get("basis") not in OUTSTANDING_KINDS
    ):
        parse_output = {**parse_output, "basis": kinds[0]}
    outcome, line = _settle(db, parse_output, entities, dealer=dealer, agent_filter=agent_filter, companies=companies)
    if outcome is not None and outcome.slot and outcome.slot.get("asking") == "kind" and outcome.reply:
        outcome.reply = _kind_question(_dict(outcome.slot.get("extras")))  # bare, as the mock draws it
    asked = _dict(outcome.values.get("kind")) if outcome is not None else {}
    if asked.get("value") == rf.ALL and outcome is not None:
        # Two unreadable answers to the kind question: a plain give-up, never a run (an unanswered kind would run
        # without the word).
        word = str(asked.get("missed") or "that")
        return rf.Outcome(values=outcome.values, reply=GIVE_UP.format(word=word), slot=None, extras=outcome.extras), line
    return outcome, line


def _settle(
    db: Any, parse_output: dict[str, Any], entities: Any, *, dealer: bool = False, agent_filter: bool = True,
    companies: Any = (),
) -> tuple[rf.Outcome | None, str | None]:
    """Every required field settled, or the line to send instead of running. Returns
    `(outcome, None)` (send `outcome.reply` with `outcome.slot` unless `outcome.done`), or
    `(None, line)` for a word or a dimension the ask cannot run with.

    The slot's extras carry the first message's args and its number (`top_n`), so an
    answering turn runs the first message's ask; every field still missing is asked in one
    numbered reply (chat fix PR-B S1), and an answer settling any of them is read whole."""
    parse_output = typed_group_by(parse_output)
    slot = parse_output.get("required_ask")
    ranking_detail = parse_output.get("ranking_detail")
    shown_frame = _dict(parse_output.get("sales_ranking_frame"))
    if (
        isinstance(ranking_detail, dict)
        and ranking_detail.get("keys")
        and shown_frame.get("group_by") in _DETAIL_OF
        and ranking_detail.get("group_by") == shown_frame.get("group_by")  # the pick is of the list on screen
    ):
        return _detail_outcome(db, shown_frame, ranking_detail), None
    if (
        isinstance(ranking_detail, dict)
        and ranking_detail.get("group_by") == MORE_PAGE
        and shown_frame.get("basis") in OUTSTANDING_KINDS
    ):
        if LIST_PICKS.get(shown_frame.get("basis")) == ranking_detail.get("list"):
            # Eval hard guard: the next page of the document list "1" printed under this summary.
            return so_list_outcome(db, shown_frame, ranking_detail["list"], offset=ranking_detail.get("offset")), None
        return more_outcome(db, shown_frame, ranking_detail.get("offset")), None
    if (
        isinstance(ranking_detail, dict)
        and ranking_detail.get("group_by") in LIST_PICKS.values()
        and LIST_PICKS.get(shown_frame.get("basis")) == ranking_detail.get("group_by")
    ):
        return so_list_outcome(db, shown_frame, ranking_detail["group_by"]), None
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME and slot.get("asking") == "scope":
        return _scope_answer(db, parse_output, slot), None
    semantic = isinstance(parse_output.get(OBJECT_KEY), dict)
    if semantic:
        # SALES-ACCOUNT-TYPE semantic carry (A3): the parser's object is the whole ask (`from_object`). A scoped drill over
        # the rows on screen runs first (V5); then the ask is read as a fresh one: no open slot, no held frame, no refine.
        shown_frame = _dict(parse_output.get("sales_ranking_frame"))
        if parse_output.get("ranking_drill") == "scoped" and shown_frame:
            drilled = _drill(db, parse_output, shown_frame, entities, reading="scoped", dealer=dealer, companies=companies)
            if drilled is not None:
                return drilled
        parse_output = {k: v for k, v in parse_output.items() if k not in _OBJECT_DROPS}
        slot = None
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME:
        extras = _dict(slot.get("extras"))
        if (dealer or not agent_filter) and extras.get("agent_options") and "sales_agent" not in _dict(slot.get("values")):
            # A contact the route refuses the agent dimension (linked to a customer between turns): no list is printed.
            return None, DEALER_REFUSAL
        args = _dict(extras.get("args"))
        held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
        held = _owed_held(extras, _dict(slot.get("values")), held)
        asked_field = next((f for f in SALES_RANKING_ASK.fields if f.name == slot.get("asking")), None)
        if asked_field is not None and asked_field.name == "basis":
            # The basis (or kind) question: the parser's pick of an offered option, else its own `basis` reading when it is
            # one of the options the question offers; anything else is no basis (never "invoiced" for a kind question).
            offered = {v for v, _l in (_basis_offered(extras) if extras.get("kind_ask") else BASIS_OPTIONS)}
            if extras.get("kind_ask"):
                offered |= set(NAMED_KINDS)  # named, never offered (owner 29 Oct)
            picked = rf.picked_option(slot, _dict(parse_output.get("required_ask_answer")))
            said = picked.value if picked.status == "ok" else next(
                (v for v in (parse_output.get("basis"), parse_output.get("sales_basis")) if v in offered), None
            )
            parse_output = {**parse_output, "basis": said if said in offered else None}
        elif extras.get("kind_ask") and parse_output.get("basis") not in OUTSTANDING_KINDS:
            parse_output = {**parse_output, "basis": None}
        if asked_field is not None and asked_field.name != "basis" and rf.is_parser_only(asked_field, extras):
            # The word question and the sales agent pick: the parser's declared pick only, never the reply's text.
            answer = _dict(parse_output.get("required_ask_answer"))
            if asked_field.name == "kind":
                # What else the reply says edits the held ask (`kind_edits`); the held values are recomputed from it.
                slot, line = kind_edits(db, parse_output, slot, dealer=dealer, companies=companies)
                if slot is None:
                    return None, line
                extras = _dict(slot.get("extras"))
                args = _dict(extras.get("args"))
                held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
                held = _owed_held(extras, _dict(slot.get("values")), held)
            return rf.collect(
                db, SALES_RANKING_ASK, slot=slot, reply=rf.picked_option(slot, answer),
                cancel=answer.get("mode") == "cancel", given=held,
            ), None
        filled = _reply_fills(parse_output, _dict(slot.get("values")), held)
        if filled:
            # A partial answer is not a miss: what it settled is kept, and only what is
            # still open is asked again (in one reply), or the ask runs.
            values = {
                **_dict(slot.get("values")),
                **{name: {"value": got.value, "label": got.label} for name, got in filled.items()},
            }
            return rf.collect(db, SALES_RANKING_ASK, slot={**slot, "values": values}, given=held), None
        swapped = _swap_axis(parse_output, extras)
        if swapped is not None:
            # R5 a3 (live turn c404da24): a refine naming another axis and filling no owed field is the
            # axis changing, not the answer: it replaces the slot's group_by, every filter stays, and
            # the fields still owed are asked again in one question (no "I don't know ... as a number").
            if dealer and _dealer_outside(parse_output, swapped["args"].get("group_by")):
                return None, DEALER_REFUSAL
            args = swapped["args"]
            held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
            held = _owed_held(extras, _dict(slot.get("values")), held)
            if args.get("group_by") != _dict(extras.get("args")).get("group_by") and _dict(extras.get("args")).get("group_by") in (None, *TREND_AXES):
                # What a total or a month trend settled on its own (no count, both measures) is not
                # what the new axis owes: the new axis's rules (`held`) decide, typed values stay.
                slot = {**slot, "values": _settled_by_its_axis(_dict(slot.get("values")), _dict(extras.get("args")).get("group_by"))}
            slot, args = _reply_wins(parse_output, slot, args)
            held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
            held = _owed_held(extras, _dict(slot.get("values")), held)
            extras = {**extras, "args": args}
        if parse_output.get("compare_to") in COMPARE_TO:
            # REPORT-SMART-L S4-1: a reply that sets the comparison and fills no owed field adds the
            # comparison to the held args and asks the owed fields again: no miss, no basis word.
            held_args = {**args, "compare_to": parse_output["compare_to"]}
            if held_args.get("group_by") == "month":
                return rf.Outcome(reply=COMPARE_BY_MONTH_LINE, slot=None), None  # a month breakdown is not compared
            return rf.collect(db, SALES_RANKING_ASK, slot=slot, given=held, extras={"args": held_args}), None
        if swapped is not None:
            if args.get("compare_to") and args.get("group_by") == "month":
                return rf.Outcome(reply=COMPARE_BY_MONTH_LINE, slot=None), None
            return rf.collect(db, SALES_RANKING_ASK, slot=slot, given=held, extras={"args": args}), None
        if int(slot.get("misses") or 0) < 1 and _echoes_axis(parse_output, extras):
            # R5 (live, flash-lite a342e9f0): the open ask's own axis said again fills nothing and is no
            # number: the owed fields are asked again with no miss line; it still counts as one miss, so a
            # second echo gives up as today (default top 10).
            slot, args = _reply_wins(parse_output, slot, args)
            held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
            held = _owed_held(extras, _dict(slot.get("values")), held)
            again = rf.collect(db, SALES_RANKING_ASK, slot=slot, given=held, extras={"args": args})
            if again.slot:
                again.slot["misses"] = 1
            return again, None
        reply_dates = {"start": parse_output.get("date_filter_start"), "end": parse_output.get("date_filter_end")}
        reply: Any = jsc.js_string(parse_output.get("required_ask_reply") or "")
        if asked_field is not None and (asked_field.name == "basis" or rf.is_parser_only(asked_field, extras)):
            # An option-bearing question never reads the reply's text (`_from_pick` would take a typed digit or label).
            said = basis_from(parse_output)
            # (An unread reply keeps its typed words only so a give-up can echo them; they are never interpreted.)
            reply = rf.Resolved("ok", value=said, label=said) if said else rf.Resolved("unknown", label=str(reply))
        outcome = rf.collect(
            db,
            SALES_RANKING_ASK,
            slot=slot,
            reply=reply,
            cancel=_dict(parse_output.get("required_ask_answer")).get("mode") == "cancel",  # the parser's declared cancel
            given=held,
            extras={
                "reply_dates": reply_dates,
                "reply_top_n": parse_output.get("top_n"),
                "reply_metric": metric_from(parse_output),
                "reply_basis": basis_from(parse_output),
            },
        )
        if slot.get("asking") == "top_n" and outcome.slot is None and not outcome.done and not outcome.cancelled:
            # The helper gave up on the count (a second miss): run the default top 10 and say
            # so (crew ruling). The period field keeps the helper's own give-up.
            # It goes on through the collector with the count settled, so every later field still owed (the agent pick,
            # the word question) is asked; the note rides the extras to the result.
            values = {**outcome.values, "top_n": {"value": DEFAULT_TOP_N, "label": str(DEFAULT_TOP_N)}}
            return rf.collect(
                db, SALES_RANKING_ASK, slot={**slot, "values": values, "misses": 0}, given=held,
                extras={"note": DEFAULT_TOP_N_NOTE},
            ), None
        return outcome, None

    frame = parse_output.get("sales_ranking_frame")
    frame = frame if isinstance(frame, dict) else {}
    drill = parse_output.get("ranking_drill")
    raw_group = jsc.js_string(parse_output.get("group_by") or "").strip().lower()
    # A refine never changes the axis: a verdict naming another axis than the held ranking's
    # is not one, whatever its `ranking_refine` says (crew live pass, 8 Oct 2026).
    if parse_output.get("bare_top_selling") is True and frame and _dict(frame.get("shown")) and not frame.get("stale"):
        # REPORT-SMART-L R2: a top_selling-labelled follow-up naming no axis and no grain refines the ranking
        # on screen (whatever its axis), keeping the rest, exactly as a `ranking_refine` does.
        parse_output = {**parse_output, "group_by": None, "ranking_refine": True}
        raw_group = ""
    if raw_group == "channel" and parse_output.get("sales_channel") in ("dealer", "project") and frame and not frame.get("stale"):
        # REPORT-CHANNEL-FILTER (owner ruling 24 Oct ~19:50, PLAN-report-channel-filter-1024.md): a channel axis
        # within one named channel is one row by construction, so "<channel> sales only" over a held ranking or total
        # is that channel's FILTER on it, never a new axis across all: a refine, which applies `sales_channel` (`_refine`).
        parse_output = {**parse_output, "group_by": None, "ranking_refine": True}
        raw_group = ""
    new_axis = bool(frame) and bool(raw_group) and GROUP_BY.get(raw_group, raw_group) != frame.get("group_by")
    if not new_axis and restates_the_ask(parse_output):
        # The same axis typed again is a new ask (a new frame): read whole, nothing held.
        parse_output = {**parse_output, "ranking_refine": False}
    if parse_output.get("ranking_refine") is True and frame and not new_axis:
        return _refine(db, parse_output, frame, entities, dealer=dealer, companies=companies)
    if drill == "scoped":
        # Owner ruling B (23 Oct): only the parser's `scoped` narrows to the rows on screen. A new axis
        # read as global, unsure or not at all runs across all (below), and the header says so.
        drilled = _drill(db, parse_output, frame, entities, reading=drill, dealer=dealer, companies=companies)
        if drilled is not None:
            return drilled
    held_period: rf.Resolved | None = None
    held_product: dict[str, Any] = {}
    held_channel: str | None = None
    held_filters: dict[str, Any] = {}
    holding = False
    # Owner ruling B + S6b (23 Oct): a new axis that runs across all, right after a ranking, keeps what is
    # on screen and widens only the ranked side: the same hold a refine naming another axis uses.
    across_all = new_axis and drill != "scoped" and bool(_dict(frame.get("shown"))) and not frame.get("stale")
    source: dict[str, Any] = {}
    keep_product = False
    total_frame = bool(frame) and not frame.get("group_by")
    if new_axis and (parse_output.get("ranking_refine") is True or across_all):
        if total_frame and _new_subject(parse_output):
            source = {}  # the parser's own `new_subject` over a held TOTAL is a fresh ask: nothing carries
        else:
            # A total has no rows to rank across, so the product it was for stays on a product axis too.
            source, keep_product = frame, total_frame
    elif _dict(parse_output.get(HELD_KEY)):
        # R8: the engine stamped what the held sales report total, a ranking held for a customer, or the open ask this
        # replaced showed (`with_held`): the same hold, one more source. A total has no rows to rank across, so
        # the product it was for stays on a product axis too (crew target: its variants ranked).
        source, keep_product = _dict(parse_output.get(HELD_KEY)), True
    if source:
        # Not a refine (it names another axis): the fresh ask reads it whole, its dates included.
        # Chat fix PR-B S4 (AC-B6): the new axis is still asked (8 Oct rule), but the held period,
        # product and channel stay, never asked again; the message's own period, product or channel wins.
        axis = GROUP_BY.get(raw_group, raw_group)
        held_period = period_from(source.get("date_from"), source.get("date_to"))
        widened = _widened(parse_output)
        held_product = {
            k: source[k] for k in ("product_code", "product_ids")
            if source.get(k) and (keep_product or k not in _AXIS_FILTERS.get(axis, ())) and widened != "product"
        }
        if axis != "channel" and widened != "channel" and source.get("channel") in ("dealer", "project"):
            held_channel = source["channel"]
        # A brand, category or sales agent filter on screen is held too (the new axis's own filter is not): owner ruling
        # B / S6b on a turn whose report_ask is null. An object turn never reaches here (`_OBJECT_DROPS` empties `source`).
        # TODO(REPORT-FILTER-ALL): delete with the rest of the old hold path in PR B (crew Q3, 5 Nov).
        held_filters = {
            k: source[k] for k in ("brand_ids", "category_ids", "sales_agent_ids", "account_types")
            if source.get(k) and k not in _AXIS_FILTERS.get(axis, ())
        }
        held_customer = _dict(parse_output.get(HELD_KEY)).get("customer_ids")
        if held_customer and _customer_stays(parse_output, axis):
            # Only off the stamp, never the frame: an open ask the message replaced is newer than a ranking still on screen.
            # The ids the report ran on, so a pick's ledgers stay exactly the pick's: never re-read from a code or a name.
            held_filters["customer_ids"] = held_customer
        holding = True
        parse_output = {**parse_output, "ranking_refine": False}

    args, line = _fresh_args(
        db, parse_output, entities, dealer=dealer, agent_filter=agent_filter, companies=companies, ask_kind=True
    )
    if args is None:
        return None, line
    not_applied = args.pop("_unbound", [])
    agent_words = args.pop("_agent_words", None)
    kind_ask = args.pop("_kind_ask", None)
    from app.services.reports.ask_params import _asked_number

    own_book = {"channel"}
    if args.get("account_types") and all(_asked_number(str(v).strip().upper()) is not None for v in args["account_types"]):
        own_book.add("account_types")  # an account number names no company; a type word may be in the other one
    if (
        holding and source.get("company") and _widened(parse_output) != "company"
        and not set(args) - _NON_FILTER_ARGS - own_book
    ):
        # The company it ran in stays, unless this message has a subject of its own (that may be in the other company)
        # or widens to every company.
        args["company"] = source["company"]
    named = {
        jsc.js_string(e.get("hint") or "").strip().lower()
        for e in jsc.array(parse_output.get("entities"))
        if isinstance(e, dict) and e.get("current_message") is not False
    } & _FILTER_HINTS
    if parse_output.get("capability_from") == "outstanding":
        named -= {"warehouse"}  # item 9: an outstanding ask's unknown location narrows nothing, as before #1922
    if named and parse_output.get("capability_from") and not set(args) - _NON_FILTER_ARGS and not held_product and not kind_ask:
        # A sales total or outstanding ask that NAMED a subject which resolved to no filter would run over everything.
        return None, CATALOGUE_LINE
    if held_product and not (args.get("product_code") or args.get("product_ids")):
        args.update(held_product)
    if held_channel and not args.get("channel"):
        args["channel"] = held_channel
    for key, value in held_filters.items():
        args.setdefault(key, value)  # the message's own values win
    if holding:
        # S6c: the measure and the basis on screen stay too (the message's own win).
        # An outstanding ask the parser named no kind for never inherits a SALES basis (the kind is asked, as `_refine` does).
        asks_kind = parse_output.get("capability_from") == "outstanding" and parse_output.get("basis") not in OUTSTANDING_KINDS
        for key in ("measure", "basis"):
            if key == "basis" and asks_kind and source.get("basis") not in OUTSTANDING_KINDS:
                continue
            if not args.get(key) and source.get(key):
                args[key] = source[key]
    if (
        parse_output.get("ranking_refine") is not True
        and not dealer  # the route forces a dealer's links, so a plain total can never widen
        and not args.get("group_by")
        and not set(args) - _NON_FILTER_ARGS
        and not kind_ask
        and not parse_output.get("capability_from")  # a sales / outstanding total with no filter is the company's own
    ):
        # Not a valid ask: no axis and nothing to total. Say what can be ranked and open nothing.
        return None, CATALOGUE_LINE
    top_n = parse_output.get("top_n")
    if top_n is None and holding and source.get("top_n"):
        top_n = source["top_n"]  # S6c: the count on screen stays
    if top_n is None and parse_output.get("report_breakdown") is True and args.get("group_by"):
        top_n = BREAKDOWN_TOP_N  # a breakdown lists every row (`by_capability`)
    # An ask routed from an outstanding status (`as_outstanding`), not a sales ranking that merely names that basis.
    outstanding_ask = parse_output.get("capability_from") == "outstanding"
    if outstanding_ask and args.get("group_by"):
        # REPORT-OUTSTANDING-SUMMARY item 4 (owner 29 Oct, as before #1922): an outstanding breakdown asks neither "How
        # many?" nor the measure. Every row, ranked by quantity as the old report ranked its groups (R10), unless the
        # user named a count or a measure.
        if top_n is None:
            top_n = BREAKDOWN_TOP_N
        args.setdefault("measure", "qty")
    if args.get("compare_to") and args.get("group_by") == "month":
        return None, COMPARE_BY_MONTH_LINE
    given = {**_given_choices(args), **_given_top_n(args, top_n)}
    breakdown = (
        parse_output.get("report_breakdown") is True and bool(args.get("group_by"))
        and not any(parse_output.get(k) not in (None, "") for k in ("rank_direction", "top_n", "rank_by"))  # a ranking mark
    )
    if breakdown and "metric" not in given:
        # A breakdown (no ranking marker from the parser) shows both qty and RM, sorted by amount: no measure question.
        given["metric"] = rf.Resolved("ok", value=None, label="")
    agent_pick = args.pop("sales_agent_pick", None)
    if agent_pick:
        given["sales_agent"] = rf.Resolved("ambiguous", options=tuple((i, str(n)) for i, n in agent_pick))
    own = _own_companies(companies)
    if own and not dealer and parse_output.get("ranking_refine") is not True:
        # R1: the company the message (the parser's `sales_company`) names, among the contact's own, narrows the ask, a
        # sales and an outstanding one alike. Owner O-R2 (3 Nov): none named is never asked; the route runs over every
        # company the contact holds and the reply shows each one's total.
        named, foreign = _company_said(parse_output, own)
        if foreign:
            return None, COMPANY_FORBIDDEN_LINE  # the message named a company the contact does not hold
        if named is not None:
            args["company"] = str(named[0])
    if (
        parse_output.get("capability_from") == "outstanding"
        and args.get("basis") in OUTSTANDING_KINDS
        and not args.get("group_by")
    ):
        # An outstanding TOTAL that named its kind shows both measures (no "by quantity or by amount?"); a ranking by an
        # axis still asks what it ranks by (phase 3, S5).
        given["metric"] = rf.Resolved("ok", value=args.get("measure"), label=args.get("measure") or "")
    # REPORT-OUTSTANDING-SUMMARY item 9 (owner 29 Oct, as before #1922): an ask with no period of its own takes the
    # period on screen, a switch from a sales answer to an outstanding kind and a fresh outstanding ask included; the
    # header shows it.
    on_screen = None
    if (parse_output.get("capability_from") == "outstanding" or args.get("basis") in OUTSTANDING_KINDS) and not frame.get("stale"):
        on_screen = period_from(frame.get("date_from"), frame.get("date_to"))
    period = period_from(parse_output.get("date_filter_start"), parse_output.get("date_filter_end")) or held_period or on_screen
    if period is not None and (parse_output.get("ranking_refine") is not True or args.get("group_by")):
        # A refine with no ranking held has nothing to refine: it is a fresh ask, and a
        # period alone never runs a total (it asks). One that names its own axis (R5 row 7) keeps its period.
        given["period"] = period
    extras: dict[str, Any] = {"args": args, "top_n": top_n}
    if agent_words:
        extras["agent_words"] = agent_words  # semantic carry: the words the agents were typed as (`arg_names`)
    if breakdown:
        extras["breakdown"] = True
    if not_applied:
        extras["not_applied"] = not_applied
    if parse_output.get("capability_from") == "outstanding":
        extras["kind_ask"] = True  # the basis question is the three kinds (Q2)
    if period is None and (args.get("basis") in OUTSTANDING_KINDS or extras.get("kind_ask")):
        # An outstanding kind takes no period: none named means every date (the route's own reading).
        given["period"] = rf.Resolved("ok", value={"from": None, "to": None}, label="all dates")
    if across_all and frame.get("group_by") in AXIS_NOUNS and _drill_source(frame):
        # Owner ruling B: after a ranking, a new axis runs across all, and the header line says so.
        extras["note"] = f"Across all {AXIS_NOUNS[frame['group_by']][1]}"
    if kind_ask:
        _ask_kind(given, extras, kind_ask)
    if agent_pick:
        extras["agent_options"] = [[str(i), str(n)] for i, n in agent_pick]
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras=extras), None


def _ask_kind(given: dict[str, Any], extras: dict[str, Any], kind_ask: dict[str, Any]) -> None:
    """Owe the word question (the last field). The words ride the extras to the answer."""
    extras["kind_words"] = kind_ask["words"]
    extras["kind_match"] = kind_ask["match"]
    extras["kind_held"] = kind_ask["held"]
    extras["kind_choices"] = kind_ask["choices"]
    if kind_ask.get("company"):
        extras["kind_company"] = kind_ask["company"]  # C6-1: `[id, name]` of the company the word also is
    if kind_ask.get("both"):
        extras["kind_both"] = True  # M2: company, brand or both (`_kind_options`)
    given["kind"] = rf.Resolved("ambiguous", options=_kind_options(extras))


def _own_companies(companies: Any) -> list[Any]:
    return [c for c in jsc.array(companies) if isinstance(c, (list, tuple)) and len(c) == 3]


def _company_said(parse_output: dict[str, Any], own: list[Any]) -> tuple[Any, bool]:
    """The contact's own company the message names (the parser's `sales_company`, by name or code), and whether it named one
    the contact does not hold."""
    said = " ".join(jsc.js_string(parse_output.get("sales_company") or "").split()).casefold()
    named = next((c for c in own if said and said in (str(c[1]).casefold(), str(c[2]).casefold())), None)
    return named, bool(said) and named is None


def _customer_stays(parse_output: dict[str, Any], axis: str | None) -> bool:
    """Owner ruling, 1 Nov 2026 (CHATBOT-FOLLOWUP-CARRY): the held customer stays on a follow-up unless this message replaces
    it: a customer of its own (named, or the one a pick just answered), "my ...", the parser's widening to all customers
    (`broaden_axis`, or `ranking_drill` global: "global when it says so"), or customers as the axis now ranked. Parser fields
    and engine keys only."""
    return (
        axis != "customer"
        and _widened(parse_output) != "customer"
        and parse_output.get("ranking_drill") != "global"
        and "customer" not in _current_kinds(parse_output)
        and parse_output.get("ranking_pick") is not True
        and parse_output.get("self_reference") is not True
    )


def _widened(parse_output: dict[str, Any]) -> str | None:
    """The one held axis the parser widened to "all" this turn (`broaden_axis` with `broaden_to`
    "all", template R-P3-09): the old hold path drops it and keeps the rest (the company: every company). The object
    path does not read it (REPORT-FILTER-ALL: the object's ALL, `_read_all`). Parser fields only."""
    if parse_output.get("broaden_to") != "all":
        return None
    axis = jsc.js_string(parse_output.get("broaden_axis") or "").strip().lower()
    return axis if axis in ("channel", "product", "customer", "company") else None


def _refine(
    db: Any, parse_output: dict[str, Any], frame: dict[str, Any], entities: Any = (), *, dealer: bool = False, companies: Any = ()
) -> tuple[rf.Outcome | None, str | None]:
    """The parser said this message only refines the sales ranking that ran (`ranking_refine`):
    the held route args re-run with ONLY the keys the verdict changed (count, period, basis,
    measure; a product named on it replaces the held one). A dealer's refine passes the same
    check a fresh ask does, over the HELD args."""
    if dealer:
        from app.services.reports.ask import DEALER_KEYS

        if (
            frame.get("group_by") not in (None, *DEALER_KEYS)
            or frame.get("sales_agent_ids")
            or frame.get("customer_agent_ids")
            or frame.get("warehouse_codes")
            or frame.get("channel")
            or frame.get("account_types")
        ):
            return None, DEALER_REFUSAL
        if any(" ".join(jsc.js_string(w).split()) for w in jsc.array(_dict(parse_output.get("report_ask_words")).get("account_type"))):
            return None, DEALER_REFUSAL  # the route refuses the account filter to a customer-scoped contact
    args = {k: v for k, v in frame.items() if k not in _FRAME_ONLY}
    widened = _widened(parse_output)
    for key in _AXIS_FILTERS.get(widened or "", ()):
        args.pop(key, None)  # REPORT-SMART-L R0: the widened axis is dropped, the rest held
    channel = parse_output.get("sales_channel")
    if channel in ("dealer", "project"):
        if dealer:
            return None, DEALER_REFUSAL
        args["channel"] = channel
    # A brand or category word the refine names replaces that dimension; the rest stays held.
    plan = (
        _account_plan(db, parse_output, companies, ask=True, held_company=frame.get("company"))
        if not dealer else _account_plan(None, {})
    )
    words = _dict(parse_output.get("report_ask_words"))
    read = {**parse_output, "report_ask_words": {**words, "brand": _brand_words(words, plan)}}
    filters, line = _word_filters(db, read, (("brand", "brand_ids"), ("category", "category_ids")))
    if filters is None:
        return None, line
    args.update(filters)
    if plan["account_types"]:
        args["account_types"] = plan["account_types"]  # an account word replaces the held account filter
    kind_ask = None
    if plan["ask"]:
        # What the question adds replaces that dimension on the held ask, as a plain brand or account word does.
        kind_ask, line = _kind_ask(db, parse_output, plan, {"account_types": plan["account_types"]})
        if kind_ask is None:
            return None, line
    # A customer of its own (named, or the one a pick just answered) replaces the held one, and may be in the other company.
    own_customer = _gate_ids(entities, "customer") if (
        "customer" in _current_kinds(parse_output) or parse_output.get("ranking_pick") is True
    ) else []
    if own_customer:
        args["customer_ids"] = own_customer
        args.pop("company", None)
    elif parse_output.get("ranking_pick") is True:
        args.pop("customer_ids", None)  # a pick that lost its row is never the held customer
    if "product" in _current_kinds(parse_output):
        product_args, line = _product_args(entities)
        if product_args is None:
            return None, line
        if product_args:
            for key in ("product_code", "product_ids"):
                args.pop(key, None)
            args.update(product_args)
    if parse_output.get("basis") in BASES:
        args["basis"] = parse_output["basis"]
    if metric_from(parse_output):
        args["measure"] = metric_from(parse_output)  # `measure`, else the top selling key `rank_by`
    # An outstanding refine never infers its kind: unless the parser picked or declared one, the held sales basis is not
    # carried and the kind is asked (the held period stays: a "by X" follow-up keeps what is on screen, AC-RU-16).
    # A frame already on an outstanding kind keeps it: the user chose it (Q12).
    asks_kind = (
        parse_output.get("capability_from") == "outstanding"
        and parse_output.get("basis") not in OUTSTANDING_KINDS
        and args.get("basis") not in OUTSTANDING_KINDS
    )
    if asks_kind:
        args.pop("basis", None)
    if parse_output.get("compare_to") in COMPARE_TO:
        args["compare_to"] = parse_output["compare_to"]
    if parse_output.get("self_reference") is True:
        args["mine"] = True
        if not own_customer:
            # "my ...": the contact's own accounts, as a fresh ask reads them, never the customer held.
            args.pop("customer_ids", None)
            scope = _gate_ids([e for e in jsc.array(entities) if isinstance(e, dict) and e.get("scope")], "customer")
            if scope:
                args["customer_ids"] = scope
    if args.get("compare_to") and args.get("group_by") == "month":
        return None, COMPARE_BY_MONTH_LINE
    top_n = parse_output.get("top_n")
    if top_n is None:
        top_n = frame.get("top_n")
    period = period_from(parse_output.get("date_filter_start"), parse_output.get("date_filter_end")) or period_from(
        frame.get("date_from"), frame.get("date_to")
    )
    # A held ranking has both choices (its args ran): a refine never asks.
    given = {**_given_choices(args), **_given_top_n(args, top_n)}
    for name, key in (("metric", "measure"), ("basis", "basis")):
        if name not in given and not (asks_kind and name == "basis"):
            given[name] = rf.Resolved("ok", value=args.get(key), label=args.get(key) or "")
    if asks_kind:
        given.pop("basis", None)
    if period is not None:
        given["period"] = period
    extras = {"args": args, "top_n": top_n, **({"kind_ask": True} if asks_kind else {})}
    own = _own_companies(companies)
    if own and not dealer:
        # A company the refine names narrows it, as on a fresh ask (sales and outstanding alike); one the contact does
        # not hold is said. None named keeps the held one, or every company (owner O-R2: never asked).
        named, foreign = _company_said(parse_output, own)
        if foreign:
            return None, COMPANY_FORBIDDEN_LINE
        if named is not None:
            args["company"] = str(named[0])
    if kind_ask:
        _ask_kind(given, extras, kind_ask)
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras=extras), None


def _named_words(parse_output: dict[str, Any], axis: str) -> list[str]:
    """The words this message named on `axis` (as the parser gave them), for a line."""
    hint = "sales_agent" if axis == "sales_agent" else axis
    words = [" ".join(jsc.js_string(w).split()) for w in jsc.array(_dict(parse_output.get("report_ask_words")).get(hint))]
    words += [
        " ".join(jsc.js_string(e.get("raw") or "").split())
        for e in _current_entities(parse_output, "warehouse" if axis == "location" else hint)
    ]
    return [w for w in words if w]


def _drill_source(frame: dict[str, Any]) -> bool:
    """Is the ranking on screen a population a drill can narrow (agents, customers, ...), not a month
    or channel list? One test with the scoped drill."""
    from app.services.reports.ask import drill_param

    source = jsc.js_string(frame.get("group_by") or "")
    return source in AXIS_NOUNS and drill_param(source, source) is not None


def _unsure_line(group_by: str, top_n: Any, source: str, count: int) -> str:
    """"Top 10 customers of the 3 sales agents above, or across all customers?" (card rule 1)."""
    one, many = AXIS_NOUNS[group_by]
    src_one, src_many = AXIS_NOUNS[source]
    got = top_n_from(top_n)
    head = f"Top {got.value} {many if got.value != 1 else one}" if got.status == "ok" else many.capitalize()
    rows = f"the {count} {src_many}" if count != 1 else f"the {src_one}"
    return f"{head} of {rows} above, or across all {many}?"


def _drill(
    db: Any, parse_output: dict[str, Any], frame: dict[str, Any], entities: Any, *, reading: str,
    dealer: bool = False, companies: Any = (),
) -> tuple[rf.Outcome | None, str | None] | None:
    """The parser read this ranking as about the rows the last ranking printed
    (`ranking_drill` scoped), or maybe so (unsure, asked; nothing runs). Scoped keeps every
    held filter, the period, the basis and the measure; the message's own filters, basis,
    measure, period and direction replace held ones (card rule 2); the declared link
    (`reports.ask.drill_param`) narrows to exactly the rows printed, the same axis included
    ("bottom 2 of these agents"). A scoped drill with nothing held is said, never guessed;
    None means an unsure one with nothing above to narrow by, which is the fresh ask."""
    from app.services.reports.ask import drill_param

    shown = _dict(frame.get("shown"))
    rows = [r for r in jsc.array(shown.get("rows")) if isinstance(r, dict)]
    source = jsc.js_string(shown.get("group_by") or "")
    unsure = reading == "unsure"
    drillable = bool(rows) and _drill_source(frame)
    if unsure and not drillable:
        return None
    if not rows or source not in AXIS_NOUNS:
        return None, NO_RANKING_LINE

    # The message's own reading, exactly as a fresh ask reads it (axis, filters, choices).
    own, line = _fresh_args(
        db, parse_output, entities, dealer=dealer, companies=companies, ask_kind=True, held_company=frame.get("company")
    )
    if own is None:
        return None, line
    kind_ask = own.pop("_kind_ask", None)
    own.pop("_agent_words", None)
    group_by = own.get("group_by")
    if group_by is None:
        return None, CATALOGUE_LINE
    param = drill_param(source, group_by)
    if param is None:
        return None, NOT_A_SOURCE_LINES.get(source, CATALOGUE_LINE)
    keys: list[str] = []
    for row in rows:
        row_keys = [k for k in (jsc.js_string(v) for v in jsc.array(row.get("keys"))) if k]
        if not row_keys:
            # A printed row naming nothing to narrow by ("(blank)"): said, never dropped.
            if unsure:
                return None  # nothing to scope to: the global reading is the only one left
            return None, NO_KEYS_LINE.format(name=jsc.js_string(row.get("name")), plural=AXIS_NOUNS[source][1])
        keys.extend(k for k in row_keys if k not in keys)
    if len(keys) > DRILL_MAX_KEYS:
        if unsure:
            return None
        return None, TOO_MANY_LINE.format(max=DRILL_MAX_KEYS, plural=AXIS_NOUNS[source][1])

    held = {k: v for k, v in frame.items() if k not in _FRAME_ONLY and k not in _AXIS_FILTERS.get(group_by, ())}
    if dealer and any(held.get(k) for k in ("sales_agent_ids", "customer_agent_ids", "warehouse_codes", "channel")):
        return None, DEALER_REFUSAL
    message_filters = {k: v for k, v in own.items() if k not in _NON_FILTER_ARGS}
    named = message_filters.get(param)
    if isinstance(named, list):
        # The message names its own value on the link's param ("these agents, ALICE only"):
        # it narrows within the rows printed; one that is not among them is said, never dropped.
        inside = [k for k in named if k in keys]
        if not inside:
            names = ", ".join(_named_words(parse_output, source)) or "That"
            return None, NOT_IN_ROWS_LINE.format(name=names, plural=AXIS_NOUNS[source][1])
        keys = inside
    same_axis = group_by == source
    sort = own["sort"]
    if same_axis and parse_output.get("rank_direction") not in ("top", "bottom"):
        sort = frame.get("sort") or sort  # "these agents by quantity" keeps the held direction
    args = {**held, **message_filters, "group_by": group_by, "sort": sort, param: keys}
    for key in ("basis", "measure"):
        if own.get(key):
            args[key] = own[key]
    own_period = period_from(parse_output.get("date_filter_start"), parse_output.get("date_filter_end"))
    period = own_period or period_from(frame.get("date_from"), frame.get("date_to"))
    top_n = parse_output.get("top_n")
    if top_n is None and same_axis:
        top_n = frame.get("top_n")
    scoped = _branch(args, top_n, period, held=True, kind_ask=kind_ask)
    if unsure:
        # One question, nothing runs. The slot holds BOTH readings, so the reply only has to
        # say which ("the agents above" / "all"); its axis, count and period are the slot's.
        question = _unsure_line(group_by, parse_output.get("top_n"), source, len(rows))
        scope = {
            "question": question,
            "source": source,
            "scoped": scoped,
            "global": _branch(own, parse_output.get("top_n"), own_period, held=False, kind_ask=kind_ask),
        }
        slot = {"ask": ASK_NAME, "values": {}, "asking": "scope", "options": [], "misses": 0,
                "extras": {"scope": scope}}
        return rf.Outcome(values={}, reply=question, slot=slot), None
    return _collect_branch(db, scoped), None


def _branch(
    args: dict[str, Any], top_n: Any, period: rf.Resolved | None, *, held: bool, kind_ask: Any = None
) -> dict[str, Any]:
    """One reading of a ranking, kept as plain data (it may wait in a slot): its args, count,
    period, and whether its metric and basis are the held ranking's (never asked again)."""
    return {
        "args": args,
        "top_n": top_n,
        "period": {"value": period.value, "label": period.label} if period is not None else None,
        "held": held,
        "kind_ask": kind_ask,
    }


def _collect_branch(db: Any, branch: dict[str, Any]) -> rf.Outcome:
    args, top_n = _dict(branch.get("args")), branch.get("top_n")
    if args.get("compare_to") and args.get("group_by") == "month":
        # A drill keeps the held comparison; a month breakdown of it is said (review nit 2).
        return rf.Outcome(reply=COMPARE_BY_MONTH_LINE, slot=None)
    given = {**_given_choices(args), **_given_top_n(args, top_n)}
    if branch.get("held"):
        # A drill has both choices (the held args ran); only the count is asked when not named.
        for name, key in (("metric", "measure"), ("basis", "basis")):
            if name not in given:
                given[name] = rf.Resolved("ok", value=args.get(key), label=args.get(key) or "")
    period = _dict(branch.get("period"))
    if period:
        given["period"] = rf.Resolved("ok", value=period.get("value"), label=period.get("label") or "")
    extras: dict[str, Any] = {"args": args, "top_n": top_n}
    if branch.get("kind_ask"):
        _ask_kind(given, extras, branch["kind_ask"])  # a word that is both asks once, after the other owed fields
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras=extras)


def _scope_answer(db: Any, parse_output: dict[str, Any], slot: dict[str, Any]) -> rf.Outcome:
    """The reply to the scope question: the PARSER's reading of it (`ranking_drill` scoped or
    global) picks the reading the slot holds. Anything else asks once more, then gives up."""
    scope = _dict(_dict(slot.get("extras")).get("scope"))
    reading = parse_output.get("ranking_drill")
    if reading in ("scoped", "global") and isinstance(scope.get(reading), dict):
        return _collect_branch(db, scope[reading])
    if int(slot.get("misses") or 0) >= 1:
        return rf.Outcome(reply=SCOPE_GIVE_UP, slot=None)
    return rf.Outcome(reply=jsc.js_string(scope.get("question") or ""), slot={**slot, "misses": 1})


def route_args(outcome: rf.Outcome) -> dict[str, Any]:
    """The settled ask as `crm_report_ask`'s params (the route's names)."""
    args = dict(_dict(outcome.extras.get("args")))
    for name, key in (("metric", "measure"), ("basis", "basis")):
        settled = _dict(outcome.values.get(name)).get("value")
        if settled:
            args[key] = settled
    period = _dict(_dict(outcome.values.get("period")).get("value"))
    if period.get("from") and period.get("to"):  # an outstanding kind with no period sends none (every date)
        args["date_from"] = period["from"]
        args["date_to"] = period["to"]
    top_n = (outcome.values.get("top_n") or {}).get("value")
    if args.get("group_by") and isinstance(top_n, int):
        args["top_n"] = top_n
    agent = _dict(outcome.values.get("sales_agent")).get("value")
    if agent:
        args["sales_agent_ids"] = [str(agent)]  # the agent the person picked
    kind = _dict(outcome.values.get("kind")).get("value")
    for key, values in _dict(_dict(outcome.extras.get("kind_choices")).get(kind)).items():
        args[key] = list(values)  # brand or account type: the answer to the question
    return args


#: REPORT-OUTSTANDING-SUMMARY item 3: the route params that make an outstanding ask about a subject (a product, a
#: customer or a brand, as the pre-#1922 report's subjects); without one the ask is the outstanding document list.
_SUBJECT_ARGS = ("product_code", "product_ids", "spec", "customer_ids", "brand_ids", "account_types")
#: Outstanding kind -> the grouping that lists its documents (`reports.ask.DOCUMENT_LISTS`).
LIST_GROUPS = {"outstanding": "sales_order", "pending_delivery": "delivery_order"}


def document_list_args(args: dict[str, Any], outcome: rf.Outcome) -> dict[str, Any] | None:
    """Item 3 (owner 29 Oct, as before #1922): an outstanding ask (the kind question's own, `kind_ask`) of undelivered
    orders or pending delivery that names no subject and no axis is the outstanding document LIST, not a company figure:
    the args grouped by its document. None for every other ask. The caller applies V1-DOC-SCOPE first."""
    if not outcome.extras.get("kind_ask") or args.get("group_by") or args.get("basis") not in LIST_GROUPS:
        return None
    if any(args.get(k) for k in _SUBJECT_ARGS):
        return None
    return {**args, "group_by": LIST_GROUPS[args["basis"]], "top_n": BREAKDOWN_TOP_N}


def with_customer_groups(db: Any, args: dict[str, Any], linked: Any = None) -> dict[str, Any]:
    """Owner R3 (round 7d): the ONE point the report ask's customer ids are final for the route (both paths pass it,
    after `route_args`). A customer the office grouped is one customer: each id widens to every ledger of its explicit
    `customer_group_id` in the same company (read from `customers` on the turn's company-scoped session, never a name
    rule). `linked` (a dealer's own customers): a widened ledger outside them is left out (the route's own cap stays
    behind it). Args without customer ids, or ids in no group, are returned as they are, less any id that is no UUID (no
    row: the route would refuse it, the query would raise)."""
    from app.services.chatbot.lanes.business.fetch import is_uuid

    given = [str(i) for i in jsc.array(args.get("customer_ids")) if i]
    ids = [i for i in given if is_uuid(i)]  # M5: a non-UUID is no row (no DataError, no route 400)
    if ids != given:
        args = {**{k: v for k, v in args.items() if k != "customer_ids"}, **({"customer_ids": ids} if ids else {})}
    if not ids or db is None:
        return args
    from sqlalchemy import and_, or_

    from app.models.order import Customer

    groups = {
        (str(g), str(c))
        for g, c in db.query(Customer.customer_group_id, Customer.company_id).filter(Customer.id.in_(ids)).all()
        if g
    }
    if not groups:
        return args
    rows = db.query(Customer.id).filter(
        or_(*[and_(Customer.customer_group_id == g, Customer.company_id == c) for g, c in sorted(groups)])
    ).all()
    own = None if linked is None else {str(i) for i in jsc.array(linked)}
    added = [str(r[0]) for r in rows if str(r[0]) not in ids and (own is None or str(r[0]) in own)]
    return {**args, "customer_ids": [*ids, *sorted(added)]} if added else args


#: SALES-UNIFIED (contract section 7): a billing line has no warehouse, so the route answers an
#: invoiced ask by location (axis or filter) with 422 `location_needs_order_basis`. Said here
#: before anything runs.
INVOICED_LOCATION_LINE = "Sales by location are for delivered or ordered sales only."


def invoiced_location_line(args: dict[str, Any]) -> str | None:
    """The line for settled route args the route would refuse as an invoiced ask by location;
    None for any other ask."""
    if args.get("basis") != "invoiced":
        return None
    if args.get("group_by") == "location" or args.get("warehouse_codes"):
        return INVOICED_LOCATION_LINE
    return None


#: The entity kinds a report ask turns into a route param (a customer, product, brand, category, sales agent,
#: location or spec). Any other kind the message named has no param.
_APPLIED_HINTS = frozenset(
    {"customer", "product", "brand", "category", "product_type", "sales_agent", "warehouse", "specification", "spec",
     "account_type"}
)


def unapplied_words(parse_output: dict[str, Any], args: dict[str, Any]) -> list[str]:
    """REPORT-UNIFY (plan 2.4, P11): the words of a parsed filter the route has no param for, each as the
    "Not applied" text (`a/c 3 (no account filter)`). An account number on a customer the ask did not
    narrow to, and any entity kind the report does not filter by."""
    out: list[str] = []
    for e in jsc.array(parse_output.get("entities")):
        if not isinstance(e, dict) or e.get("current_message") is False:
            continue
        hint = jsc.js_string(e.get("hint") or "").strip().lower()
        raw = " ".join(jsc.js_string(e.get("raw") or "").split())
        account = e.get("account")
        if isinstance(account, int) and not isinstance(account, bool) and account >= 1 and not args.get("customer_ids"):
            out.append(f"a/c {account} (no account filter)")
        elif hint and hint not in _APPLIED_HINTS and raw:
            out.append(f"{raw} (no {hint.replace('_', ' ')} filter)")
    return list(dict.fromkeys(out))


def sole_unapplied_question(words: list[str], args: dict[str, Any]) -> str | None:
    """REPORT-UNIFY (AC-RU-14, P11): every filter the message named has no route param and nothing is grouped, so
    the figure would not be what was asked: the words are said and the subject asked, never answered."""
    if not words or args.get("group_by") or set(args) - _NON_FILTER_ARGS - {"date_from", "date_to", "top_n"}:
        return None
    return f"{'; '.join(words)}. Which customer or sales agent do you want?"


def error_line(envelope: Any) -> str | None:
    """A route refusal said as its own message (403: `report_dimension_not_allowed`,
    `customer_not_permitted`, `sales_report_not_enabled`), a 404 as `I couldn't find that
    <thing>.`; None for any other error (the generic error path answers it)."""
    if not isinstance(envelope, dict):
        return None
    status = envelope.get("status_code")
    detail = _dict(envelope.get("detail"))
    message = jsc.js_string(detail.get("message") or "").strip()
    if status == 403 and message:
        return message
    if status == 404:
        thing = message.split(" not found", 1)[0].strip().lower() if " not found" in message else ""
        return f"I couldn't find that {thing}." if thing else "I couldn't find that."
    return None


# --------------------------------------------------------------------------- #
# SALES-ACCOUNT-TYPE semantic carry (PLAN-report-semantic-carry-2nov.md A2, A3): the parser's `report_ask` object
# --------------------------------------------------------------------------- #

#: The parser's whole report ask after the message (`parser.with_report_ask`). The engine keeps the key on a verdict only
#: for a prompt that carries the marker (`from_object`), so the key's presence is that prompt in use; a dict is the ask.
OBJECT_KEY = "report_ask"
#: The held names -> ids (the frame's and the open question's, `_held_names`), written by `from_object` alone, which drops
#: any value the parser put there: the lane maps a name carried back to the id it ran with by the company rule (SC-5).
HELD_IDS_KEY = "report_ask_ids"
#: The route's axis name the parser's `group_by` spells otherwise.
_PARSER_AXIS = {"location": "warehouse"}
#: The sales total's basis question (`sales_basis_ask.ASK_NAME`): its `carry` is a held ask too (`_held_object`).
SALES_BASIS_ASK = "sales_basis"
#: An open field of this ask -> the words the `Held report (open question: ...)` line names it with.
OPEN_QUESTION_WORDS = {
    "basis": "basis", "period": "period", "top_n": "count", "metric": "measure",
    "kind": "brand or account type", "sales_agent": "sales agent", "scope": "scope",
}
#: M2: the words the Held report line names the company-or-brand question with (`kind_both`); the brand or account type
#: question keeps its own.
COMPANY_OR_BRAND_WORDS = "company or brand"
#: REPORT-FILTER-ALL: the `report_ask` filter slots. Each takes the explicit ALL (`parser.REPORT_ALL`: company and channel
#: "ALL", a list ["ALL"]): every value, no filter. An empty one the parser left over a held value keeps it (`_keep_held`).
_FILTER_SLOTS = ("company", "channel", "sales_agents", "account_types", "brands", "categories", "customers", "products")
#: TODO(REPORT-FILTER-ALL): delete with `_legacy_all` once the owner publishes a prompt that writes ALL. The legacy widen
#: signal (`turn.decide.widened_kinds`, an entity hint) -> the slots it empties; brand and account type widen together.
_LEGACY_WIDEN_SLOTS = {
    "sales_agent": ("sales_agents",), "brand": ("brands", "account_types"), "account_type": ("brands", "account_types"),
    "category": ("categories",), "customer": ("customers",), "product": ("products",), "company": ("company",),
    "channel": ("channel",),
}
#: A breakdown axis -> the object slot that filters its own dimension (C6-2: an axis whose slot the ask filters to ONE
#: value is one row, not a breakdown).
_AXIS_SLOTS = {
    "sales_agent": "sales_agents", "brand": "brands", "account_type": "account_types", "category": "categories",
    "customer": "customers", "product": "products", "channel": "channel",
}
#: The id params the held report names, the object list each one is shown in, and the row column it is named by.
_NAMED_PARAMS = (
    ("sales_agent_ids", "sales_agents"), ("brand_ids", "brands"), ("category_ids", "categories"),
    ("customer_ids", "customers"), ("product_ids", "products"),
)
#: The verdict keys an object turn does not read: the held ranking, the parser's per-message refine and drill readings
#: (a scoped drill runs first, `_settle`), and the engine's held stamps. The object is the whole ask.
_OBJECT_DROPS = ("sales_ranking_frame", "ranking_refine", "ranking_drill", HELD_KEY, "bare_top_selling", "required_ask")
#: The entity hints the object's lists replace (every other entity of the message stays: a location, a spec).
_OBJECT_HINTS = frozenset({"sales_agent", "brand", "category", "account_type", "customer", "product"})
#: The parser's report statuses: the object counts on a parse that is a report ask, or that answers this ask's question.
REPORT_STATUSES = frozenset({ASK_NAME, "top_selling", *SALES_STATUSES, *OUTSTANDING_STATUSES})


def arg_names(db: Any, args: Any, companies: Any = (), words: Any = None) -> dict[str, dict[str, str]]:
    """The word each id of a report's route args is shown with, and the company's name among the contact's own. Kept
    beside the ids on the frame and on an open question's slot, so the `Held report:` line names them and never prints
    an id. A carried word is resolved again (`_word_filters`), so a row is shown by a word that resolves back to exactly
    the held rows in the ask's company: a sales agent by the one word it was typed as (`words`: word -> the ids it
    resolved to) when that word resolves back to exactly those rows, else by its code (unique per company); a brand or
    category by its name when the name resolves to exactly those rows, else by its code; a customer by its name (the
    held ids ride beside it, `_fresh_args`), and every ledger of a customer group held whole by the group's one name, so
    that name maps back to exactly those ids (round 7d, `_group_names`); a product by its code."""
    from app.models.order import Customer
    from app.models.product import Brand, Product, ProductCategory
    from app.models.sales_agent import SalesAgent
    from app.services.chatbot.lanes.business.fetch import is_uuid

    args = _dict(args)
    out: dict[str, dict[str, str]] = {}
    columns = {
        "sales_agent_ids": (SalesAgent, SalesAgent.sales_agent, None),
        "brand_ids": (Brand, Brand.brand_name, Brand.brand_code),
        "category_ids": (ProductCategory, ProductCategory.category_name, ProductCategory.category_code),
        "customer_ids": (Customer, Customer.customer_name, None),
        "product_ids": (Product, Product.product_code, None),
    }
    company = jsc.js_string(args.get("company") or "").strip()
    for param, (model, name, code) in columns.items():
        ids = [str(i) for i in jsc.array(args.get(param)) if is_uuid(i)]  # M5: a non-UUID is no row (no DataError)
        if not ids or db is None:
            continue
        rows = db.query(model.id, name, code if code is not None else name).filter(model.id.in_(ids)).all()
        named = {str(i): str(n or c or "").strip() for i, n, c in rows}
        if code is not None:
            codes = {str(i): str(c or "").strip() for i, _n, c in rows}
            hint = "brand" if param == "brand_ids" else "category"
            for shown in {n.casefold() for n in named.values() if n}:
                held = {i for i, n in named.items() if n.casefold() == shown}
                word = next(n for n in named.values() if n.casefold() == shown)
                if set(_in_company(db, hint, _fresh_ids(db, hint, word), company or None)) != held:
                    named.update({i: codes[i] or named[i] for i in held})  # the name would widen or miss: the code
        if param == "customer_ids":
            named.update(_group_names(db, ids))
        if param == "sales_agent_ids":
            for word, typed in _dict(words).items():
                typed = {str(i) for i in jsc.array(typed) if str(i) in named}
                if typed and set(_in_company(db, "sales_agent", _fresh_ids(db, "sales_agent", word), company or None)) == typed:
                    named.update({i: str(word) for i in typed})  # one person's codes, as the one word that names them
        out[param] = {i: n for i, n in named.items() if n}
    shown = next((str(c[1]) for c in _own_companies(companies) if company and company == str(c[0])), None)
    if shown:
        out["company"] = {company: shown}
    return out


def _group_names(db: Any, ids: list[str]) -> dict[str, str]:
    """Round 7d: the held customer ids that make up a whole explicit customer group (every ledger of it, in its company),
    each by the group's one name: the Held report line shows the group once, and that name maps back (`_held_ids`) to
    exactly those ids. A group held only in part keeps each ledger's own name."""
    from app.models.order import Customer, CustomerGroup
    from app.services.chatbot.lanes.business.fetch import is_uuid

    ids = [str(i) for i in ids if is_uuid(i)]  # M5: a non-UUID is no row (no DataError)
    if not ids:
        return {}
    held = set(ids)
    members: dict[tuple[str, str, str], set[str]] = {}
    for i, group, company, name in (
        db.query(Customer.id, Customer.customer_group_id, Customer.company_id, CustomerGroup.name)
        .join(CustomerGroup, CustomerGroup.id == Customer.customer_group_id)
        .filter(Customer.id.in_(ids))
        .all()
    ):
        if str(name or "").strip():
            members.setdefault((str(group), str(company), str(name).strip()), set()).add(str(i))
    out: dict[str, str] = {}
    for (group, company, name), found in members.items():
        whole = {
            str(r[0])
            for r in db.query(Customer.id).filter(Customer.customer_group_id == group, Customer.company_id == company).all()
        }
        if whole <= held:
            out.update({i: name for i in found})
    return out


def with_names(db: Any, slot: Any, companies: Any = ()) -> Any:
    """An open question's slot with the names of the ask so far beside its ids (`extras["names"]`, `arg_names`)."""
    if not isinstance(slot, dict) or slot.get("ask") != ASK_NAME:
        return slot
    extras = _dict(slot.get("extras"))
    so_far = route_args(rf.Outcome(values=_dict(slot.get("values")), extras=extras))
    return {**slot, "extras": {**extras, "names": arg_names(db, so_far, companies, extras.get("agent_words"))}}


def _object_of(args: dict[str, Any], names: dict[str, Any], *, words: Any = (), outstanding: bool = False) -> dict[str, Any]:
    """Route args (a frame, or an open question's ask so far) in the `report_ask` shape, in its key order: every id by the
    name it was shown with (an id with no name, or that is no row id, is left out, never printed or carried), nulls and
    empty lists kept."""
    from app.services.chatbot.head.parser import REPORT_ASK_KEYS
    from app.services.chatbot.lanes.business.fetch import is_uuid

    def named(param: str) -> list[str]:
        shown = _dict(names.get(param))
        out: list[str] = []
        for i in jsc.array(args.get(param)):
            name = shown.get(str(i)) if is_uuid(i) else None
            if name and name not in out:
                out.append(name)
        return out

    axis = jsc.js_string(args.get("group_by") or "").strip()
    axis = _PARSER_AXIS.get(axis, axis) if axis in GROUP_BY.values() else ""
    basis = args.get("basis") if args.get("basis") in BASES else None
    company = jsc.js_string(args.get("company") or "").strip()
    code = jsc.js_string(args.get("product_code") or "").strip()
    # M1: no axis is a total; a trend, or an axis run with the breakdown's own row cap (`_settle`), is a breakdown; any
    # other axis is a ranking (its count given, or still asked).
    if not axis:
        frame = "total"
    elif axis in TREND_AXES or args.get("top_n") == BREAKDOWN_TOP_N:
        frame = "breakdown"
    else:
        frame = "ranking"
    ask = {
        "kind": "outstanding" if outstanding or basis in OUTSTANDING_KINDS else "sales",
        "frame": frame,
        "basis": basis,
        "date_from": args.get("date_from") or None,
        "date_to": args.get("date_to") or None,
        "group_by": axis or None,
        # A count only for a ranking (a measure ranks it): a breakdown's and a trend's row cap is not the user's count.
        "top_n": args.get("top_n") if frame == "ranking" and args.get("measure") and isinstance(args.get("top_n"), int) else None,
        "measure": args.get("measure") or None,
        "channel": args.get("channel") if args.get("channel") in ("dealer", "project") else None,
        "company": _dict(names.get("company")).get(company) if company else None,
        "sales_agents": named("sales_agent_ids"),
        "account_types": [str(t) for t in jsc.array(args.get("account_types")) if str(t).strip()],
        "brands": named("brand_ids"),
        "categories": named("category_ids"),
        "customers": named("customer_ids"),
        "products": [code] if code else named("product_ids"),
        "brand_or_account_type": [str(w) for w in jsc.array(words) if str(w).strip()],
        "company_or_brand": [],  # M2: only an open company-or-brand question holds a name here (`_held_object`)
    }
    return {key: ask[key] for key in REPORT_ASK_KEYS}


def held_report(focus: Any, keys: Any = None) -> str | None:
    """The one `Held report` line of the user turn (A2): the open question's ask so far, naming the field it asks, or
    else the report that last ran (`Focus.sales_ranking_frame`); None when neither is held. `keys`: the `report_ask` keys
    the prompt in use defines (`parser.report_ask_keys`; None: every key)."""
    from app.services.chatbot.turn.context import held_report_line

    ask, asking = _held_object(focus)
    if ask is not None and keys is not None:
        ask = {key: ask[key] for key in keys if key in ask}
    return held_report_line(ask, asking) if ask is not None else None


def _held_object(focus: Any) -> tuple[dict[str, Any] | None, str | None]:
    """The held report in the `report_ask` shape and the open question it asks (its words), or `(None, None)`: the open
    question's ask so far (its asked words in `brand_or_account_type`, or a company-or-brand question's name in
    `company_or_brand`, named "company or brand"), else the report that last ran."""
    slot = _dict(getattr(focus, "required_ask", None))
    if slot.get("ask") == ASK_NAME:
        extras = _dict(slot.get("extras"))
        values = _dict(slot.get("values"))
        so_far = route_args(rf.Outcome(values=values, extras=extras))
        if so_far.get("group_by") and "top_n" not in so_far and isinstance(extras.get("top_n"), int):
            so_far["top_n"] = extras["top_n"]  # M1: the count (or a breakdown's row cap) the ask holds, a field before it open
        both = bool(extras.get("kind_both")) and "kind" not in values
        words = extras.get("kind_words") if "kind" not in values and not both else ()
        ask = _object_of(so_far, _dict(extras.get("names")), words=words, outstanding=bool(extras.get("kind_ask")))
        if both:
            # M2: while the company-or-brand question is open its name is held in `company_or_brand` (the answer moves it
            # to the company and / or brands).
            held = [str(h.get("word")) for h in jsc.array(extras.get("kind_held")) if isinstance(h, dict) and h.get("word")]
            ask["company_or_brand"] = list(dict.fromkeys(held))
            # REPORT-FILTER-ALL (crew re-check step 16): the company reading of that name is what the question asks, so it
            # is not held: a "brand" answer leaves no company behind for `_keep_held` to put back (the company and both
            # answers set it, `from_object`'s `kind_company` pick).
            asked = {_squash(w) for w in held} | {_squash(x) for x in jsc.array(extras.get("kind_company"))[1:]}
            if _squash(ask.get("company") or "") in asked:
                ask["company"] = None
        asking = jsc.js_string(slot.get("asking") or "").strip()
        if asking == "kind" and extras.get("kind_both"):
            return ask, COMPANY_OR_BRAND_WORDS
        return ask, OPEN_QUESTION_WORDS.get(asking, asking.replace("_", " ")) or None
    if slot.get("ask") == SALES_BASIS_ASK and slot.get("asking"):
        # CP-1: the sales total's basis question (`sales_basis_ask`) holds its first message's own fields in `carry`
        # (flat: the company by name, the channel, the axis, the period); they are the ask so far.
        carry = _dict(_dict(slot.get("extras")).get("carry"))
        raw_axis = jsc.js_string(carry.get("group_by") or "").strip().lower()
        ask = _object_of({
            "group_by": GROUP_BY.get(raw_axis), "channel": carry.get("sales_channel"),
            "date_from": carry.get("date_filter_start"), "date_to": carry.get("date_filter_end"),
        }, {})
        ask["company"] = " ".join(jsc.js_string(carry.get("sales_company") or "").split()) or None
        return ask, OPEN_QUESTION_WORDS["basis"]
    frame = _dict(getattr(focus, "sales_ranking_frame", None))
    return (_object_of(frame, _dict(frame.get("names"))), None) if frame else (None, None)


def _held_names(focus: Any) -> dict[str, dict[str, str]]:
    """Every id -> name the held report and the open question's ask hold, per param (the open ask's win)."""
    out: dict[str, dict[str, str]] = {}
    sources = (
        _dict(_dict(getattr(focus, "sales_ranking_frame", None)).get("names")),
        _dict(_dict(_dict(getattr(focus, "required_ask", None)).get("extras")).get("names")),
    )
    for names in sources:
        for param, ids in names.items():
            out.setdefault(param, {}).update({str(i): str(n) for i, n in _dict(ids).items()})
    return out


def _held_bases(focus: Any) -> set[str]:
    """The basis the held report ran with and the one the open question's ask already holds (the user chose them)."""
    frame = _dict(getattr(focus, "sales_ranking_frame", None))
    slot = _dict(getattr(focus, "required_ask", None))
    held = {frame.get("basis")}
    if slot.get("ask") == ASK_NAME:
        held |= {
            _dict(_dict(slot.get("extras")).get("args")).get("basis"),
            _dict(_dict(slot.get("values")).get("basis")).get("value"),
        }
    return {b for b in held if b in BASES}


def _rows_on_screen(verdict: dict[str, Any], focus: Any, pending: Any) -> bool:
    """V5 and the agent pick: a pick of a position under an open pick list or offer, and the answer to this ask's own
    scope or sales agent pick, are read off the rows and options on screen, as today. The parser's `continuation` alone
    sets nothing aside: a "more" under a cut summary is the pick list's own answer (`apply._answer_top_selling_pick` sets
    `ranking_detail`), which `_settle` reads before the object."""
    slot = _dict(getattr(focus, "required_ask", None))
    if slot.get("ask") == ASK_NAME and slot.get("asking") in ("sales_agent", "scope"):
        return True
    answer = _dict(verdict.get("open_question_answer"))
    picked = answer.get("mode") == "pick" and bool(jsc.array(answer.get("picked")))
    return pending is not None and bool(picked or jsc.array(verdict.get("reference_positions")))


#: An open offered-option field of this ask -> the object slot its declared pick fills (the brand-or-account-type pick:
#: `_word_kinds`, its company option the object's `company`). The measure question is a free one: the object's own
#: `measure` answers it.
_PICK_FILLS = {"basis": "basis"}


def _open_pick(verdict: dict[str, Any], focus: Any) -> tuple[str, Any, str] | None:
    """`(field, value, label)` of the offered option the parser DECLARED picked (`open_question_answer` mode pick, its first
    position in range) while one of this ask's questions is open; None otherwise. The list-pick class (V5): read off the
    options shown, never the message's words."""
    slot = _dict(getattr(focus, "required_ask", None))
    if slot.get("ask") != ASK_NAME or not slot.get("asking"):
        return None
    picked = rf.picked_option(slot, verdict.get("open_question_answer"))
    return (str(slot["asking"]), picked.value, str(picked.label)) if picked.status == "ok" else None


def _word_kinds(
    ask: dict[str, Any], verdict: dict[str, Any], focus: Any, picked: Any = None, *, company: Any = None,
    companies: Any = (), said_as_text: bool = False,
) -> list[tuple[str, str, dict[str, Any] | None, str | None]]:
    """V4: each brand / account type word of the object as `(word, how, entity, slot)`, how = brand | account_type |
    company | both | unsure (`unsure`: the tables decide, `_account_plan`, and a word in both is asked), entity: this
    message's entity of the word, if any; slot: the `said_as` that decided it (HT1), else None. Not the object's list alone (a model may
    list a word the message left open as a brand), never the message's text: in order, the declared pick of an offered
    option while the brand-or-account-type question is open fills the asked words (the V5 list-pick class): all of them
    unless the object adds a word the open ask did not already hold, else only those it still carries (a dropped one
    stays dropped, the object being the newer value); a word that is one of the contact's companies (`companies`, its name or
    code, as `_company_or_brand` reads them), named as an entity whose `said_as` is not null, is that slot (HT1: company,
    brand or both; `from_object` applies it to the company), and for any other word `said_as` is not read (with
    `said_as_text`, a prompt text that defines that key, a `said_as` counts only beside a non-empty `said_as_text`, the
    word the message typed for it: said or not, never compared with the message, HT1-13); a word this
    message names
    as an entity is that entity's kind when `kind_said` says it; with `kind_said` null, a word the object put in its
    brands or account types, whose entity the parser bound to no candidate (`canonical_code` null), that is also the
    object's own `company` (`company`) is the company (C6-1: the model read "company" and wrote the word twice), else
    unsure; a word the open question still owes is unsure (asked again), except that the object's brands answer the
    company-or-brand question (M2, `kind_both`); a word left in `brand_or_account_type` or `company_or_brand` is unsure
    (`company_or_brand` read first and whatever `kind_said` says: the slots decide, the data settles it); any other
    word, carried from the held report, keeps its list and is never asked. `kind_said` is read as said or not, never
    by its words."""
    def fold(value: Any) -> str:
        return " ".join(jsc.js_string(value).split()).casefold()

    own = {fold(c[k] or "") for c in _own_companies(companies) for k in (1, 2)} - {""}
    slot = _dict(getattr(focus, "required_ask", None))
    slot = slot if slot.get("ask") == ASK_NAME else {}
    extras = _dict(slot.get("extras"))
    owed_words = [w for w in jsc.array(extras.get("kind_words")) if fold(w)] if "kind" not in _dict(slot.get("values")) else []
    owed = {fold(w) for w in (*owed_words, *(jsc.array(extras.get("kind_match")) if owed_words else ()))}
    both_open = bool(owed_words) and bool(extras.get("kind_both"))  # M2: the company-or-brand question is open
    either = {fold(w) for w in jsc.array(ask.get("company_or_brand"))} - {""}
    named: dict[str, dict[str, Any]] = {}
    every: dict[str, list[dict[str, Any]]] = {}  # REPORT-FILTER-ALL: each entity of this message naming the word
    for e in jsc.array(verdict.get("entities")):
        if isinstance(e, dict) and e.get("current_message") is not False and jsc.js_string(e.get("hint") or "").strip().lower() in ("brand", "account_type"):
            for key in {fold(e.get(k)) for k in ("raw", "canonical_code")} - {""}:
                named.setdefault(key, e)
                every.setdefault(key, []).append(e)

    def said_as_of(key: str) -> Any:
        """The `said_as` of the word over every entity of this message that names it (crew gate steps 8 / 14: "Sorento
        company, brands Sorento and Cabana" names it twice, once each way): company and brand together are both. With
        `said_as_text` defined, an entity's `said_as` counts only beside its typed word (HT1-13)."""
        said = {
            e.get("said_as") for e in every.get(key, ())
            if e.get("said_as") in SAID_AS and (not said_as_text or jsc.js_string(e.get("said_as_text") or "").strip())
        }
        if "both" in said or {"company", "brand"} <= said:
            return "both"
        return next(iter(said)) if len(said) == 1 else None
    out: list[tuple[str, str]] = []
    lists = [
        (key, default) for key, default in (
            ("company_or_brand", None), ("brands", "brand"), ("account_types", "account_type"), ("brand_or_account_type", None),
        )
    ]
    words = [(w, default) for key, default in lists for w in jsc.array(ask.get(key))]
    if picked:
        # One rule: the asked words are what the pick answers, and carry, unless the object adds a brand or account type
        # word the open ask did not already hold (the newer value: a dropped asked word then stays dropped).
        held = owed | {fold(n) for n in _dict(_dict(extras.get("names")).get("brand_ids")).values()} | {
            fold(t) for t in jsc.array(_dict(extras.get("args")).get("account_types"))
        }
        if not any(fold(w) and fold(w) not in held for w, _default in words):
            words += [(w, None) for w in owed_words]
    for word, default in words:
        word = " ".join(jsc.js_string(word).split())
        key = fold(word)
        if not key or key in {fold(w) for w, _how, _e, _s in out}:
            continue
        entity = named.get(key)
        # HT1: read only for one of the contact's companies; HT1-13: an entity whose typed word is empty says nothing.
        said_as = said_as_of(key) if {key, fold((entity or {}).get("raw"))} & own else None
        if picked and key in owed:
            how = picked
        elif said_as in SAID_AS:
            how = said_as  # HT1: a non-null `said_as` on one of the contact's companies is the parser's own slot for it
        elif key in either:
            how = "unsure"  # M2: a `company_or_brand` name is the data's to settle (`_company_or_brand`), asked when both
        elif entity is not None and "kind_said" in entity and kind_was_said(entity.get("kind_said")):
            how = jsc.js_string(entity.get("hint")).strip().lower()
        elif entity is not None and "kind_said" in entity:
            # The model committed the word to neither reading (left out of `brand_or_account_type`, bound to no candidate):
            # equal to its own company, it is that company.
            loose = default is not None and not jsc.js_string(entity.get("canonical_code") or "").strip()
            how = "company" if loose and key == fold(company or "") else "unsure"
        elif default is None or (key in owed and not (both_open and default == "brand")):
            how = "unsure"
        else:
            how = default  # M2: an owed name the object moved to its brands answers the company-or-brand question
        out.append((word, how, entity, how if said_as in SAID_AS and how == said_as else None))
    return out


def _entity(raw: str, hint: str, code: Any = None, **more: Any) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": code, "current_message": True, "confident": True, **more}


def from_object(
    verdict: dict[str, Any], *, on: bool, focus: Any = None, pending: Any = None, companies: Any = (),
    said_as_text: bool = False, all_value: bool = False,
) -> dict[str, Any]:
    """Engine seam, right after the parse (A3). `on`: the prompt in use carries the report ask marker
    (`ParserConfig.report_ask`); off, the key is dropped and nothing else changes.

    On, a `report_ask` object is the whole report the user wants after this message: its slots become the flat fields the
    fresh ask already reads (the kind, the period, the axis, the count, the measure, the channel, the company, the basis,
    and one entity per name), so every word -> id resolution, question and rail below runs unchanged and no carry seam
    reads the turn. Value checks only: V1, the object's basis counts when this message's own `basis` / `sales_basis` says
    it or the held report / open ask already has it; the open question's declared pick fills the slot it asks when the
    object left it null (`_open_pick`; the word question's company option fills the company, C6-1); a month or year axis
    takes only this message's own count. REPORT-FILTER-ALL: the object is final; a filter slot written ALL is no
    filter, and the one safety rule (`_keep_held`) keeps a held value the object left empty. `all_value`: the prompt in use
    defines ALL (`parser.REPORT_ALL` in `ParserConfig.report_ask_defined`); off, the legacy widen signal stands in for it
    (`_legacy_all`). An axis this message does not type stays the held one on an answer to the open question, and over a
    slot the ask filters to one value (C6-2). The held names -> ids ride
    along for the lane's customer rule (`_fresh_args`). The object counts only on a report parse (`REPORT_STATUSES`)
    or a reply while this ask's question is open; an object that is not a sales or outstanding ask, or a turn read off
    the rows on screen (`_rows_on_screen`), keeps today's path: the object is set aside (null). `companies`: the contact's
    own (`sales_company_ask._companies`, the engine's read of the turn), for `said_as` (`_word_kinds`); `said_as_text`:
    the prompt text defines that key (`ParserConfig.said_as_text`)."""
    if HELD_IDS_KEY in verdict:
        verdict = {k: v for k, v in verdict.items() if k != HELD_IDS_KEY}  # the engine's own key: no parser value survives
    if not on:
        return {k: v for k, v in verdict.items() if k != OBJECT_KEY} if OBJECT_KEY in verdict else verdict
    from app.services.chatbot.head.parser import REPORT_ASK_FRAMES, REPORT_ASK_KEYS

    raw = verdict.get(OBJECT_KEY)
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    held_ask, _asking = _held_object(focus)
    # REPORT-FILTER-ALL (crew gate X "清除所有筛选"): on the ALL prompt the object is null on every message that is not a
    # report ask, so an object of the held report's kind is that report's follow-up, whatever the rest of the parse read
    # (a clear with no report word came back with no status and a casual message type).
    follow_up = (
        all_value and isinstance(raw, dict) and held_ask is not None and verdict.get("topic_reset") is not True
        and raw.get("kind") == held_ask.get("kind")
    )
    reported = (
        status in REPORT_STATUSES or _dict(getattr(focus, "required_ask", None)).get("ask") == ASK_NAME or follow_up
    )
    if (
        not isinstance(raw, dict) or raw.get("kind") not in ("sales", "outstanding") or not reported
        or _rows_on_screen(verdict, focus, pending)
    ):
        return {**verdict, OBJECT_KEY: None}
    ask = {key: raw.get(key) for key in REPORT_ASK_KEYS}  # the schema's keys only
    cleared = _read_all(ask) | (set() if all_value else _legacy_all(ask, verdict))
    if follow_up:
        # REPORT-FILTER-ALL: the one keep rule over the report's own slots (period, basis, measure, frame, breakdown,
        # count), before anything below reads them; its filter half runs once the axis is settled (`_keep_held`).
        _keep_held_report(ask, held_ask, framed="frame" in raw)
    # M1: what the report gives back, the parser's own call; null or absent (a text without the key) is today's inference.
    frame = ask["frame"] = ask.get("frame") if ask.get("frame") in REPORT_ASK_FRAMES else None

    def names(key: str) -> list[str]:
        out: list[str] = []
        for value in jsc.array(ask.get(key)):
            word = " ".join(jsc.js_string(value).split())
            if word and word.casefold() not in {w.casefold() for w in out}:
                out.append(word)
        return out

    basis = ask.get("basis") if ask.get("basis") in BASES else None
    if basis is not None and basis not in {verdict.get("basis"), verdict.get("sales_basis")} | _held_bases(focus):
        basis = None  # V1: never defaulted; the basis question asks
    ask["basis"] = basis
    own_company = ask.get("company")  # the object's own, before any carry (C6-1)
    pick = _open_pick(verdict, focus)
    if pick is not None and _PICK_FILLS.get(pick[0]) and ask.get(_PICK_FILLS[pick[0]]) in (None, ""):
        # One rule: the open question's declared pick fills the slot it asks when the object left that slot null.
        ask[_PICK_FILLS[pick[0]]] = pick[1]
    asked = _dict(getattr(focus, "required_ask", None))
    if (
        ask.get("basis") in (None, "") and asked.get("ask") == ASK_NAME and asked.get("asking") == "basis"
        and _dict(asked.get("extras")).get("kind_ask") and status in STATUS_KIND
    ):
        # Owner wording (4 Nov): the outstanding kind question's answer the parser wrote as the document status that
        # names the kind ("Sales order" -> so_outstanding) is that kind, the report ask's own outstanding ask.
        ask["basis"], status = STATUS_KIND[status], "outstanding"
    kind_company = _dict(_dict(getattr(focus, "required_ask", None)).get("extras")).get("kind_company")
    if (
        pick is not None and pick[0] == "kind" and pick[1] in (COMPANY_KIND_OPTION[0], BOTH_KIND_OPTION[0])
        and jsc.array(kind_company)
    ):
        # C6-1: the company option of the word question: the word is that company (`_word_kinds` drops it as a word).
        # M2: the both option is that company AND the brand (`_word_kinds` keeps the word as a brand).
        ask["company"] = own_company = str(jsc.array(kind_company)[-1])
    elif (
        pick is not None and pick[0] == "kind" and pick[1] == "brand" and jsc.array(kind_company)
        and _squash(ask.get("company") or "") in {_squash(x) for x in jsc.array(kind_company)[1:]}
    ):
        # REPORT-FILTER-ALL (crew re-check step 16, owner: a "brand" answer replaces the company reading of the name, it
        # does not add to it): the declared brand pick settles the asked name, so the object's company of that same
        # name is no filter.
        ask["company"] = own_company = None
    basis = ask["basis"] if ask.get("basis") in BASES else None
    outstanding = ask.get("kind") == "outstanding" or basis in OUTSTANDING_KINDS
    # C6-2: the held report carries into this one unless the message starts another report kind or resets the topic.
    carrying = (
        held_ask is not None and verdict.get("topic_reset") is not True
        and held_ask.get("kind") == ("outstanding" if outstanding else "sales")
    )
    held_axis = (held_ask or {}).get("group_by") if carrying else None
    axis = jsc.js_string(ask.get("group_by") or "").strip().lower() or None
    if frame == "total" and axis is None:
        # Crew re-check step 1 on v78: the object came back total with no axis; the parse's top-level `group_by` is this
        # message's own reading (the prompt: from the current message only). It is the candidate the rule below weighs.
        own = jsc.js_string(verdict.get("group_by") or "").strip().lower()
        axis = own or None
    own_slot = _AXIS_SLOTS.get(axis or "")
    if (
        frame == "total" and axis is not None and axis != held_axis and own_slot
        and not (len(names(own_slot)) == 1 if own_slot != "channel" else ask.get("channel") in ("dealer", "project"))
    ):
        # REPORT-FILTER-ALL (crew re-check step 1 / fa-36): a total frame beside an axis this message names itself (none
        # held, or another one) whose own slot is not one value is that slot's values side by side: the breakdown
        # (prompt edit 6). An axis over a slot the ask filters to ONE value is one row (C6-2, AF-1's noisy "brand"), and
        # a copied held axis under a total is still dropped (below).
        frame = ask["frame"] = "breakdown"
    if frame == "total":
        axis = None  # M1: one figure; the held axis and count are not carried, so no count or measure is asked
    elif frame == "breakdown" and axis is None:
        axis = held_axis  # M1: a breakdown on the held axis
    own_count = ask.get("top_n")
    counted = (
        frame == "breakdown" and axis is not None
        and isinstance(own_count, int) and not isinstance(own_count, bool) and own_count > 0
    )
    if counted:
        # AF-7: the object's own count makes a breakdown a ranking cut to that count (never every row).
        frame = "ranking"
    elif (
        frame == "ranking" and axis is not None and axis == held_axis and (held_ask or {}).get("frame") == "breakdown"
        and not (isinstance(own_count, int) and not isinstance(own_count, bool) and own_count > 0)
        and verdict.get("rank_direction") != "bottom"
    ):
        # HT1-8: a ranking on the held every-row list's own axis with no count of its own (only a filter changed) is that
        # list again, every row; never "How many?". Its own count ranks (AF-7, CP-6); a bottom ranking is asked its count.
        frame = "breakdown"
    # This message types an axis: the parser's own `by_words`, or a count, direction or ranked measure (main's `_typed`).
    typed = bool(jsc.js_string(verdict.get("by_words") or "").strip()) or any(
        verdict.get(k) not in (None, "") for k in ("top_n", "rank_direction", "rank_by")
    )
    # M1: a frame naming an axis other than the held one, on a new ask (no declared answer to the open question), is the
    # parser's own call: that axis wins over the held one, an open count question included. It never lifts the
    # one-value rule below.
    framed = (
        frame is not None and axis is not None and axis != held_axis
        and _dict(verdict.get("open_question_answer")).get("mode") is None
    )
    open_slot = _dict(getattr(focus, "required_ask", None))
    if axis and open_slot.get("ask") == ASK_NAME and not (typed or framed):
        # A reply to this ask's open question sets no axis the held ask did not have unless this message types one: the
        # held ask's axis stays (a total stays one).
        held_group = _dict(_dict(open_slot.get("extras")).get("args")).get("group_by")
        if GROUP_BY.get(axis, axis) != held_group:
            axis = _PARSER_AXIS.get(held_group, held_group) if held_group in GROUP_BY.values() else None
    slot_of_axis = _AXIS_SLOTS.get(axis or "")
    if slot_of_axis and not typed and (
        len(names(slot_of_axis)) == 1 if slot_of_axis != "channel" else ask.get("channel") in ("dealer", "project")
    ):
        # C6-2 (turn 23d6cb50): an axis this message does not type, over a slot the ask filters to ONE value, is one
        # row: not a breakdown, the held axis stays.
        axis = held_axis
        slot_of_axis = _AXIS_SLOTS.get(axis or "")
    if frame == "ranking" and axis is not None and axis not in TREND_AXES and ask.get("measure") not in METRICS:
        # CP-2 / CP-6 (crew ruling, ask less): a ranking the parser framed (or a counted breakdown, AF-7) ranks by the
        # object's measure, else the held one, else amount; it never asks "By quantity or by amount?".
        held_measure = (held_ask or {}).get("measure") if carrying else None
        ask["measure"] = held_measure if held_measure in METRICS else "amount"
    if carrying:
        typed = [
            e.get(k) for e in jsc.array(verdict.get("entities"))
            if isinstance(e, dict) and e.get("current_message") is not False for k in ("raw", "canonical_code")
        ]
        _keep_held(ask, held_ask, cleared, slot_of_axis, companies, typed)
    breakdown = frame == "breakdown" and axis is not None
    if outstanding:
        status = status if status in OUTSTANDING_STATUSES else "outstanding"
    elif axis is None:
        status = "sales_report"  # a total
    elif breakdown:
        status = "sales_analysis"  # M1: every row (`by_capability` marks the breakdown), never a top selling ranking
    elif status not in (ASK_NAME, "top_selling", *SALES_STATUSES):
        status = "sales_report"
    held = _held_names(focus)
    entities = [
        e for e in jsc.array(verdict.get("entities"))
        if not (isinstance(e, dict) and jsc.js_string(e.get("hint") or "").strip().lower() in _OBJECT_HINTS)
    ]
    # By name: the lane maps a held name back to its id, or resolves it, by the company rule (`_word_filters`).
    entities.extend(_entity(name, "sales_agent") for name in names("sales_agents"))
    entities.extend(_entity(name, "category") for name in names("categories"))
    picked = pick[1] if pick is not None and pick[0] == "kind" else None
    held_company = (held_ask or {}).get("company") if carrying else None
    for word, how, entity, slot in _word_kinds(
        ask, verdict, focus, picked, company=own_company, companies=companies, said_as_text=said_as_text
    ):
        if slot is not None:
            # HT1: the parser's own slot for a name that is one of the contact's companies. Company or both: the name is
            # the ask's company. Brand: the brand only, and the object's own company slot stays as written: the object is
            # final (REPORT-FILTER-ALL round 6, crew re-check step 14a, where said_as brand used to drop an object company
            # of the same name and the display disagreed with the parse).
            same = _squash(ask.get("company") or "") == _squash(word)
            if slot != "brand" and not same:
                ask["company"] = word
        if how in ("brand", BOTH_KIND_OPTION[0]):  # M2: the both option keeps the word as the brand beside the company
            entities.append(_entity(word, "brand"))
        elif how == "account_type":
            entities.append(_entity(word, "account_type"))
        elif how != "company":  # a word that is the ask's company is no brand or account type filter (C6-1)
            # Unsure: the brand-or-account-type plan reads it against the tables (`_account_plan`), asked when in both;
            # a `said_as` null rides along (HT1-5, `_company_or_brand`).
            more = {"said_as": None} if entity is not None and "said_as" in entity else {}
            entities.append(_entity(word, "brand", kind_said=None, **more))
    # A held customer is never looked up again (the lane takes its id, `_fresh_args`); any other goes to the resolver.
    entities.extend(_entity(name, "customer") for name in names("customers") if not _held_ids(held, "customer_ids", name))
    entities.extend(_entity(code, "product") for code in names("products"))
    # A month or year axis lists every bucket: it takes no count this message did not give (a copied one is not its own).
    top_n = verdict.get("top_n") if axis in TREND_AXES else ask.get("top_n")
    if frame in ("total", "breakdown"):
        top_n = None  # M1: no count: one figure, or every row
    out = {k: v for k, v in verdict.items() if k != "by_words"}  # the object names the axis, not this message's words
    if breakdown:
        # M1: a stray direction or ranked measure beside a breakdown frame is not read (the real C5 parse). A counted
        # ranking (AF-7) keeps the parser's own direction ("bottom 5").
        out.update(rank_direction=None, rank_by=None)
    out.update(
        order_status=status,
        group_by=axis,
        top_n=top_n if isinstance(top_n, int) and not isinstance(top_n, bool) else None,
        measure=ask.get("measure") if ask.get("measure") in METRICS else None,
        sales_channel=ask.get("channel") if ask.get("channel") in ("dealer", "project") else None,
        sales_company=" ".join(jsc.js_string(ask.get("company") or "").split()) or None,
        date_filter_start=ask.get("date_from") or None,
        date_filter_end=ask.get("date_to") or None,
        basis=basis,
        sales_basis=None,
        ranking_refine=False,
        entities=entities,
        # A pick here is of the open question's options (no list is on screen, `_rows_on_screen`): the object already
        # holds what it picked, and the open question is not read on an object turn.
        open_question_answer=None,
        reference_positions=[],
    )
    out[OBJECT_KEY] = ask  # as read, the carried lists included: the lane maps its held customer names to their ids
    if held:
        out[HELD_IDS_KEY] = held
    return out


def _read_all(ask: dict[str, Any]) -> set[str]:
    """REPORT-FILTER-ALL: the filter slots the object writes ALL (`parser.REPORT_ALL`), each set to no filter (null or [])
    in place. ALL anywhere in a list is the whole list."""
    from app.services.chatbot.head.parser import REPORT_ALL

    out: set[str] = set()
    for slot in _FILTER_SLOTS:
        value = ask.get(slot)
        values = jsc.array(value) if isinstance(value, list) else [value]
        if any(isinstance(v, str) and v.strip().casefold() == REPORT_ALL.casefold() for v in values):
            ask[slot] = [] if isinstance(value, list) else None
            out.add(slot)
    return out


def _legacy_all(ask: dict[str, Any], verdict: dict[str, Any]) -> set[str]:
    """TODO(REPORT-FILTER-ALL): delete once the owner publishes a prompt that writes ALL (crew ruling Q2, 5 Nov). A
    prompt without ALL widens by the legacy signal (`turn.decide.widened_kinds`: `broaden_axis` with `broaden_to` "all",
    and the customer on a global drill or "my ..."): each slot it names that the object left empty reads as ALL."""
    from app.services.chatbot.turn.decide import widened_kinds

    slots = {slot for kind in widened_kinds(verdict) for slot in _LEGACY_WIDEN_SLOTS.get(kind, ())}
    return {slot for slot in slots if not ask.get(slot)}


def _keep_held_report(ask: dict[str, Any], held_ask: dict[str, Any], *, framed: bool) -> None:
    """REPORT-FILTER-ALL, the same ONE rule as `_keep_held`, over the report's own slots (crew gate 5 Nov: "clear all"
    lost the period and basis): a slot the object left null, over a held value, keeps it; a value replaces it. The
    period is one slot (both dates null keeps both). `framed`: the prompt defines `frame`; a null frame keeps the held
    frame, and every frame but a total keeps the held breakdown axis when the object names none, and the held count on
    that same axis when it gives none. A total is the object's own call: no axis, no count."""
    for slot in ("basis", "measure"):
        if ask.get(slot) in (None, "") and held_ask.get(slot):
            ask[slot] = held_ask[slot]
    if not ask.get("date_from") and not ask.get("date_to") and (held_ask.get("date_from") or held_ask.get("date_to")):
        ask["date_from"], ask["date_to"] = held_ask.get("date_from"), held_ask.get("date_to")
    if not framed:
        return
    if ask.get("frame") is None:
        ask["frame"] = held_ask.get("frame")
    if ask.get("frame") == "total":
        return
    if not ask.get("group_by"):
        ask["group_by"] = held_ask.get("group_by")
    if ask.get("top_n") is None and ask.get("group_by") == held_ask.get("group_by"):
        ask["top_n"] = held_ask.get("top_n")


def _keep_held(
    ask: dict[str, Any], held_ask: dict[str, Any], cleared: set[str], axis_slot: str | None, companies: Any = (),
    typed: Any = (),
) -> None:
    """REPORT-FILTER-ALL, the ONE safety rule over the parser's final object: a filter slot it left empty, over a held
    value, without ALL, forgot to echo it: the held value stays. Not the axis's own slot (a breakdown ranks across it,
    C6-2), and not a held brand or account type name the object moved to the other of the two lists or to the company
    (`_MOVES`: the brand-or-account-type answer, a name the message calls the company); the company itself is never
    un-held by a move ("<name> brand only" keeps the held company). Then a company that is none of the contact's own,
    that this message does not type, and that spells the held one is the held one (`_held_spelling`)."""
    def fold(value: Any) -> set[str]:
        return {_squash(v) for v in (jsc.array(value) if isinstance(value, list) else [value]) if v}

    def new_in(slot: str) -> set[str]:  # what the object newly puts in this slot (a refill equals the held value)
        return fold(ask.get(slot)) - fold(held_ask.get(slot))

    for slot in _FILTER_SLOTS:
        held = held_ask.get(slot)
        if slot in cleared or slot == axis_slot or ask.get(slot) or not held:
            continue
        if isinstance(held, list):
            moved = {name for other in _MOVES.get(slot, ()) for name in new_in(other)}
            ask[slot] = [v for v in held if _squash(v) not in moved]
        else:
            ask[slot] = held
    ask["company"] = _held_spelling(ask.get("company"), held_ask.get("company"), companies, typed)


#: `_keep_held`: the slots a held list name can move to (the model moves a word between brands and account types, and a
#: name the message calls the company out of the brands). Every other slot only ever refills.
_MOVES = {"brands": ("account_types", "company"), "account_types": ("brands",)}


def _held_spelling(company: Any, held: Any, companies: Any = (), typed: Any = ()) -> Any:
    """HT1-18 (v202 parse "Sorenth" over a held Sorento): the object's company, unless it is none of the contact's own
    companies (by name or code), no entity of this message names it (`typed`: the raw words and codes of this message's
    entities), and it is a near spelling of the held one: then the held one. An own company always wins (HT1-18b /
    HT1-19); a company the message typed stays as written and is refused downstream when not held (HT1-20)."""
    from difflib import SequenceMatcher

    said, kept = _squash(company or ""), _squash(held or "")
    if not said or not kept or said == kept:
        return company
    own = {_squash(c[i]) for c in list(companies or ()) if isinstance(c, (list, tuple)) for i in (1, 2) if len(c) > i}
    if said in own or said in {_squash(t) for t in list(typed or ()) if t}:
        return company
    return held if SequenceMatcher(None, said, kept).ratio() >= _ECHO_RATIO else company


#: `_held_spelling`: how close an unknown company name must be to the held one to be its echo (one wrong letter in a
#: seven-letter name is 0.86; another company's name is far below).
_ECHO_RATIO = 0.8


_COMPANY_ROWS = {"sales_agent": "SalesAgent", "brand": "Brand", "category": "ProductCategory", "customer": "Customer"}


def _in_company(db: Any, hint: str, ids: Any, company: Any) -> list[str]:
    """The ids (of one subject kind) that are rows of `company` or shared (no company); every id when no company is
    named."""
    ids = [str(i) for i in jsc.array(ids) if i]
    if not ids or not company or db is None:
        return ids
    from sqlalchemy import or_

    from app.services.chatbot.lanes.business.fetch import is_uuid

    ids = [i for i in ids if is_uuid(i)]  # M5: a non-UUID is no row of the company (no DataError)

    from app.models.order import Customer
    from app.models.product import Brand, ProductCategory
    from app.models.sales_agent import SalesAgent

    model = {"SalesAgent": SalesAgent, "Brand": Brand, "ProductCategory": ProductCategory, "Customer": Customer}[_COMPANY_ROWS[hint]]
    rows = db.query(model.id).filter(model.id.in_(ids), or_(model.company_id == str(company), model.company_id.is_(None))).all()
    keep = {str(r[0]) for r in rows}
    return [i for i in ids if i in keep]


def _fresh_ids(db: Any, hint: str, word: str) -> list[str]:
    """The ids a brand, category or sales agent word resolves to, as `_word_filters` resolves it (none for an ambiguous
    category)."""
    if hint == "category":
        from app.services.chatbot.lanes import business as business_pkg

        found, _named, ambiguous, _unknown = business_pkg._top_selling_category_ids({"category_words": [word]}, db=db)
        return [] if ambiguous else [str(i) for i in found]
    return [str(i) for i in _resolve_word(db, hint, word)[0]]


def _customer_in(db: Any, name: str, company: Any) -> list[str]:
    """The one customer of `company` whose stored name is `name` (the Held report line prints it as stored, case aside),
    for a principal that may read customers; none when no company is named, when no row has it, or when several share it
    (a shared name is never widened)."""
    if db is None or not company or not name or staff_principal.lacks(db, staff_principal.CUSTOMERS_VIEW):
        return []
    from sqlalchemy import func

    from app.models.order import Customer

    rows = db.query(Customer.id).filter(
        func.lower(Customer.customer_name) == " ".join(name.split()).casefold(), Customer.company_id == str(company)
    ).limit(2).all()
    return [str(rows[0][0])] if len(rows) == 1 else []


def _held_ids(held: dict[str, Any], param: str, name: str) -> list[str]:
    """The ids the held report (or the open question's ask) showed by this name."""
    folded = " ".join(jsc.js_string(name).split()).casefold()
    return [str(i) for i, n in _dict(held.get(param)).items() if folded and " ".join(str(n).split()).casefold() == folded]


def _object_scope(parse_output: dict[str, Any], companies: Any) -> dict[str, Any] | None:
    """An object turn's word scope (`_word_filters`): the contact's own company the ask names (None: none named) and
    the held names -> ids (`from_object`). None off the object path."""
    if not isinstance(parse_output.get(OBJECT_KEY), dict):
        return None
    named, _foreign = _company_said(parse_output, _own_companies(companies))
    return {
        "company": str(named[0]) if named is not None else None,
        "company_name": str(named[1]) if named is not None else "",
        "held": _dict(parse_output.get(HELD_IDS_KEY)),
    }
