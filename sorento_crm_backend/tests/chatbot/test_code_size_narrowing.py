"""CHATBOT-FAIL-TRIAGE-B2 S1, AC-6: a code head plus a size narrows the family.

"SRTWC286 250MM", "SRTWC286200MM", "srtwc286-200mm": the parser (stubbed here) emits the code head
as the product and a `size` specification (the reserved any-dimension key); the code narrows to
EVERY variant holding that size under ANY dimension key, never "Couldn't find". The family shape
mirrors backup 1028 with ZZ codes; the bare head is not itself a product code.

Postgres only; every test seeds its own chain.
"""
from __future__ import annotations

import json

import pytest

from app.models.product_spec import ProductSpecifications
from app.services.product_code_family import narrow_code_tokens_by_specs
from tests.chatbot.test_closed_lists_bare_size import WC, _ask, _ent, _seed, _spec
from tests.chatbot.test_closed_lists_bare_size import session_factory, seeded, stub_access  # noqa: F401
from tests.chatbot.conftest import system_settings_row  # noqa: F401
from tests.chatbot.test_engine import stub_parser  # noqa: F401
from tests.chatbot.test_trap_spec_search import ENDPOINT, _route_codes, client, world  # noqa: F401

ANY = ["dim_height", "dim_length", "dim_width", "trap_length"]
HEAD = "ZZSRT286"

# variant suffix -> trap_length (backup 1028 shape)
TRAP = {
    "SH": 250, "SH-150": 150, "SH-200": 200, "SH-NEW": 250, "SH-NEW-150": 150,
    "SH-NEW-200": 200, "SH-NEW-P": 180, "SH-P": 180, "SH-PP": 250, "SH-UF": 250,
}

P_TRAP_SUFFIXES = {"SH-P", "SH-NEW-P", "SH-PP"}


def _code(suffix: str) -> str:
    return f"{HEAD}-{suffix}"


def _size(value, any_keys=ANY) -> dict:
    spec = {"key": "size", "value": value, "evidence": f"{value}mm", "grounded": True}
    if any_keys is not None:
        spec["any_keys"] = list(any_keys)
    return spec


def _set_values(world, code: str, values: dict) -> None:
    row = world.db.query(ProductSpecifications).filter(ProductSpecifications.product_id == world.codes[code].id).first()
    wrapped = {k: {"value": v} for k, v in values.items()}
    if row is None:
        world.db.add(ProductSpecifications(id=__import__("uuid").uuid4().__str__(), product_id=world.codes[code].id, values=wrapped))
    else:
        row.values = wrapped
    world.db.flush()


@pytest.fixture
def srt(world):
    for suffix, length in TRAP.items():
        world.product(_code(suffix), f"SORENTO WATER CLOSET {suffix}", stock=1)
        _set_values(world, _code(suffix), {"trap_length": length, "trap_type": "p_trap" if suffix in P_TRAP_SUFFIXES else "s_trap"})
    return world


