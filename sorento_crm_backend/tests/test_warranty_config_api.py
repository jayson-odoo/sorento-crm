"""S7b gate, part 2 - the warranty configuration API (AC-P1 to AC-P13).

Written BEFORE the implementation. The entitlement engine is built, correct, and
unconfigurable: 31 Kinds, 41 Terms and TWO Kind Rules, with 29 of the 31 Kinds
unreachable by any rule. A product that reaches no Kind gets no verdict, and nothing
on any screen says so. This slice is the editor, and this file is its contract.

Every route in the plan's pinned API contract is exercised for happy path, auth
denial and validation error. The rulings the UAC settled (AC-P0a to AC-P13) are one
test each, named in the docstring.

**Everything the first draft of this gate left open is now ruled** (UAC "Phase B
corrections - after the red suite", AC-P14 to AC-P25), so nothing here is
deliberately loose any more:

- **AC-P14** the envelope: policies are `ListResponse[T]` =
  `{data, pagination:{total,page,limit}, empty}`; kinds, kinds-select, kind-rules
  and defect-types are BARE ARRAYS. Settled by the code - `app/schemas/common.py`
  and the FE's `DataGridApiResponse<T>` are already the same shape - so the Phase-1
  prototype's `{data, total}` is the thing that was wrong.
- **AC-P15** the success codes: `POST` 201 with the row, `PATCH` 200 with the row,
  `DELETE` 200 (`complaint_root_causes.py` is the precedent for all three). Exact,
  not a tolerated pair.
- **AC-P16** `term_count` on the policy LIST row and `assessment_count` on the term
  row, because the delete is offered from the grid and the delete endpoints are
  void: a count that exists only on the detail response cannot reach the dialog.
- **AC-P17** `has_no_rules` / `has_no_terms` as explicit booleans. Computing "zero"
  in a grid cell makes it visible in exactly one place and invisible to export, to
  MCP and to the AI assistant - AC-P7's own disease one layer up.
- **AC-P18** `GET /defect-types`, guarded by `warranty.policies.view`.
- **AC-P20** `duration_months > 0`.
- **AC-P21** Supersede is refused 422 on an already-closed incumbent and on a new
  `effective_from` at or before the incumbent's own.
- **AC-P22** the overlap guard applies to PATCH, and a policy never overlaps itself.
- **AC-P24** an unknown `match_type` or an empty `match_value` is 422 at WRITE time
  while the engine keeps its tolerant READ behaviour. A deliberate layer split.
- **AC-P26** there is NO undo for Supersede, and the recovery from a mis-dated one
  is two supported steps. The whole ruling rests on the two refusals NAMING those
  steps, so the message content is gated here, not just the status - and the
  two-step path is exercised end to end, because a ruling that says "the recovery
  is two steps" is wrong if the second step is refused.

The failure codes were never stated anywhere and stay as this gate pinned them:
409 for a conflict with an existing row (duplicate version, overlapping window, a
Kind still referenced), 422 for a payload that cannot be right, 404 for a policy
outside the caller's company scope, 403 for a missing permission.

Permissions are modelled by patching the lookup rather than by seeding roles: a
blank schema has no roles, and seeding an RBAC chain here would be testing
`UserPermissionService` rather than these routes.

Company scope is set the way production sets it - on the SESSION, through the
router-level `apply_company_scope` dependency - never by hand-filtering a query.
AC-P9 is only real if the thing being tested is the thing that runs.

Everything runs on Postgres via ``blank_session`` - never sqlite.

Run: venv/bin/python -m pytest tests/test_warranty_config_api.py -q -p no:randomly
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app import database as app_database  # noqa: E402
from app.dependencies import get_current_user, get_current_user_or_api_key  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.complaints import Complaint, ComplaintProductLine  # noqa: E402
from app.models.lookup import LookupOption, LookupSet  # noqa: E402
from app.models.warranty import (  # noqa: E402
    WarrantyAssessment,
    WarrantyKindRule,
    WarrantyPolicy,
    WarrantyProductKind,
    WarrantyTerm,
)
from app.services.company_scope_resolver import apply_company_scope  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code  # noqa: E402

# ---------------------------------------------------------------- the contract

# AC-P0a: NOT /master-data-management, whose prefix `lib/route-module-map.ts` gates
# on the PRODUCT module. A warranty editor there survives uninstalling warranty and
# disappears when the product module is uninstalled - exactly backwards.
BASE = "/api/v1/warranty-management"
POLICIES = f"{BASE}/policies"
KINDS = f"{BASE}/kinds"
RULES = f"{BASE}/kind-rules"

# AC-P11. Terms ride the policies slug and kind rules ride the kinds slug: a rule
# has no life apart from the Kind it points at, and a slug nobody will ever grant
# separately is a slug that rots.
P_VIEW = "warranty.policies.view"
P_ADD = "warranty.policies.add"
P_EDIT = "warranty.policies.edit"
P_DELETE = "warranty.policies.delete"
K_VIEW = "warranty.kinds.view"
K_ADD = "warranty.kinds.add"
K_EDIT = "warranty.kinds.edit"
K_DELETE = "warranty.kinds.delete"

SORENTO = "00000000-0000-0000-0000-000000000001"

# AC-D2's four, and nothing else.
MATCH_TYPES = ("category", "model_prefix", "model_list", "series")

# AC-P15, exact. `complaint_root_causes.py` is the precedent for all three, and the
# prototype's documented 204-on-delete is wrong. Named rather than inlined so the
# ruling is one edit if it is ever revisited - and so a permissive tuple cannot creep
# back in under a constant that still reads like a decision.
CREATED = 201
UPDATED = 200
DELETED = 200

# Every overlap refusal is ONE guard over one fact - "this window collides with an
# existing row" - so it answers with ONE code wherever it fires: POST, PATCH, and
# the reopen-a-superseded-policy case AC-P26 turns on. Named so that cannot drift.
# (AC-P26's prose says 422 for the reopen; AC-P2 / AC-P22 make it the same guard as
# the POST refusal, and two codes for one fact is how a frontend ends up with two
# error branches that disagree. Reported.)
OVERLAP_REFUSED = 409


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture
def client(db):
    """A logged-in principal, scoped to Sorento. Permissions come from `granted()`.

    `apply_company_scope` is overridden rather than left to the real resolver: the
    resolver reads a JWT this test never issues, so it would fail closed (UNSET ->
    zero rows) and every assertion in the file would pass for the wrong reason.
    The override stamps the scope onto the SAME session the route uses, which is
    exactly what production does - so AC-P9 is tested against the real mechanism.
    """
    holder = {"scope": frozenset({SORENTO})}

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, holder["scope"])
        return holder["scope"]

    principal = {"id": str(uuid.uuid4()), "email": "warranty-admin@example.test"}
    app.dependency_overrides[app_database.get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as c:
            c.scope_holder = holder
            yield c
    finally:
        for dep in (
            app_database.get_db,
            get_current_user,
            get_current_user_or_api_key,
            apply_company_scope,
        ):
            app.dependency_overrides.pop(dep, None)


@contextmanager
def granted(*slugs: str):
    """Hold exactly these permissions and no others.

    Deliberately exact rather than "grant everything": a test that granted all eight
    could never notice a route reading the wrong slug, which is the most likely way
    the policies / kinds split gets quietly undone.
    """
    allowed = set(slugs)
    with patch("app.dependencies.UserPermissionService") as service:
        service.return_value.check_user_has_permission.side_effect = (
            lambda _user_id, slug: slug in allowed
        )
        service.return_value.get_user_role_slugs.return_value = set()
        yield


@contextmanager
def as_company(client, db, company_id: str):
    """Act as a principal whose active company is `company_id` (AC-P9)."""
    previous = client.scope_holder["scope"]
    client.scope_holder["scope"] = frozenset({company_id})
    set_company_scope(db, frozenset({company_id}))
    try:
        yield
    finally:
        client.scope_holder["scope"] = previous
        set_company_scope(db, previous)


# ------------------------------------------------------------------- seed helpers


def _company(db, stem: str) -> str:
    row = Company(
        id=str(uuid.uuid4()),
        name=f"{TEST_PREFIX} {stem}",
        code=unique_code(stem)[:50],
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row.id


def _kind_row(db, stem: str, *, is_active: bool = True) -> WarrantyProductKind:
    row = WarrantyProductKind(
        id=str(uuid.uuid4()),
        code=unique_code(stem)[:64],
        name=f"{TEST_PREFIX} {stem}"[:255],
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _policy_row(db, *, effective_from: date, effective_to=None, version=None) -> WarrantyPolicy:
    row = WarrantyPolicy(
        id=str(uuid.uuid4()),
        version=(version or unique_code("v"))[:32],
        effective_from=effective_from,
        effective_to=effective_to,
    )
    db.add(row)
    db.flush()
    return row


def _term_row(db, policy, kind, part_name, **kw) -> WarrantyTerm:
    row = WarrantyTerm(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        kind_id=kind.id,
        part_name=part_name,
        duration_months=kw.get("duration_months"),
        is_lifetime=kw.get("is_lifetime", False),
        covered_defect_type_ids=kw.get("covered_defect_type_ids"),
        installation_included=kw.get("installation_included", False),
        registration_bonus_months=kw.get("registration_bonus_months"),
    )
    db.add(row)
    db.flush()
    return row


def _rule_row(db, kind, match_type, match_value, priority=0) -> WarrantyKindRule:
    row = WarrantyKindRule(
        id=str(uuid.uuid4()),
        kind_id=kind.id,
        match_type=match_type,
        match_value=match_value,
        priority=priority,
    )
    db.add(row)
    db.flush()
    return row


def _defect_type(db, label: str) -> str:
    """A REAL `lookup_options` row - Postgres enforces what sqlite ignored, and
    `covered_defect_type_ids` holds `lookup_options.id` values (AC-D18)."""
    lookup_set = LookupSet(
        id=str(uuid.uuid4()), set_key=unique_code("defectset")[:80], name=f"{TEST_PREFIX} defects"
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(
        id=str(uuid.uuid4()),
        set_id=lookup_set.id,
        value=f"{TEST_PREFIX}-{label}"[:150],
        label=label[:255],
        sort_order=0,
    )
    db.add(option)
    db.flush()
    return option.id


def _assessment(db, term, *, verdict="covered", expiry=date(2030, 10, 16)) -> WarrantyAssessment:
    """A stored verdict against a real complaint product line (AC-P8, AC-P8a)."""
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=unique_code("CMP")[:60],
        complaint_date=date(2026, 7, 1),
        status="new",
    )
    db.add(complaint)
    db.flush()
    line = ComplaintProductLine(
        id=str(uuid.uuid4()),
        complaint_id=complaint.id,
        product_code="SRTWC8366",
        sort_order=0,
    )
    db.add(line)
    db.flush()
    row = WarrantyAssessment(
        id=str(uuid.uuid4()),
        complaint_product_line_id=line.id,
        term_id=term.id,
        computed_verdict=verdict,
        computed_expiry=expiry,
        part_name=term.part_name,
        policy_id=term.policy_id,
        policy_version=db.query(WarrantyPolicy).filter(WarrantyPolicy.id == term.policy_id).one().version,
    )
    db.add(row)
    db.flush()
    return row


def _policy_body(**overrides) -> dict:
    body = {
        "version": unique_code("V")[:32],
        "effective_from": "2026-01-01",
        "effective_to": None,
        "policy_text": f"{TEST_PREFIX} clause 17: residential installations only.",
    }
    body.update(overrides)
    return body


def _term_body(kind_id: str, **overrides) -> dict:
    body = {
        "kind_id": kind_id,
        "part_name": f"{TEST_PREFIX} Ceramic Body",
        "duration_months": 60,
        "is_lifetime": False,
        "installation_included": False,
        "registration_bonus_months": None,
        "covered_defect_type_ids": None,
    }
    body.update(overrides)
    return body


def _kind_body(**overrides) -> dict:
    body = {
        "code": unique_code("kind")[:64],
        "name": f"{TEST_PREFIX} Water Closet",
        "consumer_label": "Toilet",
        "sort_order": 0,
        "is_active": True,
    }
    body.update(overrides)
    return body


def _rule_body(kind_id: str, **overrides) -> dict:
    body = {
        "kind_id": kind_id,
        "match_type": "model_prefix",
        "match_value": "SRTWC",
        "priority": 0,
    }
    body.update(overrides)
    return body


def _rows(response):
    """The rows of a list response.

    AC-P14 splits the envelope by resource - `ListResponse[T]` for policies, a bare
    array for everything else - and two dedicated tests below own that split. This
    accessor exists so the other ninety tests can assert the ROWS without restating
    the wrapper ninety times.
    """
    body = response.json()
    if isinstance(body, list):
        return body
    assert isinstance(body, dict), f"Unrecognised list response: {body!r}"
    assert "data" in body, f"List response carries neither a bare array nor `data`: {body!r}"
    return body["data"]


def _assert_deleted(response) -> None:
    """AC-P15 + AC-P16: a delete answers **200 with a `{"message": ...}` body**.

    `complaint_root_causes.py` is the precedent - it returns
    `service.delete_root_cause(...)`, which is a dict carrying a message. "Void"
    in AC-P16 describes the FRONTEND, which ignores the body; it is not the wire.
    A genuinely empty 200 is a JSON parse error in several HTTP clients (and in
    `extractApiError`'s own `response.json()` path), so the empty variant would
    turn a successful delete into a thrown error on the screen that just did it.
    """
    assert response.status_code == DELETED, response.text
    assert response.content, (
        "The delete answered 200 with an EMPTY body. AC-P16 wants a "
        '`{"message": ...}` payload; an empty 200 throws in a client that parses '
        "the body unconditionally."
    )
    body = response.json()
    assert isinstance(body, dict), f"The delete body is not an object: {body!r}"
    assert isinstance(body.get("message"), str) and body["message"].strip(), (
        f"The delete body carries no non-empty `message`: {body!r}"
    )


def _message(response) -> str:
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        return response.text
    if isinstance(body, dict):
        return str(body.get("message") or body.get("detail") or body)
    return str(body)


def _create_policy(client, **overrides) -> dict:
    with granted(P_ADD):
        response = client.post(POLICIES, json=_policy_body(**overrides))
    assert response.status_code == CREATED, response.text
    return response.json()


def _create_kind(client, **overrides) -> dict:
    with granted(K_ADD):
        response = client.post(KINDS, json=_kind_body(**overrides))
    assert response.status_code == CREATED, response.text
    return response.json()


# =============================================================================
# AC-P1 - a policy is a version and a dated window
# =============================================================================


def test_a_policy_carries_a_version_a_start_and_an_optional_end(client):
    """AC-P1. `effective_to` is genuinely optional - the policy in force today has
    no end, and a sentinel like 9999-12-31 puts a magic value in every comparison."""
    created = _create_policy(client, effective_from="2026-03-01", effective_to=None)
    assert created["effective_from"] == "2026-03-01"
    assert created["effective_to"] is None
    assert created["version"]

    with granted(P_VIEW):
        fetched = client.get(f"{POLICIES}/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["term_count"] == 0, (
        "PolicyResponse must carry term_count - AC-P13's confirmation names how many "
        "Terms a delete takes with it, and there is no other endpoint that knows."
    )


def test_creating_a_policy_without_a_version_is_a_422(client):
    with granted(P_ADD):
        response = client.post(POLICIES, json=_policy_body(version=None))
    assert response.status_code == 422, response.text


def test_creating_a_policy_without_an_effective_from_is_a_422(client):
    """A policy with no start date can never be "in force on the purchase date", so
    it would silently never match rather than fail."""
    with granted(P_ADD):
        response = client.post(POLICIES, json=_policy_body(effective_from=None))
    assert response.status_code == 422, response.text


def test_a_duplicate_version_in_the_same_company_is_refused(client):
    """AC-P1: (company, version) is unique."""
    first = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01", effective_to="2020-12-31")
    with granted(P_ADD):
        response = client.post(
            POLICIES,
            json=_policy_body(version="ZZT-V15", effective_from="2021-01-01", effective_to=None),
        )
    assert response.status_code == 409, response.text
    assert "ZZT-V15" in _message(response)
    assert first["version"] == "ZZT-V15"


def test_the_same_version_in_a_different_company_is_allowed(client, db):
    """AC-P1. Sorento's Version 15 and Mocha's Version 15 are different documents
    that disagree on durations - a global unique version would force one brand to
    renumber its own published policy."""
    _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    other = _company(db, "mocha")
    with as_company(client, db, other):
        with granted(P_ADD):
            response = client.post(
                POLICIES, json=_policy_body(version="ZZT-V15", effective_from="2020-01-01")
            )
    assert response.status_code == CREATED, response.text


def test_the_policies_list_is_the_shared_list_response_envelope(client):
    """AC-P14, and the one test that OWNS the envelope question for policies.

    `{data, pagination:{total, page, limit}, empty}` - `app/schemas/common.py`'s
    `ListResponse[T]`, which is byte-for-byte what the frontend `DataGrid`'s
    `DataGridApiResponse<T>` already reads. The Phase-1 prototype's `{data, total}`
    would have broken at wiring time: `listPolicies` sends `buildDataGridParams`
    (page / limit / sort / dir / query) and then reads a body that has no
    `pagination`, so the grid would have paged a list it could not count.
    """
    _create_policy(client, version="ZZT-A", effective_from="2020-01-01", effective_to="2020-12-31")
    _create_policy(client, version="ZZT-B", effective_from="2021-01-01")

    with granted(P_VIEW):
        response = client.get(POLICIES, params={"page": 1, "limit": 1})
    assert response.status_code == 200, response.text
    body = response.json()

    assert isinstance(body, dict), f"The policies list is not an envelope: {body!r}"
    assert "data" in body and isinstance(body["data"], list)
    assert "pagination" in body, (
        "The policies list must be ListResponse[PolicyResponse]. Without "
        "`pagination` the DataGrid cannot render a page count for a request it "
        "already sent page and limit on."
    )
    pagination = body["pagination"]
    for key in ("total", "page", "limit"):
        assert key in pagination, f"pagination.{key} is missing: {pagination!r}"
    assert pagination["page"] == 1 and pagination["limit"] == 1
    assert pagination["total"] >= 2, (
        "`total` is the count of the whole filtered set, not of the page - a total "
        "that equals the page size makes every grid claim it is on its last page."
    )
    assert len(body["data"]) == 1, "limit=1 returned more than one row."


def test_the_policy_list_shows_only_the_active_companys_policies(client, db):
    """AC-P10's premise. `WarrantyPolicy` is company-scoped and the scope listener
    does the filtering; a route that re-filters by hand is a second copy of the rule
    that can disagree with the first."""
    _create_policy(client, version="ZZT-SORENTO", effective_from="2020-01-01")
    other = _company(db, "mocha")
    with as_company(client, db, other):
        with granted(P_ADD):
            client.post(POLICIES, json=_policy_body(version="ZZT-MOCHA", effective_from="2020-01-01"))
        with granted(P_VIEW):
            listing = client.get(POLICIES, params={"limit": 100})
        assert listing.status_code == 200, listing.text
        versions = {row["version"] for row in _rows(listing)}
    assert "ZZT-MOCHA" in versions
    assert "ZZT-SORENTO" not in versions


# =============================================================================
# AC-P2 / AC-P2b - the overlap arithmetic, on the boundary day
# =============================================================================


def test_two_policies_that_merely_touch_are_allowed(client):
    """AC-P2b. Both ends INCLUSIVE, so [2020-01-01, 2020-12-31] and
    [2021-01-01, ...) share no day. Refusing this would make publishing the next
    version impossible without leaving a calendar hole, and a hole is an `unknown`
    verdict handed to a real customer."""
    _create_policy(client, version="ZZT-A", effective_from="2020-01-01", effective_to="2020-12-31")
    with granted(P_ADD):
        response = client.post(
            POLICIES, json=_policy_body(version="ZZT-B", effective_from="2021-01-01")
        )
    assert response.status_code == CREATED, response.text


def test_two_policies_sharing_exactly_one_day_are_refused(client):
    """AC-P2b, the boundary from the other side. One shared day makes "the version
    in force on the purchase date" arbitrary for that day."""
    _create_policy(client, version="ZZT-A", effective_from="2020-01-01", effective_to="2020-12-31")
    with granted(P_ADD):
        response = client.post(
            POLICIES, json=_policy_body(version="ZZT-B", effective_from="2020-12-31")
        )
    assert response.status_code == OVERLAP_REFUSED, response.text


def test_the_overlap_refusal_names_the_other_version_and_its_range(client):
    """AC-P2b: "overlaps an existing policy" is not something an admin can act on.

    The message has to carry the version AND both ends, because the admin's next
    action is to pick a date, and they cannot pick one they were not told."""
    _create_policy(client, version="ZZT-INCUMBENT", effective_from="2020-01-01", effective_to="2020-12-31")
    with granted(P_ADD):
        response = client.post(
            POLICIES, json=_policy_body(version="ZZT-NEW", effective_from="2020-06-01")
        )
    assert response.status_code == OVERLAP_REFUSED, response.text
    message = _message(response)
    assert "ZZT-INCUMBENT" in message, f"The refusal does not name the other version: {message}"
    assert "2020-01-01" in message, f"The refusal does not name the range start: {message}"
    assert "2020-12-31" in message, f"The refusal does not name the range end: {message}"


def test_an_open_ended_policy_overlaps_everything_after_its_start(client):
    """AC-P2b: NULL `effective_to` is open-ended, i.e. `coalesce(to, infinity)`.
    Treating NULL as "no end date to compare" lets a second policy be published on
    top of the one currently in force, silently."""
    _create_policy(client, version="ZZT-OPEN", effective_from="2020-01-01", effective_to=None)
    with granted(P_ADD):
        response = client.post(
            POLICIES,
            json=_policy_body(version="ZZT-LATER", effective_from="2030-01-01", effective_to="2030-12-31"),
        )
    assert response.status_code == OVERLAP_REFUSED, response.text
    assert "ZZT-OPEN" in _message(response)


def test_a_window_ending_the_day_before_an_open_ended_policy_starts_is_allowed(client):
    """The other boundary of the open-ended case, and the shape Supersede produces."""
    _create_policy(client, version="ZZT-OPEN", effective_from="2020-01-01", effective_to=None)
    with granted(P_ADD):
        response = client.post(
            POLICIES,
            json=_policy_body(version="ZZT-PRIOR", effective_from="1990-01-01", effective_to="2019-12-31"),
        )
    assert response.status_code == CREATED, response.text


def test_a_window_ending_on_the_day_an_open_ended_policy_starts_is_refused(client):
    _create_policy(client, version="ZZT-OPEN", effective_from="2020-01-01", effective_to=None)
    with granted(P_ADD):
        response = client.post(
            POLICIES,
            json=_policy_body(version="ZZT-PRIOR", effective_from="1990-01-01", effective_to="2020-01-01"),
        )
    assert response.status_code == OVERLAP_REFUSED, response.text


def test_policies_of_different_companies_never_overlap_each_other(client, db):
    """AC-P2b. Sorento's window and Mocha's window are answers to different
    questions; an overlap check that ignores the company refuses Mocha's first
    policy because Sorento already published one."""
    _create_policy(client, version="ZZT-SORENTO", effective_from="2020-01-01", effective_to=None)
    other = _company(db, "mocha")
    with as_company(client, db, other):
        with granted(P_ADD):
            response = client.post(
                POLICIES,
                json=_policy_body(version="ZZT-MOCHA", effective_from="2020-06-01", effective_to=None),
            )
    assert response.status_code == CREATED, response.text


def test_editing_a_policy_into_an_overlap_is_refused_too(client):
    """The guard belongs to the value, not to the verb. A PATCH that only checks
    the version leaves the same arbitrary answer one edit away."""
    _create_policy(client, version="ZZT-A", effective_from="2020-01-01", effective_to="2020-12-31")
    later = _create_policy(client, version="ZZT-B", effective_from="2021-01-01", effective_to=None)
    with granted(P_EDIT):
        response = client.patch(f"{POLICIES}/{later['id']}", json={"effective_from": "2020-06-01"})
    assert response.status_code == OVERLAP_REFUSED, response.text
    assert "ZZT-A" in _message(response)


def test_a_policy_does_not_overlap_itself(client):
    """The commonest false positive: PATCHing the policy_text of an open-ended
    policy re-runs the overlap check, finds the row itself, and refuses an edit that
    changed no date at all."""
    policy = _create_policy(client, version="ZZT-A", effective_from="2020-01-01", effective_to=None)
    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{policy['id']}", json={"policy_text": f"{TEST_PREFIX} amended"}
        )
    assert response.status_code == UPDATED, response.text
    assert response.json()["policy_text"] == f"{TEST_PREFIX} amended", (
        "AC-P15: PATCH answers 200 with the ROW. A bare 200 forces the FE to refetch "
        "before it can render what it just saved."
    )
    assert response.json()["id"] == policy["id"]


