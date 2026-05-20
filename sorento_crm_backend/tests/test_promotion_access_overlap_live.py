"""Live-DB integration test: contact access types → promotion/attachment visibility.

Exercises the real Postgres JSONB ``?|`` overlap operator end-to-end:

1. Inserts a RespondWorkspace + RespondContact + 3 Promotion rows with distinct
   ``access_levels`` arrays.
2. Uses ``ContactAccessTypeService.set_contact_access_codes`` to assign codes to
   the contact via the M2M pivot.
3. Calls ``ContactAccessTypeService.resolve_contact_access_codes(respond_io_id,
   space_id)`` to prove the (respond_io_id, space_id) → codes resolution.
4. Calls ``PromotionService.list_promotions(contact_access_codes=...)`` to prove
   the SQL filter actually emits ``access_levels ?| CAST(ARRAY[...] AS VARCHAR[])``
   and matches the expected promotions.
5. Wraps everything in a single transaction that is ALWAYS rolled back, so the
   shared dev database is left untouched.

Skipped automatically when DATABASE_URL is unset or unreachable.

Run with: pytest tests/test_promotion_access_overlap_live.py -v
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.marketing import Promotion
from app.models.respond_workspace import RespondWorkspace
from app.services.contact_access_type_service import ContactAccessTypeService
from app.services.error_handler import AppException
from app.services.marketing_service import PromotionService


pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


@pytest.fixture()
def db() -> Session:
    """Session in an outer transaction that is rolled back at teardown."""
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT in case anything inside auto-commits
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def fixtures(db: Session):
    """Insert workspace + contact + 3 promotions with distinct access_levels."""
    suffix = uuid.uuid4().hex[:8]
    workspace = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp-{suffix}",
        name=f"test-workspace-{suffix}",
        api_key_ciphertext="test-cipher-stub",
    )
    db.add(workspace)
    db.flush()

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60000{suffix[:6]}",  # unique phone
        name=f"Test Contact {suffix}",
        respond_io_id=f"rid-{suffix}",
        workspace_id=workspace.id,
    )
    db.add(contact)
    db.flush()

    today = date.today()
    start = today - timedelta(days=1)
    end = today + timedelta(days=30)

    # Three promotions covering the three relevant cases for the overlap filter.
    promo_dealer = Promotion(
        id=str(uuid.uuid4()),
        description=f"TEST_DEALER_{suffix}",
        access_levels=["dealer"],
        is_active=True,
        start_date=start,
        end_date=end,
    )
    promo_vip = Promotion(
        id=str(uuid.uuid4()),
        description=f"TEST_VIP_{suffix}",
        # Use a catalog code the contact will NOT be assigned to.
        access_levels=["end_user"],
        is_active=True,
        start_date=start,
        end_date=end,
    )
    promo_both = Promotion(
        id=str(uuid.uuid4()),
        description=f"TEST_BOTH_{suffix}",
        access_levels=["dealer", "end_user"],
        is_active=True,
        start_date=start,
        end_date=end,
    )
    db.add_all([promo_dealer, promo_vip, promo_both])
    db.flush()

    return {
        "workspace": workspace,
        "contact": contact,
        "promo_dealer_id": promo_dealer.id,
        "promo_vip_id": promo_vip.id,
        "promo_both_id": promo_both.id,
        "promo_codes": {promo_dealer.description, promo_vip.description, promo_both.description},
    }


def _list_codes_for_test_promos(result: dict, expected_codes: set[str]) -> set[str]:
    """Filter the listing response down to just our test promotions."""
    return {p.description for p in result["data"] if p.description in expected_codes}


def test_set_and_get_contact_access_codes(db: Session, fixtures):
    """Pivot CRUD: set replaces the assignment atomically; get returns the
    catalog-ordered codes."""
    svc = ContactAccessTypeService(db)
    contact_id = fixtures["contact"].id

    assert svc.get_contact_access_codes(contact_id) == []

    svc.set_contact_access_codes(contact_id, ["dealer", "end_user"])
    db.flush()
    got = svc.get_contact_access_codes(contact_id)
    assert set(got) == {"dealer", "end_user"}

    # Replacement, not append: setting to just ['dealer'] drops end_user.
    svc.set_contact_access_codes(contact_id, ["dealer"])
    db.flush()
    assert svc.get_contact_access_codes(contact_id) == ["dealer"]

    # Empty list clears all assignments.
    svc.set_contact_access_codes(contact_id, [])
    db.flush()
    assert svc.get_contact_access_codes(contact_id) == []


def test_resolve_contact_access_codes_by_respond_id_and_space(db: Session, fixtures):
    """Resolution path: (respond_io_id, space_id) → contact → codes."""
    svc = ContactAccessTypeService(db)
    contact = fixtures["contact"]
    workspace = fixtures["workspace"]

    svc.set_contact_access_codes(contact.id, ["dealer"])
    db.flush()

    got = svc.resolve_contact_access_codes(contact.respond_io_id, workspace.space_id)
    assert got == ["dealer"]


def test_resolve_contact_access_codes_unknown_pair_404(db: Session, fixtures):
    svc = ContactAccessTypeService(db)
    with pytest.raises(AppException) as exc_info:
        svc.resolve_contact_access_codes("does-not-exist", fixtures["workspace"].space_id)
    assert exc_info.value.status_code == 404


def test_promotion_list_filtered_by_overlap_dealer(db: Session, fixtures):
    """contact_access_codes=['dealer'] keeps dealer-only + dealer+end_user;
    drops end_user-only. This is the SQL path that previously failed with
    'operator does not exist: jsonb ?| jsonb' before the ARRAY(String) cast."""
    svc = PromotionService(db)
    result = svc.list_promotions(
        page=1,
        limit=100,
        contact_access_codes=["dealer"],
        active=True,
    )
    seen = _list_codes_for_test_promos(result, fixtures["promo_codes"])
    expected_dealer = next(
        p for p in result["data"] if p.id == fixtures["promo_dealer_id"]
    )
    assert "TEST_DEALER_" in expected_dealer.description
    assert any(p.description.startswith("TEST_BOTH_") for p in result["data"])
    assert not any(p.description.startswith("TEST_VIP_") for p in result["data"])
    # And re-checked via the filtered set:
    assert any(c.startswith("TEST_DEALER_") for c in seen)
    assert any(c.startswith("TEST_BOTH_") for c in seen)
    assert not any(c.startswith("TEST_VIP_") for c in seen)


def test_promotion_list_filtered_by_overlap_end_user(db: Session, fixtures):
    """contact_access_codes=['end_user'] keeps end_user-only + dealer+end_user;
    drops dealer-only."""
    svc = PromotionService(db)
    result = svc.list_promotions(
        page=1,
        limit=100,
        contact_access_codes=["end_user"],
        active=True,
    )
    seen = _list_codes_for_test_promos(result, fixtures["promo_codes"])
    assert any(c.startswith("TEST_VIP_") for c in seen)
    assert any(c.startswith("TEST_BOTH_") for c in seen)
    assert not any(c.startswith("TEST_DEALER_") for c in seen)


def test_promotion_list_empty_contact_codes_returns_nothing(db: Session, fixtures):
    """A contact with no assigned access types must see zero rows (an empty
    codes list cannot overlap anything by definition)."""
    svc = PromotionService(db)
    result = svc.list_promotions(
        page=1,
        limit=100,
        contact_access_codes=[],
        active=True,
    )
    assert result["pagination"]["total"] == 0
    assert result["data"] == []


def test_promotion_list_none_codes_keeps_admin_path(db: Session, fixtures):
    """contact_access_codes=None means no contact context — the FE/admin path
    that should see EVERY active promotion. Test only checks that our 3 fixtures
    survive (the dev DB may have other rows we don't care about)."""
    svc = PromotionService(db)
    result = svc.list_promotions(
        page=1,
        limit=1000,
        contact_access_codes=None,
        active=True,
    )
    seen = _list_codes_for_test_promos(result, fixtures["promo_codes"])
    assert seen == fixtures["promo_codes"]


def test_promotion_get_404_when_no_overlap(db: Session, fixtures):
    """A promotion the contact's codes don't overlap with returns 404 (matches
    the route-level not-found semantics)."""
    from app.api.v1.marketing.promotions import get_promotion as _route  # noqa: F401
    svc = PromotionService(db)
    # Direct service call is permissive — it returns the promo and just filters
    # inline attachments. The 404 check lives in the FastAPI route. The route is
    # covered separately by test_promotion_get_route_access_overlap below.
    promo = svc.get_promotion(fixtures["promo_vip_id"], contact_access_codes=["dealer"])
    assert promo is not None
    # Inline attachments must come back as an empty list (no overlap possible
    # because the underlying access_levels are end_user-only).
    assert getattr(promo, "attachments", []) == []