@pytest.fixture
def basin(world):
    """A fresh family whose size sits under `width`, never trap_length."""
    for suffix, width in (("A", 600), ("B", 600), ("C", 450), ("D", 300)):
        world.product(f"ZZSRB510-{suffix}", f"SORENTO BASIN {suffix}", stock=1)
        _set_values(world, f"ZZSRB510-{suffix}", {"dim_width": width, "dim_length": 100 + width // 10})
    return world


def _narrow(world, head, specs):
    return narrow_code_tokens_by_specs(world.db, tokens=[head], allowed_types=["product"], specs=specs)


def _sorted(codes):
    return None if codes is None else sorted(codes)


# 1
@pytest.mark.parametrize(
    "size, suffixes",
    [(200, ["SH-200", "SH-NEW-200"]), (250, ["SH", "SH-NEW", "SH-PP", "SH-UF"]), (150, ["SH-150", "SH-NEW-150"])],
)
def test_head_plus_size_narrows_to_every_variant_holding_it(srt, size, suffixes):
    assert _sorted(_narrow(srt, HEAD, [_size(size)])) == sorted(_code(s) for s in suffixes)


# 2
def test_size_matches_under_whichever_dimension_key_holds_it(basin):
    assert _sorted(_narrow(basin, "ZZSRB510", [_size(600)])) == ["ZZSRB510-A", "ZZSRB510-B"]


# 3
def test_a_value_under_a_non_dimension_key_does_not_match(srt):
    _set_values(srt, _code("SH-P"), {"trap_length": 180, "pack_qty": 200})
    assert _sorted(_narrow(srt, HEAD, [_size(200)])) == sorted([_code("SH-200"), _code("SH-NEW-200")])


# 4
def test_a_size_no_variant_holds_leaves_the_family_as_it_is(srt):
    assert _narrow(srt, HEAD, [_size(300)]) is None


# 5
def test_size_and_a_second_spec_and_across_specs_or_across_any_keys(srt):
    specs = [_size(250), {"key": "trap_type", "value": "s_trap", "grounded": True}]
    assert _sorted(_narrow(srt, HEAD, specs)) == sorted(_code(s) for s in ("SH", "SH-NEW", "SH-UF"))


# 6 controls
def test_control_a_named_key_still_narrows(srt):
    specs = [{"key": "trap_length", "value": 200, "grounded": True}]
    assert _sorted(_narrow(srt, HEAD, specs)) == sorted([_code("SH-200"), _code("SH-NEW-200")])


def test_control_size_without_any_keys_behaves_as_today(srt):
    assert _narrow(srt, HEAD, [_size(200, any_keys=None)]) is None


# 7
def test_resolve_route_narrows_head_plus_size(client, srt):
    body = {
        "query": "ZZSRT286 200MM",
        "tokens": [HEAD],
        "raw_tokens": [HEAD],
        "allowed_entity_types": ["product"],
        "match_mode": "and",
        "spec_fallback": True,
        "exact_match": True,
        "extracted_specs": [_size(200)],
        "dry_run": True,
    }
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 200, response.text
    assert _route_codes(response.json()) == sorted([_code("SH-200"), _code("SH-NEW-200")]), response.json()


# 8: through the turn path with a stubbed parser (resolve gate level, the harness's reach)
def test_turn_with_stubbed_parser_names_the_matching_variants(session_factory, seeded, stub_access, monkeypatch):  # noqa: F811
    rows = tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items())
    ids = _seed(session_factory, rows)
    r, calls = _ask(
        session_factory, stub_access, monkeypatch, "ZZSRT286200MM how many in stock",
        _ent(HEAD, "product"), _spec("200MM", "size", 200),
    )
    from tests.chatbot.test_closed_lists_spec_over_held import _fetched

    text = ((r.reply or {}).get("text") or "")
    assert "Couldn't find" not in text, text
    assert _fetched(calls) == sorted([ids[_code("SH-200")], ids[_code("SH-NEW-200")]]), (text, calls)


# 9 pin
def test_ground_bare_grounds_the_parsers_size_with_any_keys_and_no_candidate_line(session_factory, seeded):  # noqa: F811
    from app.models.base import set_company_scope
    from app.services.chatbot.head.bare_size import ground_bare
    from app.services.company_scope import DEFAULT_COMPANY_ID

    _seed(session_factory, tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items()))
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    entity = {"raw": "SRTWC286200MM", "hint": "specification", "spec_key": "size", "spec_value": 200, "spec_unit": "mm"}
    g = ground_bare(db, entity, [entity], None, None)
    assert g is not None and g.value == 200 and g.unit == "mm", g
    assert "trap_length" in (g.any_keys or []), g


# --------------------------------------------------------------------------- #
# AC-6 gaps: short head, head with variant letters, non-stock asks, fresh keys  #
# --------------------------------------------------------------------------- #

SHORT_HEAD = "ZZSRTWC287"  # the family prefix; "wc287" is its short form, as "wc286" is of SRTWC286-SH


@pytest.fixture
def srt_wc(world):
    """Same family shape under a longer letter prefix, so the typed "wc287" is a SUBSTRING of every code."""
    for suffix, length in TRAP.items():
        world.product(f"{SHORT_HEAD}-{suffix}", f"SORENTO WATER CLOSET {suffix}", stock=1)
        _set_values(world, f"{SHORT_HEAD}-{suffix}", {"trap_length": length})
    return world


def _wc(*suffixes):
    return sorted(f"{SHORT_HEAD}-{s}" for s in suffixes)


def _route(client, head, specs, query):
    body = {
        "query": query, "tokens": [head], "raw_tokens": [head], "allowed_entity_types": ["product"],
        "match_mode": "and", "spec_fallback": True, "exact_match": True, "extracted_specs": specs, "dry_run": True,
    }
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 200, response.text
    return _route_codes(response.json())


# a. short head
def test_short_head_unit_level_narrows_to_the_200_variants(srt_wc):
    assert _sorted(_narrow(srt_wc, "wc287", [_size(200)])) == _wc("SH-200", "SH-NEW-200")


def test_short_head_resolve_route_narrows_to_the_200_variants(client, srt_wc):
    assert _route(client, "wc287", [_size(200)], "wc287 200mm") == _wc("SH-200", "SH-NEW-200")


