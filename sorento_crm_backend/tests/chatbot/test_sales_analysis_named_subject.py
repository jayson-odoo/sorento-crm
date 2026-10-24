"""CHAT-PICK-QTY-STATE round 2, item 3: a sales_analysis parse that names a product or a
customer THIS message runs the sales report for that subject (red tests, test-first).

Live (gpt-5.4-mini, prompt v63): "b2155-nl-blue dealer sales september 2026" sometimes parses
as `order_status: sales_analysis` WITH the product entity. The company analysis has no product
or customer filter, so after "Sorento or Mocha?" it answers the whole company's dealer total
under a product question. The same message parsed as `sales_report` runs `crm_sales_report`
for the product, which is the right answer.

Rule: the code picks the tool from the parser's params. An entity of hint product / customer
with `current_message` true makes a sales_analysis parse a sales report of that subject.

* N1 (AC-9, two companies) the X2 parse runs `crm_sales_report`, no analysis, no question.
* N2 (AC-9, one company) the same.
* N3 (parity) the report args equal those of the sales_report parse of the same message.
* N4 (AC-10) a customer named this message: the same class.
* G5 (AC-11) no entity: the company question as today.
* G6 (AC-11) a CARRIED product (current_message false) never reroutes.
* G7 the company question's answering turn still runs the analysis for the picked company.

Harness: `test_sales_analysis_company_pick` (real `engine.run_turn`, Postgres, parser, access,
resolver and MCP faked).
"""
from __future__ import annotations

from typing import Any

from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_sales_analysis_company_pick import (  # noqa: F401  (fixtures)
    ANALYSIS, PRODUCT_CODE, PRODUCT_RAW, PRODUCT_UUID, QUESTION, REPORT, SEP_2026,
    _calls, _pick, _reply, _turn_a, one, two,
)

