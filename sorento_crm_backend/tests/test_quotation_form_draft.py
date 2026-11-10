"""QUOTE-AUTOSAVE: a proposal / quotation form's draft and its History.

Owner, 10 Nov 2026: "the quotation should be always saved ... with history just like our tag
designer". Plan: documentation/plans/project-sales/PLAN-quote-autosave-10nov.md (card rules 1-7).

What these pin, the ones worth the most first:

- **An autosave never reaches the record.** Not its lines, not its ``updated_at``, not the
  floor-breach alert to management, not the audit log. That is the whole reason the draft is a
  separate write: today's PATCH alerts management per line, so autosaving through it would page a
  manager for every price typed on the way to the real one.
- **A stale tab cannot overwrite a newer draft**, and its refused typing is kept as History, so
  "two tabs" never loses either person's work.
- **Save writes History and clears the draft in the record's own commit**; a Save the server
  refuses keeps the draft.
- **Issue and Request approval refuse while a draft is unsaved**, so nobody sends a revision that
  misses edits sitting in a draft.
- **Restore never destroys**: the draft it replaces is kept as History, and a restored entry is
  reconciled so it can still be saved after the record moved on.

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
    _product,
    _sign,
    _uom,
    api,
)


def _root(project_id: str) -> str:
    return f"{BASE}/projects/{project_id}/quotation-documents"


def _state(subject: str, *, total: str = "0", **extra) -> dict:
    """A form state in the shape ``QuotationFormClient`` holds it. The server keeps it as given and
    reads only ``total`` and the scope / staged keys it reconciles."""
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


def _put_draft(client, project_id, document_id, doc, base_rev):
    return client.put(
        f"{_root(project_id)}/{document_id}/form-draft", json={"doc": doc, "base_rev": base_rev}
    )


def _history(client, project_id, document_id) -> list:
    response = client.get(f"{_root(project_id)}/{document_id}/history")
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ------------------------------------------------------------------ rule 1: autosave


def test_an_autosave_writes_the_draft_and_nothing_else(api, monkeypatch):
    client, db, _company, user_id, project, _party = api
    sent = []
    from app.services import project_notify_service

    monkeypatch.setattr(
        project_notify_service, "notify_floor_breach", lambda *a, **k: sent.append(k)
    )
    document = _create_document(client, project.id, subject_title=f"{MARKER} Before")
    before = client.get(f"{_root(project.id)}/{document['id']}").json()

    first = _put_draft(client, project.id, document["id"], _state(f"{MARKER} Typed"), 0)
    assert first.status_code == 200, first.text
    assert first.json()["rev"] == 1
    second = _put_draft(client, project.id, document["id"], _state(f"{MARKER} Typed more"), 1)
    assert second.json()["rev"] == 2

    after = client.get(f"{_root(project.id)}/{document['id']}").json()
    # The record is exactly as it was: its subject, and its updated_at.
    assert after["subject_title"] == f"{MARKER} Before"
    assert after["updated_at"] == before["updated_at"]
    # ...and the read page knows a draft is waiting, and whose.
    assert after["has_form_draft"] is True
    assert after["form_draft_by_name"] == f"{MARKER} Baser"
    assert after["form_draft_at"] is not None

    draft = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()
    assert draft["doc"]["header"]["subject_title"] == f"{MARKER} Typed more"
    assert draft["rev"] == 2
    assert draft["updated_by_name"] == f"{MARKER} Baser"

    # No History for an autosave (the designer's rule), no alert, no audit row per keystroke.
    assert _history(client, project.id, document["id"]) == []
    assert sent == []
    db.expire_all()
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_type.in_(["quotation_document_drafts", "quotation_document_snapshots"]))
        .count()
        == 0
    )


def test_no_draft_reads_as_none_and_rev_zero(api):
    client, _db, _company, _user, project, _party = api
    document = _create_document(client, project.id)
    draft = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()
    assert draft == {"doc": None, "rev": 0, "updated_at": None, "updated_by_name": None}
    assert client.get(f"{_root(project.id)}/{document['id']}").json()["has_form_draft"] is False


# ------------------------------------------------------------------ card Q4: two tabs


def test_a_stale_tab_is_refused_and_its_typing_kept_as_history(api):
    client, db, _company, _user, project, _party = api
    document = _create_document(client, project.id)
    assert _put_draft(client, project.id, document["id"], _state(f"{MARKER} Tab A"), 0).status_code == 200

    # Tab B opened before tab A's write, so it still holds rev 0.
    stale = _put_draft(
        client, project.id, document["id"], _state(f"{MARKER} Tab B", total="42.50"), 0
    )
    assert stale.status_code == 409, stale.text
    body = stale.json()
    assert body["code"] == "quotation_draft_stale"
    assert body["details"]["rev"] == 1
    assert body["details"]["updated_by_name"] == f"{MARKER} Baser"

    # Tab A's draft stands...
    draft = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()
    assert draft["doc"]["header"]["subject_title"] == f"{MARKER} Tab A"
    # ...and tab B's typing is not lost: it is a History entry with its own total.
    entries = _history(client, project.id, document["id"])
    assert [entry["kind"] for entry in entries] == ["conflict"]
    assert entries[0]["grand_total"] in ("42.50", 42.5)
    detail = client.get(f"{_root(project.id)}/{document['id']}/history/{entries[0]['id']}").json()
    assert detail["doc"]["header"]["subject_title"] == f"{MARKER} Tab B"


# ------------------------------------------------------------------ rule 4: Save


def test_save_writes_a_history_entry_and_clears_the_draft(api):
    client, db, _company, _user, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "Basin").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    _add_priced_line(client, _current_version_id(db, scope["id"]), product, price="250.00", qty="4")
    _put_draft(client, project.id, document["id"], _state(f"{MARKER} Saved title"), 0)

    saved = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={
            "subject_title": f"{MARKER} Saved title",
            "form_state": _state(f"{MARKER} Saved title"),
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["subject_title"] == f"{MARKER} Saved title"
    assert saved.json()["has_form_draft"] is False

    entries = _history(client, project.id, document["id"])
    assert [entry["kind"] for entry in entries] == ["saved"]
    # A Save's figure is the record's own grand total, not the form's display figure.
    assert str(entries[0]["grand_total"]) in ("1000.00", "1000.0", "1000")
    assert entries[0]["created_by_name"] == f"{MARKER} Baser"
    # The draft row is kept with its counter moved on, so a tab still on rev 1 is stale.
    draft = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()
    assert draft["doc"] is None and draft["rev"] == 2
    assert _put_draft(client, project.id, document["id"], _state("late"), 1).status_code == 409


def test_a_refused_save_keeps_the_draft_and_writes_no_history(api):
    client, _db, _company, _user, project, _party = api
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    _put_draft(client, project.id, document["id"], _state(f"{MARKER} Kept"), 0)

    refused = client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={
            "scopes": [{"id": scope["id"], "scope_label": "x"}],
            "remove_scope_ids": [scope["id"]],
            "form_state": _state(f"{MARKER} Kept"),
        },
    )
    assert refused.status_code == 422, refused.text
    draft = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()
    assert draft["doc"]["header"]["subject_title"] == f"{MARKER} Kept"
    # Only the conflict entries a stale write makes, never a "saved" one for a refused Save.
    assert _history(client, project.id, document["id"]) == []


# ------------------------------------------------------------------ card Q2: new proposal


def test_a_first_edit_creates_the_record_and_its_draft_together(api):
    client, _db, _company, _user, project, _party = api
    created = _create_document(
        client,
        project.id,
        subject_title=f"{MARKER} First edit",
        form_draft=_state(f"{MARKER} First edit"),
    )
    assert created["document_no"].startswith(f"{MARKER}/Q/")
    assert created["has_form_draft"] is True
    draft = client.get(f"{_root(project.id)}/{created['id']}/form-draft").json()
    assert draft["rev"] == 1
    assert draft["doc"]["header"]["subject_title"] == f"{MARKER} First edit"


# ------------------------------------------------------------------ rule 7: issue / approval


def test_issue_and_request_approval_refuse_while_a_draft_is_unsaved(api):
    client, db, _company, _user, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "WC").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    _add_priced_line(client, _current_version_id(db, scope["id"]), product, price="250.00", qty="4")
    _sign(client, _root(project.id), document["id"])
    _put_draft(client, project.id, document["id"], _state("pending"), 0)

    issue = client.post(f"{_root(project.id)}/{document['id']}/issue")
    assert issue.status_code == 409, issue.text
    assert issue.json()["code"] == "quotation_draft_pending"

    approval = client.post(
        f"{_root(project.id)}/{document['id']}/approval-status",
        json={"to_status_id": str(uuid.uuid4())},
    )
    assert approval.status_code == 409, approval.text
    assert approval.json()["code"] == "quotation_draft_pending"

    # Discard (or Save) lifts it: the issue goes through.
    discarded = client.delete(f"{_root(project.id)}/{document['id']}/form-draft?base_rev=1")
    assert discarded.status_code == 200, discarded.text
    assert client.post(f"{_root(project.id)}/{document['id']}/issue").status_code == 201


def test_discard_with_a_stale_rev_is_refused(api):
    client, _db, _company, _user, project, _party = api
    document = _create_document(client, project.id)
    _put_draft(client, project.id, document["id"], _state("a"), 0)
    _put_draft(client, project.id, document["id"], _state("b"), 1)
    stale = client.delete(f"{_root(project.id)}/{document['id']}/form-draft?base_rev=1")
    assert stale.status_code == 409
    draft = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()
    assert draft["doc"]["header"]["subject_title"] == "b"


# ------------------------------------------------------------------ rule 6: locked


def test_an_approval_locked_document_refuses_its_draft(api):
    client, db, _company, _user, project, _party = api
    from app.services import project_quotation_approval_service as approvals

    from .test_project_quotation_document_routes import _document_row

    document = _create_document(client, project.id)
    row = _document_row(db, document["id"])
    row.approval_status_id = approvals._status_by_key(db, approvals.STATUS_PENDING).id
    db.commit()

    locked = _put_draft(client, project.id, document["id"], _state("x"), 0)
    assert locked.status_code == 422, locked.text
    assert locked.json()["code"] == "quotation_locked_for_approval"


# ------------------------------------------------------------------ rule 5: History / Restore


def test_restore_loads_the_entry_and_keeps_the_draft_it_replaced(api):
    client, _db, _company, _user, project, _party = api
    document = _create_document(client, project.id)
    client.patch(
        f"{_root(project.id)}/{document['id']}",
        json={"form_state": _state(f"{MARKER} Monday", total="100.00")},
    )
    saved_entry = _history(client, project.id, document["id"])[0]
    rev = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()["rev"]
    _put_draft(client, project.id, document["id"], _state(f"{MARKER} Tuesday"), rev)

    stale = client.post(
        f"{_root(project.id)}/{document['id']}/history/{saved_entry['id']}/restore",
        json={"base_rev": rev},
    )
    assert stale.status_code == 409

    restored = client.post(
        f"{_root(project.id)}/{document['id']}/history/{saved_entry['id']}/restore",
        json={"base_rev": rev + 1},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["doc"]["header"]["subject_title"] == f"{MARKER} Monday"
    assert restored.json()["rev"] == rev + 2

    kinds = [entry["kind"] for entry in _history(client, project.id, document["id"])]
    assert kinds == ["before_restore", "saved"]
    before = _history(client, project.id, document["id"])[0]
    detail = client.get(f"{_root(project.id)}/{document['id']}/history/{before['id']}").json()
    assert detail["doc"]["header"]["subject_title"] == f"{MARKER} Tuesday"


def test_a_history_entry_is_not_readable_through_another_document(api):
    client, _db, _company, _user, project, _party = api
    mine = _create_document(client, project.id)
    other = _create_document(client, project.id)
    client.patch(f"{_root(project.id)}/{mine['id']}", json={"form_state": _state("mine")})
    entry = _history(client, project.id, mine["id"])[0]
    assert client.get(f"{_root(project.id)}/{other['id']}/history/{entry['id']}").status_code == 404
    restore = client.post(
        f"{_root(project.id)}/{other['id']}/history/{entry['id']}/restore", json={"base_rev": 0}
    )
    assert restore.status_code == 404


def test_a_restored_entry_is_reconciled_against_the_record_as_it_is_now(api):
    """Without this a restored entry could never be saved: the form sends a saved scope's lines by
    id, and an id the current version no longer holds is a 404 on Save."""
    client, db, _company, user_id, project, _party = api
    uom = _uom(db)
    product = _product(db, _category(db, "Tap").id, uom, FIXTURE_LIST_PRICE)
    db.commit()
    document = _create_document(client, project.id)
    kept = _add_scope(client, project.id, document["id"], f"{MARKER} Kept")
    gone = _add_scope(client, project.id, document["id"], f"{MARKER} Gone")
    version_id = _current_version_id(db, kept["id"])
    line = _add_priced_line(client, version_id, product, price="250.00", qty="4")

    old_version = str(uuid.uuid4())
    entry_state = _state(
        f"{MARKER} Old",
        scopes=[
            {"key": kept["id"], "id": kept["id"], "scope_label": "Kept", "series_id": ""},
            {"key": gone["id"], "id": gone["id"], "scope_label": "Gone", "series_id": ""},
        ],
        staged={
            kept["id"]: {
                "versionId": old_version,
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
    client.patch(f"{_root(project.id)}/{document['id']}", json={"form_state": entry_state})
    entry = _history(client, project.id, document["id"])[0]
    # The "Gone" scope is removed after the entry was written.
    removed = client.patch(
        f"{_root(project.id)}/{document['id']}", json={"remove_scope_ids": [gone["id"]]}
    )
    assert removed.status_code == 200, removed.text

    rev = client.get(f"{_root(project.id)}/{document['id']}/form-draft").json()["rev"]
    doc = client.post(
        f"{_root(project.id)}/{document['id']}/history/{entry['id']}/restore",
        json={"base_rev": rev},
    ).json()["doc"]

    by_label = {scope["scope_label"]: scope for scope in doc["scopes"]}
    assert by_label["Kept"]["id"] == kept["id"]
    assert by_label["Gone"]["id"] is None  # a new scope now
    kept_staged = doc["staged"][kept["id"]]
    assert kept_staged["versionId"] == version_id
    assert kept_staged["seeded"] == []
    assert [l["id"] for l in kept_staged["lines"]] == [line["id"], None]
    assert kept_staged["lines"][1]["line"] is None
    assert [l["id"] for l in doc["staged"][gone["id"]]["lines"]] == [None]
    assert doc["removedIds"] == []


def test_draft_rows_cascade_with_their_document(api):
    client, db, _company, _user, project, _party = api
    document = _create_document(client, project.id)
    _put_draft(client, project.id, document["id"], _state("x"), 0)
    client.patch(f"{_root(project.id)}/{document['id']}", json={"form_state": _state("x")})
    assert client.delete(f"{_root(project.id)}/{document['id']}").status_code == 204
    db.expire_all()
    assert db.query(QuotationDocumentDraft).filter_by(document_id=document["id"]).count() == 0
    assert db.query(QuotationDocumentSnapshot).filter_by(document_id=document["id"]).count() == 0
