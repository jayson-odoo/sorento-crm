"""AGENT-PANEL-COMPOSER Phase 2 (red): sending files with a panel message.

UAC: documentation/plans/chatbot/agent-panel-composer-8nov-acceptance-criteria.md, T1 to T12 and the
`can_attach` flag of the greeting.

Two harnesses:
- `brain`: `agent_loop.run_agent_turn` is a recorder (text and images captured). The route, the
  attachments, the re-link and the message rows are real. `panel_service.decide_route` is a box the test
  sets, `_stamp_route` records the decision, `agent_view` is a stub (the recorder has no turn rows).
- `real_loop`: the real agent loop over a scripted model client, to read the stored envelope (T10) and
  the next turn's history (T12).

Baseline tests (marked "baseline") pass before any implementation: they prove the harness, not the lane.

Contract assumed (tell the captain if one does not fit):
- The files fields of a stored user message are `metadata_json["files"]`, each
  `{id, filename, size, mime_type, kind, sheet, rows_read, rows_total, pages}` with NO url.
- The chat request is `{"conversation_id", "message", "attachments": [{"id", "sheet"}]}`.
"""
from __future__ import annotations

import base64
import io
import uuid
from types import SimpleNamespace

import pytest

from app.models.ai_assistant import AIAssistantMessage
from app.models.chatbot_turn import ChatbotTurn
from app.models.entity_attachment import EntityAttachmentLink
from app.services.chatbot import panel_service
from app.services.chatbot.agent import loop as agent_loop
from app.services.chatbot.router import RouteDecision
from tests.chatbot._panel_files_helpers import (
    CHAT_URL,
    CONVERSATION,
    DEALERS,
    DRAFT,
    GREETING_URL,
    UPLOAD_URL,
    act_as,
    csv_bytes,
    panel,  # noqa: F401  (fixture)
    pdf_bytes,
    png_bytes,
    store,  # noqa: F401  (fixture)
    upload,
    xlsx_bytes,
)
from tests.chatbot.test_panel_agent_side import answer_  # noqa: F401
from tests.chatbot.test_panel_principal import (  # noqa: F401  (fixtures and helpers)
    AGENT,
    USE,
    _scope_listeners,
    grants,
    seed_staff,
    staff,
)

NOT_READABLE_HERE = "I can't read files for you here."
FILE_NOT_FOUND = "File not found"
NOT_YET = "Files cannot be read here yet."


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


@pytest.fixture()
def brain(panel, monkeypatch):
    """The user is on the brain; the agent loop is a recorder."""
    panel.grants.add(AGENT)
    box = SimpleNamespace(
        calls=[],
        stamped=[],
        decision=RouteDecision("agent", "jev"),
        provider="gemini",
        reply="ZZT agent reply",
    )

    def fake_run_agent_turn(db, **kw):
        box.calls.append(kw)
        return SimpleNamespace(
            turn_id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), reply_text=box.reply, status="answered",
            limit_hit=None, rounds=1, usage={}, tool_calls=[], pending_action=None, notes=[],
        )

    monkeypatch.setattr(agent_loop, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(agent_loop, "enforce_agent_rate_limit", lambda ident: None)
    monkeypatch.setattr(agent_loop, "agent_provider_name", lambda db: box.provider, raising=False)
    monkeypatch.setattr(panel_service, "decide_route", lambda db, **kw: box.decision)
    monkeypatch.setattr(panel_service, "_stamp_route", lambda db, turn_id, decision: box.stamped.append(decision))
    monkeypatch.setattr(
        panel_service,
        "agent_view",
        lambda db, key, result: {
            "turn_id": result.turn_id, "reply_text": result.reply_text, "status": "answered", "steps": [],
            "tool_calls": [], "actions": [], "pending_action": None,
        },
    )
    panel.box = box
    return panel


def send(p, attachments=None, message="grant access to these", conv=None, client=None):
    body = {"conversation_id": conv or p.staff.conv_id, "message": message}
    if attachments is not None:
        body["attachments"] = attachments
    return (client or p.client).post(CHAT_URL, json=body)


def up(p, name, data, ctype="application/octet-stream") -> dict:
    resp = upload(p.client, name, data, ctype)
    assert resp.status_code == 201, resp.text
    return resp.json()


def messages(p, conv=None) -> list[AIAssistantMessage]:
    return (
        p.factory().query(AIAssistantMessage)
        .filter(AIAssistantMessage.conversation_id == (conv or p.staff.conv_id))
        .order_by(AIAssistantMessage.created_at, AIAssistantMessage.id)
        .all()
    )


def link_of(p, attachment_id: str):
    return p.factory().query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id == attachment_id).all()