def test_an_effective_to_before_the_effective_from_is_a_422(client):
    """A window that ends before it starts matches nothing and reads as a typo
    nowhere."""
    with granted(P_ADD):
        response = client.post(
            POLICIES,
            json=_policy_body(effective_from="2026-01-01", effective_to="2025-01-01"),
        )
    assert response.status_code == 422, response.text


# =============================================================================
# AC-P2a - Supersede, in one transaction
# =============================================================================


def test_supersede_closes_the_incumbent_the_day_before_and_creates_the_new_policy(client, db):
    """AC-P2a. AC-P2's refusal is right and, alone, turns the screen's main job -
    publishing version N+1 - into a two-step performed in the correct order."""
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01", effective_to=None)

    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
        )
    assert response.status_code == CREATED, response.text
    body = response.json()
    assert body["closed"]["id"] == incumbent["id"]
    assert body["closed"]["effective_to"] == "2025-12-31", (
        "The incumbent must be closed the day BEFORE the new one starts. Closing it "
        "ON that day leaves both in force for a day; closing it a day earlier leaves "
        "a hole."
    )
    assert body["created"]["version"] == "ZZT-V16"
    assert body["created"]["effective_from"] == "2026-01-01"

    db.expire_all()
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == incumbent["id"]).one()
    assert row.effective_to == date(2025, 12, 31)


