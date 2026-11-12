"""N8N-RETIRE-A: the CRM executes a turn's send actions itself (`crm_sender`).

Red tests written from the plan contract (section 4b). A FAKE client stands in for
`RespondClient`, so nothing here touches the network. Postgres only, via
`tests/_pg_fixture.py`; every test seeds its own `chatbot.turns` row.

Covers UAC 4, 5, 6, 7, 8, 10, 12, 13. Timeout handling, the settings switch and the
Retry route are deliberately not tested here yet.

Run: SORENTO_ENV_FILE=.env.ci-tests pytest tests/test_crm_sender.py -q
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from tests._pg_fixture import blank_session

CONTACT = "900000123"
IDENT = f"id:{CONTACT}"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


class _NoClose:
    """The test's session, handed to code that closes its own."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass


@pytest.fixture
def factory(db):
    return lambda: _NoClose(db)


@pytest.fixture
def turn_id(db):
    from app.models.chatbot_turn import ChatbotTurn

    turn = ChatbotTurn(contact_respond_id=CONTACT, envelope={}, status="processing")
    db.add(turn)
    db.flush()
    return str(turn.id)


class FakeClient:
    """Records every outbound call as (method, args, kwargs).

    `script` maps a 0-based call number to an exception to raise on that call; any
    other call succeeds with a message id.
    """

    def __init__(self, script: dict | None = None, *, lookup=None, message_id=None):
        self.calls: list[tuple] = []
        self.lookups: list[tuple] = []
        self.script = script or {}
        self.lookup = lookup if lookup is not None else []
        self.message_id = message_id

    def _do(self, name, *args, **kwargs):
        n = len(self.calls)
        self.calls.append((name, args, kwargs))
        exc = self.script.get(n)
        if exc is not None:
            raise exc
        return {"messageId": self.message_id if self.message_id is not None else n + 1}

    def list_messages(self, identifier, limit=50, cursor=None):
        self.lookups.append((identifier, limit))
        if isinstance(self.lookup, Exception):
            raise self.lookup
        return {"items": list(self.lookup), "pagination": {}}

    def send_message(self, *a, **k):
        return self._do("send_message", *a, **k)

    def send_quick_reply(self, *a, **k):
        return self._do("send_quick_reply", *a, **k)

    def send_attachment(self, *a, **k):
        return self._do("send_attachment", *a, **k)

    def set_conversation_assignee(self, *a, **k):
        return self._do("set_conversation_assignee", *a, **k)

    def create_comment(self, *a, **k):
        return self._do("create_comment", *a, **k)

    def update_contact(self, *a, **k):
        return self._do("update_contact", *a, **k)

    def names(self):
        return [c[0] for c in self.calls]


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.test/v2/contact/x/message")
    return httpx.HTTPStatusError(
        f"HTTP {code}", request=req, response=httpx.Response(code, request=req)
    )


def _outbound_disabled():
    from app.services.error_handler import AppException

    return AppException(
        status_code=403,
        message="Outbound messages are switched off for this contact",
        code="OUTBOUND_DISABLED",
    )


def _run(factory, turn_id, actions, client):
    from app.services.chatbot import crm_sender

    return crm_sender.send(
        factory, turn_id=turn_id, contact_id=CONTACT, actions=actions, client=client
    )


def _logs(db, turn_id):
    from app.models.integration import IntegrationLog

    return (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.business_id == turn_id,
            IntegrationLog.integration_channel == "chatbot_sender",
        )
        .order_by(IntegrationLog.created_at, IntegrationLog.id)
        .all()
    )


def _payload(row) -> dict:
    return json.loads(row.request_payload)


# --------------------------------------------------------------------------
# split_text
# --------------------------------------------------------------------------


def test_split_text_short_text_is_one_part():
    from app.services.chatbot.crm_sender import split_text

    assert split_text("hello there", with_quick_replies=False) == ["hello there"]


def test_split_text_limits_are_the_n8n_numbers():
    from app.services.chatbot import crm_sender

    assert crm_sender.TEXT_PART_MAX_CHARS == 3900
    assert crm_sender.QUICK_REPLY_PART_MAX_CHARS == 1024


def test_split_text_respects_3900_limit():
    from app.services.chatbot.crm_sender import split_text

    text = "\n".join(["x" * 100] * 80)  # about 8000 chars
    parts = split_text(text, with_quick_replies=False)
    assert len(parts) >= 3
    assert all(len(p) <= 3900 for p in parts)


