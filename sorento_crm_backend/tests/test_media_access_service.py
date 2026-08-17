"""Effective media-limit resolution (PLAN-chatbot-media-endpoint, slice S1).

Contract under test: ``app.services.media_access_service``

    resolve_effective_limit(db, contact_id: str, modality: str) -> int
        The monthly limit that actually applies right now: the contact's own
        override when one is set, otherwise the system default for that
        modality. Answers independently of whether the modality is currently
        *allowed* -- a not-yet-configured contact still has an effective
        limit, it just has no row granting access to spend against it (see
        the FE contract docblock's `effective_monthly_limit: 50` on a
        `has_row: false` item).

    resolve_media_settings(db) -> MediaSettings
        Reads the `system_settings` singleton's `media_*` columns, falling
        back to the plan's hardcoded defaults (S1 UAC section 2.4 of the
        plan) when no row exists at all -- never a stale cache, so a changed
        default takes effect on the very next call (UAC S1-09 / S1-07's
        "without a deploy").

Models under test: ``app.models.media.ContactMediaLimit`` (table
``contact_media_limit``, PK `(contact_id, modality)`, absence of a row means
denied by construction -- see PLAN section 2.2).

AC ids covered: S1-07, S1-09.

All tests run against a blank Postgres schema (tests/_pg_fixture.blank_session)
because `system_settings` is a real production singleton on the live DB and
must not be touched by a test; a blank schema starts with zero rows so
"no system_settings row" and "no contact_media_limit row" are both exercised
honestly rather than assumed.
"""
from __future__ import annotations

import uuid

from tests._pg_fixture import blank_session


def _contact(db, marker: str):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+1555{marker}",
        name=f"ZZT contact {marker}",
    )
    db.add(contact)
    db.flush()
    return contact


def _system_setting_row(db, **media_overrides):
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), name="ZZT Settings")
    for key, value in media_overrides.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# S1-09 -- no row, NULL-limit row, override row, changed default              #
# --------------------------------------------------------------------------- #


def test_no_contact_media_limit_row_resolves_to_the_system_default():
    """S1-09: absence of a `contact_media_limit` row still resolves an
    effective limit (the system default) -- resolution is independent of the
    gate flag, matching the FE contract's `has_row:false, effective_monthly_limit:50`.
    """
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        _system_setting_row(db, media_image_monthly_limit=50)
        contact = _contact(db, "noro w")

        effective = resolve_effective_limit(db, contact.id, "image")

        assert effective == 50


def test_row_with_null_limit_inherits_the_system_default():
    """S1-09: a row exists (access granted) but carries no override -- NULL
    `monthly_limit` means inherit, not zero."""
    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        _system_setting_row(db, media_image_monthly_limit=50)
        contact = _contact(db, "nullrow")
        db.add(
            ContactMediaLimit(
                contact_id=contact.id,
                modality="image",
                is_allowed=True,
                monthly_limit=None,
            )
        )
        db.flush()

        effective = resolve_effective_limit(db, contact.id, "image")

        assert effective == 50


def test_row_with_an_override_wins_over_the_system_default():
    """S1-09 / S1-07: a per-contact override sits on top of the default."""
    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        _system_setting_row(db, media_image_monthly_limit=50)
        contact = _contact(db, "override")
        db.add(
            ContactMediaLimit(
                contact_id=contact.id,
                modality="image",
                is_allowed=True,
                monthly_limit=200,
            )
        )
        db.flush()

        effective = resolve_effective_limit(db, contact.id, "image")

        assert effective == 200


def test_changed_system_default_takes_effect_without_a_restart():
    """S1-09: no caching -- the very next call reflects a changed default."""
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        setting = _system_setting_row(db, media_image_monthly_limit=50)
        contact = _contact(db, "livedef")

        before = resolve_effective_limit(db, contact.id, "image")

        setting.media_image_monthly_limit = 90
        db.flush()

        after = resolve_effective_limit(db, contact.id, "image")

        assert before == 50
        assert after == 90


def test_voice_modality_resolves_against_its_own_default_column():
    """A voice lookup must not silently read the image default column."""
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        _system_setting_row(
            db, media_image_monthly_limit=50, media_voice_monthly_limit=100
        )
        contact = _contact(db, "voicedef")

        assert resolve_effective_limit(db, contact.id, "image") == 50
        assert resolve_effective_limit(db, contact.id, "voice") == 100


def test_no_system_settings_row_at_all_falls_back_to_the_plan_default():
    """A blank install (no `system_settings` row) must not error -- it uses
    the plan's hardcoded default (50 for image, PLAN section 2.4)."""
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        contact = _contact(db, "nosettingsrow")

        assert resolve_effective_limit(db, contact.id, "image") == 50


# --------------------------------------------------------------------------- #
# S1-07 -- overrides are per contact; every other contact stays on default;   #
# clearing an override returns to the default without a deploy                #
# --------------------------------------------------------------------------- #


def test_override_is_scoped_to_its_own_contact_only():
    """S1-07: a 200 override on one contact must not leak to another."""
    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        _system_setting_row(db, media_image_monthly_limit=50)
        overridden = _contact(db, "ovr-a")
        plain = _contact(db, "ovr-b")
        db.add(
            ContactMediaLimit(
                contact_id=overridden.id,
                modality="image",
                is_allowed=True,
                monthly_limit=200,
            )
        )
        db.flush()

        assert resolve_effective_limit(db, overridden.id, "image") == 200
        assert resolve_effective_limit(db, plain.id, "image") == 50


