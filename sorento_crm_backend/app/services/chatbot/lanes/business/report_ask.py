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

from datetime import date
from typing import Any

from app.services.chatbot import contracts, jsc
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
    "month": "month",
}

#: The parser's other report types (`order_status`): one that fills no open field of the sales
#: ranking question is a new ask, not its answer (chat fix PR-B S2c, `names_its_own_ask`).
OTHER_REPORTS = frozenset({"top_selling", "sales_report", "sales_analysis", "outstanding"})

#: The entity hints `take_words` moves, and the noun each is said with when it names nothing.
WORD_HINTS = {"brand": "brand", "sales_agent": "sales agent", "category": "category"}

#: One ceiling, shared with the routes (owner, 30 Sep 2026).
TOP_N_MIN, TOP_N_MAX = 1, TOP_SELLING_N_CEILING
#: Said above a ranking whose named N passed the ceiling (owner, 30 Sep 2026: no 100 cap, and
#: no silent clamp either). It promises no count: fewer items than the ceiling may have sold.
CEILING_NOTE = f"I can list at most the top {TOP_N_MAX:,} in one reply."
#: A month breakdown is a trend, never asked "How many?": every month of the period (1b code
#: review S2). This is its own row count, not a second top-N limit.
MONTH_TOP_N = 100

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
    "month": ("month", "months"),
}
#: Said when a drill names rows ("these agents") and no ranking is held: never a guess.
NO_RANKING_LINE = (
    "I don't have a ranking to take those from. "
    "Ask the ranking first, for example top 5 sales agents for a product this year."
)
#: A channel or a month list is not a drill source: those are named in words.
NOT_A_SOURCE_LINES = {
    "month": "I can't narrow by the months above. Name the period instead, for example September.",
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
}
#: The frame keys that are not route params.
_FRAME_ONLY = ("date_from", "date_to", "top_n", "shown", "stale")


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
    return f"{d.day} {d.strftime('%b %Y')}"


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
        "ok", value={"from": first.isoformat(), "to": last.isoformat()}, label=f"{_label(first)} to {_label(last)}"
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
KIND_QUESTION = "Undelivered orders, pending delivery or unpaid invoices?"
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
SALES_REPORT_GRANT = "sales_orders.sales_report"


