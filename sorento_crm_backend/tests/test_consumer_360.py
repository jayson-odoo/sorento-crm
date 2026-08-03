"""Consumer 360 - the read surface for the ledger S1 built.

Sorento sells through dealers and therefore does not know who owns its products. The whole
module exists to fix that, and until this endpoint there was no way to look at what it had
collected. An asset nobody can see is indistinguishable from one that was never collected.

Four things only the endpoint can get wrong, and each is a test below.

1. **Purchase value is OMITTED, not nulled, without the permission** (AC-L24). `None` means
   "the receipt showed no total"; absent means "you may not see it". Serialising the first
   when you mean the second tells a CS agent the dealer sold it for nothing. The seed grants
   this permission to nobody, so the denied path is the DEFAULT path and has to be the one
   that works.

2. **A merged profile redirects rather than 404s** (AC-L10). The losing row is retained
   pointing at the survivor precisely so "where did this consumer go" is answerable. A 404
   tells a CS agent following an old link that the record was deleted.

3. **Complaints reach a consumer two ways and both count.** Through a line naming one of
   their purchases (AC-L16), and through the phone on the complaint itself. A complaint
   lodged before any receipt arrived has no purchase link at all - and it is exactly the one
   a CS agent is looking for, because it is the one still open.

4. **The headline count excludes provisional profiles** (AC-L7). A phone somebody typed into
   a message is not a consumer Sorento knows. Counting it makes the number go up without the
   asset going up, which is the one number that must not lie.

Run: venv/bin/python -m pytest tests/test_consumer_360.py -q -p no:randomly
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app.database import get_db  # noqa: E402
from app.models.complaints import Complaint, ComplaintProductLine  # noqa: E402
from app.models.consumers import ConsumerProfile  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

BASE = "/api/v1/consumer-management/consumers"
PHONE = "+60127773344"

_USER_ID = "130c548f-048f-53b2-97a6-3a54676bea77"
_ROLE_ID = "7c50d6db-8dce-555a-85a2-86cf7756f33f"


# Two principals, because the value rule only means something when a reader who is NOT
# superadmin is doing the reading. Superadmin bypasses every permission check by design,
# so asserting the denial against one would assert nothing at all - and the denial is the
# DEFAULT state, since the seed grants `consumers.purchase_value.view` to nobody.
_CS_USER_ID = "6a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d"
_CS_ROLE_ID = "7b2c3d4e-5f6a-4b7c-8d9e-1f2a3b4c5d6e"


def _seed_user(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(
        UserRole(
            id=_CS_ROLE_ID,
            slug=f"{TEST_PREFIX}-cs".lower(),
            name="CS",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.flush()
    db.add(User(id=_USER_ID, email="root@test.com", name="Root", status="ACTIVE"))
    db.add(User(id=_CS_USER_ID, email="cs@test.com", name="CS", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.add(UserRoleAssignment(user_id=_CS_USER_ID, role_id=_CS_ROLE_ID))

    # The CS role can OPEN a consumer and cannot see what anything cost. That pair is
    # the ordinary shape of this permission in production.
    view = UserPermission(
        id=str(uuid.uuid4()), slug="consumers.profiles.view", name="View consumers"
    )
    db.add(view)
    db.flush()
    db.add(
        UserRolePermission(
            id=str(uuid.uuid4()), role_id=_CS_ROLE_ID, permission_id=view.id
        )
    )
    db.commit()


@pytest.fixture
def stack():
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    with blank_session() as db:
        _seed_user(db)

        def _override_get_db():
            yield db

        def _override_user():
            return {"id": _USER_ID, "email": "cs@test.com"}

        async def _override_scope():
            # What a real request with a bearer token does. Without it the resolver sees
            # no token, falls back to UNSET (fail-closed), and every scoped table reads
            # empty - which looks exactly like "the endpoint returns nothing" rather than
            # "the request had no company".
            set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
            return frozenset({DEFAULT_COMPANY_ID})

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_user
        app.dependency_overrides[apply_company_scope] = _override_scope
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(stack):
    return stack[0]


@pytest.fixture
def cs_client(stack):
    """The same client, reading as a non-superadmin CS agent.

    Every value assertion below uses this one. Against a superadmin the check is vacuous:
    superadmin bypasses permissions, so it would pass whether or not the omission works.
    """
    from app.dependencies import get_current_user, get_current_user_or_api_key

    def _cs():
        return {"id": _CS_USER_ID, "email": "cs@test.com"}

    app.dependency_overrides[get_current_user] = _cs
    app.dependency_overrides[get_current_user_or_api_key] = _cs
    return stack[0]


@pytest.fixture
def db(stack):
    return stack[1]


def _profile(db, *, phone: str = PHONE, provisional: bool = False) -> ConsumerProfile:
    from app.services.consumer_service import ensure_profile

    profile = ensure_profile(
        db, phone=phone, full_name=f"{TEST_PREFIX} Consumer", provisional=provisional
    )
    db.commit()
    return profile


def _first_purchase_line(db, purchase):
    """`ConsumerPurchase` has no `lines` relationship, and reading one silently yields
    nothing rather than raising in a service. That is exactly how the lodge service
    shipped every complaint line with a NULL purchase link. Query it.
    """
    from app.models.consumers import ConsumerPurchaseLine

    return (
        db.query(ConsumerPurchaseLine)
        .filter(ConsumerPurchaseLine.purchase_id == purchase.id)
        .order_by(ConsumerPurchaseLine.sort_order)
        .first()
    )


def _purchase(db, profile, *, total_value=None):
    from app.services.consumer_service import record_purchase

    purchase = record_purchase(
        db,
        purchase_date=date(2025, 10, 16),
        consumer_profile_id=str(profile.id),
        dealer_document_number=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        total_value=total_value,
        currency="MYR" if total_value is not None else None,
        lines=[{"kind_code": "water_closet", "claimed_text": "SRTWC8152", "quantity": 1}],
    )
    db.commit()
    return purchase


# ========================================================= value, omitted not nulled


def test_purchase_value_is_absent_without_the_permission(cs_client, db):
    """The DEFAULT path, because the seed grants this permission to nobody.

    `total_value` must not appear at all. A null would read as "the receipt showed no
    total", which is a different fact and a materially worse one to show a CS agent.
    """
    profile = _profile(db)
    _purchase(db, profile, total_value=1250)

    body = cs_client.get(f"{BASE}/{profile.id}").json()
    assert body["purchases"], "The purchase must still be visible - only its value is not."
    purchase = body["purchases"][0]
    assert "total_value" not in purchase
    assert "currency" not in purchase, (
        "The currency on its own implies a value is held. It goes with it."
    )


def test_the_purchase_date_survives_the_value_being_hidden(cs_client, db):
    """Hiding the whole purchase would take the DATE away, and the date is the only
    field the warranty verdict depends on.
    """
    profile = _profile(db)
    _purchase(db, profile, total_value=1250)
    purchase = cs_client.get(f"{BASE}/{profile.id}").json()["purchases"][0]
    assert purchase["purchase_date"] == "2025-10-16"
    assert purchase["dealer_document_number"]


def test_the_line_value_is_hidden_too(cs_client, db):
    """A per-line value would leak exactly what the header's hidden total protects."""
    profile = _profile(db)
    _purchase(db, profile, total_value=1250)
    lines = cs_client.get(f"{BASE}/{profile.id}").json()["purchases"][0]["lines"]
    assert lines, "The line itself is visible - it says WHAT was bought."
    assert "line_value" not in lines[0]


