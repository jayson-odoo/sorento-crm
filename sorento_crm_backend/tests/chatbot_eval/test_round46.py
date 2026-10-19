"""EVAL-BENCH round 46: the pre-registered certification rule (pooled score, per-item majority, flip rate,
x1 go/no-go, early stop) and the parser flip count. Synthetic rows only.

Grade rows carry `item_id` (targets.grade_turn). Recorded live rows are `{"item_id", "turn": {"trace": [...]}}`
with the parser output at the `understood` record's `raw.parser_raw`.
"""
from __future__ import annotations

import pytest

from scripts.chatbot_eval import targets
from scripts.chatbot_eval.targets import summarise


def parser_flips(runs_rows):
    return targets.parser_flips(runs_rows)


def g(item, passed, slice_="s", kind=None):
    return {"item_id": item, "slice": slice_, "kind": kind, "passed": passed, "reason": "r", "checks": {},
            "leaks": [], "made_up": []}


def run(slice_, verdicts):
    return [g(f"i{k}", v, slice_) for k, v in enumerate(verdicts)]


BARS = {"s": 0.9}


# ---------------------------------------------------------------- A pooled
def test_pooled_is_total_over_total_not_mean_of_rates():
    runs = [run("s", [True] * 10), run("s", [False] * 1 + [True] * 0), run("s", [True] * 10)]
    st = summarise(runs, BARS)["slices"]["s"]
    assert st["pooled"] == 20 / 21
    assert st["rate"] != st["pooled"]          # mean of rates is (1 + 0 + 1) / 3


def test_meets_uses_pooled_not_rate():
    runs = [run("s", [True] * 10), run("s", [False]), run("s", [True] * 10)]
    out = summarise(runs, {"s": 0.9})
    assert out["slices"]["s"]["rate"] < 0.9 <= out["slices"]["s"]["pooled"]
    assert out["meets"] is True


def test_unknown_is_out_of_pooled():
    runs = [run("s", [True, None]), run("s", [True, None]), run("s", [True, None])]
    assert summarise(runs, BARS)["slices"]["s"]["pooled"] == 1.0


# ---------------------------------------------------------------- B majority
def test_majority_counts_and_known_in_one_run_exclusion():
    runs = [
        [g("a", True), g("b", False), g("c", True), g("d", True)],
        [g("a", True), g("b", False), g("c", False), g("d", None)],
        [g("a", True), g("b", True), g("c", False), g("d", None)],
    ]
    st = summarise(runs, BARS)["slices"]["s"]
    assert st["majority_n"] == 3        # d is known in one run only
    assert st["majority_pass"] == 1     # a passes 3/3; b 1/3; c 1/3


def test_majority_needs_more_than_half():
    runs = [[g("a", True)], [g("a", False)]]
    st = summarise(runs, BARS)["slices"]["s"]
    assert st["majority_n"] == 1 and st["majority_pass"] == 0


def test_rows_without_id_are_skipped_and_counted():
    noid = {**g("z", True), "item_id": None}
    runs = [[g("a", True), dict(noid)], [g("a", True), dict(noid)], [g("a", True), dict(noid)]]
    st = summarise(runs, BARS)["slices"]["s"]
    assert st["majority_n"] == 1 and st["no_id"] == 3


# ---------------------------------------------------------------- C flips
def test_flip_count_and_rate():
    runs = [
        [g("a", True), g("b", True), g("c", False)],
        [g("a", True), g("b", False), g("c", False)],
        [g("a", True), g("b", True), g("c", False)],
    ]
    st = summarise(runs, BARS)["slices"]["s"]
    assert st["flips"] == 1 and st["flip_rate"] == 1 / 3


# ---------------------------------------------------------------- D x1 go/no-go
def test_fewer_than_three_runs_is_go_no_go_only():
    out = summarise([run("s", [True] * 10)], BARS)
    assert out["meets"] is False and "at least 3 runs" in out["reason"]
    assert out["slices"]["s"]["go"] is True
    assert "certified" not in out["slices"]["s"] and "certified" not in out
    low = summarise([run("s", [True] * 5 + [False] * 5)], BARS)
    assert low["slices"]["s"]["go"] is False


