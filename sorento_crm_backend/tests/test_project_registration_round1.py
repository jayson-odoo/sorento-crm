"""PROJECT-REG-PORTAL fix round 1 (reviewer + security-reviewer findings), REWORKED onto projects.

Each block names the finding it pins. Plan: PLAN-project-registration-portal-25oct.md. The row
lock (S6), owner assignment (S9), cross-company ids (S10), the drafts filter (N12) and the
ineligible applicant (round 2) moved to test_project_registration_approval.py, where approve
and reject now live; the embedding cost (B3) is re-pointed at the reads that still embed: a
pending project's detail and the portal's.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event, text

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._project_registration_support import (
    STAFF,
    KIND,
    PORTAL,
    SUB,
    as_contact,
    as_user,
    create_draft,
    developer,
    fields,
    pending,
    project,
    registration,
    second_company,
    sorento,
    stub_semantic,
    submit,
    uid,
    world,  # noqa: F401  (fixture)
)

from app.services import project_registration_service as _svc

MANAGE = "projects.projects.manage"
REAL_SEMANTIC = _svc.semantic_matches  # before `world` stubs it


# ------------------------------------------------------------------ B1 title length


def test_b1_a_title_over_2000_characters_is_422_naming_the_field(world):
    res = as_contact(world, world.a).post(
        SUB, json={"fields": fields(world.debtor_a.id, title="X" * 2001)}
    )
    assert res.status_code == 422, res.text
    assert "title" in res.text.lower()


def test_b1_a_title_of_exactly_2000_is_fine(world):
    res = as_contact(world, world.a).post(
        SUB, json={"fields": fields(world.debtor_a.id, title="X" * 2000)}
    )
    assert res.status_code == 200, res.text


def test_b1_submit_carrying_a_long_title_is_422_and_changes_nothing(world):
    d = create_draft(world)
    res = submit(world, d["id"], body=fields(world.debtor_a.id, title="X" * 2001))
    assert res.status_code == 422, res.text
    assert registration(world, d["id"]).approval_state == "draft"


# ------------------------------------------------------------------ B2 lead numbering seed


def test_b2_the_lead_rule_keeps_reset_none_and_the_project_rule_is_monthly():
    from app.services import project_seed_service as seed

    with blank_session() as session:
        assert seed.seed_numbering_rule(session) is True
        assert seed.seed_lead_numbering_rule(session) is True
        rows = dict(
            session.execute(
                text(
                    "select doc_type, reset_policy from document_numbering_rules "
                    "where doc_type in ('project', 'project_lead')"
                )
            ).all()
        )
        assert rows["project"] == "monthly"
        assert rows[seed.LEAD_NUMBERING["doc_type"]] == "none"


# ------------------------------------------------------------------ B3 embedding cost


@pytest.fixture
def embed_calls(monkeypatch):
    """The real meaning signal over a counting fake of the one network call."""
    from app.services import embedding_worker
    from app.services import project_registration_service as svc

    real = REAL_SEMANTIC
    calls: list = []

    def fake(chunks, timeout=30):
        calls.append({"chunks": list(chunks), "timeout": timeout})
        return [[0.0, 0.0, 0.0] for _ in chunks]

    monkeypatch.setattr(embedding_worker, "_embed_text_chunks", fake)
    svc.clear_embedding_cache()
    yield SimpleCalls(calls, real, svc)
    svc.clear_embedding_cache()


class SimpleCalls:
    def __init__(self, calls, real, svc):
        self.calls, self.real, self.svc = calls, real, svc

    def enable(self, monkeypatch):
        monkeypatch.setattr(self.svc, "semantic_matches", self.real)


def test_b3_a_pending_projects_detail_makes_one_embed_call_at_three_seconds(world, embed_calls, monkeypatch):
    rid = pending(world, title="QUEUE TOWER 0")
    embed_calls.enable(monkeypatch)
    res = as_user(world, world.approver).get(f"{STAFF}/{rid}")
    assert res.status_code == 200, res.text
    assert len(embed_calls.calls) == 1
    assert len(embed_calls.calls[0]["chunks"]) == 1
    assert embed_calls.calls[0]["timeout"] == 3


def test_b3_a_second_read_of_the_same_project_makes_no_embed_call(world, embed_calls, monkeypatch):
    rid = pending(world, title="CACHED TOWER")
    embed_calls.enable(monkeypatch)
    c = as_user(world, world.approver)
    assert c.get(f"{STAFF}/{rid}").status_code == 200
    assert len(embed_calls.calls) == 1
    assert c.get(f"{STAFF}/{rid}").status_code == 200
    assert len(embed_calls.calls) == 1


def test_b3_the_portal_detail_goes_through_the_same_cache(world, embed_calls, monkeypatch):
    rid = pending(world, title="PORTAL CACHED TOWER")
    embed_calls.enable(monkeypatch)
    c = as_contact(world, world.a)
    assert c.get(f"{SUB}/{rid}").status_code == 200
    assert c.get(f"{SUB}/{rid}").status_code == 200
    assert len(embed_calls.calls) == 1
    # and the CRM read of the same text is a cache hit too
    assert as_user(world, world.approver).get(f"{STAFF}/{rid}").status_code == 200
    assert len(embed_calls.calls) == 1


def test_b3_a_failing_embed_keeps_the_detail_readable_and_is_not_retried(world, monkeypatch):
    from app.services import embedding_worker
    from app.services import project_registration_service as svc

    real = REAL_SEMANTIC
    attempts: list = []

    def boom(chunks, timeout=30):
        attempts.append(len(chunks))
        raise RuntimeError("provider down")

    monkeypatch.setattr(embedding_worker, "_embed_text_chunks", boom)
    svc.clear_embedding_cache()
    ids = [pending(world, title=f"GUDANG {n} DI ATAS LOT 9001, MUKIM TEBRAU", mukim="Tebrau") for n in range(3)]
    monkeypatch.setattr(svc, "semantic_matches", real)
    c = as_user(world, world.approver)
    for rid in ids:
        res = c.get(f"{STAFF}/{rid}")
        assert res.status_code == 200, res.text
        assert res.json()["possible_duplicates"] == []
    assert len(attempts) == 1  # one try, then the 30 s back-off: not once per read


def test_b3_ownership_checks_never_build_the_duplicates(world, monkeypatch):
    from app.services import project_registration_service as svc

    rid = pending(world)

    def boom(*a, **kw):
        raise AssertionError("the duplicates were computed for an ownership check")

    monkeypatch.setattr(svc, "find_possible_duplicates", boom)
    c = as_contact(world, world.a)
    assert c.get(f"{SUB}/{rid}/revisions").status_code == 200
    assert c.get(f"{SUB}/{rid}/neighbours").status_code == 200


# ------------------------------------------------------------------ S4 / S5 comments, attachments


def test_s4_the_kind_has_no_comments(world):
    rid = pending(world)
    c = as_contact(world, world.a)
    res = c.get(f"{SUB}/{rid}/comments")
    assert res.status_code in (400, 404), res.text
    res = c.post(f"{SUB}/{rid}/comments", data={"body": "hello"})
    assert res.status_code in (400, 404, 422), res.text


def test_s5_attachments_are_refused_for_the_kind(world):
    d = create_draft(world)
    c = as_contact(world, world.a)
    res = c.get(f"{PORTAL}/attachments", params={"kind": KIND, "submission_id": d["id"]})
    assert res.status_code == 400, res.text
    res = c.post(
        f"{PORTAL}/attachments",
        data={"kind": KIND, "submission_id": d["id"]},
        files={"file": ("a.png", b"x", "image/png")},
    )
    assert res.status_code == 400, res.text


# ------------------------------------------------------------------ S8 listener churn


def test_s8_only_a_title_or_developer_change_queues_a_project_embedding():
    from app.models.embeddings import EmbeddingQueue
    from app.services.embedding_change_listener import register_embedding_change_listeners

    register_embedding_change_listeners()
    with blank_session() as session:
        company_id = sorento(session)
        party = developer(session, company_id, "Zeta Holdings")
        row = project(session, company_id, "LISTENER TOWER")

        def queued():
            session.flush()
            rows = session.query(EmbeddingQueue).filter(
                EmbeddingQueue.source_type == "project", EmbeddingQueue.source_id == row.id
            )
            count = rows.count()
            # A source keeps one pending row (EMBED-QUEUE-DEDUPE), so settle each event
            # before the next step: otherwise a second change folds into the first row.
            rows.update({"status": "completed"}, synchronize_session=False)
            return count

        base = queued()
        assert base >= 1  # the insert
        from datetime import datetime

        row.last_meaningful_activity_at = datetime.utcnow()
        assert queued() == base
        row.title = "LISTENER TOWER PHASE 2"
        assert queued() == base + 1
        row.developer_party_id = party.id
        assert queued() == base + 2


def test_s8_the_profile_queues_the_parent_only_when_state_or_mukim_changes():
    from app.models.embeddings import EmbeddingQueue
    from app.models.projects import ProjectSalesProfile
    from app.services.embedding_change_listener import register_embedding_change_listeners

    register_embedding_change_listeners()
    with blank_session() as session:
        company_id = sorento(session)
        row = project(session, company_id, "PROFILE TOWER", state="Johor")

        def queued():
            session.flush()
            rows = session.query(EmbeddingQueue).filter(
                EmbeddingQueue.source_type == "project", EmbeddingQueue.source_id == row.id
            )
            count = rows.count()
            # A source keeps one pending row (EMBED-QUEUE-DEDUPE), so settle each event
            # before the next step: otherwise a second change folds into the first row.
            rows.update({"status": "completed"}, synchronize_session=False)
            return count

        base = queued()
        profile = session.get(ProjectSalesProfile, row.id)
        profile.location = "Somewhere"
        assert queued() == base
        profile.mukim = "Tebrau"
        assert queued() == base + 1


# ------------------------------------------------------------------ S11 customer company


def test_s11_the_customer_is_checked_under_the_registrations_company_only(world):
    from app.models.company import RespondContactCompany

    from ._project_registration_support import debtor

    d = create_draft(world)
    world.db.add(
        RespondContactCompany(id=uid(), respond_contact_id=world.a, company_id=world.other_company)
    )
    world.db.flush()
    foreign_debtor = debtor(world.db, world.other_company, world.agent_a)
    c = as_contact(world, world.a)
    res = c.put(f"{SUB}/{d['id']}", json={"fields": fields(foreign_debtor.id)})
    assert res.status_code == 422, res.text
    res = c.post(SUB, json={"fields": fields(foreign_debtor.id)})
    assert res.status_code == 422, res.text