def dealers_xlsx() -> bytes:
    return xlsx_bytes({"Dealers": DEALERS})


# --------------------------------------------------------------------------- #
# Baselines (pass today)
# --------------------------------------------------------------------------- #


def test_baseline_a_typed_message_runs_the_recorded_agent(brain):
    resp = send(brain)

    assert resp.status_code == 200, resp.text
    assert len(brain.box.calls) == 1
    assert brain.box.calls[0]["text"] == "grant access to these"
    assert resp.json()["messages"][-1]["content"] == "ZZT agent reply"


# --------------------------------------------------------------------------- #
# T1, T2: what may be attached
# --------------------------------------------------------------------------- #


def test_t1_another_users_file_is_404_and_nothing_runs(brain, session_factory):
    mine = up(brain, "mine.csv", csv_bytes(), "text/csv")
    other = seed_staff(session_factory)
    act_as(other)

    resp = send(brain, [{"id": mine["id"], "sheet": None}], conv=other.conv_id)

    assert resp.status_code == 404
    assert FILE_NOT_FOUND in resp.text
    assert messages(brain, other.conv_id) == [], "a message was saved for a refused send"
    assert brain.box.calls == []
    assert [l.entity_type for l in link_of(brain, mine["id"])] == [DRAFT]


def test_t1_an_unknown_id_is_404_and_nothing_is_saved(brain):
    resp = send(brain, [{"id": str(uuid.uuid4()), "sheet": None}])

    assert resp.status_code == 404
    assert FILE_NOT_FOUND in resp.text
    assert messages(brain) == [] and brain.box.calls == []


def test_t1_a_file_that_was_already_sent_cannot_be_sent_again(brain):
    made = up(brain, "once.csv", csv_bytes(), "text/csv")
    assert send(brain, [{"id": made["id"], "sheet": None}]).status_code == 200
    brain.box.calls.clear()

    resp = send(brain, [{"id": made["id"], "sheet": None}], message="again")

    assert resp.status_code == 404
    assert brain.box.calls == []


def test_t1_one_bad_id_among_good_ones_sends_none_of_them(brain):
    good = up(brain, "good.csv", csv_bytes(), "text/csv")

    resp = send(brain, [{"id": good["id"], "sheet": None}, {"id": str(uuid.uuid4()), "sheet": None}])

    assert resp.status_code == 404
    assert [l.entity_type for l in link_of(brain, good["id"])] == [DRAFT]
    assert brain.box.calls == []


def test_t2_six_attachments_is_422(brain):
    six = [{"id": str(uuid.uuid4()), "sheet": None} for _ in range(6)]

    resp = send(brain, six)

    assert resp.status_code == 422
    assert brain.box.calls == []


def test_t2_empty_message_and_no_files_is_422(brain):
    for message in ("", "   "):
        assert send(brain, [], message=message).status_code == 422
        assert send(brain, None, message=message).status_code == 422
    assert brain.box.calls == []


def test_t2_an_empty_message_with_one_file_is_fine(brain):
    made = up(brain, "d.xlsx", dealers_xlsx())

    resp = send(brain, [{"id": made["id"], "sheet": "Dealers"}], message="")

    assert resp.status_code == 200, resp.text
    assert len(brain.box.calls) == 1
    assert brain.box.calls[0]["text"].lstrip().startswith('Attached file "d.xlsx"')


def test_t2_whitespace_message_with_one_file_is_fine(brain):
    made = up(brain, "d.xlsx", dealers_xlsx())

    assert send(brain, [{"id": made["id"], "sheet": None}], message="  \n ").status_code == 200