# ================================================================= the merged profile


def test_a_merged_profile_points_at_its_survivor_instead_of_404ing(client, db):
    """AC-L10. A CS agent following an old link must learn where the person went, not
    that the record was deleted.
    """
    from app.services.consumer_service import merge_profiles

    survivor = _profile(db)
    loser = _profile(db, phone="+60127773355")
    merge_profiles(db, surviving_id=str(survivor.id), losing_id=str(loser.id))
    db.commit()

    response = client.get(f"{BASE}/{loser.id}")
    assert response.status_code == 200, "A merged profile is found, not missing."
    assert response.json()["merged_into_id"] == str(survivor.id)


def test_a_merged_profile_is_not_listed(client, db):
    """Listing it would show one person twice under two names."""
    from app.services.consumer_service import merge_profiles

    survivor = _profile(db)
    loser = _profile(db, phone="+60127773355")
    merge_profiles(db, surviving_id=str(survivor.id), losing_id=str(loser.id))
    db.commit()

    ids = [row["id"] for row in client.get(BASE).json()["data"]]
    assert str(survivor.id) in ids
    assert str(loser.id) not in ids


def test_an_unknown_consumer_is_a_clean_404(client):
    assert client.get(f"{BASE}/{uuid.uuid4()}").status_code == 404


