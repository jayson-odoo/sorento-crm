"""The SUPPLIER-ASK sweep script's own grading and pricing (no DB, no network)."""
from decimal import Decimal

from scripts import sweep_supplier_ask as sweep


def test_the_sweep_holds_at_least_24_phrasings_covering_every_axis():
    texts = [t.text for c in sweep.CASES for t in c.turns]
    assert len(sweep.CASES) >= 24
    repeat = [c for c in sweep.CASES if c.name.startswith("owner-turn1-repeat-")]
    assert len(repeat) == 5 and {c.turns[0].text for c in repeat} == {"outstaing for 太阳 for SRTW2600 after 2025"}
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


def test_tool_events_read_the_flat_trace_shape():
    """Crew round 4: `TurnTrace.add` keeps `name` / `args` beside `kind`; reading `payload` graded every PO turn as
    'no PO list'."""
    trace = [
        {"kind": "tool", "at": 1, "name": sweep.PO_TOOL, "args": {"supplier_ids": ["a"]}},
        {"kind": "tool", "payload": {"name": "crm_report_ask", "args": {}}},
        {"stage": "understood", "facts": {}},
    ]
    assert sweep._tool_events(trace) == [(sweep.PO_TOOL, {"supplier_ids": ["a"]}), ("crm_report_ask", {})]


def test_a_gemini_model_is_priced_from_the_seed_prices_not_the_flat_fallback():
    from app.services.analytics_connector.prices import SEED_PRICES

    prices = {m: (Decimal(i), Decimal(c or i), Decimal(o)) for m, (i, c, o, _n) in SEED_PRICES.items()}
    assert sweep._price_of("models/gemini-3.5-flash-lite", prices) == prices["gemini-3.5-flash-lite"]
    assert sweep._price_of("gemini-3.5-flash-lite-preview-10-2026", prices) == prices["gemini-3.5-flash-lite"]
    calls = [{"model": "gemini-3.5-flash-lite", "prompt": 50_000, "completion": 500, "cached": 0}]
    assert sweep._usd(calls, prices, Decimal("0.01")) == Decimal("0.01625")


def test_turn_cost_goes_through_the_model_name_rules():
    """Review round 4 (M8c): `_usd` prices a `models/` id through `_price_of`."""
    prices = {"gemini-3.5-flash-lite": (Decimal("0.30"), Decimal("0.03"), Decimal("2.50"))}
    calls = [{"model": "models/gemini-3.5-flash-lite", "prompt": 1_000_000, "completion": 0, "cached": 0}]
    assert sweep._usd(calls, prices, Decimal("9")) == Decimal("0.30")


def test_the_price_table_carries_the_seed_prices_under_the_db_rows():
    """Review round 4 (M8d): a copy whose table has no Gemini row still prices Gemini from the seed list; a DB row wins."""

    class _Db:
        def execute(self, *_a, **_k):
            class _R:
                def all(self):
                    return [("gpt-5.4-mini", Decimal("1"), None, Decimal("2"))]

            return _R()

    table = sweep._price_table(_Db())
    assert table["gemini-3.5-flash-lite"] == (Decimal("0.30"), Decimal("0.03"), Decimal("2.50"))
    assert table["gpt-5.4-mini"] == (Decimal("1"), Decimal("1"), Decimal("2"))