def test_a_failed_supersede_leaves_the_incumbent_open(client, db):
    """AC-P2a: ONE transaction. Half a supersede is the worst state of the three -
    the old policy has been closed and no policy governs anything after that day, so
    every purchase from then on answers `unknown`.

    The second half is made to fail on a duplicate version, which is a refusal the
    admin can actually provoke by hand.
    """
    _policy_row(db, effective_from=date(1990, 1, 1), effective_to=date(1999, 12, 31), version="ZZT-TAKEN")
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01", effective_to=None)

    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-TAKEN", effective_from="2026-01-01"),
        )
    assert response.status_code == 409, response.text

    db.expire_all()
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == incumbent["id"]).one()
    assert row.effective_to is None, (
        "The incumbent was closed even though the new policy was refused. That is a "
        "half-superseded state: no policy is in force after 2025-12-31."
    )
    assert (
        db.query(WarrantyPolicy).filter(WarrantyPolicy.version == "ZZT-V16").first() is None
    )


def test_superseding_a_policy_outside_the_company_scope_is_a_404(client, db):
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    other = _company(db, "mocha")
    with as_company(client, db, other):
        with granted(P_ADD):
            response = client.post(
                f"{POLICIES}/{incumbent['id']}/supersede",
                json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
            )
    assert response.status_code == 404, response.text