def test_split_text_with_quick_replies_uses_1024_limit():
    from app.services.chatbot.crm_sender import split_text

    text = "\n".join(["y" * 100] * 30)  # about 3000 chars
    assert len(split_text(text, with_quick_replies=False)) == 1
    parts = split_text(text, with_quick_replies=True)
    assert len(parts) >= 3
    assert all(len(p) <= 1024 for p in parts)


def test_split_text_cuts_on_paragraph_break_before_line_break():
    from app.services.chatbot.crm_sender import split_text

    first = "\n".join(["a" * 50] * 40)  # 40 lines, ~2040 chars
    second = "\n".join(["b" * 50] * 40)
    parts = split_text(first + "\n\n" + second, with_quick_replies=False)
    assert parts == [first, second]


def test_split_text_hard_cuts_a_single_overlong_line():
    from app.services.chatbot.crm_sender import split_text

    parts = split_text("z" * 8000, with_quick_replies=False)
    assert [len(p) for p in parts] == [3900, 3900, 200]


@pytest.mark.parametrize("text", ["", "   ", "\n\n \n"])
def test_split_text_empty_or_blank_is_no_parts(text):
    from app.services.chatbot.crm_sender import split_text

    assert split_text(text, with_quick_replies=False) == []


@pytest.mark.parametrize("qr", [False, True])
def test_split_text_loses_no_non_whitespace_character(qr):
    from app.services.chatbot.crm_sender import split_text

    text = "\n\n".join(
        ["\n".join([f"line{p}-{i} " + "w" * 90 for i in range(15)]) for p in range(8)]
    ) + "\n" + "q" * 5000
    parts = split_text(text, with_quick_replies=qr)
    strip = lambda s: "".join(s.split())  # noqa: E731
    assert strip("".join(parts)) == strip(text)
    assert all(p == p.strip() for p in parts)


# --------------------------------------------------------------------------
# send(): actions in order, all five kinds
# --------------------------------------------------------------------------


