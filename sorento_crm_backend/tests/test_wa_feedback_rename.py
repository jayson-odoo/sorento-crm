"""WA-COMPLAINT-INTAKE round 15 red tests (core): "idea" becomes "feedback" in the filing flow.

Contract: documentation/plans/chatbot/COPY-wa-feedback-rename.md (owner ruling 14 Nov ~23:20). The user-facing
word is EN "feedback" / MS "maklum balas" / ZH "反馈"; the type stays shown ("Problem report" / "Feature
request"); the record number goes through ONE display function, `submission_types.display_number`, which
returns it unchanged this round.

Covers the test list items that live in core (the chatbot package is out of bounds for a test outside
`tests/chatbot/`, see `tests/chatbot/test_import_boundary.py`): the reply copy table, the rendered complete
reply, the display seam on the WhatsApp complete reply, the submission type labels, the idle reminder and the
status-update session text. The agent, tool labels, ideate lane and canned denial live in
`tests/chatbot/agent/test_wa_feedback_rename_agent.py`; the copy publish in
`tests/test_wa_feedback_copy_migration.py`.

Postgres only (blank schema via the `env` harness of test_ideation_capture_turn.py); every DB test seeds its
own chain.
"""
from __future__ import annotations

import re
import sys

import pytest

from app.main import app  # noqa: F401,E402  (first app import: resolves a circular import)

from app.services import chatbot_reply_copy
from app.services.ideation_capture_replies import render_reply
from tests.test_ideation_capture_turn import Env, env  # noqa: F401  (fixture)

LANGS = ("en", "ms", "zh")