def test_three_runs_have_no_go_key():
    out = summarise([run("s", [True] * 10)] * 3, BARS)
    assert out["meets"] is True and "go" not in out["slices"]["s"]


# ---------------------------------------------------------------- E early stop
def test_stopped_slice_shows_no_percentage_and_fails_meets():
    runs = [run("s", [True] * 10) for _ in range(3)] + []
    runs = [r + run("t", [True] * 4) for r in runs]
    out = summarise(runs, {"s": 0.9, "t": 0.9}, stopped={"t": 0.8})
    t = out["slices"]["t"]
    assert t["status"] == "stopped" and t["best_reachable"] == 0.8
    for key in ("rate", "pooled", "majority_pass", "majority_n", "flips", "lowest"):
        assert key not in t
    assert out["meets"] is False


def test_stopped_unbarred_slice_does_not_fail_meets():
    runs = [run("s", [True] * 10) + run("t", [True]) for _ in range(3)]
    out = summarise(runs, {"s": 0.9}, stopped={"t": 0.5})
    assert out["slices"]["t"]["status"] == "stopped" and out["meets"] is True


# ---------------------------------------------------------------- F parser flips
def prow(item, **parsed):
    return {"item_id": item, "turn": {"trace": [{"stage": "routed"},
                                                 {"stage": "understood", "raw": {"parser_raw": parsed}}]}}


BASE = dict(domain_hint="inventory", routing={"suggested_team": "warehouse", "suggested_agent": "a"},
            asks=[{"domain": "inventory", "intent": "check_stock"}],
            entities=[{"raw": "ab1", "hint": "product", "spec_key": None}],
            state_changes=[{"op": "refine", "axis": "brand", "position": 1}])


def test_identical_signatures_do_not_flip():
    out = parser_flips([[prow("a", **BASE)], [prow("a", **BASE)], [prow("a", **BASE)]])
    assert out == {"items": 1, "flipped": 0, "rate": 0.0, "fields": {}, "no_parse": 0, "no_id": 0, "dup_rows": 0,
                   "partial_parse": 0, "parse_failed": 0, "parse_capped": 0, "parse_missing": 0}


def test_state_change_op_difference_flips_that_field():
    other = {**BASE, "state_changes": [{"op": "carry", "axis": "brand", "position": 1}]}
    out = parser_flips([[prow("a", **BASE)], [prow("a", **other)]])
    assert out["items"] == 1 and out["flipped"] == 1 and out["rate"] == 1.0
    assert out["fields"] == {"state_changes": 1}


def test_ask_order_and_entity_order_do_not_flip():
    shuffled = {**BASE, "asks": [{"domain": "x", "intent": "y"}, *BASE["asks"]],
                "entities": [{"raw": "z", "hint": "p"}, *BASE["entities"]]}
    a = {**shuffled, "asks": list(reversed(shuffled["asks"])), "entities": list(reversed(shuffled["entities"]))}
    assert parser_flips([[prow("a", **shuffled)], [prow("a", **a)]])["flipped"] == 0


def test_missing_understood_counts_no_parse_and_single_run_items_are_skipped():
    bare = {"item_id": "b", "turn": {"trace": [{"stage": "routed"}]}}
    out = parser_flips([[prow("a", **BASE), bare, prow("only", **BASE)], [prow("a", **BASE), bare]])
    assert out["items"] == 1 and out["no_parse"] == 1 and out["flipped"] == 0


# ---------------------------------------------------------------- guards (behaviour already in place)
def _changed(field):
    b = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in BASE.items()}
    if field == "domain_hint":
        b["domain_hint"] = "order"
    elif field == "routing_team":
        b["routing"] = {**b["routing"], "suggested_team": "purchasing"}
    elif field == "routing_agent":
        b["routing"] = {**b["routing"], "suggested_agent": "b"}
    elif field == "ask":
        b["asks"] = [{"domain": "inventory", "intent": "check_po"}]
    elif field == "entity_raw":
        b["entities"] = [{**b["entities"][0], "raw": "cd2"}]
    elif field == "entity_hint":
        b["entities"] = [{**b["entities"][0], "hint": "customer"}]
    elif field == "entity_spec_key":
        b["entities"] = [{**b["entities"][0], "spec_key": "colour"}]
    elif field == "state_op":
        b["state_changes"] = [{**b["state_changes"][0], "op": "carry"}]
    return b


