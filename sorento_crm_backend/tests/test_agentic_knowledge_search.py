"""AGENTIC-KNOWLEDGE P1, asking (UAC AC-K12, K13, K17 helper) and the safety rules (AC-K19).

`knowledge_service.search` joins each chunk to its attachment and that attachment's type AT
QUERY TIME, so the vectors here are hand built (see tests/_knowledge_seed.py) and every
refusal is asserted by the absence of an otherwise-matching passage: a positive control sits
beside each negative so a test cannot pass because nothing ever matched.
"""
from __future__ import annotations

import pytest

from app.models.base import UNSET, set_company_scope
from tests._knowledge_seed import (
    SORENTO_COMPANY_ID,
    query_embed,
    seed_attachment,
    seed_chunk,
    seed_company,
    seed_reader,
    seed_team,
    seed_type,
    vec_with_similarity,
)
from tests._pg_fixture import blank_session

EXACT = vec_with_similarity(1.0)


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _ask(db, user_id, query="how many days of annual leave?", **kw):
    from app.services import knowledge_service as ks

    return ks.search(db, user_id=user_id, query=query, embed=query_embed, **kw)


def _world(db, *, audience="staff", team_name=None):
    """A reader, one readable file with one exactly-matching chunk, and its type."""
    team_id = seed_team(db, team_name) if team_name else None
    att_type = seed_type(db, audience=audience, team_id=team_id)
    att = seed_attachment(db, att_type, "Employee Handbook 2026.pdf")
    chunk = seed_chunk(db, att, EXACT, text="Annual leave is 14 days after three years.", page=14, heading="Leave")
    return seed_reader(db), att_type, att, chunk


# ---------------------------------------------------------------- AC-K12 shape and ranking


def test_a_matching_passage_carries_document_page_heading_text_and_similarity(db):
    user_id, _, _, _ = _world(db)

    out = _ask(db, user_id)

    assert out["status"] == "ok"
    assert len(out["passages"]) == 1
    p = out["passages"][0]
    assert "Employee Handbook 2026" in p["document"]
    assert p["page"] == 14
    assert p["heading"] == "Leave"
    assert p["text"] == "Annual leave is 14 days after three years."
    assert p["similarity"] == pytest.approx(1.0, abs=1e-3)


def test_passages_come_best_first_and_top_k_caps_them(db):
    user_id = seed_reader(db)
    att_type = seed_type(db, audience="staff")
    att = seed_attachment(db, att_type)
    seed_chunk(db, att, vec_with_similarity(0.97), text="second best", index=0, page=2)
    seed_chunk(db, att, vec_with_similarity(1.0), text="best", index=1, page=1)
    seed_chunk(db, att, vec_with_similarity(0.98), text="middle", index=2, page=3)

    out = _ask(db, user_id, top_k=2)

    assert [p["text"] for p in out["passages"]] == ["best", "middle"]


def test_a_passage_below_the_similarity_floor_is_dropped(db):
    from app.services.knowledge_service import KNOWLEDGE_SIMILARITY_FLOOR

    user_id = seed_reader(db)
    att = seed_attachment(db, seed_type(db, audience="staff"))
    seed_chunk(db, att, vec_with_similarity(min(1.0, KNOWLEDGE_SIMILARITY_FLOOR + 0.03)), text="above", index=0)
    seed_chunk(db, att, vec_with_similarity(KNOWLEDGE_SIMILARITY_FLOOR - 0.05), text="below", index=1)

    out = _ask(db, user_id)

    assert [p["text"] for p in out["passages"]] == ["above"]


def test_a_search_with_nothing_relevant_is_ok_and_empty(db):
    user_id, *_ = _world(db)
    # An orthogonal query: similarity 0 to every stored chunk.
    from app.services import knowledge_service as ks
    from tests._knowledge_seed import one_hot

    out = ks.search(db, user_id=user_id, query="unrelated", embed=lambda texts: [one_hot(7)])

    assert out["status"] == "ok"
    assert out["passages"] == []


# ---------------------------------------------------------------- AC-K12 audiences (staff see all three)


@pytest.mark.parametrize("audience", ["staff", "dealer", "public"])
def test_staff_read_every_audience_that_is_not_off(db, audience):
    user_id, *_ = _world(db, audience=audience)

    assert len(_ask(db, user_id)["passages"]) == 1


