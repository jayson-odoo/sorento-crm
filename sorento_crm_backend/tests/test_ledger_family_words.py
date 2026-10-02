"""`ledger_family.family_words`: the customer companies the chatbot names, group name only.

Owner rule (2 Oct 2026, PR #1435): when the chatbot names a customer company it prints the
GROUP NAME ONLY, "HANLIM TRADING SDN BHD": no "(6 accounts)" count and no "and N more".
Several groups are each named. Pure function, no database.
"""
from __future__ import annotations

from app.services.ledger_family import family_words

H1 = "HANLIM TRADING SDN BHD [A/C I]"
H2 = "HANLIM TRADING SDN BHD [A/C II]"
H3 = "HANLIM TRADING SDN BHD [A/C III]"
S1 = "SOON HENG HARDWARE CO.SDN.BHD. [A/C I]"
C1 = "CHENG HUAT HARDWARE (SENTUL) SDN BHD [A/C I]"
C2 = "CHENG HUAT HARDWARE (SENTUL) SDN BHD [A/C II]"


def test_several_ledgers_of_one_group_print_the_group_name_without_a_count() -> None:
    assert family_words([H1, H2, H3]) == "HANLIM TRADING SDN BHD"


def test_one_ledger_prints_its_group_name_without_its_ledger_marker() -> None:
    assert family_words([H1]) == "HANLIM TRADING SDN BHD"


def test_several_groups_are_each_named_never_and_n_more() -> None:
    assert family_words([H1, H2, S1]) == "HANLIM TRADING SDN BHD and SOON HENG HARDWARE CO.SDN.BHD."
    assert family_words([H1, S1, C1, C2]) == (
        "HANLIM TRADING SDN BHD, SOON HENG HARDWARE CO.SDN.BHD. and CHENG HUAT HARDWARE (SENTUL) SDN BHD"
    )


def test_a_bracket_every_ledger_shares_stays_in_the_group_name() -> None:
    assert family_words([C1, C2]) == "CHENG HUAT HARDWARE (SENTUL) SDN BHD"


def test_a_plain_name_prints_as_is_and_nothing_prints_none() -> None:
    assert family_words(["ZZT OWN A"]) == "ZZT OWN A"
    assert family_words([]) is None