def test_a_malformed_id_is_a_404_not_a_500(client):
    """A bad-format id is a guaranteed-missing row from the caller's side. Letting it
    reach the DB layer turns it into a 500 that leaks an error and masks the real answer.
    """
    assert client.get(f"{BASE}/not-a-uuid").status_code == 404


# ==================================================================== the complaints


def test_a_complaint_reaches_the_consumer_through_its_purchase_line(client, db):
    """AC-L16. The join a frontend must never re-derive for itself."""
    profile = _profile(db)
    purchase = _purchase(db, profile)

    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{TEST_PREFIX}-C1",
        status="submitted",
        defect_description="Water keeps running.",
    )
    db.add(complaint)
    db.flush()
    db.add(
        ComplaintProductLine(
            id=str(uuid.uuid4()),
            complaint_id=complaint.id,
            product_code="SRTWC8152",
            consumer_purchase_line_id=_first_purchase_line(db, purchase).id,
        )
    )
    db.commit()

    numbers = [c["complaint_number"] for c in client.get(f"{BASE}/{profile.id}").json()["complaints"]]
    assert f"{TEST_PREFIX}-C1" in numbers


def test_a_complaint_with_no_purchase_link_still_reaches_the_consumer(client, db):
    """The one a CS agent is actually looking for.

    A complaint lodged before any receipt arrived has no purchase to link to - which is
    normal, since AC-C14 lets it lodge with nothing. Reaching it only through purchases
    would hide exactly the complaints that are still open.
    """
    profile = _profile(db)
    db.add(
        Complaint(
            id=str(uuid.uuid4()),
            complaint_number=f"{TEST_PREFIX}-C2",
            status="submitted",
            contact_number=PHONE,
        )
    )
    db.commit()

    numbers = [c["complaint_number"] for c in client.get(f"{BASE}/{profile.id}").json()["complaints"]]
    assert f"{TEST_PREFIX}-C2" in numbers


def test_a_consumer_with_nothing_yet_returns_empty_sections_not_a_404(client, db):
    """Every section always renders (CRUD UX standard). A profile with no purchases is a
    normal, common state - it is what a provisional profile looks like - and the page has
    to be able to say so.
    """
    profile = _profile(db)
    body = client.get(f"{BASE}/{profile.id}").json()
    assert body["purchases"] == []
    assert body["complaints"] == []
    assert body["counts"] == {"purchases": 0, "complaints": 0}


# ======================================================================= finding them


def test_a_consumer_is_found_by_a_phone_typed_the_way_a_human_types_it(client, db):
    """A CS agent types "012-777 3344"; the column holds "+60127773344"."""
    profile = _profile(db)
    ids = [row["id"] for row in client.get(BASE, params={"query": "012-777 3344"}).json()["data"]]
    assert str(profile.id) in ids


def test_a_consumer_is_found_by_name(client, db):
    profile = _profile(db)
    ids = [row["id"] for row in client.get(BASE, params={"query": TEST_PREFIX}).json()["data"]]
    assert str(profile.id) in ids


# ========================================================================== the count


def test_the_headline_count_excludes_provisional_profiles(client, db):
    """AC-L7. The one number that must not lie.

    A provisional profile is a phone somebody typed into a message. Counting it makes
    "we know N consumers" go up while the asset stays exactly where it was.
    """
    _profile(db, phone="+60127770001", provisional=False)
    _profile(db, phone="+60127770002", provisional=True)

    body = client.get(f"{BASE}/stats/headline").json()
    assert body["consumers"] == 1
    assert body["provisional"] == 1


def test_the_headline_route_is_not_shadowed_by_the_detail_route(client, db):
    """`/consumers/stats/headline` must not be read as `/consumers/{id}` with id=stats.

    Different segment counts make this safe today, but the SLA module already shipped a
    route-shadowing bug of exactly this shape, so it is pinned rather than assumed.
    """
    response = client.get(f"{BASE}/stats/headline")
    assert response.status_code == 200
    assert "consumers" in response.json()
