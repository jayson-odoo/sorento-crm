"""Q1, near-code typos (owner ruling (a), 23 Oct 2026; crew option (d)).

When the parser corrected a TYPED code (the entity's `raw` differs from its `canonical_code` after
`token_key` folding of case, spaces and dashes), the turn asks the existing resolver about the raw
token once. Measured read-only on the lane catalogue: a code typo shows the parser's pick as a
`trgm` neighbour of the raw (11 of 11); a name or description ask never does (it resolves to
nothing, or through spec search), and a code with no typo arrives through prefix / substring.
So: the pick among the raw's trigram alternatives -> the reply is the existing did-you-mean, the
parser's pick FIRST, then the resolver's other close codes (D1's cap of 3). Anything else answers
as today. Roster picks and carried entities are never read as corrections.

Driven through `engine.run_turn` (`_r9_engine_console`: the real resolver and real trigram
neighbours over seeded catalogue rows), both paths. The rows below reproduce the measured tiers:
srttw8259gm -> SRTWT8259-GM / SRT209-GM / SRT769-GM; mcm7471gm -> MCM7721-GM / MCM7741-GM /
MCM7722-GM (the pick second in trigram order); CLB109A -> CL8109A / C9109A / CB3109A.
"""
from __future__ import annotations

import dataclasses
import uuid
from typing import Any

import pytest

from app.services.chatbot import turn_runtime
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot._r9_engine_console import EngineConsole, answer, stock
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

STOCK = "crm_inventory_stock_balance_list"
NEAR_ROWS = [
    "SRTWT8259-GM", "SRT209-GM", "SRT769-GM", "VLDWT8259-GM",
    "MCM7721-GM", "MCM7741-GM", "MCM7722-GM",
    "CL8109A", "C9109A", "CB3109A",
]
PATHS = pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])


def _seed_near_rows(session_factory) -> dict[str, str]:
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    cat = db.query(ProductCategory).filter(ProductCategory.category_code == "ZZTC-r9").one()
    uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.uom_code == "ZZTU-r9").one()
    by_uuid: dict[str, str] = {}
    for code in NEAR_ROWS:
        pid = str(uuid.uuid4())
        by_uuid[pid] = code
        db.add(Product(id=pid, product_code=code, product_name=f"ZZT {code}", category_id=cat.id,
                       base_uom_id=uom.id, list_price=1))
    db.commit()
    return by_uuid


class Resolves:
    """Every call the turn makes to the resolve route, with its tokens."""

    def __init__(self, monkeypatch) -> None:
        from app.api.v1.system import references as references_mod

        self.tokens: list[list[str]] = []
        real = references_mod.resolve_reference_post

        def spy(payload, *a, **k):
            self.tokens.append(list(payload.tokens or []))
            return real(payload, *a, **k)

        monkeypatch.setattr(references_mod, "resolve_reference_post", spy)


def _console(session_factory, monkeypatch, stub_access, phone: str, gate: bool) -> tuple[EngineConsole, Resolves]:  # noqa: F811
    c = EngineConsole(session_factory, monkeypatch, stub_access, phone=phone)
    monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: False)
    c.stock_on_hand = 12
    c.codes.update(_seed_near_rows(session_factory))
    c.uuid_of = {code: pid for pid, code in c.codes.items()}
    if gate:
        real = parser_mod.resolve_config
        monkeypatch.setattr(
            parser_mod, "resolve_config",
            lambda db, **k: dataclasses.replace(real(db, **k), state_block=True),
        )
    return c, Resolves(monkeypatch)


def _ask(raw: str, pick: str | None, gate: bool, *, current_message: bool = True) -> dict[str, Any]:
    """A stock ask naming one product: `raw` as typed, `pick` the parser's canonical_code."""
    row = {**entity(raw, hint="product", current_message=current_message), "canonical_code": pick}
    v = stock(row)
    if gate:
        v["state_changes"] = [{"op": "new_subject", "axis": None, "position": None},
                              {"op": "set", "axis": "product", "position": None}]
    return v


