"""N8N-RETIRE-A parity: the CRM sender behaves like the LIVE n8n sender, row by row.

Spec: documentation/plans/chatbot/n8n-retire-a-sender-parity.md. One test (or a small
parametrized set) per row marked "parity"; names start `test_row<NN>_`. A FakeClient stands in
for RespondClient, so nothing reaches the network. All strings are invented.
"""
from __future__ import annotations

import httpx
import pytest

from tests.test_crm_sender import (  # noqa: F401 - fixtures used by name
    CONTACT,
    FakeClient,
    _NoClose,
    _logs,
    _run,
    _status_error,
    db,
    factory,
    turn_id,
)
from tests.test_crm_sender_wiring import (  # noqa: F401 - fixtures used by name
    _answer,
    _claimed_row,
    _drain_turn,
    _settings,
    fake_respond,
    workspace,
)


def u16(value: str) -> int:
    """Length in UTF-16 code units, the unit n8n's JavaScript counts in."""
    return len(value.encode("utf-16-le")) // 2


def _sends(fake, name="send_message"):
    return [c for c in fake.calls if c[0] == name]


# --------------------------------------------------------------------------- #
# Row 2: without a contact id or a turn id, nothing is sent
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "which",
    ["turn_none", "turn_blank", "contact_none", "contact_blank"],
)
def test_row02_missing_contact_or_turn_id_sends_nothing(db, factory, turn_id, which):
    from app.services.chatbot import crm_sender, direct_ingress

    ids = {
        "turn_none": (None, CONTACT),
        "turn_blank": ("", CONTACT),
        "contact_none": (turn_id, None),
        "contact_blank": (turn_id, ""),
    }[which]
    fake = FakeClient()
    result = crm_sender.send(
        factory, turn_id=ids[0], contact_id=ids[1], actions=[{"kind": "send_message", "text": "hi"}], client=fake
    )
    assert fake.calls == []
    assert result in {
        direct_ingress.SEND_REFUSED,
        direct_ingress.SEND_TIMEOUT,
        direct_ingress.SEND_HTTP_ERROR,
    }


# --------------------------------------------------------------------------- #
# Row 3: any dry_run action drops the WHOLE turn
# --------------------------------------------------------------------------- #


