"""The PDPA collection notice, as configurable versioned data (fork 6, hard gate on S3).

Fork 6 was answered on 2026-07-31: consent is collected for **warranty and service only**,
erasure anonymises the person and retains the purchase, and PDPA 2010 s.7(2) requires the
collection notice in **Bahasa Malaysia AND English**. What was never built is the notice
itself, and S2b shipped the hole in a visible way:

    CONSENT_NOTICE_VERSION = "2026-08-BM-EN-DRAFT"   # consumer_service.py

Every `consumer_profiles` row already stamps that string into `consent_notice_version`. It
points at nothing. "Which wording did this person actually see" - the one question a consent
record exists to answer - is currently unanswerable, and would stay unanswerable for every
profile created before somebody wrote the text.

Five things shape this suite.

1. **A published notice is IMMUTABLE.** The record has to survive the question "prove what
   this person agreed to, eighteen months ago". Editing text in place destroys exactly that,
   and it destroys it silently and retroactively for everyone who already accepted. Editing
   means publishing a NEW version; the old row is never touched.

2. **Both languages or it does not publish.** s.7(2) is not satisfied by an English notice
   with a Malay column left for later, and a nullable column is how "later" becomes "never".
   The guard is at publish time rather than insert time so a draft can be worked on.

3. **The version a profile stamps must RESOLVE.** The stamp is the whole point of the column.
   A test that only checks a notice exists would pass while `consumer_service` kept writing
   its hardcoded literal, so the resolution is asserted end to end: create a profile, read its
   stamp back, and find the exact text through it.

4. **The stamp has to FIT.** `consumer_profiles.consent_notice_version` is `VARCHAR(32)`
   (S2b), so the identifier format is part of the contract, not a formatting preference. A
   longer scheme would truncate or raise, per-row, at intake.

5. **The purpose is a closed set and belongs on the NOTICE.** A notice is wording plus the
   lawful basis it establishes; letting a notice declare `marketing` would prop open the
   one-way door fork 6 deliberately closed - service-only consent cannot later be used for
   broadcasting without fresh consent from each person.

Decisions taken here because nobody has ruled them, asserted so the next reader inherits an
answer rather than a coin flip:

- **The portal reads the notice unauthenticated.** A consumer must be able to read what they
  are agreeing to BEFORE identifying themselves. Requiring auth to see a privacy notice is a
  contradiction.
- **Seeding is idempotent and never rewrites a published version.** A deploy that re-ran the
  seeder and changed published wording would be the immutability bug with extra steps.

Run: venv/bin/python -m pytest tests/test_consent_notice_registry.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from ._pg_fixture import blank_session  # noqa: E402

# ---------------------------------------------------------------- the contract

REGISTRY_MODULE = "app.services.consent_notice_service"

# The notice shown at consumer intake. A key, not a single global row: the technician
# portal and any future dealer portal collect different data for different purposes and
# will each need their own wording.
INTAKE_KEY = "consumer_intake"

# Fork 6's closed set. `marketing` is deliberately absent.
PURPOSE = "warranty_service"

# AC-L4 / S2b: consumer_profiles.consent_notice_version is VARCHAR(32).
MAX_STAMP = 32


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _registry():
    if importlib.util.find_spec(REGISTRY_MODULE) is None:
        raise AssertionError(
            f"{REGISTRY_MODULE} does not exist. The PDPA notice is configurable data with "
            "versions, not a constant in consumer_service - which is what it is today, and "
            "it points at no text at all."
        )
    return importlib.import_module(REGISTRY_MODULE)


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _publish(db, **overrides):
    reg = _registry()
    create = _fn(reg, "create_notice", "(db, *, notice_key, purpose, body_en, body_ms, ...)")
    payload = {
        "notice_key": INTAKE_KEY,
        "purpose": PURPOSE,
        "body_en": overrides.pop("body_en", "English collection notice."),
        "body_ms": overrides.pop("body_ms", "Notis pengumpulan dalam Bahasa Malaysia."),
    }
    payload.update(overrides)
    notice = create(db, **payload)
    publish = _fn(reg, "publish_notice", "(db, notice_id)")
    return publish(db, str(notice.id))


# =========================================================== the seeded notice


def test_the_intake_notice_is_seeded_and_published(db):
    """The gate fork 6 named. Without a published notice the portal has nothing lawful
    to show, and S3 cannot collect a name.
    """
    reg = _registry()
    seed = _fn(reg, "seed_consent_notices", "(db)")
    seed(db)
    current = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    assert current is not None, "seed_consent_notices must publish the consumer intake notice."
    assert current.purpose == PURPOSE


def test_the_seeded_notice_carries_real_text_in_both_languages(db):
    """s.7(2) is a build requirement, not a docstring.

    Length floors rather than exact strings: the wording will be revised by somebody who
    writes Malay properly, and a test pinned to today's sentence would fail on the day it
    is corrected. What must never change is that BOTH are substantial.
    """
    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)
    current = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    assert len(current.body_en.strip()) > 200, "The English notice is a placeholder."
    assert len(current.body_ms.strip()) > 200, "The Malay notice is a placeholder."
    lowered = current.body_ms.lower()
    assert any(word in lowered for word in ("peribadi", "maklumat")), (
        "The Malay body does not read as Malay. A copy of the English text in the Malay "
        "column satisfies the column and not the statute."
    )


def test_seeding_twice_changes_nothing(db):
    """A deploy re-running the seeder must not rewrite published wording - that is the
    immutability bug wearing a different hat.
    """
    reg = _registry()
    seed = _fn(reg, "seed_consent_notices", "(db)")
    seed(db)
    first = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    before = (first.version, first.body_en, first.body_ms)
    seed(db)
    again = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    assert (again.version, again.body_en, again.body_ms) == before


# =========================================================== immutability


def test_a_published_notice_cannot_be_edited(db):
    """"Prove what this person agreed to" is the only job this record has."""
    reg = _registry()
    published = _publish(db)
    update = getattr(reg, "update_notice", None)
    if update is None:
        pytest.skip("No update entry point exists, which satisfies immutability by absence.")
    with pytest.raises(Exception) as exc:
        update(db, str(published.id), body_en="rewritten after the fact")
    assert "publish" in str(exc.value).lower() or "immutable" in str(exc.value).lower()


def test_editing_means_a_new_version_and_the_old_text_survives(db):
    """The old row is the evidence for everyone who accepted it. It stays readable."""
    reg = _registry()
    first = _publish(db, body_en="First English text.", body_ms="Teks Bahasa Malaysia pertama.")
    second = _publish(db, body_en="Second English text.", body_ms="Teks Bahasa Malaysia kedua.")

    assert second.version == first.version + 1
    current = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    assert current.version == second.version

    by_stamp = _fn(reg, "notice_for_stamp", "(db, stamp)")
    old = by_stamp(db, _fn(reg, "stamp_for", "(notice)")(first))
    assert old is not None and old.body_en == "First English text.", (
        "A consumer who accepted v1 must still be able to be shown v1."
    )


# =========================================================== the publish guard


def test_publishing_without_malay_is_refused(db):
    """s.7(2). A notice in English only is not a notice."""
    reg = _registry()
    create = _fn(reg, "create_notice", "(db, ...)")
    draft = create(
        db,
        notice_key=INTAKE_KEY,
        purpose=PURPOSE,
        body_en="A perfectly good English notice that is long enough to look finished.",
        body_ms="",
    )
    with pytest.raises(Exception) as exc:
        _fn(reg, "publish_notice", "(db, notice_id)")(db, str(draft.id))
    message = str(exc.value).lower()
    assert "malay" in message or "bahasa" in message or "body_ms" in message


def test_publishing_without_english_is_refused(db):
    reg = _registry()
    draft = _fn(reg, "create_notice", "(db, ...)")(
        db,
        notice_key=INTAKE_KEY,
        purpose=PURPOSE,
        body_en="   ",
        body_ms="Notis pengumpulan maklumat peribadi yang cukup panjang untuk kelihatan siap.",
    )
    with pytest.raises(Exception):
        _fn(reg, "publish_notice", "(db, notice_id)")(db, str(draft.id))


def test_a_purpose_outside_the_closed_set_is_refused(db):
    """Fork 6's one-way door, defended at the point wording is written.

    Service-only consent cannot later be used for broadcasting without fresh consent from
    each person, and re-contacting them to ask is itself arguably marketing. A notice that
    could declare `marketing` is how that door gets propped open.
    """
    reg = _registry()
    with pytest.raises(Exception) as exc:
        _fn(reg, "create_notice", "(db, ...)")(
            db,
            notice_key=INTAKE_KEY,
            purpose="marketing",
            body_en="English.",
            body_ms="Bahasa Malaysia.",
        )
    assert "purpose" in str(exc.value).lower()


def test_an_unpublished_draft_is_never_current(db):
    """A draft is work in progress. Serving it to a consumer would collect data under
    wording nobody approved.
    """
    reg = _registry()
    _publish(db, body_en="Published English.", body_ms="Bahasa Malaysia diterbitkan.")
    _fn(reg, "create_notice", "(db, ...)")(
        db,
        notice_key=INTAKE_KEY,
        purpose=PURPOSE,
        body_en="Draft that must not be served.",
        body_ms="Draf yang tidak boleh disajikan.",
    )
    current = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    assert current.body_en == "Published English."


# =========================================================== the stamp


def test_the_stamp_fits_the_column_it_is_written_into(db):
    """`consumer_profiles.consent_notice_version` is VARCHAR(32) (S2b).

    The identifier format is contract, not taste: a longer scheme truncates or raises per
    row, at intake, on the write that matters.
    """
    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)
    current = _fn(reg, "current_notice", "(db, notice_key)")(db, INTAKE_KEY)
    stamp = _fn(reg, "stamp_for", "(notice)")(current)
    assert isinstance(stamp, str) and stamp
    assert len(stamp) <= MAX_STAMP, f"Stamp {stamp!r} is {len(stamp)} chars, column holds {MAX_STAMP}."


def test_a_stamp_resolves_back_to_the_exact_wording(db):
    """The round trip is the feature. Everything else is bookkeeping."""
    reg = _registry()
    published = _publish(db, body_en="Round trip English.", body_ms="Perjalanan pergi balik.")
    stamp = _fn(reg, "stamp_for", "(notice)")(published)
    found = _fn(reg, "notice_for_stamp", "(db, stamp)")(db, stamp)
    assert found is not None and str(found.id) == str(published.id)


def test_an_unknown_stamp_resolves_to_nothing_rather_than_guessing(db):
    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)
    assert _fn(reg, "notice_for_stamp", "(db, stamp)")(db, "consumer_intake.v99") is None
    assert _fn(reg, "notice_for_stamp", "(db, stamp)")(db, "nonsense") is None


# =========================================================== the intake path


def test_consumer_intake_stamps_the_registry_version_not_a_literal(db):
    """Point 3: the assertion that catches the real failure.

    A suite that only proved a notice exists would stay green while `consumer_service` kept
    writing "2026-08-BM-EN-DRAFT" - a string that resolves to nothing - onto every profile.
    """
    from app.services import consumer_service

    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)

    literal = getattr(consumer_service, "CONSENT_NOTICE_VERSION", None)
    if literal is not None:
        assert _fn(reg, "notice_for_stamp", "(db, stamp)")(db, str(literal)) is not None, (
            f"consumer_service stamps {literal!r}, which resolves to no notice. The "
            "constant must come from the registry."
        )


def test_every_profile_stamp_in_the_database_resolves(db):
    """The migration's other half. Rows already carry the placeholder, so shipping a
    registry without backfilling them leaves the same unanswerable question, just with a
    table beside it now.
    """
    from sqlalchemy import text

    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)
    by_stamp = _fn(reg, "notice_for_stamp", "(db, stamp)")

    stamps = [
        row[0]
        for row in db.execute(
            text(
                "SELECT DISTINCT consent_notice_version FROM consumer_profiles "
                "WHERE consent_notice_version IS NOT NULL"
            )
        ).all()
    ]
    unresolved = [s for s in stamps if by_stamp(db, s) is None]
    assert not unresolved, f"Profile stamps resolving to no notice: {unresolved}"


def test_a_staff_created_profile_claims_no_notice(db):
    """The honest half of the fix, and it is not cosmetic.

    `ensure_profile` runs from staff screens and n8n contact events, where
    nobody is ever shown a notice. Stamping a version there asserts that a person read
    words that were never on their screen - which is precisely the lie this column exists
    to prevent, and it is worse than a blank because it looks like evidence.
    """
    from app.models.access import RespondContact
    from app.services import consumer_service

    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)

    contact = RespondContact(id="zzt-consent-contact", phone_number="+60123456789", name="ZZT")
    db.add(contact)
    db.flush()

    profile = consumer_service.ensure_profile(
        db, phone="+60123456789", full_name="ZZT Consumer", respond_contact_id=contact.id
    )
    assert profile.consent_purpose == PURPOSE, "The lawful basis is still recorded."
    assert profile.consent_notice_version is None, (
        "Nobody showed this person a notice, so nothing may claim they saw one."
    )
    assert profile.consent_recorded_at is None


def test_the_portal_path_stamps_the_published_notice(db):
    """And the other half: when a notice IS displayed, the stamp resolves to it."""
    from app.models.access import RespondContact
    from app.services import consumer_service

    reg = _registry()
    _fn(reg, "seed_consent_notices", "(db)")(db)

    contact = RespondContact(id="zzt-consent-contact-2", phone_number="+60129876543", name="ZZT2")
    db.add(contact)
    db.flush()
    profile = consumer_service.ensure_profile(
        db, phone="+60129876543", full_name="ZZT Consumer 2", respond_contact_id=contact.id
    )

    consumer_service.record_consent(db, profile)
    assert profile.consent_recorded_at is not None
    found = _fn(reg, "notice_for_stamp", "(db, stamp)")(db, profile.consent_notice_version)
    assert found is not None and found.is_published


def test_recording_consent_with_no_published_notice_fails_closed(db):
    """Collecting personal data with nothing lawful on screen is the failure s.7
    describes. Failing closed here is cheaper than finding it in an audit.
    """
    from app.models.access import RespondContact
    from app.services import consumer_service

    contact = RespondContact(id="zzt-consent-contact-3", phone_number="+60127654321", name="ZZT3")
    db.add(contact)
    db.flush()
    profile = consumer_service.ensure_profile(
        db, phone="+60127654321", full_name="ZZT Consumer 3", respond_contact_id=contact.id
    )
    with pytest.raises(Exception) as exc:
        consumer_service.record_consent(db, profile)
    assert "consent" in str(exc.value).lower()