TEXT = "b2155-nl-blue dealer sales september 2026"
#: The resolver is asked about the punctuation-free token in the parser's own case (measured).
X2_MATCH = {"B2155NLBLUE": {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}}
CUSTOMER_UUID = "c0570000-0000-4000-8000-00000000c057"
CUSTOMER_MATCH = {"hanlim": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": "300-H070"}}


def _x2(order_status: str = "sales_analysis", entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The X2 parse, field for field, as the parser emitted it live."""
    if entities is None:
        entities = [{
            "raw": "B2155-NL-BLUE", "hint": "product", "account": None, "quantity": None,
            "spec_key": None, "confident": True, "spec_value": None, "canonical_code": None,
            "hint_confident": None, "current_message": True,
        }]
    return _parser_output(
        message_type="business_query", intent_hint="check_order", domain_hint="sales",
        order_status=order_status, entities=entities, entity_op="replace_combine",
        sales_channel="dealer", sales_basis=None, sales_company=None, scope_intent="specific",
        open_question_answer={"mode": None, "items": [], "picked": [], "qty_for_all": None},
        **SEP_2026,
    )


def _customer(current: bool = True) -> dict[str, Any]:
    return {"raw": "hanlim", "hint": "customer", "canonical_code": None, "current_message": current, "confident": True}


def _assert_report(result: Any, captured: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    assert _calls(captured, ANALYSIS) == [], f"a named subject never runs the company analysis: {captured}"
    calls = _calls(captured, REPORT)
    assert calls, f"the named subject must run the sales report: {captured}"
    assert QUESTION not in _reply(result), f"no company question for a named subject: {_reply(result)!r}"
    return calls[0]


def _assert_dealer_sep(args: dict[str, Any]) -> None:
    assert args.get("channel") == "dealer", args
    assert args.get("date_from") == "2026-09-01" and args.get("date_to") == "2026-09-30", args


# --------------------------------------------------------------------------- #
# N1 - N4 (RED)
# --------------------------------------------------------------------------- #


def test_n1_a_sales_analysis_parse_naming_a_product_runs_the_report_two_companies(two):
    result, captured = two.say(_x2(), TEXT, matches=X2_MATCH)
    args = _assert_report(result, captured)
    assert args.get("product_code") == PRODUCT_CODE, args
    _assert_dealer_sep(args)
    assert two.next_open_question() is None or QUESTION not in str(two.next_open_question()), (
        f"no company question may be left open: {two.next_open_question()}"
    )


def test_n2_a_sales_analysis_parse_naming_a_product_runs_the_report_one_company(one):
    result, captured = one.say(_x2(), TEXT, matches=X2_MATCH)
    args = _assert_report(result, captured)
    assert args.get("product_code") == PRODUCT_CODE, args
    _assert_dealer_sep(args)


def test_n3_the_report_args_equal_those_of_the_sales_report_parse(two):
    _r, captured_report = two.say(_x2("sales_report"), TEXT, matches=X2_MATCH)
    expected = _calls(captured_report, REPORT)
    assert expected, f"setup: the sales_report parse runs the report: {captured_report}"
    _r, captured = two.say(_x2("sales_analysis"), TEXT, matches=X2_MATCH)
    got = _calls(captured, REPORT)
    assert got and got[0] == expected[0], f"same args as the sales_report parse: {got} vs {expected}"
    assert _calls(captured, ANALYSIS) == [], captured


def test_n4_a_sales_analysis_parse_naming_a_customer_runs_the_report_for_it(two):
    text = "hanlim dealer sales september 2026"
    _r, setup = two.say(_x2("sales_report", [_customer()]), text, matches=CUSTOMER_MATCH)
    assert _calls(setup, REPORT) and _calls(setup, REPORT)[0].get("customer_ids") == [CUSTOMER_UUID], (
        f"setup: the sales_report parse resolves the customer: {setup}"
    )
    result, captured = two.say(_x2(entities=[_customer()]), text, matches=CUSTOMER_MATCH)
    args = _assert_report(result, captured)
    assert args.get("customer_ids") == [CUSTOMER_UUID], args
    _assert_dealer_sep(args)


# --------------------------------------------------------------------------- #
# G5 - G7 (GREEN guards)
# --------------------------------------------------------------------------- #


def test_g5_no_named_subject_is_still_the_company_question(two):
    result, captured = two.say(_x2(entities=[]), "dealer sales september 2026")
    assert QUESTION in _reply(result), _reply(result)
    assert _calls(captured, REPORT) == [], captured


def test_g6_a_carried_product_never_reroutes(two):
    """The engine turn: the verdict itself carries the product with `current_message` false."""
    _r, captured_a = two.say(_turn_a(), "b2155-nl-blue sales 2026")
    assert _calls(captured_a, REPORT), f"setup: turn A runs the product report: {captured_a}"
    carried = [{
        "raw": PRODUCT_RAW, "hint": "product", "canonical_code": None,
        "current_message": False, "confident": True,
    }]
    result, captured = two.say(_x2(entities=carried), "dealer sales september 2026", matches=X2_MATCH)
    assert _calls(captured, REPORT) == [], f"a carried product never reroutes: {captured}"
    assert QUESTION in _reply(result) or _calls(captured, ANALYSIS), (captured, _reply(result))


def test_g7_the_answer_to_the_company_question_still_runs_the_analysis(two):
    result, _c = two.say(_x2(entities=[]), "dealer sales september 2026")
    assert QUESTION in _reply(result), _reply(result)
    qf = _parser_output(
        message_type="business_query", intent_hint=None, domain_hint=None, entities=[],
        entity_op="reuse", domain_in_message=False, open_question_answer=_pick(1),
    )
    _result, captured = two.say(qf, "Sorento")
    calls = _calls(captured, ANALYSIS)
    assert calls and calls[0].get("company") == "Sorento", captured
    assert _calls(captured, REPORT) == [], captured


# --------------------------------------------------------------------------- #
# B1 / S1 (RED) - the named subject reaches the report through a picker and a re-hint
# --------------------------------------------------------------------------- #

from tests.chatbot.test_sales_analysis_company_pick import _pick  # noqa: E402
from tests.chatbot.test_new_ask_drops_sales_channel import (  # noqa: E402,F401  (fixture)
    CUSTOMER_UUID_1, _ambiguous_customer_services, _report_calls, chat,
)


def _ambiguous_turn_1(order_status: str) -> dict[str, Any]:
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status=order_status,
        sales_channel="dealer", domain_in_message=True, entity_op="replace_combine",
        entities=[{"raw": "zz demo", "hint": "customer", "canonical_code": None,
                   "current_message": True, "confident": True}],
    )


def _pick_1() -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[],
        reference_positions=[1], reference_target="dym", entity_op="reuse", order_status=None,
    )


def _ambiguous_then_pick(chat, order_status: str, tag: str):
    _r1, captured1 = chat(
        _ambiguous_turn_1(order_status), "dealer sales for zz demo", f"ZZT-nsub-{tag}-1",
        resolve_services=_ambiguous_customer_services(),
    )
    assert _report_calls(captured1) == [] and not _calls(captured1, ANALYSIS), captured1
    assert (chat.session().get("open_question") or {}).get("kind") == "customer_pick", (
        "setup: the customer picker must be armed", chat.session().get("open_question"),
    )
    return chat(_pick_1(), "1", f"ZZT-nsub-{tag}-2")


def test_b1_parity_the_sales_report_parse_picks_into_the_report(chat):
    _r, captured = _ambiguous_then_pick(chat, "sales_report", "par")
    calls = _report_calls(captured)
    assert calls and calls[0].get("customer_ids") == [CUSTOMER_UUID_1], captured
    assert calls[0].get("channel") == "dealer", calls[0]


def test_b1_an_ambiguous_customer_on_a_sales_analysis_parse_picks_into_the_report(chat):
    _r, captured = _ambiguous_then_pick(chat, "sales_analysis", "b1")
    assert _calls(captured, ANALYSIS) == [], f"the pick never runs the company analysis: {captured}"
    calls = _report_calls(captured)
    assert calls and calls[0].get("customer_ids") == [CUSTOMER_UUID_1], captured
    assert calls[0].get("channel") == "dealer", calls[0]


def test_s1_a_customer_hinted_word_that_is_a_product_renders_the_report(one):
    matches = {"Srt5674N": {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": "SRT5674-N"}}
    word = [{"raw": "Srt5674-N", "hint": "customer", "canonical_code": None,
             "current_message": True, "confident": True}]
    text = "dealer Srt5674-N sales september 2026"
    _r, setup = one.say(_x2("sales_report", word), text, matches=matches)
    assert _calls(setup, REPORT), f"setup: the sales_report parse renders the report: {setup}"
    result, captured = one.say(_x2("sales_analysis", word), text, matches=matches)
    assert _calls(captured, REPORT), f"the report must run: {captured}"
    assert "matched" not in _reply(result).lower() and "escalate" not in _reply(result).lower(), _reply(result)


# --------------------------------------------------------------------------- #
# Kind picker and did-you-mean picker (RED): the answer keeps the asking turn's subject kind
# --------------------------------------------------------------------------- #

from app.services.chatbot.lanes.business.services import ResolveGateServices  # noqa: E402
from tests.chatbot.conftest import validating_resolve_entity  # noqa: E402

_U1, _U2 = "c0570000-0000-4000-8000-000000000001", "c0570000-0000-4000-8000-000000000002"


def _one_token_services(resolution: dict[str, Any], *, unresolved: bool) -> ResolveGateServices:
    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["zz demo"], "resolutions": [resolution],
            "unresolved_tokens": ["zz demo"] if unresolved else [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve),
        probe=lambda **_: {"items": [], "has_result": False},
    )


def _kind_services() -> ResolveGateServices:
    """One word that is both a customer and a product: the engine asks which kind."""
    match = lambda kind, uuid, code: {  # noqa: E731
        "entity_type": kind, "canonical_code": code, "uuid": uuid, "company_code": "SRT",
        "display": {"customer_name": code},
    }
    return _one_token_services(
        {"token": "zz demo", "matches": [match("customer", _U1, "ZZ A"), match("product", _U2, "ZZ B")]},
        unresolved=False,
    )


def _dym_services() -> ResolveGateServices:
    """A customer word that is no customer but has two near ones: the did-you-mean pick."""
    alts = [{"canonical_code": f"ZZDEMO{i}", "uuid": u, "entity_type": "customer"} for i, u in ((1, _U1), (2, _U2))]
    return _one_token_services(
        {"token": "zz demo", "resolved": False, "matches": [], "alternatives": alts}, unresolved=True
    )


def _picker_turn_1(order_status: str, confident: bool, hint: str = "customer") -> dict[str, Any]:
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status=order_status,
        sales_channel="dealer", domain_in_message=True, entity_op="replace_combine",
        entities=[{"raw": "zz demo", "hint": hint, "canonical_code": None,
                   "current_message": True, "confident": confident}],
    )


def _picker_then_pick(chat, services, order_status: str, kind: str, confident: bool, tag: str):
    hint = "product" if kind == "kind_pick" else "customer"
    chat(_picker_turn_1(order_status, confident, hint), "dealer sales for zz demo", f"ZZT-nsub-{tag}-1",
         resolve_services=services())
    assert (chat.session().get("open_question") or {}).get("kind") == kind, (
        f"setup: the {kind} must be armed", chat.session().get("open_question"),
    )
    answer = _pick_1() if kind != "kind_pick" else _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], entity_op="reuse",
        order_status=None, open_question_answer=_pick(2),  # the kind picker lists customer, then product
    )
    extra = {"resolve_services": services()} if kind == "kind_pick" else {}
    return chat(answer, "1", f"ZZT-nsub-{tag}-2", **extra)


def test_kind_picker_parity_the_sales_report_parse_picks_into_the_report(chat):
    _r, captured = _picker_then_pick(chat, _kind_services, "sales_report", "kind_pick", False, "kpar")
    calls = _report_calls(captured)
    assert calls and calls[0].get("product_code") == "ZZ B", captured


def test_kind_picker_answer_on_a_sales_analysis_parse_runs_the_report(chat):
    _r, captured = _picker_then_pick(chat, _kind_services, "sales_analysis", "kind_pick", False, "kpick")
    assert _calls(captured, ANALYSIS) == [], f"the kind pick never runs the company analysis: {captured}"
    calls = _report_calls(captured)
    assert calls and calls[0].get("product_code") == "ZZ B", captured
    assert calls[0].get("channel") == "dealer", calls[0]


def test_did_you_mean_parity_the_sales_report_parse_picks_into_the_report(chat):
    _r, captured = _picker_then_pick(chat, _dym_services, "sales_report", "customer_pick", True, "dpar")
    calls = _report_calls(captured)
    assert calls and calls[0].get("customer_ids") == [_U1], captured


def test_did_you_mean_answer_on_a_sales_analysis_parse_runs_the_report(chat):
    _r, captured = _picker_then_pick(chat, _dym_services, "sales_analysis", "customer_pick", True, "dpick")
    assert _calls(captured, ANALYSIS) == [], f"the did-you-mean pick never runs the company analysis: {captured}"
    calls = _report_calls(captured)
    assert calls and calls[0].get("customer_ids") == [_U1], captured
    assert calls[0].get("channel") == "dealer", calls[0]
