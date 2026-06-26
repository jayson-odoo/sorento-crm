"""Service + endpoint tests for the conversation-SLA record-navigation feature.

Mirrors tests/test_complaint_neighbours.py, adapted to the conversation SLA list
contract (see docs/plans/PLAN-record-navigation-standardization.md):

- filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- active sort (column + dir) reorders the neighbours.
- circular wrap (first.prev = last, last.next = first).
- out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- scope split: form-SLA rows NEVER appear in the conversation neighbours set.
- /neighbours endpoint enforces auth -> 401/403 with no principal.

Runs against the live Postgres test DB (same pattern as the other SLA tests):
seed rows with a unique marker, assert, clean up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.models.access import RespondContact
from app.models.sla import ConversationSLATracking, SLAPolicy
from app.services.sla_service import ConversationSLATrackingService

# Unique markers so the `query=` filter (contact phone/name) matches ONLY this
# test's rows and nothing else already in the shared DB.
NAME_MARKER = "NBRCONV"
PHONE_PREFIX = "+60999000"
POLICY_CODE = "NBR-CONV-POLICY"


@pytest.fixture(autouse=True)
def _clean_state():
    def _wipe(conn):
        # Order matters: trackers FK -> contacts; contacts unique on phone.
        conn.execute(
            text(
                "DELETE FROM conversation_sla_tracking WHERE respond_contact_id IN "
                "(SELECT id FROM respond_contacts WHERE name LIKE 'NBRCONV%')"
            )
        )
        conn.execute(text("DELETE FROM respond_contacts WHERE name LIKE 'NBRCONV%'"))
        conn.execute(text("DELETE FROM sla_policies WHERE code = :c"), {"c": POLICY_CODE})

    with engine.connect() as conn:
        try:
            _wipe(conn)
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            _wipe(conn)
            conn.commit()
        except Exception:
            conn.rollback()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed_policy(db: Session) -> SLAPolicy:
    existing = db.query(SLAPolicy).filter(SLAPolicy.code == POLICY_CODE).first()
    if existing:
        return existing
    p = SLAPolicy(
        id=str(uuid.uuid4()),
        code=POLICY_CODE,
        name="NBR Conversation Policy",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed_contact(db: Session, idx: int, *, name_marker: str = NAME_MARKER) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"{PHONE_PREFIX}{idx:04d}",
        name=f"{name_marker}-{idx:03d}",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_tracking(
    db: Session,
    policy: SLAPolicy,
    contact: RespondContact,
    *,
    current_tier: int,
    source_entity_type: str | None = None,
) -> ConversationSLATracking:
    now = datetime.utcnow()
    t = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        current_tier=current_tier,
        respond_contact_id=contact.id,
        due_at=now + timedelta(hours=4),
        source_entity_type=source_entity_type,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _seed_ordered_set(
    db: Session, n: int = 5, *, name_marker: str = NAME_MARKER
) -> list[ConversationSLATracking]:
    """Seed n conversation trackers whose current_tier is 0..n-1.

    Sorting asc by current_tier yields exactly this order, so neighbour
    expectations are unambiguous.
    """
    policy = _seed_policy(db)
    rows: list[ConversationSLATracking] = []
    for i in range(n):
        contact = _seed_contact(db, i, name_marker=name_marker)
        rows.append(_seed_tracking(db, policy, contact, current_tier=i))
    return rows


# --------------------------------------------------------------------------- #
# Service-level: ConversationSLATrackingService.neighbours                      #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = ConversationSLATrackingService(db)
    out = svc.neighbours(
        rows[2].id, query=NAME_MARKER, sort_field="current_tier", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # Seed a filtered subset plus extra non-matching rows; the neighbours total
    # must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)
    # Noise: conversation rows whose contact name does NOT contain "NBRCONV-"
    # (no hyphen after the prefix) so query="NBRCONV-" excludes them, while the
    # "NBRCONV" cleanup LIKE still sweeps them.
    policy = _seed_policy(db)
    for i in range(4):
        noise_contact = _seed_contact(db, 100 + i, name_marker="NBRCONVNOISE")
        _seed_tracking(db, policy, noise_contact, current_tier=i)

    svc = ConversationSLATrackingService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole conversation set
    filtered = svc.neighbours(
        target[0].id, query=NAME_MARKER + "-", sort_field="current_tier"
    )

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    assert filtered["total"] != unfiltered["total"]
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)  # current_tier 0..4
    svc = ConversationSLATrackingService(db)
    asc = svc.neighbours(rows[2].id, query=NAME_MARKER, sort_field="current_tier", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=NAME_MARKER, sort_field="current_tier", sort_dir="desc")
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = ConversationSLATrackingService(db)
    out = svc.neighbours(rows[0].id, query=NAME_MARKER, sort_field="current_tier", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = ConversationSLATrackingService(db)
    out = svc.neighbours(rows[3].id, query=NAME_MARKER, sort_field="current_tier", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must fall
    # back to the unfiltered conversation set so the pager is never dead, and the
    # total reflects the unfiltered count.
    _seed_ordered_set(db, 3)  # match query=NAME_MARKER
    policy = _seed_policy(db)
    outside_contact = _seed_contact(db, 200, name_marker="NBRCONVOUTSIDE")
    outside = _seed_tracking(db, policy, outside_contact, current_tier=9)

    svc = ConversationSLATrackingService(db)
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=NAME_MARKER + "-", sort_field="current_tier")
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_excludes_form_sla_rows(db: Session) -> None:
    # Scope split: a form-SLA tracker (source_entity_type in FORM_SLA_TYPES) must
    # never appear in the conversation neighbours set, and must NOT inflate the total.
    conv = _seed_ordered_set(db, 3)
    policy = _seed_policy(db)
    form_contact = _seed_contact(db, 300, name_marker=NAME_MARKER)
    form_row = _seed_tracking(
        db, policy, form_contact, current_tier=5, source_entity_type="complaint"
    )

    svc = ConversationSLATrackingService(db)
    out = svc.neighbours(conv[0].id, query=NAME_MARKER, sort_field="current_tier")
    assert out["total"] == 3, "form rows must not inflate the conversation total"

    # The form row is not in the conversation scope -> resolved only via the D2
    # unfiltered fallback, which is ALSO conversation-scoped, so it stays absent.
    form_out = svc.neighbours(form_row.id, query=NAME_MARKER, sort_field="current_tier")
    assert form_out["index"] is None
    assert form_out["prev_id"] is None and form_out["next_id"] is None


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    rows = _seed_ordered_set(db, 3)
    svc = ConversationSLATrackingService(db)
    out = svc.neighbours(rows[1].id, sort_field="current_tier", sort_dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #

NEIGHBOURS_PATH = "/api/v1/sla-management/conversation-sla-tracking/neighbours"


def test_neighbours_endpoint_requires_auth() -> None:
    # No Bearer token, no X-API-Key -> 401/403.
    with TestClient(app) as client:
        res = client.get(NEIGHBOURS_PATH, params={"id": str(uuid.uuid4())})
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422_or_auth() -> None:
    # id is required -> FastAPI validation 422, or auth rejection; never 200/500.
    with TestClient(app) as client:
        res = client.get(NEIGHBOURS_PATH)
    assert res.status_code in (401, 403, 422), res.text
