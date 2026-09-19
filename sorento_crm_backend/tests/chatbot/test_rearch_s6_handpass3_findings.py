"""AC-1593 item 3 (16 Sep 2026, browser pass 3, "notes for the captain" - non-blocking
but the coordinator asked for reds): turn `c16197ef` ("outstanding for chin chun")
rendered a customer roster mixing 3 raw account codes with 1 full name - "1. 300-C043
2. 300-C124 3. 300-C001 4. CHIN CHUN HARDWARE SDN BHD - [A/C I]". `turn/narrow.py::
_options` already implements the label half of the contract correctly (`label = name
or raw or code`, measured, not a red here) - what it does NOT do is collapse several
candidate rows that share the SAME resolved name into one roster line (contract 103's
own "a family is one code across several rows, one choice not two" reasoning, applied
here to a customer's several ledgers sharing one name rather than a product's several
ledgers sharing one code).
"""
from __future__ import annotations


def test_customer_candidates_sharing_the_same_name_collapse_to_one_roster_line() -> None:
    from app.services.chatbot.turn.narrow import decide
    from app.services.chatbot.turn.state import Focus, Profile

    candidates = [
        {"uuid": "u1", "canonical_code": "300-H070", "name": "HANLIM TRADING SDN BHD [A/C II]"},
        {"uuid": "u2", "canonical_code": "300-H030", "name": "HANLIM TRADING SDN BHD [A/C II]"},
        {"uuid": "u3", "canonical_code": "300-H118", "name": "HANLIM TRADING SDN BHD [A/C I]"},
    ]

    outcome = decide(
        kind="customer",
        policy_value="must_narrow_one",
        focus=Focus(),
        profile=Profile(),
        resolved_candidates=candidates,
    )

    names = [o.get("label") for o in outcome.ask_options]
    assert names.count("HANLIM TRADING SDN BHD [A/C II]") == 1, (
        f"two rows sharing one name must print as ONE roster line, got {names!r}"
    )
    assert len(outcome.ask_options) == 2, (
        f"3 rows, 2 distinct names, must be a 2-line roster - got {len(outcome.ask_options)}: {names!r}"
    )
