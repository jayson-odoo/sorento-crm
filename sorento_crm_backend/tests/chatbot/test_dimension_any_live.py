"""DIMENSION-ANY on prod's LIVE path (crew gate on 3747d171, 28 Oct 2026): parser text v188 = prod's v69 runs
closed_lists=False, lookup_lists=True, so the candidate block and its size line never ran there.

What the parser is offered on that path is the Spec block of the lookup lists (`lookup_lists.number_hits`), and
it fills spec_key / spec_value from a line's "(key: value)" bracket. Owner rules, kept semantic (the parser
decides; code offers lines off registry data and resolves what the parser picked):
- a length is offered as "Size N mm, any dimension (size: N)", so a size with no dimension named can be emitted
  as such, and grounds to every dimension (no dimension invented in the reply);
- every dimension's own line is offered for a length no key holds, so a NAMED miss ("length 999mm") is said back
  as named;
- a unit the registry lists as an alias ("10 inch", "15cm") is offered in the key's own unit (254 mm, 150 mm).
"""
from __future__ import annotations

import json
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.product_spec import ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_bare_size import WC, _ent, _seed, _spec
from tests.chatbot.test_closed_lists_spec_over_held import _fetched, _message, _stock_ask
from tests.chatbot.test_dimension_any import WCS, _aliases
from tests.chatbot.test_engine import _envelope, seeded, stub_access  # noqa: F401

SIZE_150 = "Size 150mm, any dimension (size: 150)"


def _labels(session_factory, message: str) -> list[str]:
    from app.models.base import set_company_scope
    from app.services.chatbot.head import lookup_lists

    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return [h.row.label for h in lookup_lists.number_hits(message, db)]


# --- What the parser is offered -------------------------------------------------------------------------------


def test_a_length_leads_with_the_any_dimension_size_line(session_factory, seeded):
    _seed(session_factory, WCS)

    labels = _labels(session_factory, "zzwc with 150mm got stock")

    assert labels[0] == SIZE_150, labels
    assert "Height 150mm (dim_height: 150)" in labels and "Trap outlet length 150mm (trap_length: 150)" in labels, labels


def test_a_centimetre_size_is_offered_in_mm_off_the_registry_alias(session_factory, seeded):
    _seed(session_factory, WCS)
    _aliases(session_factory)

    assert _labels(session_factory, "zzwc with 15cm got stock")[0] == SIZE_150


def test_an_inch_size_is_offered_in_mm_off_the_registry_alias_even_when_no_key_holds_it(session_factory, seeded):
    _seed(session_factory, WCS)
    _aliases(session_factory)

    labels = _labels(session_factory, "kitchen sink 10 inch")

    assert labels[0] == "Size 254mm, any dimension (size: 254)", labels
    assert "Length 254mm (dim_length: 254)" in labels, labels


def test_a_length_no_key_holds_offers_every_dimension_so_a_named_miss_is_nameable(session_factory, seeded):
    _seed(session_factory, WCS)

    labels = _labels(session_factory, "zzwc with length 999mm got stock")

    assert labels[0] == "Size 999mm, any dimension (size: 999)", labels
    assert {"Length 999mm (dim_length: 999)", "Width 999mm (dim_width: 999)", "Height 999mm (dim_height: 999)"} <= set(labels), labels


def test_a_unit_with_no_registry_alias_is_no_size(session_factory, seeded):
    """The unit words beyond mm / cm / m are registry data: with no alias on file, "10 inch" offers nothing."""
    _seed(session_factory, WCS)
    _aliases(session_factory, {})

    assert _labels(session_factory, "kitchen sink 10 inch") == []


def test_guard_a_litre_quantity_keeps_its_held_key_lines_only(session_factory, seeded):
    db = session_factory()
    db.add(ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key="zz_capacity", label="Capacity", data_type="numeric", unit="L",
        synonyms={"_self": ["capacity"]}, applies_when={},
    ))
    db.commit()
    _seed(session_factory, (("ZZDL-B", WC, {"zz_capacity": 12}),))

    labels = _labels(session_factory, "bin 12l")

    assert labels == ["Capacity 12L (zz_capacity: 12)"], labels


# --- The parser's pick, through the live engine path ------------------------------------------------------------


def _live(session_factory, stub_access, monkeypatch, text: str, *entities: dict):
    """One turn with prod's flags: closed_lists off, lookup_lists on. The parser is stubbed to the given pick."""
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import lookup_lists
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot.test_closed_lists_hidden_keys_entries import real_hidden_spec_keys

    def config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k",
            closed_lists=False, lookup_lists=True,
        )

    seen: list[str] = []
    monkeypatch.setattr(lookup_lists, "EMBED", None, raising=False)
    monkeypatch.setattr(parser_mod, "resolve_config", config)
    monkeypatch.setattr(parser_mod, "parse", lambda c, block: seen.append(str(block)) or _stock_ask(*entities))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        MCPRuntimeClient, "call_tool", lambda self, name, args: calls.append((name, args)) or json.dumps({"ok": True, "items": []})
    )
    stub_access(hidden_spec_keys=real_hidden_spec_keys(session_factory))
    r = engine_mod.run_turn(_envelope(message=_message(text, 0)), session_factory=session_factory)
    return r, calls, seen[-1] if seen else ""


def _text(r) -> str:
    return ((r.reply or {}).get("text") or "")


def test_live_the_size_line_reaches_the_parser(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory, WCS)

    _r, _calls, block = _live(session_factory, stub_access, monkeypatch, "zzwc with 150mm got stock", _ent("zzwc", "category"))

    assert f"- {SIZE_150}" in block.splitlines(), block


def test_live_a_size_pick_matches_every_dimension(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, WCS)

    r, calls, _b = _live(
        session_factory, stub_access, monkeypatch, "zzwc with 150mm got stock", _ent("zzwc", "category"), _spec("150mm", "size", 150),
    )

    assert _fetched(calls) == sorted([ids["ZZDA-H"], ids["ZZDA-T"]]), (_text(r), calls)


def test_live_an_inch_size_pick_is_its_mm_value_and_a_miss_names_it(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory, WCS)
    _aliases(session_factory)

    r, calls, _b = _live(
        session_factory, stub_access, monkeypatch, "zzwc 10 inch got stock", _ent("zzwc", "category"), _spec("10 inch", "size", 254),
    )

    assert _fetched(calls) == [], (_text(r), calls)
    assert "254 mm" in _text(r), _text(r)


def test_live_a_named_length_miss_is_said_with_its_dimension(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory, WCS)

    r, calls, _b = _live(
        session_factory, stub_access, monkeypatch, "zzwc with length 999mm got stock",
        _ent("zzwc", "category"), _spec("length 999mm", "dim_length", 999),
    )

    assert _fetched(calls) == [], (_text(r), calls)
    assert "length 999 mm" in _text(r).lower(), _text(r)