def test_send_runs_all_five_kinds_in_order(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient()
    actions = [
        {"kind": "send_message", "text": "Hello"},
        {
            "kind": "send_attachments",
            "attachments_src": [{"url": "https://cdn.test/a.png", "filename": "a.png"}],
        },
        {"kind": "assign_conversation", "respond_user_id": "77"},
        {"kind": "add_comment", "text": "note", "mention_user_ids": ["1"]},
        {"kind": "update_contact_fields", "fields": {"is_human_intervened": True}},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == [
        "send_message",
        "send_attachment",
        "set_conversation_assignee",
        "create_comment",
        "update_contact",
    ]
    assert all(c[1][0] == IDENT for c in fake.calls)
    assert fake.calls[0][1][1] == "Hello"
    assert fake.calls[2][1][1] == "77"


def test_send_long_text_goes_out_as_parts_in_order(db, factory, turn_id):
    fake = FakeClient()
    text = "A" * 3000 + "\n\n" + "B" * 3000
    _run(factory, turn_id, [{"kind": "send_message", "text": text}], fake)
    assert fake.names() == ["send_message", "send_message"]
    assert fake.calls[0][1][1] == "A" * 3000
    assert fake.calls[1][1][1] == "B" * 3000


@pytest.mark.parametrize("replies", ["Yes, No , Maybe", ["Yes", " No ", "Maybe"]])
def test_quick_replies_ride_only_the_last_part(db, factory, turn_id, replies):
    fake = FakeClient()
    text = "\n\n".join(["P" * 800, "Q" * 800, "R" * 800])  # three parts at 1024
    _run(
        factory,
        turn_id,
        [{"kind": "send_message", "text": text, "quick_replies": replies}],
        fake,
    )
    assert fake.names() == ["send_message", "send_message", "send_quick_reply"]
    name, args, _ = fake.calls[2]
    assert args[0] == IDENT
    assert args[1] == "R" * 800
    assert args[2] == ["Yes", "No", "Maybe"]


def test_single_part_with_quick_replies_is_one_quick_reply_call(db, factory, turn_id):
    fake = FakeClient()
    _run(
        factory,
        turn_id,
        [{"kind": "send_message", "text": "Pick one", "quick_replies": "A,B"}],
        fake,
    )
    assert fake.names() == ["send_quick_reply"]
    assert fake.calls[0][1][2] == ["A", "B"]


def test_attachments_one_call_each_with_type_and_caption(db, factory, turn_id):
    fake = FakeClient()
    atts = [
        {"url": "https://cdn.test/1", "attachmentType": "video", "mimeType": "image/png"},
        {"url": "https://cdn.test/2", "mimeType": "audio/mpeg", "caption": "listen"},
        {"url": "https://cdn.test/3", "mimeType": "application/pdf", "filename": "x.pdf"},
        {"url": "https://cdn.test/4", "mimeType": "image/jpeg"},
    ]
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert fake.names() == ["send_attachment"] * 4

    def parts(call):
        _, args, kwargs = call
        vals = list(args[1:]) + [kwargs.get(k) for k in ("attachment_type", "url", "caption")]
        return args, kwargs

    types = []
    for _, args, kwargs in fake.calls:
        types.append(args[1] if len(args) > 1 else kwargs.get("attachment_type"))
    assert types == ["video", "audio", "file", "image"]
    urls = [a[2] if len(a) > 2 else k.get("url") for _, a, k in fake.calls]
    assert urls == [f"https://cdn.test/{i}" for i in (1, 2, 3, 4)]
    captions = [a[3] if len(a) > 3 else k.get("caption") for _, a, k in fake.calls]
    assert captions[1] == "listen"
    assert captions[0] in (None, "") and captions[2] in (None, "")


def test_comment_with_mentions_is_prefixed_on_its_own_line(db, factory, turn_id):
    fake = FakeClient()
    _run(
        factory,
        turn_id,
        [{"kind": "add_comment", "text": "Needs a human", "mention_user_ids": ["A", "B"]}],
        fake,
    )
    assert fake.calls[0][1][1] == "{{@user.A}} {{@user.B}}\nNeeds a human"


@pytest.mark.parametrize("mentions", [None, []])
def test_comment_without_mentions_is_just_the_text(db, factory, turn_id, mentions):
    fake = FakeClient()
    action = {"kind": "add_comment", "text": "Plain note"}
    if mentions is not None:
        action["mention_user_ids"] = mentions
    _run(factory, turn_id, [action], fake)
    assert fake.calls[0][1][1] == "Plain note"


def test_contact_fields_become_custom_fields_list(db, factory, turn_id):
    fake = FakeClient()
    _run(
        factory,
        turn_id,
        [{"kind": "update_contact_fields", "fields": {"alpha": "1", "beta": True}}],
        fake,
    )
    assert fake.calls[0][1][1] == {
        "custom_fields": [
            {"name": "alpha", "value": "1"},
            {"name": "beta", "value": True},
        ]
    }


def test_dry_run_and_unknown_kinds_are_skipped(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient()
    actions = [
        {"kind": "send_message", "text": "dry", "dry_run": True},
        {"kind": "teleport", "text": "??"},
        {"kind": "send_message", "text": "real"},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_message"]
    assert fake.calls[0][1][1] == "real"


# --------------------------------------------------------------------------
# Logging: one integration_log row per attempted step
# --------------------------------------------------------------------------


def test_each_step_writes_one_success_row(db, factory, turn_id):
    fake = FakeClient()
    text = "A" * 3000 + "\n\n" + "B" * 3000
    _run(
        factory,
        turn_id,
        [
            {"kind": "send_message", "text": text},
            {"kind": "assign_conversation", "respond_user_id": "9"},
        ],
        fake,
    )
    rows = _logs(db, turn_id)
    assert len(rows) == 3
    for row in rows:
        assert row.integration_channel == "chatbot_sender"
        assert row.business_table == "chatbot.turns"
        assert str(row.business_id) == turn_id
        assert row.direction == "outbound"
        assert row.status == "success"
        body = _payload(row)
        assert body["sender"] == "crm"
        assert "kind" in body
    assert sorted(_payload(r)["step"] for r in rows) == ["0.0", "0.1", "1.0"]


def test_a_failed_step_writes_one_failed_row_with_plain_message(db, factory, turn_id):
    fake = FakeClient({0: _status_error(400)})
    _run(factory, turn_id, [{"kind": "send_message", "text": "hi"}], fake)
    rows = _logs(db, turn_id)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].status_code == 400
    assert rows[0].error_message
    assert "Traceback" not in rows[0].error_message
    assert _payload(rows[0])["sender"] == "crm"
    assert _payload(rows[0])["step"] == "0.0"


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------

_REFUSALS = [
    pytest.param(lambda: httpx.ConnectError("refused"), id="connect_error"),
    pytest.param(lambda: _status_error(400), id="http_400"),
    pytest.param(lambda: _status_error(401), id="http_401"),
    pytest.param(lambda: _status_error(403), id="http_403"),
    pytest.param(lambda: _status_error(404), id="http_404"),
    pytest.param(lambda: _status_error(422), id="http_422"),
    pytest.param(lambda: _status_error(429), id="http_429"),
    pytest.param(lambda: _outbound_disabled(), id="outbound_disabled"),
]


@pytest.mark.parametrize("make_exc", _REFUSALS)
def test_refusal_returns_refused_stops_and_logs_failed(db, factory, turn_id, make_exc):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: make_exc()})
    actions = [
        {"kind": "send_message", "text": "first"},
        {"kind": "assign_conversation", "respond_user_id": "9"},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_REFUSED
    assert fake.names() == ["send_message"], "later steps must not be attempted"
    rows = _logs(db, turn_id)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].error_message and "Traceback" not in rows[0].error_message


# --------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------


def test_resume_skips_confirmed_steps(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    text = "A" * 3000 + "\n\n" + "B" * 3000
    actions = [{"kind": "send_message", "text": text}]

    first = FakeClient({1: _status_error(400)})
    assert _run(factory, turn_id, actions, first) == direct_ingress.SEND_REFUSED
    assert first.names() == ["send_message", "send_message"]

    second = FakeClient()
    assert _run(factory, turn_id, actions, second) == direct_ingress.SEND_OK
    assert second.names() == ["send_message"]
    assert second.calls[0][1][1] == "B" * 3000


def test_fully_confirmed_turn_sends_nothing_on_repeat(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    actions = [
        {"kind": "send_message", "text": "hi"},
        {"kind": "assign_conversation", "respond_user_id": "9"},
    ]
    assert _run(factory, turn_id, actions, FakeClient()) == direct_ingress.SEND_OK

    again = FakeClient()
    assert _run(factory, turn_id, actions, again) == direct_ingress.SEND_OK
    assert again.calls == []


# --------------------------------------------------------------------------
# Never raises
# --------------------------------------------------------------------------


def test_send_never_raises_on_an_unexpected_error(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: RuntimeError("boom")})
    result = _run(factory, turn_id, [{"kind": "send_message", "text": "hi"}], fake)
    assert result in {
        direct_ingress.SEND_REFUSED,
        direct_ingress.SEND_TIMEOUT,
        direct_ingress.SEND_HTTP_ERROR,
    }
    assert result != direct_ingress.SEND_OK


# --------------------------------------------------------------------------- #
# Round 2: covers()
# --------------------------------------------------------------------------- #


def _row(mode=None, contacts=None):
    from types import SimpleNamespace

    return SimpleNamespace(chatbot_reply_sender_mode=mode, chatbot_reply_sender_contacts=contacts)


def test_covers_n8n_mode_covers_nobody():
    from app.services.chatbot import crm_sender

    assert crm_sender.covers(_row("n8n", "900000123"), CONTACT) is False
    assert crm_sender.covers(_row(None), CONTACT) is False
    assert crm_sender.covers(None, CONTACT) is False


def test_covers_contacts_mode_only_listed():
    from app.services.chatbot import crm_sender

    row = _row("contacts", f"111\n{CONTACT},222")
    assert crm_sender.covers(row, CONTACT) is True
    assert crm_sender.covers(row, "999") is False


def test_covers_all_mode_covers_everyone():
    from app.services.chatbot import crm_sender

    assert crm_sender.covers(_row("all"), CONTACT) is True
    assert crm_sender.covers(_row("all"), "anyone") is True


# --------------------------------------------------------------------------- #
# Round 2: unknown outcome (timeout, 408, 5xx) and the conversation lookup
# --------------------------------------------------------------------------- #

import time  # noqa: E402

_UNKNOWN = [
    pytest.param(lambda: httpx.ReadTimeout("slow"), id="read_timeout"),
    pytest.param(lambda: _status_error(408), id="http_408"),
    pytest.param(lambda: _status_error(500), id="http_500"),
    pytest.param(lambda: _status_error(503), id="http_503"),
]


def _outgoing_text(text, *, age_seconds=0, traffic="outgoing"):
    ms = int((time.time() - age_seconds) * 1000)
    return {
        "messageId": ms * 1000,
        "traffic": traffic,
        "timestamp": ms,
        "message": {"type": "text", "text": text},
    }


def _outgoing_attachment(url, *, age_seconds=0):
    ms = int((time.time() - age_seconds) * 1000)
    return {
        "messageId": ms * 1000,
        "traffic": "outgoing",
        "timestamp": ms,
        "message": {"type": "attachment", "attachment": {"type": "image", "url": url}},
    }


_NEXT = {"kind": "assign_conversation", "respond_user_id": "9"}


@pytest.mark.parametrize("make_exc", _UNKNOWN)
def test_unknown_text_found_in_conversation_counts_as_sent(db, factory, turn_id, make_exc):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: make_exc()}, lookup=[_outgoing_text("Hello customer")])
    actions = [{"kind": "send_message", "text": "Hello customer"}, _NEXT]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_message", "set_conversation_assignee"], "the part must not be sent again"
    assert len(fake.lookups) == 1
    rows = _logs(db, turn_id)
    first = [r for r in rows if _payload(r)["step"] == "0.0"]
    assert len(first) == 1 and first[0].status == "success"
    assert _payload(first[0]).get("confirmed_by") == "lookup"