def test_superseding_an_already_closed_policy_is_a_422(client, db):
    """AC-P21. Supersede sets the incumbent's `effective_to` to the day before the
    new start. Run against a policy that ALREADY has an end date, it either rewrites
    a closed window or opens a calendar gap - and a gap is an `unknown` verdict
    handed to a customer for no reason (the engine's own ruling).

    AC-P2a only ever said "Given an OPEN-ENDED policy in force".
    """
    incumbent = _create_policy(
        client, version="ZZT-V15", effective_from="2020-01-01", effective_to="2020-12-31"
    )
    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
        )
    assert response.status_code == 422, response.text

    db.expire_all()
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == incumbent["id"]).one()
    assert row.effective_to == date(2020, 12, 31), "The closed window was rewritten."
    assert db.query(WarrantyPolicy).filter(WarrantyPolicy.version == "ZZT-V16").first() is None


@pytest.mark.parametrize(
    "new_from,why",
    [
        ("2020-01-01", "the same day the incumbent starts"),
        ("2019-06-01", "before the incumbent starts"),
    ],
)
def test_superseding_from_a_date_at_or_before_the_incumbents_start_is_a_422(
    client, db, new_from, why
):
    """AC-P21, the case the overlap check can never catch.

    `effective_to = new_from - 1 day` would land BEFORE the incumbent's own
    `effective_from`: an inverted window. An inverted range overlaps nothing, so
    AC-P2b's guard reports no conflict and the policy silently governs no day at all.
    """
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from=new_from),
        )
    assert response.status_code == 422, f"{why}: {response.text}"

    db.expire_all()
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == incumbent["id"]).one()
    assert row.effective_from == date(2020, 1, 1)
    assert row.effective_to is None, f"{why}: the incumbent was closed anyway."


def test_superseding_a_closed_policy_names_the_version_that_closed_it(client):
    """AC-P26. The refusal has to be actionable, or the ruling collapses into "no".

    The successor is DERIVABLE - it is the policy whose window begins the day after
    this one ends - which is exactly why AC-P26 needs no predecessor column. If the
    message cannot name it, the admin is told they may not do the thing and not what
    to do instead, and that is the failure AC-P2a already exists to prevent once.
    """
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    with granted(P_ADD):
        first = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
        )
    assert first.status_code == CREATED, first.text

    with granted(P_ADD):
        again = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V17", effective_from="2027-01-01"),
        )
    assert again.status_code == 422, again.text
    message = _message(again)
    assert "ZZT-V16" in message, (
        "The refusal does not name the version that closed this one: " + message
    )


def test_reopening_a_superseded_policy_names_the_successor_and_says_to_delete_it(client):
    """AC-P26. This is the dead end the ruling is about: the admin mis-dated a
    supersede, tries to reopen the incumbent, and the overlap guard correctly
    refuses because the successor really does overlap.

    Relaxing the guard would be wrong. Naming the way out is the whole fix, so the
    message is the contract: the successor's version, and the instruction to delete
    it first.
    """
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    with granted(P_ADD):
        client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
        )

    with granted(P_EDIT):
        reopen = client.patch(f"{POLICIES}/{incumbent['id']}", json={"effective_to": None})
    assert reopen.status_code == OVERLAP_REFUSED, reopen.text
    message = _message(reopen)
    assert "ZZT-V16" in message, f"The refusal does not name the successor: {message}"
    assert "delete" in message.lower(), (
        "The refusal does not say to delete the successor first. AC-P26 has no undo "
        f"endpoint precisely because this sentence exists: {message}"
    )


def test_the_two_step_recovery_from_a_misdated_supersede_works_end_to_end(client, db):
    """AC-P26, and the test that decides whether the ruling is right at all.

    Supersede with the wrong date, delete the successor (which loses nothing - a
    freshly superseded policy has no Terms yet), then reopen the incumbent. If the
    third step is refused, there IS no recovery path and the ruling needs an undo
    endpoint after all.

    Note for the implementer: step three sends `{"effective_to": null}`. Every
    `XUpdate` schema in this repo is all-Optional, so "set it to null" and "did not
    mention it" arrive identically unless the route distinguishes them
    (`model_dump(exclude_unset=True)`). A PATCH that cannot clear a nullable column
    makes this path impossible while every other test in the file still passes.
    """
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    with granted(P_ADD):
        superseded = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
        )
    assert superseded.status_code == CREATED, superseded.text
    successor_id = superseded.json()["created"]["id"]

    with granted(P_DELETE):
        removed = client.delete(f"{POLICIES}/{successor_id}")
    _assert_deleted(removed)

    with granted(P_EDIT):
        reopened = client.patch(f"{POLICIES}/{incumbent['id']}", json={"effective_to": None})
    assert reopened.status_code == UPDATED, (
        "Step three of AC-P26's recovery was refused, so there is no way back from a "
        f"mis-dated supersede: {reopened.text}"
    )
    assert reopened.json()["effective_to"] is None

    db.expire_all()
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == incumbent["id"]).one()
    assert row.effective_to is None, "The incumbent is still closed in the database."
    assert row.effective_from == date(2020, 1, 1), "Reopening moved the start date."


def test_superseding_needs_the_add_permission(client):
    incumbent = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    with granted(P_VIEW):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(version="ZZT-V16", effective_from="2026-01-01"),
        )
    assert response.status_code == 403, response.text


# =============================================================================
# AC-P13 - deleting a policy takes its terms, and says how many
# =============================================================================


def test_a_policy_reports_how_many_terms_a_delete_would_take(client, db):
    """AC-P13. "A count is the difference between a considered delete and a
    discovered one."

    Read from the row, not from a preview endpoint: neither the plan nor the
    prototype has one, and the prototype's delete helper returns void - so
    `term_count` on the policy IS the confirmation dialog's source.
    """
    policy = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy["id"]).one()
    kind = _kind_row(db, "wc")
    _term_row(db, row, kind, "Ceramic Body", is_lifetime=True)
    _term_row(db, row, kind, "Flushing Fittings", duration_months=60)

    with granted(P_VIEW):
        detail = client.get(f"{POLICIES}/{policy['id']}")
        listing = client.get(POLICIES, params={"limit": 100})
    assert detail.status_code == 200, detail.text
    assert detail.json()["term_count"] == 2
    listed = {r["id"]: r for r in _rows(listing)}[policy["id"]]
    assert listed["term_count"] == 2, (
        "term_count must be on the LIST row too - the delete is offered from the "
        "grid, and a dialog that has to fetch the row first shows the count late "
        "or not at all."
    )


def test_deleting_a_policy_cascades_its_terms(client, db):
    """AC-P13. Terms have no life apart from their Policy."""
    policy = _create_policy(client, version="ZZT-V15", effective_from="2020-01-01")
    row = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy["id"]).one()
    kind = _kind_row(db, "wc")
    _term_row(db, row, kind, "Ceramic Body", is_lifetime=True)
    _term_row(db, row, kind, "Flushing Fittings", duration_months=60)

    with granted(P_DELETE):
        response = client.delete(f"{POLICIES}/{policy['id']}")
    _assert_deleted(response)

    db.expire_all()
    assert db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy["id"]).first() is None
    assert db.query(WarrantyTerm).filter(WarrantyTerm.policy_id == policy["id"]).count() == 0


