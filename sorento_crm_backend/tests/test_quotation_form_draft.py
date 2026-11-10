"""QUOTE-AUTOSAVE: a proposal / quotation form's draft and its History.

Owner, 10 Nov 2026: "the quotation should be always saved ... with history just like our tag
designer". Plan: documentation/plans/project-sales/PLAN-quote-autosave-10nov.md (card + the owner's
answers Q1-Q5 of 10 Nov ~15:10 MYT).

What these pin, the ones worth the most first:

- **An autosave never reaches the record**: not its fields, not its ``updated_at``, not the
  floor-breach alert to management, not the audit log (Q1).
- **A new proposal's draft is private and unnumbered** until its first Save (Q2).
- **The older tab goes view-only** (Q4): a write from it is refused and what it carried is kept.
- **Save writes History and clears the draft** in the record's own commit; a refused Save keeps it.
- **Restore is the tag designer's** (Q3): the state being left is kept first.
- **Issue and Request approval refuse a pending draft.**
- **Discard draft** is a 5 s reversible pending action (Q5).

Postgres only, via the route suite's own ``api`` fixture (``blank_session``).
"""
from __future__ import annotations

import uuid

from app.models.audit import AuditLog
from app.models.projects import QuotationDocumentDraft, QuotationDocumentSnapshot

from .test_project_quotation_document_routes import (  # noqa: F401  (``api`` is a fixture)
    BASE,
    FIXTURE_LIST_PRICE,
    MARKER,
    _add_priced_line,
    _add_scope,
    _category,
    _create_document,
    _current_version_id,
    _document_row,
    _product,
    _sign,
    _uom,
    _user,
    api,
)


def _root(project_id: str) -> str:
    return f"{BASE}/projects/{project_id}/quotation-documents"


def _state(subject: str, *, total: str = "0", **extra) -> dict:
    """A form state in the shape ``QuotationFormClient`` holds it."""
    return {
        "v": 1,
        "header": {"subject_title": subject},
        "letter": {},
        "scopes": [],
        "staged": {},
        "removedIds": [],
        "total": total,
        **extra,
    }


def _open(client, project_id, document_id) -> dict:
    response = client.post(f"{_root(project_id)}/{document_id}/form-draft/open")
    assert response.status_code == 200, response.text
    return response.json()


def _put(client, project_id, document_id, doc, token):
    return client.put(
        f"{_root(project_id)}/{document_id}/form-draft", json={"doc": doc, "token": token}
    )


def _history(client, project_id, document_id) -> list:
    response = client.get(f"{_root(project_id)}/{document_id}/history")
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ------------------------------------------------------------------ Q1: autosave


def test_an_autosave_writes_the_draft_and_nothing_else(api, monkeypatch):
    client, db, _company, _user_id, project, _party = api
    sent = []
    from app.services import project_notify_service

    monkeypatch.setattr(
        project_notify_service, "notify_floor_breach", lambda *a, **k: sent.append(k)
    )
    document = _create_document(client, project.id, subject_title=f"{MARKER} Before")
    before = client.get(f"{_root(project.id)}/{document['id']}").json()

    opened = _open(client, project.id, document["id"])
    assert opened["doc"] is None and opened["token"]
    assert _put(client, project.id, document["id"], _state(f"{MARKER} Typed"), opened["token"]).status_code == 200
    second = _put(client, project.id, document["id"], _state(f"{MARKER} Typed more"), opened["token"])
    assert second.status_code == 200, second.text

    after = client.get(f"{_root(project.id)}/{document['id']}").json()
    assert after["subject_title"] == f"{MARKER} Before"
    assert after["updated_at"] == before["updated_at"]
    assert after["has_form_draft"] is True
    assert after["form_draft_by_name"] == f"{MARKER} Baser"

    reopened = _open(client, project.id, document["id"])
    assert reopened["doc"]["header"]["subject_title"] == f"{MARKER} Typed more"
    assert reopened["updated_by_name"] == f"{MARKER} Baser"
    assert reopened["token"] != opened["token"]

    # The tag designer's rule: an autosave writes no History, alerts nobody, audits nothing.
    assert _history(client, project.id, document["id"]) == []
    assert sent == []
    db.expire_all()
    assert (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type.in_(["quotation_document_drafts", "quotation_document_snapshots"])
        )
        .count()
        == 0
    )


