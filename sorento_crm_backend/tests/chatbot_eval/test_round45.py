"""EVAL-BENCH round 45: the replay's parse source and a missing pinned prompt version.

No DB: `_pin_resolves` and `engine.run_turn` are stubbed. Synthetic rows only.
"""
from __future__ import annotations

import pytest

from app.services.chatbot import engine as engine_mod
from scripts.chatbot_eval import replay as replay_mod

PIN = "11111111-1111-4111-8111-111111111111"
STATE = {"set": {"brand": "x"}}


def _row(*, understood=None, ctx_raw=None, override=None):
    trace = [{"stage": "received", "raw": {}}]
    if understood is not None:
        trace.append({"stage": "understood", "raw": {"parser_raw": understood}})
    envelope = {"message": {"message": {"text": "hi"}}, "contact": {"id": 1}}
    if override:
        envelope["prompt_overrides"] = {"chatbot_semantic_parser": override}
    return {"id": "t1", "case_id": "c1", "trace": trace, "envelope": envelope,
            "response": {"ctx": {"parse": {"_parser_raw": ctx_raw} if ctx_raw is not None else {}}}}


def _factory():
    def f():
        raise AssertionError("no DB in this test")
    f._rolled_back = True
    return f


# ------------------------------------------------------------------ 1. parse source
def test_red_1a_understood_record_wins_over_the_stripped_ctx_parse():
    row = _row(understood={"intent": "a", "state_changes": STATE}, ctx_raw={"intent": "a"})
    assert replay_mod._recorded_parse(row) == {"intent": "a", "state_changes": STATE}


def test_guard_1b_only_ctx_parse_still_returns_it():
    assert replay_mod._recorded_parse(_row(ctx_raw={"intent": "a"})) == {"intent": "a"}


def test_guard_1c_neither_is_none():
    assert replay_mod._recorded_parse(_row()) is None


def test_guard_1d_an_empty_understood_dict_falls_back():
    assert replay_mod._recorded_parse(_row(understood={}, ctx_raw={"intent": "a"})) == {"intent": "a"}


# ------------------------------------------------------------------ 2. missing pinned prompt version
def _run(monkeypatch, row, resolves):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("engine reached")

    monkeypatch.setattr(engine_mod, "run_turn", boom)
    monkeypatch.setattr(replay_mod, "_pin_resolves", lambda factory, vid: resolves)
    out = replay_mod._replay_one(row, _factory())
    return out, calls


def test_red_2a_a_pin_the_db_lacks_skips_the_turn_without_running_it(monkeypatch):
    out, calls = _run(monkeypatch, _row(ctx_raw={"intent": "a"}, override=PIN), resolves=False)
    assert out["skipped"] == "prompt_missing", out
    assert calls == [] and out["misses"] == [] and out["stages"] == {}


def test_guard_2b_a_stored_pin_runs(monkeypatch):
    out, calls = _run(monkeypatch, _row(ctx_raw={"intent": "a"}, override=PIN), resolves=True)
    assert calls == [1] and out["skipped"] is None


def test_guard_2c_no_override_runs_without_asking_the_db(monkeypatch):
    out, calls = _run(monkeypatch, _row(ctx_raw={"intent": "a"}), resolves=False)
    assert calls == [1] and out["skipped"] is None


def test_guard_2d_prompt_missing_counts_as_a_skip_in_the_diff():
    skipped = {"case_id": "c1", "turn_id": "t1", "skipped": "prompt_missing", "misses": [], "stages": {}}
    res = replay_mod.diff_rows([skipped], [dict(skipped)])
    assert res["counts"]["skipped"] == {"prompt_missing": 1}
    assert res["compared"] == 0 and res["broken"] == []


def test_red_2e_a_non_dict_prompt_overrides_is_ignored_like_the_engine_does(monkeypatch):
    row = _row(ctx_raw={"intent": "a"})
    row["envelope"]["prompt_overrides"] = "not-a-dict"
    out, calls = _run(monkeypatch, row, resolves=False)
    assert calls == [1] and out["skipped"] is None, out


def test_red_1e_an_emission_without_state_changes_does_not_override_ctx():
    row = _row(understood={"intent": "emission"}, ctx_raw={"intent": "ctx"})
    assert replay_mod._recorded_parse(row) == {"intent": "ctx"}


def test_red_1f_an_emission_with_empty_state_changes_does_not_override_ctx():
    row = _row(understood={"intent": "emission", "state_changes": []}, ctx_raw={"intent": "ctx"})
    assert replay_mod._recorded_parse(row) == {"intent": "ctx"}