def test_deleting_a_policy_needs_the_delete_permission(client):
    policy = _create_policy(client)
    with granted(P_EDIT):
        response = client.delete(f"{POLICIES}/{policy['id']}")
    assert response.status_code == 403, response.text


def test_deleting_a_policy_outside_the_company_scope_is_a_404(client, db):
    policy = _create_policy(client)
    other = _company(db, "mocha")
    with as_company(client, db, other):
        with granted(P_DELETE):
            response = client.delete(f"{POLICIES}/{policy['id']}")
    assert response.status_code == 404, response.text
    db.expire_all()
    assert db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy["id"]).first() is not None


# =============================================================================
# AC-P3 / AC-P3a - one Term, one part, one promise
# =============================================================================


def test_a_term_names_one_kind_one_part_and_a_duration(client, db):
    """AC-P3."""
    policy = _create_policy(client)
    kind = _kind_row(db, "wc")
    defect = _defect_type(db, "Cracking")

    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{policy['id']}/terms",
            json=_term_body(
                kind.id,
                part_name="Ceramic Body",
                duration_months=None,
                is_lifetime=True,
                installation_included=True,
                covered_defect_type_ids=[defect],
                registration_bonus_months=12,
            ),
        )
    assert response.status_code == CREATED, response.text
    body = response.json()
    assert body["kind_id"] == kind.id
    assert body["part_name"] == "Ceramic Body"
    assert body["is_lifetime"] is True
    assert body["installation_included"] is True
    assert body["covered_defect_type_ids"] == [defect]
    assert body["registration_bonus_months"] == 12


@pytest.mark.parametrize(
    "duration_months,is_lifetime,why",
    [
        (60, True, "both a duration and lifetime"),
        (None, False, "neither a duration nor lifetime"),
        (0, False, "a zero-month duration"),
        (-12, False, "a negative duration"),
    ],
)
def test_a_term_must_be_lifetime_or_a_positive_duration_never_both_never_neither(
    client, db, duration_months, is_lifetime, why
):
    """AC-P3 / AC-P3a. A term with neither answers `unknown` on every complaint
    forever (the engine's own ruling); a term with zero months tells the customer
    their cover expired on the day they bought it."""
    policy = _create_policy(client)
    kind = _kind_row(db, "wc")
    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{policy['id']}/terms",
            json=_term_body(kind.id, duration_months=duration_months, is_lifetime=is_lifetime),
        )
    assert response.status_code == 422, f"{why} was accepted: {response.text}"


def test_editing_a_term_into_an_invalid_duration_is_refused_too(client, db):
    """The XOR belongs to the value, not to the verb."""
    policy = _create_policy(client)
    kind = _kind_row(db, "wc")
    with granted(P_ADD):
        created = client.post(
            f"{POLICIES}/{policy['id']}/terms", json=_term_body(kind.id, duration_months=60)
        )
    assert created.status_code == CREATED, created.text
    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{policy['id']}/terms/{created.json()['id']}",
            json={"is_lifetime": True},
        )
    assert response.status_code == 422, (
        "Setting is_lifetime on a term that still has 60 months left both fields "
        f"populated: {response.text}"
    )


def test_two_terms_for_the_same_kind_and_part_are_refused(client, db):
    """AC-P3: (policy_id, kind_id, part_name) is unique. Two rows for one part is
    two expiries for one promise, and `resolve` returns both."""
    policy = _create_policy(client)
    kind = _kind_row(db, "wc")
    with granted(P_ADD):
        first = client.post(
            f"{POLICIES}/{policy['id']}/terms",
            json=_term_body(kind.id, part_name="Ceramic Body", duration_months=60),
        )
        second = client.post(
            f"{POLICIES}/{policy['id']}/terms",
            json=_term_body(kind.id, part_name="Ceramic Body", duration_months=24),
        )
    assert first.status_code == CREATED, first.text
    assert second.status_code == 409, second.text


def test_a_term_pointing_at_a_kind_that_does_not_exist_is_refused(client, db):
    """`warranty_terms.kind_id` is a real FK. A route that lets the constraint
    raise gets a 500 and an aborted transaction instead of a message."""
    policy = _create_policy(client)
    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{policy['id']}/terms", json=_term_body(str(uuid.uuid4()))
        )
    assert response.status_code in (404, 422), response.text


def test_creating_a_term_needs_the_policies_add_permission(client, db):
    """AC-P11: Terms ride the POLICIES slug. There is no `warranty.terms.*`."""
    policy = _create_policy(client)
    kind = _kind_row(db, "wc")
    with granted(P_VIEW, K_ADD):
        response = client.post(
            f"{POLICIES}/{policy['id']}/terms", json=_term_body(kind.id)
        )
    assert response.status_code == 403, response.text


# =============================================================================
# AC-P4 - every Term of a Kind, together
# =============================================================================


def test_terms_can_be_read_grouped_by_kind(client, db):
    """AC-P4, seeded with the real Water Closet case: three Terms under one Kind
    that disagree on lifetime, duration, defect scope AND installation.

    A screen that shows one at a time cannot be checked against the policy document,
    which is the only way anybody knows the configuration is right.
    """
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    wc = _kind_row(db, "watercloset")
    pump = _kind_row(db, "boosterpump")
    crack = _defect_type(db, "Cracking")

    _term_row(db, policy, wc, "Ceramic Body", is_lifetime=True, installation_included=True,
              covered_defect_type_ids=[crack])
    _term_row(db, policy, wc, "Flushing Fittings", duration_months=60)
    _term_row(db, policy, wc, "Seat Cover Soft Close", duration_months=24)
    _term_row(db, policy, pump, "Pump", duration_months=24, registration_bonus_months=12)

    with granted(P_VIEW):
        response = client.get(f"{POLICIES}/{policy.id}/terms", params={"group_by": "kind"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("groups") is not None, (
        "?group_by=kind must return `groups` - the prototype's "
        "`WarrantyTermsGrouped` is `{groups, total}` and `listTermsGroupedByKind` "
        "reads nothing else. AC-P4 is about seeing a Kind's Terms TOGETHER; a flat "
        "list the FE regroups is the same screen with the bug moved."
    )
    groups = {g["kind"]["id"]: g for g in body["groups"]}
    assert set(groups) == {wc.id, pump.id}
    wc_parts = {t["part_name"] for t in groups[wc.id]["terms"]}
    assert wc_parts == {"Ceramic Body", "Flushing Fittings", "Seat Cover Soft Close"}
    assert len(groups[pump.id]["terms"]) == 1

    ceramic = next(t for t in groups[wc.id]["terms"] if t["part_name"] == "Ceramic Body")
    fittings = next(t for t in groups[wc.id]["terms"] if t["part_name"] == "Flushing Fittings")
    assert ceramic["is_lifetime"] is True and fittings["is_lifetime"] is False
    assert ceramic["installation_included"] is True and fittings["installation_included"] is False
    assert ceramic["covered_defect_type_ids"] == [crack]
    assert fittings["covered_defect_type_ids"] in (None, [])


def test_the_ungrouped_terms_route_still_answers(client, db):
    """The plan writes `?group_by=kind` as an OPTION, so the bare route exists.

    The prototype only ever calls the grouped form, which is why this is asserted
    loosely - the rows are the contract, the wrapper is not.
    """
    policy = _create_policy(client)
    kind = _kind_row(db, "wc")
    _term_row(db, db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy["id"]).one(),
              kind, "Ceramic Body", is_lifetime=True)

    with granted(P_VIEW):
        flat = client.get(f"{POLICIES}/{policy['id']}/terms")
    assert flat.status_code == 200, flat.text
    assert len(_rows(flat)) == 1


def test_a_policy_with_no_terms_returns_an_empty_group_list_not_a_404(client):
    """The CRUD standard: every section renders, with an explicit empty state. A 404
    here would make a brand-new policy look broken."""
    policy = _create_policy(client)
    with granted(P_VIEW):
        response = client.get(f"{POLICIES}/{policy['id']}/terms", params={"group_by": "kind"})
    assert response.status_code == 200, response.text
    assert response.json()["groups"] == []


# =============================================================================
# AC-P9 - a nested Term route is the only thing scoping Terms at all
# =============================================================================


@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_terms_of_another_companys_policy_are_a_404(client, db, method):
    """AC-P9. `WarrantyTerm` is deliberately NOT company-scoped - it is only ever
    reachable through `policy_id` - which makes an unguarded nested route hand
    another company's warranty terms to anyone who guesses an id.

    The Policy must be loaded FIRST, under the caller's scope. Filtering the terms
    by hand instead would still 200 with an empty list, which is a different bug
    wearing the same result on the happy path.
    """
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    kind = _kind_row(db, "wc")
    term = _term_row(db, policy, kind, "Ceramic Body", is_lifetime=True)
    other = _company(db, "mocha")

    with as_company(client, db, other):
        with granted(P_VIEW, P_ADD, P_EDIT, P_DELETE):
            if method == "get":
                response = client.get(f"{POLICIES}/{policy.id}/terms")
            elif method == "post":
                response = client.post(
                    f"{POLICIES}/{policy.id}/terms", json=_term_body(kind.id, part_name="Sneak")
                )
            elif method == "patch":
                response = client.patch(
                    f"{POLICIES}/{policy.id}/terms/{term.id}", json={"duration_months": 999}
                )
            else:
                response = client.delete(f"{POLICIES}/{policy.id}/terms/{term.id}")

    assert response.status_code == 404, f"{method.upper()} leaked: {response.text}"

    db.expire_all()
    survivor = db.query(WarrantyTerm).filter(WarrantyTerm.id == term.id).first()
    assert survivor is not None, "The cross-company DELETE went through."
    assert survivor.duration_months is None, "The cross-company PATCH went through."


def test_a_term_belonging_to_another_policy_is_a_404(client, db):
    """The second half of the same hazard: the right company, the wrong parent. A
    route that loads the term by id alone edits a term under a policy the URL never
    named."""
    first = _create_policy(client, version="ZZT-A", effective_from="2020-01-01", effective_to="2020-12-31")
    second = _create_policy(client, version="ZZT-B", effective_from="2021-01-01")
    kind = _kind_row(db, "wc")
    term = _term_row(
        db, db.query(WarrantyPolicy).filter(WarrantyPolicy.id == first["id"]).one(),
        kind, "Ceramic Body", is_lifetime=True,
    )
    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{second['id']}/terms/{term.id}", json={"duration_months": 12}
        )
    assert response.status_code == 404, response.text