# b. a head that already carries variant letters
def test_head_with_variant_letters_plus_size_narrows_under_it(srt):
    assert _sorted(_narrow(srt, "ZZSRT286-SH-NEW", [_size(200)])) == [_code("SH-NEW-200")]


def test_head_with_variant_letters_plus_size_the_exact_code_holds_is_not_replaced(srt):
    """SH holds 250 itself: the exact code is its own answer, never a pick among its siblings.
    RED today: the narrowing correctly leaves it alone, but the route then answers the whole SH* family."""
    assert _narrow(srt, "ZZSRT286-SH", [_size(250)]) is None


def test_route_exact_code_that_holds_the_size_answers_that_code(client, srt):
    assert _route(client, "ZZSRT286-SH", [_size(250)], "ZZSRT286-SH 250mm") == [_code("SH")]


# d. fresh anti-overfit: dim_length and diameter, short head
@pytest.fixture
def pipes(world):
    for suffix, values in (
        ("A", {"dim_length": 900}), ("B", {"dim_length": 900, "dim_width": 50}), ("C", {"diameter": 900}),
        ("D", {"dim_length": 450}), ("E", {"diameter": 110}),
    ):
        world.product(f"ZZSRTPP731-{suffix}", f"SORENTO PIPE {suffix}", stock=1)
        _set_values(world, f"ZZSRTPP731-{suffix}", values)
    return world


PIPE_ANY = ["dim_height", "dim_length", "dim_width", "diameter"]


def test_size_under_dim_length_or_diameter_with_a_short_head(pipes):
    got = _narrow(pipes, "pp731", [_size(900, PIPE_ANY)])
    assert _sorted(got) == ["ZZSRTPP731-A", "ZZSRTPP731-B", "ZZSRTPP731-C"]


def test_size_under_dim_length_or_diameter_with_the_full_head(pipes):
    got = _narrow(pipes, "ZZSRTPP731", [_size(900, PIPE_ANY)])
    assert _sorted(got) == ["ZZSRTPP731-A", "ZZSRTPP731-B", "ZZSRTPP731-C"]


# c. non-stock asks through the turn path
def _called_ids(calls) -> set[str]:
    import json
    import re

    blob = json.dumps(calls, default=str)
    return set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", blob))


@pytest.mark.parametrize(
    "intent, domain",
    [("check_product", "master_products"), ("check_price", "master_products")],
)
def test_non_stock_ask_head_plus_size_names_the_matching_variants(session_factory, seeded, stub_access, monkeypatch, intent, domain):  # noqa: F811
    from tests.chatbot.test_closed_lists_spec_over_held import _turns
    from tests.chatbot.test_engine import _parser_output

    ids = _seed(session_factory, tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items()))
    verdict = _parser_output(
        intent_hint=intent, domain_hint=domain, user_goal=intent,
        entities=[_ent(HEAD, "product"), _spec("200MM", "size", 200)],
    )
    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [("ZZSRT286200MM", verdict)], gate=True)
    text = ((r.reply or {}).get("text") or "")
    assert "Couldn't find" not in text, text
    wanted = {ids[_code("SH-200")], ids[_code("SH-NEW-200")]}
    unwanted = {v for k, v in ids.items() if k not in (_code("SH-200"), _code("SH-NEW-200"))}
    assert wanted <= _called_ids(calls) and not (unwanted & _called_ids(calls)), (text, calls)


# --------------------------------------------------------------------------- #
# Loose family lookup (short head anywhere in a code) under brand scope         #
# --------------------------------------------------------------------------- #

SRT_BRAND_HEAD = "ZZSRTWC287"
MCH_BRAND_HEAD = "ZZMWC287"


@pytest.fixture
def two_brands(world):
    """The digits 287 under two brands, both holding 200: SORENTO ZZSRTWC287-* and MOCHA ZZMWC287-*."""
    for suffix, length in (("SH-200", 200), ("SH-250", 250), ("UF-200", 200)):
        world.product(f"{SRT_BRAND_HEAD}-{suffix}", f"SORENTO WC {suffix}", brand=world.sorento, stock=1)
        _set_values(world, f"{SRT_BRAND_HEAD}-{suffix}", {"trap_length": length})
        world.product(f"{MCH_BRAND_HEAD}-{suffix}", f"MOCHA WC {suffix}", brand=world.mocha, stock=1)
        _set_values(world, f"{MCH_BRAND_HEAD}-{suffix}", {"trap_length": length})
    return world