def test_clearing_the_override_returns_to_the_default():
    """S1-07: setting `monthly_limit` back to NULL un-overrides, live."""
    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import resolve_effective_limit

    with blank_session() as db:
        _system_setting_row(db, media_image_monthly_limit=50)
        contact = _contact(db, "clearovr")
        row = ContactMediaLimit(
            contact_id=contact.id,
            modality="image",
            is_allowed=True,
            monthly_limit=200,
        )
        db.add(row)
        db.flush()
        assert resolve_effective_limit(db, contact.id, "image") == 200

        row.monthly_limit = None
        db.flush()

        assert resolve_effective_limit(db, contact.id, "image") == 50


# --------------------------------------------------------------------------- #
# The degraded tier is resolved per modality (PLAN 16.1)                      #
# --------------------------------------------------------------------------- #


def test_degraded_model_is_resolved_per_modality_never_shared():
    """One shared column meant the image tier decided what happened to a voice
    note. They are separate quotas with separate ledger counts, so they get
    separate degraded models - and voice's ships NULL because no cheaper
    transcription model has been measured."""
    from app.services.media_access_service import resolve_media_settings

    with blank_session() as db:
        _system_setting_row(
            db,
            media_image_degraded_model="gpt-4o-mini",
            media_voice_degraded_model=None,
        )
        settings = resolve_media_settings(db)

        assert settings.degraded_model_for("image") == "gpt-4o-mini"
        assert settings.degraded_model_for("voice") is None


def test_degraded_model_for_voice_reads_its_own_column_once_it_is_named():
    from app.services.media_access_service import resolve_media_settings

    with blank_session() as db:
        _system_setting_row(db, media_voice_degraded_model="whisper-cheap")
        settings = resolve_media_settings(db)

        assert settings.degraded_model_for("voice") == "whisper-cheap"
        # Naming a voice tier must not invent an image one.
        assert settings.degraded_model_for("image") is None


def test_no_system_settings_row_means_no_degraded_tier_for_either_modality():
    """A blank install refuses at the quota rather than degrading, which is the
    behaviour PLAN 3.2 specifies for an unconfigured degraded tier."""
    from app.services.media_access_service import resolve_media_settings

    with blank_session() as db:
        settings = resolve_media_settings(db)

        assert settings.degraded_model_for("image") is None
        assert settings.degraded_model_for("voice") is None


# --------------------------------------------------------------------------- #
# upsert_access is a single INSERT ... ON CONFLICT DO UPDATE                   #
# --------------------------------------------------------------------------- #


def test_upsert_access_a_second_save_updates_the_same_row_in_place():
    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import upsert_access

    with blank_session() as db:
        _system_setting_row(db, media_image_monthly_limit=50)
        contact = _contact(db, "upsert2")

        first = upsert_access(
            db, contact.id, "image", is_allowed=True, monthly_limit=10, max_clip_seconds=None
        )
        second = upsert_access(
            db, contact.id, "image", is_allowed=False, monthly_limit=None, max_clip_seconds=None
        )

        rows = (
            db.query(ContactMediaLimit)
            .filter(ContactMediaLimit.contact_id == contact.id)
            .all()
        )
        assert len(rows) == 1
        assert first["is_allowed"] is True and first["effective_monthly_limit"] == 10
        assert second["is_allowed"] is False and second["effective_monthly_limit"] == 50


def test_upsert_access_ignores_a_clip_override_for_the_image_modality():
    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import upsert_access

    with blank_session() as db:
        contact = _contact(db, "upsertclip")

        upsert_access(
            db, contact.id, "image", is_allowed=True, monthly_limit=None, max_clip_seconds=30
        )

        row = (
            db.query(ContactMediaLimit)
            .filter(ContactMediaLimit.contact_id == contact.id)
            .one()
        )
        assert row.max_clip_seconds is None


def test_upsert_access_survives_a_row_inserted_underneath_it():
    """Two operators saving a never-configured contact at once: the second save
    must land as an update of the first's row, never a unique-violation 500."""
    from sqlalchemy import text

    from app.models.media import ContactMediaLimit
    from app.services.media_access_service import upsert_access

    with blank_session() as db:
        contact = _contact(db, "upsertrace")
        # The other operator's row appears between "is there a row?" and the write:
        # inserted with raw SQL so this session's identity map knows nothing of it.
        db.execute(
            text(
                "INSERT INTO contact_media_limit "
                "(id, contact_id, modality, is_allowed, monthly_limit) "
                "VALUES (:id, :contact_id, 'image', true, 7)"
            ),
            {"id": str(uuid.uuid4()), "contact_id": contact.id},
        )

        item = upsert_access(
            db, contact.id, "image", is_allowed=False, monthly_limit=99, max_clip_seconds=None
        )

        rows = (
            db.query(ContactMediaLimit)
            .filter(ContactMediaLimit.contact_id == contact.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].is_allowed is False
        assert rows[0].monthly_limit == 99
        assert item["is_allowed"] is False
        assert item["effective_monthly_limit"] == 99