# =============================================================================
# AC-P8 / AC-P8a - configuration never rewrites history
# =============================================================================


def test_editing_a_term_does_not_recompute_existing_assessments(client, db):
    """AC-P8. An assessment is what was decided at the time. Silently rewriting it
    is how a verdict a consumer was TOLD stops matching the record."""
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    kind = _kind_row(db, "wc")
    term = _term_row(db, policy, kind, "Seat Cover Soft Close", duration_months=24)
    assessment = _assessment(db, term, verdict="covered", expiry=date(2027, 10, 16))
    before = (
        assessment.computed_verdict,
        assessment.computed_expiry,
        assessment.part_name,
        assessment.policy_version,
        assessment.computed_at,
    )

    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{policy.id}/terms/{term.id}",
            json={"duration_months": 120, "part_name": "Seat Cover"},
        )
    assert response.status_code == UPDATED, response.text
    assert response.json()["duration_months"] == 120, "AC-P15: PATCH answers with the row."

    db.expire_all()
    row = db.query(WarrantyAssessment).filter(WarrantyAssessment.id == assessment.id).one()
    assert (
        row.computed_verdict,
        row.computed_expiry,
        row.part_name,
        row.policy_version,
        row.computed_at,
    ) == before, "Editing a term rewrote a stored verdict."


def test_deleting_a_term_leaves_its_assessments_standing(client, db):
    """AC-P8a. `warranty_assessments.term_id` is ON DELETE SET NULL and the snapshot
    columns keep the verdict readable without it. A CASCADE here would delete the
    evidence behind an answer a human already acted on."""
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    kind = _kind_row(db, "wc")
    term = _term_row(db, policy, kind, "Seat Cover Soft Close", duration_months=24)
    assessment = _assessment(db, term, verdict="expired", expiry=date(2027, 10, 16))

    with granted(P_DELETE):
        response = client.delete(f"{POLICIES}/{policy.id}/terms/{term.id}")
    _assert_deleted(response)

    db.expire_all()
    row = db.query(WarrantyAssessment).filter(WarrantyAssessment.id == assessment.id).one()
    assert row.term_id is None
    assert row.computed_verdict == "expired"
    assert row.computed_expiry == date(2027, 10, 16)
    assert row.part_name == "Seat Cover Soft Close"
    assert row.policy_version == policy.version


def test_the_term_delete_names_how_many_assessments_reference_it(client, db):
    """AC-P8a: "The delete confirmation names how many assessments reference the
    Term", per the repo's confirm-before-destroy rule. The count has to come from
    the API - the FE cannot see `warranty_assessments` at all."""
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    kind = _kind_row(db, "wc")
    term = _term_row(db, policy, kind, "Seat Cover Soft Close", duration_months=24)
    _assessment(db, term)
    _assessment(db, term)

    with granted(P_VIEW):
        grouped = client.get(f"{POLICIES}/{policy.id}/terms", params={"group_by": "kind"})
        flat = client.get(f"{POLICIES}/{policy.id}/terms")
    assert grouped.status_code == 200, grouped.text
    assert flat.status_code == 200, flat.text

    terms = grouped.json()["groups"][0]["terms"]
    assert terms[0]["assessment_count"] == 2, (
        "TermResponse must carry assessment_count (AC-P16) - AC-P8a's confirmation "
        "has nowhere else to read it, and the delete endpoint is void."
    )
    assert {t["id"]: t for t in _rows(flat)}[term.id]["assessment_count"] == 2, (
        "assessment_count must be on the ungrouped term row too. A count that "
        "appears in one of two representations of the same row is a count the "
        "dialog gets sometimes."
    )

    with granted(P_DELETE):
        response = client.delete(f"{POLICIES}/{policy.id}/terms/{term.id}")
    _assert_deleted(response)


# =============================================================================
# AC-P7 / AC-P7a - the two counts that make the hole visible
# =============================================================================


def test_the_kinds_list_carries_both_counts_and_both_are_correct(client, db):
    """AC-P7 + AC-P7a. This is the whole point of the slice: 29 of 31 Kinds are
    unreachable today and nothing anywhere says so."""
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    reachable = _kind_row(db, "reachable")
    _rule_row(db, reachable, "model_prefix", "SRTWC")
    _rule_row(db, reachable, "category", "SRT-WC")
    _term_row(db, policy, reachable, "Ceramic Body", is_lifetime=True)

    with granted(K_VIEW):
        response = client.get(KINDS, params={"limit": 200})
    assert response.status_code == 200, response.text
    rows = {r["id"]: r for r in _rows(response)}
    assert rows[reachable.id]["rule_count"] == 2
    assert rows[reachable.id]["term_count"] == 1


def test_a_kind_no_rule_reaches_is_flagged_in_the_payload(client, db):
    """AC-P7. "A Kind no rule reaches can never be assessed, and that is invisible
    today." A flag computed in a grid cell is visible in exactly one place."""
    orphan = _kind_row(db, "orphan")
    with granted(K_VIEW):
        response = client.get(KINDS, params={"limit": 200})
    assert response.status_code == 200, response.text
    row = {r["id"]: r for r in _rows(response)}[orphan.id]
    assert row["rule_count"] == 0
    assert row["has_no_rules"] is True, (
        "AC-P7a's zero must be a field, not a colour. Export, MCP and the AI "
        "assistant all read this payload and none of them can see a Tailwind class."
    )


def test_a_kind_no_term_covers_is_flagged_too(client, db):
    """AC-P7a. A Kind that no Term covers returns `no_term` for every product that
    reaches it - the same invisible dead end one column further along."""
    kind = _kind_row(db, "ruled-but-uncovered")
    _rule_row(db, kind, "model_prefix", "SRTWC")

    with granted(K_VIEW):
        response = client.get(KINDS, params={"limit": 200})
    assert response.status_code == 200, response.text
    row = {r["id"]: r for r in _rows(response)}[kind.id]
    assert row["rule_count"] == 1
    assert row["has_no_rules"] is False
    assert row["term_count"] == 0
    assert row["has_no_terms"] is True


def test_the_kind_select_endpoint_returns_id_code_and_name(client, db):
    """The dropdown feed the Term and Rule editors both need. Cursor rule: no UUIDs
    in the UI, so the picker has to carry the human-readable pair."""
    kind = _kind_row(db, "wc")
    with granted(K_VIEW):
        response = client.get(f"{KINDS}/select")
    assert response.status_code == 200, response.text
    match = next(r for r in _rows(response) if r["id"] == kind.id)
    assert match["code"] == kind.code
    assert match["name"] == kind.name


