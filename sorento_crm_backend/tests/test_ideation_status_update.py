"""#1355 - pull the shared service's idea status-event feed, send the approved
``ideation_status_update`` template to the requester.

Keys back to
``documentation/plans/ideation/ideation-status-update-29sep-acceptance-criteria.md``
(AC-IS001 onward). Postgres only (``tests/_pg_fixture.py``). Two seams are stubbed,
nothing else: the feed (a fake feed over a list of events that honours ``after``, or
``httpx`` behind a ``MockTransport`` for the request shape) and the Respond.io HTTP
client (``RespondClient``), so the template mapping path - ``respond_template_defaults``
to ``send_template_for_use_case`` - is the production one over real rows.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.services.ideation_status_update_service as svc
import app.services.integration_service as integration_service
import app.services.respond_messaging_service as messaging
from app.models.access import RespondContact
from app.models.integration import IntegrationLog
from app.models.respond_template import (
    TEMPLATE_DEFAULT_USE_CASES,
    RespondChannel,
    RespondMessageTemplate,
    RespondTemplateDefault,
)
from app.models.respond_workspace import RespondWorkspace
from app.services.ideation_turn_service import _IdeationConfig
from tests._pg_fixture import blank_session, unique_code

BASE_URL = "https://shared.test/be"
API_KEY = "ws-key"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


class FakeRespondClient:
    """Stands in for RespondClient. Records template sends; a free-text send is a
    test failure (AC-IS050)."""

    sent: list[dict[str, Any]] = []
    fail_with: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    def send_template_message(self, identifier, **kwargs):
        if FakeRespondClient.fail_with is not None:
            raise FakeRespondClient.fail_with
        FakeRespondClient.sent.append({"identifier": identifier, **kwargs})
        return {"messageId": 991}

    def send_message(self, *args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("free text must never be sent for an ideation status update")


@pytest.fixture
def db(monkeypatch) -> Session:
    FakeRespondClient.sent = []
    FakeRespondClient.fail_with = None
    monkeypatch.setattr(integration_service, "RespondClient", FakeRespondClient)
    # The template path never reads the window. It is held OPEN anyway so that a drift
    # to send_text_or_template would take the free-text branch and hit the
    # send_message trap above (AC-IS050).
    monkeypatch.setattr(
        messaging,
        "get_window_state",
        lambda *a, **k: {"open": True, "last_incoming_at": None, "checked_at": ""},
    )
    monkeypatch.setattr(
        svc,
        "_resolve_ideation_config",
        lambda _db: _IdeationConfig(base_url=BASE_URL, api_key=API_KEY, product_id=None),
    )
    with blank_session() as session:
        yield session


def _map_template(db: Session, *, params: int = 3, status: str = "approved") -> RespondMessageTemplate:
    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=unique_code("space"),
        name="ZZT workspace",
        api_key_ciphertext="not-encrypted-test",
        is_active=True,
        is_default=True,
    )
    db.add(ws)
    db.flush()
    ch = RespondChannel(id=str(uuid.uuid4()), workspace_id=ws.id, respond_channel_id=453209)
    db.add(ch)
    db.flush()
    body = "Update on your idea {{1}}: it is now {{2}}. Track it here: {{3}}"
    tpl = RespondMessageTemplate(
        id=str(uuid.uuid4()),
        channel_id=ch.id,
        respond_template_id=77,
        name=unique_code("idea-status"),
        language_code="en",
        category="UTILITY",
        status=status,
        components=[{"type": "body", "text": body}],
        body_text=body,
        param_count=params,
    )
    db.add(tpl)
    db.flush()
    db.add(
        RespondTemplateDefault(
            use_case="ideation_status_update",
            template_id=tpl.id,
            template_name_snapshot=tpl.name,
            param_mapping={"1": "idea_number", "2": "status_label", "3": "track_url"},
        )
    )
    db.commit()
    return tpl


def _contact(db: Session, *, phone: str | None = None, outbound: bool = True,
             respond_io_id: str | None = "auto") -> RespondContact:
    phone = phone or f"+601{uuid.uuid4().int % 10**8:08d}"
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone,
        respond_io_id=(str(uuid.uuid4().int % 10**9) if respond_io_id == "auto" else respond_io_id),
        outbound_enabled=outbound,
        session_vars={},
    )
    db.add(c)
    db.commit()
    return c


def _event(seq: int, *, phone: str | None, kind: str = "status_changed", **over) -> dict:
    ev = {
        "event_id": str(uuid.uuid4()),
        "seq": seq,
        "kind": kind,
        "occurred_at": "2026-09-28T09:10:00Z",
        "idea_id": str(uuid.uuid4()),
        "idea_number": f"IDEA-{seq:04d}",
        "idea_title": "Faster quotation",
        "product_id": "prod-1",
        "status_label": "Discussed",
        "from_status_label": "New",
        "track_url": f"https://ss.test/public/ideas/tok{seq}",
        "requester_phone": phone,
        "merged_into": None,
        "separated_from": None,
        "is_test": False,
    }
    ev.update(over)
    return ev


class FakeFeed:
    """At-least-once feed over a fixed list, honouring ``after`` and ``limit``."""

    def __init__(self, events: list[dict], *, shuffle: bool = False, fail: Exception | None = None):
        self.events = events
        self.shuffle = shuffle
        self.fail = fail
        self.calls: list[dict] = []

    def __call__(self, base_url, api_key, *, after, limit):
        self.calls.append({"base_url": base_url, "api_key": api_key, "after": after, "limit": limit})
        if self.fail is not None:
            raise self.fail
        page = [e for e in self.events if e["seq"] > after][:limit]
        if self.shuffle:
            page = list(reversed(page))
        return {"events": page, "next_after": page[-1]["seq"] if page else after}


def _rows(db: Session, event_id: str | None = None) -> list[IntegrationLog]:
    q = db.query(IntegrationLog).filter(IntegrationLog.business_table == "ideation_status_events")
    if event_id is not None:
        q = q.filter(IntegrationLog.business_id == event_id)
    return q.all()


def _payload(row: IntegrationLog) -> dict:
    return json.loads(row.request_payload or "{}")


# ---------------------------------------------------------------------------
# Template use case
# ---------------------------------------------------------------------------


def test_ac_is001_use_case_registered_and_listed(db):
    from app.services import respond_template_service as rts

    assert "ideation_status_update" in TEMPLATE_DEFAULT_USE_CASES
    rows = rts.get_defaults(db)
    assert any(r["use_case"] == "ideation_status_update" for r in rows)


def test_ac_is001_set_default_accepts_the_ideation_variables(db):
    """The mapping screen saves through ``set_default``, which refuses a variable missing
    from ``PARAM_VARIABLES``; the other tests insert the row directly and never hit it."""
    from app.services import respond_template_service as rts

    tpl = _map_template(db)
    out = rts.set_default(
        db,
        "ideation_status_update",
        template_id=tpl.id,
        param_mapping={"1": "idea_number", "2": "status_label", "3": "track_url"},
    )
    assert out["is_valid"] is True
    assert out["param_mapping"] == {"1": "idea_number", "2": "status_label", "3": "track_url"}


# ---------------------------------------------------------------------------
# Kinds (AC-IS020 to AC-IS024), send path (AC-IS050), log row (AC-IS060)
# ---------------------------------------------------------------------------


def test_ac_is020_status_changed_sends_the_template_and_logs_success(db):
    tpl = _map_template(db)
    c = _contact(db)
    ev = _event(5, phone=c.phone_number)

    out = svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert out["sent"] == 1
    assert len(FakeRespondClient.sent) == 1
    send = FakeRespondClient.sent[0]
    assert send["identifier"] == c.respond_io_id
    assert send["template_name"] == tpl.name
    assert send["parameters"] == ["IDEA-0005", "Discussed", "https://ss.test/public/ideas/tok5"]

    (row,) = _rows(db, ev["event_id"])
    assert row.integration_channel == "respond_io"
    assert row.external_reference == "IDEA-0005"
    assert row.endpoint == "ideation_status_update"
    assert row.direction == "outbound"
    assert row.status == "success"
    p = _payload(row)
    assert p["event_id"] == ev["event_id"]
    assert p["kind"] == "status_changed"
    assert p["idea_number"] == "IDEA-0005"
    assert p["template"] == tpl.name
    assert p["parameters"] == ["IDEA-0005", "Discussed", "https://ss.test/public/ideas/tok5"]


def test_ac_is021_merged_names_the_survivor(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(
        6, phone=c.phone_number, kind="merged",
        merged_into={"idea_number": "IDEA-0012", "title": "Quote speed"},
    )

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent[0]["parameters"][1] == "combined with IDEA-0012"
    assert _rows(db, ev["event_id"])[0].status == "success"


def test_ac_is022_unmerged_says_separated_again_and_the_new_status(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(
        7, phone=c.phone_number, kind="unmerged", status_label="New",
        separated_from={"idea_number": "IDEA-0012", "title": "Quote speed"},
    )

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert (
        FakeRespondClient.sent[0]["parameters"][1]
        == "handled separately again from IDEA-0012, now New"
    )


def test_ac_is023_idea_number_falls_back_to_title(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(8, phone=c.phone_number, idea_number=None, idea_title="Faster quotation")

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent[0]["parameters"][0] == "Faster quotation"


def test_ac_is024_unknown_kind_skips_logs_and_advances(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(9, phone=c.phone_number, kind="archived")

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent == []
    (row,) = _rows(db, ev["event_id"])
    assert (row.status, row.error_code) == ("skipped", "UNKNOWN_KIND")
    assert svc.get_cursor(db, BASE_URL) == 9


def test_ac_is050_template_even_with_an_open_window_and_message_var(db):
    """The fixture holds the window OPEN; FakeRespondClient.send_message raises."""
    tpl = _map_template(db, params=1)
    db.query(RespondTemplateDefault).filter_by(use_case="ideation_status_update").update(
        {"param_mapping": {"1": "message"}}
    )
    db.commit()
    c = _contact(db)
    ev = _event(10, phone=c.phone_number)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent[0]["template_name"] == tpl.name
    assert FakeRespondClient.sent[0]["parameters"] == [
        "Update on your idea IDEA-0010: it is now Discussed. Track it here: "
        "https://ss.test/public/ideas/tok10"
    ]


# ---------------------------------------------------------------------------
# Idempotency (AC-IS030, AC-IS031)
# ---------------------------------------------------------------------------


def test_ac_is030_redelivered_event_is_not_sent_twice(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(11, phone=c.phone_number)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))
    # Cursor rewound (at-least-once redelivery of the same event).
    svc.set_cursor(db, BASE_URL, 0)
    db.commit()
    out = svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert len(FakeRespondClient.sent) == 1
    assert out["seen"] == 1
    assert len(_rows(db, ev["event_id"])) == 1
    assert svc.get_cursor(db, BASE_URL) == 11


def test_ac_is030_same_event_twice_in_one_page(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(12, phone=c.phone_number)
    dup = dict(ev, seq=13)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev, dup]))

    assert len(FakeRespondClient.sent) == 1
    assert len(_rows(db, ev["event_id"])) == 1
    assert svc.get_cursor(db, BASE_URL) == 13


def test_ac_is031_database_refuses_a_second_row_for_an_event(db):
    eid = str(uuid.uuid4())
    for _ in range(2):
        db.add(
            IntegrationLog(
                integration_channel="respond_io",
                business_table="ideation_status_events",
                business_id=eid,
                direction="outbound",
                endpoint="ideation_status_update",
                http_method="POST",
                status="skipped",
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ---------------------------------------------------------------------------
# Guards (AC-IS040 to AC-IS044)
# ---------------------------------------------------------------------------


def test_ac_is040_is_test_never_sends_and_logs(db):
    _map_template(db)
    c = _contact(db)
    ev = _event(20, phone=c.phone_number, is_test=True)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent == []
    (row,) = _rows(db, ev["event_id"])
    assert (row.status, row.error_code) == ("skipped", "IS_TEST")
    assert row.external_reference == "IDEA-0020"


def test_ac_is041_opted_out_skips_and_logs(db):
    _map_template(db)
    c = _contact(db, outbound=False)
    ev = _event(21, phone=c.phone_number)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent == []
    (row,) = _rows(db, ev["event_id"])
    assert (row.status, row.error_code) == ("skipped", "OPTED_OUT")


def test_ac_is042_unknown_phone_skips_and_logs(db):
    tpl = _map_template(db)
    ev = _event(22, phone="+60999000111")

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent == []
    (row,) = _rows(db, ev["event_id"])
    assert (row.status, row.error_code) == ("skipped", "UNKNOWN_CONTACT")
    # AC-IS061: a skip still names the mapped template.
    assert _payload(row)["template"] == tpl.name


def test_ac_is042_contact_without_respond_io_id_is_unknown(db):
    _map_template(db)
    c = _contact(db, respond_io_id=None)
    ev = _event(23, phone=c.phone_number)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent == []
    assert _rows(db, ev["event_id"])[0].error_code == "UNKNOWN_CONTACT"


def test_ac_is043_phone_matches_by_digits(db):
    _map_template(db)
    digits = f"601{uuid.uuid4().int % 10**8:08d}"
    c = _contact(db, phone=digits)
    ev = _event(24, phone=f"+{digits[:2]} {digits[2:4]}-{digits[4:]}")

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert FakeRespondClient.sent[0]["identifier"] == c.respond_io_id


def test_ac_is044_no_requester_phone_skips_and_logs(db):
    _map_template(db)
    ev = _event(25, phone=None)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert _rows(db, ev["event_id"])[0].error_code == "NO_REQUESTER_PHONE"


# ---------------------------------------------------------------------------
# Template mapping and send errors (AC-IS051, AC-IS052), AC-IS061, AC-IS062
# ---------------------------------------------------------------------------


def test_ac_is051_missing_mapping_skips_logs_and_goes_on(db):
    c = _contact(db)
    ev1 = _event(30, phone=c.phone_number)
    ev2 = _event(31, phone=c.phone_number)

    out = svc.poll_ideation_status_events(db, fetch=FakeFeed([ev1, ev2]))

    assert FakeRespondClient.sent == []
    assert out["skipped"] == 2
    for ev in (ev1, ev2):
        (row,) = _rows(db, ev["event_id"])
        assert (row.status, row.error_code) == ("skipped", "NO_TEMPLATE")
        assert "no default template configured" in (row.error_message or "")
        assert _payload(row)["template"] is None
    assert svc.get_cursor(db, BASE_URL) == 31


def test_ac_is051_unapproved_template_skips(db):
    _map_template(db, status="pending")
    c = _contact(db)
    ev = _event(32, phone=c.phone_number)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert _rows(db, ev["event_id"])[0].error_code == "NO_TEMPLATE"


def test_ac_is052_send_error_logs_failed_and_advances(db):
    _map_template(db)
    c = _contact(db)
    ev1 = _event(33, phone=c.phone_number)
    ev2 = _event(34, phone=c.phone_number)
    FakeRespondClient.fail_with = RuntimeError("respond 500")

    out = svc.poll_ideation_status_events(db, fetch=FakeFeed([ev1, ev2]))

    assert out["failed"] == 2
    row = _rows(db, ev1["event_id"])[0]
    assert (row.status, row.error_code) == ("failed", "SEND_FAILED")
    assert "respond 500" in row.error_message
    assert svc.get_cursor(db, BASE_URL) == 34


def test_ac_is062_no_row_is_ever_pending_or_processing(db):
    _map_template(db)
    c = _contact(db)
    off = _contact(db, outbound=False)
    events = [
        _event(40, phone=c.phone_number),
        _event(41, phone=c.phone_number, is_test=True),
        _event(42, phone=off.phone_number),
        _event(43, phone="+60999000222"),
    ]

    svc.poll_ideation_status_events(db, fetch=FakeFeed(events))

    statuses = {r.status for r in _rows(db)}
    assert statuses <= {"success", "skipped", "failed"}
    assert len(_rows(db)) == 4


# ---------------------------------------------------------------------------
# Poller and cursor (AC-IS010 to AC-IS017)
# ---------------------------------------------------------------------------


def test_ac_is010_feed_request_shape(monkeypatch):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"events": [], "next_after": 7})

    real_client = httpx.Client
    monkeypatch.setattr(
        svc.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )

    out = svc.fetch_status_events(BASE_URL + "/", API_KEY, after=7, limit=100)

    assert out == {"events": [], "next_after": 7}
    assert seen["path"] == "/be/ideation/intake/status-events"
    assert seen["params"] == {"after": "7", "limit": "100", "includeTest": "true"}
    assert seen["auth"] == f"Bearer {API_KEY}"


def test_ac_is010_poll_uses_the_stored_cursor_and_limit_100(db):
    svc.set_cursor(db, BASE_URL, 55)
    db.commit()
    feed = FakeFeed([])

    svc.poll_ideation_status_events(db, fetch=feed)

    assert feed.calls == [{"base_url": BASE_URL, "api_key": API_KEY, "after": 55, "limit": 100}]


def test_ac_is011_events_handled_ascending(db):
    _map_template(db)
    c = _contact(db)
    events = [_event(s, phone=c.phone_number) for s in (50, 51, 52)]

    svc.poll_ideation_status_events(db, fetch=FakeFeed(events, shuffle=True))

    assert [s["parameters"][0] for s in FakeRespondClient.sent] == [
        "IDEA-0050", "IDEA-0051", "IDEA-0052",
    ]
    assert svc.get_cursor(db, BASE_URL) == 52


def test_ac_is012_cursor_moves_with_each_handled_event(db, monkeypatch):
    _map_template(db)
    c = _contact(db)
    events = [_event(s, phone=c.phone_number) for s in (60, 61)]
    cursors_at_send: list[int] = []

    original = FakeRespondClient.send_template_message

    def spy(self, identifier, **kwargs):
        cursors_at_send.append(svc.get_cursor(db, BASE_URL))
        return original(self, identifier, **kwargs)

    monkeypatch.setattr(FakeRespondClient, "send_template_message", spy)

    svc.poll_ideation_status_events(db, fetch=FakeFeed(events))

    # The first send saw the untouched cursor, the second saw event 60 committed.
    assert cursors_at_send == [0, 60]
    assert svc.get_cursor(db, BASE_URL) == 61


def test_ac_is013_failed_log_write_keeps_the_cursor_and_does_not_raise(db, monkeypatch):
    _map_template(db)
    c = _contact(db)
    events = [_event(s, phone=c.phone_number, is_test=True) for s in (70, 71, 72)]
    real_commit = svc._commit_handled
    calls = {"n": 0}

    def flaky(db_, base_url, event, row):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("db down")
        return real_commit(db_, base_url, event, row)

    monkeypatch.setattr(svc, "_commit_handled", flaky)

    out = svc.poll_ideation_status_events(db, fetch=FakeFeed(events))

    assert svc.get_cursor(db, BASE_URL) == 70
    assert calls["n"] == 2  # stopped, event 72 not touched this tick
    assert out["stopped"] is True
    assert [r.external_reference for r in _rows(db)] == ["IDEA-0070"]


def test_ac_is013_a_sent_event_that_cannot_be_fully_logged_is_never_resent(db, monkeypatch):
    """Reviewer round 1 blocker: a success whose full row fails to commit must still
    be recorded (minimal row + cursor), or every tick re-sends it."""
    _map_template(db)
    c = _contact(db)
    ev = _event(74, phone=c.phone_number)
    real_commit = svc._commit_handled

    def always_fails(db_, base_url, event, row):
        raise RuntimeError("row rejected")

    monkeypatch.setattr(svc, "_commit_handled", always_fails)
    first = svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))
    monkeypatch.setattr(svc, "_commit_handled", real_commit)
    svc.set_cursor(db, BASE_URL, 0)  # even a rewound cursor must not re-send it
    db.commit()
    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert len(FakeRespondClient.sent) == 1
    assert first["stopped"] is False
    (row,) = _rows(db, ev["event_id"])
    assert (row.status, row.error_code) == ("success", "LOG_DEGRADED")


def test_ac_is023_an_overlong_title_is_logged_and_sent_once(db):
    """The title fallback can exceed external_reference's 255 chars."""
    _map_template(db)
    c = _contact(db)
    ev = _event(75, phone=c.phone_number, idea_number=None, idea_title="T" * 300)

    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))
    svc.set_cursor(db, BASE_URL, 0)
    db.commit()
    svc.poll_ideation_status_events(db, fetch=FakeFeed([ev]))

    assert len(FakeRespondClient.sent) == 1
    (row,) = _rows(db, ev["event_id"])
    assert row.status == "success"
    assert len(row.external_reference) == 255