def test_t3_files_from_a_user_not_on_the_brain_are_refused_and_stay_drafts(panel):
    assert AGENT not in panel.grants
    made = up(panel, "d.csv", csv_bytes(), "text/csv")

    resp = send(panel, [{"id": made["id"], "sheet": None}])

    assert resp.status_code == 422
    assert NOT_YET in resp.text
    assert [l.entity_type for l in link_of(panel, made["id"])] == [DRAFT]
    assert messages(panel) == []


# --------------------------------------------------------------------------- #
# T4, T5: the stored message and the re-link
# --------------------------------------------------------------------------- #


def test_t4_the_user_message_keeps_the_typed_text_and_the_file_fields(brain):
    sheet = up(brain, "Dealer contacts Nov.xlsx", dealers_xlsx())
    shot = up(brain, "shot.png", png_bytes(), "image/png")
    doc = up(brain, "spec.pdf", pdf_bytes(3), "application/pdf")

    resp = send(
        brain,
        [{"id": sheet["id"], "sheet": "Dealers"}, {"id": shot["id"], "sheet": None}, {"id": doc["id"], "sheet": None}],
        message="grant access to these",
    )

    assert resp.status_code == 200, resp.text
    user_msg = [m for m in messages(brain) if m.role == "user"][0]
    assert user_msg.content == "grant access to these", "the sheet block leaked into the stored text"
    files = user_msg.metadata_json["files"]
    assert files == [
        {
            "id": sheet["id"], "filename": "Dealer contacts Nov.xlsx", "size": sheet["size"],
            "mime_type": sheet["mime_type"], "kind": "sheet", "sheet": "Dealers",
            "rows_read": 2, "rows_total": 2, "pages": None,
        },
        {
            "id": shot["id"], "filename": "shot.png", "size": shot["size"], "mime_type": "image/png",
            "kind": "image", "sheet": None, "rows_read": None, "rows_total": None, "pages": None,
        },
        {
            "id": doc["id"], "filename": "spec.pdf", "size": doc["size"], "mime_type": "application/pdf",
            "kind": "pdf", "sheet": None, "rows_read": None, "rows_total": None, "pages": 3,
        },
    ]
    assert all("url" not in f and "thumb_url" not in f for f in files), "a URL was stored"


def test_t4_rows_read_is_the_cap_when_the_sheet_is_longer(brain):
    rows = [["Phone", "Name"]] + [[f"601{i:05d}", f"P{i}"] for i in range(80)]
    made = up(brain, "long.xlsx", xlsx_bytes({"Dealers": rows}))

    send(brain, [{"id": made["id"], "sheet": "Dealers"}])

    f = [m for m in messages(brain) if m.role == "user"][0].metadata_json["files"][0]
    assert (f["rows_read"], f["rows_total"]) == (50, 80)


def test_t5_the_links_move_to_the_conversation(brain):
    a = up(brain, "a.csv", csv_bytes(), "text/csv")
    b = up(brain, "b.png", png_bytes(), "image/png")

    assert send(brain, [{"id": a["id"], "sheet": None}, {"id": b["id"], "sheet": None}]).status_code == 200

    for made in (a, b):
        links = link_of(brain, made["id"])
        assert [(l.entity_type, str(l.entity_id)) for l in links] == [(CONVERSATION, brain.staff.conv_id)]
    drafts = brain.factory().query(EntityAttachmentLink).filter(
        EntityAttachmentLink.entity_type == DRAFT, EntityAttachmentLink.entity_id == brain.staff.user_id
    ).count()
    assert drafts == 0, "sent files still count as drafts"
    assert upload(brain.client, "next.csv", csv_bytes(), "text/csv").status_code == 201


# --------------------------------------------------------------------------- #
# T6: the agent's input text
# --------------------------------------------------------------------------- #


