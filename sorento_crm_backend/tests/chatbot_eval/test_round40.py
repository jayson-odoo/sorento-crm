"""EVAL-BENCH round 40 grader misfires: no_picker, tool_target, applied, and the trace cap class (tier ask, asked_type).

`test_red_*` fail on the round 38 grader; `test_guard_*` pass before and after (a real failure still fails).
Synthetic rows only: they copy the SHAPE of the events, never an item, message, reply or code of a real row.
"""
from __future__ import annotations

from scripts.chatbot_eval.targets import grade_turn
from tests.chatbot_eval.test_targets import GOLD_TS, _att, _file, item
from tests.chatbot_eval.test_targets_v2 import TOOL_A, UA, UB, row2, prod, _with_oq

OMITTED = "payload omitted: 33331 bytes exceeds the 32768 byte cap"
U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
U2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
U3 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _kind_rec(r, kind):
    return next(rec for rec in r["trace"] if rec.get("kind") == kind)


# ------------------------------------------------------------------ 1. no_picker: a did-you-mean for a held code not on file
DYM = {"kind": "product_pick", "expects": "choice", "payload": {}, "asked_at_turn": 5,
       "options": [{"label": "SRTZ90-A", "code": "SRTZ90-A"}, {"label": "SRTZ90-B", "code": "SRTZ90-B"}]}
TIER = {"kind": "tier_pick", "expects": "choice", "payload": {}, "asked_at_turn": 4,
        "options": [{"label": "Dealer"}, {"label": "End user"}]}


SUGGEST = {"head": "Did you mean:", "rows": [{"code": "SRTZ90-A", "entity_type": "product"},
                                              {"code": "SRTZ90-B", "entity_type": "product"}]}


def _dym_row(unresolved=("SRTZ99",), held=("SRTZ99",), after=DYM):
    held_recs = [{"raw": h, "hint": "product", "uuid": None, "canonical_code": None} for h in held]
    r = row2(reply="Did you mean one of these?", mem_before=held_recs, mem_after=held_recs,
             oq={"before": TIER, "after": after, "writer": "engine"},
             looked=[{"tool": None, "unresolved": list(unresolved), "product_codes": list(unresolved),
                      "unresolved_suggestions": {c: SUGGEST for c in unresolved}}])
    return r


GOLD_ANS = dict(option="dealer", options=["Dealer", "End user"])


def test_red_1_a_did_you_mean_for_an_unresolved_held_code_is_not_a_picker_failure():
    res = grade_turn(_dym_row(), item("followup", "answer", **GOLD_ANS))
    assert res["checks"]["no_picker"] is True, res["checks"]


def test_guard_1_a_picker_with_nothing_unresolved_still_fails():
    res = grade_turn(_dym_row(unresolved=()), item("followup", "answer", **GOLD_ANS))
    assert res["checks"]["no_picker"] is False, res["checks"]


def test_red_1_a_picker_for_the_other_held_code_still_fails():
    other = dict(DYM, options=[{"label": "SRTY10-A", "code": "SRTY10-A"}, {"label": "SRTY10-B", "code": "SRTY10-B"}])
    res = grade_turn(_dym_row(held=("SRTZ99", "SRTY10"), after=other), item("followup", "answer", **GOLD_ANS))
    assert res["checks"]["no_picker"] is False, res["checks"]
    ok = grade_turn(_dym_row(held=("SRTZ99", "SRTY10")), item("followup", "answer", **GOLD_ANS))
    assert ok["checks"]["no_picker"] is True, ok["checks"]


def test_guard_1_an_unresolved_code_that_was_not_held_still_fails():
    res = grade_turn(_dym_row(unresolved=("SRTQ11",)), item("followup", "answer", **GOLD_ANS))
    assert res["checks"]["no_picker"] is False, res["checks"]


# ------------------------------------------------------------------ 2a. tool_target: a picked customer named by a fragment
CUST_Q = {"kind": "customer_pick", "expects": "choice", "payload": {}, "asked_at_turn": 3,
          "options": [{"label": "Acmeco Sdn Bhd", "name": "Acmeco Sdn Bhd", "code": "300-A1", "uuid": U1, "uuids": [U1, U2]},
                      {"label": "Zenco Sdn Bhd", "name": "Zenco Sdn Bhd", "code": "300-Z1", "uuid": U3, "uuids": [U3]}]}
GOLD_PICK = dict(position=1, code="ACMECO")


def _cust_row(ids):
    return row2(reply="Nothing outstanding.", oq={"before": CUST_Q, "after": None, "writer": "engine"}, pick=[1],
                tools=[{"name": "crm_outstanding_report", "args": {"customer_ids": list(ids), "view": "render"}}])


def test_red_2a_a_picked_customer_is_seen_through_the_options_that_name_its_ids():
    res = grade_turn(_cust_row([U1, U2]), item("followup", "pick", **GOLD_PICK))
    assert res["checks"]["tool_target"] is True, res["checks"]


