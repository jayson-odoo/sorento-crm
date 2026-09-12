"""AC-1036: the ideation lane reads and writes only `session_vars.ideation`.

Reuses the existing ideation-turn harness (`tests/test_ideation_turn.py`'s `wired` /
`_turn`, which already proves AC-16 "preserves every other CRM key" against an
UNSTRUCTURED blob) and adds the one assertion this UAC line asks for: seeded with the
real five-key shape (`focus`, `open_question`, `access_levels`, `contains_flyer` besides
`ideation`), an ideation turn leaves every key except `ideation` byte-identical, and the
persisted key set never grows beyond the five.
"""
from __future__ import annotations

from tests.test_ideation_turn import _turn, wired  # noqa: F401 - fixture reused by name

FIVE_KEYS = {"focus", "open_question", "ideation", "access_levels", "contains_flyer"}


def test_the_ideation_turn_touches_only_the_ideation_key(wired) -> None:  # noqa: F811
    focus = {"products": {"value": [{"raw": "SRTWC8517"}], "set_at_turn": 3, "source": "current_message"}}
    open_question = None
    wired.set_session_vars(
        {
            "focus": focus,
            "open_question": open_question,
            "access_levels": ["dealer"],
            "contains_flyer": False,
            "ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["who"], "updated_at": "t"},
        }
    )
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )

    out = _turn()
    sv = out["session_vars"]

    assert set(sv.keys()) == FIVE_KEYS, (
        f"the ideation turn must never introduce a stray key: got {sorted(sv.keys())}"
    )
    assert sv["focus"] == focus, "the ideation lane must not touch focus"
    assert sv["open_question"] == open_question, "the ideation lane must not touch open_question"
    assert sv["access_levels"] == ["dealer"]
    assert sv["contains_flyer"] is False
    assert sv["ideation"]["status"] == "collecting"
