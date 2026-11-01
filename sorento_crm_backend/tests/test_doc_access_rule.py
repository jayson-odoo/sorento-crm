"""DOC-ACCESS-SIMPLE S1: the one-sentence rule (DAS-BE-4 .. DAS-BE-7).

A contact reads a file when ONE code is in the contact's active codes AND the type's ticks AND the
file's levels (the same code on all three). Staff read a type only when it carries the Staff tick.
Vectors are hand built (tests/_knowledge_seed.py); every refusal sits beside a positive control.
"""
from __future__ import annotations

import pytest

from tests._knowledge_seed import (
    query_embed,
    seed_attachment,
    seed_chunk,
    seed_reader,
    seed_team,
    seed_type,
    vec_with_similarity,
)
from tests._pg_fixture import blank_session

EXACT = vec_with_similarity(1.0)
ALL = ["dealer", "end_user", "sorento_office", "mocha_dealer", "cabana_dealer"]


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _file(db, att_type, levels, text, name=None):
    att = seed_attachment(db, att_type, name or f"{text}.pdf")
    att.access_levels = list(levels)
    db.flush()
    seed_chunk(db, att, EXACT, text=text)
    return att


def _ask(db, codes, **kw):
    from app.services import knowledge_service as ks

    out = ks.search_for_contact(db, access_codes=frozenset(codes), query="warranty", embed=query_embed, **kw)
    assert out["status"] == "ok", out
    return [p["text"] for p in out["passages"]]


# ---------------------------------------------------------------- DAS-BE-4


def test_contact_needs_same_code_on_type_and_file(db):
    t = seed_type(db, staff=False, codes=["dealer"])
    _file(db, t, ["end_user"], "end user level file")

    assert _ask(db, {"dealer", "end_user"}) == [], "dealer is ticked, end_user is on the file: never the same code"
    # Positive control: the file also carries dealer.
    _file(db, t, ["dealer", "end_user"], "dealer level file")
    assert _ask(db, {"dealer", "end_user"}) == ["dealer level file"]


def test_office_code_reads_only_when_ticked(db):
    t = seed_type(db, staff=False, codes=["dealer"])
    _file(db, t, ALL, "warranty policy")
    assert _ask(db, {"sorento_office"}) == []

    t2 = seed_type(db, staff=False, codes=["dealer", "sorento_office"])
    _file(db, t2, ALL, "office warranty policy")
    assert _ask(db, {"sorento_office"}) == ["office warranty policy"]


def test_brand_code_reads_brand_file(db):
    t = seed_type(db, staff=False, codes=["mocha_dealer"])
    _file(db, t, ALL, "mocha warranty")

    assert _ask(db, {"mocha_dealer"}) == ["mocha warranty"]
    assert _ask(db, {"cabana_dealer"}) == []


# ---------------------------------------------------------------- DAS-BE-5


def test_no_code_reads_nothing(db):
    t = seed_type(db, staff=True, codes=ALL)
    _file(db, t, ALL, "everything")
    calls = []

    from app.services import knowledge_service as ks

    def spy(texts):
        calls.append(texts)
        return query_embed(texts)

    out = ks.search_for_contact(db, access_codes=frozenset(), query="q", embed=spy)

    assert out == {"status": "ok", "passages": []}
    assert calls == []
    assert _ask(db, {"dealer"}) == ["everything"], "control: one ticked code reads it"


def test_codes_not_ticked_read_nothing(db):
    _file(db, seed_type(db, staff=True, codes=[]), ALL, "staff only passage")
    _file(db, seed_type(db, staff=False, codes=["dealer"]), ALL, "dealer passage")

    assert _ask(db, {"end_user", "sorento_office"}) == []
    assert _ask(db, {"dealer"}) == ["dealer passage"]


# ---------------------------------------------------------------- DAS-BE-6


def _staff_ask(db, user_id):
    from app.services import knowledge_service as ks

    return ks.search(db, user_id=user_id, query="leave", embed=query_embed)


def test_staff_reads_only_staff_ticked_types(db):
    reader = seed_reader(db)
    _file(db, seed_type(db, staff=True, codes=[]), ALL, "staff ticked passage")
    _file(db, seed_type(db, staff=True, codes=["dealer"]), ALL, "both ticked passage")
    _file(db, seed_type(db, staff=False, codes=["dealer", "end_user"]), ALL, "codes only passage")

    out = _staff_ask(db, reader)

    assert out["status"] == "ok"
    assert sorted(p["text"] for p in out["passages"]) == ["both ticked passage", "staff ticked passage"]


