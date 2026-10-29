"""CHAT-CHANNEL-LOOKUPSET: the sales channel rows read their extra words from the `sales_channel_alias` lookup set.

Contract: `documentation/plans/chatbot/PLAN-chat-channel-lookupset.md`, UAC AC-CCL-1..5.
Rows come from the source (`reports.ask.SALES_CHANNELS`); the set only holds optional aliases keyed by those
values, read through `chatbot_prompt_vars._alias_words(db, "sales_channel_alias")` like `attachment_type_alias`.
The seeded words come from the migration itself (`chan_alias_0001_sales_channel`), so the owner's starter keywords
are what the shortlist is proven against. Postgres only, blank schema, no LLM.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.main  # noqa: F401  isort:skip
from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.services.chatbot.head import lookup_lists as ll
from app.services.reports.ask import SALES_CHANNELS
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "chan_alias_0001_sales_channel.py"
SET_KEY = "sales_channel_alias"


def _migrate(session_factory) -> None:
    spec = importlib.util.spec_from_file_location("chan_alias_0001_sales_channel", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = session_factory()
    with Operations.context(MigrationContext.configure(db.connection())):
        module.upgrade()
    db.commit()


def _seed_set(session_factory, words: dict[str, list[str]], *, set_active: bool = True, inactive: tuple[str, ...] = ()) -> None:
    db = session_factory()
    s = LookupSet(id=str(uuid.uuid4()), set_key=SET_KEY, name="Sales Channel Alias", is_active=set_active)
    db.add(s)
    db.flush()
    for i, (value, keywords) in enumerate(words.items()):
        o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=value, label=value.title(), sort_order=i,
                         is_active=value not in inactive)
        db.add(o)
        db.flush()
        db.add_all(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword=k) for k in keywords)
    db.commit()


def _channel_rows(session_factory) -> dict[str, tuple[str, ...]]:
    return {r.key: r.texts for r in ll.load_rows(scoped(session_factory)) if r.list_name == "sales_channel"}


def _channel_hits(message: str, session_factory) -> list[str]:
    rows = ll.load_rows(scoped(session_factory))
    return [h.row.key for h in ll.shortlist(message, rows, None).get("sales_channel", [])]


# ------------------------------------------------------------------------------------------------ AC-CCL-1 / 3
def test_seeded_keywords_reach_the_channel_rows(session_factory):
    _migrate(session_factory)
    rows = _channel_rows(session_factory)
    assert set(rows) == set(SALES_CHANNELS), rows
    assert rows["dealer"][0] == "dealer", rows
    assert {"retail", "retailer", "经销商", "零售", "peruncit"} <= set(rows["dealer"]), rows
    assert rows["project"][0] == "project" and "project team" in rows["project"], rows


def test_retail_words_in_any_language_shortlist_the_dealer_channel(session_factory):
    _migrate(session_factory)
    for message in ("retail sales last month", "零售 sales", "经销商 sales", "peruncit sales this year"):
        assert _channel_hits(message, session_factory)[:1] == ["dealer"], message


def test_project_team_shortlists_the_project_channel(session_factory):
    _migrate(session_factory)
    assert _channel_hits("project team sales last month", session_factory)[:1] == ["project"]


# ------------------------------------------------------------------------------------------------ AC-CCL-4
def test_a_keyword_the_owner_adds_later_is_read_with_no_code_change(session_factory):
    _seed_set(session_factory, {"dealer": ["zzkedai"]})
    assert "zzkedai" in _channel_rows(session_factory)["dealer"]
    assert _channel_hits("zzkedai sales", session_factory)[:1] == ["dealer"]


def test_an_option_outside_the_sales_channels_adds_no_channel(session_factory):
    _seed_set(session_factory, {"dealer": ["zzkedai"], "zzonline": ["zzwebshop"]})
    rows = _channel_rows(session_factory)
    assert set(rows) == set(SALES_CHANNELS), rows
    assert not any("zzwebshop" in texts for texts in rows.values()), rows


# ------------------------------------------------------------------------------------------------ AC-CCL-5
def test_an_inactive_option_contributes_no_words(session_factory):
    _seed_set(session_factory, {"dealer": ["zzkedai"], "project": ["zzprojek"]}, inactive=("project",))
    rows = _channel_rows(session_factory)
    assert "zzkedai" in rows["dealer"] and rows["project"] == ("project",), rows


def test_an_inactive_set_contributes_no_words(session_factory):
    _seed_set(session_factory, {"dealer": ["zzkedai"]}, set_active=False)
    assert _channel_rows(session_factory) == {ch: (ch,) for ch in SALES_CHANNELS}


def test_no_set_keeps_the_bare_channel_words(session_factory):
    assert _channel_rows(session_factory) == {ch: (ch,) for ch in SALES_CHANNELS}