# ------------------------------------------------------------------ Q4: the older tab


def test_the_older_tab_is_refused_and_its_typing_kept_as_history(api):
    client, _db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    older = _open(client, project.id, document["id"])
    newer = _open(client, project.id, document["id"])

    holder = client.get(
        f"{_root(project.id)}/{document['id']}/form-draft/holder",
        headers={"X-Form-Draft-Token": older["token"]},
    ).json()
    assert holder["is_holder"] is False
    assert holder["holder_name"] == f"{MARKER} Baser"
    assert holder["holder_at"]
    assert client.get(
        f"{_root(project.id)}/{document['id']}/form-draft/holder",
        headers={"X-Form-Draft-Token": newer["token"]},
    ).json()["is_holder"] is True

    refused = _put(
        client, project.id, document["id"], _state(f"{MARKER} Older tab", total="42.50"),
        older["token"],
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "quotation_draft_not_holder"
    assert refused.json()["details"]["holder_name"] == f"{MARKER} Baser"

    # The newer tab keeps writing; the older tab's text is History, not lost.
    assert _put(client, project.id, document["id"], _state("Newer"), newer["token"]).status_code == 200
    entries = _history(client, project.id, document["id"])
    assert [entry["kind"] for entry in entries] == ["conflict"]
    detail = client.get(f"{_root(project.id)}/{document['id']}/history/{entries[0]['id']}").json()
    assert detail["doc"]["header"]["subject_title"] == f"{MARKER} Older tab"
    assert str(detail["grand_total"]) in ("42.50", "42.5")

    # A view-only tab cannot Save over the holder either.
    save = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={"subject_title": "x", "form_state": _state("x"), "form_token": older["token"]},
    )
    assert save.status_code == 409
    assert client.get(f"{_root(project.id)}/{document['id']}").json()["subject_title"] != "x"


# ------------------------------------------------------------------ Save


def test_save_writes_a_history_entry_and_clears_the_draft(api):
    client, db, _company, _user_id, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "Basin").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    _add_priced_line(client, _current_version_id(db, scope["id"]), product, price="250.00", qty="4")
    opened = _open(client, project.id, document["id"])
    _put(client, project.id, document["id"], _state(f"{MARKER} Saved title"), opened["token"])

    saved = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={
            "subject_title": f"{MARKER} Saved title",
            "form_state": _state(f"{MARKER} Saved title"),
            "form_token": opened["token"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["subject_title"] == f"{MARKER} Saved title"
    assert saved.json()["has_form_draft"] is False

    entries = _history(client, project.id, document["id"])
    assert [(entry["kind"], entry["version"]) for entry in entries] == [("saved", 1)]
    # A Save's figure is the record's own grand total.
    assert str(entries[0]["grand_total"]) in ("1000.00", "1000.0", "1000")
    assert entries[0]["created_by_name"] == f"{MARKER} Baser"
    assert _open(client, project.id, document["id"])["doc"] is None


def test_a_refused_save_keeps_the_draft_and_writes_no_history(api):
    client, _db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    opened = _open(client, project.id, document["id"])
    _put(client, project.id, document["id"], _state(f"{MARKER} Kept"), opened["token"])

    refused = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={
            "scopes": [{"id": scope["id"], "scope_label": "x"}],
            "remove_scope_ids": [scope["id"]],
            "form_state": _state(f"{MARKER} Kept"),
            "form_token": opened["token"],
        },
    )
    assert refused.status_code == 422, refused.text
    assert _history(client, project.id, document["id"]) == []
    assert _open(client, project.id, document["id"])["doc"]["header"]["subject_title"] == f"{MARKER} Kept"


# ------------------------------------------------------------------ Q2: a new proposal


def test_a_new_proposal_draft_is_private_and_unnumbered_until_its_first_save(api):
    client, db, company_id, user_id, project, _party = api
    from app.models.projects import ProjectQuotationDocument

    before = db.query(ProjectQuotationDocument).filter_by(project_id=project.id).count()
    opened = client.post(f"{_root(project.id)}/new-draft/open").json()
    assert opened["doc"] is None
    typed = client.put(
        f"{_root(project.id)}/new-draft",
        json={"doc": _state(f"{MARKER} New one"), "token": opened["token"]},
    )
    assert typed.status_code == 200, typed.text
    db.expire_all()
    # No record, so no number used up by a draft somebody abandons.
    assert db.query(ProjectQuotationDocument).filter_by(project_id=project.id).count() == before
    assert client.post(f"{_root(project.id)}/new-draft/open").json()["doc"]["header"]["subject_title"] == f"{MARKER} New one"

    # Private: another person opening New proposal on the same project starts clean.
    row = db.query(QuotationDocumentDraft).filter_by(project_id=project.id, document_id=None).one()
    assert row.owner_user_id == str(user_id)
    other = _user(db, f"{MARKER} Other")
    db.commit()
    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "id": other, "email": f"{other}@zzt.test", "role": "superadmin",
    }
    try:
        assert client.post(f"{_root(project.id)}/new-draft/open").json()["doc"] is None
    finally:
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin",
        }


