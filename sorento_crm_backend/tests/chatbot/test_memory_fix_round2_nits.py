"""Nits of the reviewer pass on PR #1304 at d89110c0 that are not covered elsewhere:
N2 (the About layer keeps Chinese readable) and N11 (a respond.io id shared across
workspaces degrades memory at intake, as the staff GET already refuses it).

Postgres only (`tests/chatbot/conftest.py::session_factory`).
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn import context


def test_n2_about_keeps_chinese_unescaped() -> None:
    layers = context.ContextLayers(
        level="full",
        profile_facts=[{"key": "about", "value": ["做水电工程"]}, {"key": "project", "value": "吉隆坡公寓"}],
        summaries=[],
        earlier_messages=[],
        previous_response="",
        current_subject=None,
        pending_kind=None,
        pending_options=[],
        settings_profile_line=None,
        current_message="hi",
        reply_to=None,
        media_line=None,
    )
    text_out, _report = context.assemble(layers)
    assert "做水电工程" in text_out and "吉隆坡公寓" in text_out, text_out
    assert "\\u" not in text_out, text_out


def test_n11_a_respond_id_shared_across_workspaces_degrades_memory(session_factory, monkeypatch) -> None:
    # This workspace's space: the NULL-workspace row resolves, the other workspace's
    # namesake shares its respond.io id.
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
    cid = f"ZZT-r2-n11-{uuid.uuid4().hex[:8]}"
    db = session_factory()
    other_workspace = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext) "
            "VALUES (:w, 'ZZT-other-space', 'ZZT other', 'x')"
        ),
        {"w": other_workspace},
    )
    for workspace in (None, other_workspace):
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id, "
                "chatbot_memory_level) VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :w, 'full')"
            ),
            {"cid": cid, "phone": f"+6011{uuid.uuid4().hex[:8]}", "sv": json.dumps({}), "w": workspace},
        )
    db.commit()

    intake = engine_mod._memory_intake(db, contact_respond_id=cid, dry_run=False)

    assert intake["contact_pk"] is None, intake
    assert intake["effective_level"] == "off", intake
    assert intake["degraded_reason"] == "respond_id_shared", intake
