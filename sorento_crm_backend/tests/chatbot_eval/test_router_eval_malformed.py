"""The eval records a malformed Jev answer as a router failure instead of crashing the run."""
from __future__ import annotations

import pytest

from tests.chatbot_eval.test_router_eval import ITEMS, FakeChoose, _env  # noqa: F401
from tests.chatbot_eval.test_router_eval import _results, _run, _summary


class _Malformed(FakeChoose):
    def __init__(self, bad_text, answer):
        super().__init__()
        self.bad_text, self.answer = bad_text, answer

    def __call__(self, *args, **kw):
        if self.bad_text in kw["state"]:
            self.calls.append(dict(kw))
            return self.answer
        return super().__call__(*args, **kw)


@pytest.mark.parametrize(
    "answer",
    [
        {"choice": "agent", "confidence": 0.9, "probabilities": {"chat": 0.1}, "input_tokens": 5},  # no agent key
        {"choice": "agent", "input_tokens": 5},  # no probabilities
        {"probabilities": {"agent": "high"}, "input_tokens": 5},  # not a number
    ],
)
def test_a_malformed_answer_is_a_router_failure_and_the_run_goes_on(tmp_path, answer):
    rc, out = _run(tmp_path, choose=_Malformed("why did Penang drop", answer))
    assert rc == 0
    rows = {r["id"]: r for r in _results(out)}
    assert len(rows) == len(ITEMS)
    assert rows["g2"]["route"] == "chat" and rows["g2"]["reason"] == "router_failed"
    assert _summary(out)["failures"] == 1
