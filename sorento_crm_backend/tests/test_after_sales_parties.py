"""S1 gate - after-sales parties and identity (AC-B1..AC-B21, AC-M37).

S1 is the slice that answers "who is this phone number" without ever asking. Two
nullable bindings on ``respond_contacts`` replace a door question, the Complaint
gets a real Dealer and a real Site, and the salesperson stops being free text. None
of it is user-visible, which is exactly why it needs pinning: every later slice
reads these four answers and none of them can see whether the answer is right.

**AC-B13: ``technician_id`` is DEFERRED to S6.** ``technicians`` does not exist and
S6 (AC-F6) is the slice that creates it; stubbing the table here would hand S6 a
half-defined core entity to migrate, which is worse than an absent one, and a
nullable FK added later is cheap and additive. So S1 ships **two** bindings. The
``technician`` kind is nonetheless declared now (AC-B14, AC-B15) - see
``test_kind_precedence_is_declared_as_data`` for why that is not dead weight.

Five things shape this suite, and each is a place where the obvious implementation
is wrong:

1. **Derivation is only a function if it is total.** AC-B2 permits more than one
   binding to be set and then asks for one kind. Two bindings with no precedence is
   not a derivation, it is a coin flip that will be resolved differently by the
   portal, the notification spine and the dashboard. The order is pinned as declared
   data (so it survives S6 landing the third binding) and every combination
   reachable in S1 is asserted as behaviour.

2. **The Site is not the Dealer's address.** AC-B3's Sanimart case is a dealer's
   owner reporting a fault in his own home: the same row carries a dealer binding
   AND a residential Site. Anything that derives the Site from the customer record
   sends a technician to a shop.

3. **``users.id`` is TEXT.** ``respond_contacts.user_id`` must be varchar. A uuid
   column cannot foreign-key a text one, and every other binding here IS a uuid, so
   matching the neighbours is the natural instinct and it is what breaks (the same
   trap AC-A2 records and AC-F2b-1 hit).

4. **A dry run that dirties the session still writes.** The seed sets attributes on
   ORM rows; the next query autoflushes them. ``--dry-run`` must therefore not
   assign at all, not merely skip the commit. Paging must be keyset, because a
   server-side cursor dies on the first mid-loop commit.

5. **``blank_session`` builds from ``Base.metadata``, not from migrations.** A model
   column with no migration behind it goes fully green here and is absent in
   production - the failure ADR-0012 records. So the schema tests are paired with a
   scan of ``alembic/versions`` that fails if the columns exist only on the model.

Decisions this file takes because the AC is silent. They are asserted rather than
assumed so the next reader inherits an answer instead of a coin flip:

- **Kind precedence is technician > staff > dealer > consumer** (AC-B14). Narrowest
  binding wins. ``technician_id`` is only ever set deliberately and a technician
  routed to the staff journey gets listings they must never see (AC-F8); ``user_id``
  means a Sorento employee, which outranks being somebody's shop contact. AC-B2's
  prose order (customer, user, technician) is a list of cases, not a priority. Only
  the top of that order is unreachable in S1, so the order itself is pinned as a
  declared constant rather than inferred from behaviour alone.
- **The derived kind and the journey share one vocabulary** (``consumer`` /
  ``dealer`` / ``staff`` / ``technician``). Two vocabularies for the same four-way
  split is how they drift.
- **Derivation is a pure function of the row.** No query, so it cannot differ
  between a loaded row and a serialized one, and it is callable inside a
  list-serializer loop without an N+1.
- **The self-heal never re-points an existing binding.** AC-B5a repairs a contact
  nobody configured; silently moving a configured contact to another Dealer because
  someone pasted an order number is a different and much worse act.
- **``Project`` / ``SMC`` / ``E Commerce`` and blank backfill to NULL, not to a
  role.** They are account categories, and a backfill that guesses is worse than one
  that leaves NULL. See ``test_reported_by_role_mapping_is_a_pinned_case_table``.
- **Most-recent-order-wins ties break on ``order_number`` descending, then ``id``.**
  An idempotent re-runnable seed that picks arbitrarily among equals is not
  idempotent.

Every test traces to an AC in
``documentation/plans/after-sales/after-sales-warranty-acceptance-criteria.md``,
Group B, plus AC-M37 (moved into S1 on 2026-08-02: the Site carries
``latitude`` / ``longitude`` / ``place_id`` and the typed address, and
``site_maps_url`` is never created).

Run: venv/bin/python -m pytest tests/test_after_sales_parties.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import pathlib
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Float, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app import database as app_database  # noqa: E402
from app.models.access import RespondContact  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402
from app.models.order import Customer, Order  # noqa: E402
from app.models.portal import PortalToken  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.base import UNSET, company_scope  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract

# The one module S1 is expected to add. The derivation rule has three consumers
# already (the portal door, the notification spine, the dashboard flag) and none of
# them owns it, so it lives beside neither: putting it in portal_service ties "who
# is this contact" to the portal, and the WhatsApp intake in S5 has no portal.
PARTY_MODULE = "app.services.party_service"

# The seed. A script, never a runtime path (AC-B9: orders are the seed, never the
# source), so it lives in scripts/ with the other backfills.
SEED_MODULE = "scripts.seed_customer_account_owner"

# AC-B12: representative dealer bindings for local and staging only.
DEALER_SEED_MODULE = "scripts.seed_dealer_contacts"

# AC-B4/AC-B5. Named in PLAN "S1 - The door: there isn't one".
JOURNEY_ROUTE = "/api/v1/public/portal/journey"

# AC-B5a. The plan describes the self-heal but names no route; this is the shape it
# implies - it hangs off the journey because its only effect is to change one.
ORDER_LOOKUP_ROUTE = "/api/v1/public/portal/journey/order-lookup"

JOURNEYS = frozenset({"consumer", "dealer", "staff", "technician"})

# AC-B6.
REPORTED_BY_ROLES = frozenset({"end_user", "dealer", "salesperson", "cs", "technician"})


# ---------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db):
    def _override_db():
        yield db

    app.dependency_overrides[app_database.get_db] = _override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(app_database.get_db, None)


# ----------------------------------------------------------------------- helpers


def _module(dotted: str, why: str):
    """Import a module S1 is expected to add, or fail naming the contract."""
    if importlib.util.find_spec(dotted) is None:
        raise AssertionError(f"{dotted} does not exist. {why}")
    return importlib.import_module(dotted)


def _party():
    return _module(
        PARTY_MODULE,
        "S1 needs one module owning party derivation, dealer resolution and "
        "salesperson resolution, so the answer to 'who is this contact' cannot "
        "differ between the portal door, the WhatsApp intake and the dashboard.",
    )


def _fn(dotted: str, name: str, signature: str):
    module = _module(dotted, f"{name}{signature} lives here.")
    fn = getattr(module, name, None)
    assert callable(fn), f"{dotted}.{name}{signature} must exist."
    return fn


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


def _user(db, label: str = "sales") -> User:
    """A real users row. Every FK to users.id is enforced by Postgres."""
    user_id = unique_code(label).lower()
    user = User(
        id=user_id,
        email=f"{user_id}@{TEST_PREFIX.lower()}.invalid",
        name=f"{TEST_PREFIX} {label}",
        status="ACTIVE",
    )
    db.add(user)
    db.flush()
    return user


def _customer(db, name: str = "dealer", *, owner: User | None = None) -> Customer:
    customer = Customer(
        id=str(uuid.uuid4()),
        customer_code=unique_code(name)[:50],
        customer_name=f"{TEST_PREFIX} {name}",
        account_owner_user_id=owner.id if owner else None,
    )
    db.add(customer)
    db.flush()
    return customer


def _contact(db, **bindings) -> RespondContact:
    """A respond_contacts row whose id is deliberately NOT a uuid.

    ``respond_contacts.id`` is TEXT with a uuid-shaped default, so a test seeding a
    uuid there would keep passing against a uuid FK column.
    """
    contact = RespondContact(
        id=unique_code("contact").lower(),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name=f"{TEST_PREFIX} contact",
    )
    for key, value in bindings.items():
        setattr(contact, key, value)
    db.add(contact)
    db.flush()
    return contact


def _token(db, contact: RespondContact) -> PortalToken:
    from app.services.portal_service import _utcnow

    token = PortalToken(
        id=str(uuid.uuid4()),
        token=unique_code("tok").upper(),
        contact_id=contact.id,
        space_id="9911",
        expires_at=_utcnow() + timedelta(days=7),
        verified_at=_utcnow(),
    )
    db.add(token)
    db.flush()
    return token


def _order(db, customer: Customer, *, salesman: str, order_date, number: str | None = None) -> Order:
    order = Order(
        id=str(uuid.uuid4()),
        order_number=number or unique_code("so")[:100],
        order_date=order_date,
        customer_id=customer.id,
        salesman=salesman,
    )
    db.add(order)
    db.flush()
    return order


def _transient_contact(**bindings) -> RespondContact:
    """An unsaved contact - derivation must not need the database.

    Only the two bindings S1 ships (AC-B13). The deferred third one is exercised
    through ``_SyntheticContact`` below, so nothing here depends on a column that
    does not exist until S6.
    """
    contact = RespondContact(id="transient", phone_number="+60100000000")
    contact.customer_id = bindings.get("customer_id")
    contact.user_id = bindings.get("user_id")
    return contact


class _SyntheticContact:
    """A duck-typed stand-in carrying all three bindings, including the deferred one.

    AC-B13 defers ``technician_id`` to S6, so the top of the precedence order cannot
    be reached from a real row in S1. Pinning the order only through reachable cases
    would leave the highest-priority rung untested until S6, which is exactly when
    somebody re-decides it. A synthetic input keeps the rung asserted now without
    requiring a column, and it forces the derivation to read the binding
    defensively (``getattr(contact, "technician_id", None)``) so S6 is a pure column
    addition rather than a change to this function, the endpoint and the order.
    """

    def __init__(self, *, customer_id=None, user_id=None, technician_id=None):
        self.customer_id = customer_id
        self.user_id = user_id
        self.technician_id = technician_id


# =============================================================================
# Group B schema - AC-B1, AC-B6, AC-M37
# =============================================================================


def test_respond_contacts_gains_the_two_bindings_s1_ships():
    """AC-B1 as corrected by AC-B13. Two bindings now, the third in S6.

    ``technician_id`` is deliberately absent - see
    ``test_after_sales_legacy_column_guard.py::test_s1_does_not_stub_the_deferred_technician_binding``,
    which is the guard that keeps it that way and which S6 deletes.
    """
    columns = _columns(RespondContact)
    for name in ("customer_id", "user_id"):
        assert name in columns, (
            f"respond_contacts.{name} is missing. Kind is derived from which "
            "bindings are set, so a missing column silently makes that kind "
            "unreachable."
        )
        assert columns[name].nullable, (
            f"respond_contacts.{name} must be nullable: every contact has at most "
            "one of these and a Consumer has none."
        )

    targets = {
        "customer_id": "customers.id",
        "user_id": "users.id",
    }
    for name, target in targets.items():
        fks = {fk.target_fullname for fk in columns[name].foreign_keys}
        assert target in fks, (
            f"respond_contacts.{name} must foreign-key {target}, not hold a loose "
            f"id. Found {fks or 'no foreign key'}."
        )


def test_respond_contacts_user_id_is_text_because_users_id_is_text():
    """AC-A2 boundary. A uuid column cannot foreign-key a text one.

    Every other binding added here is a uuid, so declaring this one uuid to match
    its neighbours is the natural instinct and it is the thing that breaks. Pinned
    as its own test because the failure is a DDL error at migration time in
    production and a silent type mismatch in any fixture that only writes uuids.
    """
    columns = _columns(RespondContact)
    missing = [n for n in ("user_id", "customer_id") if n not in columns]
    assert not missing, f"respond_contacts is missing {missing} (AC-B1)."
    assert isinstance(columns["user_id"].type, (String, Text)), (
        "respond_contacts.user_id must be varchar/text: users.id is Column(String) "
        f"and stays that way until the uuid-id PR stack converts it. Got "
        f"{columns['user_id'].type!r}."
    )
    assert isinstance(columns["customer_id"].type, PG_UUID), (
        "respond_contacts.customer_id must be pg UUID - customers.id is "
        f"UUID(as_uuid=False). Got {columns['customer_id'].type!r}."
    )


def test_complaints_gains_the_dealer_and_the_site():
    """AC-B1 + AC-M37. The Dealer is a FK; the Site is four fields plus an address."""
    columns = _columns(Complaint)

    assert "customer_id" in columns, (
        "complaints.customer_id is missing - the Dealer has no home, so it stays in "
        "free-text customer_name and AC-B6a's eventual drop is impossible."
    )
    assert "customers.id" in {
        fk.target_fullname for fk in columns["customer_id"].foreign_keys
    }, "complaints.customer_id must foreign-key customers.id."

    for name in ("site_address", "site_contact_name", "site_contact_phone"):
        assert name in columns, f"complaints.{name} is missing (AC-B1 site block)."

    for name in ("latitude", "longitude", "place_id"):
        assert name in columns, (
            f"complaints.{name} is missing. AC-M37 moved into S1 on 2026-08-02 "
            "precisely so the Site is defined once: the four fields land now, not "
            "in a second migration on the same concept."
        )


def test_site_coordinates_are_numeric_with_navigable_precision():
    """AC-M37 + AC-M39. The pin is what a technician navigates to.

    Text cannot be compared or bounded-box queried, and float loses exactness on a
    value that is copied between systems (the pin and the address are deliberately
    never reconciled, so the pin has to survive round-trips verbatim). Scale must
    reach at least six decimal places: five is about a metre, four is a street.
    """
    columns = _columns(Complaint)
    missing = [n for n in ("latitude", "longitude") if n not in columns]
    assert not missing, f"complaints is missing {missing} (AC-M37)."
    for name in ("latitude", "longitude"):
        col_type = columns[name].type
        assert isinstance(col_type, Numeric) and not isinstance(col_type, Float), (
            f"complaints.{name} must be Numeric, not {col_type!r}. A coordinate in "
            "text cannot be bounded-box queried and a float does not round-trip."
        )
        assert (col_type.scale or 0) >= 6, (
            f"complaints.{name} needs scale >= 6 (about 0.1m). Got scale="
            f"{col_type.scale}."
        )


def test_reported_by_role_is_added_and_the_legacy_columns_survive():
    """AC-B6. Additive, not a rename.

    Renaming a column on a live table makes the migration irreversible mid-release
    for no gain. The legacy three must still be present after S1 - if they are gone,
    the drop happened a release early and every reader listed in
    ``test_after_sales_legacy_column_guard.py`` is now an AttributeError.
    """
    columns = _columns(Complaint)
    assert "reported_by_role" in columns, "complaints.reported_by_role is missing."
    assert columns["reported_by_role"].nullable, (
        "complaints.reported_by_role must be nullable: 32 of the 47 live rows carry "
        "an account category that is not a reporter, and NULL is the honest value "
        "for them."
    )
    for legacy in ("customer_type", "customer_name", "salesperson"):
        assert legacy in columns, (
            f"complaints.{legacy} must survive S1 (AC-B6: not renamed, not dropped, "
            "read-only for one release)."
        )


def test_the_new_columns_are_in_a_migration_not_only_on_the_model():
    """The ADR-0012 failure, pinned.

    ``blank_session`` builds the schema from ``Base.metadata``, so a model column
    with no migration behind it passes every other test in this file and is absent
    in production. Scan the revision files for the columns themselves.
    """
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = [p.read_text(encoding="utf-8", errors="ignore") for p in versions.glob("*.py")]

    def _added(table: str, column: str) -> bool:
        return any(table in src and column in src and "add_column" in src for src in sources)

    missing = [
        f"{table}.{column}"
        for table, column in (
            # respond_contacts.user_id is deliberately not in this list: "user_id"
            # appears in four unrelated revisions that also touch respond_contacts,
            # so the match would be a false positive. customer_id lands in the same
            # ALTER and is unambiguous.
            ("respond_contacts", "customer_id"),
            ("complaints", "reported_by_role"),
            ("complaints", "site_address"),
            ("complaints", "place_id"),
        )
        if not _added(table, column)
    ]
    assert not missing, (
        "No alembic revision adds " + ", ".join(missing) + ". A column that exists "
        "only on the model is green in every test here and absent in production - "
        "the exact failure ADR-0012 records."
    )


def test_the_migration_carries_the_reported_by_role_backfill():
    """AC-B6. The backfill is part of the migration, not a script somebody runs.

    A data step left outside the migration is a step that is skipped on one
    environment, and then ``reported_by_role`` is NULL in staging and populated in
    production for reasons nobody can reconstruct.
    """
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = [p.read_text(encoding="utf-8", errors="ignore") for p in versions.glob("*.py")]
    assert any("reported_by_role" in src and "end_user" in src for src in sources), (
        "No revision both adds reported_by_role and mentions a mapped role value, "
        "so the backfill is not in the migration."
    )


# =============================================================================
# Kind derivation - AC-B2, and the precedence AC-B2 does not state
# =============================================================================


def test_derivation_is_a_pure_function_of_the_row():
    """AC-B2. No query, so it is safe inside a serializer loop and cannot vary.

    A derivation that queries can return a different kind for a detached row than
    for a loaded one, and it turns any list endpoint into an N+1.
    """
    derive = _fn(PARTY_MODULE, "derive_contact_kind", "(contact) -> str")
    assert derive(_transient_contact()) == "consumer", (
        "derive_contact_kind must work on a row that was never persisted - it reads "
        "three attributes and nothing else."
    )


@pytest.mark.parametrize(
    "bindings,expected,why",
    [
        ({}, "consumer", "AC-B4: nothing set is a Consumer by elimination"),
        ({"customer_id": "c"}, "dealer", "AC-B2: customer_id means dealer staff"),
        ({"user_id": "u"}, "staff", "AC-B2: user_id means Sorento staff"),
        (
            {"customer_id": "c", "user_id": "u"},
            "staff",
            "a Sorento employee who is also somebody's shop contact is staff: the "
            "employee relationship is the one that grants tools. This is the ONLY "
            "multi-binding case reachable in S1, and it is reachable today - a "
            "salesman gets a users row for Project Management (AC-B7) and may also "
            "be the configured contact for a dealer account",
        ),
    ],
)
def test_kind_precedence_is_total_for_every_case_reachable_in_s1(bindings, expected, why):
    """AC-B2 permits more than one binding and names no precedence.

    That makes derivation a partial function, which is a gap in the AC, not a
    detail: the portal, the notification spine and the dashboard would each resolve
    it their own way. AC-B14 settles it as technician > staff > dealer > consumer;
    these are the cases a real row can produce while ``technician_id`` is deferred.
    """
    derive = _fn(PARTY_MODULE, "derive_contact_kind", "(contact) -> str")
    assert derive(_transient_contact(**bindings)) == expected, why


def test_kind_precedence_is_declared_as_data():
    """AC-B14, pinned as a constant rather than inferred from behaviour.

    The top rung of the order is unreachable in S1 (AC-B13 defers the binding), so
    behaviour alone cannot pin it and it would stay undecided until S6 - which is
    exactly the moment somebody re-decides it under delivery pressure. A declared
    tuple pins the whole order now, costs nothing, and is what S6 reads instead of
    re-deriving.

    It also answers whether ``technician`` is dead weight in S1. It is not: the
    journey route is a **public, unauthenticated portal contract** consumed by a
    frontend and by n8n, neither of which deploys atomically with the backend. A
    three-member response literal in S1 makes S6 a breaking change to that contract
    (OpenAPI, the FE union type, any exhaustive switch). A four-member vocabulary
    declared once and referenced by the response model makes S6 a column addition
    and nothing else. The second reason is smaller but real: ``reported_by_role``
    already carries ``technician`` as one of its five values in S1 (AC-B6), in this
    same module - shipping a kind vocabulary that omits it invites somebody to
    derive one from the other and lose a value.
    """
    module = _party()
    precedence = getattr(module, "KIND_PRECEDENCE", None)
    assert precedence is not None, (
        f"{PARTY_MODULE}.KIND_PRECEDENCE must exist: an ordered tuple, highest "
        "priority first."
    )
    assert tuple(precedence) == ("technician", "staff", "dealer", "consumer"), (
        f"KIND_PRECEDENCE is {tuple(precedence)}; AC-B14 fixes it as "
        "('technician', 'staff', 'dealer', 'consumer'). Narrowest binding wins."
    )


def test_the_deferred_technician_binding_still_outranks_the_two_that_ship():
    """AC-B13 + AC-B14. The rung that cannot be reached from a row is still asserted.

    Synthetic input rather than a ``respond_contacts`` row, because the column does
    not exist until S6. The point is to force the derivation to read the binding
    defensively now, so S6 adds a column and changes nothing else: not this
    function, not the endpoint, not the order.
    """
    derive = _fn(PARTY_MODULE, "derive_contact_kind", "(contact) -> str")
    assert derive(_SyntheticContact(technician_id="t")) == "technician"
    assert derive(_SyntheticContact(customer_id="c", technician_id="t")) == "technician", (
        "A technician must never reach a dealer form; AC-F8 says they see today's "
        "jobs and nothing else."
    )
    assert derive(_SyntheticContact(user_id="u", technician_id="t")) == "technician"
    assert (
        derive(_SyntheticContact(customer_id="c", user_id="u", technician_id="t"))
        == "technician"
    ), "All three set must still be a total function, not a coin flip."


def test_kind_vocabulary_matches_the_journey_vocabulary():
    """One four-way split, one set of words.

    The endpoint returns a journey and the derivation returns a kind; if those are
    two vocabularies then somewhere there is a translation table that will drift.
    Asserted against the declared constant so ``technician`` counts even while no
    row can produce it.
    """
    module = _party()
    precedence = getattr(module, "KIND_PRECEDENCE", None)
    assert precedence is not None, f"{PARTY_MODULE}.KIND_PRECEDENCE must exist."
    assert set(precedence) == JOURNEYS, (
        f"KIND_PRECEDENCE covers {sorted(set(precedence))}; the journey vocabulary "
        f"is {sorted(JOURNEYS)}."
    )

    derive = _fn(PARTY_MODULE, "derive_contact_kind", "(contact) -> str")
    produced = {
        derive(_transient_contact()),
        derive(_transient_contact(customer_id="c")),
        derive(_transient_contact(user_id="u")),
    }
    assert produced == {"consumer", "dealer", "staff"}, (
        f"The three kinds reachable in S1 produced {sorted(produced)}."
    )


# =============================================================================
# The door that isn't - AC-B4, AC-B5
# =============================================================================


def test_journey_for_an_unbound_phone_is_consumer_and_asks_nothing(client, db):
    """AC-B4. Consumer by elimination, no door question."""
    contact = _contact(db)
    token = _token(db, contact)

    res = client.get(JOURNEY_ROUTE, headers={"X-Portal-Token": token.token})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["journey"] == "consumer"
    assert not any(
        isinstance(v, str) and v.lower().startswith("question") for v in body.values()
    ), (
        "The journey response must not carry a question for the contact to answer. "
        "AC-B4: there is no door."
    )


def test_journey_for_a_bound_dealer_contact_is_dealer(client, db):
    """AC-B5. A bound phone goes straight to the journey its binding implies."""
    customer = _customer(db, "sanimart")
    contact = _contact(db, customer_id=customer.id)
    token = _token(db, contact)

    res = client.get(JOURNEY_ROUTE, headers={"X-Portal-Token": token.token})
    assert res.status_code == 200, res.text
    assert res.json()["journey"] == "dealer"


def test_journey_for_a_bound_staff_contact_is_staff(client, db):
    """AC-B5. Sorento staff are known from user_id."""
    user = _user(db, "cs")
    contact = _contact(db, user_id=user.id)
    token = _token(db, contact)

    res = client.get(JOURNEY_ROUTE, headers={"X-Portal-Token": token.token})
    assert res.status_code == 200, res.text
    assert res.json()["journey"] == "staff"


def test_journey_requires_a_portal_token(client):
    """Auth denial. The journey names the contact, so it is not anonymous."""
    assert client.get(JOURNEY_ROUTE).status_code == 401
    assert client.get(JOURNEY_ROUTE, headers={"X-Portal-Token": "nonsense"}).status_code == 401


def test_journey_response_never_exposes_a_uuid(client, db):
    """Cursor rule: no UUIDs in the frontend UI, and the portal is the FE.

    The contact is a Consumer here, so there is nothing to name - but the same
    response shape carries the dealer case, and a customer_id leaking into it is how
    a raw uuid ends up rendered on a consumer's phone.
    """
    customer = _customer(db, "totalhome")
    contact = _contact(db, customer_id=customer.id)
    token = _token(db, contact)

    res = client.get(JOURNEY_ROUTE, headers={"X-Portal-Token": token.token})
    assert res.status_code == 200, res.text
    body = res.json()
    leaked = [
        f"{k}={v}"
        for k, v in body.items()
        if isinstance(v, str) and len(v) == 36 and v.count("-") == 4
    ]
    assert not leaked, f"The journey response leaks a uuid: {leaked}"


# =============================================================================
# The self-heal - AC-B5a
# =============================================================================


def test_a_quoted_order_number_binds_the_contact_and_switches_the_journey(client, db):
    """AC-B5a. The binding repairs itself, silently, with no question asked."""
    customer = _customer(db, "dilooma")
    order = _order(db, customer, salesman="SEAN", order_date=date(2026, 4, 1), number="ZZT-202604-0348")
    contact = _contact(db)
    token = _token(db, contact)

    res = client.post(
        ORDER_LOOKUP_ROUTE,
        headers={"X-Portal-Token": token.token},
        json={"order_number": order.order_number},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["matched"] is True
    assert body["journey"] == "dealer"

    db.expire_all()
    assert db.get(RespondContact, contact.id).customer_id == customer.id, (
        "The order resolved but respond_contacts.customer_id was not written, so the "
        "contact is mis-routed again on their next visit. AC-B5a is about the "
        "binding, not about this one request."
    )


def test_an_unknown_order_number_is_not_an_error_and_leaves_the_contact_unbound(client, db):
    """AC-B5a, negative. AC-C14's rule applies here first: never block the submitter.

    A Consumer with a dealer's own receipt (AC-C12 lists six real formats, none of
    which exist in ``orders``) will type something that does not resolve. Returning
    4xx turns the self-heal into a wall for the exact people it was not aimed at.
    """
    contact = _contact(db)
    token = _token(db, contact)

    res = client.post(
        ORDER_LOOKUP_ROUTE,
        headers={"X-Portal-Token": token.token},
        json={"order_number": "KCS-2112-0054"},
    )
    assert res.status_code == 200, (
        "An unresolvable order number must be a 200 saying 'no match', not a 4xx. "
        f"Got {res.status_code}: {res.text}"
    )
    body = res.json()
    assert body["matched"] is False
    assert body["journey"] == "consumer"

    db.expire_all()
    assert db.get(RespondContact, contact.id).customer_id is None


def test_the_self_heal_never_repoints_an_already_bound_contact(client, db):
    """A decision the AC does not state, and the safe direction is the strict one.

    AC-B5a exists to fix a contact nobody configured. A contact Sorento DID
    configure is a deliberate act; moving them to another Dealer because someone
    pasted an order number would silently re-route their complaints, their
    notifications and their salesperson.
    """
    configured = _customer(db, "configured")
    other = _customer(db, "other")
    _order(db, other, salesman="SEAN", order_date=date(2026, 4, 1), number="ZZT-202604-0999")
    contact = _contact(db, customer_id=configured.id)
    token = _token(db, contact)

    res = client.post(
        ORDER_LOOKUP_ROUTE,
        headers={"X-Portal-Token": token.token},
        json={"order_number": "ZZT-202604-0999"},
    )
    assert res.status_code == 200, res.text

    db.expire_all()
    assert db.get(RespondContact, contact.id).customer_id == configured.id, (
        "An existing binding was overwritten from an order number. Self-heal repairs "
        "an ABSENT binding only."
    )


def test_order_lookup_rejects_an_empty_order_number(client, db):
    """Validation. A blank string is not a lookup, it is a scan of the orders table."""
    contact = _contact(db)
    token = _token(db, contact)
    headers = {"X-Portal-Token": token.token}

    assert client.post(ORDER_LOOKUP_ROUTE, headers=headers, json={}).status_code == 422
    assert (
        client.post(ORDER_LOOKUP_ROUTE, headers=headers, json={"order_number": "   "}).status_code
        == 422
    )


def test_order_lookup_requires_a_portal_token(client):
    """Auth denial. It writes a binding, so it is certainly not anonymous."""
    res = client.post(ORDER_LOOKUP_ROUTE, json={"order_number": "202604-0348"})
    assert res.status_code == 401, res.text


# =============================================================================
# The Sanimart case - AC-B3
# =============================================================================


def test_a_dealer_contact_reporting_from_home_keeps_his_home_as_the_site(db):
    """AC-B3. Being a dealer contact never forces the Site to be the shop.

    Three answers have to come apart on the same row: the Dealer comes from the
    binding, the Site comes from what was typed, and the salesperson comes from the
    Dealer. An implementation that derives the Site from the customer record passes
    every dealer-track test and sends a technician to a shop.
    """
    owner = _user(db, "accountowner")
    sanimart = _customer(db, "sanimart", owner=owner)
    contact = _contact(db, customer_id=sanimart.id)

    resolve_dealer = _fn(
        PARTY_MODULE, "resolve_dealer_customer_id", "(db, contact) -> Optional[str]"
    )
    resolve_salesperson = _fn(
        PARTY_MODULE, "resolve_salesperson_user_id", "(db, complaint) -> Optional[str]"
    )

    home = "12 Jalan Rumah, Taman Sri Muda, 40400 Shah Alam"
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=unique_code("cmp"),
        customer_id=resolve_dealer(db, contact),
        site_address=home,
        site_contact_name=f"{TEST_PREFIX} owner",
        site_contact_phone=contact.phone_number,
        reported_by_role="dealer",
    )
    db.add(complaint)
    db.flush()

    assert complaint.customer_id == sanimart.id, "The Dealer must resolve from the binding."
    assert complaint.site_address == home, (
        "The Site was rewritten to the dealer's address. AC-B3: the Site lives on the "
        "Complaint and is whatever was reported."
    )
    assert resolve_salesperson(db, complaint) == owner.id, (
        "The salesperson must resolve from the Dealer's account owner even though "
        "the Site is residential."
    )


# =============================================================================
# Salesperson resolution - AC-B9, AC-B10
# =============================================================================


def test_salesperson_resolves_only_from_the_account_owner(db):
    """AC-B9, stated as behaviour rather than as a grep.

    This customer has orders, and those orders name a salesman. If resolution ever
    falls back to ``orders.salesman`` this test is the only thing that notices - and
    that fallback is exactly the shortcut somebody takes when ~770 dealers come back
    unresolved.
    """
    resolve = _fn(PARTY_MODULE, "resolve_salesperson_user_id", "(db, complaint) -> Optional[str]")
    known = _user(db, "onorders")
    customer = _customer(db, "hasorders")  # deliberately no account owner
    _order(db, customer, salesman=known.name, order_date=date(2026, 5, 1))

    complaint = Complaint(id=str(uuid.uuid4()), customer_id=customer.id)
    db.add(complaint)
    db.flush()

    assert resolve(db, complaint) is None, (
        "Salesperson resolved to something even though customers.account_owner_user_id "
        "is NULL. Orders are the seed, never the source (AC-B9)."
    )


def test_a_complaint_with_no_dealer_has_no_salesperson(db):
    """AC-B10. Unresolved is a real answer, and it must be returned, not guessed."""
    resolve = _fn(PARTY_MODULE, "resolve_salesperson_user_id", "(db, complaint) -> Optional[str]")
    complaint = Complaint(id=str(uuid.uuid4()))
    db.add(complaint)
    db.flush()
    assert resolve(db, complaint) is None


def test_the_party_module_never_mentions_orders_salesman():
    """AC-B9 as a guard, scoped to the code S1 adds.

    The repo-wide version of this guard cannot pass today (the orders API serializes
    the column and the embedding worker embeds it - see
    ``test_after_sales_legacy_column_guard.py``), so the enforceable form is that the
    NEW runtime module contains no reference to it at all.
    """
    source = pathlib.Path(_party().__file__).read_text(encoding="utf-8")
    for banned in ("salesman", "customer_type", "Complaint.customer_name", "complaint.customer_name"):
        assert banned not in source, (
            f"{PARTY_MODULE} references {banned!r}. Runtime resolution reads "
            "customers.account_owner_user_id and nothing else; the legacy columns are "
            "read-only for one release and then dropped."
        )


# =============================================================================
# reported_by_role backfill - AC-B6
# =============================================================================


def test_reported_by_role_values_are_the_five_the_ac_names():
    """AC-B6. The vocabulary is closed; anything else is a typo with a home."""
    module = _party()
    roles = getattr(module, "REPORTED_BY_ROLES", None)
    assert roles is not None, f"{PARTY_MODULE}.REPORTED_BY_ROLES must exist."
    assert set(roles) == REPORTED_BY_ROLES, f"Got {sorted(roles)}."


@pytest.mark.parametrize(
    "customer_type,expected,why",
    [
        ("Dealer", "dealer", "4 live rows; the only account category that is also a reporter"),
        ("End User", "end_user", "3 live rows"),
        (
            "Salesperson",
            "salesperson",
            "5 live rows, and NOT one of the five configured complaints_customer_type "
            "lookup options - the mapping must cover values the lookup set never had",
        ),
        (
            "Project",
            None,
            "24 live rows. A project sale says nothing about who reported the fault. "
            "AC-B6 itself calls it an account category, and a backfill that guesses "
            "is worse than one that leaves NULL",
        ),
        ("SMC", None, "7 live rows; an account category, not a reporter"),
        ("E Commerce", None, "1 live row; a channel, not a reporter"),
        (
            None,
            None,
            "3 live rows are NULL. The PLAN says the blanks become 'cs'; that asserts "
            "Customer Service reported them, which no evidence supports",
        ),
        ("", None, "empty string is a blank, same as NULL"),
        ("   dealer  ", "dealer", "case and whitespace tolerant - it is free text today"),
        ("Something Else", None, "an unrecognised value maps to NULL, never to a default role"),
    ],
)
def test_reported_by_role_mapping_is_a_pinned_case_table(customer_type, expected, why):
    """AC-B6. Every distinct live value, with a decision for each.

    The live table holds 47 rows across 7 distinct values. Two of them differ from
    what the plan assumed: 'Salesperson' is not in the configured lookup set at all,
    and there are 3 blanks rather than the 7 the plan cites (7 is the SMC count).
    """
    to_role = _fn(
        PARTY_MODULE, "reported_by_role_from_customer_type", "(value) -> Optional[str]"
    )
    assert to_role(customer_type) == expected, why


# =============================================================================
# The salesperson seed - AC-B7, AC-B8, AC-B10, AC-B11
# =============================================================================


def _seed():
    return _fn(
        SEED_MODULE,
        "seed_account_owners",
        "(db, *, code_map=None, dry_run=True, batch=500) -> dict",
    )


def test_a_single_salesman_customer_resolves(db):
    """AC-B7. 2,191 of 3,284 customers resolve with no ambiguity at all."""
    seed = _seed()
    user = _user(db, "sean")
    customer = _customer(db, "single")
    _order(db, customer, salesman="SEAN", order_date=date(2026, 1, 5))

    stats = seed(db, code_map={"SEAN": user.id}, dry_run=False, batch=500)

    db.expire_all()
    assert db.get(Customer, customer.id).account_owner_user_id == user.id
    assert stats["matched_set"] >= 1, f"stats did not report the write: {stats}"


def test_most_recent_order_wins_for_a_multi_salesman_customer(db):
    """AC-B8. 322 customers carry more than one salesman code."""
    seed = _seed()
    old = _user(db, "old")
    recent = _user(db, "recent")
    customer = _customer(db, "multi")
    _order(db, customer, salesman="OLD", order_date=date(2025, 1, 1))
    _order(db, customer, salesman="RECENT", order_date=date(2026, 6, 1))

    seed(db, code_map={"OLD": old.id, "RECENT": recent.id}, dry_run=False, batch=500)

    db.expire_all()
    assert db.get(Customer, customer.id).account_owner_user_id == recent.id


def test_a_tie_on_order_date_breaks_deterministically(db):
    """AC-B8 says most-recent-wins and stops there.

    Two orders on the same day with different salesmen is not hypothetical on 322
    customers, and an arbitrary pick makes the seed non-idempotent: a re-run flips
    the account owner, which flips who is notified about every complaint for that
    dealer. Pinned as order_number descending, then id descending.
    """
    seed = _seed()
    lower = _user(db, "lower")
    higher = _user(db, "higher")
    customer = _customer(db, "tie")
    same_day = date(2026, 6, 1)
    _order(db, customer, salesman="LOWER", order_date=same_day, number="ZZT-202606-0001")
    _order(db, customer, salesman="HIGHER", order_date=same_day, number="ZZT-202606-0002")

    code_map = {"LOWER": lower.id, "HIGHER": higher.id}
    seed(db, code_map=code_map, dry_run=False, batch=500)
    db.expire_all()
    first = db.get(Customer, customer.id).account_owner_user_id
    assert first == higher.id, (
        "A same-date tie must resolve to the higher order_number. Got "
        f"{'the lower' if first == lower.id else repr(first)}."
    )

    seed(db, code_map=code_map, dry_run=False, batch=500)
    db.expire_all()
    assert db.get(Customer, customer.id).account_owner_user_id == first, (
        "The tie-break is not stable across runs, so the seed is not idempotent."
    )


def test_an_order_with_no_date_never_outranks_one_with_a_date(db):
    """orders.order_date is nullable. NULL is not 'most recent'.

    Postgres sorts NULLs first on DESC by default, so the natural query hands the
    account owner to whatever order forgot its date.
    """
    seed = _seed()
    dated = _user(db, "dated")
    undated = _user(db, "undated")
    customer = _customer(db, "nulldate")
    _order(db, customer, salesman="DATED", order_date=date(2025, 3, 1))
    _order(db, customer, salesman="UNDATED", order_date=None)

    seed(db, code_map={"DATED": dated.id, "UNDATED": undated.id}, dry_run=False, batch=500)

    db.expire_all()
    assert db.get(Customer, customer.id).account_owner_user_id == dated.id


def test_junk_and_unmapped_codes_leave_the_account_owner_alone(db):
    """AC-B10. `0`, `ACT`, `CS01`, `WH02`, `MARKETING`, `SAMPLE`, `FUNITURE`, `TERA`.

    Unresolved must stay NULL and be counted, so the ~770 dealers with no orders and
    the junk-code ones land on the dashboard flag rather than on an arbitrary user.
    """
    seed = _seed()
    customer = _customer(db, "junk")
    _order(db, customer, salesman="WH02", order_date=date(2026, 2, 2))

    stats = seed(db, code_map={}, dry_run=False, batch=500)

    db.expire_all()
    assert db.get(Customer, customer.id).account_owner_user_id is None
    assert stats["unresolved"] >= 1, f"unresolved was not counted: {stats}"


def test_suffixed_codes_collapse_many_to_one(db):
    """AC-B11. SEAN / SEAN I / SEAN III / SEAN IV are one person.

    Also the reason the map cannot be a column on ``users``: one user needs four
    codes.
    """
    seed = _seed()
    sean = _user(db, "seanmulti")
    a = _customer(db, "suffixa")
    b = _customer(db, "suffixb")
    _order(db, a, salesman="SEAN", order_date=date(2026, 1, 1))
    _order(db, b, salesman="SEAN III", order_date=date(2026, 1, 1))

    seed(
        db,
        code_map={"SEAN": sean.id, "SEAN I": sean.id, "SEAN III": sean.id, "SEAN IV": sean.id},
        dry_run=False,
        batch=500,
    )

    db.expire_all()
    assert db.get(Customer, a.id).account_owner_user_id == sean.id
    assert db.get(Customer, b.id).account_owner_user_id == sean.id


def test_the_code_map_is_configured_data_not_a_module_constant(db):
    """AC-B11 says "as configured", and there is nowhere configured to put it.

    ``users`` has no salesman-code column, and one user needs four codes, so a
    column could not hold them anyway. The map has to be persisted and editable, or
    the next suffix Sorento invents is a deploy.
    """
    load = _fn(SEED_MODULE, "load_salesman_code_map", "(db) -> dict[str, str]")
    upsert = _fn(SEED_MODULE, "upsert_salesman_code", "(db, code, user_id) -> None")

    sean = _user(db, "cfg")
    upsert(db, "SEAN", sean.id)
    upsert(db, "SEAN IV", sean.id)
    db.flush()

    mapping = load(db)
    assert mapping.get("SEAN") == sean.id
    assert mapping.get("SEAN IV") == sean.id, "Many codes to one user must be storable."


def test_a_dry_run_writes_nothing(db):
    """The autoflush trap. Skipping the commit is not enough.

    The seed sets attributes on ORM rows; the very next query autoflushes them, and
    a dry run has then written the whole table while reporting that it did not. The
    re-read below is what catches it, because it triggers that autoflush.
    """
    seed = _seed()
    user = _user(db, "dry")
    customer = _customer(db, "dryrun")
    _order(db, customer, salesman="DRY", order_date=date(2026, 1, 5))

    stats = seed(db, code_map={"DRY": user.id}, dry_run=True, batch=500)

    assert db.get(Customer, customer.id).account_owner_user_id is None, (
        "A dry run assigned the account owner. It must not touch the attribute at "
        "all - autoflush turns a dirty row into an UPDATE regardless of the commit."
    )
    assert stats["matched_set"] >= 1, (
        f"A dry run must still report what it would do; got {stats}."
    )


def test_a_dry_run_at_batch_one_writes_nothing(db):
    """Verified at --batch 1, per the plan.

    Batch boundaries are where a commit sneaks into a dry run, and with the default
    batch of 500 a test never crosses one.
    """
    seed = _seed()
    user = _user(db, "dry1")
    customers = []
    for i in range(3):
        customer = _customer(db, f"batch{i}")
        _order(db, customer, salesman="DRY1", order_date=date(2026, 1, i + 1))
        customers.append(customer)

    seed(db, code_map={"DRY1": user.id}, dry_run=True, batch=1)

    for customer in customers:
        assert db.get(Customer, customer.id).account_owner_user_id is None


def test_keyset_paging_covers_every_customer_at_batch_one(db):
    """Keyset, not yield_per: a named cursor dies on the first mid-loop commit.

    At batch 1 with three customers, an off-by-one in the ``id > last_id`` predicate
    silently skips rows, and the seed reports success having done a third of the job.
    """
    seed = _seed()
    user = _user(db, "paged")
    customers = []
    for i in range(3):
        customer = _customer(db, f"page{i}")
        _order(db, customer, salesman="PAGED", order_date=date(2026, 1, i + 1))
        customers.append(customer)

    seed(db, code_map={"PAGED": user.id}, dry_run=False, batch=1)

    db.expire_all()
    for customer in customers:
        assert db.get(Customer, customer.id).account_owner_user_id == user.id


def test_the_seed_corrects_a_prior_bad_run_and_is_a_no_op_on_the_second(db):
    """AC-K1 shape. "Set where mismatch", never "update where NULL".

    "Update where NULL" cannot repair the run that wrote the wrong value, which is
    the run you most need to repair.
    """
    seed = _seed()
    wrong = _user(db, "wrong")
    right = _user(db, "right")
    customer = _customer(db, "correcting", owner=wrong)
    _order(db, customer, salesman="RIGHT", order_date=date(2026, 4, 4))

    code_map = {"RIGHT": right.id}
    seed(db, code_map=code_map, dry_run=False, batch=500)
    db.expire_all()
    assert db.get(Customer, customer.id).account_owner_user_id == right.id, (
        "A wrong prior value was not corrected - the seed is 'update where NULL'."
    )

    stats = seed(db, code_map=code_map, dry_run=False, batch=500)
    assert stats["matched_set"] == 0, (
        f"A second run rewrote rows that were already correct: {stats}."
    )
    assert stats["matched_unchanged"] >= 1


def test_the_seed_sees_customers_in_every_company(db):
    """The fail-closed scope filter, which a script never sets.

    ``customers`` and ``orders`` both carry ``CompanyScopedMixin``. A script running
    off a bare ``SessionLocal`` has ``UNSET`` scope, which resolves to zero rows -
    so the seed reports "0 scanned, nothing to do" and exits successfully having
    done nothing. AC-B11 also records that every salesman suffix appears under BOTH
    Sorento and Mocha, so a Sorento-only scope is wrong even when the scope is set.
    """
    seed = _seed()
    other = Company(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Mocha", code=unique_code("MC")[:20])
    db.add(other)
    db.flush()

    user = _user(db, "crosscompany")
    with company_scope(db, frozenset({other.id})):
        customer = _customer(db, "mocha")
        _order(db, customer, salesman="MOCHA", order_date=date(2026, 3, 3))
    customer_id = customer.id

    with company_scope(db, UNSET):
        stats = seed(db, code_map={"MOCHA": user.id}, dry_run=False, batch=500)

    db.expire_all()
    with company_scope(db, None):
        assert db.get(Customer, customer_id).account_owner_user_id == user.id, (
            f"The seed missed a customer outside the default scope (stats={stats}). "
            "It must set its own company scope rather than inherit UNSET."
        )


# =============================================================================
# Dealer-contact seed for testing - AC-B12
# =============================================================================


def test_the_dealer_contact_seed_binds_an_exact_phone_match(db):
    """AC-B12. Representative bindings for local and staging; production is manual.

    The matching rule is a decision this file takes, because AC-B12 says only
    "representative": exact normalised phone equality, mirroring
    ``backfill_requested_by_contact``'s exact-match-or-leave rule. Anything fuzzier
    binds a consumer to a dealer, which is the one error this whole slice exists to
    avoid.
    """
    seed = _fn(DEALER_SEED_MODULE, "seed_dealer_contacts", "(db, *, dry_run=True) -> dict")
    contact = _contact(db)
    customer = _customer(db, "phonematch")
    customer.phone_number = contact.phone_number
    db.flush()

    seed(db, dry_run=False)

    db.expire_all()
    assert db.get(RespondContact, contact.id).customer_id == customer.id


def test_the_dealer_contact_seed_leaves_an_ambiguous_phone_unbound(db):
    """Two customers on one number is a guess, and a guess here mis-routes a person."""
    seed = _fn(DEALER_SEED_MODULE, "seed_dealer_contacts", "(db, *, dry_run=True) -> dict")
    contact = _contact(db)
    for label in ("ambig_a", "ambig_b"):
        customer = _customer(db, label)
        customer.phone_number = contact.phone_number
    db.flush()

    seed(db, dry_run=False)

    db.expire_all()
    assert db.get(RespondContact, contact.id).customer_id is None


def test_the_dealer_contact_seed_dry_run_writes_nothing(db):
    """Same autoflush trap as the salesperson seed."""
    seed = _fn(DEALER_SEED_MODULE, "seed_dealer_contacts", "(db, *, dry_run=True) -> dict")
    contact = _contact(db)
    customer = _customer(db, "dryphone")
    customer.phone_number = contact.phone_number
    db.flush()

    seed(db, dry_run=True)

    assert db.get(RespondContact, contact.id).customer_id is None
