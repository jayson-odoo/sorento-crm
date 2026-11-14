"""WA-COMPLAINT-INTAKE round 15 red tests: the copy publish ("idea" becomes "feedback").

Contract: documentation/plans/chatbot/COPY-wa-feedback-rename.md, "How it ships". `seed_prompt_registry` is
insert-only, so a seeded install keeps the old text. A publish adds each new text as the next version and moves
that key's `production` label ONLY where production still equals the stock text it replaces (strip-normalised);
an owner-edited text is left alone; a re-run is a no-op.

ASSUMPTION (the migration's file name is not known yet): the publish lives in core as
`app.services.ideation_copy_rename.publish(session)`, called by the round's migration after
`seed_prompt_registry`. These tests drive that function on a blank Postgres schema.

The "stock" texts below are the ones shipped before this round (an install seeded before it holds them on
`production`); the expected texts are the contract table (tests/test_wa_feedback_rename.py TABLE).
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401,E402  (first app import: resolves a circular import)

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from tests._pg_fixture import blank_session
from tests.test_wa_feedback_rename import TABLE

#: short copy name -> language -> the text shipped before this round.
STOCK = {
    "no_access": {
        "en": (
            "You need a CRM login with Ideas access to submit ideas here. Please ask your "
            "Sorento contact for one."
        ),
        "ms": (
            "Anda perlukan log masuk CRM dengan akses Idea untuk menghantar idea di sini. "
            "Sila minta daripada orang perhubungan Sorento anda."
        ),
        "zh": "您需要拥有 Ideas 权限的 CRM 登录账号，才能在这里提交创意。请向您的 Sorento 联系人申请。",
    },
    "complete_issue": {
        "en": "Logged as issue {{idea_number}}\n{{title}}",
        "ms": "Direkodkan sebagai isu {{idea_number}}\n{{title}}",
        "zh": "已记录为问题 {{idea_number}}\n{{title}}",
    },
    "similar_offered_see_all": {
        "en": "See all your ideas: {{link}}",
        "ms": "Lihat semua idea anda: {{link}}",
        "zh": "查看您的全部创意：{{link}}",
    },
}
EDITED_KEY = "chatbot_reply_ideation_capture_error"
EDITED_TEXT = "OWNER EDITED: sorry, that did not save. Try again soon."


def _key(name: str, lang: str) -> str:
    return f"chatbot_reply_ideation_capture_{name}" + ("" if lang == "en" else f".{lang}")


CASES = [(name, lang) for name in STOCK for lang in ("en", "ms", "zh")]


@pytest.fixture
def db():
    with blank_session() as session:
        try:
            ai_prompt_registry.bust_cache()
            yield session
        finally:
            ai_prompt_registry.bust_cache()


def _production(db, name: str):
    db.expire_all()
    label = db.query(AIPromptLabel).filter(AIPromptLabel.name == name, AIPromptLabel.label == "production").one()
    return db.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).one()


def _versions(db, name: str) -> list[int]:
    db.expire_all()
    rows = db.query(AIPromptVersion).filter(AIPromptVersion.name == name).order_by(AIPromptVersion.version).all()
    return [v.version for v in rows]


def _set_production_text(db, name: str, text: str) -> None:
    """The production version's template, as an install seeded before this round (or edited by the owner)."""
    current = _production(db, name)
    current.template = text
    db.flush()


def _seeded_install(db) -> None:
    from app.services.ai_prompt_seed import seed_prompt_registry

    seed_prompt_registry(db.connection())
    for name, lang in CASES:
        _set_production_text(db, _key(name, lang), STOCK[name][lang])
    _set_production_text(db, EDITED_KEY, EDITED_TEXT)


def _publish(db) -> None:
    from app.services.ideation_copy_rename import publish

    publish(db)
    db.flush()


@pytest.mark.parametrize("name, lang", CASES)
def test_publish_moves_a_stock_production_to_a_new_version_with_the_table_text(db, name, lang):
    _seeded_install(db)
    key = _key(name, lang)
    before = _versions(db, key)
    _publish(db)
    after = _versions(db, key)
    assert after == before + [max(before) + 1], (before, after)
    current = _production(db, key)
    assert current.version == max(after)
    assert current.template == TABLE[name][lang]


def test_publish_counts_a_whitespace_only_difference_as_stock(db):
    from app.services.ai_prompt_seed import seed_prompt_registry

    seed_prompt_registry(db.connection())
    key = _key("no_access", "en")
    _set_production_text(db, key, "\n" + STOCK["no_access"]["en"] + "  \n")
    _publish(db)
    assert _production(db, key).template == TABLE["no_access"]["en"]


def test_an_owner_edited_production_keeps_its_label(db):
    _seeded_install(db)
    before_versions = _versions(db, EDITED_KEY)
    before = _production(db, EDITED_KEY)
    _publish(db)
    after = _production(db, EDITED_KEY)
    assert after.id == before.id
    assert after.template == EDITED_TEXT
    assert _versions(db, EDITED_KEY) == before_versions


def test_a_second_publish_adds_no_version(db):
    _seeded_install(db)
    _publish(db)
    keys = [_key(name, lang) for name, lang in CASES] + [EDITED_KEY]
    once = {key: (_versions(db, key), _production(db, key).id) for key in keys}
    _publish(db)
    twice = {key: (_versions(db, key), _production(db, key).id) for key in keys}
    assert twice == once
