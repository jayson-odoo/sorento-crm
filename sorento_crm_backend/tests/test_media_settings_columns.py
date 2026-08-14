"""The chatbot-media settings columns reach the frontend, and refuse nonsense.

Contract: PLAN-chatbot-media-endpoint section 2.4 and section 16.1, plus the
repo's standing rule that a new `system_settings` column must appear in BOTH
manual dict builders - `SystemSettingUpdate` AND the hand-written `get_settings`
response dict. Schema inheritance alone drops it, and the symptom is a control
that always renders its default and never the saved value.

`media_voice_degraded_model` is the column section 16.1 adds. It ships NULL and
unseeded on purpose: image's two tiers were measured (section 14.1) and are
seeded by migration 358, voice's were not, and a NULL degraded model means the
quota is a hard refusal rather than a claimed degradation that did not happen.

`media_language_mode` is validated here because `language_strategy()` builds a
different transcription request per mode and treats anything unrecognised as
`pinned` - so an unconstrained typo would look like the setting had been ignored
rather than refused.

Postgres, never sqlite: the round trip is the point, and `system_settings` is a
real production singleton, so every test runs on a blank schema.
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.user_management.settings import (
    SystemSettingUpdate,
    _update_general_settings_impl,
    get_settings,
)
from app.models.user import SystemSetting
from tests._pg_fixture import blank_session


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        yield session


def test_voice_degraded_model_round_trips_through_the_update_builder(db: Session):
    db.add(SystemSetting(id="ss-media-1", name="ZZT Settings"))
    db.commit()

    _update_general_settings_impl(
        SystemSettingUpdate(media_voice_degraded_model="whisper-cheap"), db
    )

    row = db.query(SystemSetting).first()
    assert row.media_voice_degraded_model == "whisper-cheap"
    # And it can be cleared back to "no degraded tier", which is what makes the
    # hard refusal reachable again.
    _update_general_settings_impl(
        SystemSettingUpdate(media_voice_degraded_model=None), db
    )
    assert db.query(SystemSetting).first().media_voice_degraded_model is None


def test_voice_degraded_model_is_in_the_get_response_dict(db: Session):
    """The other manual builder. A column present in only one of the two is
    invisible to the frontend, which is a documented repeat failure here."""
    db.add(
        SystemSetting(
            id="ss-media-2",
            name="ZZT Settings",
            media_voice_degraded_model="whisper-cheap",
        )
    )
    db.commit()

    payload = asyncio.run(get_settings(current_user={"id": "zzt"}, db=db))
    settings = payload["settings"]

    assert "media_voice_degraded_model" in settings
    assert settings["media_voice_degraded_model"] == "whisper-cheap"
    # Its image counterpart is a separate field, not the same one read twice.
    assert "media_image_degraded_model" in settings


def test_voice_degraded_model_defaults_to_null_and_is_not_seeded(db: Session):
    """Section 16.1: image was measured and is seeded; voice was not, so it must
    arrive NULL rather than claiming a degradation nobody has measured."""
    db.add(SystemSetting(id="ss-media-3", name="ZZT Settings"))
    db.commit()

    row = db.query(SystemSetting).first()
    assert row.media_voice_degraded_model is None


@pytest.mark.parametrize("mode", ["pinned", "hints", "auto"])
def test_language_mode_accepts_each_allowed_value(mode: str):
    assert SystemSettingUpdate(media_language_mode=mode).media_language_mode == mode


@pytest.mark.parametrize("mode", ["klingon", "PINNED", "pinned ", ""])
def test_language_mode_rejects_anything_else(mode: str):
    """Free text here silently degraded to `pinned` inside
    `MediaSettings.language_strategy()`, so a typo read as "the setting was
    ignored" rather than "the value is not allowed"."""
    with pytest.raises(ValidationError):
        SystemSettingUpdate(media_language_mode=mode)
