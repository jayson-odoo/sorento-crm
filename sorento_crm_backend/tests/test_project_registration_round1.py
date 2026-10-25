"""PROJECT-REG-PORTAL fix round 1 (reviewer + security-reviewer findings), test-first.

Each block names the finding it pins. Plan: PLAN-project-registration-portal-25oct.md.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import event, text

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._project_registration_support import (
    CRM,
    KIND,
    PORTAL,
    SUB,
    approve_body,
    as_contact,
    as_user,
    create_draft,
    developer,
    fields,
    grant,
    pending,
    project,
    project_type,
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


@pytest.fixture
def db(monkeypatch):
    from app.models.base import company_scope

    stub_semantic(monkeypatch)
    with blank_session() as session:
        session.company_id = sorento(session)
        session.other_company = second_company(session)
        with company_scope(session, frozenset({session.company_id, session.other_company})):
            yield session


def _find(db, title, **kw):
    from app.services.project_registration_service import find_possible_duplicates

    return find_possible_duplicates(db, company_id=db.company_id, title=title, **kw)


# ------------------------------------------------------------------ B1 title and lots


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
    assert registration(world, d["id"]).status == "draft"


def test_b1_leading_zeros_do_not_change_a_lot_number():
    from app.services.project_registration_service import parse_lot_numbers

    assert parse_lot_numbers("DI ATAS LOT 09001") == {"9001"}
    assert parse_lot_numbers("PT 000123 DAN LOT 0") == {"123", "0"}


def test_b1_a_zero_padded_lot_still_matches_both_ways(db):
    padded = project(db, db.company_id, "KILANG ALPHA LOT 09001 MUKIM TEBRAU")
    assert [r["project_id"] for r in _find(db, "GUDANG DI ATAS LOT 9001, MUKIM TEBRAU")] == [padded.id]
    plain = project(db, db.company_id, "KILANG BETA LOT 7001 MUKIM KULAI")
    assert [r["project_id"] for r in _find(db, "GUDANG DI ATAS LOT 07001, MUKIM KULAI")] == [plain.id]


def test_b1_the_lot_pattern_carries_at_most_twenty_numbers():
    from app.services import project_registration_service as svc

    lots = {str(n) for n in range(1000, 1060)}
    assert svc.MAX_LOT_NUMBERS == 20
    pattern = svc.lot_pattern(lots)
    assert len(re.findall(r"\d{4}", pattern)) == 20


def test_b1_a_title_with_sixty_lots_is_answered_not_refused(db):
    title = "BLOK " + " ".join(f"LOT {n}" for n in range(1000, 1060)) + " MUKIM TEBRAU"
    assert isinstance(_find(db, title), list)


def test_b1_a_failing_lot_read_degrades_to_no_lot_matches(db, monkeypatch):
    from app.services import project_registration_service as svc

    existing = project(db, db.company_id, "Setia Alam Phase 3B")

    def boom(title):
        raise RuntimeError("bad row")

    monkeypatch.setattr(svc, "parse_lot_numbers", boom)
    assert [r["project_id"] for r in _find(db, "Setia Alam Ph 3B")] == [existing.id]


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


def test_b3_a_list_of_pending_rows_makes_one_embed_call_at_three_seconds(world, embed_calls, monkeypatch):
    for n in range(3):
        pending(world, title=f"QUEUE TOWER {n}")
    embed_calls.enable(monkeypatch)
    res = as_user(world, world.approver).get(CRM)
    assert res.status_code == 200, res.text
    assert len(res.json()["data"]) == 3
    assert len(embed_calls.calls) == 1
    assert len(embed_calls.calls[0]["chunks"]) == 3
    assert embed_calls.calls[0]["timeout"] == 3


def test_b3_a_second_read_of_the_same_rows_makes_no_embed_call(world, embed_calls, monkeypatch):
    rid = pending(world, title="CACHED TOWER")
    embed_calls.enable(monkeypatch)
    c = as_user(world, world.approver)
    assert c.get(f"{CRM}/{rid}").status_code == 200
    assert len(embed_calls.calls) == 1
    assert c.get(f"{CRM}/{rid}").status_code == 200
    assert c.get(CRM).status_code == 200
    assert len(embed_calls.calls) == 1


def test_b3_the_portal_detail_goes_through_the_same_cache(world, embed_calls, monkeypatch):
    rid = pending(world, title="PORTAL CACHED TOWER")
    embed_calls.enable(monkeypatch)
    c = as_contact(world, world.a)
    assert c.get(f"{SUB}/{rid}").status_code == 200
    assert c.get(f"{SUB}/{rid}").status_code == 200
    assert len(embed_calls.calls) == 1


def test_b3_a_failing_embed_keeps_the_other_signals_and_is_not_retried_per_row(world, monkeypatch):
    from app.services import embedding_worker
    from app.services import project_registration_service as svc

    real = REAL_SEMANTIC
    attempts: list = []

    def boom(chunks, timeout=30):
        attempts.append(len(chunks))
        raise RuntimeError("provider down")

    monkeypatch.setattr(embedding_worker, "_embed_text_chunks", boom)
    svc.clear_embedding_cache()
    existing = project(world.db, world.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-R1")
    ids = [
        pending(world, title=f"GUDANG {n} DI ATAS LOT 9001, MUKIM TEBRAU", mukim="Tebrau")
        for n in range(3)
    ]
    monkeypatch.setattr(svc, "semantic_matches", real)
    rows = as_user(world, world.approver).get(CRM).json()["data"]
    assert {r["id"] for r in rows} == set(ids)
    assert all([d["project_id"] for d in r["possible_duplicates"]] == [existing.id] for r in rows)
    assert len(attempts) == 1


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


# ------------------------------------------------------------------ S6 row lock


def test_s6_approve_and_reject_read_the_registration_with_a_row_lock(world):
    a, b = pending(world), pending(world)
    seen: list = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        if "project_registrations" in statement and statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement.upper())

    engine = world.db.get_bind()
    event.listen(engine, "before_cursor_execute", spy)
    try:
        c = as_user(world, world.approver)
        assert c.post(f"{CRM}/{a}/approve", json=approve_body(world, a)).status_code == 200
        assert any("FOR UPDATE" in s for s in seen)
        seen.clear()
        assert c.post(f"{CRM}/{b}/reject", json={"reason": "no"}).status_code == 200
        assert any("FOR UPDATE" in s for s in seen)
    finally:
        event.remove(engine, "before_cursor_execute", spy)


# ------------------------------------------------------------------ S7 mukim parse


def test_s7_the_mukim_stops_at_a_stop_word_or_a_full_stop():
    from app.services.project_registration_service import parse_mukim

    assert parse_mukim("GUDANG DI ATAS LOT 9001 MUKIM TEBRAU DAERAH JOHOR BAHRU") == "tebrau"
    assert parse_mukim("KILANG DI ATAS LOT 12 MUKIM KLANG.") == "klang"
    assert parse_mukim("LOT 5 MUKIM SENAI NEGERI JOHOR") == "senai"
    assert parse_mukim("LOT 5 MUKIM PLENTONG UNTUK TETUAN X") == "plentong"
    assert parse_mukim("LOT 5, MUKIM TEBRAU, JOHOR") == "tebrau"
    assert parse_mukim("LOT 5 MUKIM TEBRAU") == "tebrau"
    assert parse_mukim("LOT 5 MUKIM SUNGAI BULOH FOR MESSRS X") == "sungai buloh"


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
            return (
                session.query(EmbeddingQueue)
                .filter(EmbeddingQueue.source_type == "project", EmbeddingQueue.source_id == row.id)
                .count()
            )

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
            return (
                session.query(EmbeddingQueue)
                .filter(EmbeddingQueue.source_type == "project", EmbeddingQueue.source_id == row.id)
                .count()
            )

        base = queued()
        profile = session.get(ProjectSalesProfile, row.id)
        profile.location = "Somewhere"
        assert queued() == base
        profile.mukim = "Tebrau"
        assert queued() == base + 1


# ------------------------------------------------------------------ S9 owner assignment


def _approve(world, rid, **over):
    return as_user(world, world.approver).post(f"{CRM}/{rid}/approve", json=approve_body(world, rid, **over))


def test_s9_the_applicant_may_own_it_without_the_manage_grant(world):
    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.applicant_user)
    assert res.status_code == 200, res.text


def test_s9_another_owner_needs_the_manage_grant(world):
    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "project_owner_assign_forbidden"
    assert registration(world, rid).status == "pending"


def test_s9_a_manager_may_pick_another_active_user_of_the_company(world):
    world.perms[world.approver].add(MANAGE)
    grant(world.db, world.owner, "projects.projects.view", world.company_id)
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 200, res.text


def test_s9_an_owner_with_no_access_to_the_company_is_422(world):
    from app.models.company import UserCompany

    world.perms[world.approver].add(MANAGE)
    world.db.query(UserCompany).filter_by(user_id=world.owner).delete()
    world.db.flush()
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 422, res.text
    assert registration(world, rid).status == "pending"


def test_s9_an_inactive_owner_is_422(world):
    from app.models.user import User

    world.perms[world.approver].add(MANAGE)
    grant(world.db, world.owner, "projects.projects.view", world.company_id)
    world.db.get(User, world.owner).status = "inactive"
    world.db.flush()
    rid = pending(world)
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 422, res.text


def test_s9_without_an_applicant_the_owner_defaults_to_the_approver(world):
    from app.models.projects import Project

    world.perms[world.approver].discard(MANAGE)
    rid = pending(world, world.b)
    body = approve_body(world, rid)
    body.pop("owner_user_id", None)
    res = as_user(world, world.approver).post(f"{CRM}/{rid}/approve", json=body)
    assert res.status_code == 200, res.text
    world.db.expire_all()
    assert world.db.get(Project, res.json()["project_id"]).owner_user_id == world.approver


# ------------------------------------------------------------------ S10 cross-company ids


def test_s10_a_party_type_or_template_of_another_company_is_422(world):
    rid = pending(world)
    foreign_dev = developer(world.db, world.other_company, "Foreign Developer")
    foreign_arch = developer(world.db, world.other_company, "Foreign Architect", "architect")
    foreign_contractor = developer(world.db, world.other_company, "Foreign Builder", "main_contractor")
    foreign_type = project_type(world.db, world.other_company, "Foreign Type")
    c = as_user(world, world.approver)

    for over in (
        {"developer_party_id": foreign_dev.id},
        {"architect_party_id": foreign_arch.id},
        {"main_contractor_party_id": foreign_contractor.id},
        {"type_id": foreign_type.id},
        {"template_id": uid()},
        {"brand_ids": [uid()]},
    ):
        res = c.post(f"{CRM}/{rid}/approve", json=approve_body(world, rid, **over))
        assert res.status_code == 422, (over, res.status_code, res.text)
    assert registration(world, rid).status == "pending"


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


# ------------------------------------------------------------------ N12 drafts


def test_n12_status_all_leaves_the_contacts_unsent_drafts_out(world):
    draft = create_draft(world)["id"]
    sent = pending(world)
    ids = {r["id"] for r in as_user(world, world.approver).get(CRM, params={"status": "all"}).json()["data"]}
    assert sent in ids
    assert draft not in ids


# ------------------------------------------------------------------ round 2: ineligible applicant


def test_r2_an_ineligible_applicant_falls_back_to_the_approver_without_manage(world):
    from app.models.projects import Project
    from app.models.user import User

    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    world.db.get(User, world.applicant_user).status = "inactive"
    world.db.flush()
    res = _approve(world, rid, owner_user_id=world.applicant_user)
    assert res.status_code == 200, res.text
    world.db.expire_all()
    assert world.db.get(Project, res.json()["project_id"]).owner_user_id == world.approver


def test_r2_another_owner_keeps_its_rules_when_the_applicant_is_ineligible(world):
    from app.models.user import User

    world.perms[world.approver].discard(MANAGE)
    rid = pending(world)
    world.db.get(User, world.applicant_user).status = "inactive"
    world.db.flush()
    res = _approve(world, rid, owner_user_id=world.owner)
    assert res.status_code == 403, res.text
