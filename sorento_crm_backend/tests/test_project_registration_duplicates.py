"""PROJECT-REG-PORTAL possible duplicates (UAC D5, D6 as amended by audit round 3).

Owner ruling, audit round 3: duplicates are named by MEANING ONLY. A project is a possible
duplicate exactly when `semantic_matches` returns it at or above
`REGISTRATION_SEMANTIC_THRESHOLD`. The lot + mukim rule, the spelling (trigram) rule and the
hard-coded phase-sibling filter are gone: the model decides. The lot / mukim parsers go with them.

Service level, over a Postgres session. The meaning signal is stubbed at `semantic_matches` /
`embed_text` so no test needs an embedding key; the stub list is the only way a project is named.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._project_registration_support import project, stub_semantic
from ._sample_request_seed import second_company, sorento


@pytest.fixture
def db(monkeypatch):
    from app.models.base import company_scope

    holder = stub_semantic(monkeypatch)
    with blank_session() as session:
        session.company_id = sorento(session)
        session.other_company = second_company(session)
        session.semantic = holder
        # Both companies in scope, on purpose: the service's own company predicate must be the
        # only thing keeping the other company's rows out.
        with company_scope(session, frozenset({session.company_id, session.other_company})):
            yield session


def _find(db, title, **kw):
    from app.services.project_registration_service import find_possible_duplicates

    return find_possible_duplicates(db, company_id=db.company_id, title=title, **kw)


def _codes(rows):
    return [r["project_code"] for r in rows]


# ------------------------------------------------------------------ the removed rules


def test_the_lot_mukim_and_spelling_helpers_no_longer_exist():
    from app.services import project_registration_service as svc

    for name in ("parse_lot_numbers", "parse_mukim", "lot_pattern"):
        assert not hasattr(svc, name), name


def test_the_service_no_longer_reads_the_spelling_matcher():
    """No `find_clashes` / sibling-filter import left in the duplicates path: the clash
    matcher stays the staff registration lock's, not the queue's."""
    import inspect

    from app.services import project_registration_service as svc

    source = inspect.getsource(svc.find_possible_duplicates)
    assert "find_clashes" not in source
    assert "are_sibling_developments" not in source


def test_same_lot_and_mukim_without_a_meaning_match_is_not_named(db):
    project(db, db.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    assert _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU, JOHOR") == []


def test_a_spelling_near_title_without_a_meaning_match_is_not_named(db):
    project(db, db.company_id, "Setia Alam Phase 3B")
    assert _find(db, "Setia Alam Ph 3B") == []


def test_a_title_equal_to_a_project_without_a_meaning_match_is_not_named(db):
    """Even the identical title is not named by spelling: the exact-title refusal lives at
    approve time (the identity index), not in this list."""
    project(db, db.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    assert _find(db, "KILANG ALPHA LOT 9001 MUKIM TEBRAU") == []


def test_a_phase_sibling_with_a_meaning_match_is_named(db):
    """No hard-coded phase filter: when the model says it is close, it is named."""
    sibling = project(db, db.company_id, "TAMAN DELTA FASA 4 DI ATAS LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-SIB")
    db.semantic.append((sibling.id, 0.91))
    rows = _find(db, "TAMAN DELTA FASA 5 DI ATAS LOT 9001 MUKIM TEBRAU")
    assert [r["project_id"] for r in rows] == [sibling.id]


def test_a_phase_sibling_without_a_meaning_match_is_not_named(db):
    project(db, db.company_id, "TAMAN DELTA FASA 4 DI ATAS LOT 9001 MUKIM TEBRAU")
    assert _find(db, "TAMAN DELTA FASA 5 DI ATAS LOT 9001 MUKIM TEBRAU") == []


# ------------------------------------------------------------------ D5 meaning


def test_d5_the_threshold_constant():
    from app.services.project_registration_service import REGISTRATION_SEMANTIC_THRESHOLD

    assert REGISTRATION_SEMANTIC_THRESHOLD == 0.80


def test_d5_a_cosine_at_or_above_the_bar_names_the_project(db):
    existing = project(db, db.company_id, "MENARA ZETA OFFICE TOWER", code="PRJ-ZZT-M1")
    for cosine in (0.80, 0.93):
        db.semantic[:] = [(existing.id, cosine)]
        rows = _find(db, "BLOK PEJABAT BARU ZETA")
        assert rows == [{"project_id": existing.id, "project_code": "PRJ-ZZT-M1", "title": existing.title}], cosine


def test_d5_a_cosine_below_the_bar_does_not(db):
    existing = project(db, db.company_id, "MENARA ZETA OFFICE TOWER")
    db.semantic[:] = [(existing.id, 0.79)]
    assert _find(db, "BLOK PEJABAT BARU ZETA") == []


def test_d5_an_embedding_failure_returns_no_matches_and_never_raises(db, monkeypatch):
    from app.services import project_registration_service as svc

    def boom(*args, **kwargs):
        raise RuntimeError("no embedding key")

    monkeypatch.undo()  # drop the stub so the real semantic_matches runs
    monkeypatch.setattr(svc, "embed_text", boom)
    monkeypatch.setattr(svc, "embed_texts", boom)
    assert svc.semantic_matches(db, company_id=db.company_id, text="BLOK PEJABAT BARU ZETA") == []
    assert _find(db, "BLOK PEJABAT BARU ZETA") == []


# ------------------------------------------------------------------ D6 scope, cap, order


def test_d6_another_companys_project_is_never_named(db):
    foreign = project(db, db.other_company, "KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    db.semantic[:] = [(foreign.id, 0.99)]  # the meaning signal offers it: the company filter holds
    assert _find(db, "CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU") == []


def test_d6_strongest_meaning_first_without_repeats(db):
    a = project(db, db.company_id, "Menara Zeta Office Tower", code="PRJ-ZZT-A")
    b = project(db, db.company_id, "Menara Eta Office Tower", code="PRJ-ZZT-B")
    c = project(db, db.company_id, "Menara Theta Office Tower", code="PRJ-ZZT-C")
    db.semantic[:] = [(b.id, 0.85), (a.id, 0.95), (c.id, 0.90), (a.id, 0.95)]
    rows = _find(db, "Blok Pejabat Baru")
    assert _codes(rows) == ["PRJ-ZZT-A", "PRJ-ZZT-C", "PRJ-ZZT-B"]
    assert len({r["project_id"] for r in rows}) == len(rows)


def test_d6_the_cap_is_five_and_limit_is_honoured(db):
    made = [project(db, db.company_id, f"BLOK {n} SENTINEL TOWER") for n in range(7)]
    db.semantic[:] = [(p.id, 0.99 - n * 0.01) for n, p in enumerate(made)]
    assert len(_find(db, "Blok baru")) == 5
    assert len(_find(db, "Blok baru", limit=2)) == 2
    assert [r["project_id"] for r in _find(db, "Blok baru")] == [p.id for p in made[:5]]


def test_d6_an_unknown_project_id_from_the_meaning_signal_is_ignored(db):
    real = project(db, db.company_id, "Menara Zeta Office Tower")
    db.semantic[:] = [("00000000-0000-0000-0000-00000000dead", 0.99), (real.id, 0.90)]
    assert [r["project_id"] for r in _find(db, "Blok Pejabat Baru")] == [real.id]