def test_the_shared_vocabulary_lists_are_bare_arrays(client, db):
    """The one test that OWNS the envelope question for kinds and rules.

    AC-P14: policies are the ONLY `ListResponse[T]`; kinds, kinds-select,
    kind-rules and defect-types are bare arrays. They are the shared vocabulary -
    tens of rows, no server-side paging, and four frontend call sites that cast the
    body straight to an array.
    """
    kind = _kind_row(db, "wc")
    _rule_row(db, kind, "model_prefix", "SRTWC")
    with granted(K_VIEW):
        kinds = client.get(KINDS)
        select = client.get(f"{KINDS}/select")
        rules = client.get(RULES)
    with granted(P_VIEW):
        defects = client.get(f"{BASE}/defect-types")
    for name, response in (
        ("kinds", kinds),
        ("kinds/select", select),
        ("kind-rules", rules),
        ("defect-types", defects),
    ):
        assert response.status_code == 200, f"{name}: {response.text}"
        assert isinstance(response.json(), list), (
            f"GET {name} returned {type(response.json()).__name__}, not a bare array. "
            "The prototype casts the body straight to an array and never reads a "
            "wrapper."
        )


def test_creating_a_kind_with_a_duplicate_code_is_refused(client):
    """`warranty_product_kinds.code` is the seed's idempotence key - NOT NULL and
    UNIQUE, or a re-run inserts duplicates."""
    kind = _create_kind(client)
    with granted(K_ADD):
        response = client.post(KINDS, json=_kind_body(code=kind["code"]))
    assert response.status_code == 409, response.text


def test_creating_a_kind_without_a_code_is_a_422(client):
    with granted(K_ADD):
        response = client.post(KINDS, json=_kind_body(code=None))
    assert response.status_code == 422, response.text


def test_reading_the_kinds_list_needs_the_kinds_view_permission(client):
    with granted(P_VIEW):
        response = client.get(KINDS)
    assert response.status_code == 403, response.text


# =============================================================================
# The defect-type picker - a route the plan's contract omits
# =============================================================================


def test_the_defect_type_picker_returns_lookup_option_ids_and_labels(client, db):
    """AC-P3's "optional defect-type restriction" needs a picker, and the existing
    `GET /api/v1/lookup/{set_key}/options` cannot serve it: it returns `value` +
    `label` and NOT `lookup_options.id`, which is what the `uuid[]` column stores.

    Named by the Phase-1 prototype (`listDefectTypes` -> `GET /defect-types`) and
    ABSENT from the plan's pinned contract - reported, and gated here so it is not
    quietly dropped as un-specified.
    """
    lookup_set = LookupSet(
        id=str(uuid.uuid4()), set_key="complaints_defect_type", name=f"{TEST_PREFIX} defect types"
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(
        id=str(uuid.uuid4()),
        set_id=lookup_set.id,
        value=f"{TEST_PREFIX}-cracking",
        label="Cracking",
        sort_order=0,
    )
    db.add(option)
    db.flush()

    with granted(P_VIEW):
        response = client.get(f"{BASE}/defect-types")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list)
    match = next(r for r in rows if r["id"] == option.id)
    assert match["label"] == "Cracking", (
        "The picker must return lookup_options.id, not its `value` - the uuid[] "
        "column stores ids, and a varchar compared to a uuid column matches nothing."
    )


def test_the_defect_type_picker_denies_a_principal_holding_nothing(client):
    with granted():
        response = client.get(f"{BASE}/defect-types")
    assert response.status_code == 403, response.text


# =============================================================================
# AC-P12 - a master-data delete must not rewrite the policy document
# =============================================================================


def test_the_kind_foreign_keys_really_do_cascade():
    """AC-P12's premise, asserted before the refusal that depends on it.

    If these FKs ever stop cascading, the refusal below becomes belt-and-braces and
    a reviewer will delete it as redundant. They cascade: an unguarded hard delete
    of one Kind removes warranty promises from EVERY policy at once, and the
    assessments that quoted them keep a snapshot pointing at a term that is gone.
    """
    for model, column in ((WarrantyTerm, "kind_id"), (WarrantyKindRule, "kind_id")):
        fks = list(model.__table__.c[column].foreign_keys)
        assert fks, f"{model.__tablename__}.{column} has no foreign key at all."
        assert fks[0].ondelete == "CASCADE", (
            f"{model.__tablename__}.{column} is ON DELETE {fks[0].ondelete}. AC-P12's "
            "refusal is written against CASCADE; if this changed, re-read the ruling."
        )


def test_deleting_a_kind_is_refused_while_a_term_or_a_rule_references_it(client, db):
    """AC-P12, and the refusal names BOTH counts.

    "1 term is using it" is a message an admin can act on. "Cannot delete" is one
    they escalate.
    """
    policy_body = _create_policy(client)
    policy = db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_body["id"]).one()
    kind = _kind_row(db, "wc")
    _term_row(db, policy, kind, "Ceramic Body", is_lifetime=True)
    _term_row(db, policy, kind, "Flushing Fittings", duration_months=60)
    _rule_row(db, kind, "model_prefix", "SRTWC")

    with granted(K_DELETE):
        response = client.delete(f"{KINDS}/{kind.id}")
    assert response.status_code == 409, response.text
    message = _message(response)
    assert "2" in message, f"The refusal does not name the term count: {message}"
    assert "1" in message, f"The refusal does not name the rule count: {message}"

    db.expire_all()
    assert db.query(WarrantyProductKind).filter(WarrantyProductKind.id == kind.id).first() is not None
    assert db.query(WarrantyTerm).filter(WarrantyTerm.kind_id == kind.id).count() == 2


def test_an_unreferenced_kind_can_be_deleted(client, db):
    """The refusal is about references, not about Kinds. A vocabulary nobody can
    prune fills with typos."""
    kind = _create_kind(client)
    with granted(K_DELETE):
        response = client.delete(f"{KINDS}/{kind['id']}")
    _assert_deleted(response)
    db.expire_all()
    assert db.query(WarrantyProductKind).filter(WarrantyProductKind.id == kind["id"]).first() is None


def test_deleting_a_kind_needs_the_kinds_delete_permission(client, db):
    kind = _create_kind(client)
    with granted(K_EDIT, P_DELETE):
        response = client.delete(f"{KINDS}/{kind['id']}")
    assert response.status_code == 403, response.text


# =============================================================================
# AC-P5 - kind rules, and the four match types
# =============================================================================


@pytest.mark.parametrize("match_type", MATCH_TYPES)
def test_every_declared_match_type_can_be_saved(client, db, match_type):
    """AC-P5."""
    kind = _kind_row(db, "wc")
    with granted(K_ADD):
        response = client.post(RULES, json=_rule_body(kind.id, match_type=match_type))
    assert response.status_code == CREATED, response.text
    assert response.json()["match_type"] == match_type


@pytest.mark.parametrize("match_type", ["colour", "MODEL_PREFIX_TYPO", "", None, "regex"])
def test_an_undeclared_match_type_is_refused_at_write_time(client, db, match_type):
    """AC-P5. The engine already treats an unknown type as matching nothing and logs
    a warning - which means a typo produces a rule that is saved, listed, and inert.
    That is AC-P7's disease with a different cause."""
    kind = _kind_row(db, "wc")
    with granted(K_ADD):
        response = client.post(RULES, json=_rule_body(kind.id, match_type=match_type))
    assert response.status_code == 422, f"{match_type!r} was accepted: {response.text}"


@pytest.mark.parametrize("match_value", ["", "   ", None])
def test_a_rule_with_an_empty_match_value_is_refused(client, db, match_value):
    """The engine's ruling, enforced one layer earlier: an empty `match_value`
    matches NOTHING, so a saved one is a row that can never fire and never explains
    itself. (The engine keeps its own guard - legacy rows already hold `''`.)"""
    kind = _kind_row(db, "wc")
    with granted(K_ADD):
        response = client.post(RULES, json=_rule_body(kind.id, match_value=match_value))
    assert response.status_code == 422, f"{match_value!r} was accepted: {response.text}"


def test_rules_can_be_filtered_by_kind(client, db):
    """The pinned `?kind_id=` - the Rules tab is read one Kind at a time."""
    wc = _kind_row(db, "wc")
    pump = _kind_row(db, "pump")
    _rule_row(db, wc, "model_prefix", "SRTWC")
    _rule_row(db, pump, "model_prefix", "SRTBP")

    with granted(K_VIEW):
        response = client.get(RULES, params={"kind_id": wc.id, "limit": 100})
    assert response.status_code == 200, response.text
    assert {r["kind_id"] for r in _rows(response)} == {wc.id}


