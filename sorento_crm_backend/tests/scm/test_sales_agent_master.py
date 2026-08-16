"""The salesperson master: how a code on a document becomes a row, and what may be set on it.

The agent code is the only thing an AutoCount extract states about who sold an order, and
the captain's file carries 38 of them. So the master has to be reachable from a string, and
the string is spelled by whoever typed the export: `SEAN I`, `sean i`, `  SEAN I `. If those
three make three rows then the demand class the captain fills in lands on one of them and
the other two keep classifying nothing, which looks exactly like the feature not working.

The second half is the closed vocabulary. `scm.priority_policy.demand_class_weights` is keyed
on `project` / `retail`, so an agent stamped with a third word does not rank lower - it drops
out of the comparison entirely, silently, for every order that agent sells.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.company import Company
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException
from app.services.scm import sales_agent_service as svc
from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS, PROJECT
from tests._pg_fixture import blank_session, pg_session

MARKER = "ZZTAGENT"


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture(params=["migrated", "create_all"])
def any_shape(request):
    """The same session, over each of the two schemas this table is ever built by.

    `migrated` is the shared database, whose `sales_agents` came from migration 356 (or from
    the AutoCount branch's 303 and was then altered by it). `create_all` is the CI shape: the
    schema is emitted from the model and alembic is stamped without a single migration body
    running. A constraint expressed in only one of the two is a constraint that holds
    everywhere except the machine that gates the merge - or only there.
    """
    factory = pg_session if request.param == "migrated" else blank_session
    with factory() as s:
        yield s


def _code(stem: str = "SEAN") -> str:
    """An agent code shaped like the captain's, but this test's own."""
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _rows(db, code: str) -> list[SalesAgent]:
    """Every master row whose code matches, however it was spelled when written."""
    return [
        a for a in db.query(SalesAgent).all()
        if (a.sales_agent or "").strip().upper() == code.strip().upper()
    ]


def _agent(db, code: str, company_id=None) -> SalesAgent:
    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, company_id=company_id)
    db.add(row)
    return row


def _other_company(db) -> str:
    """A second company, so "scoped" can be told from "unscoped". Seeded, never borrowed:
    the shared database holds exactly one company and CI's holds only the seeded Sorento."""
    cid = str(uuid.uuid4())
    db.add(Company(id=cid, name=f"{MARKER} company", code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}",
                   is_active=True))
    db.flush()
    return cid


# --------------------------------------------------------------------------- #
# 1. an unknown code becomes a row rather than blocking the file
# --------------------------------------------------------------------------- #

def test_an_unknown_agent_code_is_created_and_stamped_as_coming_from_an_import(db):
    """AC-6.4. The captain has 38 codes and no list of them anywhere else in this system.

    Refusing the file until somebody types them in would make the first upload impossible;
    creating them silently as if an admin had is the other failure, because then nobody can
    tell which rows are waiting for a demand class. `source` is what separates the two.
    """
    code = _code()

    agent = svc.resolve_or_create(db, code)

    assert agent is not None
    assert agent.sales_agent == code
    assert agent.source == svc.IMPORT_SOURCE
    assert agent.is_active is True
    assert agent.demand_class is None, "an invented agent must not be given a class"


def test_resolve_or_create_is_idempotent_across_case_and_whitespace(db):
    """One agent, however the export spells them.

    Three rows for one salesperson is not a cosmetic problem: the captain fills in the demand
    class on one of them, and the other two keep classifying nothing while looking correct.
    """
    code = _code()

    first = svc.resolve_or_create(db, code)
    again = svc.resolve_or_create(db, f"  {code.lower()} ")
    third = svc.resolve_or_create(db, code.title())

    assert first.id == again.id == third.id
    assert len(_rows(db, code)) == 1, "a case or spacing variant created a second master row"


def test_a_blank_agent_code_creates_nothing(db):
    """A file column that is simply empty states nothing, and an empty master row is a row
    every future import would then resolve to."""
    before = db.query(SalesAgent).count()

    assert svc.resolve_or_create(db, "") is None
    assert svc.resolve_or_create(db, "   ") is None
    assert svc.resolve_or_create(db, None) is None
    assert db.query(SalesAgent).count() == before


def test_an_agent_an_admin_created_is_adopted_not_overwritten(db):
    """The import resolves onto the existing row; it never restates who made it.

    The captain fills in `demand_class` and `person_label` by hand. If a weekly upload reset
    `source` to `import` - or worse, cleared the class - his work would be undone every
    Monday and the classification would flap.
    """
    code = _code()
    db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent=code, source=svc.MANUAL_SOURCE,
                      person_label="Sean", demand_class=PROJECT, is_active=True))
    db.flush()

    agent = svc.resolve_or_create(db, code.lower())

    assert agent.source == svc.MANUAL_SOURCE
    assert agent.demand_class == PROJECT
    assert agent.person_label == "Sean"
    assert len(_rows(db, code)) == 1


