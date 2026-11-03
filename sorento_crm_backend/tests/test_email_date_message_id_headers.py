"""Every outbound email carries an RFC 5322 Date and Message-ID header.

Owner report (3 Nov 2026): CRM mail such as "OI: BRW-BB @ SO423361" showed "None" where Outlook
shows the sent time. Outlook reads the sent time from the Date header, and none of the three SMTP
builders in `app/services/notification_email.py` set one (smtplib's `sendmail` does not add it).

The guard below captures the exact bytes each sender hands to `smtplib`, so a future builder that
skips the shared stamping fails here, not in a customer's inbox.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import message_from_string
from email.utils import parsedate_to_datetime

import pytest

from app.services import notification_email as ne

_SMTP_CONFIG = {
    "host": "smtp.example.test",
    "port": "587",
    "secure": False,
    "username": None,
    "password": None,
    "from_addr": "ai@sorento.example",
}


class _FakeSMTP:
    sent: list = []

    def __init__(self, host, port, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        _FakeSMTP.sent.append(msg)


@pytest.fixture()
def captured(monkeypatch):
    _FakeSMTP.sent = []
    monkeypatch.setattr(ne.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(ne.smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP.sent


def _send_mime():
    return ne.send_mime_email(
        to_list=["buyer@example.test"],
        cc_list=["cc@example.test"],
        subject="OI: BRW-BB @ SO000001",
        body_text="body",
        body_html="<p>body</p>",
        attachments=[("OI-0000-0001.xlsx", "application/vnd.ms-excel", b"xlsx")],
        smtp_config=_SMTP_CONFIG,
        from_name="Sorento AI",
    )


def _send_multi():
    return ne.send_notification_email_multi(
        ["a@example.test", "b@example.test"], "Subject", "body", "<p>body</p>",
        smtp_config=_SMTP_CONFIG,
    )


def _send_single():
    return ne.send_notification_email(
        "a@example.test", "Subject", "body", smtp_config=_SMTP_CONFIG, from_name="Sorento",
    )


SENDERS = {
    "send_mime_email (outbox: OI, reserve, notifications, password reset)": _send_mime,
    "send_notification_email_multi": _send_multi,
    "send_notification_email": _send_single,
}


@pytest.mark.parametrize("send", list(SENDERS.values()), ids=list(SENDERS.keys()))
def test_every_sender_stamps_date_and_message_id(captured, send):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    assert send() is None
    after = datetime.now(timezone.utc)
    assert len(captured) == 1
    msg = message_from_string(captured[0])

    assert msg.get_all("Date") and len(msg.get_all("Date")) == 1
    sent_at = parsedate_to_datetime(msg["Date"])
    assert sent_at.tzinfo is not None
    # Malaysia time, so Outlook and any raw-header reader agree with the sender's clock.
    assert sent_at.utcoffset() == timedelta(hours=8)
    assert before <= sent_at <= after

    assert msg.get_all("Message-ID") and len(msg.get_all("Message-ID")) == 1
    mid = msg["Message-ID"]
    assert mid.startswith("<") and mid.endswith(">")
    assert mid.endswith("@sorento.example>")


@pytest.mark.parametrize("send", list(SENDERS.values()), ids=list(SENDERS.keys()))
def test_message_id_is_unique_per_send(captured, send):
    send()
    send()
    ids = [message_from_string(raw)["Message-ID"] for raw in captured]
    assert ids[0] != ids[1]


def test_existing_headers_and_parts_are_unchanged(captured):
    _send_mime()
    msg = message_from_string(captured[0])
    assert msg["Subject"] == "OI: BRW-BB @ SO000001"
    assert msg["From"] == '"Sorento AI" <ai@sorento.example>'
    assert msg["To"] == "buyer@example.test"
    assert msg["Cc"] == "cc@example.test"
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["OI-0000-0001.xlsx"]


def test_message_id_falls_back_when_sender_has_no_domain(captured):
    cfg = dict(_SMTP_CONFIG, from_addr="noreply")
    assert ne.send_notification_email("a@example.test", "S", "b", smtp_config=cfg) is None
    mid = message_from_string(captured[0])["Message-ID"]
    assert mid.startswith("<") and mid.endswith(">") and "@" in mid
    assert not mid.endswith("@noreply>")


@pytest.mark.parametrize(
    "from_addr", ["ai@sorento.example", " ai@sorento.example ", "Sorento <ai@sorento.example >"]
)
def test_message_id_domain_is_the_sender_domain(captured, from_addr):
    cfg = dict(_SMTP_CONFIG, from_addr=from_addr)
    assert ne.send_notification_email("a@example.test", "S", "b", smtp_config=cfg) is None
    assert message_from_string(captured[0])["Message-ID"].endswith("@sorento.example>")
