"""REPORT-SPEC-W1: the L1 report corpus (`golden/report_turns.jsonl`) replayed through the real engine, no LLM.

Plan `documentation/plans/chatbot/ARCH-report-engine-7nov.md` 3.0 / 3.2 (lane plan `PLAN-report-spec-w1-8nov.md`).
Every later report lane (W2-W7) keeps this file green; a phrasing that fails becomes an `xfail` row tagged with its
lane id, never a code patch.

One row is one recorded turn: the message, the recorded parser object (`report_ask`), the `Held report` line the
engine printed into that parse (`held`), and what the turn must give (`expect`: `route_params` in names as shown,
`ask_field`, or `refusal`). The rows of one conversation (`head`, `run`, `section`) replay in order through the
`rbot` / `world` harness of `test_report_filter_all_live.py` (the recorded object as the parse, the way
`scripts/chatbot_eval/replay.py` feeds `mock_reformulator_output`; the real engine, report lane and presenter).
Each conversation replays once per session: its outcomes are kept, and every row's test reads its own.

The prompt a row ran on is pinned by md5 (`prompt_md5`, the `test_report_filter_all.py:382-390` pattern): the
replay reads the report flags (`report_ask`, the defined keys, `said_as`) from that exact text.

Rebuild the corpus: `venv/bin/python -m tests.chatbot.golden._build_report_turns` (backend dir).
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import pathlib
from typing import Any

import pytest

from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture
from tests.chatbot.test_report_ask_lane import CUSTOMER_NAME, console_no_grant  # noqa: F401 - fixture
from tests.chatbot.test_report_filter_all import FORBIDDEN
from tests.chatbot.test_report_filter_all_live import _verdict
from tests.chatbot.test_report_semantic_carry import _ent, _pick_of, _ran, rbot, world  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_totals_filters import _kind_slot, _option_position
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "golden" / "report_turns.jsonl"
RECORDED = HERE / "golden" / "report_turns.recorded.jsonl"
PLANS = HERE.parents[2] / "documentation" / "plans" / "chatbot"
PROMPTS = {  # md5 -> the pinned text (never edited in place)
    "289da7e56130a489ecb624031996acc2": "prompt-report-filter-all.txt",
    "d29c19830b22aa47403a88ddcb8e817d": "prompt-prod-v72-d29c1983.txt",
}
HELD_PREFIX = "Held report"  # turn/context.py HELD_REPORT_PREFIX
EXPECTATION_HEAD, SEED_HEAD = "4c1b310a", "2a8e6f7c"
STEPS_PER_RUN, RUNS_PER_HEAD = 26, 3
STEP18_RERUN = 3  # the step-18 turns re-run on 289da7e5 (crew, plan 3.2.1)

ROWS: list[dict[str, Any]] = [json.loads(ln) for ln in CORPUS.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _key(r: dict[str, Any]) -> tuple[str, str, str, Any]:
    return (r["head"], r["run"], r["step"], r["turn_id"])


def _conv(r: dict[str, Any]) -> tuple[str, str, str]:
    return (r["head"], r["run"], r["section"])


def _id(r: dict[str, Any]) -> str:
    return f"{r['head']}-r{r['run']}-s{r['step']}"


CONVERSATIONS: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
for _r in ROWS:
    CONVERSATIONS[_conv(_r)].append(_r)


# ------------------------------------------------------------------------------------------ the corpus file


def test_corpus_file_has_every_expectation_turn() -> None:
    keys = [_key(r) for r in ROWS]
    assert len(keys) == len(set(keys)), [k for k, n in collections.Counter(keys).items() if n > 1]
    live = [r for r in ROWS if r["head"] == EXPECTATION_HEAD]
    assert len(live) == STEPS_PER_RUN * RUNS_PER_HEAD and all(r["role"] == "expectation" for r in live), len(live)
    assert {r["run"] for r in live} == {"1", "2", "3"}
    if not RECORDED.exists():
        pytest.skip("the step-18 re-run on 289da7e5 arrives with crew's extraction (report_turns.recorded.jsonl)")
    rerun = [r for r in ROWS if r["role"] == "expectation" and r["step"].startswith("18.") and r["head"] not in (EXPECTATION_HEAD, SEED_HEAD)]
    assert len(rerun) == STEP18_RERUN and {r["prompt_md5"] for r in rerun} == {"289da7e56130a489ecb624031996acc2"}, rerun


def test_every_row_carries_its_held_line() -> None:
    for r in ROWS:
        assert "held" in r, _id(r)
        held = r["held"]
        if held is None:
            continue
        assert isinstance(held, str) and held.startswith(HELD_PREFIX) and "\n" not in held, (_id(r), held)
        tail = held.partition("): ")[2] if held.startswith(HELD_PREFIX + " (") else held.partition(": ")[2]
        assert json.loads(tail) == r["held_spec"], _id(r)


def test_seed_rows_are_never_expectations() -> None:
    seeds = [r for r in ROWS if r["head"] == SEED_HEAD]
    assert len(seeds) == STEPS_PER_RUN * RUNS_PER_HEAD, len(seeds)
    assert all(r["role"] == "seed" and r["expect"] is None for r in seeds)
    assert all(r["head"] != SEED_HEAD for r in ROWS if r["role"] == "expectation")


def test_every_expectation_row_names_one_outcome_and_a_pinned_prompt() -> None:
    for r in ROWS:
        assert r["prompt_md5"] in PROMPTS, (_id(r), r["prompt_md5"])
        if r["role"] != "expectation" or r.get("skip"):
            continue
        assert isinstance(r["expect"], dict) and len(r["expect"]) == 1, _id(r)
        assert set(r["expect"]) <= {"route_params", "ask_field", "refusal"}, _id(r)
        assert not r.get("xfail") or r["xfail"].startswith(("REPORT-SPEC-W3", "REPORT-SPEC-W4")), (_id(r), r["xfail"])


@pytest.mark.parametrize("md5,name", sorted(PROMPTS.items()))
def test_the_pinned_prompts_are_unchanged(md5, name) -> None:
    assert hashlib.md5((PLANS / name).read_bytes()).hexdigest() == md5, name


# ------------------------------------------------------------------------------------------ replay


_OUTCOMES: dict[tuple[str, str, str], dict[tuple[str, str, str, Any], dict[str, Any]]] = {}


def _pin_prompt(monkeypatch, md5: str) -> None:
    """The harness config (`rbot`: flag on, stub text) with the report flags of the pinned text."""
    text = (PLANS / PROMPTS[md5]).read_text(encoding="utf-8")
    assert parser_mod.REPORT_ASK_LINE in text, PROMPTS[md5]
    current = parser_mod.resolve_config

    def _cfg(*a, **k):
        cfg = current(*a, **k)
        return dataclasses.replace(
            cfg, report_ask=True, report_ask_defined=parser_mod.report_ask_defined_in(text),
            said_as=parser_mod.SAID_AS_WORD in text,
        )

    monkeypatch.setattr(parser_mod, "resolve_config", _cfg)


def _names(rbot, args: dict[str, Any]) -> dict[str, Any]:
    """Route args with ids turned back into the names a row states (company name, brand code, agent name)."""
    from app.models.company import Company
    from app.models.product import Brand
    from app.models.sales_agent import SalesAgent

    db = rbot.console.session_factory()
    try:
        out = dict(args)
        if args.get("company"):
            out["company"] = db.get(Company, args["company"]).name
        for key, model, col in (("brand_ids", Brand, "brand_code"), ("sales_agent_ids", SalesAgent, "sales_agent")):
            if args.get(key):
                out[key] = sorted(getattr(db.get(model, i), col) for i in args[key])
        return out
    finally:
        db.close()


def _entities(row: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for e in (row.get("parse") or {}).get("entities") or []:
        ent = _ent(e["raw"], "brand", e.get("canonical_code", e["raw"].upper()), e.get("kind_said"))
        ent.update({k: e[k] for k in ("said_as", "said_as_text") if k in e})
        out.append(ent)
    return out


def _world(value: Any) -> Any:
    if isinstance(value, list):
        return [CUSTOMER_NAME if v == "__customer__" else v for v in value]
    return value


def _say(rbot, row: dict[str, Any]) -> dict[str, Any]:
    parse = row.get("parse") or {}
    flat = dict(parse.get("flat") or {})
    if parse.get("pick_option"):
        pos = _option_position(_kind_slot(rbot), parse["pick_option"])
        flat.update(open_question_answer=_pick_of(pos), reference_positions=[pos])
    if "setup" in row:
        setup = {k: _world(v) for k, v in row["setup"].items()}
        text, calls = rbot.say(_verdict(setup), "setup: the held report of the gold row")
        assert _ran(calls), f"{_id(row)} setup did not run: {text!r}"
    before = len(rbot.blocks)
    text, calls = rbot.say(_verdict(row["report_ask"] or {}, *_entities(row), **flat), row["text"])
    block = rbot.blocks[before] if len(rbot.blocks) > before else ""
    held = [ln for ln in block.splitlines() if ln.startswith(HELD_PREFIX)]
    ran = _ran(calls)
    return {
        "text": text,
        "held": held,
        "route_params": _names(rbot, ran[-1]) if ran else None,
        "ask_field": None if ran else _kind_slot(rbot).get("asking"),
    }


def _outcome(request, row: dict[str, Any]) -> dict[str, Any]:
    conv = _conv(row)
    if conv not in _OUTCOMES:
        rbot = request.getfixturevalue("rbot")
        request.getfixturevalue("world")
        monkeypatch = request.getfixturevalue("monkeypatch")
        md5s = {r["prompt_md5"] for r in CONVERSATIONS[conv]}
        assert len(md5s) == 1, f"{conv}: one conversation, one prompt: {md5s}"
        _pin_prompt(monkeypatch, md5s.pop())
        _OUTCOMES[conv] = {_key(r): _say(rbot, r) for r in CONVERSATIONS[conv]}
    return _OUTCOMES[conv][_key(row)]


ASSERTED = [r for r in ROWS if r["role"] == "expectation"]


def _param(r: dict[str, Any]) -> Any:
    marks = []
    if r.get("skip"):
        marks.append(pytest.mark.skip(reason=r["skip"]))
    return pytest.param(r, id=_id(r), marks=marks)


@pytest.mark.parametrize("row", [_param(r) for r in ASSERTED])
def test_engine_prints_the_recorded_held_line(request, row) -> None:
    """The `Held report` line the engine prints for this turn (from the turns before it) is the recorded one: an
    engine change that moves what the parser reads shows here first (plan 1.5, step 11)."""
    if not row["held_recorded"]:
        pytest.skip("held line pending crew's extraction (report_turns.recorded.jsonl)")
    got = _outcome(request, row)["held"]
    want = [row["held"]] if row["held"] is not None else []
    assert got == want, f"{_id(row)}: engine printed {got}, recorded {want}"


def _same(want: Any, got: Any) -> bool:
    if want in (None, []):
        return got in (None, [], "")
    if isinstance(want, list):
        return sorted(want) == sorted(got or [])
    return want == got


@pytest.mark.parametrize("row", [_param(r) for r in ASSERTED])
def test_report_golden(request, row) -> None:
    if row.get("xfail"):
        request.applymarker(pytest.mark.xfail(reason=row["xfail"], strict=True))
    out = _outcome(request, row)
    where = f"{_id(row)} {row['text']!r}"
    assert FORBIDDEN not in out["text"], f"{where}: {out['text']!r}"
    expect = row["expect"]
    if "route_params" in expect:
        got = out["route_params"]
        assert got is not None, f"{where}: no report ran: {out['text']!r}"
        bad = {k: (v, got.get(k)) for k, v in expect["route_params"].items() if not _same(v, got.get(k))}
        assert not bad, f"{where}: (want, got) {bad}; args {got}"
    elif "ask_field" in expect:
        assert out["route_params"] is None, f"{where}: a report ran: {out['route_params']}"
        assert out["ask_field"] == expect["ask_field"], f"{where}: asked {out['ask_field']!r}: {out['text']!r}"
    else:
        assert out["route_params"] is None and expect["refusal"] in out["text"], f"{where}: {out['text']!r}"


def test_report_golden_counts() -> None:
    """The numbers the PR posts."""
    exp = [r for r in ROWS if r["role"] == "expectation"]
    print(f"rows={len(ROWS)} expectation={len(exp)} seed={sum(r['role'] == 'seed' for r in ROWS)} "
          f"xfail={sum(bool(r.get('xfail')) for r in exp)} skip={sum(bool(r.get('skip')) for r in exp)}")
    assert exp