def _scoped_to(world, brand):
    from app.models.base import set_brand_scope

    set_brand_scope(world.db, frozenset({brand.id}))


def test_short_head_scoped_to_sorento_never_reaches_the_mocha_family_unit(two_brands):
    _scoped_to(two_brands, two_brands.sorento)
    got = _sorted(_narrow(two_brands, "wc287", [_size(200)]))
    assert got == sorted([f"{SRT_BRAND_HEAD}-SH-200", f"{SRT_BRAND_HEAD}-UF-200"]), got


def test_short_head_scoped_to_mocha_never_reaches_the_sorento_family_unit(two_brands):
    _scoped_to(two_brands, two_brands.mocha)
    got = _sorted(_narrow(two_brands, "wc287", [_size(200)]))
    assert got == sorted([f"{MCH_BRAND_HEAD}-SH-200", f"{MCH_BRAND_HEAD}-UF-200"]), got


def test_short_head_resolve_route_scoped_to_one_brand(client, two_brands):
    _scoped_to(two_brands, two_brands.sorento)
    got = _route(client, "wc287", [_size(200)], "wc287 200mm")
    assert got == sorted([f"{SRT_BRAND_HEAD}-SH-200", f"{SRT_BRAND_HEAD}-UF-200"]), got
    assert not [c for c in got if c.startswith(MCH_BRAND_HEAD)], got


def test_unscoped_short_head_reaches_both_brands_200_variants(two_brands):
    """Control: with no brand scope the two brands' 200 variants are all one family of the short head."""
    got = _sorted(_narrow(two_brands, "wc287", [_size(200)]))
    assert got == sorted(
        [f"{SRT_BRAND_HEAD}-SH-200", f"{SRT_BRAND_HEAD}-UF-200", f"{MCH_BRAND_HEAD}-SH-200", f"{MCH_BRAND_HEAD}-UF-200"]
    ), got


def test_an_anchored_hit_wins_over_a_substring_family(world):
    """"wc288" starts WC288-A / WC288-B (anchored) and sits inside ZZSRTWC288-* (substring): the anchored
    family answers alone, never a mix."""
    for code, length in (("WC288-A-200", 200), ("WC288-B-250", 250), ("ZZSRTWC288-SH-200", 200), ("ZZSRTWC288-SH-250", 250)):
        world.product(code, f"WC {code}", stock=1)
        _set_values(world, code, {"trap_length": length})
    assert _sorted(_narrow(world, "wc288", [_size(200)])) == ["WC288-A-200"]


# Turn path: a contact scoped to SORENTO, a short head, the other brand's code in no reply and no call.
def test_turn_short_head_scoped_contact_sees_only_its_brand(
    session_factory, stub_parser, stub_access, system_settings_row, monkeypatch  # noqa: F811
):
    from app.models.access import RespondContact
    from app.models.company import RespondContactCompany
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._brand_scope_seed import brand, branded_product
    from tests._pg_fixture import unique_code
    from tests.chatbot.test_engine import _parser_output
    from tests.chatbot.test_engine_company_scope import (
        _scope_envelope, _seed_workspace, _spy_resolve_kinds, _wire_business_query_turn,
    )
    from app.services.chatbot import engine as engine_mod

    db = session_factory()
    srt, mch = brand(db, "SORENTO"), brand(db, "MOCHA")
    mine, theirs = {}, {}
    for suffix, length in (("SH-200", 200), ("SH-250", 250)):
        for store, head, b in ((mine, SRT_BRAND_HEAD, srt), (theirs, MCH_BRAND_HEAD, mch)):
            p = branded_product(db, f"{head}-{suffix}", b)
            db.add(ProductSpecifications(id=str(__import__("uuid").uuid4()), product_id=p.id, values={"trap_length": {"value": length}}))
            store[suffix] = p
    db.commit()
    workspace_id = _seed_workspace(session_factory)
    contact_id = unique_code("rid")
    db = session_factory()
    row = RespondContact(
        respond_io_id=contact_id, phone_number=f"+6{unique_code('PH')}", workspace_id=workspace_id,
        session_vars={"variables": {}}, brand_ids=[srt.id], chatbot_allowed=True,
    )
    db.add(row)
    db.flush()
    db.add(RespondContactCompany(respond_contact_id=row.id, company_id=DEFAULT_COMPANY_ID))
    db.commit()

    _wire_business_query_turn(session_factory, system_settings_row, monkeypatch)
    ent = {"raw": "wc287", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}
    size = {"raw": "200mm", "hint": "specification", "spec_key": "size", "spec_value": 200, "spec_unit": "mm",
            "canonical_code": None, "current_message": True, "confident": True}
    stub_parser(_parser_output(domain_hint="inventory", entities=[ent, size]))
    stub_access()
    calls = _spy_resolve_kinds(monkeypatch)
    result = engine_mod.run_turn(
        _scope_envelope(contact_id, message_id=unique_code("msg"), text="wc287 200mm stock"), session_factory=session_factory
    )
    assert result.status == "done", result.error
    matched = {m.get("uuid") for m in (calls[-1] if calls else [])}
    text = result.reply["text"]
    assert mine["SH-200"].id in matched, (matched, text)
    assert theirs["SH-200"].id not in matched and theirs["SH-250"].id not in matched, matched
    assert MCH_BRAND_HEAD not in text, text


