"""AGENT-PANEL-COMPOSER Phase 2 (red): the hourly purge of abandoned draft files.

UAC: P1. Drafts (`ai_assistant_draft` links) uploaded more than 24 h ago are hard-deleted (storage
object, renditions, link, row). Sent files and newer drafts stay.

The hourly scheduler registration itself is not asserted here: the pinned contract names only
`panel_files.purge_drafts(db, *, older_than=timedelta(hours=24)) -> int`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment
from tests.chatbot._panel_files_helpers import (
    CONVERSATION,
    csv_bytes,
    panel,  # noqa: F401  (fixture)
    png_bytes,
    store,  # noqa: F401  (fixture)
    upload,
)
from tests.chatbot.test_panel_principal import (  # noqa: F401  (fixtures)
    _scope_listeners,
    grants,
    staff,
)


def age(p, attachment_id: str, hours: float) -> None:
    db = p.factory()
    row = db.query(Attachment).filter(Attachment.id == attachment_id).one()
    row.uploaded_at = datetime.now(timezone.utc) - timedelta(hours=hours)
    db.commit()


def exists(p, attachment_id: str) -> bool:
    db = p.factory()
    return (
        db.query(Attachment).filter(Attachment.id == attachment_id).first() is not None
        or db.query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id == attachment_id).first() is not None
    )


def make(p, name="f.csv", data=None, ctype="text/csv") -> dict:
    resp = upload(p.client, name, data if data is not None else csv_bytes(), ctype)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_p1_an_old_draft_is_deleted_with_its_storage_and_renditions(panel):
    from app.services.chatbot.panel_files import purge_drafts

    old = make(panel, "old.png", png_bytes(), "image/png")
    assert len(panel.store.objects) >= 2
    age(panel, old["id"], 25)

    removed = purge_drafts(panel.factory())

    assert removed == 1
    assert not exists(panel, old["id"])
    assert panel.store.objects == {}, "an object or a rendition survived the purge"


def test_p1_a_newer_draft_stays(panel):
    from app.services.chatbot.panel_files import purge_drafts

    fresh = make(panel, "fresh.csv")
    age(panel, fresh["id"], 23)

    assert purge_drafts(panel.factory()) == 0
    assert exists(panel, fresh["id"])
    assert len(panel.store.objects) == 1


def test_p1_a_sent_file_stays_however_old(panel):
    from app.services.chatbot.panel_files import purge_drafts

    sent = make(panel, "sent.csv")
    db = panel.factory()
    link = db.query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id == sent["id"]).one()
    link.entity_type = CONVERSATION
    link.entity_id = panel.staff.conv_id
    db.commit()
    age(panel, sent["id"], 24 * 40)

    assert purge_drafts(panel.factory()) == 0
    assert exists(panel, sent["id"])
    assert len(panel.store.objects) == 1


def test_p1_only_the_old_drafts_of_a_mixed_set_go(panel):
    from app.services.chatbot.panel_files import purge_drafts

    old_a = make(panel, "a.csv")
    old_b = make(panel, "b.csv")
    new = make(panel, "c.csv")
    age(panel, old_a["id"], 48)
    age(panel, old_b["id"], 24.5)

    assert purge_drafts(panel.factory()) == 2
    assert not exists(panel, old_a["id"]) and not exists(panel, old_b["id"])
    assert exists(panel, new["id"])


def test_p1_older_than_is_a_parameter(panel):
    from app.services.chatbot.panel_files import purge_drafts

    mid = make(panel, "m.csv")
    age(panel, mid["id"], 2)

    assert purge_drafts(panel.factory()) == 0
    assert purge_drafts(panel.factory(), older_than=timedelta(hours=1)) == 1
    assert not exists(panel, mid["id"])


def test_p1_a_storage_failure_on_one_file_does_not_stop_the_sweep(panel, monkeypatch):
    from app.services.chatbot.panel_files import purge_drafts

    a = make(panel, "a.csv")
    b = make(panel, "b.csv")
    age(panel, a["id"], 30)
    age(panel, b["id"], 30)
    real = panel.store.delete_file
    calls = {"n": 0}

    def flaky(key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("storage down")
        return real(key)

    monkeypatch.setattr(panel.store, "delete_file", flaky)

    purge_drafts(panel.factory())

    assert calls["n"] >= 2, "the sweep stopped at the first storage error"
