"""RELEASE-HOTFIX-0930: the narrower reads the ledger-family rule from core.

`ledger_family_key` / `ledger_family_label` moved from `turn/narrow.py` to
`app/services/ledger_family.py` (see `tests/test_ledger_family.py`). `narrow.py` still exposes
both names, so `compose.py` and `session_state.py` are untouched, but they must be the SAME
objects as core's: a second copy here is the drift the move exists to prevent.
"""
from __future__ import annotations

from app.services import ledger_family
from app.services.chatbot.turn import narrow


def test_the_narrower_exposes_cores_functions_not_a_copy() -> None:
    assert narrow.ledger_family_key is ledger_family.ledger_family_key
    assert narrow.ledger_family_label is ledger_family.ledger_family_label
