"""EVAL-BENCH round 41: the which-one stamp setting is the bot's own, not inferred from the audience.

The chain on main: `stock_visibility.resolve_policy` -> `turn_runtime._stock_availability_only` -> `Profile.stock_availability_only`
-> the stamp gate in `lanes/business/answer.py`. The live runner records the value on the row (`asker_profile`); a stock tool's
envelope carries `stock_visibility.mode` as the fallback; with neither, the check is unknown. Synthetic rows only.
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.chatbot_eval import replay as replay_mod
from scripts.chatbot_eval.targets import grade_turn
from tests.chatbot_eval.test_round40 import DEALER_ASKER, GOLD_AMB, MATCHING, STAMPS, _which_one
from tests.chatbot_eval.test_targets import item

LINKED_DEALER = dict(DEALER_ASKER, audience="linked_dealer")


def _with_profile(r, flag):
    r["asker_profile"] = {"stock_availability_only": flag, "source": "turn_runtime._stock_availability_only"}
    return r


def _with_mode(r, mode):
    r["trace"].append({"kind": "tool", "name": "crm_inventory_stock_balance_list", "args": {},
                       "envelope": {"stock_visibility": {"mode": mode}}})
    return r


def _which(r, asker=None):
    return grade_turn(r, item("attachment", **({"asker": asker} if asker else {}), **GOLD_AMB))["checks"]["which_one"]


# (a) the recorded flag decides, over the audience
def test_red_a_a_linked_dealer_whose_recorded_flag_is_false_expects_a_stamped_list():
    assert _which(_with_profile(_which_one(MATCHING, STAMPS), False), LINKED_DEALER) is True
    assert _which(_with_profile(_which_one(MATCHING, [None] * 3), False), LINKED_DEALER) is False


def test_red_a_staff_whose_recorded_flag_is_true_expects_a_bare_list():
    assert _which(_with_profile(_which_one(MATCHING, [None] * 3), True)) is True
    assert _which(_with_profile(_which_one(MATCHING, STAMPS), True)) is False


# (b) the stock tool envelope's stock_visibility.mode when no profile is recorded
def test_red_b_the_envelope_mode_availability_means_a_bare_list():
    assert _which(_with_mode(_which_one(MATCHING, [None] * 3), "availability")) is True
    assert _which(_with_mode(_which_one(MATCHING, STAMPS), "availability")) is False


def test_red_b_any_other_envelope_mode_means_a_stamped_list():
    assert _which(_with_mode(_which_one(MATCHING, STAMPS), "compact")) is True
    assert _which(_with_mode(_which_one(MATCHING, [None] * 3), "compact")) is False


def test_red_b_the_recorded_flag_wins_over_the_envelope():
    r = _with_profile(_with_mode(_which_one(MATCHING, STAMPS), "availability"), False)
    assert _which(r) is True


# (c) no source: unknown, never inferred from the audience
def test_red_c_no_source_is_unknown_for_a_dealer_and_for_staff():
    for asker in (None, DEALER_ASKER, LINKED_DEALER):
        for stamps in ([None] * 3, STAMPS):
            r = _which_one(MATCHING, stamps)
            assert _which(r, asker) is None, (asker, stamps)
    res = grade_turn(_which_one(MATCHING, STAMPS), item("attachment", **GOLD_AMB))
    assert res["passed"] is None, res


def test_guard_c_a_picker_over_the_wrong_codes_fails_whatever_the_setting_source():
    assert _which(_with_profile(_which_one(["XY-1", "XY-2"], STAMPS[:2]), False)) is False
    assert _which(_which_one(["XY-1", "XY-2"], STAMPS[:2])) is False


# (d) the runner records the flag the engine uses
def test_red_d_the_runner_stores_the_engine_s_stock_availability_flag(monkeypatch):
    from app.services.chatbot import engine, turn_runtime

    seen = []

    def fake(db, contact, space_id):
        seen.append((db, contact, space_id))
        return True

    monkeypatch.setattr(turn_runtime, "_stock_availability_only", fake)
    monkeypatch.setattr(engine, "_contact_respond_id", lambda envelope: "c-1")
    db = object()
    out = replay_mod._asker_profile(db, SimpleNamespace())
    assert out == {"stock_availability_only": True, "source": "turn_runtime._stock_availability_only"}, out
    assert seen == [(db, "c-1", None)], seen   # the engine's own call: load_profile(db, contact) passes no space


def test_red_d_an_unreadable_policy_stores_no_flag(monkeypatch):
    from app.services.chatbot import engine, turn_runtime

    def boom(db, contact, space_id):
        raise RuntimeError("policy unreadable")

    monkeypatch.setattr(turn_runtime, "_stock_availability_only", boom)
    monkeypatch.setattr(engine, "_contact_respond_id", lambda envelope: "c-1")
    assert replay_mod._asker_profile(object(), SimpleNamespace()) is None
