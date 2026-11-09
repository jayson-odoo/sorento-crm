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

Rebuild the corpus: `SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m tests.chatbot.golden._build_report_turns` (backend dir).
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
STEP18_RERUN = 9  # the step-18 sequence (18.1 / 18.2 / 18.4) re-run x3 on 289da7e5, head f3d4789f, runs r1-r3 (crew 8 Nov)
STEP18_PENDING = "pending crew re-run x3 on 289da7e5 (dev cap)"

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
    rerun = [r for r in ROWS if r["role"] == "expectation" and r["step"].startswith("18.") and r["head"] not in (EXPECTATION_HEAD, SEED_HEAD, "gold")]
    if not rerun:
        pytest.skip(STEP18_PENDING)
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


def test_the_corpus_is_what_the_builder_writes() -> None:
    """The corpus never drifts from its sources (EXPECT / PARSER_MISS, the recorded rows, the gold rows)."""
    from tests.chatbot.golden._build_report_turns import build

    assert build() == ROWS, "report_turns.jsonl is stale: rebuild it with tests.chatbot.golden._build_report_turns"


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


REPORT_TOOL = "crm_report_ask"
SUPPLIER = ("400-L005", "LASHIQI")  # step 19's supplier as crew recorded it (code, name)
PO_GRANTS = ("purchase_orders.supplier", "purchase_orders.placed")


def _owner_world(rbot, monkeypatch) -> None:
    """The owner's hand-test user also holds the PO view and the supplier reveal (crew-handtest Setup 2), and the
    book holds step 19's supplier with one open purchase order."""
    import uuid
    from datetime import date

    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.services.chatbot import engine as engine_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import product

    current = engine_mod.check_access

    def _access(db, **kw):
        out = current(db, **kw)
        return {**out, "attributes": [*(out.get("attributes") or []), *PO_GRANTS]}

    monkeypatch.setattr(engine_mod, "check_access", _access)
    db = rbot.console.session_factory()
    try:
        # The owner's book names its brands in capitals (the recorded Held report lines print "SORENTO", "CABANA");
        # the harness world seeds "Sorento" / "Cabana". Same rows, the book's spelling.
        from app.models.product import Brand

        db.info["company_scope"] = None
        renamed = 0
        for brand in db.query(Brand).filter(Brand.brand_name.in_(("Sorento", "Cabana"))):
            brand.brand_name, renamed = brand.brand_name.upper(), renamed + 1
        assert renamed, "harness: the world seeds no Sorento / Cabana brand to spell as the book does"
        sup = Supplier(id=str(uuid.uuid4()), supplier_code=SUPPLIER[0], supplier_name=SUPPLIER[1], company_id=DEFAULT_COMPANY_ID)
        db.add(sup)
        db.flush()
        po = PurchaseOrder(id=str(uuid.uuid4()), po_number="PO-ZZT-L005", supplier_id=sup.id,
                           company_id=DEFAULT_COMPANY_ID, expected_date=date(2026, 12, 1))
        db.add(po)
        db.flush()
        db.add(PurchaseOrderLine(id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=product(db, company_id=DEFAULT_COMPANY_ID).id,
                                 qty_ordered=10, qty_received=2, line_status="open", company_id=DEFAULT_COMPANY_ID))
        db.commit()
    finally:
        db.close()


