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
from tests.chatbot.test_trap_spec_search import ENDPOINT, _route_codes, client, world  # noqa: F401

ANY = ["dim_height", "dim_length", "dim_width", "trap_length"]
HEAD = "ZZSRT286"

# variant suffix -> trap_length (backup 1028 shape)
TRAP = {
    "SH": 250, "SH-150": 150, "SH-200": 200, "SH-NEW": 250, "SH-NEW-150": 150,
    "SH-NEW-200": 200, "SH-NEW-P": 180, "SH-P": 180, "SH-PP": 250, "SH-UF": 250,
}


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
        _set_values(world, _code(suffix), {"trap_length": length, "trap_type": "p_trap" if "P" in suffix.split("-")[-1:] and suffix.endswith("P") else "s_trap"})
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
