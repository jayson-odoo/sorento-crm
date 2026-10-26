"""Phase 2 RED tests - the sales target reply text (lane SALES-TARGET-CHAT, slice 1).

UAC T3-1b, T3-2 .. T3-7. The bodies under `tests/fixtures/sales_target/` are the route's contract
shape (PLAN-sales-target-chat-25oct.md "Contract"); the expected lines are the UAC's / card's own.
Written before `crm_sales_target_progress` is wired into `present_response`: the generic envelope
runs instead and carries no `response`, so every assertion fails on that, not on a crash.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from sorento_crm_mcp.http_client import http_error_body
from sorento_crm_mcp.presenters import present_response

_FIXTURES = Path(__file__).parent / "fixtures" / "sales_target"
TOOL = "crm_sales_target_progress"


def _body(name: str) -> dict:
    return json.loads((_FIXTURES / f"{name}.json").read_text())


def _envelope(body: dict) -> dict:
    return json.loads(present_response(TOOL, json.dumps(body)))


def _text(body: dict) -> str:
    env = _envelope(body)
    assert isinstance(env.get("response"), str) and env["response"], (
        f"{TOOL} is not wired into present_response: envelope keys {sorted(env)}"
    )
    return env["response"]


def _dealer_body(**changes) -> dict:
    body = _body("dealer-q4")
    body["dealers"][0].update(changes)
    return body


# ------------------------------------------------------------------ T3-1b

def test_present_period_labels() -> None:
    q4 = _text(_dealer_body())
    assert q4.split("\n")[0] == "Sales target Q4 2026 (1 Oct to 31 Dec)", q4

    month = _text(_dealer_body(period_start="2026-10-01", period_end="2026-10-31"))
    assert month.split("\n")[0] == "Sales target Oct 2026 (1 Oct to 31 Oct)", month

    year = _text(_dealer_body(period_start="2026-01-01", period_end="2026-12-31"))
    assert year.split("\n")[0] == "Sales target 2026 (1 Jan to 31 Dec)", year

    span = _text(_dealer_body(period_start="2026-10-01", period_end="2026-11-15"))
    assert span.split("\n")[0].startswith("Sales target 1 Oct to 15 Nov 2026"), span


def test_present_two_dealer_targets_header_ends_with_dealer_name() -> None:
    body = _body("dealer-q4")
    other = copy.deepcopy(body["dealers"][0])
    other.update(target_no="TGT-000020", subject_label="BKIN ELECTRICAL SDN BHD")
    body["dealers"].append(other)
    headers = [ln for ln in _text(body).split("\n") if ln.startswith("Sales target Q4 2026")]
    assert headers == [
        "Sales target Q4 2026 (1 Oct to 31 Dec), BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD",
        "Sales target Q4 2026 (1 Oct to 31 Dec), BKIN ELECTRICAL SDN BHD",
    ], headers


def test_present_quantity_target_has_plain_numbers() -> None:
    body = _dealer_body(
        metric="quantity", threshold_unit="quantity", target_value=500.0, achieved_value=320.0,
        next_tier={"tier": 1, "threshold": 400.0, "threshold_points": None,
                   "rates": [{"label": None, "rate": 3.0}], "additional_rates": [], "gap": 80.0},
    )
    text = _text(body)
    assert "RM" not in text, text
    assert re.search(r"\b80(\.00)?\b to go", text), text


# ------------------------------------------------------------------ T3-2

def test_present_dealer_target() -> None:
    assert _text(_body("dealer-q4")).split("\n") == [
        "Sales target Q4 2026 (1 Oct to 31 Dec)",
        "Counts: A/C I",
        "Achieved: RM 17,414.05 (provisional, incl. tax, to 23 Oct)",
        "Next tier: Tier 1, 3% at RM 85,000.00, RM 67,585.95 to go",
    ]


def test_dealer_reply_has_no_incentive_amount_and_envelope_has_result() -> None:
    env = _envelope(_body("dealer-q4"))
    assert env.get("has_result") is True, env
    lowered = env["response"].lower()
    assert "rebate" not in lowered and "commission" not in lowered and "incentive" not in lowered, env


# ------------------------------------------------------------------ T3-3

def test_present_closed_period_not_reached() -> None:
    lines = _text(_body("dealer-q3-missed")).split("\n")
    assert lines[0] == "Sales target Q3 2026 (1 Jul to 30 Sep)", lines
    assert "Counts: A/C I" in lines, lines
    assert "Achieved: RM 47,407.44 (provisional, incl. tax)" in lines, lines
    assert "Tier 1 (3%) at RM 50,000.00: not reached, short RM 2,592.56" in lines, lines
    assert not any(ln.startswith("Next tier:") for ln in lines), lines


# ------------------------------------------------------------------ T3-4

def test_present_points_without_ratio() -> None:
    lines = _text(_body("dealer-points-no-ratio")).split("\n")
    assert "Target: 25,000 points" in lines, lines
    assert "Achieved: RM 22,140.48 (provisional, incl. tax)" in lines, lines
    assert "Points are not converted yet, so I can't compare." in lines, lines
    assert not any("Tier" in ln for ln in lines), lines


# ------------------------------------------------------------------ T3-5

def test_present_salesperson_blocks() -> None:
    text = _text(_body("salesperson"))
    blocks = text.split("\n\n")
    assert len(blocks) == 3, blocks
    own, team, dealers = (b.split("\n") for b in blocks)
    assert own[0] == "Your sales target Q4 2026 (1 Oct to 31 Dec)", own
    assert "Target: RM 100,000.00, RM 60,000.00 to go" in own, own  # no-tier agent target
    assert any(ln.startswith("Achieved: RM 40,000.00") and "provisional" not in ln for ln in own), own
    assert "Open opportunities closing by 31 Dec: RM 40,000.00" in own, own
    assert team[0] == "Team SRT TEAM ALPHA target Q4 2026 (1 Oct to 31 Dec)", team
    assert "Target: RM 300,000.00, RM 180,000.00 to go" in team, team
    assert dealers == [
        "Your dealers, smallest gap first:",
        "BKIN ELECTRICAL SDN BHD [A/C I]: RM 5,275.80 of RM 50,000.00 (Tier 1), RM 44,724.20 to go",
        "A CRAFT IDEA SDN BHD [A/C I]: RM 866.40 of RM 60,000.00 (Tier 1), RM 59,133.60 to go",
        "BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD [A/C I]: RM 17,414.05 of RM 85,000.00 (Tier 1), RM 67,585.95 to go",
        "NO TIER DEALER SDN BHD [A/C I, A/C III]: RM 8,000.00 of RM 20,000.00, RM 12,000.00 to go",
        "ZZ TOP DEALER SDN BHD [A/C I]: RM 95,000.00, top tier reached (Tier 3)",
    ], dealers


def test_present_salesperson_without_own_target() -> None:
    blocks = _text(_body("salesperson-no-own")).split("\n\n")
    assert blocks[0] == "No sales target is set for you right now.", blocks
    assert blocks[1].split("\n")[0] == "Your dealers, smallest gap first:", blocks


def test_present_no_agent_tier_target_reached() -> None:
    body = _body("salesperson")
    body["own"][0]["achieved_value"] = 120000.0
    own = _text(body).split("\n\n")[0].split("\n")
    assert "Target reached: RM 100,000.00" in own, own


def test_present_dealer_with_no_lines() -> None:
    body = _body("dealer-q4")
    body["dealers"] = []
    assert _text(body) == "No sales target is set for your accounts right now."


# ------------------------------------------------------------------ T3-6

def test_present_rates_and_top_tier() -> None:
    additional = _dealer_body(next_tier={
        "tier": 2, "threshold": 115000.0, "threshold_points": None,
        "rates": [{"label": "A/C I", "rate": 6.0}], "additional_rates": [{"label": "A/C I", "rate": 1.0}],
        "gap": 97585.95})
    assert "Next tier: Tier 2, 6% + additional 1% at RM 115,000.00, RM 97,585.95 to go" in _text(additional).split("\n")

    two_accounts = [{"code": "300-B129", "label": "A/C I"}, {"code": "300-B131", "label": "A/C III"}]
    per_account = _dealer_body(accounts=two_accounts, next_tier={
        "tier": 1, "threshold": 85000.0, "threshold_points": None,
        "rates": [{"label": "A/C I", "rate": 3.0}], "additional_rates": [], "gap": 67585.95})
    lines = _text(per_account).split("\n")
    assert "Counts: A/C I, A/C III" in lines, lines
    assert "Next tier: Tier 1, 3% on A/C I at RM 85,000.00, RM 67,585.95 to go" in lines, lines

    several = _dealer_body(accounts=two_accounts, next_tier={
        "tier": 1, "threshold": 85000.0, "threshold_points": None,
        "rates": [{"label": "A/C I", "rate": 3.0}, {"label": "A/C III", "rate": 4.0}],
        "additional_rates": [], "gap": 67585.95})
    assert "Next tier: Tier 1, 3% on A/C I, 4% on A/C III at RM 85,000.00, RM 67,585.95 to go" in _text(several).split("\n")

    top = _dealer_body(next_tier=None, tier_reached={
        "tier": 3, "threshold": 90000.0, "threshold_points": None,
        "rates": [{"label": "A/C I", "rate": 5.0}], "additional_rates": []})
    assert "Top tier reached: Tier 3, 5%" in _text(top).split("\n")


# ------------------------------------------------------------------ T3-7

def test_sales_target_error_envelope() -> None:
    raw = http_error_body(
        '{"success": false, "message": "not enabled", "code": "sales_target_not_enabled"}',
        status_code=403, path="/api/v1/sales/target-progress", method="GET",
    )
    env = json.loads(present_response(TOOL, raw))
    assert env["has_result"] is False, env
    assert env["status_code"] == 403, env
    assert env["response"] == "" and env["answers"] == [], env
    assert env["detail"]["code"] == "sales_target_not_enabled", env


# ------------------------------------------------------------------ T3-8, T3-9

def test_present_dealer_row_next_threshold() -> None:
    body = _body("dealer-two-tiers")
    row = _body("dealer-two-tiers")["dealers"][0]
    salesperson = _body("salesperson-no-own")
    salesperson["dealers"] = [row]
    text = _text(salesperson)
    assert (
        "TWO TIER DEALER SDN BHD [A/C I]: RM 55,000.00 of RM 70,000.00 (Tier 2), RM 15,000.00 to go"
        in text.split("\n")
    ), text
    assert "RM 50,000.00 (Tier" not in text, body


def test_present_pipeline_date_is_target_end() -> None:
    body = _body("salesperson")
    body["own"][0].update(period_end="2026-10-31", target_end_date="2026-12-31", pipeline_value=40000.0)
    text = _text(body)
    assert "Open opportunities closing by 31 Dec: RM 40,000.00" in text.split("\n"), text
    assert "closing by 31 Oct" not in text, text


# ------------------------------------------------------------------ T3-10

def test_present_named_dealer_has_no_own_block() -> None:
    text = _text(_body("salesperson-narrowed"))
    for absent in ("Your sales target", "No sales target is set for you", "Team "):
        assert absent not in text, text
    assert (
        "BKIN ELECTRICAL SDN BHD [A/C I, A/C III, A/C IV]: RM 19,973.83 of RM 50,000.00 (Tier 1), RM 30,026.17 to go"
        in text.split("\n")
    ), text


def test_not_narrowed_with_no_own_still_says_no_target() -> None:
    body = _body("salesperson-narrowed")
    body["narrowed"] = False
    assert _text(body).startswith("No sales target is set for you right now."), body


def test_present_narrowed_no_dealer_lines() -> None:
    body = _body("salesperson-narrowed")
    body["dealers"] = []
    assert _text(body) == "No sales target is set for that dealer right now."
    body["window"] = {"date_from": "2026-07-01", "date_to": "2026-09-30"}
    assert _text(body) == "No sales target is set for that dealer for Q3 2026."