SAME_NAME_Q = {"kind": "customer_pick", "expects": "choice", "payload": {}, "asked_at_turn": 3,
               "options": [{"label": "Acmeco Sdn Bhd", "name": "Acmeco Sdn Bhd", "code": "300-A1", "uuid": U1, "uuids": [U1]},
                           {"label": "Acmeco Holdings", "name": "Acmeco Holdings", "code": "300-A2", "uuid": U2, "uuids": [U2]}]}


def _same_name_row(ids):
    return row2(reply="Nothing outstanding.", oq={"before": SAME_NAME_Q, "after": None, "writer": "engine"}, pick=[1],
                tools=[{"name": "crm_outstanding_report", "args": {"customer_ids": list(ids), "view": "render"}}])


def test_red_2a_a_lookup_to_another_option_that_matches_the_fragment_fails():
    wrong = grade_turn(_same_name_row([U2]), item("followup", "pick", **GOLD_PICK))
    assert wrong["checks"]["tool_target"] is False, wrong["checks"]
    right = grade_turn(_same_name_row([U1]), item("followup", "pick", **GOLD_PICK))
    assert right["checks"]["tool_target"] is True, right["checks"]
    both = grade_turn(_same_name_row([U1, U2]), item("followup", "pick", **GOLD_PICK))
    assert both["checks"]["tool_target"] is False, both["checks"]


def test_guard_2a_ids_of_another_customer_still_fail():
    res = grade_turn(_cust_row([U3]), item("followup", "pick", **GOLD_PICK))
    assert res["checks"]["tool_target"] is False, res["checks"]
    res = grade_turn(_cust_row([U1, U3]), item("followup", "pick", **GOLD_PICK))
    assert res["checks"]["tool_target"] is False, res["checks"]


def test_guard_2a_ids_no_option_names_still_fail():
    res = grade_turn(_cust_row([UB]), item("followup", "pick", **GOLD_PICK))
    assert res["checks"]["tool_target"] is False, res["checks"]


# ------------------------------------------------------------------ 2b. tool_target: the period question fetches nothing
def _period_row(range_event=True):
    r = row2(reply="Which period for the customer?", oq={"before": CUST_Q, "after": None, "writer": "engine"}, pick=[1])
    if range_event:
        r["trace"].append({"kind": "do_range", "asked": "Which period?"})
    return r


def test_red_2b_the_period_question_after_a_customer_pick_is_unknown_not_wrong():
    res = grade_turn(_period_row(), item("followup", "pick", **GOLD_PICK))
    assert res["checks"]["tool_target"] is None, res["checks"]


def test_guard_2b_no_tool_and_no_question_still_fails():
    res = grade_turn(_period_row(range_event=False), item("followup", "pick", **GOLD_PICK))
    assert res["checks"]["tool_target"] is False, res["checks"]


# ------------------------------------------------------------------ 3. applied: a brand narrowing over the held family
GOLD_BRAND = dict(subject_after=["SRTA100-P"], filter={"kind": "brand", "value": "acme"})


def _brand_row(*, brands=1, specs=(), matched=("SRTA100-P",), event=True):
    r = row2(verdict={"entities": [], "reference_positions": []}, mem_before=[prod("SRTA100-P", UA)],
             mem_after=[prod("SRTA100-P", UA)], tools=[TOOL_A])
    if event:
        r["trace"].append({"kind": "held_family", "held": 1, "family": 1, "brands": brands,
                           "matched": list(matched), "specs": [list(s) for s in specs]})
    return r


def test_red_3_a_brand_narrowing_over_the_held_family_counts_as_applied():
    res = grade_turn(_brand_row(), item("followup", "refine", **GOLD_BRAND))
    assert res["checks"]["applied"] is True, res["checks"]


def test_guard_3_matches_not_looked_up_are_not_applied():
    res = grade_turn(_brand_row(matched=("SRTA999",)), item("followup", "refine", **GOLD_BRAND))
    assert res["checks"]["applied"] is False, res["checks"]


def test_guard_3_no_brand_in_the_event_is_not_applied():
    res = grade_turn(_brand_row(brands=0), item("followup", "refine", **GOLD_BRAND))
    assert res["checks"]["applied"] is False, res["checks"]


def test_guard_3_a_brand_event_does_not_apply_a_spec_filter():
    gold = dict(subject_after=["SRTA100-P"], filter={"kind": "spec", "value": "p trap"})
    res = grade_turn(_brand_row(), item("followup", "refine", **gold))
    assert res["checks"]["applied"] is False, res["checks"]


# ------------------------------------------------------------------ 4a. the tier ask after a capped memory event
GOLD_CODE = dict(code="SRTA100", fact="inventory")