def test_ac_is022_unmerged_with_no_status_label_reads_cleanly(db):
    ev = _event(76, phone=None, kind="unmerged", status_label="",
                separated_from={"idea_number": "IDEA-0012", "title": "x"})
    assert svc.build_context_vars(ev)["status_label"] == "handled separately again from IDEA-0012"


def test_ac_is011_seq_must_be_an_int(db):
    assert svc._seq({"seq": 5}) == 5
    assert svc._seq({"seq": "6"}) == 6
    assert svc._seq({"seq": 5.7}) is None
    assert svc._seq({"seq": True}) is None


def test_ac_is014_feed_outage_keeps_the_cursor(db):
    svc.set_cursor(db, BASE_URL, 80)
    db.commit()

    out = svc.poll_ideation_status_events(
        db, fetch=FakeFeed([], fail=svc.IdeationFeedError("boom"))
    )

    assert out["sent"] == 0
    assert svc.get_cursor(db, BASE_URL) == 80
    assert _rows(db) == []


def test_ac_is014_http_error_becomes_feed_error(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(
        svc.httpx,
        "Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down")), **kw
        ),
    )
    with pytest.raises(svc.IdeationFeedError):
        svc.fetch_status_events(BASE_URL, API_KEY, after=0, limit=100)


def test_ac_is015_config_error_does_not_raise(db, monkeypatch):
    def boom(_db):
        raise RuntimeError("cannot decrypt")

    monkeypatch.setattr(svc, "_resolve_ideation_config", boom)
    assert svc.poll_ideation_status_events(db, fetch=FakeFeed([]))["sent"] == 0


