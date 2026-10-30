"""LOOKUP-EMBED-CENTRAL AC-LEC-25: the gemini lookup floors, pinned to evidence.

Fixture: tests/fixtures/lookup_meaning_only_labels.json (rows, labelled phrases) with the cached gemini-embedding-001
vectors of its phrases and row texts in lookup_meaning_only_vectors.npz (float16, unit). No embed call, no crew path.
A "decision" is one meaning-only phrase (no row reaches it by spelling or partial) whose nearest row by meaning is at
or above the list's gemini floor; it is right when the phrase is a positive and that row is one of its gold rows.
Report and sweep: scripts/eval/lookup_floors_report.md (scripts/eval/tune_lookup_floors.py).

The cached vectors support 35 category meaning-only positives and only 2 file type positives, none for brand and
sales channel, so only the category list has enough decisions (>= 10) to carry a precision claim.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import app.main  # noqa: F401  isort:skip
from app.services.chatbot.head import candidates, list_resolver as lr
from app.services.chatbot.head.lookup_lists import LookupRow, _fold

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MODEL = "gemini-embedding-001"
MIN_DECISIONS = 10


@pytest.fixture(scope="module")
def world():
    doc = json.loads((FIXTURES / "lookup_meaning_only_labels.json").read_text())
    z = np.load(FIXTURES / "lookup_meaning_only_vectors.npz", allow_pickle=True)
    vectors = {str(t): v.astype(np.float32) for t, v in zip(z["texts"], z["vecs"])}
    rows = [LookupRow(r["list"], r["key"], r["label"], tuple(r["texts"])) for r in doc["rows"]]
    return doc, vectors, lr._prepare(rows)


def decisions(world, list_name, floor):
    doc, vectors, index = world
    floors = lr.FLOORS[list_name]
    made = right = 0
    wrong = []
    for e in doc["entries"]:
        if e["list"] != list_name or e["kind"] == "excluded":
            continue
        phrase = e["phrase"]
        folded = _fold(phrase)
        scores = lr._score_list(index[list_name], folded, candidates.trigrams(folded)) if folded else {}
        if any(s.spell >= floors["spell"] or s.partial >= floors["partial"] for s in scores.values()):
            continue
        best = None
        for row in index[list_name].rows:
            have = [vectors[t] for t in row.texts if t in vectors]
            if have:
                cos = max(float(vectors[phrase] @ v) for v in have)
                if best is None or cos > best[0]:
                    best = (cos, row)
        if best is None or best[0] < floor:
            continue
        made += 1
        gold = {t.casefold() for t in e.get("gold", [])}
        if e["kind"] == "pos" and gold & {t.casefold() for t in best[1].texts}:
            right += 1
        else:
            wrong.append((phrase, best[1].label))
    return made, right, wrong


def test_the_audited_gemini_floors_are_the_ones_in_the_resolver():
    assert lr.MEANING_FLOORS_BY_MODEL[MODEL] == {
        "category": 0.70, "spec": 0.75, "file_type": 0.65, "brand": 0.60, "promotion_kind": 0.75,
        "location": 0.65, "salesperson": 0.70, "customer": 0.75, "sales_channel": 0.65, "spec_key": 0.75,
    }


def test_the_fixture_is_the_size_the_report_describes(world):
    doc = world[0]
    count = lambda ln, kind: sum(e["list"] == ln and e["kind"] == kind for e in doc["entries"])  # noqa: E731
    assert count("category", "pos") >= 30 and count("category", "neg") >= 30
    for ln in ("file_type", "brand", "sales_channel"):
        assert count(ln, "neg") >= 30, ln
    assert not any(e["kind"] == "excluded" and "gold" in e for e in doc["entries"])


def test_category_decisions_at_the_current_floor_are_pinned(world):
    made, right, wrong = decisions(world, "category", lr.MEANING_FLOORS_BY_MODEL[MODEL]["category"])
    assert (made, right) == (34, 32), (made, right, wrong)
    assert {p for p, _ in wrong} == {"flush tank", "jet spray"}


@pytest.mark.parametrize("list_name", ["file_type", "brand", "sales_channel"])
def test_the_other_lists_have_too_few_meaning_only_decisions_to_move_a_floor(world, list_name):
    made, _right, _wrong = decisions(world, list_name, lr.MEANING_FLOORS_BY_MODEL[MODEL][list_name])
    assert made < MIN_DECISIONS


@pytest.mark.xfail(
    strict=True,
    reason="category at 0.70: 32 of 34 right = 0.94, just under 0.95 (flush tank -> Flush valve, jet spray -> Hand shower). "
    "0.71 gives 30 of 31 = 0.97 by dropping only the jet spray decision; see scripts/eval/lookup_floors_report.md. "
    "Turns green (and this marker must go) only if the floor moves.",
)
def test_category_floor_gives_precision_of_at_least_95_percent(world):
    made, right, wrong = decisions(world, "category", lr.MEANING_FLOORS_BY_MODEL[MODEL]["category"])
    assert made >= MIN_DECISIONS
    assert right / made >= 0.95, wrong