def test_t6_text_is_typed_then_one_block_per_file_in_order(brain):
    sheet = up(brain, "Dealer contacts Nov.xlsx", dealers_xlsx())
    shot = up(brain, "shot.png", png_bytes(), "image/png")
    doc = up(brain, "spec.pdf", pdf_bytes(3), "application/pdf")

    send(
        brain,
        [{"id": sheet["id"], "sheet": "Dealers"}, {"id": shot["id"], "sheet": None}, {"id": doc["id"], "sheet": None}],
    )

    text = brain.box.calls[0]["text"]
    assert text.startswith("grant access to these\n\n")
    head = 'Attached file "Dealer contacts Nov.xlsx", sheet "Dealers": 2 rows.'
    assert head in text
    assert "| Phone | Name | Role |" in text and "| 60123456789 | Person A | owner |" in text
    assert text.index(head) < text.index("[image: shot.png]") < text.index("[pdf: spec.pdf, 3 pages]")
    assert "\n\n[image: shot.png]" in text and "\n\n[pdf: spec.pdf, 3 pages]" in text


def test_t6_the_sheet_named_on_send_is_the_one_read(brain):
    made = up(brain, "two.xlsx", xlsx_bytes({"First": [["A1", "B1"], ["x", "y"]], "Second": DEALERS}))

    send(brain, [{"id": made["id"], "sheet": "Second"}])

    text = brain.box.calls[0]["text"]
    assert 'sheet "Second"' in text and "Person A" in text and "| x | y |" not in text


def test_s6_an_unknown_sheet_on_send_reads_the_first_non_empty_one(brain):
    made = up(brain, "two.xlsx", xlsx_bytes({"Blank": [], "Real": DEALERS}))

    send(brain, [{"id": made["id"], "sheet": "No such sheet"}])

    assert 'sheet "Real"' in brain.box.calls[0]["text"]


def test_t6_a_csv_block_has_no_sheet_part(brain):
    made = up(brain, "people.csv", csv_bytes(2), "text/csv")

    send(brain, [{"id": made["id"], "sheet": None}])

    first = brain.box.calls[0]["text"].split("\n\n", 1)[1].split("\n")[0]
    assert first == 'Attached file "people.csv": 2 rows.'


# --------------------------------------------------------------------------- #
# T7: routing
# --------------------------------------------------------------------------- #


def test_t7_a_chat_decision_is_overridden_to_the_agent_with_reason_attachment(brain):
    made = up(brain, "d.csv", csv_bytes(), "text/csv")
    brain.box.decision = RouteDecision("chat", "open_question")

    resp = send(brain, [{"id": made["id"], "sheet": None}])

    assert resp.status_code == 200, resp.text
    assert len(brain.box.calls) == 1, "the agent did not run for a turn with files"
    assert [(d.side, d.reason) for d in brain.box.stamped] == [("agent", "attachment")]
    assert resp.json()["messages"][-1]["metadata_json"]["route"] == "agent"


def test_t7_an_agent_decision_stays_agent(brain):
    made = up(brain, "d.csv", csv_bytes(), "text/csv")
    brain.box.decision = RouteDecision("agent", "pending_action")

    send(brain, [{"id": made["id"], "sheet": None}])

    assert len(brain.box.calls) == 1


def test_t7_not_eligible_replies_the_fixed_line_and_runs_nothing(brain):
    made = up(brain, "d.csv", csv_bytes(), "text/csv")
    brain.box.decision = RouteDecision("chat", "not_eligible:no_linked_user")

    resp = send(brain, [{"id": made["id"], "sheet": None}])

    assert resp.status_code == 200, resp.text
    last = resp.json()["messages"][-1]
    assert last["content"] == NOT_READABLE_HERE
    assert last["metadata_json"]["route"] == "chat" and last["metadata_json"]["status"] == "refused"
    assert brain.box.calls == []


# --------------------------------------------------------------------------- #
# T8, T9: images and PDFs
# --------------------------------------------------------------------------- #


def _decode(part) -> bytes:
    return base64.b64decode(part.data_b64)


def test_t8_an_image_goes_as_the_1024_px_jpeg_rendition(brain):
    from PIL import Image

    shot = up(brain, "shot.png", png_bytes((1500, 1000)), "image/png")

    send(brain, [{"id": shot["id"], "sheet": None}], message="what is this error")

    images = brain.box.calls[0]["images"]
    assert len(images) == 1
    assert images[0].mime == "image/jpeg"
    raw = _decode(images[0])
    assert raw[:3] == b"\xff\xd8\xff"
    assert max(Image.open(io.BytesIO(raw)).size) == 1024
    assert "[image: shot.png]" in brain.box.calls[0]["text"]


