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
    _outgoing_text,
    _payload,
    _run,
    _status_error,
    db,
    factory,
    turn_id,
)
from tests.test_crm_sender_wiring import (  # noqa: F401 - fixtures used by name
    _answer,
    _claimed_row,
    SENDER_URL,
    _drain_turn,
    _give_n8n_sender,
    _settings,
    _turn,
    fake_respond,
    workspace,
)


def u16(value: str) -> int:
    """Length in UTF-16 code units, the unit n8n's JavaScript counts in."""
    return len(value.encode("utf-16-le")) // 2


def _url_of(call):
    _, args, kwargs = call
    return args[2] if len(args) > 2 else kwargs.get("url")


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


def test_row06_labels_are_trimmed_and_empty_ones_dropped_before_the_cap(db, factory, turn_id):
    raw = "a, ,b,,  c ," + ",".join(f"n{i}" for i in range(12))
    fake = FakeClient()
    _run(factory, turn_id, [{"kind": "send_message", "text": "Pick", "quick_replies": raw}], fake)
    assert fake.calls[0][1][2] == ["a", "b", "c"] + [f"n{i}" for i in range(7)]


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
    # No whitespace: a hard cut at 3900 units, which falls between two whole emoji.
    assert split_text(text, with_quick_replies=False) == ["😀" * 1950, "😀" * 50]


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


def test_row13_a_short_text_over_1000_bytes_still_splits_by_the_09_shrink():
    from app.services.chatbot.crm_sender import split_text

    # 600 units (under 1024) but 1800 bytes. lim 600 -> 540 -> 486 -> 437 -> 393 -> 353 -> 317
    # (951 bytes); no break point, so the hard cut is at 317 and the remaining 283 fit.
    assert split_text("あ" * 600, with_quick_replies=True) == ["あ" * 317, "あ" * 283]
    # The same text without buttons has no byte cap.
    assert split_text("あ" * 600, with_quick_replies=False) == ["あ" * 600]


def test_row13_emoji_buttons_shrink_to_whole_emoji_under_1000_bytes():
    from app.services.chatbot.crm_sender import split_text

    # 300 emoji = 600 units, 1200 bytes. lim 600 -> 540 (1080 bytes) -> 486 (972 bytes).
    assert split_text("😀" * 300, with_quick_replies=True) == ["😀" * 243, "😀" * 57]


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


def _js_split(text: str, buttons: bool) -> list[str]:
    """The live n8n sendmsg chunker, ported line for line (lengths in UTF-16 units)."""
    import struct

    def enc(value):
        raw = value.encode("utf-16-le", "surrogatepass")
        return list(struct.unpack(f"<{len(raw) // 2}H", raw))

    def dec(units):
        return struct.pack(f"<{len(units)}H", *units).decode("utf-16-le", "surrogatepass")

    def nbytes(units):
        return len(dec(units).encode("utf-8", "surrogatepass"))

    def trim(units):
        return enc(dec(units).strip())

    def last_index(units, ch, frm):
        for i in range(min(frm, len(units) - 1), -1, -1):
            if units[i] == ord(ch):
                return i
        return -1

    limit, floor, cap = (1024, 450, 1000) if buttons else (3900, 800, float("inf"))
    rest = trim(enc(text))
    parts: list[str] = []
    while len(rest) > limit or nbytes(rest) > cap:
        lim = min(limit, len(rest))
        while lim > 1 and nbytes(rest[:lim]) > cap:
            lim = int(lim * 0.9)
        at = last_index(rest, "\n", lim)
        if at < floor:
            at = last_index(rest, " ", lim)
        if at < floor:
            at = lim
        if 0 < at < len(rest) and 0xD800 <= rest[at - 1] <= 0xDBFF:
            at -= 1
        parts.append(dec(trim(rest[:at])))
        rest = trim(rest[at:])
    if rest:
        parts.append(dec(rest))
    return parts