def test_the_first_save_numbers_the_proposal_and_adopts_its_draft(api):
    client, db, _company, _user_id, project, _party = api
    older = client.post(f"{_root(project.id)}/new-draft/open").json()
    newer = client.post(f"{_root(project.id)}/new-draft/open").json()
    # The older New-proposal tab loses its claim; its typing is kept for the record to come.
    lost = client.put(
        f"{_root(project.id)}/new-draft",
        json={"doc": _state(f"{MARKER} Older new tab"), "token": older["token"]},
    )
    assert lost.status_code == 409
    assert client.post(
        _root(project.id),
        json={"subject_title": "x", "form_state": _state("x"), "form_token": older["token"]},
    ).status_code == 409

    created = client.post(
        _root(project.id),
        json={
            "subject_title": f"{MARKER} First save",
            "form_state": _state(f"{MARKER} First save"),
            "form_token": newer["token"],
        },
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["document_no"].startswith(f"{MARKER}/Q/")
    assert document["has_form_draft"] is False
    kinds = [entry["kind"] for entry in _history(client, project.id, document["id"])]
    assert kinds == ["saved", "conflict"]
    # The private draft is gone: the next New proposal starts clean.
    assert client.post(f"{_root(project.id)}/new-draft/open").json()["doc"] is None


# ------------------------------------------------------------------ rule 7: issue / approval


def test_issue_and_request_approval_refuse_while_a_draft_is_unsaved(api):
    client, db, _company, user_id, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "WC").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    _add_priced_line(client, _current_version_id(db, scope["id"]), product, price="250.00", qty="4")
    _sign(client, _root(project.id), document["id"])
    opened = _open(client, project.id, document["id"])
    _put(client, project.id, document["id"], _state("pending"), opened["token"])

    issue = client.post(f"{_root(project.id)}/{document['id']}/issue")
    assert issue.status_code == 409, issue.text
    assert issue.json()["code"] == "quotation_draft_pending"
    approval = client.post(
        f"{_root(project.id)}/{document['id']}/approval-status",
        json={"to_status_id": str(uuid.uuid4())},
    )
    assert approval.status_code == 409, approval.text
    assert approval.json()["code"] == "quotation_draft_pending"

    # Discard (the pending action's handler) lifts it: the issue goes through.
    from app.services.record_actions import _discard_form_draft

    _discard_form_draft(
        db, {"entity_id": opened["draft_id"], "requested_by_id": user_id, "token": opened["token"]}
    )
    db.commit()
    assert client.post(f"{_root(project.id)}/{document['id']}/issue").status_code == 201


# ------------------------------------------------------------------ Q5: Discard draft


def test_discard_is_a_five_second_reversible_record_action(api):
    from app.services.form_action_grace import WINDOW_REVERSIBLE
    from app.services.form_action_registry import get_action

    action = get_action("quotation_form_draft.discard")
    assert action is not None
    assert action.window == WINDOW_REVERSIBLE
    assert action.entity_types == ("quotation_form_draft",)
    assert action.permission == "projects.projects.edit"


def test_discard_clears_the_draft_and_writes_no_history(api):
    client, db, _company, user_id, project, _party = api
    from app.services.record_actions import _discard_form_draft

    document = _create_document(client, project.id)
    opened = _open(client, project.id, document["id"])
    _put(client, project.id, document["id"], _state("thrown"), opened["token"])
    _discard_form_draft(
        db, {"entity_id": opened["draft_id"], "requested_by_id": user_id, "token": opened["token"]}
    )
    db.commit()
    assert _open(client, project.id, document["id"])["doc"] is None
    assert _history(client, project.id, document["id"]) == []


