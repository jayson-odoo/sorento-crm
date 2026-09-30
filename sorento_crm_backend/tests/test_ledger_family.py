"""RELEASE-HOTFIX-0930: the ledger-family rule is core (`app/services/ledger_family.py`).

It moved out of `app/services/chatbot/turn/narrow.py` because `stock_ask_service` (core) had
started importing it from there, which `tests/chatbot/test_import_boundary.py` forbids. These
pin the rule itself, so the move is provably behaviour-preserving, and pin that the core caller
reads the ONE copy.
"""
from __future__ import annotations

import pytest

from app.services import stock_ask_service
from app.services.ledger_family import ledger_family_key, ledger_family_label


@pytest.mark.parametrize(
    "name",
    [
        "HANLIM TRADING SDN BHD [A/C I]",
        "HANLIM TRADING SDN BHD - [A/C II]",
        "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)",
        "hanlim trading sdn. bhd.",
    ],
)
def test_ledgers_of_one_trading_name_share_a_key(name: str) -> None:
    assert ledger_family_key(name) == "HANLIM TRADING"


def test_two_shops_are_two_keys_and_an_empty_name_is_no_key() -> None:
    assert ledger_family_key("CHIN CHUN HARDWARE SDN BHD - [A/C I]") == "CHIN CHUN HARDWARE"
    assert ledger_family_key("CHIN CHUN HARDWARE SDN BHD") != ledger_family_key("HANLIM TRADING SDN BHD")
    assert ledger_family_key("") == ""
    assert ledger_family_key("(SRT)") == ""


def test_label_is_the_name_without_its_ledger_marker() -> None:
    assert ledger_family_label("HANLIM TRADING SDN BHD - [A/C II]") == "HANLIM TRADING SDN BHD"
    assert ledger_family_label("HANLIM TRADING (JB) SDN BHD (SRT)") == "HANLIM TRADING SDN BHD"
    assert ledger_family_label("CHIN CHUN HARDWARE SDN BHD") == "CHIN CHUN HARDWARE SDN BHD"
    # A name that is ONLY a marker keeps its own text rather than becoming blank.
    assert ledger_family_label("[A/C I]") == "[A/C I]"


def test_the_stock_ask_record_reads_the_core_copy() -> None:
    """The boundary half (no `app.services.chatbot` import) is
    `tests/chatbot/test_import_boundary.py`'s; this pins where the name comes from instead.
    The chatbot side of the same pin is `tests/chatbot/test_ledger_family_is_core.py` (a test
    outside `tests/chatbot/` may not import the package either)."""
    import inspect

    assert "from app.services.ledger_family import" in inspect.getsource(stock_ask_service)