# --------------------------------------------------------------------------- #
# Owner ruling 31 Oct: a size no variant holds says the existing "None with ..." clause (answer.py:3098), #
# then lists the variants as today. Never "Couldn't find".                                                  #
# --------------------------------------------------------------------------- #


def _reply_for(session_factory, stub_access, monkeypatch, intent, domain, entities):  # noqa: F811
    from tests.chatbot.test_closed_lists_hidden_keys_entries import real_hidden_spec_keys
    from tests.chatbot.test_closed_lists_spec_over_held import _turns
    from tests.chatbot.test_engine import _parser_output

    _seed(session_factory, tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items()))
    verdict = _parser_output(intent_hint=intent, domain_hint=domain, user_goal=intent, entities=entities)
    stub_access(hidden_spec_keys=real_hidden_spec_keys(session_factory))
    [(r, _calls)] = _turns(session_factory, lambda: None, monkeypatch, [("x", verdict)], gate=True)
    return (r.reply or {}).get("text") or ""


ASKS = [("check_stock", "inventory"), ("check_product", "master_products")]


@pytest.mark.parametrize("intent, domain", ASKS)
def test_a_size_no_variant_holds_says_none_with_size_then_lists_the_variants(session_factory, seeded, stub_access, monkeypatch, intent, domain):  # noqa: F811
    text_ = _reply_for(session_factory, stub_access, monkeypatch, intent, domain, [_ent(HEAD, "product"), _spec("300MM", "size", 300)])
    import re

    assert re.search(r"None with size 300\s?mm", text_), text_
    assert "ZZSRT286-SH" in text_, text_  # the variants are still listed, as today
    assert "Couldn't find" not in text_, text_


@pytest.mark.parametrize("intent, domain", ASKS)
def test_a_size_some_variant_holds_has_no_none_with_clause(session_factory, seeded, stub_access, monkeypatch, intent, domain):  # noqa: F811
    text_ = _reply_for(session_factory, stub_access, monkeypatch, intent, domain, [_ent(HEAD, "product"), _spec("200MM", "size", 200)])
    assert "None with" not in text_, text_
    assert "Couldn't find" not in text_, text_


@pytest.mark.parametrize("intent, domain", ASKS)
def test_a_named_key_no_variant_holds_says_none_with_that_label(session_factory, seeded, stub_access, monkeypatch, intent, domain):  # noqa: F811
    """The clause builds `None with {label.lower()} {value}`; the label is the registry's own for the key
    (this fixture's `trap_length` label is "Trap outlet length"), the value as said (300 mm, with or without the space)."""
    text_ = _reply_for(session_factory, stub_access, monkeypatch, intent, domain, [_ent(HEAD, "product"), _spec("trap length 300mm", "trap_length", 300)])
    import re

    assert re.search(r"None with trap outlet length 300\s?mm", text_), text_
    assert "Couldn't find" not in text_, text_


# --------------------------------------------------------------------------- #
# Review round 1 (31 Oct): the clause on the HIT path, hidden keys, searchable, multi-token #
# --------------------------------------------------------------------------- #


def _rows_turn(session_factory, stub_access, monkeypatch, verdict, ids_by_code, *, hidden=None):
    """One turn like `_turns`, but the tools answer with REAL rows for the product ids asked, so the
    reply is composed on the HIT path (the stock `_turns` stub answers empty and only ever shows the miss)."""
    import json

    from app.models.base import set_company_scope  # noqa: F401
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import parser as parser_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot.test_closed_lists_hidden_keys_entries import real_hidden_spec_keys
    from tests.chatbot.test_closed_lists_spec_over_held import _message
    from tests.chatbot.test_engine import _envelope

    code_of = {v: k for k, v in ids_by_code.items()}

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=True)

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: verdict)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []

    def call_tool(self, name, args):
        calls.append((name, args))
        asked = [code_of[i] for i in (args.get("product_ids") or []) if i in code_of]
        items = [
            {
                "title": c,
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": c},
                    {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": 7},
                ],
            }
            for c in asked
        ]
        return json.dumps({"result_type": "stock", "intro": "Stock summary for the requested products.", "items": items, "has_result": bool(items)})

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call_tool)
    stub_access(hidden_spec_keys=hidden if hidden is not None else real_hidden_spec_keys(session_factory))
    r = engine_mod.run_turn(_envelope(message=_message("x", 0)), session_factory=session_factory)
    return ((r.reply or {}).get("text") or ""), calls


