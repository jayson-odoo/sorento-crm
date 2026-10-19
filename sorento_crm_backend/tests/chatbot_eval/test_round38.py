"""EVAL-BENCH round 38 G1: the attachments sent are read from the full tool results.

The trace caps a big tool result to {head, bytes, truncated}, so a reply that DID send files graded files = [].
The live runner keeps the uncapped results in `row["tool_results"]`; they are the source when present.
Synthetic data only.
"""
from __future__ import annotations

import json

from scripts.chatbot_eval.targets import grade_turn
from tests.chatbot_eval.test_targets import GOLD_TS, _att, _file, check, item

TOOL = "crm_master_product_attachments_list"
CAPPED = {"head": '{"result_type": "product_attachments"', "bytes": 90000, "truncated": True}


def _capped(label_files, *, full=True, announce=False):
    """An attachment row whose trace envelope is capped; `full` adds the uncapped tool results."""
    r = _att([_file("x")])
    for rec in r["trace"]:
        if rec.get("kind") == "tool":
            rec["envelope"] = dict(CAPPED)
        if rec.get("stage") == "replied" and not announce:
            rec["facts"].pop("files", None)
    if full:
        r["tool_results"] = [{"name": TOOL, "args": {}, "result": json.dumps(
            {"result_type": "product_attachments", "items": [], "attachments": label_files})}]
    return r


def test_red_a_capped_envelope_files_are_read_from_full_results():
    # the live shape: the replied stage carries facts.files as an int above 0
    r = _capped([_file("Technical Specifications", "a.pdf"), _file("Technical Specifications", "b.pdf")], announce=True)
    assert any(x.get("stage") == "replied" and x["facts"]["files"] > 0 for x in r["trace"])
    res = grade_turn(r, item("attachment", **GOLD_TS))
    assert res["checks"]["files"] is True, res["checks"]
    assert res["checks"]["type"] is True, res["checks"]
    check(res, True)


def test_guard_a_no_tool_results_keeps_the_envelope_path():
    check(grade_turn(_att([_file("Technical Specifications")]), item("attachment", **GOLD_TS)), True)
    r = _capped([], full=False)
    assert grade_turn(r, item("attachment", **GOLD_TS))["checks"]["files"] is False


def test_guard_b_full_results_with_no_attachments_still_fail_files():
    res = grade_turn(_capped([]), item("attachment", **GOLD_TS))
    assert res["checks"]["files"] is False, res["checks"]


def test_guard_c_full_results_of_another_type_still_fail_type():
    res = grade_turn(_capped([_file("Drawing"), _file("Drawing", "b.pdf")]), item("attachment", **GOLD_TS))
    assert res["checks"]["type"] is False, res["checks"]