def test_unknown_quick_reply_found_in_conversation_counts_as_sent(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ReadTimeout("slow")}, lookup=[_outgoing_text("Pick one")])
    actions = [{"kind": "send_message", "text": "Pick one", "quick_replies": "A,B"}, _NEXT]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_quick_reply", "set_conversation_assignee"]


def test_unknown_attachment_found_by_url_counts_as_sent(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    url = "https://cdn.test/zzt-file.png"
    fake = FakeClient({0: _status_error(502)}, lookup=[_outgoing_attachment(url)])
    actions = [{"kind": "send_attachments", "attachments_src": [{"url": url}]}, _NEXT]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_attachment", "set_conversation_assignee"]


@pytest.mark.parametrize(
    "lookup",
    [
        pytest.param([], id="empty_conversation"),
        pytest.param([_outgoing_text("something else")], id="other_text"),
        pytest.param([_outgoing_text("Hello customer", traffic="incoming")], id="incoming_same_text"),
        pytest.param([_outgoing_text("Hello customer", age_seconds=3600)], id="same_text_long_before"),
    ],
)
def test_unknown_text_not_found_is_refused_so_the_drain_resends(db, factory, turn_id, lookup):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ReadTimeout("slow")}, lookup=lookup)
    actions = [{"kind": "send_message", "text": "Hello customer"}, _NEXT]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_REFUSED
    assert fake.names() == ["send_message"], "later steps are not attempted"
    rows = _logs(db, turn_id)
    assert [r.status for r in rows] == ["failed"]


