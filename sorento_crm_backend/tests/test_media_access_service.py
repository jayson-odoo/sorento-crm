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
