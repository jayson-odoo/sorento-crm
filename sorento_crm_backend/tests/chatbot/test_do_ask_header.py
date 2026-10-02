"""DO-ASK-SIMPLIFY rule 1: the DO list header names a customer once, not every ledger.

`documentation/plans/chatbot/PLAN-do-ask-simplify-2oct.md`, rule 1. The `Customer:` line of
`tail/scope_block.py::search_scope_header` groups the in-scope customer rows by ledger family
(`app/services/ledger_family.py`) and prints the family label, with a count when the family
has several rows and "and N more" when several families are in scope. The rows themselves
keep their own full ledger name; only the header shortens.

Pure function tests: no database, no engine.
"""
from __future__ import annotations

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


def test_the_header_never_lists_a_ledger_marker_for_a_family() -> None:
    line = _customer_line(_header(_HANLIM))
    assert "[A/C" not in line and "CERAMIC" not in line, line


def test_dates_line_is_unchanged() -> None:
    assert "Dates: 01/10/2026 to 31/10/2026" in _header(_HANLIM)
