"""DIMENSION-ANY (owner, prod v69, 28 Oct 2026): a measurement matches every dimension.

"wc with 150mm got stock" answered "water closets with height 150 mm ... none matched", and "wc with
length 150mm got stock" answered "... with length 150 mm ... none matched". Owner: "when it comes to
dimension, it shouldn't restrict to just 1 dimension, it should search all dimension".

- A measurement with no dimension named matches ANY dimension of the product (every numeric registry
  key in a length unit), unit-normalised, and the reply names no dimension.
- A NAMED dimension matches that dimension first; when the set is empty, it falls back to any
  dimension under "None with length 150 mm; these have 150 mm in another dimension:".

Which keys are dimensions is the registry's own unit, never a key list in code.
"""
from __future__ import annotations

import uuid

from app.models.product_spec import ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_bare_size import WC, _ask, _ent, _seed, _spec
from tests.chatbot.test_closed_lists_spec_over_held import _fetched
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401


def _with_depth(session_factory) -> None:
    """The R6-1 fixture's registry has no depth; DIMENSION-ANY's prod case has one."""
    db = session_factory()
    db.add(ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key="depth", label="Depth", data_type="numeric", unit="mm",
        synonyms={"_self": ["depth", "deep"]}, applies_when={},
    ))
    db.commit()


WCS = (
    ("ZZDA-H", WC, {"dim_height": 150, "dim_width": 400}),
    ("ZZDA-T", WC, {"trap_length": 150}),
    ("ZZDA-X", WC, {"dim_width": 400, "dim_length": 650}),
)


def _text(r) -> str:
    return ((r.reply or {}).get("text") or "")


def test_a_bare_150mm_wc_matches_every_dimension_that_holds_150(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, WCS)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "zzwc with 150mm got stock", _ent("zzwc", "category"), _spec("150mm", "size", 150))

    assert _fetched(calls) == sorted([ids["ZZDA-H"], ids["ZZDA-T"]]), (_text(r), calls)
    said = _text(r).lower()
    assert "150 mm" in said, said
    # No dimension is invented: the customer named none.
    for word in ("height", "length", "width", "trap", "depth", "size 150"):
        assert word not in said, said


def test_a_bare_size_reaches_a_product_whose_150mm_is_its_depth(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, (
        ("ZZDD-D", WC, {"depth": 150}),
        ("ZZDD-W", WC, {"dim_width": 400}),
    ))
    _with_depth(session_factory)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "zzwc 150mm", _ent("zzwc", "category"), _spec("150mm", "size", 150))

    assert _fetched(calls) == [ids["ZZDD-D"]], (_text(r), calls)


def test_a_bare_size_in_cm_is_read_in_mm(session_factory, seeded, stub_access, monkeypatch):
    """The parser copied the typed "15" off "15cm": the number is normalised to the registry's mm."""
    ids = _seed(session_factory, WCS)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "zzwc 15cm got stock", _ent("zzwc", "category"), _spec("15cm", "size", 15))

    assert _fetched(calls) == sorted([ids["ZZDA-H"], ids["ZZDA-T"]]), (_text(r), calls)
    assert "150 mm" in _text(r), _text(r)


def test_the_candidate_line_offers_the_bare_size_when_only_height_holds_it(session_factory, seeded):
    """The prod miss: no width or length held 150, so the parser saw only "spec dim_height = 150"."""
    from app.models.base import set_company_scope
    from app.services.chatbot.head import candidates

    _seed(session_factory, WCS)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    lines = candidates.candidate_lines(candidates.shortlist(db, "zzwc with 150mm got stock"))

    line = next(ln for ln in lines if ln.startswith('- "150mm"'))
    assert line.startswith('- "150mm": size 150 mm (no dimension named); spec '), lines


def test_the_candidate_line_for_a_cm_size_is_in_mm(session_factory, seeded):
    from app.models.base import set_company_scope
    from app.services.chatbot.head import candidates

    _seed(session_factory, WCS)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    lines = candidates.candidate_lines(candidates.shortlist(db, "zzwc 15cm got stock"))

    line = next(ln for ln in lines if ln.startswith('- "15cm"'))
    assert line.startswith('- "15cm": size 150 mm (no dimension named); spec '), lines
    assert "spec dim_height = 150" in line, lines


def test_a_named_length_no_product_holds_falls_back_to_any_dimension_with_a_line(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, WCS)

    r, calls = _ask(
        session_factory, stub_access, monkeypatch, "zzwc with length 150mm got stock",
        _ent("zzwc", "category"), _spec("length 150mm", "dim_length", 150),
    )

    assert _fetched(calls) == sorted([ids["ZZDA-H"], ids["ZZDA-T"]]), (_text(r), calls)
    assert "None with length 150 mm; these have 150 mm in another dimension:" in _text(r), _text(r)


def test_guard_a_named_length_a_product_holds_stays_strict_with_no_fallback_line(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, (*WCS, ("ZZDA-L", WC, {"dim_length": 150})))

    r, calls = _ask(
        session_factory, stub_access, monkeypatch, "zzwc with length 150mm got stock",
        _ent("zzwc", "category"), _spec("length 150mm", "dim_length", 150),
    )

    assert _fetched(calls) == [ids["ZZDA-L"]], (_text(r), calls)
    assert "another dimension" not in _text(r), _text(r)


def test_guard_a_named_length_no_dimension_holds_stays_an_honest_miss(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory, WCS)

    r, calls = _ask(
        session_factory, stub_access, monkeypatch, "zzwc with length 999mm got stock",
        _ent("zzwc", "category"), _spec("length 999mm", "dim_length", 999),
    )

    assert _fetched(calls) == [], (_text(r), calls)
    assert "another dimension" not in _text(r), _text(r)
    assert "999 mm" in _text(r), _text(r)
