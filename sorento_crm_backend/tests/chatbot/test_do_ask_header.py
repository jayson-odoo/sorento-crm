"""DO-ASK-SIMPLIFY rule 1: the DO list header names a customer once, not every ledger.

`documentation/plans/chatbot/PLAN-do-ask-simplify-2oct.md`, rule 1. The `Customer:` line of
`tail/scope_block.py::search_scope_header` groups the in-scope customer rows by ledger family
(`app/services/ledger_family.py`) and prints the family label, with a count when the family
has several rows and "and N more" when several families are in scope. The rows themselves
keep their own full ledger name; only the header shortens.

Pure function tests: no database, no engine.
"""
from __future__ import annotations

import json

from app.services.chatbot.tail import scope_block as scope_block_mod

_HANLIM = [
    "HANLIM TRADING SDN BHD [A/C II]",
    "HANLIM TRADING SDN BHD [A/C I]",
    "HANLIM TRADING SDN BHD [A/C III]",
    "HANLIM TRADING SDN BHD [A/C IV]",
    "HANLIM TRADING SDN BHD",
    "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)",
]


def _header(names: list[str]) -> str:
    qf = {"entities": [], "date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}
    gate_json = {
        "compatible_entities": [
            {"entity_type": "customer", "code": f"300-H{i:03d}", "display_name": name}
            for i, name in enumerate(names)
        ]
    }
    header = scope_block_mod.search_scope_header(
        domain="order", qf=qf, gate_json=gate_json, resolver_json={}
    )
    assert header is not None, "test setup sanity: the order domain must produce a header"
    return header


def _customer_line(header: str) -> str:
    lines = [line for line in header.split("\n") if line.startswith("Customer:")]
    assert len(lines) == 1, header
    return lines[0]


def test_six_hanlim_ledgers_print_one_family_name_with_a_count() -> None:
    assert _customer_line(_header(_HANLIM)) == "Customer: HANLIM TRADING SDN BHD (6 accounts)"


def test_one_ledger_prints_its_own_full_name() -> None:
    assert _customer_line(_header(["HANLIM TRADING SDN BHD [A/C I]"])) == (
        "Customer: HANLIM TRADING SDN BHD [A/C I]"
    )


def test_several_families_print_the_first_family_and_a_count_of_the_rest() -> None:
    names = [
        "CHIN CHUN HARDWARE SDN BHD - [A/C I]",
        "CHIN CHUN HARDWARE SDN BHD - [CERAMIC]",
        "CHIN CHUN HOMEMART SDN BHD - [A/C I]",
        "CHIN CHUN HARDWARE AND TIMBER TRADING",
        "JIMMY - I",
    ]
    assert _customer_line(_header(names)) == (
        "Customer: CHIN CHUN HARDWARE SDN BHD (2 accounts) and 3 more"
    )


def test_one_ledger_reached_twice_is_one_account() -> None:
    assert _customer_line(_header(["ZZT BATH IDEA (KEMAMAN OUTLET)"] * 2)) == (
        "Customer: ZZT BATH IDEA (KEMAMAN OUTLET)"
    )


def test_the_header_never_lists_a_ledger_marker_for_a_family() -> None:
    line = _customer_line(_header(_HANLIM))
    assert "[A/C" not in line and "CERAMIC" not in line, line


def test_dates_line_is_unchanged() -> None:
    assert "Dates: 01/10/2026 to 31/10/2026" in _header(_HANLIM)


# --- review round 1 ---------------------------------------------------------------------- #


def test_the_carried_customer_rows_print_one_family_name_with_a_count() -> None:
    """B1: the answer to the period question ("this month") names no customer of its own,
    so the header reads the FOCUS carry (`_focus_words`), not the gate."""
    header = scope_block_mod.search_scope_header(
        domain="order",
        qf={"entities": [], "date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"},
        gate_json={"compatible_entities": []},
        resolver_json={},
        focus_customers=[{"hint": "customer", "display_name": name} for name in _HANLIM],
    )
    assert _customer_line(header) == "Customer: HANLIM TRADING SDN BHD (6 accounts)", header


def test_an_empty_do_list_names_the_customer_once_too() -> None:
    """S1: the miss composer's own header (`answer.not_found_error_message`) groups the same
    way, so an empty DO list does not list every ledger either."""
    from app.services.chatbot.lanes.business.answer import not_found_error_message

    rows = [
        {"uuid": f"00000000-0000-4000-8000-00000000000{i}", "entity_type": "customer", "code": "300-H", "display_name": n}
        for i, n in enumerate(_HANLIM)
    ]
    out = not_found_error_message(
        {},
        parser={"domain_hint": "order", "entities": [], "routing": {"suggested_team": "customer_service"}},
        resolved={"tokens": [], "unresolved_tokens": [], "resolutions": [], "intersection": rows, "by_entity_type": {"customer": rows}},
        gate={"gate_passed": True, "compatible_entities": rows},
    )
    first_line = (out.get("escalate_message") or "").split("\n", 1)[0]
    assert first_line == "Customer: HANLIM TRADING SDN BHD (6 accounts)", json.dumps(out)


def test_a_bracket_every_account_shares_stays_in_the_name() -> None:
    """Tester pass 1: "(SENTUL)" is the branch, shared by both ledgers, not a ledger marker;
    dropping it would read as every CHENG HUAT HARDWARE branch."""
    names = [
        "CHENG HUAT HARDWARE (SENTUL) SDN BHD - [A/C I]",
        "CHENG HUAT HARDWARE (SENTUL) SDN BHD - [IBORN]",
    ]
    assert _customer_line(_header(names)) == "Customer: CHENG HUAT HARDWARE (SENTUL) SDN BHD (2 accounts)"
