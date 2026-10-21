"""`turn_runtime.focus_diff` over a reset that drops a stored list.

`focus_to_wire` (turn/state.py) leaves an empty `last_list` out of the wire dict, so the focus
before a turn can carry the key while the focus after it does not. The diff indexed the after
dict by the before dict's keys and raised KeyError: 'last_list', and the turn answered "Sorry, I
ran into a problem understanding that": a conversation whose focus holds a stored list (written
on the state path) followed by "clear all", whose reset wipe keeps only RESET_KEEPS.
"""

from app.services.chatbot.turn.apply import RESET_KEEPS
from app.services.chatbot.turn.state import Focus
from app.services.chatbot.turn_runtime import focus_diff


def _focus_with_a_stored_list() -> Focus:
    return Focus(last_list=[{"position": 1, "code": "CL8109A"}, {"position": 2, "code": "C9109A"}])


def test_a_reset_wipe_over_a_stored_list_diffs_without_error():
    before = _focus_with_a_stored_list()
    after = Focus(**{key: getattr(before, key) for key in RESET_KEEPS})
    diff = focus_diff(before, after)
    assert diff["last_list"]["before"]
    assert diff["last_list"]["after"] is None


def test_a_stored_list_that_appears_is_diffed_too():
    diff = focus_diff(Focus(), _focus_with_a_stored_list())
    assert diff["last_list"]["before"] is None
    assert diff["last_list"]["after"]