# ---------------------------------------------------------------- AC-K13 hand-off


def test_handoff_teams_are_the_distinct_escalate_to_names_of_readable_types(db):
    user_id = seed_reader(db)
    hr = seed_team(db, "ZZTK HR")
    sales = seed_team(db, "ZZTK Sales Support")
    off_only = seed_team(db, "ZZTK Off Team")
    for audience, team in (("staff", hr), ("dealer", hr), ("public", sales), ("off", off_only)):
        att = seed_attachment(db, seed_type(db, audience=audience, team_id=team))
        seed_chunk(db, att, EXACT, text=f"{audience} passage")
    # A readable type with no hand-off team contributes nothing.
    seed_attachment(db, seed_type(db, audience="staff", team_id=None))

    out = _ask(db, user_id)

    assert sorted(out["handoff_teams"]) == ["ZZTK HR", "ZZTK Sales Support"]


def test_handoff_teams_are_still_named_when_no_passage_matches(db):
    """The no-answer path ("not in the documents, please ask HR") needs the team even with 0 passages."""
    from app.services import knowledge_service as ks
    from tests._knowledge_seed import one_hot

    team = seed_team(db, "ZZTK HR")
    att = seed_attachment(db, seed_type(db, audience="staff", team_id=team))
    seed_chunk(db, att, EXACT)
    user_id = seed_reader(db)

    out = ks.search(db, user_id=user_id, query="something the handbook lacks", embed=lambda t: [one_hot(9)])

    assert out["status"] == "ok"
    assert out["passages"] == []
    assert out["handoff_teams"] == ["ZZTK HR"]


# ---------------------------------------------------------------- AC-K19 safety


def test_a_user_without_the_read_permission_gets_a_refusal_and_no_passages(db):
    _world(db)
    nobody = seed_reader(db, slugs=("inventory.stock.view",))

    out = _ask(db, nobody)

    assert out == {"status": "denied", "passages": [], "handoff_teams": []}


def test_the_read_permission_is_the_one_that_opens_the_files(db):
    from app.services.knowledge_service import READ_PERMISSION

    assert READ_PERMISSION == "resource.attachments.view"
    user_id, *_ = _world(db)
    assert _ask(db, user_id)["status"] == "ok"
    assert _ask(db, seed_reader(db, slugs=("resource.attachments.upload",)))["status"] == "denied"


def test_another_companys_file_is_not_returned_to_a_user_scoped_to_mine(db):
    other = seed_company(db)
    user_id = seed_reader(db)
    att_type = seed_type(db, audience="staff")
    mine = seed_attachment(db, att_type, "Mine.pdf", company_id=SORENTO_COMPANY_ID)
    theirs = seed_attachment(db, att_type, "Theirs.pdf", company_id=other)
    seed_chunk(db, mine, EXACT, text="my company passage")
    seed_chunk(db, theirs, EXACT, text="other company passage")

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    out = _ask(db, user_id)
    assert [p["text"] for p in out["passages"]] == ["my company passage"]

    # Positive control: scoped to the other company, the same query sees only its file.
    set_company_scope(db, frozenset({other}))
    out = _ask(db, user_id)
    assert [p["text"] for p in out["passages"]] == ["other company passage"]


def test_an_unset_company_scope_returns_nothing(db):
    """Fail closed, as the records search does (`_embedding_company_filter`)."""
    user_id, *_ = _world(db)
    assert len(_ask(db, user_id)["passages"]) == 1

    set_company_scope(db, UNSET)

    assert _ask(db, user_id)["passages"] == []


def test_a_chunk_whose_stamped_company_differs_from_the_scope_is_not_returned(db):
    """The chunk's own company_id is filtered too, not only the attachment's."""
    other = seed_company(db)
    user_id = seed_reader(db)
    att = seed_attachment(db, seed_type(db, audience="staff"), company_id=SORENTO_COMPANY_ID)
    seed_chunk(db, att, EXACT, company_id=other)

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))

    assert _ask(db, user_id)["passages"] == []


def test_switching_the_type_to_off_hides_already_read_files_at_once(db):
    user_id, att_type, _, _ = _world(db)
    assert len(_ask(db, user_id)["passages"]) == 1

    att_type.ai_audience = "off"
    db.flush()

    assert _ask(db, user_id)["passages"] == [], "audience is read live, with no re-embed"

    att_type.ai_audience = "dealer"
    db.flush()
    assert len(_ask(db, user_id)["passages"]) == 1, "and switching back shows them again"