def _pick(gate: bool, *positions: int) -> dict[str, Any]:
    v = verdict(message_type="business_query", domain_hint="inventory", domain_in_message=False,
                reference_positions=list(positions), open_question_answer=answer("pick", picked=list(positions)))
    if gate:
        v["state_changes"] = [{"op": "pick", "axis": None, "position": p} for p in positions]
    return v


def _offered(c: EngineConsole) -> list[str]:
    question = c.stored_question or {}
    assert question.get("kind") == "product_pick", question
    return [str(o.get("code")) for o in sorted(question.get("options") or [], key=lambda o: o["position"])]


def _stocked(c: EngineConsole, since: int) -> list[str]:
    return [c.codes[p] for name, args in c.tool_calls[since:] if name == STOCK for p in args.get("product_ids") or []]


# --- the corrections: a did-you-mean with the parser's pick first --------------------------------------


@PATHS
@pytest.mark.parametrize(
    "raw,pick,others",
    [("srttw8259gm", "SRTWT8259-GM", {"SRT209-GM", "SRT769-GM"}),
     ("mcm7471gm", "MCM7741-GM", {"MCM7721-GM", "MCM7722-GM"})],
    ids=["srttw8259gm", "mcm7471gm_pick_second_in_trigram_order"],
)
def test_q1_a_corrected_typed_code_asks_did_you_mean_with_the_pick_first(
    session_factory, monkeypatch, stub_access, gate, raw, pick, others  # noqa: F811
):
    c, _ = _console(session_factory, monkeypatch, stub_access, f"+6000002{len(raw)}{int(gate)}1", gate)
    text = c.say(f"{raw} in stock?", _ask(raw, pick, gate))
    assert f'Couldn\'t find "{raw}" (product). Did you mean:' in text, text
    assert f"1. {pick}" in text, text
    offered = _offered(c)
    assert offered[0] == pick, offered
    assert set(offered[1:3]) <= others and len(offered) <= 3, offered
    assert "Stock summary" not in text, "a corrected typo was answered as if typed"
    # The only stock call is the did-you-mean's own has-it probe, over the offered codes in order.
    assert _stocked(c, 0) == offered, _stocked(c, 0)


@PATHS
def test_q1_clb109a_with_no_pick_asks_did_you_mean(session_factory, monkeypatch, stub_access, gate):  # noqa: F811
    c, _ = _console(session_factory, monkeypatch, stub_access, f"+600000231{int(gate)}", gate)
    text = c.say("CLB109A stock", _ask("CLB109A", None, gate))
    assert 'Couldn\'t find "CLB109A" (product). Did you mean:' in text, text
    assert set(_offered(c)) == {"CL8109A", "C9109A", "CB3109A"}, _offered(c)


# --- guards: answered as today ----------------------------------------------------------------------------