def test_unknown_attachment_not_found_is_refused(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient(
        {0: httpx.ReadTimeout("slow")}, lookup=[_outgoing_attachment("https://cdn.test/other.png")]
    )
    actions = [{"kind": "send_attachments", "attachments_src": [{"url": "https://cdn.test/a.png"}]}]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_REFUSED


def test_unknown_text_with_failing_lookup_is_timeout(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ReadTimeout("slow")}, lookup=httpx.ConnectError("down"))
    actions = [{"kind": "send_message", "text": "Hello customer"}, _NEXT]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_TIMEOUT
    assert fake.names() == ["send_message"]
    rows = _logs(db, turn_id)
    assert rows and rows[-1].status == "failed"
    assert rows[-1].error_message and "Traceback" not in rows[-1].error_message


@pytest.mark.parametrize(
    "action,method",
    [
        ({"kind": "assign_conversation", "respond_user_id": "9"}, "set_conversation_assignee"),
        ({"kind": "update_contact_fields", "fields": {"a": "1"}}, "update_contact"),
    ],
)
def test_unknown_on_idempotent_step_is_resent_once_in_the_run(db, factory, turn_id, action, method):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ReadTimeout("slow")})
    assert _run(factory, turn_id, [action], fake) == direct_ingress.SEND_OK
    assert fake.names() == [method, method]
    assert fake.lookups == []


@pytest.mark.parametrize(
    "action,method",
    [
        ({"kind": "assign_conversation", "respond_user_id": "9"}, "set_conversation_assignee"),
        ({"kind": "update_contact_fields", "fields": {"a": "1"}}, "update_contact"),
    ],
)
def test_unknown_twice_on_idempotent_step_is_refused(db, factory, turn_id, action, method):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ReadTimeout("slow"), 1: httpx.ReadTimeout("slow")})
    assert _run(factory, turn_id, [action], fake) == direct_ingress.SEND_REFUSED
    assert fake.names() == [method, method]


def test_unknown_on_comment_is_timeout_with_no_lookup(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ReadTimeout("slow")})
    actions = [{"kind": "add_comment", "text": "note"}, _NEXT]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_TIMEOUT
    assert fake.names() == ["create_comment"]
    assert fake.lookups == []