def _verdict(intent, domain, entities):
    from tests.chatbot.test_engine import _parser_output

    return _parser_output(intent_hint=intent, domain_hint=domain, user_goal=intent, entities=entities)


@pytest.mark.parametrize("intent, domain", ASKS)
def test_hit_path_size_no_variant_holds_says_none_with_and_lists_the_rows(session_factory, seeded, stub_access, monkeypatch, intent, domain):  # noqa: F811
    import re

    ids = _seed(session_factory, tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items()))
    text_, calls = _rows_turn(session_factory, stub_access, monkeypatch, _verdict(intent, domain, [_ent(HEAD, "product"), _spec("300MM", "size", 300)]), ids)
    assert re.search(r"None with size 300\s?mm", text_), (text_, calls)
    assert "ZZSRT286-SH" in text_, text_  # the variants' rows are there, so this IS the hit path
    assert "Couldn't find" not in text_, text_


@pytest.mark.parametrize("intent, domain", ASKS)
def test_hit_path_named_key_no_holder_says_none_with_that_label(session_factory, seeded, stub_access, monkeypatch, intent, domain):  # noqa: F811
    import re

    ids = _seed(session_factory, tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items()))
    text_, _ = _rows_turn(session_factory, stub_access, monkeypatch, _verdict(intent, domain, [_ent(HEAD, "product"), _spec("trap length 300mm", "trap_length", 300)]), ids)
    assert re.search(r"None with trap outlet length 300\s?mm", text_), text_
    assert "ZZSRT286-SH" in text_, text_


def test_hit_path_control_a_size_a_variant_holds_has_no_clause(session_factory, seeded, stub_access, monkeypatch):  # noqa: F811
    ids = _seed(session_factory, tuple((_code(s), WC, {"trap_length": v}) for s, v in TRAP.items()))
    text_, _ = _rows_turn(session_factory, stub_access, monkeypatch, _verdict("check_stock", "inventory", [_ent(HEAD, "product"), _spec("200MM", "size", 200)]), ids)
    assert "None with" not in text_ and "ZZSRT286-SH-200" in text_, text_


# S1: a non-numeric spec value is said in the customer's own word
def test_s1_non_numeric_value_no_variant_holds_reads_the_customers_word(session_factory, seeded, stub_access, monkeypatch):  # noqa: F811
    import uuid as _uuid

    from app.models.product_spec import ProductSpecRegistry

    ids = _seed(session_factory, tuple((_code(s), WC, {"trap_length": v, "trap_type": "s_trap"}) for s, v in TRAP.items()))
    db = session_factory()
    db.add(ProductSpecRegistry(
        id=str(_uuid.uuid4()), spec_key="trap_type", label="Trap", data_type="enum", allowed_values=["s_trap", "p_trap"],
        synonyms={"p_trap": ["p trap"], "s_trap": ["s trap"]},
    ))
    db.commit()
    ent = _spec("p trap", "trap_type", "p_trap")  # no variant of the family is a p trap
    text_, _ = _rows_turn(session_factory, stub_access, monkeypatch, _verdict("check_stock", "inventory", [_ent(HEAD, "product"), ent]), ids)
    assert "None with" in text_, text_
    assert "p_trap" not in text_, text_  # the stored value never reaches the customer
    assert "p trap" in text_, text_  # the customer's own word does


# ---- S2: more than one code token, and a family past the cap

HEAD_B = "ZZSRT640"


def _none(world, tokens, specs):
    out: list = []
    got = narrow_code_tokens_by_specs(world.db, tokens=tokens, allowed_types=["product"], specs=specs, none_out=out)
    return got, out