# --------------------------------------------------------------------------- #
# 2. the closed vocabulary
# --------------------------------------------------------------------------- #

def test_a_demand_class_outside_the_vocabulary_is_rejected_by_the_service(db):
    """`dealer` is the obvious wrong answer, and it reads perfectly well to a person.

    The weights map has no key for it, so every order this agent sells would score as if the
    class factor did not exist - which is indistinguishable, on screen, from an agent nobody
    has classified yet.
    """
    code = _code()
    svc.resolve_or_create(db, code)

    with pytest.raises(AppException) as exc:
        svc.set_demand_class(db, code, "dealer")

    assert exc.value.status_code == 400
    assert "dealer" in str(exc.value.detail)


def test_a_demand_class_outside_the_vocabulary_is_rejected_by_the_database(db):
    """The service guard is a nicer error, not the guarantee.

    Rows also arrive from an admin screen, a script and a merge with the AutoCount mirror
    that owns this table on another branch, so the constraint has to live where all of them
    meet it.
    """
    # Inside a savepoint: the failed insert aborts the transaction it runs in, and the
    # fixture's outer one has to survive to roll the rest of the test back.
    savepoint = db.begin_nested()
    db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent=_code(), demand_class="dealer"))

    with pytest.raises(IntegrityError):
        db.flush()

    savepoint.rollback()


@pytest.mark.parametrize("value", [PROJECT, DEFAULT_DEMAND_CLASS, None])
def test_the_vocabulary_the_planner_weighs_is_accepted(db, value):
    """The other half of the same guard: the two words the policy is keyed on, plus the
    unset state, all have to survive. A constraint that rejected `retail` would make the
    captain's own mapping unfillable."""
    code = _code()
    svc.resolve_or_create(db, code)

    agent = svc.set_demand_class(db, code, value)

    assert agent.demand_class == value


def test_setting_a_class_on_an_agent_nobody_holds_is_refused(db):
    """Silently creating the agent instead would let a typo become a master row that then
    classifies orders under a code no document ever states."""
    with pytest.raises(AppException) as exc:
        svc.set_demand_class(db, _code(), PROJECT)

    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# 3. reading many at once, which is what an import actually does
# --------------------------------------------------------------------------- #

def test_resolve_many_answers_for_the_codes_it_holds_and_stays_quiet_about_the_rest(db):
    """The import asks about every agent in the file at once, and must not create any of
    them while it is only previewing."""
    known, unknown = _code("KNOWN"), _code("UNKNOWN")
    svc.set_demand_class(db, svc.resolve_or_create(db, known).sales_agent, PROJECT)
    before = db.query(SalesAgent).count()

    found = svc.resolve_many(db, [f" {known.lower()} ", unknown, ""])

    assert set(found) == {known}
    assert found[known].demand_class == PROJECT
    assert db.query(SalesAgent).count() == before, "a read created a master row"


# --------------------------------------------------------------------------- #
# 4. one code per company, not one code ever
# --------------------------------------------------------------------------- #

def test_two_companies_may_each_hold_the_same_agent_code(any_shape):
    """`company_id` has to be expressible, not merely present.

    The master ships shared (every row NULL company), because the client's own files show the
    same agents selling for both of his companies. But a global unique on the code alone would
    mean a tenant could NEVER hold its own `SEAN III` beside the shared one - so the documented
    future, `company_id IS NULL OR company_id = <scope>` in the service, could not have been
    written without a schema change first. The column would be decoration.
    """
    code = _code("SHARED")
    _agent(any_shape, code, company_id=None)
    _agent(any_shape, code, company_id=_other_company(any_shape))

    any_shape.flush()

    assert len(_rows(any_shape, code)) == 2


def test_two_shared_rows_cannot_hold_the_same_agent_code(any_shape):
    """The half the coalesce buys. Postgres treats NULLs as distinct, so a plain two-column
    unique on `(company_id, sales_agent)` would let the shared master - which today is ALL of
    it - hold `SEAN III` twice, and the class the client fills in would land on one of them
    while the other kept classifying nothing.
    """
    code = _code("SHARED")
    _agent(any_shape, code, company_id=None)
    any_shape.flush()

    # Inside a savepoint: the failed insert aborts its transaction, and the fixture's outer
    # one has to survive to roll the rest of the test back.
    savepoint = any_shape.begin_nested()
    _agent(any_shape, code, company_id=None)

    with pytest.raises(IntegrityError):
        any_shape.flush()

    savepoint.rollback()


def test_one_company_cannot_hold_the_same_agent_code_twice(any_shape):
    """And the other half: scoping the unique must not have loosened it within a company."""
    code = _code("SHARED")
    company = _other_company(any_shape)
    _agent(any_shape, code, company_id=company)
    any_shape.flush()

    savepoint = any_shape.begin_nested()
    _agent(any_shape, code, company_id=company)

    with pytest.raises(IntegrityError):
        any_shape.flush()

    savepoint.rollback()