def test_a_discard_from_a_tab_that_lost_the_draft_keeps_the_newer_tabs_work(api):
    client, db, _company, user_id, project, _party = api
    import pytest

    from app.services.record_actions import _discard_form_draft

    document = _create_document(client, project.id)
    older = _open(client, project.id, document["id"])
    newer = _open(client, project.id, document["id"])
    _put(client, project.id, document["id"], _state(f"{MARKER} Newer tab"), newer["token"])
    with pytest.raises(Exception) as refused:
        _discard_form_draft(
            db, {"entity_id": older["draft_id"], "requested_by_id": user_id, "token": older["token"]}
        )
    assert getattr(refused.value, "status_code", None) == 409
    db.rollback()
    assert _open(client, project.id, document["id"])["doc"]["header"]["subject_title"] == f"{MARKER} Newer tab"


def test_someone_else_cannot_discard_my_private_new_draft(api):
    client, db, _company, user_id, project, _party = api
    import pytest

    from app.services.record_actions import assert_form_draft_discardable

    opened = client.post(f"{_root(project.id)}/new-draft/open").json()
    other = _user(db, f"{MARKER} Other")
    db.commit()
    with pytest.raises(Exception) as refused:
        assert_form_draft_discardable(db, opened["draft_id"], other)
    assert getattr(refused.value, "status_code", None) == 404
    assert assert_form_draft_discardable(db, opened["draft_id"], user_id).id == opened["draft_id"]


# ------------------------------------------------------------------ rule 6: locked


def test_an_approval_locked_document_refuses_its_draft(api):
    client, db, _company, _user_id, project, _party = api
    from app.services import project_quotation_approval_service as approvals

    document = _create_document(client, project.id)
    opened = _open(client, project.id, document["id"])
    row = _document_row(db, document["id"])
    row.approval_status_id = approvals._status_by_key(db, approvals.STATUS_PENDING).id
    db.commit()

    locked = _put(client, project.id, document["id"], _state("x"), opened["token"])
    assert locked.status_code == 422, locked.text
    assert locked.json()["code"] == "quotation_locked_for_approval"


# ------------------------------------------------------------------ Q3: History / Restore


