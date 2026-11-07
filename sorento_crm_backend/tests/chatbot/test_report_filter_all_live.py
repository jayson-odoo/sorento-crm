"""REPORT-FILTER-ALL: every parser object crew recorded on the 6 LIVE hand-test runs of 7 Nov (heads 2a8e6f7c and
4c1b310a, 3 runs each, Gemini flash-lite, prompt 289da7e5), replayed in order through the engine with the report each
turn must give (owner, 7 Nov ~16:00: no later round may break an old turn).

Source: crew's two crew-notes on #2209, "crew live-run recorded parser objects ... part aa / ab", committed as
`fixtures/report_filter_all_live_7nov.jsonl` (sales agent names mapped to the test world's AGENT A; the open question's
option list dropped). A turn record holds the message text and the `report_ask` object only, so each verdict mirrors
the object onto the flat fields the live parser fills beside it (basis, period, company, axis).

Not replayed here:
* step 18 (the v72 text, no ALL): the bridge `_legacy_all` it exercises goes once 289da7e5 is published;
* step 19 and step 1's Dealer / Project split: moved to their own lane (owner, 7 Nov ~16:00).
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture
from tests.chatbot.test_report_ask_lane import console_no_grant  # noqa: F401 - fixture
from tests.chatbot.test_report_filter_all import FORBIDDEN, _said, all_on  # noqa: F401 - fixture + helpers
from tests.chatbot.test_report_semantic_carry import _pick_of, _ran, _v, rbot, world  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_totals_filters import _kind_slot, _option_position
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures

ROWS = [
    json.loads(line)
    for line in (pathlib.Path(__file__).parent / "fixtures" / "report_filter_all_live_7nov.jsonl").read_text().splitlines()
    if line.strip()
]
RUNS = sorted({(r["head"], r["run"]) for r in ROWS})
SEP_FROM = "2026-09-01"

# What each turn gives, from the hand test's Expected (laneboard/scripts/2209.md): company / brand / agent filter on
# (True) or off (False), None = the step does not decide it (the object's own call, e.g. step 0 with or without a brand).
FILTERS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14a", "14b", "14c", "14d"]
EXPECT: dict[str, dict[str, Any]] = {
    "0": dict(company=True, brand=None, agent=False, group_by="sales_agent"),
    "1": dict(company=True, brand=True, agent=False),
    "2": dict(company=True, brand=False, agent=False),
    "3": dict(company=True, brand=True, agent=False),
    "4": dict(company=True, brand=False, agent=False),
    "5": dict(company=True, brand=False, agent=True, group_by=None),
    "6": dict(company=True, brand=False, agent=False),
    "7": dict(company=False, brand=False, agent=False),
    "8": dict(company=True, brand=True, agent=False),
    "9": dict(company=True, brand=True, agent=False),
    "10": dict(company=True, brand=True, agent=True, group_by=None),
    "11": dict(company=False, brand=False, agent=False),
    "12": dict(company=True, brand=True, agent=False),
    "13": dict(company=False, brand=False, agent=False),
    "14a": dict(company=True, brand=True, agent=False),
    "14b": dict(company=False, brand=False, agent=False),
    "14c": dict(company=True, brand=None, agent=False),
    "14d": dict(company=False, brand=False, agent=False),
}
# Parser misses, pinned as the code applies them (the object is final). Step 11 on 4c1b310a: all three runs wrote
# company "Sorento" beside ALL in every list; 2a8e6f7c's three wrote company "ALL". The user block the parser got is
# byte-identical on both heads for the same history (replayed 7 Nov), so the flip is the model's, not the code's.
PARSER_MISS = {("4c1b310a", run, "11"): dict(company=True) for run in ("1", "2", "3")}


def _rows(head: str, run: str) -> dict[str, dict[str, Any]]:
    return {r["step"]: r for r in ROWS if r["head"] == head and r["run"] == run}


def _verdict(ra: dict[str, Any], *entities: dict[str, Any], **over: Any) -> dict[str, Any]:
    """The recorded object (absent keys are null / []) with the flat fields the live parser fills beside it."""
    ra = {
        "kind": "sales", "frame": None, "basis": None, "date_from": None, "date_to": None, "group_by": None,
        "top_n": None, "measure": None, "channel": None, "company": None, "sales_agents": [], "account_types": [],
        "brands": [], "categories": [], "customers": [], "products": [], "brand_or_account_type": [],
        "company_or_brand": [], **ra,
    }
    company = ra["company"] if ra["company"] not in (None, "ALL") else None
    flat = dict(
        basis=ra["basis"], group_by=ra["group_by"], sales_company=company, domain_in_message=True,
        date_filter_start=ra["date_from"], date_filter_end=ra["date_to"],
    )
    return _v("sales_report", ra, *entities, **{**flat, **over})


def _check(head: str, run: str, step: str, text: str, calls: Any) -> None:
    want = {**EXPECT[step], **PARSER_MISS.get((head, run, step), {})}
    where = f"{head} run {run} step {step}"
    assert FORBIDDEN not in text, f"{where}: {text!r}"
    ran = _ran(calls)
    assert ran, f"{where}: no report ran: {text!r}"
    args = ran[-1]
    assert args.get("basis") == "delivered" and args.get("date_from") == SEP_FROM, f"{where}: {args}"
    for key, arg in (("company", "company"), ("brand", "brand_ids"), ("agent", "sales_agent_ids")):
        if want.get(key) is not None:
            assert bool(args.get(arg)) is want[key], f"{where}: {key} {'missing' if want[key] else 'kept'}: {args}"
    if want.get("company"):
        assert args.get("company") == DEFAULT_COMPANY_ID, f"{where}: {args}"
    if "group_by" in want:
        assert args.get("group_by") == want["group_by"], f"{where}: {args}"


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("head,run", RUNS, ids=[f"{h}-r{r}" for h, r in RUNS])
def test_live_step0_every_agent_breakdown(rbot, world, head, run) -> None:
    r = _rows(head, run)["0"]
    text, calls = rbot.say(_verdict(r["report_ask"]), r["text"])
    _check(head, run, "0", text, calls)


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("head,run", RUNS, ids=[f"{h}-r{r}" for h, r in RUNS])
def test_live_steps1_to_14_every_filter_turn_in_order(rbot, world, head, run) -> None:
    rows = _rows(head, run)
    for step in FILTERS:
        r = rows[step]
        text, calls = rbot.say(_verdict(r["report_ask"]), r["text"])
        _check(head, run, step, text, calls)


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("head,run", RUNS, ids=[f"{h}-r{r}" for h, r in RUNS])
def test_live_steps15_to_17_company_or_brand_then_brand_then_split(rbot, world, head, run) -> None:
    """Step 15's object writes company Sorento + brand SORENTO for a bare "Sorento"; live asked company, brand or both
    from the entity's `said_as` null (not recorded: rebuilt as K16 does). Step 16 "brand" is the brand pick; step 17
    splits by channel. Brand SORENTO across every company throughout."""
    rows = _rows(head, run)
    r15, r16, r17 = rows["15"], rows["16"], rows["17"]
    text, calls = rbot.say(_verdict(r15["report_ask"], _said("Sorento", None, "")), r15["text"])
    slot = _kind_slot(rbot)
    assert not _ran(calls) and slot.get("asking") == "kind", f"{head} r{run} step 15: {text!r}"
    pos = _option_position(slot, "brand")
    v16 = _verdict(r16["report_ask"], open_question_answer=_pick_of(pos), reference_positions=[pos], continuation=True,
                   entity_op="reuse", domain_in_message=False)
    text, calls = rbot.say(v16, r16["text"])
    args = _ran(calls)[-1] if _ran(calls) else {}
    assert args.get("brand_ids") and not args.get("company") and args.get("basis") == "delivered", f"16: {text!r} {args}"
    text, calls = rbot.say(_verdict(r17["report_ask"]), r17["text"])
    assert FORBIDDEN not in text, text
    args = _ran(calls)[-1] if _ran(calls) else {}
    assert args.get("group_by") == "channel" and args.get("brand_ids") and not args.get("company"), f"17: {text!r} {args}"


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("head,run", RUNS, ids=[f"{h}-r{r}" for h, r in RUNS])
def test_live_step20_a_bare_sales_ask_asks_its_basis(rbot, world, head, run) -> None:
    """Owner 7 Nov ~14:00: "Sorento brand sales September 2026" asks the basis (the object wrote none)."""
    r = _rows(head, run)["20"]
    text, calls = rbot.say(_verdict(r["report_ask"]), r["text"])
    assert not _ran(calls) and "Invoiced, delivered, ordered or outstanding?" in text, text


def test_live_fixture_holds_all_156_turns_of_the_six_runs() -> None:
    assert len(ROWS) == 156 and len(RUNS) == 6, (len(ROWS), RUNS)
