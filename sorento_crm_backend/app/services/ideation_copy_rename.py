"""WA-COMPLAINT-INTAKE round 15: publish the "feedback" reply copy (documentation/plans/chatbot/
COPY-wa-feedback-rename.md, "How it ships").

`seed_prompt_registry` is insert-only, so an install seeded before this round keeps the old "idea" texts on its
`production` labels. `publish(session)` adds each new text (the shipped fallback in `chatbot_reply_copy`) as the
next version and moves that key's `production` label, but ONLY where production still equals the stock text it
replaces (strip-normalised). A text the owner edited is left alone with a warning; a re-run is a no-op because
production then equals the new text. Each key and language is judged on its own. Modelled on
`alembic/versions/idea_capture_fields_0001.py`; migration `wa_0004_feedback_copy` calls it after the seed.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_seed import _ensure_version, _max_version, _set_label
from app.services.chatbot_reply_copy import CHATBOT_REPLY_COPY, FALLBACK_LANGUAGES, language_suffix

logger = logging.getLogger(__name__)

#: short copy name -> language -> the text shipped before this round, verbatim (an install seeded before it
#: froze exactly this on `production`).
STOCK: dict[str, dict[str, str]] = {
    "no_access": {
        "en": 'You need a CRM login with Ideas access to submit ideas here. Please ask your Sorento contact for one.',
        "ms": 'Anda perlukan log masuk CRM dengan akses Idea untuk menghantar idea di sini. Sila minta daripada orang perhubungan Sorento anda.',
        "zh": '您需要拥有 Ideas 权限的 CRM 登录账号，才能在这里提交创意。请向您的 Sorento 联系人申请。',
    },
    "unconfigured": {
        "en": "Idea capture isn't set up here yet, so I couldn't log that. Please try again later or reach out to the team.",
        "ms": 'Penghantaran idea belum disediakan di sini, jadi saya tidak dapat merekodkannya. Sila cuba lagi nanti atau hubungi pasukan kami.',
        "zh": '这里还没有开通创意提交功能，所以我无法记录。请稍后再试，或联系我们的团队。',
    },
    "ask_idea": {
        "en": "Sure, what's your idea? Tell me what you'd like changed, in one message.",
        "ms": 'Boleh! Apakah idea anda? Beritahu saya apa yang anda mahu ubah, dalam satu mesej.',
        "zh": '好的！您的创意是什么？请用一条消息告诉我您想改进什么。',
    },
    "give_up": {
        "en": "I still couldn't find an idea in that. When you're ready, send your idea in one message, for example what you'd like changed.",
        "ms": 'Saya masih tidak menjumpai idea dalam mesej itu. Bila anda sudah bersedia, hantar idea anda dalam satu mesej, contohnya apa yang anda mahu ubah.',
        "zh": '我还是没能从中找到创意。准备好后，请用一条消息发送您的创意，例如您想改进什么。',
    },
    "similar_offered": {
        "en": 'You already have ideas like this:',
        "ms": 'Anda sudah ada idea yang serupa:',
        "zh": '您已经有类似的创意：',
    },
    "similar_offered_reply": {
        "en": 'Reply a number to edit that one, or NEW to log this as a new idea.',
        "ms": 'Balas dengan nombor untuk mengedit idea itu, atau NEW untuk merekod sebagai idea baharu.',
        "zh": '回复编号即可编辑该创意，或回复 NEW 记录为新创意。',
    },
    "similar_offered_see_all": {
        "en": 'See all your ideas: {{link}}',
        "ms": 'Lihat semua idea anda: {{link}}',
        "zh": '查看您的全部创意：{{link}}',
    },
    "similar_picked_no_link": {
        "en": 'Open {{idea_number}} in the CRM Ideas page to add this.',
        "ms": 'Buka {{idea_number}} di halaman Idea CRM untuk menambah ini.',
        "zh": '请在 CRM 的创意页面打开 {{idea_number}} 补充这些内容。',
    },
    "complete": {
        "en": "Idea {{idea_number}} is in: {{title}}\nOpen it to add what I didn't catch:\n{{missing}}\n{{link}}",
        "ms": 'Idea {{idea_number}} sudah diterima: {{title}}\nBuka untuk menambah apa yang saya tidak tangkap:\n{{missing}}\n{{link}}',
        "zh": '创意 {{idea_number}} 已收到：{{title}}\n打开它补充我没有记录到的内容：\n{{missing}}\n{{link}}',
    },
    "complete_no_link": {
        "en": 'Idea {{idea_number}} is in: {{title}}',
        "ms": 'Idea {{idea_number}} sudah diterima: {{title}}',
        "zh": '创意 {{idea_number}} 已收到：{{title}}',
    },
    "complete_issue": {
        "en": 'Logged as issue {{idea_number}}\n{{title}}',
        "ms": 'Direkodkan sebagai isu {{idea_number}}\n{{title}}',
        "zh": '已记录为问题 {{idea_number}}\n{{title}}',
    },
    "type_refused": {
        "en": "I couldn't file this: the Ideas workspace doesn't take this type yet.",
        "ms": 'Saya tidak dapat menghantar ini: ruang kerja Idea belum menerima jenis ini.',
        "zh": '我无法提交这个：创意工作区暂时不接受此类型。',
    },
    "error": {
        "en": "Sorry, I couldn't save that idea just now. Please try again in a moment.",
        "ms": 'Maaf, saya tidak dapat menyimpan idea itu sekarang. Sila cuba lagi sebentar nanti.',
        "zh": '抱歉，我暂时无法保存这个创意，请稍后再试。',
    },
    "config_error": {
        "en": "Idea capture isn't set up correctly here, so I couldn't save that. Please let your Sorento contact know.",
        "ms": 'Penangkapan idea tidak disediakan dengan betul di sini, jadi saya tidak dapat menyimpannya. Sila maklumkan kepada wakil Sorento anda.',
        "zh": '此处的创意收集设置不正确，所以我无法保存。请告知您的 Sorento 联系人。',
    },
}


def _publish_key(session: Session, short: str, stock: str) -> None:
    registry_key, new_text, tokens = CHATBOT_REPLY_COPY[short]
    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == registry_key, AIPromptLabel.label == "production")
        .first()
    )
    if label is None:
        return
    current = session.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).first()
    if current is None:
        return
    text = (current.template or "").strip()
    if text == new_text.strip():
        return  # already published
    if text != stock.strip():
        logger.warning(
            "prompt %s version %s is customised; leaving it, the feedback text is not published",
            registry_key,
            current.version,
        )
        return
    row = _ensure_version(session, registry_key, _max_version(session, registry_key) + 1, new_text, list(tokens))
    _set_label(session, registry_key, "production", row.id)


def publish(session: Session) -> None:
    """Publish every changed key in every language on `session` (the caller commits)."""
    for name, texts in STOCK.items():
        for lang in FALLBACK_LANGUAGES:
            _publish_key(session, f"ideation_capture_{name}{language_suffix(lang)}", texts[lang])
