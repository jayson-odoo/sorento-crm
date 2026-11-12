"""PROJECT-NAME (10 Nov): a short project NAME beside the long legal title.

Card: documentation/plans/projects/CARD-project-name-10nov.md (owner answers Q1 a, Q2 a, Q3 a,
Q4 a, Q5 b). Bound here:

- `projects.name` and `leads.name`: optional, at most 80 characters, whitespace collapsed, blank
  stored as null, never unique and never part of the registration lock (Q3, Q4).
- Staff register, edit, salesperson draft, portal registration and approve all carry it (Q5).
- A lead's name is carried onto the project it qualifies into, unless the confirm step sends one.
- The AI extract proposes it from the same schema (no new extractor).
- Search matches the name; notifications show the name, the title when there is none (Q1).

Every name is invented.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    AI_EXTRACT,
    LIST,
    as_user,
    developer,
    register_body,
    save_draft,
    title,
    v2,
)
from ._project_registration_support import STAFF, world  # noqa: F401  (fixture)

NAME = "Residensi Contoh Phase 2"
LEADS = "/api/v1/project-sales/leads"


def _register(w, **over):
    return as_user(w, w.owner).post(LIST, json=register_body(w, **over))


def _stored(w, project_id: str):
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.get(Project, project_id)


# ------------------------------------------------------------------ staff register / edit


def test_register_stores_the_name_with_whitespace_collapsed(v2):
    res = _register(v2, name=f"  Residensi   Contoh\tPhase 2  ")
    assert res.status_code == 201, res.text
    assert res.json()["name"] == NAME
    assert _stored(v2, res.json()["id"]).name == NAME


def test_register_without_a_name_leaves_it_null(v2):
    res = _register(v2)
    assert res.status_code == 201, res.text
    assert res.json()["name"] is None


def test_a_blank_name_is_stored_as_null(v2):
    res = _register(v2, name="   ")
    assert res.status_code == 201, res.text
    assert _stored(v2, res.json()["id"]).name is None


def test_a_name_over_80_characters_is_refused(v2):
    res = _register(v2, name="N" * 81)
    assert res.status_code == 422, res.text


def test_an_80_character_name_is_accepted(v2):
    res = _register(v2, name="N" * 80)
    assert res.status_code == 201, res.text


def test_the_name_is_not_unique_and_not_part_of_the_lock(v2):
    """Q4 (a): two projects of one developer may share a name; only the title locks."""
    dev = developer(v2.db, v2.company_id, f"CONTOH Dev {uuid.uuid4().hex[:6]}")
    first = _register(v2, name=NAME, developer_party_id=dev.id)
    second = _register(v2, name=NAME, developer_party_id=dev.id)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text


def test_edit_sets_renames_and_clears_the_name_without_touching_the_title(v2):
    created = _register(v2).json()
    url = f"{STAFF}/{created['id']}"
    before = _stored(v2, created["id"])
    old_title, old_norm = before.title, before.normalised_title

    set_ = as_user(v2, v2.owner).put(url, json={"name": NAME})
    assert set_.status_code == 200, set_.text
    assert set_.json()["name"] == NAME
    after = _stored(v2, created["id"])
    assert (after.title, after.normalised_title) == (old_title, old_norm)

    cleared = as_user(v2, v2.owner).put(url, json={"name": ""})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["name"] is None


def test_an_edit_that_does_not_send_the_name_keeps_it(v2):
    created = _register(v2, name=NAME).json()
    res = as_user(v2, v2.owner).put(f"{STAFF}/{created['id']}", json={"location": "Kuantan"})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == NAME


def test_edit_refuses_a_name_over_80(v2):
    created = _register(v2).json()
    res = as_user(v2, v2.owner).put(f"{STAFF}/{created['id']}", json={"name": "N" * 81})
    assert res.status_code == 422, res.text


def test_the_projects_list_searches_the_name(v2):
    marker = uuid.uuid4().hex[:10]
    created = _register(v2, name=f"Taman {marker}").json()
    res = as_user(v2, v2.owner).get(LIST, params={"search": marker})
    assert res.status_code == 200, res.text
    assert [row["id"] for row in res.json()["data"]] == [created["id"]]
    assert res.json()["data"][0]["name"] == f"Taman {marker}"


def test_the_projects_list_still_searches_the_title(v2):
    text = title("Searchable")
    created = _register(v2, title=text).json()
    res = as_user(v2, v2.owner).get(LIST, params={"search": text.split()[-1]})
    assert [row["id"] for row in res.json()["data"]] == [created["id"]]


# ------------------------------------------------------------------ salesperson draft / approve


def test_a_salesperson_draft_keeps_the_name(v2):
    res = save_draft(v2, v2.sub_a, name=NAME)
    assert res.status_code == 201, res.text
    assert _stored(v2, res.json()["id"]).name == NAME


def test_approve_keeps_the_name_and_may_set_it(v2):
    from ._project_register_v2_support import approve_as_manager

    draft = save_draft(v2, v2.sub_a, name="Draft name").json()
    as_user(v2, v2.sub_a).post(f"{STAFF}/{draft['id']}/submit", json={})
    res = approve_as_manager(v2, draft["id"], name=NAME)
    assert res.status_code == 200, res.text
    assert res.json()["name"] == NAME


# ------------------------------------------------------------------ AI extract


def test_the_registration_extract_schema_asks_for_the_name():
    from app.services.ai_extract.form_schema_registry import get_form_schema

    fields = {f.name: f for f in get_form_schema("portal.project_registration")}
    assert "name" in fields
    assert fields["name"].label == "Project name"
    assert fields["name"].note  # the instruction that keeps lot numbers out


def test_ai_extract_proposes_the_name(v2, monkeypatch):
    from app.services.ai_extract.extract_service import AIExtractService, ExtractResult

    monkeypatch.setattr(
        AIExtractService,
        "extract",
        lambda self, form_key, files, **k: ExtractResult(values={"name": f" {NAME} ", "title": "T"}),
    )
    res = as_user(v2, v2.owner).post(AI_EXTRACT, data={"text": "CADANGAN MEMBINA ..."})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("proposals", body)["name"] == NAME


def test_ai_extract_proposes_no_name_when_none_was_read(v2, monkeypatch):
    from app.services.ai_extract.extract_service import AIExtractService, ExtractResult

    monkeypatch.setattr(
        AIExtractService, "extract", lambda self, form_key, files, **k: ExtractResult(values={})
    )
    res = as_user(v2, v2.owner).post(AI_EXTRACT, data={"text": "CADANGAN MEMBINA ..."})
    body = res.json()
    assert body.get("proposals", body)["name"] is None


def test_ai_extract_caps_a_long_proposed_name_at_80(v2, monkeypatch):
    from app.services.ai_extract.extract_service import AIExtractService, ExtractResult

    monkeypatch.setattr(
        AIExtractService,
        "extract",
        lambda self, form_key, files, **k: ExtractResult(values={"name": "X" * 120}),
    )
    res = as_user(v2, v2.owner).post(AI_EXTRACT, data={"text": "CADANGAN"})
    body = res.json()
    assert len(body.get("proposals", body)["name"]) <= 80


# ------------------------------------------------------------------ display + notifications


def test_display_name_prefers_the_name_and_falls_back_to_the_title():
    from app.services.project_service import project_display_name

    assert project_display_name(SimpleNamespace(name=NAME, title="LONG TITLE")) == NAME
    assert project_display_name(SimpleNamespace(name=None, title="LONG TITLE")) == "LONG TITLE"
    assert project_display_name(SimpleNamespace(name="  ", title="LONG TITLE")) == "LONG TITLE"


def test_the_reassigned_notification_names_the_project(monkeypatch):
    from app.services import project_notify_service as notify

    sent = {}
    monkeypatch.setattr(notify, "_send", lambda db, **kw: sent.update(kw) or 1)
    project = SimpleNamespace(
        id="p1", project_code="PPF2611003", name=NAME, title="CADANGAN MEMBINA ...",
        approval_state=None, company_id="c1",
    )
    notify.notify_reassigned(
        None, project=project, request=SimpleNamespace(id="r1"), previous_owner_id=None,
        new_owner_id="u1",
    )
    assert NAME in sent["body"]
    assert "CADANGAN" not in sent["body"]


# ------------------------------------------------------------------ leads (Q5 b)


def _lead(w, **over):
    body = {"title": title("Lead"), "customer_id": w.customer.id}
    body.update(over)
    return as_user(w, w.owner).post(LEADS, json=body)


def test_a_lead_stores_and_edits_its_name(v2):
    created = _lead(v2, name=f"  {NAME} ")
    assert created.status_code == 201, created.text
    assert created.json()["name"] == NAME

    edited = as_user(v2, v2.owner).put(f"{LEADS}/{created.json()['id']}", json={"name": ""})
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] is None


def test_a_lead_name_over_80_is_refused(v2):
    assert _lead(v2, name="N" * 81).status_code == 422


def test_the_lead_list_searches_the_name(v2):
    marker = uuid.uuid4().hex[:10]
    created = _lead(v2, name=f"Taman {marker}").json()
    res = as_user(v2, v2.owner).get(LEADS, params={"query": marker})
    assert res.status_code == 200, res.text
    assert [row["id"] for row in res.json()["data"]] == [created["id"]]


def test_qualify_carries_the_lead_name_onto_the_project(v2):
    lead = _lead(v2, name=NAME).json()
    res = as_user(v2, v2.owner).post(f"{LEADS}/{lead['id']}/qualify", json={})
    assert res.status_code == 201, res.text
    assert res.json()["name"] == NAME


def test_a_name_sent_on_qualify_wins_over_the_lead_name(v2):
    lead = _lead(v2, name=NAME).json()
    res = as_user(v2, v2.owner).post(
        f"{LEADS}/{lead['id']}/qualify", json={"name": "Phase 3B"}
    )
    assert res.status_code == 201, res.text
    assert res.json()["name"] == "Phase 3B"


# ------------------------------------------------------------------ dealer portal (Q5 b)


def test_the_portal_draft_stores_and_returns_the_name(world):
    from ._project_registration_support import create_draft, field_values, registration

    draft = create_draft(world, name=f" {NAME} ")
    assert registration(world, draft["id"]).name == NAME
    assert field_values(draft)["name"] == NAME


def test_the_portal_refuses_a_name_over_80(world):
    from ._project_registration_support import SUB, as_contact, fields

    body = fields(world.debtor_a.id, name="N" * 81)
    res = as_contact(world, world.a).post(SUB, json={"fields": body})
    assert res.status_code == 422, res.text


# ------------------------------------------------------------------ backfill (Q2 a)


def _backfill():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_project_names.py"
    spec = importlib.util.spec_from_file_location("backfill_project_names", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_backfill_dry_run_proposes_and_writes_nothing(v2, monkeypatch):
    backfill = _backfill()
    created = _register(v2).json()
    named = _register(v2, name="Already named").json()
    monkeypatch.setattr(v2.db, "rollback", lambda: None)  # the fixture's session must survive

    rows = backfill.dry_run(v2.db, lambda title: "Proposed Name")

    by_id = {pid: (code, name) for pid, code, _title, name in rows}
    assert by_id[created["id"]] == (created["project_code"], "Proposed Name")
    assert named["id"] not in by_id
    assert _stored(v2, created["id"]).name is None


def _apply(v2, monkeypatch, rows):
    monkeypatch.setattr(v2.db, "commit", v2.db.flush)
    return _backfill().apply(v2.db, rows)


def test_the_backfill_apply_writes_only_reviewed_unnamed_rows(v2, monkeypatch):
    unnamed = _register(v2).json()
    refused = _register(v2).json()
    named = _register(v2, name="Keep me").json()

    result = _apply(v2, monkeypatch, [
        {"project_id": unnamed["id"], "proposed_name": " Taman  Contoh "},
        {"project_id": refused["id"], "proposed_name": ""},
        {"project_id": named["id"], "proposed_name": "Overwrite"},
        {"project_id": "not-an-id", "proposed_name": "Nowhere"},
    ])

    assert result == {"written": 1, "skipped": 3}
    assert _stored(v2, unnamed["id"]).name == "Taman Contoh"
    assert _stored(v2, refused["id"]).name is None
    assert _stored(v2, named["id"]).name == "Keep me"


def test_the_backfill_apply_writes_by_id_when_two_companies_share_a_code(v2, monkeypatch):
    """Security review: a code is unique per company only, and the script runs across all."""
    from ._project_registration_support import project as seed_project

    ours = _register(v2).json()
    theirs = seed_project(v2.db, v2.other_company, title("Theirs"), code=ours["project_code"])

    _apply(v2, monkeypatch, [{"project_id": ours["id"], "proposed_name": "Ours"}])

    assert _stored(v2, ours["id"]).name == "Ours"
    assert _stored(v2, theirs.id).name is None


def test_the_backfill_csv_never_starts_a_cell_with_a_formula(tmp_path):
    backfill = _backfill()
    assert backfill._safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert backfill._safe_cell("Taman Contoh") == "Taman Contoh"
    assert backfill._unsafe_cell("'=HYPERLINK(1)") == "=HYPERLINK(1)"
    assert backfill._unsafe_cell("Taman Contoh") == "Taman Contoh"


def test_a_nul_byte_in_the_name_is_dropped_not_a_500(v2):
    res = _register(v2, name="Taman\x00 Contoh")
    assert res.status_code == 201, res.text
    assert res.json()["name"] == "Taman Contoh"


def test_the_portal_refuses_a_non_text_name(world):
    from ._project_registration_support import SUB, as_contact, fields

    for bad in (42, ["x"]):
        body = dict(fields(world.debtor_a.id), name=bad)
        res = as_contact(world, world.a).post(SUB, json={"fields": body})
        assert res.status_code == 422, res.text


def test_a_submit_only_clash_preview_keeps_d8s_four_keys_without_the_name(v2):
    dev = developer(v2.db, v2.company_id, f"CONTOH Dev {uuid.uuid4().hex[:6]}")
    text = title("Redacted")
    _register(v2, title=text, developer_party_id=dev.id, name=NAME)
    res = as_user(v2, v2.sub_a).post(
        f"{STAFF}/clash-preview", json={"title": text, "developer_party_id": dev.id}
    )
    assert res.status_code == 200, res.text
    candidates = res.json()["candidates"]
    assert candidates
    for candidate in candidates:
        # D8 (owner): a submit-only salesperson learns code and title only; unchanged here.
        assert set(candidate) == {"project_id", "project_code", "title", "blocks"}


def test_the_clash_preview_names_the_candidate(v2):
    dev = developer(v2.db, v2.company_id, f"CONTOH Dev {uuid.uuid4().hex[:6]}")
    text = title("Clash")
    _register(v2, title=text, developer_party_id=dev.id, name=NAME)
    res = as_user(v2, v2.owner).post(
        f"{STAFF}/clash-preview", json={"title": text, "developer_party_id": dev.id}
    )
    assert res.status_code == 200, res.text
    assert NAME in [c.get("name") for c in res.json()["candidates"]]


def test_qualify_refuses_a_long_name_in_details_with_422_not_500(v2):
    """Reviewer: `details` is a free dict, so the length check must sit in the service."""
    lead = _lead(v2).json()
    res = as_user(v2, v2.owner).post(
        f"{LEADS}/{lead['id']}/qualify", json={"details": {"name": "N" * 81}}
    )
    assert res.status_code == 422, res.text


def test_the_portal_collapses_whitespace_inside_the_name(world):
    from ._project_registration_support import create_draft, registration

    draft = create_draft(world, name="Residensi  \t Contoh   Phase 2")
    assert registration(world, draft["id"]).name == NAME


# ------------------------------------------------------------------ lead notifications (crew pass)


def _lead_row(**over):
    base = dict(
        id="l1", lead_code="LEAD-000001", name=NAME, title="CADANGAN MEMBINA BLOK A",
        developer_party_id=None, location=None, estimated_value=None, owner_user_id="u1",
        assigned_at=None, declined_at=None, declined_reason="Too far",
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def lead_sent(monkeypatch):
    from app.services import project_lead_service as leads

    sent = {}
    monkeypatch.setattr(leads, "_notify_users", lambda db, **kw: sent.update(kw) or 1)
    monkeypatch.setattr(leads, "_party_name", lambda db, pid: None)
    monkeypatch.setattr(leads, "_user_label", lambda db, uid: "Sales A")
    monkeypatch.setattr(leads, "_decline_recipients", lambda db, lead: ["u2"])
    return leads, sent


@pytest.mark.parametrize("which", ["assigned", "declined"])
def test_a_lead_notification_names_the_lead(lead_sent, which):
    leads, sent = lead_sent
    getattr(leads, f"notify_lead_{which}")(None, lead=_lead_row())
    assert sent["body"].startswith(NAME)
    assert "CADANGAN" not in sent["body"]


@pytest.mark.parametrize("which", ["assigned", "declined"])
def test_a_lead_notification_falls_back_to_the_title(lead_sent, which):
    leads, sent = lead_sent
    getattr(leads, f"notify_lead_{which}")(None, lead=_lead_row(name=None))
    assert sent["body"].startswith("CADANGAN MEMBINA BLOK A")
