"""POST /api/v1/external/media/process -- the synchronous fast path.

Contract: PLAN-chatbot-media-endpoint.md section 3 (`app/api/v1/external/media.py`,
mounted prefix "media", permission slug `integration.chatbot_media.process`) +
chatbot-media-endpoint-acceptance-criteria.md slice S2 (+ S1-05, which is the
same gate observed from this endpoint rather than from the service).

These tests exercise ONLY the "decide, meter, record" half (PLAN section 3.3,
steps 1-9) -- never the worker-side extraction. The route's own async wait
(`asyncio.wait_for(_await_job(job_id), timeout=...)`, PLAN 3.3b) is
short-circuited by monkeypatching `_await_job` to raise
`asyncio.TimeoutError` immediately, so every test here returns in
milliseconds regardless of `media_sync_wait_seconds` and never depends on a
real worker process. `status`/`result` content is therefore NOT asserted here
-- that is S3's job (tests/test_media_job_lifecycle.py). What IS asserted:
`decision`, `idempotent_replay`, `job_id` presence/absence, `tier`, `quota`,
`notices`, and the `contact_media_usage` ledger row PLAN 3.3 step 7 commits
BEFORE any waiting begins.

`enqueue_job` is monkeypatched to a no-op stub (same technique as
tests/test_customer_import_route.py::stub_queue) -- these tests must never
touch Redis/RQ.

Auth: `X-API-Key` -> `get_external_api_user`, permission
`integration.chatbot_media.process` via `require_external_permission`
(app/api/v1/external/permissions.py). Route behaviour is under test, so
`tests/_external_auth.external_permissions_granted` is used except in the
S2-11 auth-denial cases, which are the ONE place authorization itself is
under test.

AC ids covered: S1-05, S2-01, S2-02, S2-03, S2-04, S2-05, S2-06, S2-07,
S2-08, S2-09, S2-10, S2-11, S2-12.

Implementation seam required for S2-10 (`test_period_key_and_reset_label_...`):
"now" must be resolved through a module-level `_now_utc()` callable in BOTH
`app.services.media_access_service` and `app.api.v1.external.media` (even if
one simply re-exports the other), so the test can pin the instant instead of
sleeping until a real month boundary. `raising=False` on those two
`monkeypatch.setattr` calls means the test still runs (and still fails
honestly, on the `period_key` assertion) if the coder names the seam
differently -- but it will not do what this test intends until it matches.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_db, get_external_api_user
from app.main import app

from tests._external_auth import external_permissions_granted
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/external/media/process"


# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _contact(db, label: str):
    """A contact with a marker-prefixed, UUID-suffixed respond_io_id.

    The suffix matters beyond hygiene: burst limiting (S2-05) and the
    monthly-quota tests bucket by `respond_io_id` in Redis with a real TTL,
    so a fixed id would let a stray key from a previous run of the same test
    (or a rerun inside the same burst window) corrupt the count this test is
    asserting on.
    """
    from app.models.access import RespondContact

    unique = f"{label}-{uuid.uuid4().hex[:10]}"
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+1555{unique}",
        respond_io_id=f"ZZT-rio-{unique}",
        name=f"ZZT media-process {unique}",
    )
    db.add(contact)
    db.flush()
    return contact


def _allow(db, contact, modality: str, *, monthly_limit=None, max_clip_seconds=None):
    from app.models.media import ContactMediaLimit

    db.add(
        ContactMediaLimit(
            contact_id=contact.id,
            modality=modality,
            is_allowed=True,
            monthly_limit=monthly_limit,
            max_clip_seconds=max_clip_seconds,
        )
    )
    db.flush()


def _settings_row(db, **media_overrides):
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), name="ZZT Settings")
    for key, value in media_overrides.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


def _body(*, respond_io_id, message_id, modality="image", **extra):
    payload = {
        "respond_io_id": respond_io_id,
        "message_id": message_id,
        "modality": modality,
        "media_url": "https://cdn.respond.io/x.jpg",
        "mime_type": "image/jpeg",
        "caption": "check stock for these",
        "turn_id": "turn-1",
    }
    payload.update(extra)
    return payload


async def _instant_timeout(_job_id):
    raise asyncio.TimeoutError()


def _client(db, *, monkeypatch, api_user=None) -> TestClient:
    def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override
    if api_user is not None:
        app.dependency_overrides[get_external_api_user] = lambda: api_user

    # PLAN 3.3b: short-circuit the wait so every test returns instantly and
    # never depends on a worker actually running.
    monkeypatch.setattr(
        "app.api.v1.external.media._await_job", _instant_timeout
    )
    # No test here may reach Redis/RQ.
    monkeypatch.setattr(
        "app.api.v1.external.media.enqueue_job",
        lambda *a, **kw: MagicMock(id=str(uuid.uuid4())),
    )
    return TestClient(app)


def _usage_rows(db, respond_io_id):
    from app.models.media import ContactMediaUsage

    return (
        db.query(ContactMediaUsage)
        .filter(ContactMediaUsage.respond_io_id == respond_io_id)
        .all()
    )


# --------------------------------------------------------------------------- #
# S1-05 / S2-03 -- the gate fails closed, no row means denied                 #
# --------------------------------------------------------------------------- #


def test_no_limit_row_is_denied_gate_and_spends_nothing(monkeypatch):
    """S1-05: a contact with no `contact_media_limit` row for the modality is
    refused, no job is created, no provider call is made (nothing to
    monkeypatch a provider call with here -- proven by `job_id` being absent
    and no job row existing)."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "gate1")

        response = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="m-1"),
            headers={"X-API-Key": "whatever"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "denied_gate"
        assert body["job_id"] is None

        from app.models.media import MediaExtractionJob

        assert db.query(MediaExtractionJob).count() == 0


def test_modality_not_allowed_is_denied_gate_with_a_refusal_ledger_row(monkeypatch):
    """S2-03 + S2-04: an explicit `is_allowed=false` row is also the gate, and
    the refusal is recorded so a dead gate is observable."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "gate2")
        from app.models.media import ContactMediaLimit

        db.add(
            ContactMediaLimit(contact_id=contact.id, modality="image", is_allowed=False)
        )
        db.flush()

        response = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="m-1"),
            headers={"X-API-Key": "whatever"},
        )

        assert response.json()["decision"] == "denied_gate"
        rows = _usage_rows(db, contact.respond_io_id)
        assert len(rows) == 1
        assert rows[0].outcome == "refused_gate"


# --------------------------------------------------------------------------- #
# S2-01 -- decide + meter + record before any spend, ledger survives          #
# --------------------------------------------------------------------------- #


def test_accepted_call_writes_the_ledger_row_before_any_wait(monkeypatch):
    """S2-01: the ledger row is committed inside the fast path, independent
    of the (short-circuited) wait/extraction outcome."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "accept1")
        _allow(db, contact, "image", monthly_limit=50)

        response = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="m-1"),
            headers={"X-API-Key": "whatever"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "accepted"
        assert body["job_id"]

        rows = _usage_rows(db, contact.respond_io_id)
        assert len(rows) == 1
        assert rows[0].outcome == "accepted"


# --------------------------------------------------------------------------- #
# S2-02 -- strict idempotency on (respond_io_id, message_id, modality)        #
# --------------------------------------------------------------------------- #


def test_repeating_the_identical_call_replays_the_same_decision(monkeypatch):
    """S2-02: n8n's `retryOnFail` must be free -- same job_id, no second
    ledger row, `idempotent_replay: true`."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "idem1")
        _allow(db, contact, "image", monthly_limit=50)
        body = _body(respond_io_id=contact.respond_io_id, message_id="dup-1")

        first = client.post(ENDPOINT, json=body, headers={"X-API-Key": "k"})
        second = client.post(ENDPOINT, json=body, headers={"X-API-Key": "k"})

        assert first.json()["idempotent_replay"] is False
        assert second.json()["idempotent_replay"] is True
        assert second.json()["job_id"] == first.json()["job_id"]
        assert second.json()["decision"] == first.json()["decision"]

        rows = _usage_rows(db, contact.respond_io_id)
        assert len(rows) == 1, "exactly one ledger row must exist after the replay"


def test_idempotency_key_includes_modality_a_different_modality_is_a_new_call(
    monkeypatch,
):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "idem2")
        _allow(db, contact, "image", monthly_limit=50)
        _allow(db, contact, "voice", monthly_limit=50)

        client.post(
            ENDPOINT,
            json=_body(
                respond_io_id=contact.respond_io_id,
                message_id="same-id",
                modality="image",
            ),
            headers={"X-API-Key": "k"},
        )
        second = client.post(
            ENDPOINT,
            json=_body(
                respond_io_id=contact.respond_io_id,
                message_id="same-id",
                modality="voice",
                duration_ms=1000,
            ),
            headers={"X-API-Key": "k"},
        )

        assert second.json()["idempotent_replay"] is False
        assert len(_usage_rows(db, contact.respond_io_id)) == 2


# --------------------------------------------------------------------------- #
# S2-05 -- burst limiting is per contact, and is not the quota                #
# --------------------------------------------------------------------------- #


def test_burst_limit_denies_the_sixth_item_without_touching_quota(monkeypatch):
    """S2-05: burst is `media_burst_limit` per `media_burst_window_seconds`
    (settings, PLAN 2.4), enforced via `app.services.rate_limit.hit`
    (namespaced bucket, PLAN 3.3 step 5). Five accepted items then a sixth
    inside the window is `denied_burst`, and the sixth's refusal must not
    count against the monthly quota (S2-04's outcome split: only
    `accepted`/`failed` count against quota)."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "burst1")
        _allow(db, contact, "image", monthly_limit=50)
        _settings_row(db, media_burst_limit=5, media_burst_window_seconds=60)

        statuses = []
        for i in range(6):
            r = client.post(
                ENDPOINT,
                json=_body(respond_io_id=contact.respond_io_id, message_id=f"burst-{i}"),
                headers={"X-API-Key": "k"},
            )
            statuses.append(r.json()["decision"])

        assert statuses[:5] == ["accepted"] * 5
        assert statuses[5] == "denied_burst"

        rows = _usage_rows(db, contact.respond_io_id)
        accepted_rows = [r for r in rows if r.outcome == "accepted"]
        refused_rows = [r for r in rows if r.outcome == "refused_burst"]
        assert len(accepted_rows) == 5
        assert len(refused_rows) == 1


# --------------------------------------------------------------------------- #
# S2-06 -- at the quota limit the contact is degraded, not turned away        #
# --------------------------------------------------------------------------- #


def test_at_quota_limit_degrades_when_a_degraded_model_is_configured(monkeypatch):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "quota1")
        _allow(db, contact, "image", monthly_limit=1)
        _settings_row(db, media_image_degraded_model="gpt-4o-mini")

        first = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="q-1"),
            headers={"X-API-Key": "k"},
        )
        second = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="q-2"),
            headers={"X-API-Key": "k"},
        )

        assert first.json()["decision"] == "accepted"
        assert first.json()["tier"] == "standard"
        assert second.json()["decision"] == "accepted"
        assert second.json()["tier"] == "degraded"
        degrade_notices = [n["kind"] for n in second.json()["notices"]]
        assert "degraded" in degrade_notices


