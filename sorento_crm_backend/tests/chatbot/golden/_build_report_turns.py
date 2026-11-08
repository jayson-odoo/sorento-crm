"""Build `report_turns.jsonl`, the L1 report corpus (REPORT-SPEC-W1, `ARCH-report-engine-7nov.md` 3.0 / 3.2).

usage (cwd = sorento_crm_backend): SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m tests.chatbot.golden._build_report_turns

Inputs, nothing else:
* the recorded turns: `report_turns.recorded.jsonl` (crew's plan 3.2.1 extraction: the 156 #2209 live turns plus the
  step-18 re-run, each with `turn_id` and the `Held report` line the engine printed), or, until it lands, the
  committed `fixtures/report_filter_all_live_7nov.jsonl` (same turns, no `held` / `turn_id`: `held_recorded` false);
* the expectations already pinned in `test_report_filter_all_live.py` (`EXPECT`, `PARSER_MISS`, and steps 15-17
  and 20 as that file asserts them), which are the owner's Expected list of the 7 Nov 04:41 crew-handtest on #2209;
* the L0 gold rows whose engine outcome an existing test asserts (`GOLD` below, with the test that asserts it).

No expectation is new. `expect.route_params` names values as shown (company name, brand code, agent name), never
ids, so the agent's `crm_report_ask` (W5) can replay the same rows; an absent key is a slot the step does not decide.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
PLANS = BACKEND.parent / "documentation" / "plans" / "chatbot"
RECORDED = HERE / "report_turns.recorded.jsonl"
FIXTURE = HERE.parent / "fixtures" / "report_filter_all_live_7nov.jsonl"
GOLD_DIR = BACKEND / "scripts" / "chatbot_eval" / "gold"
OUT = HERE / "report_turns.jsonl"

EXPECTATION_HEAD = "4c1b310a"  # app code == merged head f3d4789f (plan 3.2.1)
SEED_HEAD = "2a8e6f7c"  # +45/-15 app lines from it: seed rows only
CANDIDATE = "prompt-report-filter-all.txt"  # 289da7e5, the ALL prompt the runs used
V72 = "prompt-prod-v72-d29c1983.txt"  # crew's v74 = the production v72 text: step 18 of the 156 turns
SEP = {"basis": "delivered", "date_from": "2026-09-01", "date_to": "2026-09-30"}
SORENTO, AGENT = "Sorento", "AGENT A"

# The conversations of one run (the hand-test sections; each starts fresh).
SECTION = {"0": "0", "15": "15", "16": "15", "17": "15", "18.1": "18", "18.2": "18", "18.4": "18", "19": "19", "20": "19"}
# The brand list each brand-on step names (the owner's Expected: "Brand SORENTO", step 8 "SORENTO and CABANA").
BRANDS = {"8": ["SORENTO", "CABANA"]}
# Step 18 repeats steps 1, 2 and 4 (owner's Steps, 18).
REPEATS = {"18.1": "1", "18.2": "2", "18.4": "4"}

XFAIL_W3 = "REPORT-SPEC-W3"
# Step 18 on the v72 text (crew Q1 (a), 8 Nov): steps 1 / 2 / 4's expectation, xfail where today's engine misses.
V72_MISS = {
    s: f"{XFAIL_W3}: the v72 text has no ALL, so the clear leaves `brands` out and the held brand stays "
       "(owner Expected 18: the fix needs the new prompt)"
    for s in ("18.2", "18.4")
}
STEP19_PENDING = "the flat parse (the supplier entity) is not on record for this turn, so it cannot be replayed"


def md5(name: str) -> str:
    return hashlib.md5((PLANS / name).read_bytes()).hexdigest()


def held_spec(held: str | None) -> dict[str, Any] | None:
    if held is None:
        return None
    tail = held.partition("): ")[2] if held.startswith("Held report (") else held.partition(": ")[2]
    return json.loads(tail)


def _route(step: str, want: dict[str, Any]) -> dict[str, Any]:
    """`EXPECT[step]` (company / brand / agent on or off, None: not decided) as route params in names."""
    out: dict[str, Any] = dict(SEP)
    if want.get("company") is not None:
        out["company"] = SORENTO if want["company"] else None
    if want.get("brand") is not None:
        out["brand_ids"] = BRANDS.get(step, ["SORENTO"]) if want["brand"] else []
    if want.get("agent") is not None:
        out["sales_agent_ids"] = [AGENT] if want["agent"] else []
    if "group_by" in want:
        out["group_by"] = want["group_by"]
    return out


def _expect(step: str) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """(expect, parse extras, skip reason) for one hand-test step, as `test_report_filter_all_live.py` pins it."""
    from tests.chatbot.test_report_filter_all_live import EXPECT

    base = REPEATS.get(step, step)
    if base in EXPECT:
        return {"route_params": _route(base, EXPECT[base])}, {}, None
    if step == "15":  # the bare "Sorento": one company-or-brand question (`said_as` null, rebuilt as K16 does)
        return {"ask_field": "kind"}, {"entities": [{"raw": "Sorento", "said_as": None, "said_as_text": ""}]}, None
    if step == "16":  # "brand" picks the brand option of step 15's question
        flat = {"continuation": True, "entity_op": "reuse", "domain_in_message": False}
        return {"route_params": {**SEP, "company": None, "brand_ids": ["SORENTO"]}}, {"pick_option": "brand", "flat": flat}, None
    if step == "17":
        return {"route_params": {**SEP, "company": None, "brand_ids": ["SORENTO"], "group_by": "channel"}}, {}, None
    if step == "20":  # owner 7 Nov ~14:00: the object writes no basis, so the basis is asked
        return {"ask_field": "basis"}, {}, None
    if step == "19":  # crew 8 Nov: run 3's parse is the expectation (supplier outstanding POs); see STEP19
        return None, {}, STEP19_PENDING
    raise KeyError(step)


# Owner Expected 19: that supplier's open purchase orders (crew 8 Nov: run 3's parse, supplier 400-L005, is the
# expectation; runs 1 and 2 read it as an incoming / brand ask).
PO_TOOL = "crm_procurement_po_placed_list"
STEP19_EXPECT: dict[str, Any] = {"route_params": {"supplier_ids": ["400-L005"]}}


def _live_rows() -> tuple[list[dict[str, Any]], bool]:
    from tests.chatbot.test_report_filter_all_live import PARSER_MISS

    def _load(path: pathlib.Path) -> list[dict[str, Any]]:
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []

    # Crew's extraction rows replace the fixture's turn of the same (head, run, step); the rest keep the fixture's
    # (no `held` / `turn_id` yet: `held_recorded` false). Extraction rows of a new head (the step-18 re-run) append.
    recorded = {(r["head"], str(r["run"]), str(r["step"])): r for r in _load(RECORDED)}
    rows = [recorded.pop((r["head"], str(r["run"]), str(r["step"])), r) for r in _load(FIXTURE)] + list(recorded.values())
    out = []
    for r in rows:
        head, run, step = r["head"], str(r["run"]), str(r["step"])
        prompt = r.get("prompt_md5") or md5(V72 if step.startswith("18.") and head in (EXPECTATION_HEAD, SEED_HEAD) else CANDIDATE)
        expect, parse, skip = _expect(step)
        if head == SEED_HEAD:  # seed rows are replayed for their state, never asserted
            expect, skip = None, None
        row: dict[str, Any] = {
            "head": head, "run": run, "step": step, "section": SECTION.get(step, "1"),
            "turn_id": r.get("turn_id"), "text": r["text"],
            "held": r.get("held"), "held_spec": held_spec(r.get("held")), "held_recorded": "held" in r,
            "report_ask": r.get("report_ask"),
            "open_question": r.get("open_question", r.get("open_question_kind")),
            "prompt_md5": prompt, "role": "seed" if head == SEED_HEAD else "expectation",
            "expect": expect,
        }
        if parse:
            row["parse"] = parse
        if skip:
            row["skip"] = skip
        if step in V72_MISS and head == EXPECTATION_HEAD and prompt == md5(V72):
            row["xfail"] = V72_MISS[step]
        if (head, run, step) in PARSER_MISS:
            row["xfail"] = f"{XFAIL_W3}: the parser kept company Sorento beside ALL in every list (PARSER_MISS)"
        if r.get("parser_raw"):  # the whole recorded parse: replayed as it is (replay.py's recorded-parse mode)
            row["parser_raw"] = r["parser_raw"]
            if step == "19" and head != SEED_HEAD:
                row.pop("skip", None)
                row["expect"], row["tool"] = STEP19_EXPECT, PO_TOOL
                if run != "3":
                    row["xfail"] = f"{XFAIL_W3}: the parse read LASHIQI as {r['parser_raw']['entities'][0]['hint']} / {r['parser_raw']['domain_hint']}, not the supplier's outstanding POs (crew 8 Nov)"
        if r.get("note"):
            row["note"] = r["note"]
        out.append(row)
    return out, recorded


# L0 gold rows converted to L1: the gold object replayed as the parse, with the outcome the named test asserts.
# `setup`: the held report the gold row's `held` line names, run first as an object in the test world's names
# (gold's masked zqa / zqc / zqd are the world's agent, category and customer).
WORLD = {"zqa": AGENT, "zqc": "ZZT CATEGORY", "zqd": "__customer__"}
GOLD = {
    "fa-16": ("parser_report_filter_all", "test_report_filter_all.py::test_fa16_fa20_the_gold_clear_all_object_clears_company_and_channel_too",
              {"route_params": {"basis": "delivered", "date_from": "2026-09-01", "group_by": "month", "company": None, "channel": None}}, {}),
    "fa-20": ("parser_report_filter_all", "test_report_filter_all.py::test_fa16_fa20_the_gold_clear_all_object_clears_company_and_channel_too",
              {"route_params": {"basis": "delivered", "date_from": "2026-09-01", "group_by": "month", "company": None, "channel": None}}, {}),
    "fa-36": ("parser_report_filter_all", "test_report_filter_all.py::test_fa36_the_gold_step1_object_is_the_dealer_project_breakdown",
              {"route_params": {"company": SORENTO, "brand_ids": ["SORENTO"], "group_by": "channel"}},
              {"entities": [{"raw": "sorento", "canonical_code": "SORENTO", "kind_said": "brand"}]}),
    "tf-13": ("parser_report_totals_filters", "test_report_totals_filters_ht1.py::test_g4_tf13_a_bare_name_with_said_as_null_asks_one_question_and_runs_nothing (docstring: a null basis asks the basis first)",
              {"ask_field": "basis"}, {"entities": [{"raw": "Sorento", "canonical_code": "SORENTO", "said_as": None}]}),
    "tf-29": ("parser_report_totals_filters", "test_report_totals_filters_ht1.py::test_g4_tf29_an_object_company_beside_said_as_brand_is_applied_as_written (docstring: brand only when the parse leaves the company null, HT1-3)",
              {"route_params": {"basis": "delivered", "company": None, "brand_ids": ["SORENTO"]}},
              {"entities": [{"raw": "sorento", "canonical_code": "SORENTO", "kind_said": "brand", "said_as": "brand"}]}),
    "tf-30": ("parser_report_totals_filters", "test_report_totals_filters_ht1.py::test_g4_tf30_company_and_brand_runs_both_filters",
              {"route_params": {"basis": "delivered", "company": SORENTO, "brand_ids": ["SORENTO"]}},
              {"entities": [{"raw": "sorento", "canonical_code": "SORENTO", "kind_said": "brand", "said_as": "both"}]}),
}


def _world_names(value: Any) -> Any:
    if isinstance(value, list):
        return [WORLD.get(v, v) for v in value]
    return WORLD.get(value, value)


def _gold_rows() -> list[dict[str, Any]]:
    out = []
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    for gid, (fname, source, expect, parse) in GOLD.items():
        if fname not in cache:
            lines = (GOLD_DIR / f"{fname}.jsonl").read_text(encoding="utf-8").splitlines()
            cache[fname] = {r["id"]: r for r in map(json.loads, filter(str.strip, lines))}
        g = cache[fname][gid]
        spec = held_spec(g["held"])
        row: dict[str, Any] = {
            "head": "gold", "run": fname, "step": gid, "section": gid, "turn_id": None, "text": g["message"],
            "held": g["held"], "held_spec": spec, "held_recorded": True,
            "report_ask": g["expect"]["report_ask"], "open_question": None, "prompt_md5": md5(CANDIDATE),
            "role": "expectation", "expect": expect, "source": source,
        }
        if spec is not None:
            row["setup"] = {k: _world_names(v) for k, v in spec.items()}
        if parse:
            row["parse"] = parse
        out.append(row)
    return out


def build() -> list[dict[str, Any]]:
    live, _recorded = _live_rows()
    return live + _gold_rows()


def main() -> None:
    rows = build()
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{OUT.name}: {len(rows)} rows, {sum(r['role'] == 'expectation' for r in rows)} expectation, "
          f"{sum(r['role'] == 'seed' for r in rows)} seed, {sum('xfail' in r for r in rows)} xfail, "
          f"{sum('skip' in r for r in rows)} skip, recorded={RECORDED.exists()}")


if __name__ == "__main__":
    main()