def test_s2_two_codes_one_family_holds_the_size_no_unattributed_none_with(srt):
    """Reading: family A (HEAD) holds 200, family B (HEAD_B) holds no 200. A none-with that is not tied to
    B would tell the customer that no listed variant holds a size that A's variants do hold. So either the
    clause is withheld (none_out empty) or each entry names its own `token` (B's)."""
    for suffix, v in (("X", 100), ("Y", 150)):
        srt.product(f"{HEAD_B}-{suffix}", f"SORENTO WATER CLOSET {suffix}", stock=1)
        _set_values(srt, f"{HEAD_B}-{suffix}", {"trap_length": v})
    got, none = _none(srt, [HEAD, HEAD_B], [_size(200)])
    assert got is not None and sorted(c for c in got if c.startswith(HEAD)) == sorted([_code("SH-200"), _code("SH-NEW-200")]), got
    hits = [n for n in none if n.get("value") == 200]
    assert all(str(n.get("token", "")).upper() == HEAD_B for n in hits), none


def test_s2_two_codes_neither_family_holds_the_size_says_none(srt):
    for suffix, v in (("X", 100), ("Y", 150)):
        srt.product(f"{HEAD_B}-{suffix}", f"SORENTO WATER CLOSET {suffix}", stock=1)
        _set_values(srt, f"{HEAD_B}-{suffix}", {"trap_length": v})
    _got, none = _none(srt, [HEAD, HEAD_B], [_size(300)])
    assert [n for n in none if n.get("value") == 300], none


def test_s2_a_family_past_the_cap_with_the_holder_beyond_it_says_no_false_none_with(world):
    from app.services import product_code_family as pcf

    total = pcf._FAMILY_CAP + 5
    for i in range(total):
        world.product(f"ZZCAP901-SH{i:03d}", f"SORENTO CAP {i}", stock=1)
        _set_values(world, f"ZZCAP901-SH{i:03d}", {"dim_width": 300 if i == total - 1 else 100})
    got, none = _none(world, ["ZZCAP901"], [_size(300, ["dim_width"])])
    assert len(pcf._family_rows(world.db, 'ZZCAP901', loose=True)) == pcf._FAMILY_CAP  # the cap bites
    assert not [n for n in none if n.get("value") == 300], (none, got)


# ---- S3 / SF1: a variant that is not chat searchable is never picked

@pytest.fixture
def unsearchable_holder(srt):
    """A 300 holder in the family whose PRODUCT is not chat searchable; every searchable variant lacks 300."""
    row = srt.product(_code("SH-300"), "SORENTO WATER CLOSET SH-300", stock=1)
    _set_values(srt, _code("SH-300"), {"trap_length": 300})
    row.is_searchable = False
    srt.db.flush()
    return srt


@pytest.fixture
def unsearchable_category_holder(srt):
    from decimal import Decimal  # noqa: F401
    import uuid as _uuid

    from app.models.product import ProductCategory

    cat = ProductCategory(id=str(_uuid.uuid4()), category_code="ZZT-MISC", category_name="ZZT-MISC", is_searchable=False)
    srt.db.add(cat)
    srt.db.flush()
    row = srt.product(_code("SH-300"), "SORENTO WATER CLOSET SH-300", stock=1)
    _set_values(srt, _code("SH-300"), {"trap_length": 300})
    row.category_id = cat.id
    srt.db.flush()
    return srt


@pytest.mark.parametrize("fixture_name", ["unsearchable_holder", "unsearchable_category_holder"])
@pytest.mark.parametrize("head", [HEAD, "srt286"])
def test_s3_a_non_searchable_holder_is_never_picked(request, fixture_name, head):
    world = request.getfixturevalue(fixture_name)
    got, none = _none(world, [head], [_size(300)])
    assert got is None, got  # never narrowed to the code the contact cannot be told about
    assert [n for n in none if n.get("value") == 300], none  # the searchable family holds none: say so


@pytest.mark.parametrize("fixture_name", ["unsearchable_holder", "unsearchable_category_holder"])
def test_s3_route_never_names_the_non_searchable_code(request, client, fixture_name):
    request.getfixturevalue(fixture_name)
    body = {
        "query": f"{HEAD} 300mm", "tokens": [HEAD], "raw_tokens": [HEAD], "allowed_entity_types": ["product"],
        "match_mode": "and", "spec_fallback": True, "exact_match": True, "extracted_specs": [_size(300)], "dry_run": True,
    }
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 200, response.text
    blob = response.text
    assert _code("SH-300") not in blob, blob  # neither a match nor an unresolved "Couldn't find" token
    assert "spec_none" in response.json(), response.json()


# ---- S4: _keep_exact_variants leaves `intersection` alone when the kept token has no exact row

