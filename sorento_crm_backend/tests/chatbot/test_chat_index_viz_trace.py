"""CHAT-INDEX-VIZ BE-1 (contract: documentation/plans/chatbot/chat-index-viz-20oct-contract.md).

`closed_lists_index.block_with_matches(db, entries, message, held_ids, hidden)` returns the
exact lines `block()` returns plus one match dict per entry it sent, and the engine writes a
`closed_lists_index` trace event in index mode only. ZZ data only; Postgres only.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.services import ai_prompt_registry
from app.services import chatbot_prompt_vars as pv
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import candidates
from app.services.chatbot.head import closed_lists_index as cli
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot import test_closed_lists_index_mode as idx
from tests.chatbot import test_closed_lists_index_warehouse as wh
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _turn_row, seeded, stub_access  # noqa: F401

DRAWING_LINE_PREFIX = "File type zz_idx_drawing:"


@pytest.fixture(autouse=True)
def _fresh_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _world(session_factory):
    """The index-mode world (file types, held product) plus the finish registry with a `-FRG` suffix."""
    wh._seed(session_factory)
    idx._seed_world(session_factory)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return db


def _held_id(db) -> str:
    from app.models.product import Product

    return str(db.query(Product).filter(Product.product_code == idx.HELD).one().id)


def _call(db, entries, message, held=None):
    assert hasattr(cli, "block_with_matches"), "closed_lists_index.block_with_matches does not exist yet"
    return cli.block_with_matches(db, entries, message, held or [], frozenset())


# --------------------------------------------------------------------------- #
# block_with_matches
# --------------------------------------------------------------------------- #


def test_code_suffix_word_matches_the_specification_entry(session_factory):
    db = _world(session_factory)
    lines, matches = _call(db, [], "frg stock")
    hits = [m for m in matches if m["word"] == "frg"]
    assert len(hits) == 1, matches
    hit = hits[0]
    assert hit["list"] == "Specifications"
    assert "finish" in hit["entry"] and "french_gold" in hit["entry"], hit
    assert hit["close_spelling"] is False
    assert hit["held"] is False
    assert hit["line"].startswith('- "frg":') and hit["line"] in lines, (hit, lines)


def test_file_type_named_exactly_matches_with_the_gram_as_word(session_factory):
    db = _world(session_factory)
    lines, matches = _call(db, [], "send zz idx drawing please")
    hits = [m for m in matches if m["list"] == "File types"]
    assert len(hits) == 1, matches
    assert hits[0]["word"] == "zz idx drawing", hits[0]
    assert hits[0]["entry"].startswith(DRAWING_LINE_PREFIX), hits[0]
    assert hits[0]["close_spelling"] is False
    assert hits[0]["entry"] in lines, lines


def test_file_type_named_by_near_spelling_sets_close_spelling(session_factory):
    db = _world(session_factory)
    _lines, matches = _call(db, [], "send zz idx drawng please")
    hits = [m for m in matches if m["list"] == "File types"]
    assert hits, matches
    assert hits[0]["close_spelling"] is True, hits[0]
    assert hits[0]["entry"].startswith(DRAWING_LINE_PREFIX), hits[0]


def test_certificate_kind_and_scheme_use_their_own_list_names(session_factory):
    db = _world(session_factory)
    _lines, matches = _call(db, [], "zz idx cert zzsch")
    names = {m["list"] for m in matches}
    assert "Certificates" in names, matches
    assert "Certificate schemes" in names, matches


def test_held_lines_have_no_word_and_are_marked_held(session_factory):
    db = _world(session_factory)
    held = _held_id(db)
    lines, matches = _call(db, [], "zzqwerty", [held])
    held_matches = [m for m in matches if m["held"]]
    assert held_matches, matches
    for m in held_matches:
        assert m["word"] is None, m
        assert m["list"] == "On record for the held product", m
        assert m["close_spelling"] is False
    assert any(m["entry"].startswith(DRAWING_LINE_PREFIX) for m in held_matches), held_matches
    assert any("zz_idxvis" in m["entry"] for m in held_matches), held_matches
    assert cli.HELD_HEADER in lines
    assert all(not m["held"] for m in matches if m["word"] is not None)


def test_candidate_code_item_is_listed_under_products(session_factory):
    db = _world(session_factory)
    entry = candidates.WordCandidates(gram="zzidxp1", position=0, items=["code ZZIDXP1 (ZZT ZZIDXP1)"])
    lines, matches = _call(db, [entry], "zzidxp1")
    assert matches == [{
        "word": "zzidxp1", "list": "Products", "entry": "code ZZIDXP1 (ZZT ZZIDXP1)",
        "close_spelling": False, "held": False, "line": '- "zzidxp1": code ZZIDXP1 (ZZT ZZIDXP1)',
    }], matches
    assert matches[0]["line"] in lines


def test_candidate_item_kinds_map_to_list_names(session_factory):
    db = _world(session_factory)
    entry = candidates.WordCandidates(gram="zzw", position=0, items=[
        "product type Basin (class = basin)", "spec colour = red (Red)", "flag zz_flag = true (ZZ Flag)",
        "size 600 mm",
    ])
    _lines, matches = _call(db, [entry], "zzw")
    by_entry = {m["entry"]: m["list"] for m in matches}
    assert by_entry["product type Basin (class = basin)"] == "Product types"
    assert by_entry["spec colour = red (Red)"] == "Specifications"
    assert by_entry["flag zz_flag = true (ZZ Flag)"] == "Specifications"
    assert by_entry["size 600 mm"] == "Sizes"
    assert all(m["word"] == "zzw" for m in matches)


def test_near_item_strips_the_prefix_and_sets_close_spelling(session_factory):
    db = _world(session_factory)
    entry = candidates.WordCandidates(gram="whyte", position=0, items=["near spec finish = white (White)"])
    _lines, matches = _call(db, [entry], "whyte")
    assert len(matches) == 1, matches
    assert matches[0]["entry"] == "spec finish = white (White)"
    assert matches[0]["close_spelling"] is True
    assert matches[0]["list"] == "Specifications"
    assert matches[0]["line"] == '- "whyte": near spec finish = white (White)'


def test_block_is_unchanged_for_the_same_input(session_factory):
    db = _world(session_factory)
    held = _held_id(db)
    message = "frg send zz idx drawing"
    entries = candidates.shortlist(db, message, [held])
    expected = cli.block(db, candidates.candidate_lines(entries), message, [held], frozenset())
    lines, _matches = _call(db, entries, message, [held])
    assert lines == expected
    assert expected, "the world must produce a non-empty block"


def test_a_word_matching_nothing_sends_nothing(session_factory):
    db = _world(session_factory)
    lines, matches = _call(db, [], "zzqwerty")
    assert matches == [] and lines == [], (lines, matches)


# --------------------------------------------------------------------------- #
# The engine's per-turn event
# --------------------------------------------------------------------------- #


def _events(session_factory, turn_id: str) -> list[dict]:
    row = _turn_row(session_factory, turn_id)
    return [r for r in row.trace if isinstance(r, dict) and r.get("kind") == "closed_lists_index"]


def test_index_mode_turn_persists_the_closed_lists_index_event(session_factory, seeded, stub_access, monkeypatch):
    wh._seed(session_factory)
    idx._seed_world(session_factory)
    idx._set_mode(session_factory, "index")
    [(_system, _block, result)] = idx._turns(session_factory, stub_access, monkeypatch, [("frg stock", idx._quiet())])
    events = _events(session_factory, result.turn_id)
    assert len(events) == 1, events
    event = events[0]
    assert event["words"] == ["frg", "stock"], event
    assert event["failed"] is False
    frg = [m for m in event["matches"] if m["word"] == "frg"]
    assert frg and frg[0]["list"] == "Specifications", event["matches"]
    assert set(frg[0]) == {"word", "list", "entry", "close_spelling", "held", "line"}


def test_index_mode_failure_records_failed_and_the_turn_still_answers(session_factory, seeded, stub_access, monkeypatch):
    wh._seed(session_factory)
    idx._seed_world(session_factory)
    idx._set_mode(session_factory, "index")

    def boom(*args, **kwargs):
        raise RuntimeError("zz index failure")

    monkeypatch.setattr(cli, "block_with_matches", boom, raising=False)
    [(_system, _block, result)] = idx._turns(session_factory, stub_access, monkeypatch, [("frg stock", idx._quiet())])
    assert (result.reply or {}).get("text"), result
    events = _events(session_factory, result.turn_id)
    assert len(events) == 1, events
    assert events[0]["failed"] is True
    assert events[0]["matches"] == []


def test_block_mode_turn_has_no_closed_lists_index_event(session_factory, seeded, stub_access, monkeypatch):
    wh._seed(session_factory)
    idx._seed_world(session_factory)
    [(_system, _block, result)] = idx._turns(session_factory, stub_access, monkeypatch, [("frg stock", idx._quiet())])
    assert _events(session_factory, result.turn_id) == []
    assert hasattr(engine_mod, "_candidate_lines")
