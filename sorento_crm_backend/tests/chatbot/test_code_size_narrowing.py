"""CHATBOT-FAIL-TRIAGE-B2 S1, AC-6: a code head plus a size narrows the family.

"SRTWC286 250MM", "SRTWC286200MM", "srtwc286-200mm": the parser (stubbed here) emits the code head
as the product and a `size` specification (the reserved any-dimension key); the code narrows to
EVERY variant holding that size under ANY dimension key, never "Couldn't find". The family shape
mirrors backup 1028 with ZZ codes; the bare head is not itself a product code.

Postgres only; every test seeds its own chain.
"""
from __future__ import annotations

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