def test_s4_a_kept_token_with_no_exact_row_leaves_the_intersection_alone():
    from app.api.v1.system.references import _keep_exact_variants

    rows = [{"entity_type": "product", "canonical_code": c} for c in (_code("SH-P"), _code("SH-PP"), _code("SH-UF"))]
    result = {
        "resolutions": [{"token": _code("SH"), "matches": list(rows), "ambiguous": True, "resolved": False}],
        "intersection": list(rows),
    }
    _keep_exact_variants(result, [_code("SH")])
    assert result["intersection"] == rows, result["intersection"]


def test_s4_control_with_an_exact_row_the_longer_codes_are_dropped():
    from app.api.v1.system.references import _keep_exact_variants

    exact = {"entity_type": "product", "canonical_code": _code("SH")}
    longer = {"entity_type": "product", "canonical_code": _code("SH-P")}
    result = {"resolutions": [{"token": _code("SH"), "matches": [exact, longer]}], "intersection": [exact, longer]}
    _keep_exact_variants(result, [_code("SH")])
    assert result["intersection"] == [exact], result


# ---- SF2: a key hidden from this contact neither narrows nor is named

def _post(client, specs, hidden, tokens=None):
    body = {
        "query": f"{HEAD} spec", "tokens": tokens or [HEAD], "raw_tokens": tokens or [HEAD], "allowed_entity_types": ["product"],
        "match_mode": "and", "spec_fallback": True, "exact_match": True, "extracted_specs": specs, "hidden_spec_keys": hidden, "dry_run": True,
    }
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_sf2_a_hidden_named_key_neither_narrows_nor_is_named_in_spec_none(client, srt):
    hidden = ["trap_length"]
    control = _post(client, [], hidden)
    held = _post(client, [{"key": "trap_length", "value": 200, "grounded": True}], hidden)
    assert _route_codes(held) == _route_codes(control), (held, control)
    missed = _post(client, [{"key": "trap_length", "value": 300, "grounded": True}], hidden)
    assert not [n for n in missed.get("spec_none") or [] if n.get("key") == "trap_length"], missed.get("spec_none")
    assert "trap_length" not in json.dumps(missed.get("spec_none") or []), missed.get("spec_none")


def test_sf2_a_size_held_only_under_a_hidden_key_does_not_narrow_or_say_none(client, srt):
    """Every variant's 200 sits under trap_length; with trap_length hidden, size 200 narrows to nothing."""
    hidden = ["trap_length"]
    control = _post(client, [], hidden)
    got = _post(client, [_size(200)], hidden)
    assert _route_codes(got) == _route_codes(control), (got, control)
    assert "trap_length" not in json.dumps(got.get("spec_none") or []), got.get("spec_none")


# ---- kill gaps

def test_digit_boundary_a_head_ending_in_a_digit_never_reaches_a_longer_numbered_code(world):
    for code, v in (("ZZSRTWC2861-SH-200", 200), ("ZZSRTWC2861-SH-250", 250), ("ZZSRTWC286-SH-250", 250), ("ZZSRTWC286-SH-300", 300)):
        world.product(code, f"WC {code}", stock=1)
        _set_values(world, code, {"trap_length": v})
    got, none = _none(world, ["ZZSRTWC286"], [_size(200)])
    assert got is None or not [c for c in got if "2861" in c], got
    assert [n for n in none if n.get("value") == 200], none  # the 286 family holds no 200; 2861's 200 is not its


def test_none_out_honours_any_keys_a_variant_holding_the_size_under_any_key_is_no_none(basin):
    got, none = _none(basin, ["ZZSRB510"], [_size(300, ["dim_length", "dim_width"])])
    assert not none, none
    got, none = _none(basin, ["ZZSRB510"], [_size(300, ["dim_length", "dim_width"]), {"key": "dim_width", "value": 600, "grounded": True}])
    assert not [n for n in none if n.get("key") == "size"], none  # the size is held (D, width 300), only the AND with 600 is empty


def test_none_out_size_with_a_second_spec_does_not_say_none_with_size_when_a_variant_holds_it(srt):
    specs = [_size(250), {"key": "trap_type", "value": "p_trap", "grounded": True}]
    _got, none = _none(srt, [HEAD], specs)
    assert not [n for n in none if n.get("key") == "size"], none


def test_the_none_with_label_exists_in_ms_and_zh():
    from app.services.chatbot import label_catalog

    entry = label_catalog.LABELS.get("None with {label} {value}.")
    assert entry and entry.get("ms") and entry.get("zh"), entry
    assert "{label}" in entry["ms"] and "{value}" in entry["ms"], entry
    assert "{label}" in entry["zh"] and "{value}" in entry["zh"], entry
