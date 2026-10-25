"""PROJECT-REG-PORTAL possible duplicates, red-first (UAC D1-D6; PLAN D8, D9).

Service level: `find_possible_duplicates` is a pure read over a Postgres session, and the
meaning signal is stubbed at `semantic_matches` / `embed_text` (D5) so no test needs an
embedding key. Each negative test carries a guard proving the premise (e.g. the spelling
matcher alone would NOT name the project), so a pass cannot come from an accident.

Expected red reason today: `ModuleNotFoundError: app.services.project_registration_service`.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._project_registration_support import developer, project, stub_semantic
from ._sample_request_seed import second_company, sorento


@pytest.fixture
def db(monkeypatch):
    from app.models.base import company_scope

    stub_semantic(monkeypatch)
    with blank_session() as session:
        session.company_id = sorento(session)
        session.other_company = second_company(session)
        # Both companies in scope, on purpose: the service's own company predicate must be the
        # only thing keeping the other company's rows out (same reasoning as the clash matcher).
        with company_scope(session, frozenset({session.company_id, session.other_company})):
            yield session


def _find(db, title, **kw):
    from app.services.project_registration_service import find_possible_duplicates

    return find_possible_duplicates(db, company_id=db.company_id, title=title, **kw)


def _codes(rows):
    return [r["project_code"] for r in rows]


def _spelling_names(db, title, row):
    from app.services.project_clash_service import find_clashes

    return any(
        c.project_id == row.id
        for c in find_clashes(db, company_id=db.company_id, developer_party_id=None, title=title,
                              include_other_developers=True)
    )


# ------------------------------------------------------------------ parsing helpers


def test_d1_lot_numbers_read_lot_pt_and_lot_no_alike():
    from app.services.project_registration_service import parse_lot_numbers

    assert parse_lot_numbers("DI ATAS LOT 9001, MUKIM TEBRAU") == {"9001"}
    assert parse_lot_numbers("DI ATAS PT 9001") == {"9001"}
    assert parse_lot_numbers("di atas Lot No. 9001") == {"9001"}
    assert parse_lot_numbers("LOT 1234 DAN LOT 5678") == {"1234", "5678"}
    assert parse_lot_numbers("MENARA ZETA TOWER 2") == set()
    assert parse_lot_numbers("") == set()


def test_d1_mukim_is_read_from_the_title():
    from app.services.project_registration_service import parse_mukim

    assert (parse_mukim("DI ATAS LOT 9001, MUKIM TEBRAU, JOHOR") or "").casefold().strip() == "tebrau"
    assert parse_mukim("MENARA ZETA TOWER 2") is None


# ------------------------------------------------------------------ D1 same lot + mukim


def test_d1_same_lot_and_mukim_is_named(db):
    existing = project(db, db.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-L1")
    rows = _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU, JOHOR")
    assert rows == [{"project_id": existing.id, "project_code": "PRJ-ZZT-L1", "title": existing.title}]


@pytest.mark.parametrize(
    "typed",
    [
        "CADANGAN PEMBINAAN GUDANG DI ATAS PT 9001, MUKIM TEBRAU",
        "CADANGAN PEMBINAAN GUDANG DI ATAS LOT NO. 9001, MUKIM TEBRAU",
    ],
)
def test_d1_pt_and_lot_no_read_as_the_same_lot(db, typed):
    existing = project(db, db.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    assert [r["project_id"] for r in _find(db, typed)] == [existing.id]


def test_d1_the_registrations_mukim_field_and_the_projects_profile_mukim_count(db):
    existing = project(db, db.company_id, "KILANG ALPHA LOT 9001", mukim="Tebrau")
    rows = _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001", mukim="TEBRAU")
    assert [r["project_id"] for r in rows] == [existing.id]


# ------------------------------------------------------------------ D2 / D3 negatives


def test_d2_same_lot_in_another_mukim_is_not_named_by_the_lot_signal(db):
    existing = project(db, db.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    title = "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM PLENTONG, JOHOR"
    assert not _spelling_names(db, title, existing), "premise: titles are unlike enough"
    assert _find(db, title) == []


def test_d2_a_profile_mukim_that_differs_is_not_named_either(db):
    project(db, db.company_id, "KILANG ALPHA LOT 9001", mukim="Tebrau")
    assert _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001", mukim="Plentong") == []


def test_d3_phase_siblings_on_the_same_lot_are_not_named(db):
    existing = project(db, db.company_id, "TAMAN DELTA FASA 4 DI ATAS LOT 9001 MUKIM TEBRAU")
    title = "TAMAN DELTA FASA 5 DI ATAS LOT 9001 MUKIM TEBRAU"
    assert _find(db, title) == []
    assert existing.id  # the sibling exists; it is dropped, not absent


# ------------------------------------------------------------------ D4 spelling


def test_d4_spelling_drift_is_named(db):
    existing = project(db, db.company_id, "Setia Alam Phase 3B", code="PRJ-ZZT-S1")
    rows = _find(db, "Setia Alam Ph 3B")
    assert rows == [{"project_id": existing.id, "project_code": "PRJ-ZZT-S1", "title": "Setia Alam Phase 3B"}]


def test_d4_another_developers_similarly_named_project_is_still_named(db):
    """A duplicate is a duplicate whoever the developer is (the typed developer is only text)."""
    other = developer(db, db.company_id, "Zeta Holdings Sdn Bhd")
    existing = project(db, db.company_id, "Setia Alam Phase 3B", developer_party=other)
    assert [r["project_id"] for r in _find(db, "Setia Alam Ph 3B", developer_name="Eta Group")] == [existing.id]


def test_d4_unrelated_titles_are_not_named(db):
    project(db, db.company_id, "Tropicana Aman Phase 2")
    assert _find(db, "Setia Alam Ph 3B") == []


# ------------------------------------------------------------------ D5 meaning


def test_d5_the_threshold_constant():
    from app.services.project_registration_service import REGISTRATION_SEMANTIC_THRESHOLD

    assert REGISTRATION_SEMANTIC_THRESHOLD == 0.80


def test_d5_a_cosine_at_or_above_the_bar_names_the_project(db, monkeypatch):
    from app.services import project_registration_service as svc

    existing = project(db, db.company_id, "MENARA ZETA OFFICE TOWER", code="PRJ-ZZT-M1")
    for cosine in (0.80, 0.93):
        monkeypatch.setattr(svc, "semantic_matches", lambda db_, **kw: [(existing.id, cosine)])
        rows = _find(db, "BLOK PEJABAT BARU ZETA")
        assert [r["project_id"] for r in rows] == [existing.id], cosine


def test_d5_a_cosine_below_the_bar_does_not(db, monkeypatch):
    from app.services import project_registration_service as svc

    existing = project(db, db.company_id, "MENARA ZETA OFFICE TOWER")
    monkeypatch.setattr(svc, "semantic_matches", lambda db_, **kw: [(existing.id, 0.79)])
    assert _find(db, "BLOK PEJABAT BARU ZETA") == []


def test_d5_an_embedding_failure_returns_no_matches_and_never_raises(db, monkeypatch):
    from app.services import project_registration_service as svc

    def boom(text):
        raise RuntimeError("no embedding key")

    monkeypatch.undo()  # drop the autouse-style stub so the real semantic_matches runs
    monkeypatch.setattr(svc, "embed_text", boom)
    assert svc.semantic_matches(db, company_id=db.company_id, text="BLOK PEJABAT BARU ZETA") == []


def test_d5_the_other_signals_still_apply_when_the_embedding_fails(db, monkeypatch):
    from app.services import project_registration_service as svc

    existing = project(db, db.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")

    def boom(text):
        raise RuntimeError("timeout")

    monkeypatch.undo()
    monkeypatch.setattr(svc, "embed_text", boom)
    rows = _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU")
    assert [r["project_id"] for r in rows] == [existing.id]


# ------------------------------------------------------------------ D6 scope, cap, order


def test_d6_another_companys_project_is_never_named(db, monkeypatch):
    from app.services import project_registration_service as svc

    foreign = project(db, db.other_company, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    foreign_spelled = project(db, db.other_company, "Setia Alam Phase 3B")
    # the meaning signal also offers the foreign project: the company filter must hold
    monkeypatch.setattr(svc, "semantic_matches", lambda db_, **kw: [(foreign.id, 0.99)])
    assert _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU") == []
    assert _find(db, "Setia Alam Ph 3B") == []
    assert foreign_spelled.id


def test_d6_at_most_five_strongest_first_without_repeats(db, monkeypatch):
    from app.services import project_registration_service as svc

    title = "Setia Alam Ph 3B Lot 9001 Mukim Tebrau"
    lot = project(db, db.company_id, "Gudang Beta Lot 9001 Mukim Tebrau", code="PRJ-ZZT-LOT")
    meaning = project(db, db.company_id, "Menara Zeta Office Tower", code="PRJ-ZZT-MEAN")
    spelled = project(db, db.company_id, "Setia Alam Phase 3B", code="PRJ-ZZT-SPELL")
    assert not _spelling_names(db, title, meaning), "premise: the meaning project is not a spelling hit"
    assert _spelling_names(db, title, spelled), "premise: the spelling project is a spelling hit"
    monkeypatch.setattr(
        svc, "semantic_matches", lambda db_, **kw: [(meaning.id, 0.91), (lot.id, 0.95)]
    )
    rows = _find(db, title)
    assert _codes(rows) == ["PRJ-ZZT-LOT", "PRJ-ZZT-MEAN", "PRJ-ZZT-SPELL"]
    assert len({r["project_id"] for r in rows}) == len(rows)


def test_d6_the_cap_is_five(db):
    for n in range(7):
        project(db, db.company_id, f"BLOK {n} SENTINEL LOT 9001 MUKIM TEBRAU")
    rows = _find(db, "CADANGAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU")
    assert len(rows) == 5
    assert len(_find(db, "CADANGAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU", limit=2)) == 2