#: The reply-copy table of the contract, `<br>` as a newline. `similar_picked` is unchanged and not listed.
TABLE: dict[str, dict[str, str]] = {
    "no_access": {
        "en": "You need a CRM login with access to send feedback here. Please ask your Sorento contact for one.",
        "ms": (
            "Anda perlukan log masuk CRM dengan akses untuk menghantar maklum balas di sini. "
            "Sila minta daripada orang perhubungan Sorento anda."
        ),
        "zh": "您需要拥有相应权限的 CRM 登录账号，才能在这里提交反馈。请向您的 Sorento 联系人申请。",
    },
    "unconfigured": {
        "en": "Feedback isn't set up here yet, so I couldn't log that. Please try again later or reach out to the team.",
        "ms": (
            "Maklum balas belum disediakan di sini, jadi saya tidak dapat merekodkannya. "
            "Sila cuba lagi nanti atau hubungi pasukan kami."
        ),
        "zh": "这里还没有开通反馈功能，所以我无法记录。请稍后再试，或联系我们的团队。",
    },
    "ask_idea": {
        "en": "Sure, what would you like changed? Tell me in one message.",
        "ms": "Boleh! Apa yang anda mahu ubah? Beritahu saya dalam satu mesej.",
        "zh": "好的！您希望改进什么？请用一条消息告诉我。",
    },
    "give_up": {
        "en": "I still couldn't tell what you'd like changed. When you're ready, send it in one message.",
        "ms": "Saya masih tidak pasti apa yang anda mahu ubah. Bila anda sudah bersedia, hantarkannya dalam satu mesej.",
        "zh": "我还是没能看出您想改进什么。准备好后，请用一条消息发送给我。",
    },
    "similar_offered": {
        "en": "You already sent feedback like this:",
        "ms": "Anda sudah menghantar maklum balas yang serupa:",
        "zh": "您已经提交过类似的反馈：",
    },
    "similar_offered_reply": {
        "en": "Reply a number to edit that one, or NEW to log this as new feedback.",
        "ms": "Balas dengan nombor untuk mengedit yang itu, atau NEW untuk merekod ini sebagai maklum balas baharu.",
        "zh": "回复编号即可编辑该反馈，或回复 NEW 记录为新反馈。",
    },
    "similar_offered_see_all": {
        "en": "See all your feedback: {{link}}",
        "ms": "Lihat semua maklum balas anda: {{link}}",
        "zh": "查看您的全部反馈：{{link}}",
    },
    "similar_picked_no_link": {
        "en": "Open {{idea_number}} in the CRM to add this.",
        "ms": "Buka {{idea_number}} di CRM untuk menambah ini.",
        "zh": "请在 CRM 中打开 {{idea_number}} 补充这些内容。",
    },
    "complete": {
        "en": (
            "Your feedback has been logged: Feature request - {{title}}\n"
            "Number: {{idea_number}}\n"
            "Open it to add what I didn't catch:\n"
            "{{missing}}\n"
            "{{link}}"
        ),
        "ms": (
            "Maklum balas anda telah direkodkan: Permintaan ciri - {{title}}\n"
            "Nombor: {{idea_number}}\n"
            "Buka untuk menambah apa yang saya tidak tangkap:\n"
            "{{missing}}\n"
            "{{link}}"
        ),
        "zh": (
            "您的反馈已记录：功能需求 - {{title}}\n"
            "编号：{{idea_number}}\n"
            "打开它补充我没有记录到的内容：\n"
            "{{missing}}\n"
            "{{link}}"
        ),
    },
    "complete_no_link": {
        "en": "Your feedback has been logged: Feature request - {{title}}\nNumber: {{idea_number}}",
        "ms": "Maklum balas anda telah direkodkan: Permintaan ciri - {{title}}\nNombor: {{idea_number}}",
        "zh": "您的反馈已记录：功能需求 - {{title}}\n编号：{{idea_number}}",
    },
    "complete_issue": {
        "en": "Your feedback has been logged: Problem report - {{title}}\nNumber: {{idea_number}}",
        "ms": "Maklum balas anda telah direkodkan: Laporan masalah - {{title}}\nNombor: {{idea_number}}",
        "zh": "您的反馈已记录：问题报告 - {{title}}\n编号：{{idea_number}}",
    },
    "type_refused": {
        "en": "I couldn't file this: feedback of this type can't be taken yet.",
        "ms": "Saya tidak dapat menghantar ini: maklum balas jenis ini belum boleh diterima.",
        "zh": "我无法提交这个：暂时不接受此类型的反馈。",
    },
    "error": {
        "en": "Sorry, I couldn't save that feedback just now. Please try again in a moment.",
        "ms": "Maaf, saya tidak dapat menyimpan maklum balas itu sekarang. Sila cuba lagi sebentar nanti.",
        "zh": "抱歉，我暂时无法保存这条反馈，请稍后再试。",
    },
    "config_error": {
        "en": "Feedback isn't set up correctly here, so I couldn't save that. Please let your Sorento contact know.",
        "ms": (
            "Maklum balas tidak disediakan dengan betul di sini, jadi saya tidak dapat menyimpannya. "
            "Sila maklumkan kepada wakil Sorento anda."
        ),
        "zh": "此处的反馈设置不正确，所以我无法保存。请告知您的 Sorento 联系人。",
    },
}

#: The head line of the filed reply, title filled, per type and language (the contract's owner example).
HEAD = {
    "issue": {
        "en": "Your feedback has been logged: Problem report - {title}",
        "ms": "Maklum balas anda telah direkodkan: Laporan masalah - {title}",
        "zh": "您的反馈已记录：问题报告 - {title}",
    },
    "idea": {
        "en": "Your feedback has been logged: Feature request - {title}",
        "ms": "Maklum balas anda telah direkodkan: Permintaan ciri - {title}",
        "zh": "您的反馈已记录：功能需求 - {title}",
    },
}
NUMBER_LINE = {"en": "Number: {n}", "ms": "Nombor: {n}", "zh": "编号：{n}"}

_TOKEN = re.compile(r"\{\{[^}]*\}\}")


def patch_display_number(monkeypatch, fake) -> None:
    """Replace `submission_types.display_number` everywhere it is reachable: on the module and on every loaded
    `app.*` module that imported the name directly, so the test holds wherever the caller put the seam."""
    from app.services import submission_types

    original = getattr(submission_types, "display_number", None)
    assert callable(original), "submission_types.display_number does not exist yet"
    monkeypatch.setattr(submission_types, "display_number", fake)
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith("app."):
            continue
        if getattr(module, "display_number", None) is original:
            monkeypatch.setattr(module, "display_number", fake)