def test_row03_one_dry_run_action_sends_nothing_for_the_whole_turn(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient()
    actions = [
        {"kind": "send_message", "text": "a real reply"},
        {"kind": "assign_conversation", "respond_user_id": "9"},
        {"kind": "send_message", "text": "dry", "dry_run": True},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.calls == []
    assert _logs(db, turn_id) == []


# --------------------------------------------------------------------------- #
# Row 6: buttons, split on commas, trimmed, at most 10
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("as_list", [False, True])
def test_row06_at_most_ten_buttons_are_sent_trimmed(db, factory, turn_id, as_list):
    names = [f"  opt{i} " for i in range(12)]
    raw = names if as_list else ",".join(names)
    fake = FakeClient()
    _run(factory, turn_id, [{"kind": "send_message", "text": "Pick one", "quick_replies": raw}], fake)
    assert fake.names() == ["send_quick_reply"]
    assert fake.calls[0][1][2] == [f"opt{i}" for i in range(10)]


# --------------------------------------------------------------------------- #
# Row 7: an empty assignee id is never sent to respond.io
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("assignee", [None, "", "   "])
def test_row07_assign_with_an_empty_id_is_skipped_and_the_run_continues(db, factory, turn_id, assignee):
    from app.services.chatbot import direct_ingress

    fake = FakeClient()
    actions = [
        {"kind": "assign_conversation", "respond_user_id": assignee},
        {"kind": "add_comment", "text": "after the skipped assign"},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert "set_conversation_assignee" not in fake.names()
    assert fake.names() == ["create_comment"]


# --------------------------------------------------------------------------- #
# Row 9: update_contact_fields sends nothing
# --------------------------------------------------------------------------- #


def test_row09_update_contact_fields_is_skipped_and_the_run_continues(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient()
    actions = [
        {"kind": "update_contact_fields", "fields": {"alpha": "1"}},
        {"kind": "send_message", "text": "still sent"},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert "update_contact" not in fake.names()
    assert fake.names() == ["send_message"]


# --------------------------------------------------------------------------- #
# Rows 11-13: the part rules, in UTF-16 units and UTF-8 bytes
# --------------------------------------------------------------------------- #


def test_row11_limits_count_utf16_units_plain():
    from app.services.chatbot.crm_sender import split_text

    text = "😀" * 2000  # 2000 characters, 4000 units
    parts = split_text(text, with_quick_replies=False)
    assert len(parts) >= 2
    assert all(u16(p) <= 3900 for p in parts)
    assert "".join(parts) == text


def test_row11_limits_count_utf16_units_with_buttons():
    from app.services.chatbot.crm_sender import split_text

    text = "😀" * 700  # 1400 units
    parts = split_text(text, with_quick_replies=True)
    assert len(parts) >= 2
    assert all(u16(p) <= 1024 for p in parts)
    assert "".join(parts) == text


@pytest.mark.parametrize("char", ["あ", "😀"], ids=["three_byte", "emoji"])
def test_row13_a_button_part_stays_within_1000_utf8_bytes(char):
    from app.services.chatbot.crm_sender import split_text

    text = char * 600
    parts = split_text(text, with_quick_replies=True)
    assert len(parts) >= 2
    for part in parts:
        assert len(part.encode("utf-8")) <= 1000
        assert u16(part) <= 1024
    assert "".join(parts) == text


def test_row13_buttons_ride_the_last_part_only(db, factory, turn_id):
    fake = FakeClient()
    _run(
        factory,
        turn_id,
        [{"kind": "send_message", "text": "あ" * 600, "quick_replies": "Yes,No"}],
        fake,
    )
    assert len(fake.calls) >= 2
    assert fake.names()[:-1] == ["send_message"] * (len(fake.calls) - 1)
    assert fake.names()[-1] == "send_quick_reply"
    for _, args, _kw in fake.calls:
        assert len(args[1].encode("utf-8")) <= 1000


def test_row12_cuts_at_the_last_newline_past_the_floor():
    from app.services.chatbot.crm_sender import split_text

    first = "a" * 1000 + "\n" + "b" * 1000
    text = first + "\n" + "c" * 3500
    assert split_text(text, with_quick_replies=False) == [first, "c" * 3500]


def test_row12_newline_before_the_floor_loses_to_the_last_space():
    from app.services.chatbot.crm_sender import split_text

    first = "a" * 100 + "\n" + "x" * 3000
    text = first + " " + "y" * 2000
    assert split_text(text, with_quick_replies=False) == [first, "y" * 2000]


def test_row12_no_space_and_no_newline_past_the_floor_is_a_hard_cut():
    from app.services.chatbot.crm_sender import split_text

    text = "a" * 100 + "\n" + "z" * 7000
    parts = split_text(text, with_quick_replies=False)
    assert parts == ["a" * 100 + "\n" + "z" * 3799, "z" * 3201]


def test_row12_the_floor_is_450_with_buttons():
    from app.services.chatbot.crm_sender import split_text

    past = "a" * 500 + "\n" + "b" * 900
    assert split_text(past, with_quick_replies=True) == ["a" * 500, "b" * 900]
    first = "a" * 400 + "\n" + "x" * 300
    before = first + " " + "y" * 800
    assert split_text(before, with_quick_replies=True) == [first, "y" * 800]


def test_row12_never_cuts_inside_a_surrogate_pair():
    from app.services.chatbot.crm_sender import split_text

    # The emoji occupies units 3899 and 3900: the limit falls between its two halves.
    text = "a" * 3899 + "😀" + "b" * 100
    assert split_text(text, with_quick_replies=False) == ["a" * 3899, "😀" + "b" * 100]


# --------------------------------------------------------------------------- #
# Row 21: attachments_src is a list OR {attachments: [...]}
# --------------------------------------------------------------------------- #


def test_row21_the_envelope_form_of_attachments_src_sends_the_text_and_each_file(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    envelope = {
        "attachments": [
            {"url": "https://files.test/a.pdf", "filename": "a.pdf", "mimeType": "application/pdf", "attachmentType": "file"},
            {"url": "https://files.test/b.png", "filename": "b.png", "mimeType": "image/png", "attachmentType": "image"},
        ],
        "items": [{"label": "ignored"}],
    }
    fake = FakeClient()
    actions = [
        {"kind": "send_message", "text": "Here are your files"},
        {"kind": "send_attachments", "attachments_src": envelope},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_message", "send_attachment", "send_attachment"]
    urls = [c[1][2] if len(c[1]) > 2 else c[2].get("url") for c in _sends(fake, "send_attachment")]
    assert urls == ["https://files.test/a.pdf", "https://files.test/b.png"]


# --------------------------------------------------------------------------- #
# Row 22: duplicate urls are sent once
# --------------------------------------------------------------------------- #


def test_row22_a_duplicate_url_is_sent_once(db, factory, turn_id):
    fake = FakeClient()
    atts = [
        {"url": "https://files.test/a.pdf", "filename": "a.pdf"},
        {"url": "https://files.test/a.pdf", "filename": "a-again.pdf"},
        {"url": "https://files.test/b.pdf", "filename": "b.pdf"},
    ]
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    urls = [c[1][2] if len(c[1]) > 2 else c[2].get("url") for c in _sends(fake, "send_attachment")]
    assert urls == ["https://files.test/a.pdf", "https://files.test/b.pdf"]


# --------------------------------------------------------------------------- #
# Row 23: a cdn-sorento url is replaced by a one hour presigned url
# --------------------------------------------------------------------------- #


def test_row23_cdn_urls_are_presigned_and_other_urls_pass_as_is(db, factory, turn_id, monkeypatch):
    from app.services.chatbot import crm_sender

    seen = []

    def fake_presign(session, url):
        seen.append(url)
        return "https://signed.test/zzt?sig=1"

    monkeypatch.setattr(crm_sender, "_presign", fake_presign)
    cdn = "https://files.cdn-sorento.test/a.pdf"
    other = "https://elsewhere.test/b.pdf"
    fake = FakeClient()
    _run(
        factory,
        turn_id,
        [{"kind": "send_attachments", "attachments_src": [{"url": cdn}, {"url": other}]}],
        fake,
    )
    urls = [c[1][2] if len(c[1]) > 2 else c[2].get("url") for c in _sends(fake, "send_attachment")]
    assert urls == ["https://signed.test/zzt?sig=1", other]
    assert seen == [cdn], "only the cdn-sorento url is presigned"


def test_row23_the_presign_asks_for_one_hour(db, monkeypatch):
    from app.services import storage_router
    from app.services.chatbot import crm_sender

    asked = {}

    def fake_resolve(path, **kw):
        asked["expires_in"] = kw.get("expires_in")
        return "https://signed.test/zzt?sig=2"

    monkeypatch.setattr(storage_router, "resolve_signed_url", fake_resolve)
    assert crm_sender._presign(db, "https://files.cdn-sorento.test/a.pdf") == "https://signed.test/zzt?sig=2"
    assert asked["expires_in"] == 3600


# --------------------------------------------------------------------------- #
# Row 25: the file name travels
# --------------------------------------------------------------------------- #


def test_row25_send_attachment_receives_the_entry_filename(db, factory, turn_id):
    fake = FakeClient()
    atts = [{"url": "https://files.test/a.pdf", "filename": "Quarterly Sheet.pdf"}]
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert fake.calls[0][2].get("filename") == "Quarterly Sheet.pdf"


def test_row25_respond_client_puts_the_name_in_the_payload():
    from unittest.mock import patch

    from app.services.integration_service import RespondClient

    client = RespondClient(api_key="zzt-key", base_url="https://api.test")
    with patch.object(RespondClient, "_post_contact_message", return_value={"messageId": 1}) as post:
        client.send_attachment("900000008", "file", "https://files.test/a.pdf", filename="Quarterly Sheet.pdf")
    payload = post.call_args.args[1]
    assert payload["message"]["attachment"]["fileName"] == "Quarterly Sheet.pdf"


# --------------------------------------------------------------------------- #
# Row 27: a file respond.io refuses is sent as a link, and the run goes on
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("code", [400, 404])
def test_row27_a_refused_file_falls_back_to_its_link_as_text_and_continues(db, factory, turn_id, code):
    from app.services.chatbot import crm_sender, direct_ingress

    atts = [
        {"url": "https://files.test/a.pdf", "filename": "a.pdf"},
        {"url": "https://files.test/b.pdf", "filename": "b.pdf"},
    ]
    fake = FakeClient({0: _status_error(code)})
    actions = [
        {"kind": "send_attachments", "attachments_src": atts},
        {"kind": "add_comment", "text": "after the files"},
    ]
    assert _run(factory, turn_id, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_attachment", "send_message", "send_attachment", "create_comment"]
    link = crm_sender.FILE_LINK_FALLBACK_TEXT.format(url="https://files.test/a.pdf", filename="a.pdf")
    assert fake.calls[1][1][1] == link


# --------------------------------------------------------------------------- #
# Row 31: an engine that raises sends the n8n failure sentence
# --------------------------------------------------------------------------- #


def test_row31_an_engine_that_raises_sends_the_failure_sentence(db, factory, workspace, fake_respond, monkeypatch):
    from app.services.chatbot.crm_sender import FAILURE_REPLY_TEXT

    _settings(db, chatbot_reply_sender_mode="all")
    tid, claimed_at = _claimed_row(db)

    def boom(*a, **k):
        raise RuntimeError("engine blew up")

    _drain_turn(db, factory, monkeypatch, tid, claimed_at, boom)
    sent = [c[1][1] for c in fake_respond["client"].calls if c[0] == "send_message"]
    assert sent == [FAILURE_REPLY_TEXT]