def test_a_deleted_attachment_no_longer_answers(db):
    user_id, _, att, _ = _world(db)
    assert len(_ask(db, user_id)["passages"]) == 1

    db.delete(att)
    db.flush()

    assert _ask(db, user_id)["passages"] == []


def test_a_file_whose_type_was_removed_no_longer_answers(db):
    user_id, att_type, att, _ = _world(db)

    att.attachment_type_id = None
    db.flush()

    assert _ask(db, user_id)["passages"] == []


def test_the_records_search_never_returns_a_knowledge_chunk(db):
    """AC-K10 at the reader: a keep-set records search over the same vector finds no knowledge row."""
    from app.services.embedding_service import EmbeddingReadService
    from app.services.embedding_settings import records_search_model

    model = records_search_model(db)
    att = seed_attachment(db, seed_type(db, audience="staff"))
    # Same vector, same model as the records search: only the source type differs.
    seed_chunk(db, att, EXACT, text="a knowledge row", source_type="knowledge", model_name=model)
    seed_chunk(db, att, EXACT, text="a record row", source_type="attachment", model_name=model)

    for source_type in (None, "attachment", "knowledge"):
        rows = EmbeddingReadService(db).search_current(EXACT, top_k=20, source_type=source_type)
        assert not [c for c, _, _ in rows if c.source_type == "knowledge"], source_type
    control = EmbeddingReadService(db).search_current(EXACT, top_k=20, source_type="attachment")
    assert [c.chunk_text for c, _, _ in control] == ["a record row"], "the control row is findable"


# ---------------------------------------------------------------- AC-K17 protocol helper


def test_the_protocol_is_appended_once_and_names_both_tools():
    from app.services import knowledge_service as ks

    base = "You are the assistant."

    once = ks.with_knowledge_protocol(base)

    assert once.startswith(base)
    assert ks.KNOWLEDGE_PROTOCOL_HEADER == "KNOWLEDGE PROTOCOL"
    assert ks.KNOWLEDGE_PROTOCOL_HEADER in once
    assert "crm_knowledge_search" in once
    assert "user_guides_read" in once
    assert ks.with_knowledge_protocol(once) == once, "idempotent on its header"
    assert once.count(ks.KNOWLEDGE_PROTOCOL_HEADER) == 1


# ================================================================ FIX ROUND 1 (review findings)


def test_a_soft_deleted_attachment_is_not_returned(db):
    user_id, _, att, _ = _world(db)
    assert len(_ask(db, user_id)["passages"]) == 1

    att.is_deleted = True
    db.flush()

    assert _ask(db, user_id)["passages"] == []


def test_moving_a_file_to_another_company_moves_its_knowledge_chunks_with_it(db):
    """RS4: the chunk's company follows the attachment, so the new company's search finds it."""
    from sqlalchemy import text as sql

    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.services.attachment_company_service import AttachmentCompanyService

    other = seed_company(db)
    user_id = seed_reader(db)
    att = seed_attachment(db, seed_type(db, audience="staff"), company_id=SORENTO_COMPANY_ID)
    seed_chunk(db, att, EXACT, text="moves with the file")

    set_company_scope(db, frozenset({other}))
    assert _ask(db, user_id)["passages"] == [], "not visible to the other company before the move"

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    AttachmentCompanyService(db).apply(attachment_ids=[str(att.id)], directory_ids=[], company_id=other)

    docs = db.execute(
        sql("SELECT company_id FROM embedding_documents WHERE source_type = 'knowledge' AND source_id = :i"),
        {"i": str(att.id)},
    ).fetchall()
    chunks = db.execute(
        sql("SELECT company_id FROM embedding_chunks WHERE source_type = 'knowledge' AND source_id = :i"),
        {"i": str(att.id)},
    ).fetchall()
    assert [str(r[0]) for r in docs] == [other]
    assert [str(r[0]) for r in chunks] == [other]
    set_company_scope(db, frozenset({other}))
    assert [p["text"] for p in _ask(db, user_id)["passages"]] == ["moves with the file"]
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    assert _ask(db, user_id)["passages"] == [], "and the old company no longer sees it"