#: What each guard did at b173c6e8c4, per path (measured 23 Oct; HEAD before Q1 gave the same): the reply,
#: every code a stock call carried (the did-you-mean's has-it probe included) and the resolve calls made.
B173_Q1: dict[str, Any] = {'carried_entity|old_path': {'reply': 'Stock summary for the requested products.\n'
                                      '\n'
                                      '1. *Product Code:* SRTWT8259-GM\n'
                                      '*Total:* 12\n'
                                      '*BRW:* 12\n'
                                      '\n'
                                      '_Data last updated: 29/09/2026 01:00:00_',
                             'resolve_calls': 1,
                             'stocked': ['SRTWT8259-GM']},
 'carried_entity|state_path': {'reply': 'Stock summary for the requested products.\n'
                                        '\n'
                                        '1. *Product Code:* SRTWT8259-GM\n'
                                        '*Total:* 12\n'
                                        '*BRW:* 12\n'
                                        '\n'
                                        '_Data last updated: 29/09/2026 01:00:00_',
                               'resolve_calls': 1,
                               'stocked': ['SRTWT8259-GM']},
 'code_typed_off_the_did_you_mean|old_path': {'reply': 'Stock summary for the requested products.\n'
                                                       '\n'
                                                       '1. *Product Code:* SRT209-GM\n'
                                                       '*Total:* 12\n'
                                                       '*BRW:* 12\n'
                                                       '\n'
                                                       '_Data last updated: 29/09/2026 01:00:00_',
                                              'resolve_calls': 2,
                                              'stocked': ['SRTWT8259-GM',
                                                          'SRT209-GM',
                                                          'SRT769-GM',
                                                          'SRT209-GM']},
 'code_typed_off_the_did_you_mean|state_path': {'reply': 'Stock summary for the requested products.\n'
                                                         '\n'
                                                         '1. *Product Code:* SRT209-GM\n'
                                                         '*Total:* 12\n'
                                                         '*BRW:* 12\n'
                                                         '\n'
                                                         '_Data last updated: 29/09/2026 01:00:00_',
                                                'resolve_calls': 2,
                                                'stocked': ['SRTWT8259-GM',
                                                            'SRT209-GM',
                                                            'SRT769-GM',
                                                            'SRT209-GM']},
 'exact_case_dash|old_path': {'reply': 'Stock summary for the requested products.\n'
                                       '\n'
                                       '1. *Product Code:* SRTWT8259-GM\n'
                                       '*Total:* 12\n'
                                       '*BRW:* 12\n'
                                       '\n'
                                       '_Data last updated: 29/09/2026 01:00:00_',
                              'resolve_calls': 1,
                              'stocked': ['SRTWT8259-GM']},
 'exact_case_dash|state_path': {'reply': 'Stock summary for the requested products.\n'
                                         '\n'
                                         '1. *Product Code:* SRTWT8259-GM\n'
                                         '*Total:* 12\n'
                                         '*BRW:* 12\n'
                                         '\n'
                                         '_Data last updated: 29/09/2026 01:00:00_',
                                'resolve_calls': 1,
                                'stocked': ['SRTWT8259-GM']},
 'exact_same|old_path': {'reply': 'Stock summary for the requested products.\n'
                                  '\n'
                                  '1. *Product Code:* SRTWT8259-GM\n'
                                  '*Total:* 12\n'
                                  '*BRW:* 12\n'
                                  '\n'
                                  '_Data last updated: 29/09/2026 01:00:00_',
                         'resolve_calls': 1,
                         'stocked': ['SRTWT8259-GM']},
 'exact_same|state_path': {'reply': 'Stock summary for the requested products.\n'
                                    '\n'
                                    '1. *Product Code:* SRTWT8259-GM\n'
                                    '*Total:* 12\n'
                                    '*BRW:* 12\n'
                                    '\n'
                                    '_Data last updated: 29/09/2026 01:00:00_',
                           'resolve_calls': 1,
                           'stocked': ['SRTWT8259-GM']},
 'exact_space|old_path': {'reply': 'Stock summary for the requested products.\n'
                                   '\n'
                                   '1. *Product Code:* SRTWT8259-GM\n'
                                   '*Total:* 12\n'
                                   '*BRW:* 12\n'
                                   '\n'
                                   '_Data last updated: 29/09/2026 01:00:00_',
                          'resolve_calls': 1,
                          'stocked': ['SRTWT8259-GM']},
 'exact_space|state_path': {'reply': 'Stock summary for the requested products.\n'
                                     '\n'
                                     '1. *Product Code:* SRTWT8259-GM\n'
                                     '*Total:* 12\n'
                                     '*BRW:* 12\n'
                                     '\n'
                                     '_Data last updated: 29/09/2026 01:00:00_',
                            'resolve_calls': 1,
                            'stocked': ['SRTWT8259-GM']},
 'name_resolving_to_nothing|old_path': {'reply': "Here's what you want: basin cold tap\n"
                                                 '\n'
                                                 "Couldn't find: basin cold tap (product type). Would you "
                                                 'like me to escalate to warehouse team?',
                                        'resolve_calls': 1,
                                        'stocked': []},
 'name_resolving_to_nothing|state_path': {'reply': "Here's what you want: basin cold tap\n"
                                                   '\n'
                                                   "Couldn't find: basin cold tap (product type). Would you "
                                                   'like me to escalate to warehouse team?',
                                          'resolve_calls': 1,
                                          'stocked': []},
 'position_pick_over_the_did_you_mean|old_path': {'reply': 'Stock summary for the requested products.\n'
                                                           '\n'
                                                           '1. *Product Code:* SRTWT8259-GM\n'
                                                           '*Total:* 12\n'
                                                           '*BRW:* 12\n'
                                                           '\n'
                                                           '_Data last updated: 29/09/2026 01:00:00_',
                                                  'resolve_calls': 1,
                                                  'stocked': ['SRTWT8259-GM',
                                                              'SRT209-GM',
                                                              'SRT769-GM',
                                                              'SRTWT8259-GM']},
 'position_pick_over_the_did_you_mean|state_path': {'reply': 'Stock summary for the requested products.\n'
                                                             '\n'
                                                             '1. *Product Code:* SRTWT8259-GM\n'
                                                             '*Total:* 12\n'
                                                             '*BRW:* 12\n'
                                                             '\n'
                                                             '_Data last updated: 29/09/2026 01:00:00_\n'
                                                             '\n'
                                                             'Couldn\'t find "srttw8259gm" (product). Did '
                                                             'you mean:\n'
                                                             '2. SRT209-GM\n'
                                                             '3. SRT769-GM\n'
                                                             'Reply with a code to continue, or would you '
                                                             'like me to escalate to warehouse team?',
                                                    'resolve_calls': 2,
                                                    'stocked': ['SRTWT8259-GM',
                                                                'SRT209-GM',
                                                                'SRT769-GM',
                                                                'SRTWT8259-GM']},
 'prefix_with_colour|old_path': {'reply': 'Stock summary for the requested products.\n'
                                          '\n'
                                          '1. *Product Code:* SRTWT8259-GM\n'
                                          '*Total:* 12\n'
                                          '*BRW:* 12\n'
                                          '\n'
                                          '_Data last updated: 29/09/2026 01:00:00_',
                                 'resolve_calls': 1,
                                 'stocked': ['SRTWT8259-GM']},
 'prefix_with_colour|state_path': {'reply': 'Stock summary for the requested products.\n'
                                            '\n'
                                            '1. *Product Code:* SRTWT8259-GM\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '_Data last updated: 29/09/2026 01:00:00_',
                                   'resolve_calls': 1,
                                   'stocked': ['SRTWT8259-GM']},
 'sibling_variant_pick|old_path': {'reply': 'Stock summary for the requested products.\n'
                                            '\n'
                                            '1. *Product Code:* SRTWC286-SH\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '2. *Product Code:* SRTWC286-SH-150\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '3. *Product Code:* SRTWC286-SH-200\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '4. *Product Code:* SRTWC286-SH-NEW\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '5. *Product Code:* SRTWC286-SH-NEW-150\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '6. *Product Code:* SRTWC286-SH-NEW-200\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '7. *Product Code:* SRTWC286-SH-NEW-P\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '8. *Product Code:* SRTWC286-SH-P\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '9. *Product Code:* SRTWC286-SH-PP\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '10. *Product Code:* SRTWC286-SH-UF\n'
                                            '*Total:* 12\n'
                                            '*BRW:* 12\n'
                                            '\n'
                                            '_Data last updated: 29/09/2026 01:00:00_',
                                   'resolve_calls': 1,
                                   'stocked': ['SRTWC286-SH',
                                               'SRTWC286-SH-150',
                                               'SRTWC286-SH-200',
                                               'SRTWC286-SH-NEW',
                                               'SRTWC286-SH-NEW-150',
                                               'SRTWC286-SH-NEW-200',
                                               'SRTWC286-SH-NEW-P',
                                               'SRTWC286-SH-P',
                                               'SRTWC286-SH-PP',
                                               'SRTWC286-SH-UF',
                                               'SRTWC286-SH',
                                               'SRTWC286-SH-150',
                                               'SRTWC286-SH-200',
                                               'SRTWC286-SH-NEW',
                                               'SRTWC286-SH-NEW-150',
                                               'SRTWC286-SH-NEW-200',
                                               'SRTWC286-SH-NEW-P',
                                               'SRTWC286-SH-P',
                                               'SRTWC286-SH-PP',
                                               'SRTWC286-SH-UF']},
 'sibling_variant_pick|state_path': {'reply': 'Stock summary for the requested products.\n'
                                              '\n'
                                              '1. *Product Code:* SRTWC286-SH-150\n'
                                              '*Total:* 12\n'
                                              '*BRW:* 12\n'
                                              '\n'
                                              '_Data last updated: 29/09/2026 01:00:00_',
                                     'resolve_calls': 2,
                                     'stocked': ['SRTWC286-SH',
                                                 'SRTWC286-SH-150',
                                                 'SRTWC286-SH-200',
                                                 'SRTWC286-SH-NEW',
                                                 'SRTWC286-SH-NEW-150',
                                                 'SRTWC286-SH-NEW-200',
                                                 'SRTWC286-SH-NEW-P',
                                                 'SRTWC286-SH-P',
                                                 'SRTWC286-SH-PP',
                                                 'SRTWC286-SH-UF',
                                                 'SRTWC286-SH-150']},
 'substring_8259|old_path': {'reply': 'Stock summary for the requested products.\n'
                                      '\n'
                                      '1. *Product Code:* SRTWT8259-GM\n'
                                      '*Total:* 12\n'
                                      '*BRW:* 12\n'
                                      '\n'
                                      '_Data last updated: 29/09/2026 01:00:00_',
                             'resolve_calls': 1,
                             'stocked': ['SRTWT8259-GM']},
 'substring_8259|state_path': {'reply': 'Stock summary for the requested products.\n'
                                        '\n'
                                        '1. *Product Code:* SRTWT8259-GM\n'
                                        '*Total:* 12\n'
                                        '*BRW:* 12\n'
                                        '\n'
                                        '_Data last updated: 29/09/2026 01:00:00_',
                               'resolve_calls': 1,
                               'stocked': ['SRTWT8259-GM']}}