@pytest.mark.parametrize("field,reported", [
    ("domain_hint", "domain_hint"), ("routing_team", "routing"), ("routing_agent", "routing"), ("ask", "asks"),
    ("entity_raw", "entities"), ("entity_hint", "entities"), ("entity_spec_key", "entities"),
    ("state_op", "state_changes")])
def test_each_signature_field_flips_alone(field, reported):
    out = parser_flips([[prow("a", **BASE)], [prow("a", **_changed(field))]])
    assert out["flipped"] == 1 and out["fields"] == {reported: 1}


def test_go_uses_pooled_not_rate():
    # run 1: 1 of 1 passes; run 2: 8 of 10 pass. rate = (1 + 0.8) / 2 = 0.9, pooled = 9/11 = 0.818
    out = summarise([run("s", [True]), run("s", [True] * 8 + [False] * 2)], {"s": 0.85})
    st = out["slices"]["s"]
    assert st["rate"] >= 0.85 > st["pooled"] and st["go"] is False
    # run 1: 0 of 1; run 2: 10 of 10. rate = 0.5, pooled = 10/11 = 0.909
    out = summarise([run("s", [False]), run("s", [True] * 10)], {"s": 0.85})
    st = out["slices"]["s"]
    assert st["rate"] < 0.85 <= st["pooled"] and st["go"] is True


def test_duplicate_rows_in_one_run_pass_only_if_all_known_passed():
    r1 = [g("a", True), g("a", False)]   # all -> fail; any -> pass; last -> fail
    r2 = [g("a", False), g("a", True)]   # all -> fail; any -> pass; last -> pass
    r3 = [g("a", True), g("a", True)]    # pass
    st = summarise([r1, r2, r3], BARS)["slices"]["s"]
    assert st["majority_n"] == 1 and st["majority_pass"] == 0 and st["flips"] == 1


def test_stopped_barred_slice_with_fewer_than_three_runs():
    out = summarise([run("s", [True] * 10)], {"s": 0.9}, stopped={"s": 0.5})
    assert out["slices"]["s"] == {"status": "stopped", "best_reachable": 0.5}
    assert out["meets"] is False


def test_unreadable_parse_is_no_parse_not_a_crash():
    def with_raw(item, raw):
        return {"item_id": item, "turn": {"trace": [{"stage": "understood", "raw": raw}]}}
    rows = [with_raw("a", "payload omitted: 9 bytes exceeds cap"), with_raw("b", {"parser_raw": None}),
            with_raw("c", {"parser_raw": "truncated..."}), with_raw("d", None)]
    out = parser_flips([rows, rows])
    assert out["items"] == 0 and out["flipped"] == 0 and out["no_parse"] == 4


def test_item_parsed_in_some_runs_is_not_no_parse():
    bare = {"item_id": "a", "turn": {"trace": []}}
    out = parser_flips([[bare], [prow("a", **BASE)], [prow("a", **BASE)]])
    assert out["items"] == 1 and out["no_parse"] == 0


# ---------------------------------------------------------------- round 46 review fixes
def test_parser_flips_skips_rows_without_an_id():
    row = {"item_id": None, "turn": {"trace": []}}
    out = parser_flips([[row, prow("a", **BASE)], [row, prow("a", **BASE)]])
    assert out["no_id"] == 2 and out["items"] == 1 and out["no_parse"] == 0


def test_repeated_item_id_in_a_run_counts_once_first_row_wins():
    other = {**BASE, "domain_hint": "order"}
    out = parser_flips([[prow("a", **BASE), prow("a", **other)], [prow("a", **BASE)]])
    assert out["dup_rows"] == 1 and out["items"] == 1 and out["flipped"] == 0


