"""EVAL-BENCH round 46: the pre-registered certification rule (pooled score, per-item majority, flip rate,
x1 go/no-go, early stop) and the parser flip count. Synthetic rows only.

Grade rows carry `item_id` (targets.grade_turn). Recorded live rows are `{"item_id", "turn": {"trace": [...]}}`
with the parser output at the `understood` record's `raw.parser_raw`.
"""
from __future__ import annotations

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
    assert out == {"items": 1, "flipped": 0, "rate": 0.0, "fields": {}, "no_parse": 0}


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