def _guard(name: str, c: EngineConsole, gate: bool) -> str:
    if name.startswith("exact_"):
        raw = {"exact_same": "SRTWT8259-GM", "exact_case_dash": "srtwt8259-gm", "exact_space": "SRTWT 8259GM"}[name]
        return c.say(f"{raw} stock", _ask(raw, "SRTWT8259-GM", gate))
    if name == "substring_8259":
        return c.say("8259 stock", _ask("8259", "SRTWT8259-GM", gate))
    if name == "prefix_with_colour":
        return c.say("SRTWT8259 gun metal stock", _ask("SRTWT8259 gun metal", "SRTWT8259-GM", gate))
    if name == "name_resolving_to_nothing":
        return c.say("basin cold tap stock", _ask("basin cold tap", "SRTWT8259-GM", gate))
    if name == "carried_entity":
        return c.say("stock", _ask("srttw8259gm", "SRTWT8259-GM", gate, current_message=False))
    # The did-you-mean first (the parser picked nothing), then a pick of it.
    c.say("srttw8259gm stock", _ask("srttw8259gm", None, gate))
    if name == "position_pick_over_the_did_you_mean":
        return c.say("1", _pick(gate, 1))
    if name == "code_typed_off_the_did_you_mean":
        return c.say("SRT209-GM", _ask("SRT209-GM", "SRT209-GM", gate))
    raise KeyError(name)