def _understood(item, rec):
    return {"item_id": item, "turn": {"trace": [{"stage": "understood", **rec}]}}


def test_partial_parse_is_split_into_failed_and_capped_and_not_flipped():
    failed = _understood("f", {"status": "failed", "raw": {"parser_raw": None}})
    capped = _understood("c", {"raw": "payload omitted: 9 bytes exceeds cap"})
    out = parser_flips([[prow("f", **BASE), prow("c", **BASE)], [failed, capped], [prow("f", **BASE), prow("c", **BASE)]])
    assert out["partial_parse"] == 2 and out["parse_failed"] == 1 and out["parse_capped"] == 1
    assert out["no_parse"] == 0 and out["flipped"] == 0 and out["items"] == 2


def test_entity_raw_is_normalised_and_spec_value_joins_the_tuple():
    spaced = {**BASE, "entities": [{"raw": "  AB1 ", "hint": "product", "spec_key": None}]}
    wide = {**BASE, "entities": [{"raw": "ab1", "hint": "product", "spec_key": None}]}
    assert parser_flips([[prow("a", **wide)], [prow("a", **spaced)]])["flipped"] == 0
    two = {**BASE, "entities": [{"raw": "ab  1", "hint": "product", "spec_key": None}]}
    assert parser_flips([[prow("a", **spaced)], [prow("a", **two)]])["flipped"] == 1
    v1 = {**BASE, "entities": [{"raw": "ab1", "hint": "product", "spec_key": "colour", "spec_value": "red"}]}
    v2 = {**BASE, "entities": [{"raw": "ab1", "hint": "product", "spec_key": "colour", "spec_value": "blue"}]}
    out = parser_flips([[prow("a", **v1)], [prow("a", **v2)]])
    assert out["fields"] == {"entities": 1}


def test_go_needs_a_known_verdict_in_every_run():
    runs = [run("s", [True] * 10), run("s", [None] * 3)]
    out = summarise(runs, {"s": 0.9})
    assert out["slices"]["s"]["pooled"] == 1.0 and out["slices"]["s"]["go"] is False


def test_stopped_slice_shows_no_rate_under_growth_either():
    runs = [[g("a", True, "s"), {**g("b", True, "gs"), "growth": True}] for _ in range(3)]
    out = summarise(runs, {"s": 0.9}, stopped={"gs": 0.4})
    assert out["growth"]["gs"] == {"status": "stopped", "best_reachable": 0.4}


def test_status_failed_record_is_a_failed_parse_even_with_parser_raw():
    failed = _understood("a", {"status": "failed", "raw": {"parser_raw": BASE}})
    out = parser_flips([[prow("a", **BASE)], [failed], [prow("a", **BASE)]])
    assert out["parse_failed"] == 1 and out["partial_parse"] == 1


# ---------------------------------------------------------------- round 46 fix round 2
def test_a_real_capped_record_is_parse_capped():
    from app.services.chatbot.trace import _cap
    big = {"parser_raw": {"pad": "x" * 40000}, "derived": {}}
    capped = _cap(big)
    assert isinstance(capped, dict) and capped["note"].startswith("payload omitted")
    whole = {"item_id": "a", "turn": {"trace": [{"stage": "understood", "status": "ok", "raw": capped}]}}
    inner = {"item_id": "b", "turn": {"trace": [{"stage": "understood", "raw": {"parser_raw": _cap({"pad": "x" * 40000})}}]}}
    out = parser_flips([[prow("a", **BASE), prow("b", **BASE)], [whole, inner], [prow("a", **BASE), prow("b", **BASE)]])
    assert out["parse_capped"] == 2 and out["parse_failed"] == 0 and out["partial_parse"] == 2


def test_an_empty_recording_is_parse_missing_not_parse_failed():
    empty = {"item_id": "a", "turn": {"trace": []}}
    out = parser_flips([[prow("a", **BASE)], [empty], [prow("a", **BASE)]])
    assert out["parse_missing"] == 1 and out["parse_failed"] == 0 and out["parse_capped"] == 0
    assert out["partial_parse"] == 1
