"""DO-ASK-SIMPLIFY rule 1: the DO list header names a customer once, not every ledger.

`documentation/plans/chatbot/PLAN-do-ask-simplify-2oct.md`, rule 1. The `Customer:` line of
`tail/scope_block.py::search_scope_header` groups the in-scope customer rows by ledger family
(`app/services/ledger_family.py`) and prints the family label, with a count when the family
several rows and "and N more" when several families are in scope. Owner rule (2 Oct
2026) since: the group name ONLY, no count and no "and N more"; several groups are listed
by name. The rows themselves keep their own full ledger name; only the header shortens.

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


def test_six_hanlim_ledgers_print_the_group_name_only() -> None:
    assert _customer_line(_header(_HANLIM)) == "Customer: HANLIM TRADING SDN BHD"


def test_one_ledger_prints_its_group_name() -> None:
    """Owner rule (2 Oct 2026): the group name only, even for one account."""
    assert _customer_line(_header(["HANLIM TRADING SDN BHD [A/C I]"])) == "Customer: HANLIM TRADING SDN BHD"


def test_several_families_print_each_group_name() -> None:
    names = [
        "CHIN CHUN HARDWARE SDN BHD - [A/C I]",
        "CHIN CHUN HARDWARE SDN BHD - [CERAMIC]",
        "CHIN CHUN HOMEMART SDN BHD - [A/C I]",
        "CHIN CHUN HARDWARE AND TIMBER TRADING",
        "JIMMY - I",
    ]
    assert _customer_line(_header(names)) == (
        "Customer: CHIN CHUN HARDWARE SDN BHD, CHIN CHUN HOMEMART SDN BHD, "
        "CHIN CHUN HARDWARE AND TIMBER TRADING, JIMMY - I"
    )


def test_one_ledger_reached_twice_is_one_account() -> None:
    assert _customer_line(_header(["ZZT BATH IDEA SDN BHD [A/C I]"] * 2)) == "Customer: ZZT BATH IDEA SDN BHD"


def test_the_header_never_lists_a_ledger_marker_for_a_family() -> None:
    line = _customer_line(_header(_HANLIM))
    assert "[A/C" not in line and "CERAMIC" not in line, line


def test_dates_line_is_unchanged() -> None:
    assert "Dates: 01/10/2026 to 31/10/2026" in _header(_HANLIM)


# --- review round 1 ---------------------------------------------------------------------- #


def test_the_carried_customer_rows_print_the_group_name_only() -> None:
    """B1: the answer to the period question ("this month") names no customer of its own,
    so the header reads the FOCUS carry (`_focus_words`), not the gate."""
    header = scope_block_mod.search_scope_header(
        domain="order",
        qf={"entities": [], "date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"},
        gate_json={"compatible_entities": []},
        resolver_json={},
        focus_customers=[{"hint": "customer", "display_name": name} for name in _HANLIM],
    )
    assert _customer_line(header) == "Customer: HANLIM TRADING SDN BHD", header


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
    assert first_line == "Customer: HANLIM TRADING SDN BHD", json.dumps(out)


def test_a_bracket_every_account_shares_stays_in_the_name() -> None:
    """Tester pass 1: "(SENTUL)" is the branch, shared by both ledgers, not a ledger marker;
    dropping it would read as every CHENG HUAT HARDWARE branch."""
    names = [
        "CHENG HUAT HARDWARE (SENTUL) SDN BHD - [A/C I]",
        "CHENG HUAT HARDWARE (SENTUL) SDN BHD - [IBORN]",
    ]
    assert _customer_line(_header(names)) == "Customer: CHENG HUAT HARDWARE (SENTUL) SDN BHD"



# --- owner rule, 2 Oct 2026: the group name only, never a count ---------------------------- #


def test_no_header_ever_counts_accounts_or_says_more() -> None:
    for names in (_HANLIM, _HANLIM[:2], ["CHIN CHUN HARDWARE SDN BHD - [A/C I]", "JIMMY - I", "ZZT A", "ZZT B"]):
        line = _customer_line(_header(names))
        assert "accounts)" not in line and " more" not in line, line


def test_the_not_your_account_line_names_group_names_only() -> None:
    """The customer-scope refusal ("Sorry, that isn't under your account. I can only check
    on ...") names the contact's linked groups, never every ledger."""
    from app.services import contact_customer_scope as scope_mod

    scope = scope_mod.ContactCustomerScope(
        linked=tuple((f"id{i}", n, f"300-H{i}") for i, n in enumerate(_HANLIM)) + (("idz", "ZZT OTHER SDN BHD [A/C I]", "300-Z"),),
        staff=False,
    )
    assert scope_mod.refusal_line(scope) == (
        "Sorry, that isn't under your account. I can only check on HANLIM TRADING SDN BHD and ZZT OTHER SDN BHD."
    )