GUARDS = ["exact_same", "exact_case_dash", "exact_space", "substring_8259", "prefix_with_colour",
          "name_resolving_to_nothing", "carried_entity", "position_pick_over_the_did_you_mean",
          "code_typed_off_the_did_you_mean"]
#: The guards whose raw differs from the parser's pick: the rule resolves that raw ONCE more and
#: then answers as today. Every other guard makes no extra resolver call.
ONE_RAW_LOOKUP = {"substring_8259", "prefix_with_colour", "name_resolving_to_nothing"}


@PATHS
@pytest.mark.parametrize("name", GUARDS)
def test_q1_guard_answers_as_today(session_factory, monkeypatch, stub_access, gate, name):  # noqa: F811
    c, resolves = _console(session_factory, monkeypatch, stub_access, f"+60000024{GUARDS.index(name):02d}{int(gate)}", gate)
    text = _guard(name, c, gate)
    observed = {"reply": text, "stocked": _stocked(c, 0), "resolve_calls": len(resolves.tokens)}
    expected = dict(B173_Q1[f"{name}|{'state_path' if gate else 'old_path'}"])
    expected["resolve_calls"] += 1 if name in ONE_RAW_LOOKUP else 0
    assert observed == expected, observed


@PATHS
def test_q1_guard_a_sibling_variant_pick_answers_the_picked_variant(session_factory, monkeypatch, stub_access, gate):  # noqa: F811
    c, resolves = _console(session_factory, monkeypatch, stub_access, f"+600000250{int(gate)}", gate)
    c.say("srtwc286 stock", _ask("srtwc286", "SRTWC286", gate))
    text = c.say("2", _pick(gate, 2))
    observed = {"reply": text, "stocked": _stocked(c, 0), "resolve_calls": len(resolves.tokens)}
    assert observed == B173_Q1[f"sibling_variant_pick|{'state_path' if gate else 'old_path'}"], observed


