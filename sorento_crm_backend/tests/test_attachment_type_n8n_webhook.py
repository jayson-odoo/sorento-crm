"""Per-type opt-out from the n8n intake webhook.

Every upload used to call n8n, and the upload-activity drawer reads the reply to
decide what to show. A type n8n does not handle never gets one, so the row sat on
"Processing" forever - the drawer cannot tell "still working" from "never coming".

Container Status made that visible twice over: the importer publishes the
workbook as an attachment, so one upload produced TWO permanent "Processing"
rows, the import job's and the document's.

The flag has to hold both ends or the bug half-persists: no webhook sent, and no
drawer row waiting for its answer.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from types import SimpleNamespace

import pytest

from app.models.resources import Attachment, AttachmentType
from app.services.attachment_webhook_helper import create_and_send_webhook
from tests._pg_fixture import blank_session, unique_code

# The migration is not importable as a module (alembic/versions is not a package).
_MIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic",
    "versions",
    "317_attachment_type_n8n_webhook.py",
)
_spec = importlib.util.spec_from_file_location("mig_317", _MIG_PATH)
mig317 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig317)


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _type(db, name, *, triggers=True) -> AttachmentType:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=unique_code(name),
        allowed_extensions="pdf,xlsx",
        triggers_n8n_webhook=triggers,
    )
    db.add(row)
    db.flush()
    return row


def _attachment(db, att_type) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename="f.xlsx",
        stored_filename="f.xlsx",
        file_path="https://cdn.test/f.xlsx",
        attachment_type_id=str(att_type.id),
        is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


# --- the default ----------------------------------------------------------


def test_a_new_type_triggers_the_webhook(db):
    """Default true, or introducing this column silently unhooks every type."""
    assert _type(db, "Brochure").triggers_n8n_webhook is True


# --- the send -------------------------------------------------------------


def test_an_opted_out_type_sends_nothing(db, monkeypatch):
    """Short-circuits BEFORE the webhook URL lookup, so no log row is written."""
    called = []
    monkeypatch.setattr(
        "app.services.attachment_webhook_helper.get_n8n_attachment_webhook_url",
        lambda _db: called.append("looked up") or "https://n8n.test/hook",
    )
    att_type = _type(db, "Container Status", triggers=False)

    create_and_send_webhook(db, _attachment(db, att_type), att_type, None, "user-1")

    assert called == [], "an opted-out type must not even resolve the webhook URL"


def test_an_opted_in_type_still_sends(db, monkeypatch):
    """The guard must not become an accidental global off switch."""
    reached = {}

    def spy(_db):
        # Returns None so the helper stops right after the lookup - reaching the
        # lookup at all is the assertion; actually sending would spawn a thread.
        reached["yes"] = True
        return None

    monkeypatch.setattr(
        "app.services.attachment_webhook_helper.get_n8n_attachment_webhook_url", spy
    )
    att_type = _type(db, "Product Photos", triggers=True)

    create_and_send_webhook(db, _attachment(db, att_type), att_type, None, "user-1")

    assert reached.get("yes"), "an opted-in type must still reach the webhook lookup"


def test_a_missing_type_is_treated_as_opted_in(db, monkeypatch):
    """An untyped attachment keeps today's behaviour rather than going silent."""
    reached = {}
    monkeypatch.setattr(
        "app.services.attachment_webhook_helper.get_n8n_attachment_webhook_url",
        lambda _db: reached.setdefault("yes", True) and None,
    )
    att_type = _type(db, "Untyped")

    create_and_send_webhook(db, _attachment(db, att_type), None, None, "user-1")

    assert reached.get("yes")


def test_a_type_object_without_the_attribute_is_treated_as_opted_in(db, monkeypatch):
    """Callers pass ad-hoc objects; a missing attribute must not mean "off"."""
    reached = {}
    monkeypatch.setattr(
        "app.services.attachment_webhook_helper.get_n8n_attachment_webhook_url",
        lambda _db: reached.setdefault("yes", True) and None,
    )
    att_type = _type(db, "Legacy")

    create_and_send_webhook(
        db,
        _attachment(db, att_type),
        SimpleNamespace(type_name="Legacy"),  # no triggers_n8n_webhook
        None,
        "user-1",
    )

    assert reached.get("yes")


# --- the drawer -----------------------------------------------------------


def test_the_drawer_skips_opted_out_types(db):
    """The other half. Suppressing the send alone still leaves a stuck row.

    Asserts the query the endpoint builds, not the endpoint: the route needs a
    request user and a JWT, and the thing worth pinning is which type ids get
    excluded.
    """
    opted_out = _type(db, "Container Status", triggers=False)
    opted_in = _type(db, "Product Photos", triggers=True)

    excluded = {
        str(t.id)
        for t in db.query(AttachmentType.id)
        .filter(AttachmentType.triggers_n8n_webhook.is_(False))
        .all()
    }

    assert str(opted_out.id) in excluded
    assert str(opted_in.id) not in excluded


def test_the_seeded_types_are_the_ones_n8n_ignores(db):
    """Migration 317's list, asserted against the migration rather than the live DB.

    A CI database has no attachment types at all, so reading the real rows would
    test the environment. Import the constant instead.
    """
    assert "Container Status" in mig317.OPT_OUT_TYPE_NAMES
    assert "Direct Access" in mig317.OPT_OUT_TYPE_NAMES
    assert "Response Attachment" in mig317.OPT_OUT_TYPE_NAMES
    # Stock List was the hardcoded exclusion this flag replaces - dropping it
    # would silently reintroduce the stuck row it was added to fix.
    assert "Stock_List" in mig317.OPT_OUT_TYPE_NAMES
