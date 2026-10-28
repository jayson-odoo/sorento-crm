"""FILTER-MULTISELECT PR2: the Email outbox, Outgoing mails and Respond outbox Status filters take
several values (OR within the filter). Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.models.email_outbox import EmailOutbox
from app.models.integration import IntegrationLog
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

EMAIL = "/api/v1/system/email-outbox"
MAILS = "/api/v1/system/outgoing-mails"
RESPOND = "/api/v1/system/respond-outbox"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _ids(client, url, pairs):
    return ok_ids(get(client, url, [("limit", 200), *pairs]))


# ---- Email outbox ---------------------------------------------------------------------------------

def _email(db, status):
    row = EmailOutbox(id=str(uuid.uuid4()), event_key=unique_code("ev"), recipient_email=f"{unique_code('r')}@example.com".lower(),
                      subject="ZZT subject", status=status)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def emails(db):
    return dict(p=_email(db, "pending"), s=_email(db, "sent"), f=_email(db, "failed"), f2=_email(db, "failed"))


def test_email_status_union(client, emails):
    s = emails
    assert _ids(client, EMAIL, [("status", "pending,sent")]) == {s["p"].id, s["s"].id}


def test_email_status_single_and_repeated(client, emails):
    s = emails
    assert _ids(client, EMAIL, [("status", "failed")]) == {s["f"].id, s["f2"].id}
    assert _ids(client, EMAIL, [("status", "pending"), ("status", "sent")]) == {s["p"].id, s["s"].id}


# ---- Outgoing mails -------------------------------------------------------------------------------

def _delivery(db, user, status):
    note = Notification(id=str(uuid.uuid4()), user_id=user.id, type="zzt", title="ZZT mail")
    db.add(note)
    db.flush()
    row = NotificationDelivery(id=str(uuid.uuid4()), notification_id=note.id, channel="email", status=status)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def mails(db):
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('u')}@example.com".lower(), name="ZZT Mailee")
    db.add(user)
    db.flush()
    return dict(p=_delivery(db, user, "pending"), s=_delivery(db, user, "sent"),
                f=_delivery(db, user, "failed"), f2=_delivery(db, user, "failed"))


def test_mail_status_union(client, mails):
    s = mails
    assert _ids(client, MAILS, [("status", "pending,failed")]) == {s["p"].id, s["f"].id, s["f2"].id}


def test_mail_status_single_and_repeated(client, mails):
    s = mails
    assert _ids(client, MAILS, [("status", "sent")]) == {s["s"].id}
    assert _ids(client, MAILS, [("status", "sent"), ("status", "pending")]) == {s["s"].id, s["p"].id}


# ---- Respond outbox -------------------------------------------------------------------------------

def _respond(db, status):
    row = IntegrationLog(
        id=str(uuid.uuid4()), integration_channel="respond_io", business_table="zzt", business_id=str(uuid.uuid4()),
        direction="outbound", endpoint="/x", http_method="POST", status=status,
        request_payload=json.dumps({"message": {"type": "text", "text": "ZZT hello"}}),
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def responds(db):
    return dict(p=_respond(db, "pending"), s=_respond(db, "success"), f=_respond(db, "failed"), f2=_respond(db, "failed"))


def test_respond_status_union(client, responds):
    s = responds
    assert _ids(client, RESPOND, [("status", "success,pending")]) == {s["s"].id, s["p"].id}


def test_respond_status_single_and_repeated(client, responds):
    s = responds
    assert _ids(client, RESPOND, [("status", "failed")]) == {s["f"].id, s["f2"].id}
    assert _ids(client, RESPOND, [("status", "success"), ("status", "pending")]) == {s["s"].id, s["p"].id}
