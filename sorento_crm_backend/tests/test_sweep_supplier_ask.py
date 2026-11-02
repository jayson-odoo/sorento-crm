"""The SUPPLIER-ASK sweep script's own grading and pricing (no DB, no network)."""
from decimal import Decimal

from scripts import sweep_supplier_ask as sweep


def test_the_sweep_holds_at_least_24_phrasings_covering_every_axis():
    texts = [t.text for c in sweep.CASES for t in c.turns]
    assert len(sweep.CASES) >= 24
    for needle in ("太阳", "taiyng", "SRTW2600", "after 2025", "in 2026", "March", "all", "both", "400-X008", "1 and 3"):
        assert any(needle in t for t in texts), needle
    assert any("order" in t for t in texts) and any("PO" in t for t in texts) and any("outstanding" in t for t in texts)


def test_a_list_without_a_supplier_filter_fails_whatever_was_expected():
    turn = sweep.Turn("outstanding for taiyang", "miss")
    assert sweep._grade(turn, "Here is the PO placed I found.", [(sweep.PO_TOOL, {})], True)[0] == "FAIL"
    assert sweep._grade(turn, "x", [("crm_report_ask", {"basis": "outstanding"})], True)[0] == "FAIL"
    assert sweep._grade(sweep.Turn("stock SRTW2600", "not_po"), "x", [("crm_inventory_stock_balance_list", {})], False)[0] == "PASS"


def test_ask_po_and_window_grading():
    ask = sweep.Turn("outstanding for taiyang", "ask")
    assert sweep._grade(ask, "Which one do you mean?\n1. A (X1)\n2. B (X2)", [], True)[0] == "PASS"
    po = sweep.Turn("all", "po:3", "2026-01-01")
    args = {"supplier_ids": ["a", "b", "c"], "expected_date_from": "2026-01-01"}
    assert sweep._grade(po, "x", [(sweep.PO_TOOL, args)], True)[0] == "PASS"
    assert sweep._grade(po, "x", [(sweep.PO_TOOL, {**args, "expected_date_from": "2025-01-01"})], True)[0] == "FAIL"


def test_turn_cost_reads_every_token_block_and_charges_unpriced_calls():
    trace = [
        {"stage": "understood", "facts": {"model": "m1", "prompt_tokens": 1_000_000, "completion_tokens": 0, "cached_tokens": 0}},
        {"kind": "span_extract", "payload": {"model": "m2", "tokens": {"prompt_tokens": 10, "completion_tokens": 0}}},
    ]
    calls = sweep._token_calls(trace)
    assert [c["model"] for c in calls] == ["m1", "m2"]
    usd = sweep._usd(calls, {"m1": (Decimal("0.10"), Decimal("0.01"), Decimal("0.40"))}, Decimal("0.01"))
    assert usd == Decimal("0.11")


def test_the_order_kind_clarifier_is_not_the_supplier_question_and_a_miss_runs_no_list():
    KIND_QUESTION = "Undelivered orders or pending delivery?"  # `report_ask.KIND_QUESTION`, the owner's turn-4 reply

    ask = sweep.Turn("outstaing for 太阳 for SRTW2600 in 2026", "ask")
    assert sweep._grade(ask, f"{KIND_QUESTION}\n1. Undelivered orders\n2. Pending delivery", [], True)[0] == "FAIL"
    assert sweep._grade(ask, "Which one?\n1. A (X1)", [(sweep.PO_TOOL, {"supplier_ids": ["a"]})], True)[0] == "FAIL"
    miss = sweep.Turn("outstanding PO for zzqqxx supplier", "miss")
    assert sweep._grade(miss, "x", [(sweep.PO_TOOL, {"supplier_ids": ["a"]})], True)[0] == "FAIL"
    assert sweep._grade(miss, "Sorry, I couldn't find a supplier called \"zzqqxx\".", [], True)[0] == "PASS"


def test_the_cap_stops_before_a_turn_that_would_pass_it():
    cap, floor = Decimal("0.50"), Decimal("0.01")
    assert not sweep._cap_reached(Decimal("0"), Decimal("0"), floor, cap)
    assert not sweep._cap_reached(Decimal("0.48"), Decimal("0.02"), floor, cap)
    assert sweep._cap_reached(Decimal("0.48"), Decimal("0.03"), floor, cap)
    assert sweep._cap_reached(Decimal("0.495"), Decimal("0"), floor, cap), "an unpriced turn still costs the floor"


def test_cached_tokens_are_priced_at_the_cached_rate():
    calls = [{"model": "m1", "prompt": 1_000_000, "completion": 0, "cached": 500_000}]
    usd = sweep._usd(calls, {"m1": (Decimal("0.10"), Decimal("0.02"), Decimal("0.40"))}, Decimal("0.01"))
    assert usd == Decimal("0.06")