def test_ac_is015_not_configured_does_nothing(db, monkeypatch):
    monkeypatch.setattr(
        svc,
        "_resolve_ideation_config",
        lambda _db: _IdeationConfig(base_url=None, api_key=None, product_id=None),
    )
    feed = FakeFeed([])

    out = svc.poll_ideation_status_events(db, fetch=feed)

    assert feed.calls == []
    assert out["sent"] == 0


def test_ac_is016_cursor_is_per_feed_base_url(db):
    svc.set_cursor(db, BASE_URL, 90)
    svc.set_cursor(db, "https://other.test", 3)
    db.commit()

    assert svc.get_cursor(db, BASE_URL + "/") == 90
    assert svc.get_cursor(db, "https://other.test") == 3
    assert svc.get_cursor(db, "https://third.test") == 0


def test_ac_is017_scheduler_registers_the_poll_every_60s(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler

    import app.scheduler.task_scheduler as ts

    jobs: dict[str, Any] = {}

    def fake_add_job(self, func, trigger=None, id=None, **kwargs):
        jobs[id] = (func, trigger)

    monkeypatch.setattr(BackgroundScheduler, "add_job", fake_add_job)
    monkeypatch.setattr(BackgroundScheduler, "start", lambda self: None)
    monkeypatch.setattr(ts, "register_task_handlers", lambda: None)

    ts.start_scheduler()

    func, trigger = jobs["ideation_status_events_poll"]
    assert func is ts._ideation_status_events_tick
    assert trigger.interval.total_seconds() == 60


def test_tick_never_raises(monkeypatch):
    import app.scheduler.task_scheduler as ts

    def boom(_db):
        raise RuntimeError("x")

    monkeypatch.setattr(svc, "poll_ideation_status_events", boom)
    ts._ideation_status_events_tick()  # must not raise