# --- reviewer should-fix: the pick leads even with non-exact matches ahead of it -----------------------
#
# D1 lists a resolution's `matches` before its `alternatives` (`answer.miss_token_candidates`), so a
# pick moved to the front of the alternatives alone fell out of the offer's top 3 behind three
# non-exact matches (reviewer probe). The lane's own resolution of the raw is given three non-exact
# matches here (the grounding check's own lookup, model reads off, is left as it is).


def _with_matches_ahead(monkeypatch, c: EngineConsole, token: str, codes: list[str]) -> None:
    from app.api.v1.system import references as references_mod

    real = references_mod.resolve_reference_post

    def spy(payload, *a, **k):
        out = real(payload, *a, **k)
        if payload.semantic_fallback is not False and token in (payload.tokens or []):
            for res in out.get("resolutions") or []:
                if isinstance(res, dict) and res.get("token") == token:
                    rows = [{"entity_type": "product", "canonical_code": code, "uuid": c.uuid_of[code],
                             "match_tier": "prefix", "similarity": None, "display": {"product_code": code}}
                            for code in codes]
                    res["matches"] = rows + list(res.get("matches") or [])
                    res["resolved"] = False
        return out

    monkeypatch.setattr(references_mod, "resolve_reference_post", spy)


@PATHS
def test_q1_end_to_end_reply_offers_the_pick_first_with_non_exact_matches_ahead(session_factory, monkeypatch, stub_access, gate):  # noqa: F811
    c, _ = _console(session_factory, monkeypatch, stub_access, f"+600000260{int(gate)}", gate)
    _with_matches_ahead(monkeypatch, c, "srttw8259gm", ["VLDWT8259-GM", "MCM7721-GM", "CB3109A"])
    text = c.say("srttw8259gm in stock?", _ask("srttw8259gm", "SRTWT8259-GM", gate))
    assert 'Couldn\'t find "srttw8259gm" (product). Did you mean' in text, text
    assert _offered(c)[0] == "SRTWT8259-GM", _offered(c)