_SAMPLES = [
    ("word " * 900, False),
    ("word " * 900, True),
    (("line of text\n" * 120) + "tail " * 300, False),
    (("あいう えお\n" * 150), True),
    ("😀 smile " * 400, True),
    ("para one\n\n" + "x" * 2000 + " " + "y" * 3000, False),
    ("a" * 449 + "\n" + "b" * 900, True),
    ("a" * 450 + "\n" + "b" * 900, True),
    ("a" * 799 + "\n" + "b " * 2500, False),
    ("a" * 800 + "\n" + "b " * 2500, False),
]


@pytest.mark.parametrize("text,buttons", _SAMPLES, ids=[f"sample{i}" for i in range(len(_SAMPLES))])
def test_row12_matches_the_live_chunker_part_for_part(text, buttons):
    from app.services.chatbot.crm_sender import split_text

    assert split_text(text, with_quick_replies=buttons) == _js_split(text, buttons)


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


def test_row23_the_cdn_match_is_case_sensitive(db, factory, turn_id, monkeypatch):
    from app.services.chatbot import crm_sender

    monkeypatch.setattr(crm_sender, "_presign", lambda *a, **k: "https://signed.test/zzt?sig=1")
    upper = "https://files.CDN-SORENTO.test/a.pdf"
    fake = FakeClient()
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": [{"url": upper}]}], fake)
    assert _url_of(fake.calls[0]) == upper


@pytest.mark.parametrize("failure", ["raises", "returns_none"])
def test_row23_a_presign_failure_sends_the_bare_original_url(db, factory, turn_id, monkeypatch, failure):
    from app.services import storage_router
    from app.services.chatbot import direct_ingress

    def broken(path, **kw):
        if failure == "raises":
            raise TimeoutError("signing too slow")
        return None

    monkeypatch.setattr(storage_router, "resolve_signed_url", broken)
    url = "https://files.cdn-sorento.test/a.pdf"
    fake = FakeClient()
    result = _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": [{"url": url}]}], fake)
    assert result == direct_ingress.SEND_OK
    assert _url_of(fake.calls[0]) == url


def _attachment_row(db, url):
    import uuid

    from app.models.resources import Attachment

    db.add(
        Attachment(
            id=str(uuid.uuid4()),
            original_filename="a.pdf",
            stored_filename=f"zzt-{uuid.uuid4().hex[:8]}.pdf",
            file_path=url,
        )
    )
    db.commit()


def test_row23_the_presign_asks_for_one_hour(db, monkeypatch):
    from app.services import storage_router
    from app.services.chatbot import crm_sender

    asked = {}

    def fake_resolve(path, **kw):
        asked["expires_in"] = kw.get("expires_in")
        return "https://signed.test/zzt?sig=2"

    monkeypatch.setattr(storage_router, "resolve_signed_url", fake_resolve)
    url = "https://files.cdn-sorento.test/a.pdf"
    _attachment_row(db, url)
    assert crm_sender._presign(db, url) == "https://signed.test/zzt?sig=2"
    assert asked["expires_in"] == 3600


# --------------------------------------------------------------------------- #
# Row 25: the file name travels
# --------------------------------------------------------------------------- #


def test_row25_send_attachment_receives_the_entry_filename(db, factory, turn_id):
    fake = FakeClient()
    atts = [{"url": "https://files.test/a.pdf", "filename": "Quarterly Sheet.pdf"}]
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert fake.calls[0][2].get("filename") == "Quarterly Sheet.pdf"


@pytest.mark.parametrize("kind", ["image", "video", "file"])
def test_row25_respond_client_puts_the_name_in_the_payload(kind):
    from unittest.mock import patch

    from app.services.integration_service import RespondClient

    client = RespondClient(api_key="zzt-key", base_url="https://api.test")
    with patch.object(RespondClient, "_post_contact_message", return_value={"messageId": 1}) as post:
        client.send_attachment("900000008", kind, "https://files.test/a", filename="Quarterly Sheet")
    assert post.call_args.args[1] == {
        "message": {
            "type": "attachment",
            "attachment": {"type": kind, "url": "https://files.test/a", "fileName": "Quarterly Sheet"},
        }
    }


