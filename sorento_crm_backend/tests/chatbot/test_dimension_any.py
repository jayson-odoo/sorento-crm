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


def test_the_candidate_line_offers_the_bare_size_when_only_height_holds_it(session_factory, seeded):
    """The prod miss: no width or length held 150 (nor a class-scoped key), so the parser saw only
    "spec dim_height = 150" and picked height."""
    from app.models.base import set_company_scope
    from app.services.chatbot.head import candidates

    _seed(session_factory, (("ZZDA-H", WC, {"dim_height": 150, "dim_width": 400}),))
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



# --- The words: the resolver's set and the header the reply opens with -------------------------------


def _resolve(session_factory, *specs: dict) -> dict:
    from app.models.base import set_company_scope
    from app.services.product_predicate_service import resolve_product_set

    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return resolve_product_set(db, require={}, specs=list(specs), scope_terms=["zzwc"])


def _header(outcome: dict) -> str:
    from app.services.chatbot.lanes.business.answer import build_set_header, set_noun_for

    total = outcome["qualifying_total"]
    return build_set_header(
        total, total, set_noun_for(outcome.get("class_labels") or []), {"stock": True},
        description=outcome.get("description"), dimension_fallback=outcome.get("dimension_fallback"),
    )


def test_a_bare_size_set_is_said_with_no_dimension_name(session_factory, seeded):
    _seed(session_factory, WCS)

    outcome = _resolve(session_factory, {
        "key": "size", "value": 150, "grounded": True, "any_keys": ["dim_height", "dim_length", "dim_width", "trap_length"],
    })

    header = _header(outcome)
    assert outcome["qualifying_total"] == 2, outcome
    assert header == "Here's what you want: zz water closets with 150 mm with stock (2)", header
    assert "dimension_fallback" not in outcome


def test_a_named_length_nothing_holds_comes_back_under_any_dimension_with_the_line(session_factory, seeded):
    _seed(session_factory, WCS)

    outcome = _resolve(session_factory, {"key": "dim_length", "value": 150, "grounded": True})

    assert outcome["qualifying_total"] == 2, outcome
    assert outcome["dimension_fallback"] == {"label": "Length", "value": "150 mm"}, outcome
    assert _header(outcome).split("\n") == [
        "None with length 150 mm; these have 150 mm in another dimension:",
        "Here's what you want: zz water closets with 150 mm with stock (2)",
    ], _header(outcome)


def test_guard_the_fallback_line_is_on_the_first_page_only():
    from app.services.chatbot.lanes.business.answer import build_set_header

    named = {"label": "Length", "value": "150 mm"}
    first = build_set_header(60, 50, "water closets", {"stock": True}, dimension_fallback=named)
    later = build_set_header(60, 10, "water closets", {"stock": True}, dimension_fallback=named, offset=50)

    assert first.startswith("None with length 150 mm; these have 150 mm in another dimension:\n"), first
    assert "another dimension" not in later, later


def test_guard_a_named_length_a_product_holds_carries_no_fallback(session_factory, seeded):
    _seed(session_factory, (*WCS, ("ZZDA-L", WC, {"dim_length": 150})))

    outcome = _resolve(session_factory, {"key": "dim_length", "value": 150, "grounded": True})

    assert outcome["qualifying_total"] == 1, outcome
    assert "dimension_fallback" not in outcome
    assert "length 150 mm" in _header(outcome), _header(outcome)


def test_guard_two_named_dimensions_are_never_widened(session_factory, seeded):
    """One named dimension is the owner's case; a turn naming two keeps its honest miss."""
    _seed(session_factory, WCS)

    outcome = _resolve(
        session_factory,
        {"key": "dim_length", "value": 150, "grounded": True},
        {"key": "dim_width", "value": 400, "grounded": True},
    )

    assert outcome["qualifying_total"] == 0, outcome
    assert "dimension_fallback" not in outcome


def test_guard_a_named_length_held_but_out_of_stock_is_no_fallback(session_factory, seeded):
    """Reviewer B1: a WC that holds length 150 with no stock is the honest "but no stock" miss,
    never "None with length 150 mm" over a height-150 WC that has stock."""
    from sqlalchemy import update

    from app.models.base import set_company_scope
    from app.models.inventory import Stock
    from app.services.product_predicate_service import resolve_product_set

    ids = _seed(session_factory, (("ZZPR-L", WC, {"dim_length": 150}), ("ZZPR-H", WC, {"dim_height": 150})))
    db = session_factory()
    db.execute(update(Stock).where(Stock.product_id == ids["ZZPR-L"]).values(quantity_on_hand=0))
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    outcome = resolve_product_set(
        db, require={"stock": True}, specs=[{"key": "dim_length", "value": 150, "grounded": True}], scope_terms=["zzwc"],
    )

    assert outcome["qualifying_total"] == 0, outcome
    assert "dimension_fallback" not in outcome, outcome


def test_guard_a_hidden_dimension_is_never_a_leg_of_the_fallback(session_factory, seeded):
    """Reviewer S1: the fallback's OR is built off the visible keys only."""
    from app.models.base import set_company_scope
    from app.services.product_predicate_service import resolve_product_set

    _seed(session_factory, WCS)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    outcome = resolve_product_set(
        db, require={}, specs=[{"key": "dim_length", "value": 400, "grounded": True}], scope_terms=["zzwc"],
        hidden_keys=frozenset({"dim_width"}),
    )

    assert outcome["qualifying_total"] == 0, outcome
    assert "dimension_fallback" not in outcome, outcome


def test_the_route_hands_the_fallback_to_the_reply(session_factory, seeded):
    """Reviewer S2: the resolve route's predicate carries `dimension_fallback` (a field
    `response_model`-style plumbing could drop), so the set header can lead with the line."""
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.models.base import set_company_scope

    _seed(session_factory, WCS)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    body = ResolveReferenceRequest(
        query="zzwc length 150mm", tokens=["zzwc"], require={"stock": True}, scope_terms=["zzwc"],
        extracted_specs=[{"key": "dim_length", "value": 150, "evidence": "length 150mm", "grounded": True}],
    )

    payload = resolve_reference_post(body, current_user={}, db=db)

    predicate = payload.get("predicate") or {}
    assert predicate.get("qualifying_total") == 2, payload
    assert predicate.get("dimension_fallback") == {"label": "Length", "value": "150 mm"}, predicate


def _ground(session_factory, raw: str, value, unit=None):
    from app.models.base import set_company_scope
    from app.services.chatbot.head.bare_size import ground_bare

    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    entity = {"raw": raw, "hint": "specification", "spec_key": "size", "spec_value": value, "spec_unit": unit}
    return ground_bare(db, entity, [entity], None, None)


def test_the_unit_typed_beside_the_kept_number_wins_over_the_resolvers(session_factory, seeded):
    """Reviewer S3: "15cm" with the parser's 15 is 150 mm, whatever unit came with it."""
    _seed(session_factory, WCS)
    g = _ground(session_factory, "15cm", 15, "mm")

    assert g is not None and g.value == 150 and g.unit == "mm", g


def test_guard_a_word_after_the_number_that_is_no_unit_changes_nothing(session_factory, seeded):
    """Reviewer round 2: "150 x 400mm" and "150 wide" stay a 150 mm size over every dimension."""
    _seed(session_factory, WCS)
    for raw in ("150 x 400mm", "150 wide"):
        g = _ground(session_factory, raw, 150)

        assert g is not None and g.value == 150 and g.unit == "mm", (raw, g)
        assert sorted(g.any_keys or []) == ["dim_height", "dim_length", "dim_width", "trap_length"], (raw, g)
