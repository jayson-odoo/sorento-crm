"""COMBO-SEED-FLYER AC-6b: under --strict, a plain existing description with the flyer's words gets the flyer's bold."""
from __future__ import annotations

from tests.test_import_product_combos_strict import (  # noqa: F401  (db is a fixture)
    _combos, _entry, _existing, _line, _lines, _prod, _run, db,
)

SEED_HTML = "<p><strong>A</strong> (CABINET)</p><p>L1</p>"


def _setup(db, host, description):
    _prod(db, host)
    _existing(db, host, "Pack", description=description)


def test_ac_6b_plain_description_with_same_words_gets_bold(db, tmp_path):
    _setup(db, "ZZBH1", "A (CABINET)\nL1")
    _, out = _run(db, tmp_path, [_entry("ZZBH1", "Pack", 1, combo_description=SEED_HTML)], apply=True)
    assert _combos(db, "ZZBH1", "Pack")[0].description == SEED_HTML
    verdict, _h, _n, _p, details = _line(out, "Pack")
    assert verdict == "UPDATE" and "description bold" in details


def test_ac_6b_plain_description_with_different_words_is_kept(db, tmp_path):
    _setup(db, "ZZBH2", "A (CABINET)\nL2")
    _, out = _run(db, tmp_path, [_entry("ZZBH2", "Pack", 1, combo_description=SEED_HTML)], apply=True)
    assert _combos(db, "ZZBH2", "Pack")[0].description == "A (CABINET)\nL2"
    assert "kept: description differs from flyer" in _line(out, "Pack")[4]


def test_ac_6b_rich_existing_description_is_never_touched(db, tmp_path):
    rich = "<p>A (CABINET)</p><p>L1</p>"
    _setup(db, "ZZBH3", rich)
    _run(db, tmp_path, [_entry("ZZBH3", "Pack", 1, combo_description=SEED_HTML)], apply=True)
    assert _combos(db, "ZZBH3", "Pack")[0].description == rich


def test_ac_6b_second_apply_is_skip(db, tmp_path):
    _setup(db, "ZZBH4", "A (CABINET)\nL1")
    entries = [_entry("ZZBH4", "Pack", 1, combo_description=SEED_HTML)]
    _run(db, tmp_path, entries, apply=True)
    _, out = _run(db, tmp_path, entries, apply=True)
    assert [v for v, *_ in _lines(out)] == ["SKIP"]