def test_editing_and_deleting_a_rule_needs_the_kinds_slugs(client, db):
    """AC-P11: kind rules ride the KINDS slug. There is no `warranty.kind_rules.*`."""
    kind = _kind_row(db, "wc")
    with granted(K_ADD):
        created = client.post(RULES, json=_rule_body(kind.id))
    assert created.status_code == CREATED, created.text
    rule_id = created.json()["id"]

    with granted(K_VIEW):
        denied_edit = client.patch(f"{RULES}/{rule_id}", json={"priority": 5})
    assert denied_edit.status_code == 403

    with granted(K_EDIT):
        allowed_edit = client.patch(f"{RULES}/{rule_id}", json={"priority": 5})
    assert allowed_edit.status_code == UPDATED, allowed_edit.text
    assert allowed_edit.json()["priority"] == 5

    with granted(K_EDIT):
        denied_delete = client.delete(f"{RULES}/{rule_id}")
    assert denied_delete.status_code == 403

    with granted(K_DELETE):
        allowed_delete = client.delete(f"{RULES}/{rule_id}")
    _assert_deleted(allowed_delete)


# =============================================================================
# AC-P6 / AC-P6b / AC-P6c - the tester
# =============================================================================


def test_the_tester_names_the_kind_and_the_rule_that_decided_it(client, db):
    """AC-P6. "So an admin can tell a working mapping from a lucky one before
    saving." A Kind alone cannot make that distinction."""
    kind = _kind_row(db, "wc")
    rule = _rule_row(db, kind, "model_prefix", "SRTWC")

    with granted(K_VIEW):
        response = client.post(f"{RULES}/test", json={"product_code": "SRTWC8152"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolved_kind"]["id"] == kind.id
    assert body["resolved_kind"]["code"] == kind.code
    assert body["deciding_rule"]["id"] == rule.id
    assert body["deciding_rule"]["match_type"] == "model_prefix"
    assert body["deciding_rule"]["is_candidate"] is False


def test_a_product_that_reaches_no_kind_is_a_null_answer_not_an_error(client, db):
    """29 of 31 Kinds are unreachable today, so "nothing matched" is the answer an
    admin will see most often. It has to render as an answer, not as a failure."""
    _kind_row(db, "wc")
    with granted(K_VIEW):
        response = client.post(f"{RULES}/test", json={"product_code": "NOTHINGMATCHES"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolved_kind"] is None
    assert body["deciding_rule"] is None
    assert body["matches"] == []


def test_the_tester_returns_the_whole_ranked_list_in_production_order(client, db):
    """AC-P6c. "A mapping that wins by one tie-break is a different fact from a
    mapping that is the only match, and only the second one is safe to stop thinking
    about." """
    listed = _kind_row(db, "listed")
    prefixed = _kind_row(db, "prefixed")
    categorised = _kind_row(db, "categorised")
    _rule_row(db, listed, "model_list", "SRTWC8152-RL", 0)
    _rule_row(db, prefixed, "model_prefix", "SRTWC", 0)
    _rule_row(db, categorised, "category", "SRT-WC", 5)

    with granted(K_VIEW):
        response = client.post(
            f"{RULES}/test",
            json={"product_code": "SRTWC8152-RL", "category_code": "SRT-WC"},
        )
    assert response.status_code == 200, response.text
    matches = response.json()["matches"]
    assert [m["kind"]["id"] for m in matches] == [categorised.id, listed.id, prefixed.id], (
        "AC-P5/AC-D20: priority first (the category rule at 5), then match-type "
        "specificity (model_list before model_prefix)."
    )
    assert [m["rank"] for m in matches] == [1, 2, 3]
    assert matches[0]["matched_length"] == len("SRT-WC")
    assert response.json()["deciding_rule"]["id"] == matches[0]["rule"]["id"]


def test_the_tester_ranks_an_unsaved_candidate_and_never_saves_it(client, db):
    """AC-P6b. The admin's real question is whether the rule they are ABOUT to write
    will win."""
    incumbent = _kind_row(db, "incumbent")
    challenger = _kind_row(db, "challenger")
    _rule_row(db, incumbent, "category", "SRT-WC", 0)
    before = db.query(WarrantyKindRule).count()

    with granted(K_VIEW):
        response = client.post(
            f"{RULES}/test",
            json={
                "product_code": "SRTWC8152-RL",
                "category_code": "SRT-WC",
                "candidate_rule": {
                    "kind_id": challenger.id,
                    "match_type": "model_list",
                    "match_value": "SRTWC8152-RL",
                    "priority": 0,
                },
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolved_kind"]["id"] == challenger.id
    assert body["deciding_rule"]["is_candidate"] is True
    assert body["deciding_rule"]["id"] is None, (
        "An unsaved rule has no id. Inventing one lets the FE link to a row that "
        "does not exist."
    )
    assert [m["is_candidate"] for m in body["matches"]] == [True, False]

    db.expire_all()
    assert db.query(WarrantyKindRule).count() == before, (
        "The tester persisted the candidate rule. A rule nobody saved would start "
        "deciding real complaints."
    )


def test_a_candidate_rule_with_an_undeclared_match_type_is_a_422(client, db):
    """The tester validates the candidate the same way the create route does, or it
    happily reports that a rule which can never be saved would win."""
    kind = _kind_row(db, "wc")
    with granted(K_VIEW):
        response = client.post(
            f"{RULES}/test",
            json={
                "product_code": "SRTWC8152",
                "candidate_rule": {
                    "kind_id": kind.id,
                    "match_type": "colour",
                    "match_value": "SRTWC",
                    "priority": 0,
                },
            },
        )
    assert response.status_code == 422, response.text


def test_a_saved_rule_with_an_empty_match_value_matches_nothing_through_the_route(client, db):
    """The engine's ruling, pinned at the route level too. `match_value` is NOT
    NULL, and `''` is not NULL - legacy rows can hold it, and one that matched
    everything would map every product ever typed into the tester."""
    kind = _kind_row(db, "wc")
    _rule_row(db, kind, "model_prefix", "")

    with granted(K_VIEW):
        response = client.post(f"{RULES}/test", json={"product_code": "SRTWC8152"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matches"] == []
    assert body["resolved_kind"] is None


def test_the_tester_needs_the_kinds_view_permission(client, db):
    kind = _kind_row(db, "wc")
    _rule_row(db, kind, "model_prefix", "SRTWC")
    with granted(P_VIEW):
        response = client.post(f"{RULES}/test", json={"product_code": "SRTWC8152"})
    assert response.status_code == 403, response.text


def test_the_tester_with_no_input_at_all_is_a_422(client):
    """A tester called with nothing to test would answer "no match" for every
    product, which reads as a broken mapping rather than as a blank form."""
    with granted(K_VIEW):
        response = client.post(f"{RULES}/test", json={})
    assert response.status_code == 422, response.text


# =============================================================================
# AC-P11 - who is allowed, and through which principal
# =============================================================================


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", POLICIES, None),
        ("post", POLICIES, {"version": "ZZT-X", "effective_from": "2026-01-01"}),
        ("get", KINDS, None),
        ("post", KINDS, {"code": "zzt-x", "name": "X"}),
        ("get", f"{KINDS}/select", None),
        ("get", RULES, None),
        ("post", RULES, {"kind_id": SORENTO, "match_type": "model_prefix", "match_value": "S"}),
        ("post", f"{RULES}/test", {"product_code": "SRTWC8152"}),
        ("get", f"{BASE}/defect-types", None),
    ],
)
def test_every_route_denies_a_principal_holding_nothing(client, method, path, body):
    """Deny by default. A route that forgot its dependency answers 200 here."""
    with granted():
        response = (
            getattr(client, method)(path, json=body)
            if body is not None
            else getattr(client, method)(path)
        )
    assert response.status_code == 403, f"{method.upper()} {path}: {response.text}"


def test_a_read_accepts_an_api_key_principal_and_a_write_does_not(client, db):
    """AC-P11: "Reads take `require_permission_with_api_key`, writes take
    `require_permission`."

    Modelled by making the JWT dependency fail while the api-key dependency
    succeeds - which is exactly the shape of an n8n / MCP call. A write that
    resolved an act-as principal would let automation publish a policy version, and
    `require_permission_with_api_key` is documented as read-oriented for that reason.
    """
    _create_policy(client)

    def _no_jwt():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _no_jwt
    try:
        with granted(P_VIEW, P_ADD, K_VIEW, K_ADD):
            read = client.get(POLICIES)
            write = client.post(POLICIES, json=_policy_body(effective_from="2030-01-01"))
            kinds_read = client.get(KINDS)
            kinds_write = client.post(KINDS, json=_kind_body())
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert read.status_code == 200, f"A read refused an API-key principal: {read.text}"
    assert kinds_read.status_code == 200, kinds_read.text
    assert write.status_code == 401, (
        f"POST /policies accepted an API-key principal ({write.status_code}). "
        "require_permission_with_api_key is read-oriented; nothing in S7b has the "
        "second real-user gate the two write exceptions in this codebase carry."
    )
    assert kinds_write.status_code == 401, kinds_write.text
