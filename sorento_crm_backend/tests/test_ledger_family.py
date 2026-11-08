"""RELEASE-HOTFIX-0930: the ledger-family rule is core (`app/services/ledger_family.py`).

It moved out of `app/services/chatbot/turn/narrow.py` because `stock_ask_service` (core) had
started importing it from there, which `tests/chatbot/test_import_boundary.py` forbids. These
pin the rule itself, so the move is provably behaviour-preserving, and pin that the core caller
reads the ONE copy.
"""
from __future__ import annotations

import pytest

from app.services import stock_ask_service
from app.services.ledger_family import ledger_family_key, ledger_family_label, trading_name_key, without_ledger_marker

#: CUSTOMER-GROUP-GATE (owner ruling 3 Nov 2026): the trading-name rule is SEARCH only
#: (`trading_name_key`); a which-one list joins ledgers only through a customer group, so with no
#: groups held every ledger is its own entry (`ledger_family_key`).


@pytest.mark.parametrize(
    "name",
    [
        "HANLIM TRADING SDN BHD [A/C I]",
        "HANLIM TRADING SDN BHD - [A/C II]",
        "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)",
        "hanlim trading sdn. bhd.",
    ],
)
def test_ledgers_of_one_trading_name_share_a_search_key(name: str) -> None:
    assert trading_name_key(name) == "HANLIM TRADING"


def test_without_a_group_every_ledger_is_its_own_entry() -> None:
    names = ["HANLIM TRADING SDN BHD [A/C I]", "HANLIM TRADING SDN BHD - [A/C II]", "HANLIM TRADING SDN BHD"]
    assert len({ledger_family_key(n) for n in names}) == len(names)
    # case and spacing are not a different ledger
    assert ledger_family_key("hanlim  trading sdn bhd") == ledger_family_key("HANLIM TRADING SDN BHD")


def test_two_shops_are_two_search_keys_and_an_empty_name_is_no_key() -> None:
    assert trading_name_key("CHIN CHUN HARDWARE SDN BHD - [A/C I]") == "CHIN CHUN HARDWARE"
    assert trading_name_key("CHIN CHUN HARDWARE SDN BHD") != trading_name_key("HANLIM TRADING SDN BHD")
    assert ledger_family_key("") == ""
    assert trading_name_key("(SRT)") == ""


def test_an_ungrouped_label_is_its_full_name_and_the_marker_strip_is_separate() -> None:
    assert ledger_family_label("HANLIM TRADING SDN BHD - [A/C II]") == "HANLIM TRADING SDN BHD - [A/C II]"
    assert without_ledger_marker("HANLIM TRADING SDN BHD - [A/C II]") == "HANLIM TRADING SDN BHD"
    assert without_ledger_marker("HANLIM TRADING (JB) SDN BHD (SRT)") == "HANLIM TRADING SDN BHD"
    assert without_ledger_marker("CHIN CHUN HARDWARE SDN BHD") == "CHIN CHUN HARDWARE SDN BHD"
    # A name that is ONLY a marker keeps its own text rather than becoming blank.
    assert without_ledger_marker("[A/C I]") == "[A/C I]"


def test_the_stock_ask_record_reads_the_core_copy() -> None:
    """The boundary half (no `app.services.chatbot` import) is
    `tests/chatbot/test_import_boundary.py`'s; this pins where the name comes from instead.
    The chatbot side of the same pin is `tests/chatbot/test_ledger_family_is_core.py` (a test
    outside `tests/chatbot/` may not import the package either)."""
    import inspect

    assert "from app.services.ledger_family import" in inspect.getsource(stock_ask_service)
