"""NO-SORRY-COPY (owner rule, 30 Oct 2026): the bot never says sorry or busy.

A guard on the reply COPY, not a runtime word list: every sentence the bot can send from
the canned reply table, the language catalogue (keys and MS / ZH translations) and the
named refusal lines is checked for sorry / maaf / 抱歉 / 对不起 / busy, case-insensitive.
`IDEATION_CAPTURE_ERROR` is AGENTIC-IDEATE's (#2038, owner ruling 31 Oct) and is skipped
until that lane rewrites it.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from app.api.v1.sales import analysis
from app.services import chatbot_reply_copy, contact_customer_scope, sales_report_delivered
from app.services.chatbot import console_service, do_ask, label_catalog

BANNED = re.compile(r"sorry|maaf|抱歉|对不起|busy", re.IGNORECASE)

#: Owned by another lane (see module docstring). Remove once #2038 merges.
#: By identity, so its expanded registry entries (`ideation_capture_error.ms`...) are skipped
#: too and an equal string anywhere else would still be caught.
SKIPPED = {id(chatbot_reply_copy.IDEATION_CAPTURE_ERROR)} | {
    id(text) for text in chatbot_reply_copy.IDEATION_CAPTURE_ERROR.values()
}


def _strings(value, path: str):
    if id(value) in SKIPPED:
        return
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key, f"{path}[key]")
            yield from _strings(item, f"{path}[{key!r}]")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for i, item in enumerate(value):
            yield from _strings(item, f"{path}[{i}]")


def _module_strings(module: ModuleType):
    for name, value in vars(module).items():
        if name.startswith("__") or isinstance(value, ModuleType) or callable(value):
            continue
        yield from _strings(value, f"{module.__name__}.{name}")


def _offenders(pairs):
    return [(where, text) for where, text in pairs if BANNED.search(text)]


@pytest.mark.parametrize("module", [chatbot_reply_copy, label_catalog], ids=lambda m: m.__name__)
def test_reply_copy_module_has_no_sorry_or_busy(module: ModuleType) -> None:
    assert _offenders(_module_strings(module)) == []


def test_named_reply_lines_have_no_sorry_or_busy() -> None:
    lines = {
        "analysis.REFUSAL": analysis.REFUSAL,
        "do_ask.TRANSPORTER_REFUSED": do_ask.TRANSPORTER_REFUSED,
        "console_service.AGENT_BUSY_REPLY": console_service.AGENT_BUSY_REPLY,
        "sales_report_delivered.refusal_message": sales_report_delivered.refusal_message("REPAIR"),
        "contact_customer_scope._refusal_for": contact_customer_scope._refusal_for([]),
    }
    assert _offenders(lines.items()) == []


def test_mcp_top_selling_refusal_has_no_sorry() -> None:
    """The MCP presenter repeats the analysis route's refusal; read it from source so this
    test does not need the MCP package installed in the backend venv."""
    path = Path(__file__).resolve().parents[3] / "sorento_crm_mcp" / "sorento_crm_mcp" / "presenters.py"
    if not path.exists():  # pragma: no cover - backend-only checkout
        pytest.skip("MCP package not in this checkout")
    line = next(
        ln for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.startswith("TOP_SELLING_REFUSED_OTHER_CUSTOMER")
    )
    assert not BANNED.search(line), line
    assert analysis.REFUSAL in line


def test_guard_catches_each_banned_word() -> None:
    """Kill test for the guard itself: each banned word, in any case, is caught."""
    for text in ("SORRY, no.", "Maaf, tiada.", "抱歉，没有。", "对不起", "I am Busy"):
        assert BANNED.search(text), text


def test_escalate_offer_keeps_the_accepted_offer_prefix() -> None:
    """`output_exchange` recognises an accepted offer by this phrase in the bot's own reply
    (module docstring of `chatbot_reply_copy`): the rewrite must not lose it."""
    for text in (
        chatbot_reply_copy.CHATBOT_REPLY_ESCALATE_OFFER,
        chatbot_reply_copy.CHATBOT_REPLY_ESCALATE_OFFER_NO_TEAM,
    ):
        assert re.search(r"would you like me to escalate", text, re.IGNORECASE), text


def test_every_rewritten_registry_line_has_its_translations() -> None:
    """The four registry lines are translated by exact English text: the catalogue must
    carry the NEW text with MS and ZH, or a Malay or Chinese contact reads English."""
    for text in (
        chatbot_reply_copy.CHATBOT_REPLY_NOT_SUPPORTED,
        chatbot_reply_copy.CHATBOT_REPLY_ESCALATE_OFFER,
        chatbot_reply_copy.CHATBOT_REPLY_ESCALATE_OFFER_NO_TEAM,
        chatbot_reply_copy.CHATBOT_REPLY_ACCESS_DENIED,
        chatbot_reply_copy.CHATBOT_TURN_ERROR_REPLY,
    ):
        key = text.replace("{{team}}", "{team}")
        assert key in label_catalog.INLINE, key
        assert set(label_catalog.LABELS[key]) >= {"ms", "zh"}, key


# --------------------------------------------------------------------------- #
# The migration that publishes the four registry lines.
# --------------------------------------------------------------------------- #

def _load_migration():
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "nosorry_0001_reply_copy.py"
    spec = importlib.util.spec_from_file_location("migration_under_test_nosorry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_text(session, name: str) -> str:
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == "production")
        .one()
    )
    return session.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).one().template


def test_migration_publishes_old_defaults_and_keeps_owner_edits() -> None:
    from app.models.ai_prompt import AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS
    from app.services.ai_prompt_seed import seed_prompt_registry
    from tests._pg_fixture import blank_session

    module = _load_migration()
    edited = "chatbot_reply_access_denied"
    owner_text = "You can't reach {{team}} from this number."
    with blank_session() as session:
        # Prod shape: v1 of every reworded key holds the OLD default, except one key the
        # owner already reworded in Settings > AI Prompts.
        for name, old in module.OLD_DEFAULTS.items():
            session.add(
                AIPromptVersion(
                    name=name, version=1, type="text",
                    template=owner_text if name == edited else old,
                    variables=list(PROMPT_KEYS[name].variables),
                )
            )
        session.commit()
        seed_prompt_registry(session.get_bind())

        module.upgrade.__globals__["op"] = type("Op", (), {"get_bind": staticmethod(session.get_bind)})
        module.upgrade()
        session.expire_all()

        for name in module.OLD_DEFAULTS:
            text = _production_text(session, name)
            if name == edited:
                assert text == owner_text
            else:
                assert text == PROMPT_KEYS[name].fallback()
                assert not BANNED.search(text), text

        # Idempotent: a second run publishes nothing more.
        count = session.query(AIPromptVersion).count()
        module.upgrade()
        assert session.query(AIPromptVersion).count() == count