def test_t8_a_missing_medium_rendition_falls_back_to_a_downscale_of_the_original(brain):
    from PIL import Image

    shot = up(brain, "shot.png", png_bytes((1500, 1000)), "image/png")
    for key in [k for k in brain.store.objects if ".medium." in k]:
        del brain.store.objects[key]

    send(brain, [{"id": shot["id"], "sheet": None}])

    images = brain.box.calls[0]["images"]
    assert len(images) == 1 and images[0].mime == "image/jpeg"
    assert max(Image.open(io.BytesIO(_decode(images[0]))).size) <= 1024


def test_t8_no_images_means_none_or_empty(brain):
    made = up(brain, "d.csv", csv_bytes(), "text/csv")

    send(brain, [{"id": made["id"], "sheet": None}])

    assert not brain.box.calls[0].get("images")


def test_t9_a_pdf_goes_native_on_gemini(brain):
    brain.box.provider = "gemini"
    data = pdf_bytes(3)
    doc = up(brain, "spec.pdf", data, "application/pdf")

    send(brain, [{"id": doc["id"], "sheet": None}])

    call = brain.box.calls[0]
    assert [p.mime for p in call["images"]] == ["application/pdf"]
    assert _decode(call["images"][0]) == data
    assert "[pdf: spec.pdf, 3 pages]" in call["text"]
    assert "Hello from the PDF" not in call["text"], "the PDF text was sent as well as the PDF"


def test_t9_a_pdf_is_text_on_another_provider(brain):
    brain.box.provider = "openai"
    doc = up(brain, "spec.pdf", pdf_bytes(3), "application/pdf")

    send(brain, [{"id": doc["id"], "sheet": None}])

    call = brain.box.calls[0]
    assert not call.get("images")
    text = call["text"]
    assert "[pdf: spec.pdf, 3 pages]" in text
    assert "Hello from the PDF page 1" in text and "Hello from the PDF page 3" in text
    assert text.index("[pdf: spec.pdf, 3 pages]") < text.index("Hello from the PDF page 1")


# --------------------------------------------------------------------------- #
# T11: reading the thread
# --------------------------------------------------------------------------- #


def _files_of(msgs):
    return [m for m in msgs if m["role"] == "user"][0]["metadata_json"]["files"]


def test_t11_the_chat_response_and_the_thread_carry_fresh_urls_that_are_never_stored(brain):
    shot = up(brain, "shot.png", png_bytes(), "image/png")
    sheet = up(brain, "d.xlsx", dealers_xlsx())

    resp = send(brain, [{"id": shot["id"], "sheet": None}, {"id": sheet["id"], "sheet": "Dealers"}])

    assert resp.status_code == 200, resp.text
    sent = _files_of(resp.json()["messages"])
    thread = _files_of(
        brain.client.get(f"/api/v1/system/ai-assistant/conversations/{brain.staff.conv_id}/messages").json()
    )
    for files in (sent, thread):
        by_name = {f["filename"]: f for f in files}
        assert isinstance(by_name["shot.png"]["url"], str) and by_name["shot.png"]["url"]
        assert isinstance(by_name["shot.png"]["thumb_url"], str) and by_name["shot.png"]["thumb_url"]
        assert isinstance(by_name["d.xlsx"]["url"], str) and by_name["d.xlsx"]["url"]
        assert not by_name["d.xlsx"].get("thumb_url")
    stored = [m for m in messages(brain) if m.role == "user"][0].metadata_json["files"]
    assert all("url" not in f for f in stored)


# --------------------------------------------------------------------------- #
# Greeting
# --------------------------------------------------------------------------- #


@pytest.fixture()
def greeting(panel, monkeypatch):
    from app.api.v1.system import ai_assistant as route_mod

    monkeypatch.setattr(
        route_mod.AIAssistantChatService, "generate_greeting", lambda self, uid: {"greeting": "Hi", "suggestions": []}
    )
    return panel