# --------------------------------------------------------------------------- #
# Row 27: a file respond.io refuses goes out as its bare link, and the run goes on
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("code", [400, 404])
def test_row27_a_refused_file_falls_back_to_its_bare_url_as_text_and_continues(db, factory, turn_id, code):
    from app.services.chatbot import direct_ingress

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
    assert fake.calls[1][1] == (f"id:{CONTACT}", "https://files.test/a.pdf")


def test_row27_the_fallback_link_is_the_presigned_url_when_the_url_was_a_cdn_one(db, factory, turn_id, monkeypatch):
    from app.services.chatbot import crm_sender

    monkeypatch.setattr(crm_sender, "_presign", lambda *a, **k: "https://signed.test/zzt?sig=1")
    atts = [{"url": "https://files.cdn-sorento.test/a.pdf", "filename": "a.pdf"}]
    fake = FakeClient({0: _status_error(400)})
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert fake.calls[1][1][1] == "https://signed.test/zzt?sig=1"


def test_row27_a_connection_failure_is_not_turned_into_a_link(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    fake = FakeClient({0: httpx.ConnectError("down")})
    atts = [{"url": "https://files.test/a.pdf", "filename": "a.pdf"}]
    result = _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert result == direct_ingress.SEND_REFUSED
    assert fake.names() == ["send_attachment"]


# --------------------------------------------------------------------------- #
# Row 23 / 25: a video travels with its ORIGINAL url; image and file with the presigned one
# --------------------------------------------------------------------------- #


def test_row23_a_video_is_sent_with_the_original_url_but_image_and_file_with_the_presigned_one(
    db, factory, turn_id, monkeypatch
):
    from app.services.chatbot import crm_sender

    monkeypatch.setattr(crm_sender, "_presign", lambda *a, **k: "https://signed.test/zzt?sig=1")
    base = "https://files.cdn-sorento.test"
    atts = [
        {"url": f"{base}/v.mp4", "filename": "v.mp4", "attachmentType": "video"},
        {"url": f"{base}/i.png", "filename": "i.png", "attachmentType": "image"},
        {"url": f"{base}/d.pdf", "filename": "d.pdf", "attachmentType": "file"},
    ]
    fake = FakeClient()
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert [_url_of(c) for c in fake.calls] == [
        f"{base}/v.mp4",
        "https://signed.test/zzt?sig=1",
        "https://signed.test/zzt?sig=1",
    ]


def test_row27_a_refused_cdn_video_falls_back_to_the_presigned_link(db, factory, turn_id, monkeypatch):
    from app.services.chatbot import crm_sender

    monkeypatch.setattr(crm_sender, "_presign", lambda *a, **k: "https://signed.test/zzt?sig=1")
    atts = [{"url": "https://files.cdn-sorento.test/v.mp4", "filename": "v.mp4", "attachmentType": "video"}]
    fake = FakeClient({0: _status_error(400)})
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": atts}], fake)
    assert _url_of(fake.calls[0]) == "https://files.cdn-sorento.test/v.mp4"
    assert fake.calls[1][1][1] == "https://signed.test/zzt?sig=1"


# --------------------------------------------------------------------------- #
# Row 31: an engine that raises sends the n8n failure sentence
# --------------------------------------------------------------------------- #

LIVE_FAILURE_SENTENCE = (
    "Sorry, I couldn't process that just now \u2014 something went wrong on our side. "
    "Please try again in a moment."
)


def test_row31_the_failure_sentence_is_the_live_n8n_one():
    from app.services.chatbot import crm_sender

    assert crm_sender.FAILURE_REPLY_TEXT == LIVE_FAILURE_SENTENCE


def test_row31_an_engine_that_raises_sends_the_failure_sentence(db, factory, workspace, fake_respond, monkeypatch):
    _settings(db, chatbot_reply_sender_mode="all")
    tid, claimed_at = _claimed_row(db)

    def boom(*a, **k):
        raise RuntimeError("engine blew up")

    _drain_turn(db, factory, monkeypatch, tid, claimed_at, boom)
    sent = [c[1][1] for c in fake_respond["client"].calls if c[0] == "send_message"]
    assert sent == [LIVE_FAILURE_SENTENCE]


# --------------------------------------------------------------------------- #
# P2: the presign keeps the external route's attachment-row guard
# --------------------------------------------------------------------------- #

CDN = "https://files.cdn-sorento.test/a.pdf"


def _recording_resolve(monkeypatch):
    from app.services import storage_router

    asked = []

    def fake_resolve(path, **kw):
        asked.append((path, kw))
        return "https://signed.test/zzt?sig=3"

    monkeypatch.setattr(storage_router, "resolve_signed_url", fake_resolve)
    return asked


def test_p2_without_an_attachments_row_the_original_url_is_sent_and_nothing_is_signed(
    db, factory, turn_id, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "presigned_require_attachment_row", True)
    asked = _recording_resolve(monkeypatch)
    fake = FakeClient()
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": [{"url": CDN}]}], fake)
    assert _url_of(fake.calls[0]) == CDN
    assert asked == [], "no signed url may be issued for a path with no attachments row"


def test_p2_with_a_matching_attachments_row_the_file_is_presigned(db, factory, turn_id, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "presigned_require_attachment_row", True)
    asked = _recording_resolve(monkeypatch)
    _attachment_row(db, CDN)
    fake = FakeClient()
    _run(factory, turn_id, [{"kind": "send_attachments", "attachments_src": [{"url": CDN}]}], fake)
    assert _url_of(fake.calls[0]) == "https://signed.test/zzt?sig=3"
    assert len(asked) == 1 and asked[0][1].get("expires_in") == 3600


# --------------------------------------------------------------------------- #
# P3: a failing presign lookup leaves the sender's session usable
# --------------------------------------------------------------------------- #


def test_p3_a_presign_whose_db_lookup_raises_does_not_poison_the_next_step(db, factory, monkeypatch):
    from sqlalchemy import text as sql

    from app.api.v1.external import presigned_url
    from app.services.chatbot import direct_ingress

    def broken_lookup(session, raw, key):
        session.execute(sql("SELECT * FROM zzt_table_that_does_not_exist"))  # aborts the transaction

    monkeypatch.setattr(presigned_url, "_resolve_attachment", broken_lookup)
    tid = _turn(db)
    fake = FakeClient()
    actions = [
        {"kind": "send_attachments", "attachments_src": [{"url": CDN}]},
        {"kind": "send_message", "text": "after the file"},
    ]
    assert _run(factory, tid, actions, fake) == direct_ingress.SEND_OK
    assert fake.names() == ["send_attachment", "send_message"]
    rows = _logs(db, tid)
    assert [r.status for r in rows if _payload(r)["step"] == "1.0"] == ["success"]
    assert [r for r in rows if r.status == "processing"] == []


# --------------------------------------------------------------------------- #
# P4: the link fallback is its own logged step
# --------------------------------------------------------------------------- #

_FILE = "https://files.test/a.pdf"
_FILE_ACTION = [{"kind": "send_attachments", "attachments_src": [{"url": _FILE, "filename": "a.pdf"}]}]


def test_p4_the_fallback_row_is_marked_as_a_link(db, factory, turn_id):
    fake = FakeClient({0: _status_error(400)})
    _run(factory, turn_id, _FILE_ACTION, fake)
    links = [r for r in _logs(db, turn_id) if _payload(r).get("fallback") == "link"]
    assert len(links) == 1 and links[0].status == "success"


def test_p4_a_link_that_timed_out_is_looked_up_as_text_and_neither_part_is_resent(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    first = FakeClient({0: _status_error(400), 1: httpx.ReadTimeout("slow")}, lookup=httpx.ConnectError("down"))
    assert _run(factory, turn_id, _FILE_ACTION, first) == direct_ingress.SEND_TIMEOUT
    second = FakeClient(lookup=[_outgoing_text(_FILE)])
    assert _run(factory, turn_id, _FILE_ACTION, second) == direct_ingress.SEND_OK
    assert second.calls == [], "the link arrived, and the file is not sent again"


def test_p4_a_refused_link_is_retried_as_the_link_not_the_file(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    first = FakeClient({0: _status_error(400), 1: _status_error(400)})
    assert _run(factory, turn_id, _FILE_ACTION, first) == direct_ingress.SEND_REFUSED
    second = FakeClient()
    assert _run(factory, turn_id, _FILE_ACTION, second) == direct_ingress.SEND_OK
    assert second.names() == ["send_message"]
    assert second.calls[0][1][1] == _FILE


# --------------------------------------------------------------------------- #
# P5: three failed tries of a file, then the link
# --------------------------------------------------------------------------- #

_AFTER = {"kind": "add_comment", "text": "after the file"}


def _fail_file_runs(factory, turn_id, times, exc):
    from app.services.chatbot import direct_ingress

    for _ in range(times):
        fake = FakeClient({0: exc}, lookup=[])
        result = _run(factory, turn_id, _FILE_ACTION + [_AFTER], fake)
        assert result == direct_ingress.SEND_REFUSED
        assert fake.names() == ["send_attachment"]


def test_p5_after_three_failed_tries_the_next_send_sends_the_link_and_goes_on(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    _fail_file_runs(factory, turn_id, 3, _status_error(503))
    fourth = FakeClient(lookup=[])
    assert _run(factory, turn_id, _FILE_ACTION + [_AFTER], fourth) == direct_ingress.SEND_OK
    assert fourth.names() == ["send_message", "create_comment"]
    assert fourth.calls[0][1][1] == _FILE


def test_p5_two_failed_tries_still_retry_the_file(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    _fail_file_runs(factory, turn_id, 2, _status_error(503))
    third = FakeClient(lookup=[])
    assert _run(factory, turn_id, _FILE_ACTION + [_AFTER], third) == direct_ingress.SEND_OK
    assert third.names() == ["send_attachment", "create_comment"]


def test_p5_the_link_is_the_presigned_one_when_the_file_was_presigned(db, factory, turn_id, monkeypatch):
    from app.services.chatbot import crm_sender

    monkeypatch.setattr(crm_sender, "_presign", lambda *a, **k: "https://signed.test/zzt?sig=1")
    action = [{"kind": "send_attachments", "attachments_src": [{"url": CDN, "filename": "a.pdf"}]}]
    for _ in range(3):
        _run(factory, turn_id, action, FakeClient({0: _status_error(503)}, lookup=[]))
    fourth = FakeClient()
    _run(factory, turn_id, action, fourth)
    assert fourth.calls[0][1][1] == "https://signed.test/zzt?sig=1"


def test_p5_a_connection_error_never_turns_into_a_link(db, factory, turn_id):
    from app.services.chatbot import direct_ingress

    for _ in range(4):
        fake = FakeClient({0: httpx.ConnectError("down")})
        assert _run(factory, turn_id, _FILE_ACTION, fake) == direct_ingress.SEND_REFUSED
        assert fake.names() == ["send_attachment"]


# --------------------------------------------------------------------------- #
# N1 / N2 / N3
# --------------------------------------------------------------------------- #


def test_n1_a_list_of_buttons_is_joined_then_split_on_commas(db, factory, turn_id):
    fake = FakeClient()
    _run(
        factory,
        turn_id,
        [{"kind": "send_message", "text": "Pick", "quick_replies": ["Yes, please", "No"]}],
        fake,
    )
    assert fake.calls[0][1][2] == ["Yes", "please", "No"]


def test_n1_the_cap_of_ten_applies_after_the_split(db, factory, turn_id):
    fake = FakeClient()
    raw = ["a, b, c", "d, e, f", "g, h, i", "j, k, l"]
    _run(factory, turn_id, [{"kind": "send_message", "text": "Pick", "quick_replies": raw}], fake)
    assert fake.calls[0][1][2] == list("abcdefghij")


def test_n2_a_skipped_empty_assignee_leaves_one_skipped_success_row(db, factory, turn_id):
    fake = FakeClient()
    actions = [{"kind": "assign_conversation", "respond_user_id": ""}, {"kind": "add_comment", "text": "go on"}]
    _run(factory, turn_id, actions, fake)
    assert fake.names() == ["create_comment"]
    skipped = [r for r in _logs(db, turn_id) if _payload(r).get("skipped") == "empty_assignee"]
    assert len(skipped) == 1 and skipped[0].status == "success"


@pytest.mark.parametrize("contact", [None, ""])
def test_n3_a_missing_contact_id_leaves_a_failed_row_with_a_plain_reason(db, factory, turn_id, contact):
    from app.services.chatbot import crm_sender, direct_ingress

    fake = FakeClient()
    result = crm_sender.send(
        factory, turn_id=turn_id, contact_id=contact, actions=[{"kind": "send_message", "text": "hi"}], client=fake
    )
    assert result != direct_ingress.SEND_OK
    assert fake.calls == []
    rows = _logs(db, turn_id)
    assert len(rows) == 1 and rows[0].status == "failed"
    assert rows[0].error_message and "Traceback" not in rows[0].error_message


# --------------------------------------------------------------------------- #
# N4: the CRM failure sentence belongs to the CRM path only
# --------------------------------------------------------------------------- #


def test_n4_on_the_n8n_path_a_failed_engine_turn_never_sends_the_crm_sentence(
    db, factory, workspace, fake_respond, monkeypatch
):
    from unittest.mock import MagicMock

    from app.services.chatbot import engine
    from app.services.chatbot.crm_sender import FAILURE_REPLY_TEXT

    _settings(db, chatbot_reply_sender_mode="n8n")
    _give_n8n_sender(db, workspace, monkeypatch)
    post = MagicMock(return_value=httpx.Response(200, request=httpx.Request("POST", SENDER_URL)))
    monkeypatch.setattr(httpx, "post", post)
    tid, claimed_at = _claimed_row(db)

    _drain_turn(
        db, factory, monkeypatch, tid, claimed_at,
        lambda *a, **k: engine._failed_result("t", "understood", "boom", [], False),
    )
    assert fake_respond["client"].calls == []
    for call in post.call_args_list:
        assert FAILURE_REPLY_TEXT not in str(call.kwargs.get("json"))


def test_n4_on_the_n8n_path_an_engine_that_raises_never_sends_the_crm_sentence(
    db, factory, workspace, fake_respond, monkeypatch
):
    from unittest.mock import MagicMock

    from app.services.chatbot.crm_sender import FAILURE_REPLY_TEXT

    _settings(db, chatbot_reply_sender_mode="contacts", chatbot_reply_sender_contacts="somebody-else")
    _give_n8n_sender(db, workspace, monkeypatch)
    post = MagicMock(return_value=httpx.Response(200, request=httpx.Request("POST", SENDER_URL)))
    monkeypatch.setattr(httpx, "post", post)
    tid, claimed_at = _claimed_row(db)

    def boom(*a, **k):
        raise RuntimeError("engine blew up")

    _drain_turn(db, factory, monkeypatch, tid, claimed_at, boom)
    assert fake_respond["client"].calls == []
    for call in post.call_args_list:
        assert FAILURE_REPLY_TEXT not in str(call.kwargs.get("json"))