def grant_key(parse_output: dict[str, Any]) -> str:
    """The reveal a report ask is read under (owner Q6): the Outstanding reveal for an outstanding kind
    (or an outstanding ask whose kind is still to be asked), the Sales report reveal for every other basis."""
    if not isinstance(parse_output, dict):
        return SALES_REPORT_GRANT
    if parse_output.get("order_status") != ASK_NAME:
        return SALES_REPORT_GRANT
    if parse_output.get("basis") in OUTSTANDING_KINDS or (
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
BASIS = rf.FieldSpec(name="basis", noun="basis", question=ranking_ask.RANKING_BASIS_LINE, question_fn=_basis_question, resolve=_resolve_basis, allow_all=False)

#: The scope question's slot (`asking == "scope"`, the drill ask): its words ride on the slot's
#: extras; the spec only lets the parser be shown it as the Open question (REPORT-SMART-L S3-1).
SCOPE = rf.FieldSpec(name="scope", noun="scope", question="", resolve=lambda _db, _word, _extras: rf.Resolved("unknown"), allow_all=False)

#: REPORT-UNIFY slice 3 (H3): a sales agent word that several agent rows answer to is asked as a numbered pick of
#: agents only. Never required: it is a field only when `_word_filters` found the word ambiguous.
SALES_AGENT = rf.FieldSpec(
    name="sales_agent", noun="sales agent", question="Which sales agent?", resolve=lambda _db, _word, _extras: rf.Resolved("unknown"),
    allow_all=False, required=False, pick_head="Which sales agent? Reply with a number:",
)

def _company_question(extras: dict[str, Any]) -> str:
    from app.api.v1.sales.analysis import company_question

    names = [str(o[1]) for o in (extras.get("company_options") or []) if isinstance(o, (list, tuple)) and len(o) == 2]
    return company_question(names) if len(names) > 1 else "Which company?"


#: A company the message named that the contact does not hold: said plainly, nothing runs (never run without it).
COMPANY_FORBIDDEN_LINE = "You do not have access to that company."


def _company_held(extras: dict[str, Any], values: dict[str, Any], args: dict[str, Any], held: dict[str, Any]) -> dict[str, Any]:
    """`held` with the company question brought back while it is still owed: the first message found the company
    unnamed (its options ride the slot's extras) and neither an answer nor a named company has settled it."""
    options = extras.get("company_options")
    if not options or "company" in values or args.get("company"):
        return held
    return {**held, "company": rf.Resolved("ambiguous", options=tuple((str(o[0]), str(o[1])) for o in options))}


#: REPORT-UNIFY phase 3 (R1): a contact in two companies who names neither and no product or customer is asked "<A> or
#: <B>?" (the SALES-COMPANY rule, `sales_company_ask`). A field of this ask, so every filter the message named rides the
#: slot to the answer. Never required: it is a field only when the lane found the company unnamed.
COMPANY = rf.FieldSpec(
    name="company", noun="company", question="Which company?", question_fn=_company_question,
    resolve=lambda _db, _word, _extras: rf.Resolved("unknown"), allow_all=False, required=False, pick_head_is_question=True,
)

SALES_RANKING_ASK = rf.register(rf.AskType(
    name=ASK_NAME,
    fields=(PERIOD, TOP_N, METRIC, BASIS, COMPANY, SALES_AGENT),
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
_FILTER_HINTS = frozenset({"customer", "product", "brand", "category", "sales_agent", "warehouse", "specification"})
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
    axis = _PICK_AXIS.get(getattr(pending, "kind", None) or "")
    if axis is None or jsc.js_string(verdict.get("group_by") or "").strip().lower() != axis:
        return verdict
    answer = verdict.get("open_question_answer") if isinstance(verdict.get("open_question_answer"), dict) else {}
    picked = answer.get("mode") == "pick" and bool(jsc.array(answer.get("picked")))
    if not (picked or jsc.array(verdict.get("reference_positions"))):
        return verdict
    return {**verdict, "group_by": None}


def by_capability(verdict: dict[str, Any], *, subject: bool = False, seam: bool = True) -> dict[str, Any]:
    """Engine seam, before grounding (REPORT-SMART-1021 step 2, REPORT-UNIFY Q1; `seam=False` is `run_fetch`'s own
    pass over what the seam left, which lets a pick or a document through): every sales figure ask
    (`SALES_STATUSES`, any axis the report ask has or none) and every outstanding ask that holds a filter or an
    axis (`as_outstanding`) is a sales ranking, read whole by `settle`: its filters, period, count, metric and
    basis, with every missing one asked in one numbered reply. A breakdown (no count, no direction, from a kind
    that is not a ranking) lists every row. Parser fields only; anything else is unchanged."""
    # Engine keys only this seam writes: never taken from the parser's own emission.
    verdict = {k: v for k, v in verdict.items() if k not in CAPABILITY_KEYS}
    status = jsc.js_string(verdict.get("order_status") or "").strip()
    if verdict.get("intent_hint") == "low_stock_report" and verdict.get("domain_hint") == "inventory":
        return verdict  # the reorder report is its own ask (`low_stock_ask`), whatever order status the parser also read
    if status == "top_selling":
        return from_top_selling(verdict)
    answer = verdict.get("open_question_answer") if isinstance(verdict.get("open_question_answer"), dict) else {}
    if seam and (
        (answer.get("mode") == "pick" and jsc.array(answer.get("picked"))) or jsc.array(verdict.get("reference_positions"))
    ):
        return verdict  # a pick of a position on an open roster answers it, whatever report type the parser also read
    if seam and jsc.array(verdict.get("document")):
        # The parser read an order DOCUMENT (an SO / DO list ask): the so_status seams decide it from the words; an
        # outstanding or sales report status it carried with it is converted later, at `run_fetch` (`seam=False`),
        # if it stands.
        return verdict
    if status in OUTSTANDING_STATUSES:
        return as_outstanding(verdict, subject=subject)
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
    words: dict[str, list[str]] = {hint: [] for hint in WORD_HINTS}
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
        if hint in WORD_HINTS:
            # AC-HT8-12, REPORT-UNIFY slice 3 (plan 3.2): the word the parser BOUND the mention to, a candidate's
            # label or its row id, before the verbatim raw; the raw is read only when it bound nothing.
            raw = " ".join(jsc.js_string(e.get("canonical_code") or "").split()) or raw
        if hint not in WORD_HINTS:
            kept.append(e)
            continue
        if raw and e.get("current_message") is not False and raw not in words[hint]:
            words[hint].append(raw)
    return {**verdict, "entities": kept, "report_ask_words": words, "report_ask_spec": specs}


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
    if group_by not in (None, "month"):
        return dict(values)
    return {k: v for k, v in values.items() if k != "top_n" and not (k == "metric" and not _dict(v).get("value"))}


#: REPORT-SMART-L R8: the engine's stamp (`with_held`), frame-shaped (`date_from`, `date_to`, the route params), plus
#: `product` when the held products are the gate's carried rows. Listed in `required_fields.ENGINE_KEYS`.
HELD_KEY = "report_held"
#: The route params of a held total that stay on the ranking its reply becomes: the period and the filters.
_HELD_TOTAL_KEYS = (
    "date_from", "date_to", "product_code", "product_ids", "brand_ids", "category_ids", "customer_ids",
    "sales_agent_ids", "customer_agent_ids", "channel", "spec", "warehouse_codes", "company",
)
#: REPORT-SMART-L R9: the open question a sales report reply arms with its drill offer (`fetch._sales_report_output`),
#: so the engine-held sign that the last answer was a sales report (`contracts.DETAIL_OFFER_KINDS`).
SALES_REPORT_OFFER = "sales_report_detail"
#: The bases `crm_sales_report` answers: delivered only (none named is that report's own figure).
_SALES_REPORT_BASES = (None, "delivered")


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

    On only when the parser reuses the held subject (`entity_op` reuse, no topic reset, no `new_subject` op), the
    verdict is a ranking (R9: an axis-less one too, which runs the total), no ranking frame is held (a held one
    keeps its own rules: refine, S6b, ruling B, stale), the last ask was a sales figure, and no open ask is being
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
    if (
        jsc.js_string(verdict.get("order_status") or "").strip() != ASK_NAME
        or verdict.get("entity_op") != "reuse"
        or verdict.get("topic_reset") is True
        or _new_subject(verdict, parser_ops)
        or _dict(getattr(focus, "sales_ranking_frame", None)).get("group_by")
        or contracts.SALES_DOMAIN not in (domains or [])
        or (open_ask is not None and replaced is None)
    ):
        return verdict
    axisless = not jsc.js_string(typed_group_by(verdict).get("group_by") or "").strip()
    if axisless and verdict.get("top_n") is not None:
        # AC-OR9: a typed count keeps the ranking. With no axis there is no total to hold it (a total settles no
        # count), so neither the carry nor the reroute applies: the reply is today's.
        return verdict
    if replaced is None and verdict.get("top_n") is None and verdict.get("bare_top_selling") is True:
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
    elif _dict(getattr(focus, "sales_ranking_frame", None)):
        # A held TOTAL (a report ask run with no axis): its period and filters stay (what that total showed).
        total = _dict(getattr(focus, "sales_ranking_frame", None))
        held = {k: v for k, v in total.items() if k in _HELD_TOTAL_KEYS and v not in (None, "", [])}
    else:
        window = _dict(getattr(focus, "date_window", None))
        held = {"date_from": window.get("start"), "date_to": window.get("end"), "product": bool(getattr(focus, "products", None))}
        held = {k: v for k, v in held.items() if v}
    return {**verdict, HELD_KEY: held} if held else verdict


def dealer_location_words(parse_output: dict[str, Any]) -> dict[str, Any]:
    """Engine seam, a DEALER's (customer-scoped) fresh `sales_ranking` ask, 1b fix round F1:
    this message's location words come off the resolver's entity list onto
    `report_ask_words["warehouse"]`, so no warehouse code is ever looked up for a dealer;
    the lane refuses the ask off the word alone."""
    if jsc.js_string(parse_output.get("order_status") or "").strip() != ASK_NAME or parse_output.get("required_ask"):
        return parse_output
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
    from app.services.reports.ask import DEALER_KEYS

    words = _dict(parse_output.get("report_ask_words"))
    named = any(
        " ".join(jsc.js_string(w).split())
        for hint in ("sales_agent", "warehouse")
        for w in jsc.array(words.get(hint))
    )
    return (
        (group_by is not None and group_by not in DEALER_KEYS)
        or named
        or bool(_current_entities(parse_output, "warehouse"))
        or parse_output.get("sales_channel") in ("dealer", "project")
    )


_WORD_PARAMS = (("brand", "brand_ids"), ("sales_agent", "sales_agent_ids"), ("category", "category_ids"))


def _bound_by_id(db: Any, hint: str, word: str) -> tuple[list[str], list[str]] | None:
    """`(ids, names)` of the brand / sales agent / category row whose id the parser echoed (the candidate line's
    `[id: ...]`); None when the word is not an id at all (it is a label or a raw word)."""
    from app.services.chatbot.lanes.business.fetch import is_uuid

    if db is None or not is_uuid(word):
        return None
    from app.models.product import Brand, ProductCategory
    from app.models.sales_agent import SalesAgent

    model, name_col = {
        "brand": (Brand, "brand_name"), "sales_agent": (SalesAgent, "sales_agent"), "category": (ProductCategory, "category_name"),
    }[hint]
    row = db.query(model).filter(model.id == word).first()
    return ([str(row.id)], [str(getattr(row, name_col) or "")]) if row is not None else ([], [])


def _word_filters(
    db: Any, parse_output: dict[str, Any], pairs: tuple[tuple[str, str], ...] = _WORD_PARAMS, *,
    agent_filter: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    """The brand / sales agent / category ids the verdict's `report_ask_words` resolve to, or
    the one line to say instead. Shared by a fresh ask and a ranking refine."""
    out: dict[str, Any] = {}
    words = _dict(parse_output.get("report_ask_words"))
    for hint, param in pairs:
        ids: list[str] = []
        for word in jsc.array(words.get(hint)):
            word = " ".join(jsc.js_string(word).split())
            if not word:
                continue
            bound = _bound_by_id(db, hint, word)
            if bound is not None:
                if not bound[0]:
                    return None, f"I don't know that {WORD_HINTS[hint]}."
                ids.extend(i for i in bound[0] if i not in ids)
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
                    return None, f"I don't know '{word}' as a {WORD_HINTS[hint]}."
                if ambiguous:
                    listed = ", ".join(sorted(set(ambiguous)))
                    return None, f"'{word}' matches several {SEVERAL_NOUNS[hint]}: {listed}. Ask again naming one."
                ids.extend(i for i in found if i not in ids)
                continue
            if hint == "sales_agent" and word.casefold() == jsc.js_string(parse_output.get("sales_channel") or "").casefold():
                continue  # the channel word the verdict already set (`sales_channel`), not a person
            found, names = _resolve_word(db, hint, word)
            if not found:
                return None, f"I don't know '{word}' as a {WORD_HINTS[hint]}."
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
        if ids:
            out[param] = ids
    return out, None


def _product_args(entities: Any, *, total: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    """The route's product param for the product entities a message named, or the one line to
    say instead. 1b code review S4: the sales report's PREFIX rule (S19), so "SRT5674" covers
    "SRT5674-N"; several codes travel as the prefix they share."""
    from app.services.chatbot.lanes.business.fetch import (
        is_mixed_code_set,
        outstanding_product_codes,
        sales_report_product_code,
    )

    products = [e for e in jsc.array(entities) if isinstance(e, dict) and e.get("entity_type") == "product"]
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
    db: Any, parse_output: dict[str, Any], entities: Any, *, dealer: bool = False, agent_filter: bool = True
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

    filters, line = _word_filters(db, parse_output, agent_filter=agent_filter)
    if filters is None:
        return None, line
    args.update(filters)

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
    customer_ids = _gate_ids(entities, "customer") if "customer" in kinds else []
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
        product_args, line = _product_args(_without_carried_products(parse_output, entities), total=not group_by)
        if product_args is None:
            return None, line
        args.update(product_args)

    if jsc.array(parse_output.get("report_ask_spec")):
        args["spec"] = [jsc.js_string(t) for t in jsc.array(parse_output["report_ask_spec"])]

    codes: list[str] = []
    for e in _current_entities(parse_output, "warehouse"):
        token = jsc.js_string(e.get("raw") or e.get("canonical_code") or "").strip()
        if not token:
            continue
        found = business_services.resolve_warehouse_token(db, token) if db is not None else []
        if not found:
            return None, f"I don't know '{token}' as a location."
        codes.extend(c for c in found if c not in codes)
    if codes:
        args["warehouse_codes"] = codes
    return args, None


#: The keys `_fresh_args` always sets (or an axis); any other key it sets is a filter.
_NON_FILTER_ARGS = frozenset({"basis", "measure", "sort", "group_by", "compare_to", "mine", "company"})


def _given_top_n(args: dict[str, Any], top_n: Any) -> dict[str, Any]:
    """The number as the helper's `given`: a total needs none (settled as None, never
    asked); a number the first message named is taken, or read as a word (a miss)."""
    if not args.get("group_by"):
        return {"top_n": rf.Resolved("ok", value=None, label="")}
    got = top_n_from(top_n)
    if args.get("group_by") == "month" and got.status != "ok":
        return {"top_n": rf.Resolved("ok", value=MONTH_TOP_N, label=str(MONTH_TOP_N))}
    if top_n is None:
        return {}
    return {"top_n": got if got.status == "ok" else jsc.js_string(top_n)}


def _given_choices(args: dict[str, Any]) -> dict[str, Any]:
    """The metric and the basis as the helper's `given`, off the args a message named. A total
    and a month trend show both measures, so they are never asked the metric (settled as None);
    the basis is always asked unless named. Anything not named is left out, so it is asked."""
    given: dict[str, Any] = {}
    if not args.get("group_by") or args.get("group_by") == "month":
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


def settle(
    db: Any, parse_output: dict[str, Any], entities: Any, *, dealer: bool = False, agent_filter: bool = True,
    companies: Any = (),
) -> tuple[rf.Outcome | None, str | None]:
    """`_settle`, with the company question asked as the one line `sales_company_ask` asks on the Yearly path (one
    question, one wording); the slot keeps its numbered options, so a number or a name still answers it."""
    outcome, line = _settle(db, parse_output, entities, dealer=dealer, agent_filter=agent_filter, companies=companies)
    if outcome is not None and outcome.slot and outcome.slot.get("asking") == "company" and outcome.reply:
        outcome.reply = _company_question(_dict(outcome.slot.get("extras")))
    company = _dict(outcome.values.get("company")) if outcome is not None else {}
    if company.get("value") == rf.ALL and outcome is not None:
        # Two unreadable answers to the company question: a plain give-up, never a run (the route would 403 "all").
        word = str(company.get("missed") or "that")
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
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME and slot.get("asking") == "scope":
        return _scope_answer(db, parse_output, slot), None
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME:
        extras = _dict(slot.get("extras"))
        args = _dict(extras.get("args"))
        held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
        held = _company_held(extras, _dict(slot.get("values")), args, held)
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
            held = _company_held(extras, _dict(slot.get("values")), args, held)
            if args.get("group_by") != _dict(extras.get("args")).get("group_by") and _dict(extras.get("args")).get("group_by") in (None, "month"):
                # What a total or a month trend settled on its own (no count, both measures) is not
                # what the new axis owes: the new axis's rules (`held`) decide, typed values stay.
                slot = {**slot, "values": _settled_by_its_axis(_dict(slot.get("values")), _dict(extras.get("args")).get("group_by"))}
            slot, args = _reply_wins(parse_output, slot, args)
            held = {**_given_choices(args), **_given_top_n(args, extras.get("top_n"))}
            held = _company_held(extras, _dict(slot.get("values")), args, held)
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
            held = _company_held(extras, _dict(slot.get("values")), args, held)
            again = rf.collect(db, SALES_RANKING_ASK, slot=slot, given=held, extras={"args": args})
            if again.slot:
                again.slot["misses"] = 1
            return again, None
        reply_dates = {"start": parse_output.get("date_filter_start"), "end": parse_output.get("date_filter_end")}
        outcome = rf.collect(
            db,
            SALES_RANKING_ASK,
            slot=slot,
            reply=jsc.js_string(parse_output.get("required_ask_reply") or ""),
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
            values = {**outcome.values, "top_n": {"value": DEFAULT_TOP_N, "label": str(DEFAULT_TOP_N)}}
            return rf.Outcome(values=values, extras={**outcome.extras, "note": DEFAULT_TOP_N_NOTE}), None
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
        return _refine(db, parse_output, frame, entities, dealer=dealer)
    if drill == "scoped":
        # Owner ruling B (23 Oct): only the parser's `scoped` narrows to the rows on screen. A new axis
        # read as global, unsure or not at all runs across all (below), and the header says so.
        drilled = _drill(db, parse_output, frame, entities, reading=drill, dealer=dealer)
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
    elif not _dict(frame).get("group_by") and _dict(parse_output.get(HELD_KEY)):
        # R8: no ranking held, and the engine stamped what the held sales report total (or the open ask this
        # replaced) showed (`with_held`): the same hold, one more source. A total has no rows to rank across, so
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
        # A brand, category or sales agent filter on screen is held too (the new axis's own filter is not).
        held_filters = {
            k: source[k] for k in ("brand_ids", "category_ids", "sales_agent_ids")
            if source.get(k) and k not in _AXIS_FILTERS.get(axis, ())
        }
        holding = True
        parse_output = {**parse_output, "ranking_refine": False}

    args, line = _fresh_args(db, parse_output, entities, dealer=dealer, agent_filter=agent_filter)
    if args is None:
        return None, line
    named = {
        jsc.js_string(e.get("hint") or "").strip().lower()
        for e in jsc.array(parse_output.get("entities"))
        if isinstance(e, dict) and e.get("current_message") is not False
    } & _FILTER_HINTS
    if named and parse_output.get("capability_from") and not set(args) - _NON_FILTER_ARGS and not held_product:
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
        for key in ("measure", "basis"):
            if not args.get(key) and source.get(key):
                args[key] = source[key]
    if (
        parse_output.get("ranking_refine") is not True
        and not dealer  # the route forces a dealer's links, so a plain total can never widen
        and not args.get("group_by")
        and not set(args) - _NON_FILTER_ARGS
        and not parse_output.get("capability_from")  # a sales / outstanding total with no filter is the company's own
    ):
        # Not a valid ask: no axis and nothing to total. Say what can be ranked and open nothing.
        return None, CATALOGUE_LINE
    top_n = parse_output.get("top_n")
    if top_n is None and holding and source.get("top_n"):
        top_n = source["top_n"]  # S6c: the count on screen stays
    if top_n is None and parse_output.get("report_breakdown") is True and args.get("group_by"):
        top_n = BREAKDOWN_TOP_N  # a breakdown lists every row (`by_capability`)
    if args.get("compare_to") and args.get("group_by") == "month":
        return None, COMPARE_BY_MONTH_LINE
    given = {**_given_choices(args), **_given_top_n(args, top_n)}
    agent_pick = args.pop("sales_agent_pick", None)
    if agent_pick:
        given["sales_agent"] = rf.Resolved("ambiguous", options=tuple((i, str(n)) for i, n in agent_pick))
    company_options: list[list[str]] = []
    own = [c for c in jsc.array(companies) if isinstance(c, (list, tuple)) and len(c) == 3]
    if own and not dealer and parse_output.get("ranking_refine") is not True:
        # R1: the company the message (the parser's `sales_company`) names, among the contact's own; else, with two or
        # more companies and no named subject (a customer, product, brand, category, agent or spec), the company question.
        said = " ".join(jsc.js_string(parse_output.get("sales_company") or "").split()).casefold()
        named = next((c for c in own if said and said in (str(c[1]).casefold(), str(c[2]).casefold())), None)
        if named is None and said:
            return None, COMPANY_FORBIDDEN_LINE  # the message named a company the contact does not hold
        if named is not None:
            args["company"] = str(named[0])
        elif len(own) > 1 and not any(
            args.get(k) for k in ("customer_ids", "product_code", "product_ids", "brand_ids", "category_ids", "sales_agent_ids", "spec")
        ):
            given["company"] = rf.Resolved("ambiguous", options=tuple((str(c[0]), str(c[1])) for c in own))
            company_options = [[str(c[0]), str(c[1])] for c in own]
    if (
        parse_output.get("capability_from") == "outstanding"
        and args.get("basis") in OUTSTANDING_KINDS
        and not args.get("group_by")
    ):
        # An outstanding TOTAL that named its kind shows both measures (no "by quantity or by amount?"); a ranking by an
        # axis still asks what it ranks by (phase 3, S5).
        given["metric"] = rf.Resolved("ok", value=args.get("measure"), label=args.get("measure") or "")
    period = period_from(parse_output.get("date_filter_start"), parse_output.get("date_filter_end")) or held_period
    if period is not None and (parse_output.get("ranking_refine") is not True or args.get("group_by")):
        # A refine with no ranking held has nothing to refine: it is a fresh ask, and a
        # period alone never runs a total (it asks). One that names its own axis (R5 row 7) keeps its period.
        given["period"] = period
    extras: dict[str, Any] = {"args": args, "top_n": top_n}
    if company_options:
        extras["company_options"] = company_options
    if parse_output.get("capability_from") == "outstanding":
        extras["kind_ask"] = True  # the basis question is the three kinds (Q2)
    if period is None and (args.get("basis") in OUTSTANDING_KINDS or extras.get("kind_ask")):
        # An outstanding kind takes no period: none named means every date (the route's own reading).
        given["period"] = rf.Resolved("ok", value={"from": None, "to": None}, label="all dates")
    if across_all and frame.get("group_by") in AXIS_NOUNS and _drill_source(frame):
        # Owner ruling B: after a ranking, a new axis runs across all, and the header line says so.
        extras["note"] = f"Across all {AXIS_NOUNS[frame['group_by']][1]}"
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras=extras), None


def _widened(parse_output: dict[str, Any]) -> str | None:
    """The one held axis the parser widened to "all" this turn (`broaden_axis` with `broaden_to`
    "all", template R-P3-09): the hold drops it and keeps the rest. Parser fields only."""
    if parse_output.get("broaden_to") != "all":
        return None
    axis = jsc.js_string(parse_output.get("broaden_axis") or "").strip().lower()
    return axis if axis in ("channel", "product") else None


def _refine(
    db: Any, parse_output: dict[str, Any], frame: dict[str, Any], entities: Any = (), *, dealer: bool = False
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
        ):
            return None, DEALER_REFUSAL
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
    filters, line = _word_filters(db, parse_output, (("brand", "brand_ids"), ("category", "category_ids")))
    if filters is None:
        return None, line
    args.update(filters)
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
    if parse_output.get("compare_to") in COMPARE_TO:
        args["compare_to"] = parse_output["compare_to"]
    if parse_output.get("self_reference") is True:
        args["mine"] = True
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
        if name not in given:
            given[name] = rf.Resolved("ok", value=args.get(key), label=args.get(key) or "")
    if period is not None:
        given["period"] = period
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras={"args": args, "top_n": top_n}), None


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
    dealer: bool = False,
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
    own, line = _fresh_args(db, parse_output, entities, dealer=dealer)
    if own is None:
        return None, line
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
    scoped = _branch(args, top_n, period, held=True)
    if unsure:
        # One question, nothing runs. The slot holds BOTH readings, so the reply only has to
        # say which ("the agents above" / "all"); its axis, count and period are the slot's.
        question = _unsure_line(group_by, parse_output.get("top_n"), source, len(rows))
        scope = {
            "question": question,
            "source": source,
            "scoped": scoped,
            "global": _branch(own, parse_output.get("top_n"), own_period, held=False),
        }
        slot = {"ask": ASK_NAME, "values": {}, "asking": "scope", "options": [], "misses": 0,
                "extras": {"scope": scope}}
        return rf.Outcome(values={}, reply=question, slot=slot), None
    return _collect_branch(db, scoped), None


def _branch(args: dict[str, Any], top_n: Any, period: rf.Resolved | None, *, held: bool) -> dict[str, Any]:
    """One reading of a ranking, kept as plain data (it may wait in a slot): its args, count,
    period, and whether its metric and basis are the held ranking's (never asked again)."""
    return {
        "args": args,
        "top_n": top_n,
        "period": {"value": period.value, "label": period.label} if period is not None else None,
        "held": held,
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
    return rf.collect(db, SALES_RANKING_ASK, given=given, extras={"args": args, "top_n": top_n})


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
    company = _dict(outcome.values.get("company")).get("value")
    if company and company != rf.ALL:
        args["company"] = str(company)  # the company the person chose
    agent = _dict(outcome.values.get("sales_agent")).get("value")
    if agent:
        args["sales_agent_ids"] = [str(agent)]  # the agent the person picked
    return args


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
    {"customer", "product", "brand", "category", "product_type", "sales_agent", "warehouse", "specification", "spec"}
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