def _names(rbot, args: dict[str, Any]) -> dict[str, Any]:
    """Route args in the names a row states: company name, agent name, supplier code, and brands by NAME, upper-cased
    and de-duplicated. Brands compare by name only: the test world holds two brands named Sorento (ZZTSOR and
    SORENTO) where the owner's book holds one, so how many ids stand behind one name is not checked here."""
    from app.models.company import Company
    from app.models.procurement import Supplier
    from app.models.product import Brand
    from app.models.sales_agent import SalesAgent

    db = rbot.console.session_factory()
    db.info["company_scope"] = None  # read every company's rows (the harness session is otherwise left scoped)
    try:
        out = dict(args)
        if args.get("company"):
            out["company"] = db.get(Company, args["company"]).name
        for key, model, col in (("brand_ids", Brand, "brand_name"), ("sales_agent_ids", SalesAgent, "sales_agent"),
                                ("supplier_ids", Supplier, "supplier_code")):
            if args.get(key):  # ids reach the route upper-cased: match them case-blind
                found = {str(i).lower(): n for i, n in db.query(model.id, getattr(model, col)).all()}
                out[key] = sorted({str(found.get(str(i).lower(), i)).upper() for i in args[key]})
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
    if row.get("parser_raw"):  # the whole recorded parse, as it is (replay.py's recorded-parse mode)
        verdict = row["parser_raw"]
        if parse.get("pick_option"):  # a recorded pick is a position: it must name the same option in this world
            picked = (verdict.get("open_question_answer") or {}).get("picked") or verdict.get("reference_positions")
            assert picked and list(picked)[:1] == flat["reference_positions"], (
                f"{_id(row)}: the recorded pick {picked} is not option {parse['pick_option']!r} "
                f"(position {flat['reference_positions']}) in the harness world")
    else:
        verdict = _verdict(row["report_ask"] or {}, *_entities(row), **flat)
    text, calls = rbot.say(verdict, row["text"])
    block = rbot.blocks[before] if len(rbot.blocks) > before else ""
    held = [ln for ln in block.splitlines() if ln.startswith(HELD_PREFIX)]
    ran = [a for n, a in calls if n == row.get("tool", REPORT_TOOL)]
    return {
        "text": text,
        "held": held,
        "route_params": _names(rbot, ran[-1]) if ran else None,
        "ask_field": None if ran else _kind_slot(rbot).get("asking"),
        "tools": [n for n, _a in calls],
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
        _owner_world(rbot, monkeypatch)
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
    if row.get("held_pending"):
        pytest.skip(row["held_pending"])
    got = _outcome(request, row)["held"]
    want = [row["held"]] if row["held"] is not None else []
    if row["head"] == "gold" and want:
        # A gold row's line is the parser input it was graded on, in gold's masked names (zqa / zqc / zqd) and codes;
        # the setup holds it in the world's names, so the line is compared in those names, case-blind.
        assert len(got) == 1 and got[0].split(": ", 1)[0] == want[0].split(": ", 1)[0], (got, want)
        assert _fold(json.loads(got[0].split(": ", 1)[1])) == _fold(_gold_world(row["held_spec"])), (got, want)
        return
    assert got == want, f"{_id(row)}: engine printed {got}, recorded {want}"


def _fold(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _fold(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted(_fold(v) for v in value)
    return value.casefold() if isinstance(value, str) else value


def _gold_world(spec: dict[str, Any]) -> dict[str, Any]:
    from tests.chatbot.golden._build_report_turns import WORLD

    return {k: _world(_world_names(v, WORLD)) for k, v in spec.items()}


def _world_names(value: Any, world: dict[str, str]) -> Any:
    return [world.get(v, v) for v in value] if isinstance(value, list) else world.get(value, value)


def _same(want: Any, got: Any) -> bool:
    if want in (None, []):
        return got in (None, [], "")
    if isinstance(want, list):
        return sorted(want) == sorted(got or [])
    return want == got


@pytest.mark.parametrize("row", [_param(r) for r in ASSERTED])
def test_report_golden(request, row) -> None:
    if row.get("route_pending"):
        pytest.skip(row["route_pending"])
    if row.get("xfail"):
        request.applymarker(pytest.mark.xfail(reason=row["xfail"], strict=True))
    out = _outcome(request, row)
    where = f"{_id(row)} {row['text']!r}"
    assert FORBIDDEN not in out["text"], f"{where}: {out['text']!r}"
    expect = row["expect"]
    if "route_params" in expect:
        got = out["route_params"]
        assert got is not None, f"{where}: no {row.get('tool', REPORT_TOOL)} call (tools {out['tools']}): {out['text']!r}"
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