def test_restore_keeps_the_state_being_left_then_loads_the_entry(api):
    client, _db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    opened = _open(client, project.id, document["id"])
    client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={"form_state": _state(f"{MARKER} Monday", total="100.00"), "form_token": opened["token"]},
    )
    monday = _history(client, project.id, document["id"])[0]
    _put(client, project.id, document["id"], _state(f"{MARKER} Tuesday"), opened["token"])

    newer = _open(client, project.id, document["id"])
    refused = client.post(
        f"{_root(project.id)}/{document['id']}/history/{monday['id']}/restore",
        json={"token": opened["token"]},
    )
    assert refused.status_code == 409  # the older tab is view-only

    restored = client.post(
        f"{_root(project.id)}/{document['id']}/history/{monday['id']}/restore",
        json={"token": newer["token"]},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["doc"]["header"]["subject_title"] == f"{MARKER} Monday"

    entries = _history(client, project.id, document["id"])
    assert [(e["kind"], e["version"], e["note"]) for e in entries] == [
        ("before_restore", 2, "Before restore to version 1"),
        ("saved", 1, None),
    ]
    before = client.get(f"{_root(project.id)}/{document['id']}/history/{entries[0]['id']}").json()
    assert before["doc"]["header"]["subject_title"] == f"{MARKER} Tuesday"


def test_restore_with_no_draft_keeps_the_latest_save_like_the_tag_designer(api):
    client, _db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    token = _open(client, project.id, document["id"])["token"]
    for subject in ("One", "Two"):
        client.patch(
            f"{_root(project.id)}/{document['id']}",
            json={"form_state": _state(subject), "form_token": token},
        )
    first = _history(client, project.id, document["id"])[-1]
    client.post(
        f"{_root(project.id)}/{document['id']}/history/{first['id']}/restore",
        json={"token": token},
    )
    top = _history(client, project.id, document["id"])[0]
    assert top["kind"] == "before_restore"
    detail = client.get(f"{_root(project.id)}/{document['id']}/history/{top['id']}").json()
    assert detail["doc"]["header"]["subject_title"] == "Two"


def test_a_history_entry_is_not_readable_through_another_document(api):
    client, _db, _company, _user_id, project, _party = api
    mine = _create_document(client, project.id)
    other = _create_document(client, project.id)
    client.patch(f"{_root(project.id)}/{mine['id']}", json={"form_state": _state("mine")})
    entry = _history(client, project.id, mine["id"])[0]
    assert client.get(f"{_root(project.id)}/{other['id']}/history/{entry['id']}").status_code == 404
    token = _open(client, project.id, other["id"])["token"]
    restore = client.post(
        f"{_root(project.id)}/{other['id']}/history/{entry['id']}/restore", json={"token": token}
    )
    assert restore.status_code == 404


def test_a_restored_entry_is_reconciled_against_the_record_as_it_is_now(api):
    """Without this a restored entry could never be saved: the form sends a saved scope's lines by
    id, and an id the current version no longer holds is a 404 on Save."""
    client, db, _company, _user_id, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "Tap").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    kept = _add_scope(client, project.id, document["id"], f"{MARKER} Kept")
    gone = _add_scope(client, project.id, document["id"], f"{MARKER} Gone")
    version_id = _current_version_id(db, kept["id"])
    line = _add_priced_line(client, version_id, product, price="250.00", qty="4")

    entry_state = _state(
        f"{MARKER} Old",
        scopes=[
            {"key": kept["id"], "id": kept["id"], "scope_label": "Kept", "series_id": ""},
            {"key": gone["id"], "id": gone["id"], "scope_label": "Gone", "series_id": ""},
        ],
        staged={
            kept["id"]: {
                "versionId": str(uuid.uuid4()),
                "seeded": [{"id": line["id"]}],
                "lines": [
                    {"key": "a", "id": line["id"], "line": {"id": line["id"]}, "draft": {}, "removed": False},
                    {"key": "b", "id": str(uuid.uuid4()), "line": {"x": 1}, "draft": {}, "removed": False},
                ],
            },
            gone["id"]: {
                "versionId": str(uuid.uuid4()),
                "seeded": [],
                "lines": [{"key": "c", "id": str(uuid.uuid4()), "line": {}, "draft": {}, "removed": False}],
            },
        },
        removedIds=[gone["id"]],
    )
    removed = client.patch(
        f"{_root(project.id)}/{document['id']}", json={"remove_scope_ids": [gone["id"]]}
    )
    assert removed.status_code == 200, removed.text

    # A draft or a "Before restore" entry made before the removal, opened today.
    from app.services import quotation_form_draft_service as drafts

    doc = drafts.reconcile(db, _document_row(db, document["id"]), entry_state)

    by_label = {scope["scope_label"]: scope for scope in doc["scopes"]}
    assert by_label["Kept"]["id"] == kept["id"]
    assert by_label["Gone"]["id"] is None
    kept_staged = doc["staged"][kept["id"]]
    assert kept_staged["versionId"] == version_id
    assert kept_staged["seeded"] == []
    assert [l["id"] for l in kept_staged["lines"]] == [line["id"], None]
    assert kept_staged["lines"][1]["line"] is None
    assert [l["id"] for l in doc["staged"][gone["id"]]["lines"]] == [None]
    assert doc["removedIds"] == []


def test_draft_rows_cascade_with_their_document(api):
    client, db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    token = _open(client, project.id, document["id"])["token"]
    _put(client, project.id, document["id"], _state("x"), token)
    client.patch(f"{_root(project.id)}/{document['id']}", json={"form_state": _state("x"), "form_token": token})
    assert client.delete(f"{_root(project.id)}/{document['id']}").status_code == 204
    db.expire_all()
    assert db.query(QuotationDocumentDraft).filter_by(document_id=document["id"]).count() == 0
    assert db.query(QuotationDocumentSnapshot).filter_by(document_id=document["id"]).count() == 0


# ------------------------------------------------------------------ review fix round