def test_staff_search_is_denied_without_the_permission(db):
    _file(db, seed_type(db, staff=True), ALL, "staff ticked passage")

    out = _staff_ask(db, seed_reader(db, slugs=()))

    assert out["status"] == "denied" and out["passages"] == []


def test_handoff_teams_only_staff_ticked(db):
    reader = seed_reader(db)
    hr, sales, codes_only = seed_team(db, "ZZTK HR"), seed_team(db, "ZZTK Sales"), seed_team(db, "ZZTK Codes Only")
    seed_type(db, staff=True, codes=[], team_id=hr)
    seed_type(db, staff=True, codes=["dealer"], team_id=sales)
    seed_type(db, staff=False, codes=["dealer"], team_id=codes_only)

    assert sorted(_staff_ask(db, reader)["handoff_teams"]) == ["ZZTK HR", "ZZTK Sales"]


# ---------------------------------------------------------------- DAS-BE-7


@pytest.fixture
def enqueued(monkeypatch):
    from app.services import knowledge_service as ks

    calls: list[str] = []
    monkeypatch.setattr(ks, "_enqueue", lambda attachment_id: calls.append(str(attachment_id)))
    return calls


def test_type_ai_on_clause_means_staff_or_any_code(db):
    from app.models.resources import AttachmentType
    from app.services import knowledge_service as ks

    off = seed_type(db, staff=False, codes=[])
    staff = seed_type(db, staff=True, codes=[])
    codes = seed_type(db, staff=False, codes=["dealer"])
    both = seed_type(db, staff=True, codes=["dealer"])

    on = {str(r[0]) for r in db.query(AttachmentType.id).filter(ks.type_ai_on_clause()).all()}

    assert {str(t.id) for t in (staff, codes, both)} <= on
    assert str(off.id) not in on


def test_is_readable_filename_is_pdf_or_docx_only():
    from app.services.knowledge_service import is_readable_filename

    assert is_readable_filename("Warranty.PDF") and is_readable_filename("terms.docx")
    assert not is_readable_filename("price list.xlsx") and not is_readable_filename("noextension")


def test_queue_read_queues_a_codes_only_type_and_skips_an_off_type(db, enqueued):
    from app.services import knowledge_service as ks

    on = seed_attachment(db, seed_type(db, staff=False, codes=["dealer"]))
    off = seed_attachment(db, seed_type(db, staff=False, codes=[]))

    assert ks.queue_read(db, on) is True
    assert ks.queue_read(db, off) is False
    assert enqueued == [str(on.id)]


def test_read_block_reason_off_type(db):
    from app.services import knowledge_service as ks

    off = seed_attachment(db, seed_type(db, staff=False, codes=[]))
    on = seed_attachment(db, seed_type(db, staff=False, codes=["dealer"]))

    assert ks.read_block_reason(db, off) == "The AI does not read files of this type."
    assert ks.read_block_reason(db, on) is None


def _update(db, att_type, **fields):
    from app.schemas.resources import AttachmentTypeUpdate
    from app.services.resources_service import AttachmentTypeService

    return AttachmentTypeService(db).update_type(str(att_type.id), AttachmentTypeUpdate(**fields))


def test_first_tick_queues_files(db, enqueued):
    from tests._knowledge_seed import seed_access_codes

    seed_access_codes(db, ["dealer"])
    t = seed_type(db, staff=False, codes=[])
    never = seed_attachment(db, t, "never.pdf")
    done = seed_attachment(db, t, "done.pdf")
    done.ai_read_status = "done"
    db.flush()

    _update(db, t, ai_read_codes=["dealer"])

    assert enqueued == [str(never.id)]


def test_last_untick_queues_nothing(db, enqueued):
    from tests._knowledge_seed import seed_access_codes

    seed_access_codes(db, ["dealer"])
    t = seed_type(db, staff=False, codes=["dealer"])
    seed_attachment(db, t, "never.pdf")

    _update(db, t, ai_read_codes=[])
    assert enqueued == []

    # A second tick on a type that is already on queues nothing either.
    t2 = seed_type(db, staff=True, codes=[])
    seed_attachment(db, t2, "never2.pdf")
    _update(db, t2, ai_read_codes=["dealer"])
    assert enqueued == []