def test_at_quota_limit_refuses_when_no_degraded_model_is_configured(monkeypatch):
    """PLAN 3.2: `denied_quota` is only ever returned when degradation is
    impossible (no degraded model configured)."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "quota2")
        _allow(db, contact, "image", monthly_limit=1)
        _settings_row(db, media_image_degraded_model=None)

        client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="q-1"),
            headers={"X-API-Key": "k"},
        )
        second = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="q-2"),
            headers={"X-API-Key": "k"},
        )

        assert second.json()["decision"] == "denied_quota"
        assert second.json()["job_id"] is None

        rows = _usage_rows(db, contact.respond_io_id)
        assert rows[-1].outcome == "refused_quota"


# --------------------------------------------------------------------------- #
# S2-07 -- the 80% warning fires once per contact per period per modality     #
# --------------------------------------------------------------------------- #


def test_warn_80_fires_once_and_stamps_the_period(monkeypatch):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "warn1")
        _allow(db, contact, "image", monthly_limit=5)
        _settings_row(db, media_warn_threshold_percent=80)

        responses = []
        for i in range(5):
            r = client.post(
                ENDPOINT,
                json=_body(respond_io_id=contact.respond_io_id, message_id=f"warn-{i}"),
                headers={"X-API-Key": "k"},
            )
            responses.append(r.json())

        # 80% of 5 = 4 -> the 4th accepted item (index 3) crosses it.
        notice_kinds_per_call = [{n["kind"] for n in r["notices"]} for r in responses]
        assert "warn_80" in notice_kinds_per_call[3]
        # every later call in the same period must NOT repeat it.
        assert "warn_80" not in notice_kinds_per_call[4]

        from app.models.media import ContactMediaLimit

        row = (
            db.query(ContactMediaLimit)
            .filter(
                ContactMediaLimit.contact_id == contact.id,
                ContactMediaLimit.modality == "image",
            )
            .first()
        )
        assert row.warned_period is not None


# --------------------------------------------------------------------------- #
# S2-08 -- degradation notice is its own kind, also fires once per period     #
# --------------------------------------------------------------------------- #


def test_degradation_notice_fires_once_per_period_distinct_from_warn_80(monkeypatch):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "degrade1")
        _allow(db, contact, "image", monthly_limit=1)
        _settings_row(db, media_image_degraded_model="gpt-4o-mini")

        responses = []
        for i in range(3):
            r = client.post(
                ENDPOINT,
                json=_body(respond_io_id=contact.respond_io_id, message_id=f"dg-{i}"),
                headers={"X-API-Key": "k"},
            )
            responses.append(r.json())

        # call 0 = standard (at limit exactly), calls 1 and 2 = degraded.
        kinds_1 = {n["kind"] for n in responses[1]["notices"]}
        kinds_2 = {n["kind"] for n in responses[2]["notices"]}
        assert "degraded" in kinds_1
        assert "degraded" not in kinds_2, "must fire only once per period"

        from app.models.media import ContactMediaLimit

        row = (
            db.query(ContactMediaLimit)
            .filter(
                ContactMediaLimit.contact_id == contact.id,
                ContactMediaLimit.modality == "image",
            )
            .first()
        )
        assert row.degraded_notified_period is not None


# --------------------------------------------------------------------------- #
# S2-09 -- a voice clip over the max is refused before spend                  #
# --------------------------------------------------------------------------- #


def test_voice_clip_over_the_maximum_is_denied_duration(monkeypatch):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "voice1")
        _allow(db, contact, "voice", monthly_limit=50, max_clip_seconds=120)

        response = client.post(
            ENDPOINT,
            json=_body(
                respond_io_id=contact.respond_io_id,
                message_id="v-1",
                modality="voice",
                duration_ms=150_000,
                mime_type="audio/ogg",
            ),
            headers={"X-API-Key": "k"},
        )

        body = response.json()
        assert body["decision"] == "denied_duration"
        assert body["job_id"] is None
        rows = _usage_rows(db, contact.respond_io_id)
        assert rows[0].outcome == "refused_duration"


def test_voice_clip_within_the_maximum_is_not_denied_duration(monkeypatch):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "voice2")
        _allow(db, contact, "voice", monthly_limit=50, max_clip_seconds=120)

        response = client.post(
            ENDPOINT,
            json=_body(
                respond_io_id=contact.respond_io_id,
                message_id="v-2",
                modality="voice",
                duration_ms=60_000,
                mime_type="audio/ogg",
            ),
            headers={"X-API-Key": "k"},
        )

        assert response.json()["decision"] == "accepted"


# --------------------------------------------------------------------------- #
# S2-10 -- period is computed in Asia/Kuala_Lumpur, reset date pre-rendered   #
# --------------------------------------------------------------------------- #


def test_period_key_and_reset_label_are_rendered_in_malaysia_time(monkeypatch):
    """A UTC instant that is already the next calendar day/month in MYT
    (UTC+8) must resolve `period_key` against MYT, not UTC. 2026-08-31T20:00Z
    is 2026-09-01T04:00 MYT -- the September period, not August."""
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})
        contact = _contact(db, "tz1")
        _allow(db, contact, "image", monthly_limit=50)

        fixed_now = datetime(2026, 8, 31, 20, 0, 0, tzinfo=timezone.utc)
        # The module under test resolves "now" through this seam so the test
        # can pin the instant without sleeping until a real month boundary.
        monkeypatch.setattr(
            "app.services.media_access_service._now_utc",
            lambda: fixed_now,
            raising=False,
        )
        monkeypatch.setattr(
            "app.api.v1.external.media._now_utc", lambda: fixed_now, raising=False
        )

        response = client.post(
            ENDPOINT,
            json=_body(respond_io_id=contact.respond_io_id, message_id="tz-1"),
            headers={"X-API-Key": "k"},
        )

        body = response.json()
        assert body["quota"]["period_key"] == "2026-09"
        # n8n performs no date arithmetic -- already a rendered label.
        assert body["quota"]["resets_on"] not in (None, "")
        assert "-" not in body["quota"]["resets_on"], (
            "resets_on must be a human label ('1 October'), not an ISO date"
        )


# --------------------------------------------------------------------------- #
# S2-11 -- auth and validation                                                #
# --------------------------------------------------------------------------- #


def test_missing_api_key_is_401(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch=monkeypatch)  # no api_user override

        response = client.post(
            ENDPOINT, json=_body(respond_io_id="rio-x", message_id="m-1")
        )

        assert response.status_code == 401


def test_key_without_the_permission_slug_is_403(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})

        with patch("app.api.v1.external.permissions.UserPermissionService") as service:
            service.return_value.check_user_has_permission.return_value = False
            response = client.post(
                ENDPOINT,
                json=_body(respond_io_id="rio-x", message_id="m-1"),
                headers={"X-API-Key": "k"},
            )

        assert response.status_code == 403


def test_malformed_body_is_422(monkeypatch):
    with blank_session() as db, external_permissions_granted():
        client = _client(db, monkeypatch=monkeypatch, api_user={"id": "ext"})

        response = client.post(
            ENDPOINT,
            json={"respond_io_id": "rio-x"},  # missing modality, media_url, message_id
            headers={"X-API-Key": "k"},
        )

        assert response.status_code == 422


def test_the_permission_slug_is_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert "integration.chatbot_media.process" in slugs