def test_a_lost_tab_keeps_one_history_entry_however_often_it_writes(api):
    """Security review 1: a stale tab writing every second must not grow History without bound."""
    client, _db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    older = _open(client, project.id, document["id"])
    _open(client, project.id, document["id"])
    for n in range(5):
        _put(client, project.id, document["id"], _state(f"{MARKER} burst {n}"), older["token"])
    entries = _history(client, project.id, document["id"])
    assert [entry["kind"] for entry in entries] == ["conflict"]
    detail = client.get(f"{_root(project.id)}/{document['id']}/history/{entries[0]['id']}").json()
    assert detail["doc"]["header"]["subject_title"] == f"{MARKER} burst 4"


def test_a_refused_save_from_a_lost_tab_is_kept_as_history(api):
    """Review 8: a view-only tab that presses Save loses nothing either."""
    client, _db, _company, _user_id, project, _party = api
    document = _create_document(client, project.id)
    older = _open(client, project.id, document["id"])
    _open(client, project.id, document["id"])
    refused = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={"form_state": _state(f"{MARKER} Pressed Save"), "form_token": older["token"]},
    )
    assert refused.status_code == 409
    entries = _history(client, project.id, document["id"])
    assert [entry["kind"] for entry in entries] == ["conflict"]


def test_restoring_an_entry_whose_line_a_later_save_deleted_can_still_be_saved(api):
    """Review B1: same version, line deleted by a later Save. Restore must not keep its stale id,
    or every Save of the restored draft is a 404 and Issue stays blocked."""
    client, db, _company, _user_id, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "Mixer").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    version_id = _current_version_id(db, scope["id"])
    keep = _add_priced_line(client, version_id, product, price="250.00", qty="4")
    drop = _add_priced_line(client, version_id, product, price="300.00", qty="2")
    token = _open(client, project.id, document["id"])["token"]

    client.patch(f"{_root(project.id)}/{document['id']}", json={"form_state": _state("v1"), "form_token": token})
    v1 = _history(client, project.id, document["id"])[0]
    # Version 2 deletes `drop` on the SAME version (nothing issued).
    line_body = {"product_id": product.id, "unit_price": "250.00", "quantity": "4"}
    saved = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={
            "scopes": [{"id": scope["id"], "lines": [{"id": keep["id"], **line_body}]}],
            "form_state": _state("v2"),
            "form_token": token,
        },
    )
    assert saved.status_code == 200, saved.text
    assert _current_version_id(db, scope["id"]) == version_id

    doc = client.post(
        f"{_root(project.id)}/{document['id']}/history/{v1['id']}/restore", json={"token": token}
    ).json()["doc"]
    restored = doc["record_lines"][scope["id"]]
    assert [line["id"] for line in restored["lines"]] == [keep["id"], None]
    assert restored["versionId"] == version_id


def test_a_history_entry_holds_every_scope_so_restore_brings_back_untouched_lines(api):
    """Review B2: a Save that changed only the Subject still records every scope's lines, so
    restoring it later brings back THOSE lines, not today's."""
    client, db, _company, _user_id, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "Shower").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Guard House")
    version_id = _current_version_id(db, scope["id"])
    line = _add_priced_line(client, version_id, product, price="100.00", qty="1")
    token = _open(client, project.id, document["id"])["token"]

    # Version 1 touches only the Subject: the form sends no staged lines for the scope.
    client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={"subject_title": "Subject only", "form_state": _state("Subject only"), "form_token": token},
    )
    v1 = _history(client, project.id, document["id"])[0]
    detail = client.get(f"{_root(project.id)}/{document['id']}/history/{v1['id']}").json()
    stored = detail["doc"]["record_lines"][scope["id"]]
    assert [l["unit_price"] for l in stored["lines"]] in (["100.00"], ["100.0"], ["100"])
    assert detail["doc"]["scopes"] == [
        {"key": scope["id"], "id": scope["id"], "scope_label": f"{MARKER} Guard House", "series_id": "", "notes": None}
    ]

    # Later the price becomes 200; restoring version 1 brings 100 back into the draft.
    client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={
            "scopes": [{"id": scope["id"], "lines": [{"id": line["id"], "product_id": product.id, "unit_price": "200.00", "quantity": "1"}]}],
            "form_state": _state("Price 200"),
            "form_token": token,
        },
    )
    doc = client.post(
        f"{_root(project.id)}/{document['id']}/history/{v1['id']}/restore", json={"token": token}
    ).json()["doc"]
    back = doc["record_lines"][scope["id"]]["lines"]
    assert back[0]["id"] == line["id"]
    assert str(back[0]["unit_price"]).startswith("100")