def test_greeting_can_attach_is_true_for_a_user_on_the_brain(greeting):
    greeting.grants.add(AGENT)

    body = greeting.client.get(GREETING_URL).json()

    assert body["can_attach"] is True


def test_greeting_can_attach_is_false_for_a_user_not_on_the_brain(greeting):
    resp = greeting.client.get(GREETING_URL)

    assert resp.status_code == 200
    assert resp.json()["can_attach"] is False


# --------------------------------------------------------------------------- #
# T10, T12 through the real agent loop
# --------------------------------------------------------------------------- #


class SeenProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def chat(self, messages, *, tools=None, **kw):
        import copy

        self.calls.append({"messages": copy.deepcopy(messages), **kw})
        return self.replies.pop(0)


def _install_real_loop(p, monkeypatch, provider, side="chat"):
    monkeypatch.setattr(agent_loop, "_resolve_provider", lambda db: (provider, "openai", "gpt-test", None))
    monkeypatch.setattr(agent_loop, "_fetch_catalog", lambda: {})
    monkeypatch.setattr(agent_loop, "catalog_cached", lambda fetch, **kw: {})
    monkeypatch.setattr(agent_loop, "enforce_agent_rate_limit", lambda ident: None)
    monkeypatch.setattr(panel_service, "decide_route", lambda db, **kw: RouteDecision(side, "jev"))


def _turn_rows(p) -> list[ChatbotTurn]:
    return (
        p.factory().query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == f"panel-{p.staff.conv_id}", ChatbotTurn.ingress == "agent")
        .order_by(ChatbotTurn.created_at, ChatbotTurn.id)
        .all()
    )


def test_baseline_the_real_loop_answers_a_typed_message(panel, monkeypatch):
    panel.grants.add(AGENT)
    provider = SeenProvider([answer_("ZZT typed reply.")])
    _install_real_loop(panel, monkeypatch, provider, side="agent")

    resp = send(panel, None, message="hello there")

    assert resp.status_code == 200, resp.text
    assert "ZZT typed reply." in resp.json()["messages"][-1]["content"]
    assert len(_turn_rows(panel)) == 1


def test_t10_the_envelope_records_the_files_and_the_text_the_turn_read(panel, monkeypatch):
    panel.grants.add(AGENT)
    provider = SeenProvider([answer_("ZZT saw them.")])
    _install_real_loop(panel, monkeypatch, provider)
    sheet = up(panel, "Dealer contacts Nov.xlsx", dealers_xlsx())
    shot = up(panel, "shot.png", png_bytes(), "image/png")

    resp = send(panel, [{"id": sheet["id"], "sheet": "Dealers"}, {"id": shot["id"], "sheet": None}])

    assert resp.status_code == 200, resp.text
    (turn,) = _turn_rows(panel)
    assert turn.envelope["files"] == [
        {"id": sheet["id"], "filename": "Dealer contacts Nov.xlsx", "kind": "sheet"},
        {"id": shot["id"], "filename": "shot.png", "kind": "image"},
    ]
    assert turn.envelope["text"].startswith("grant access to these\n\n")
    assert "| 60123456789 | Person A | owner |" in turn.envelope["text"]
    assert [p.mime for p in provider.calls[0]["images"]] == ["image/jpeg"], "the model never got the image"


def test_t12_the_next_turn_sees_the_rows_but_not_the_image_bytes(panel, monkeypatch):
    panel.grants.add(AGENT)
    provider = SeenProvider([answer_("ZZT first."), answer_("ZZT second.")])
    _install_real_loop(panel, monkeypatch, provider)
    sheet = up(panel, "d.xlsx", dealers_xlsx())
    shot = up(panel, "shot.png", png_bytes(), "image/png")
    send(panel, [{"id": sheet["id"], "sheet": "Dealers"}, {"id": shot["id"], "sheet": None}])

    monkeypatch.setattr(panel_service, "decide_route", lambda db, **kw: RouteDecision("agent", "jev"))

    send(panel, None, message="now tag these")

    later = provider.calls[-1]
    assert not later.get("images")
    history = "\n".join(str(m.get("content") or "") for m in later["messages"])
    assert "Person A" in history and "[image: shot.png]" in history