def _tier_row(*, state_oq="absent", asking="tier_pick"):
    r = row2(message="stock of srta100", reply="Which access level do you need?", mem_after=[], tools=[])
    for i, rec in enumerate(r["trace"]):
        if rec.get("kind") == "memory":
            r["trace"][i] = {"kind": "memory", "note": OMITTED}   # the live shape: the whole payload is capped out
        if rec.get("kind") == "state":
            if state_oq == "absent":
                r["trace"][i] = {"kind": "state", "note": OMITTED}
            else:
                rec["open_question"] = state_oq
        if rec.get("stage") == "replied":
            rec["facts"]["asking"] = asking
    return r


def test_red_4a_a_tier_ask_is_read_from_the_uncapped_state_when_memory_is_capped():
    res = grade_turn(_tier_row(state_oq=TIER), item("code_lookup", **GOLD_CODE))
    assert res["passed"] is None, (res["passed"], res["checks"])


def test_red_4a_with_no_uncapped_source_a_failure_beside_an_ask_is_unknown():
    res = grade_turn(_tier_row(), item("code_lookup", **GOLD_CODE))
    assert res["passed"] is None, (res["passed"], res["checks"])


def test_guard_4a_capped_memory_and_no_ask_still_fails():
    res = grade_turn(_tier_row(asking=None), item("code_lookup", **GOLD_CODE))
    assert res["passed"] is False, (res["passed"], res["checks"])


def test_red_4a_a_leak_beside_an_unreadable_tier_ask_stays_a_failure():
    r = _tier_row()
    r["response"]["reply"]["text"] = f"Which access level for {UA}?"
    res = grade_turn(r, item("code_lookup", **GOLD_CODE))
    assert res["passed"] is False and "internal id" in res["reason"], (res["passed"], res["reason"])


def test_guard_4a_a_readable_state_with_no_question_stays_a_failure_even_with_a_tier_ask_flag():
    res = grade_turn(_tier_row(state_oq=None, asking="tier_pick"), item("code_lookup", **GOLD_CODE))
    assert res["passed"] is False, (res["passed"], res["checks"])


def test_guard_4a_an_uncapped_memory_with_a_tier_ask_flag_stays_a_failure():
    r = row2(message="stock of srta100", reply="Which access level do you need?", mem_after=[], tools=[],
             oq={"before": None, "after": None, "writer": None})
    for rec in r["trace"]:
        if rec.get("stage") == "replied":
            rec["facts"]["asking"] = "tier_pick"
    res = grade_turn(r, item("code_lookup", **GOLD_CODE))
    assert res["passed"] is False, (res["passed"], res["checks"])


def test_guard_4a_an_uncapped_state_with_no_question_still_fails():
    res = grade_turn(_tier_row(state_oq=None, asking=None), item("code_lookup", **GOLD_CODE))
    assert res["passed"] is False, (res["passed"], res["checks"])


# ------------------------------------------------------------------ 4b. asked_type when the apply payload is capped
def _capped_apply(r, entities):
    for i, rec in enumerate(r["trace"]):
        if rec.get("kind") == "apply":
            r["trace"][i] = {"kind": "apply", "note": OMITTED}
        if rec.get("stage") == "understood":
            rec["raw"] = {"derived": {"entities": entities}, "parser_raw": {}} if entities is not None else {}
    return r


TYPE_ENT = {"raw": "drawing", "hint": "attachment_type", "canonical_code": "technical_specifications", "confident": True}


def test_red_4b_asked_type_is_read_from_the_parser_entities_when_apply_is_capped():
    r = _capped_apply(_att([_file("Technical Specifications")]), [TYPE_ENT])
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["asked_type"] is True, res["checks"]


def test_red_4b_derived_entities_without_a_tool_carrying_the_type_ids_are_unknown():
    r = _capped_apply(_att([_file("Technical Specifications")]), [TYPE_ENT])
    for rec in r["trace"]:
        if rec.get("kind") == "tool":
            rec["args"] = {"product_ids": ["x"]}
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["asked_type"] is None, res["checks"]


def test_guard_4b_a_readable_apply_needs_no_tool_ids():
    r = _att([_file("Technical Specifications")])
    for rec in r["trace"]:
        if rec.get("kind") == "tool":
            rec["args"] = {"product_ids": ["x"]}
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["asked_type"] is True, res["checks"]


def test_guard_4b_a_parser_entity_of_another_type_still_fails():
    other = dict(TYPE_ENT, canonical_code="product_photos", raw="photo")
    r = _capped_apply(_att([_file("Technical Specifications")]), [other])
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["asked_type"] is False, res["checks"]


def test_red_4b_capped_apply_and_no_parser_entities_is_unknown():
    r = _capped_apply(_att([_file("Technical Specifications")]), None)
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["asked_type"] is None, res["checks"]


def test_guard_4b_a_readable_apply_with_no_type_entity_still_fails():
    r = _att([_file("Technical Specifications")])
    for rec in r["trace"]:
        if rec.get("kind") == "apply":
            rec["verdict"]["entities"] = []
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["asked_type"] is False, res["checks"]