def test_q1_seam_the_pick_leads_d1s_candidates_ahead_of_non_exact_matches():
    """The reviewer's probe at the seam both paths share (`resolve_gate.pick_near_code_first` then D1's
    `miss_token_candidates` and cap of 3): three non-exact matches ahead of the pick in the raw token's
    resolution. Through run_turn the stock lane's offer drops such matches downstream (the test above),
    so the order is pinned here, where D1 reads it."""
    from app.services.chatbot.head.grounding import NEAR_PICK_KEY
    from app.services.chatbot.lanes.business import answer as answer_mod
    from app.services.chatbot.lanes.business import resolve_gate

    def row(code, tier, similarity=None):
        return {"entity_type": "product", "canonical_code": code, "uuid": f"zzt-{code}", "match_tier": tier,
                "similarity": similarity}

    pick = row("SRTWT8259-GM", "trgm", 0.5)
    parser = {"entities": [{"raw": "srttw8259gm", "hint": "product", "canonical_code": None, NEAR_PICK_KEY: pick}]}
    res = {"token": "srttw8259gm", "resolved": False, "ambiguous": False,
           "matches": [row("VLDWT8259-GM", "prefix"), row("MCM7721-GM", "prefix"), row("CB3109A", "substring")],
           "alternatives": [row("SRT209-GM", "trgm", 0.31), dict(pick)]}
    resolve_gate.pick_near_code_first(parser, {"resolutions": [res]})
    offered = [m["canonical_code"] for m in answer_mod._cap3(answer_mod.miss_token_candidates(res, ["product"]))]
    assert offered[0] == "SRTWT8259-GM", offered
    assert offered.count("SRTWT8259-GM") == 1, offered


def test_q1_seam_the_stock_probe_planner_mirrors_d1s_candidates_with_the_pick_first():
    """Reviewer should-fix: the stock-probe planner (`miss_suggest._token_candidates`, which must
    mirror the composer's own list exactly) reads the parser's pick first as D1's
    `miss_token_candidates` does, so the codes probed for stock are the codes the offer shows.
    Same resolution as the seam test above: three non-exact matches ahead of the pick."""
    from app.services.chatbot.head.grounding import NEAR_PICK_KEY
    from app.services.chatbot.lanes.business import answer as answer_mod
    from app.services.chatbot.lanes.business import miss_suggest, resolve_gate

    def row(code, tier, similarity=None):
        return {"entity_type": "product", "canonical_code": code, "uuid": f"zzt-{code}", "match_tier": tier,
                "similarity": similarity}

    pick = row("SRTWT8259-GM", "trgm", 0.5)
    parser = {"entities": [{"raw": "srttw8259gm", "hint": "product", "canonical_code": None, NEAR_PICK_KEY: pick}]}
    res = {"token": "srttw8259gm", "resolved": False, "ambiguous": False,
           "matches": [row("VLDWT8259-GM", "prefix"), row("MCM7721-GM", "prefix"), row("CB3109A", "substring")],
           "alternatives": [row("SRT209-GM", "trgm", 0.31), dict(pick)]}
    resolve_gate.pick_near_code_first(parser, {"resolutions": [res]})
    composed = [m["canonical_code"] for m in answer_mod.miss_token_candidates(res, ["product"])]
    for uuid_keyed in (False, True):
        planned = [m["canonical_code"] for m in
                   miss_suggest._token_candidates(res, allowed_types=["product"], uuid_keyed=uuid_keyed)]
        assert planned[0] == "SRTWT8259-GM", (uuid_keyed, planned)
        assert planned.count("SRTWT8259-GM") == 1, (uuid_keyed, planned)
        assert planned == composed, (uuid_keyed, planned, composed)