def _fake_display(number):
    return "#0184" if number else number


# --------------------------------------------------------------------------- #
# 1. The copy                                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", sorted(TABLE))
def test_copy_text_equals_the_table(name, lang):
    shipped = getattr(chatbot_reply_copy, f"IDEATION_CAPTURE_{name.upper()}")
    assert shipped[lang] == TABLE[name][lang]


def _ideation_capture_texts():
    for name, (texts, _tokens) in chatbot_reply_copy.FALLBACK_REPLY_COPY.items():
        if name.startswith("ideation_capture_"):
            for lang, text in texts.items():
                yield name, lang, text


def test_no_shipped_ideation_capture_text_says_idea():
    """Key names may say idea; the shipped texts (tokens such as {{idea_number}} aside) may not."""
    offenders = []
    for name, lang, text in _ideation_capture_texts():
        words = _TOKEN.sub("", text)
        if "idea" in words.lower() or "创意" in words:
            offenders.append(f"{name}.{lang}: {text!r}")
    assert not offenders, "\n".join(offenders)


# --------------------------------------------------------------------------- #
# 2. Rendering                                                                #
# --------------------------------------------------------------------------- #
FACTS = {"idea_number": "IDEA-0184", "title": "Quotation page error", "link": "https://crm.example/ideas/x"}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind_type", ["issue", "idea"])
def test_the_complete_reply_starts_with_the_type_head_line_and_carries_the_number(kind_type, lang):
    reply = render_reply("complete", {"type": kind_type, **FACTS}, user_message="", language=lang)
    head = HEAD[kind_type][lang].format(title=FACTS["title"])
    assert reply.startswith(head), reply
    assert "IDEA-0184" in reply
    assert NUMBER_LINE[lang].format(n="IDEA-0184") in reply.splitlines()


# --------------------------------------------------------------------------- #
# 3. The one number display seam                                              #
# --------------------------------------------------------------------------- #
def test_display_number_returns_the_number_unchanged_this_round():
    from app.services import submission_types

    assert submission_types.display_number("IDEA-0184") == "IDEA-0184"
    assert not submission_types.display_number(None)


@pytest.mark.parametrize("kind_type", ["issue", "idea"])
def test_the_whatsapp_complete_reply_shows_the_number_through_display_number(env, monkeypatch, kind_type):  # noqa: F811
    patch_display_number(monkeypatch, _fake_display)
    env.ready()
    env.created()
    text = env.idea_message(language="en")
    env.extractions[text].type = kind_type
    out = env.turn(text)
    assert out["status"] == "complete", out
    reply = out["reply_text"]
    assert "Number: #0184" in reply.splitlines(), reply
    assert "IDEA-0184" not in reply, reply


# --------------------------------------------------------------------------- #
# 5. The type labels                                                          #
# --------------------------------------------------------------------------- #
def test_the_type_labels_are_problem_report_and_feature_request():
    from app.services.submission_types import SUBMISSION_TYPES

    assert SUBMISSION_TYPES["issue"].label == "Problem report"
    assert SUBMISSION_TYPES["idea"].label == "Feature request"


# --------------------------------------------------------------------------- #
# 6. Reminder and status update (core)                                        #
# --------------------------------------------------------------------------- #
def test_the_idle_reminder_says_your_feedback():
    from app.services.ideation_turn_service import _ideation_reminder_text

    assert _ideation_reminder_text("Stock list") == (
        'Your feedback "Stock list" is still open. Reply to finish it, or say cancel.'
    )
    assert "idea" not in _ideation_reminder_text(None).lower()


def test_the_status_update_session_text_says_update_on_your_feedback():
    from app.services.ideation_status_update_service import build_context_vars

    message = build_context_vars({"kind": "status", "idea_number": "IDEA-0010", "status_label": "Discussed"})[
        "message"
    ]
    assert message.startswith("Update on your feedback IDEA-0010: it is now Discussed."), message
    assert "idea " not in message.lower()
