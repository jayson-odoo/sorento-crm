"""S5: proposing sets from the catalogue, and applying the ones a person ticks.

47 two-piece families exist across Sorento and Mocha and 23 of them have no bare
code at all, so typing roughly 94 sets by hand is the work this pass removes. It
derives candidates from the SHAPE of the product codes and writes nothing: a
person ticks the ones that are right and only that tick reaches `product_sets`.

The argument against a regex that writes by itself is in this feature's own
history - the role labels came out inverted at the start, and an unattended pass
would have propagated that across 94 rows before anybody looked.

UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
Plan: `PLAN-product-sets.md` section 7.

Every row here is created with a `ZZT` prefix and the assertions filter on it.
The proposal tables are new and therefore empty, but `products`, `companies` and
`product_categories` are not, and this suite runs against a copy of real data.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database import engine
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.product_set_proposal import ProductSetProposal, ProductSetProposalBatch
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_set_proposal_service import (
    CatalogueRow,
    ProductSetProposalService,
    derive_candidates,
)

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


def _family() -> str:
    """A five-digit family number no real catalogue row carries.

    The derivation reads the code's SHAPE, so a test code cannot wear the usual
    `ZZT-` prefix - the hyphen would land inside the prefix group and nothing
    would parse. `ZZT` plus five digits is both shape-valid and filterable.
    """
    return str(uuid.uuid4().int % 90000 + 10000)


def _row(
    code: str,
    description: str | None,
    price: str | None,
    *,
    discontinued: bool = False,
) -> CatalogueRow:
    return CatalogueRow(
        product_code=code,
        description=description,
        list_price=None if price is None else Decimal(price),
        is_discontinued=discontinued,
    )


# The 8608 family as the live catalogue copy actually holds it, down to the
# doubled spaces and the code repeated at the end of every description.
EIGHT_SIX_ZERO_EIGHT = [
    _row(
        "SRTWCX8608-RL",
        "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM) SRTWCX8608-RL",
        "1180.00",
    ),
    _row(
        "SRTWCX8608-P-RL",
        "SORENTO CLOSE COUPLED PEDESTAL (P-TRAP 180MM) SRTWCX8608-P-RL",
        "1180.00",
    ),
    _row(
        "SRTWCX8608-RL-WEPLS",
        "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM) SRTWCX8608-RL-WEPLS",
        "1180.00",
    ),
    _row("SRTWCY8608", "SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP).  SRTWCY8608", "0.00"),
    _row(
        "SRTWCY8608-WEPLS",
        "SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP).  SRTWCY8608-WEPLS",
        "0.00",
    ),
    _row("SRTWC8608-SC", "SORENTO SRTWC8608-SC SEAT COVER ONLY", "85.00"),
]


# ------------------------------------------------------- the derivation, pure
#
# No session, no ORM row, no fixture. The rule is the whole feature, so it is
# tested as a table over code shapes rather than through a database.


def test_ac_h1_the_real_8608_family_yields_one_candidate_per_anchor():
    """AC-H.1 - one candidate per X anchor, and the S-trap and P-trap differ.

    `SRTWCX8608-RL` and `SRTWCX8608-P-RL` are two different assemblies that
    share a cistern, so they are two sets and not one with a choice in it.
    """
    candidates = derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes=set())

    assert [c.set_code for c in candidates] == [
        "SRTWC8608-P-RL",
        "SRTWC8608-RL",
        "SRTWC8608-RL-WEPLS",
    ]
    assert {c.family_key for c in candidates} == {"SRTWC8608"}


def test_ac_h1_the_anchor_the_cistern_and_the_seat_cover_are_the_members():
    """AC-H.1 - anchor first, then the cistern, then the seat cover."""
    candidate = next(
        c
        for c in derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes=set())
        if c.set_code == "SRTWC8608-RL"
    )

    assert [m.product_code for m in candidate.members] == [
        "SRTWCX8608-RL",
        "SRTWCY8608",
        "SRTWC8608-SC",
    ]
    assert [m.sort_order for m in candidate.members] == [0, 1, 2]
    assert all(m.quantity == Decimal("1") for m in candidate.members)


def test_ac_h1_a_modifier_on_the_anchor_picks_the_cistern_that_shares_it():
    """AC-H.1 - `-WEPLS` on the anchor pulls the `-WEPLS` cistern, not the bare one.

    The plain anchor gets the plain cistern by the same rule read the other way:
    neither cistern shares a token with it, so the shortest code wins.
    """
    by_code = {
        c.set_code: c for c in derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes=set())
    }

    assert by_code["SRTWC8608-RL-WEPLS"].members[1].product_code == "SRTWCY8608-WEPLS"
    assert by_code["SRTWC8608-RL"].members[1].product_code == "SRTWCY8608"


def test_ac_h1_a_family_with_an_anchor_and_no_cistern_proposes_nothing():
    """AC-H.1 - a set names an assembly. One half of one is not an assembly."""
    rows = [
        _row("ZZTX40001-RL", "ZZT PEDESTAL ZZTX40001-RL", "500.00"),
        _row("ZZT40001-SC", "ZZT SEAT COVER ZZT40001-SC", "60.00"),
    ]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_ac_h1_a_family_with_a_cistern_and_no_anchor_proposes_nothing():
    """AC-H.1 - the anchor is what carries the code and the price."""
    rows = [_row("ZZTY40002", "ZZT CISTERN ZZTY40002", "0.00")]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_ac_h3_a_code_that_already_exists_is_not_proposed():
    """AC-H.3 - `taken_codes` is every product code AND every set code.

    It is what stops a second run re-proposing a set somebody already applied,
    and what stops a set being proposed for a family that already has a bare
    code in the catalogue.
    """
    taken = {"SRTWC8608-RL"}
    codes = {c.set_code for c in derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes=taken)}

    assert "SRTWC8608-RL" not in codes
    assert "SRTWC8608-P-RL" in codes


def test_ac_h3_the_skip_is_case_insensitive():
    """A code differing only in case is the same code to a person reading a flyer."""
    codes = {
        c.set_code
        for c in derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes={"srtwc8608-rl"})
    }
    assert "SRTWC8608-RL" not in codes


def test_rule7_only_the_anchor_carries_the_price():
    """Rule 7 - the pedestal reads 1180, the cistern 0.00, the seat cover 85.

    Sorento parks the whole assembly's price on the pedestal. The seat cover's
    85.00 is its standalone spare-part price, so ticking it as well would charge
    for the same seat twice.
    """
    candidate = next(
        c
        for c in derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes=set())
        if c.set_code == "SRTWC8608-RL"
    )

    assert [m.contributes_to_price for m in candidate.members] == [True, False, False]


def test_rule7_an_unpriced_anchor_ticks_nothing():
    """Rule 7 - no basis rather than a basis of zero.

    A price of zero and a missing price are different facts, and a set claiming
    RM 0.00 is worse than one that says it has no basis yet.
    """
    number = _family()
    rows = [
        _row(f"ZZTX{number}-RL", f"ZZT PEDESTAL ZZTX{number}-RL", "0.00"),
        _row(f"ZZTY{number}", f"ZZT CISTERN ZZTY{number}", "0.00"),
    ]
    candidate = derive_candidates(rows, taken_codes=set())[0]

    assert [m.contributes_to_price for m in candidate.members] == [False, False]


def test_rule8_the_name_is_the_description_with_the_code_taken_out():
    """Rule 8 - no cleverer word surgery than that; a reviewer renames it."""
    candidate = next(
        c
        for c in derive_candidates(EIGHT_SIX_ZERO_EIGHT, taken_codes=set())
        if c.set_code == "SRTWC8608-RL"
    )
    assert candidate.name == "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)"


def test_rule8_a_description_less_anchor_falls_back_to_its_set_code():
    """Rule 8 - a name is required, so there is always one."""
    number = _family()
    rows = [
        _row(f"ZZTX{number}-RL", None, "500.00"),
        _row(f"ZZTY{number}", None, "0.00"),
    ]
    candidate = derive_candidates(rows, taken_codes=set())[0]
    assert candidate.name == f"ZZT{number}-RL"


# ----------------------------------------------------------- the service, on DB


@pytest.fixture()
def db() -> Session:
    """A session whose writes are DISCARDED, even when the code under test commits.

    `SessionLocal()` + `begin_nested()` is not enough and it silently leaks: the
    service calls `db.commit()`, which commits the OUTER transaction rather than
    releasing a savepoint, so the fixture's rollback has nothing left to undo and
    every ZZT row lands in the shared database for good. That is what happened
    here - 99 sets, 407 products and 204 companies had to be swept back out.

    Binding to a connection that already holds a transaction, with
    `join_transaction_mode="create_savepoint"`, is what makes a committing test
    safe. Same approach as `tests/_pg_fixture.blank_session`.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def world(db: Session):
    """Two companies, each holding the SAME family of codes.

    Seeded rather than read off existing rows: CI's database has no data, so a
    test that reaches for an existing category passes locally and fails there.
    Both companies carrying one family is the cross-bleed case AC-H.4 asks for -
    it is also what the live catalogue does, where SRT and MOCHA share codes.
    """
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([category, uom])
    db.flush()

    number = _family()
    companies = {}
    products = {}
    for key in ("a", "b"):
        company = Company(id=str(uuid.uuid4()), name=_uid(f"co-{key}"), code=_uid(f"C{key}")[:20])
        db.add(company)
        db.flush()
        companies[key] = company
        products[key] = {}
        for role, code, price in (
            ("anchor", f"ZZTX{number}-RL", "1180.00"),
            ("cistern", f"ZZTY{number}", "0.00"),
            ("seat", f"ZZT{number}-SC", "85.00"),
        ):
            row = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=_uid("name"),
                description=f"ZZT ASSEMBLY PART {code}",
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=Decimal(price),
                company_id=company.id,
            )
            db.add(row)
            db.flush()
            products[key][role] = row

    return {
        "companies": companies,
        "products": products,
        "number": number,
        "set_code": f"ZZT{number}-RL",
    }


def _run(db: Session, company) -> dict:
    with company_scope(db, frozenset({str(company.id)})):
        return ProductSetProposalService(db).run(created_by=None)


def _apply(db: Session, company, proposal_ids: list[str]) -> dict:
    with company_scope(db, frozenset({str(company.id)})):
        return ProductSetProposalService(db).apply(proposal_ids, applied_by=None)


def test_ac_h1_the_pass_writes_nothing_to_product_sets(db: Session, world):
    """AC-H.1 - proposing is a read. Only a person's tick reaches `product_sets`."""
    before = db.query(ProductSet).count()
    before_members = db.query(ProductSetMember).count()

    batch = _run(db, world["companies"]["a"])

    assert batch["proposal_count"] == 1
    assert db.query(ProductSet).count() == before
    assert db.query(ProductSetMember).count() == before_members


def test_ac_h2_the_batch_carries_every_field_the_review_screen_reads(db: Session, world):
    """AC-H.2 - asserted explicitly, because `response_model` drops what it was not told about.

    The frontend contract is
    `product-sets/types/productSetProposal.types.ts`, and a field computed
    perfectly but never declared reads on screen as "the backend did not send it".
    """
    batch = _run(db, world["companies"]["a"])

    assert set(batch) >= {
        "id",
        "company_name",
        "created_at",
        "created_by_name",
        "family_count",
        "proposal_count",
        "proposals",
    }
    proposal = batch["proposals"][0]
    assert set(proposal) >= {
        "id",
        "family_key",
        "set_code",
        "name",
        "members",
        "computed_price",
    }
    member = proposal["members"][0]
    assert set(member) >= {
        "product_code",
        "description",
        "list_price",
        "quantity",
        "contributes_to_price",
        "sort_order",
        "is_discontinued",
    }
    # No UUID reaches the screen for a member: it is addressed by code.
    assert "product_id" not in member

    assert batch["company_name"] == world["companies"]["a"].name
    assert batch["family_count"] == 1
    assert proposal["set_code"] == world["set_code"]
    assert proposal["computed_price"] == Decimal("1180.00")
    assert [m["contributes_to_price"] for m in proposal["members"]] == [True, False, False]


def test_the_prices_on_a_proposal_are_read_live_not_snapshotted(db: Session, world):
    """A stored price snapshot goes stale and becomes a second source of truth."""
    _run(db, world["companies"]["a"])
    world["products"]["a"]["anchor"].list_price = Decimal("1250.00")
    db.flush()

    with company_scope(db, frozenset({str(world["companies"]["a"].id)})):
        batch = ProductSetProposalService(db).current()

    assert batch["proposals"][0]["computed_price"] == Decimal("1250.00")


def test_current_is_null_before_any_pass_has_run(db: Session, world):
    """No batch and a batch that found nothing are different facts."""
    with company_scope(db, frozenset({str(world["companies"]["a"].id)})):
        assert ProductSetProposalService(db).current() is None


def test_re_running_replaces_the_previous_batch(db: Session, world):
    """A second pass answers about the catalogue as it is NOW, not alongside the first."""
    first = _run(db, world["companies"]["a"])
    second = _run(db, world["companies"]["a"])

    assert second["id"] != first["id"]
    assert db.query(ProductSetProposalBatch).filter(
        ProductSetProposalBatch.id == first["id"]
    ).first() is None
    assert db.query(ProductSetProposal).filter(
        ProductSetProposal.batch_id == first["id"]
    ).count() == 0


def test_ac_h3_applying_creates_the_set_with_its_members(db: Session, world):
    """AC-H.3 - the tick is the only path onto `product_sets`."""
    batch = _run(db, world["companies"]["a"])
    proposal_id = batch["proposals"][0]["id"]

    result = _apply(db, world["companies"]["a"], [proposal_id])

    assert result["refused"] == []
    assert [row["set_code"] for row in result["applied"]] == [world["set_code"]]

    created = (
        db.query(ProductSet)
        .filter(ProductSet.set_code == world["set_code"])
        .filter(ProductSet.company_id == world["companies"]["a"].id)
        .one()
    )
    assert [m.product_id for m in created.members] == [
        world["products"]["a"]["anchor"].id,
        world["products"]["a"]["cistern"].id,
        world["products"]["a"]["seat"].id,
    ]
    assert [m.contributes_to_price for m in created.members] == [True, False, False]


def test_ac_h3_a_second_pass_does_not_re_propose_an_applied_set(db: Session, world):
    """AC-H.3 - the applied code is now taken, so the pass leaves it alone."""
    batch = _run(db, world["companies"]["a"])
    _apply(db, world["companies"]["a"], [batch["proposals"][0]["id"]])

    again = _run(db, world["companies"]["a"])

    assert again["proposal_count"] == 0
    assert [p["set_code"] for p in again["proposals"]] == []


def test_ac_h3_an_applied_proposal_leaves_the_batch(db: Session, world):
    """It has become a set. Offering it again would invite a duplicate."""
    batch = _run(db, world["companies"]["a"])
    proposal_id = batch["proposals"][0]["id"]
    _apply(db, world["companies"]["a"], [proposal_id])

    assert db.query(ProductSetProposal).filter(
        ProductSetProposal.id == proposal_id
    ).first() is None


def test_ac_h3_a_stale_proposal_id_is_refused_with_a_reason(db: Session, world):
    """AC-H.3 - apply names IDS only, so an id it does not hold creates nothing.

    Never a 500 and never silence: the reviewer ticked it and has to learn why
    it did not land.
    """
    _run(db, world["companies"]["a"])
    before = db.query(ProductSet).count()

    result = _apply(db, world["companies"]["a"], [str(uuid.uuid4())])

    assert result["applied"] == []
    assert len(result["refused"]) == 1
    assert result["refused"][0]["reason"]
    assert db.query(ProductSet).count() == before


def test_ac_h3_another_companys_proposal_is_refused(db: Session, world):
    """AC-H.3 - a proposal is reachable only through its batch, which is scoped."""
    other = _run(db, world["companies"]["b"])
    foreign_id = other["proposals"][0]["id"]
    before = db.query(ProductSet).count()

    result = _apply(db, world["companies"]["a"], [foreign_id])

    assert result["applied"] == []
    assert len(result["refused"]) == 1
    assert db.query(ProductSet).count() == before


def test_ac_h3_a_code_taken_between_propose_and_apply_is_refused(db: Session, world):
    """AC-H.3 - the pass ran yesterday; somebody typed the set this morning."""
    batch = _run(db, world["companies"]["a"])
    db.add(
        ProductSet(
            id=str(uuid.uuid4()),
            set_code=world["set_code"],
            name="typed by hand",
            company_id=world["companies"]["a"].id,
        )
    )
    db.flush()

    result = _apply(db, world["companies"]["a"], [batch["proposals"][0]["id"]])

    assert result["applied"] == []
    assert result["refused"][0]["set_code"] == world["set_code"]
    assert result["refused"][0]["reason"]


def test_ac_h4_each_company_gets_its_own_set_and_members_never_mix(db: Session, world):
    """AC-H.4 - the same codes exist twice, and the two sets must not share a part.

    This is the cross-bleed case. Both companies carry `ZZTX...-RL`; a set
    created for one must name that company's own product row, never the other's.
    """
    a, b = world["companies"]["a"], world["companies"]["b"]

    batch_a = _run(db, a)
    _apply(db, a, [batch_a["proposals"][0]["id"]])
    batch_b = _run(db, b)
    _apply(db, b, [batch_b["proposals"][0]["id"]])

    sets = (
        db.query(ProductSet)
        .filter(ProductSet.set_code == world["set_code"])
        .order_by(ProductSet.company_id)
        .all()
    )
    assert {s.company_id for s in sets} == {a.id, b.id}

    by_company = {s.company_id: s for s in sets}
    for key, company in (("a", a), ("b", b)):
        member_ids = {m.product_id for m in by_company[company.id].members}
        assert member_ids == {p.id for p in world["products"][key].values()}


def test_ac_h4_a_pass_only_ever_sees_its_own_companys_catalogue(db: Session, world):
    """AC-H.4 - one candidate, not two, even though both companies hold the family."""
    batch = _run(db, world["companies"]["a"])
    assert batch["proposal_count"] == 1

    codes = {m["product_code"] for m in batch["proposals"][0]["members"]}
    assert codes == {
        world["products"]["a"]["anchor"].product_code,
        world["products"]["a"]["cistern"].product_code,
        world["products"]["a"]["seat"].product_code,
    }


# ------------------------------------------------------- the routes themselves
#
# The service tests above cannot see a wiring mistake between the router and the
# service. The detail route has already shipped a 500 on `validate_uuid_path`
# taking a keyword-only argument positionally, and `/proposals` sits in front of
# `/{product_set_id}` where a UUID path param would otherwise swallow it.


@pytest.fixture()
def client(db: Session, world, monkeypatch):
    """A client whose actor is allowed through the gate and scoped to one company.

    The permission gate is NOT what these tests are for - RBAC has its own suite,
    and seeding a user, a role and grants here would test that instead of the
    wiring.

    The company scope IS stated, unlike the sibling route suite: the pass reads
    the whole catalogue, so an all-companies scope would derive candidates from
    the 23,000 real products this database holds and the first proposal in the
    batch would be somebody else's. The resolver itself has its own tests.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, *a, **k: True
    )

    def _scope() -> None:
        set_company_scope(db, frozenset({str(world["companies"]["a"].id)}))

    actor = {"id": str(uuid.uuid4()), "email": "zzt@example.com", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


BASE = "/api/v1/master-data/product-sets"


def test_the_get_proposals_route_is_not_swallowed_by_the_detail_route(client, world):
    """`/proposals` is declared BEFORE `/{product_set_id}` or the path param eats it.

    This repo has shipped exactly that bug before, on the SLA escalate routes.
    A swallowed route answers 404 "Product set not found" rather than the batch.
    """
    response = client.get(f"{BASE}/proposals")
    assert response.status_code == 200, response.text
    assert "batch" in response.json()


def test_the_propose_route_answers_with_the_batch(client, db, world):
    response = client.post(f"{BASE}/proposals")
    assert response.status_code == 200, response.text

    body = response.json()
    for field in (
        "id",
        "company_name",
        "created_at",
        "created_by_name",
        "family_count",
        "proposal_count",
        "proposals",
    ):
        assert field in body, f"{field} was dropped on the way out"
    assert body["proposals"], "the seeded family produced no candidate"
    assert {"product_code", "description", "list_price", "quantity",
            "contributes_to_price", "sort_order", "is_discontinued"} <= set(
        body["proposals"][0]["members"][0]
    )


def test_the_apply_route_answers_with_applied_and_refused(client, db, world):
    proposed = client.post(f"{BASE}/proposals").json()
    proposal_id = proposed["proposals"][0]["id"]

    response = client.post(f"{BASE}/proposals/apply", json={"proposal_ids": [proposal_id]})
    assert response.status_code == 200, response.text

    body = response.json()
    assert "applied" in body and "refused" in body
    assert body["refused"] == []
    assert body["applied"][0]["set_code"] == world["set_code"]
    assert body["applied"][0]["proposal_id"] == proposal_id


def test_the_apply_route_refuses_rather_than_500s_on_an_unknown_id(client, world):
    client.post(f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/proposals/apply", json={"proposal_ids": [str(uuid.uuid4())]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied"] == []
    assert len(response.json()["refused"]) == 1


# --------------------------------------------------------- more real families
#
# The 8608 table above is the ONE family this suite exercised end to end. A
# second brand's prefix (`BRBC`) proves the derivation is not hand-tuned to
# `SRTWC`, and the negative rows prove a code that parses into no family - no
# role letter, no digits, or a role with no counterpart - proposes nothing
# rather than something wrong.

BRBC_FAMILY = [
    _row(
        "BRBCX2201-RL",
        "BRAVAT CLOSE COUPLED PEDESTAL (S-TRAP) BRBCX2201-RL",
        "950.00",
    ),
    _row("BRBCY2201", "BRAVAT CLOSE-COUPLED CISTERN ONLY BRBCY2201", "0.00"),
    _row("BRBC2201-SC", "BRAVAT BRBC2201-SC SEAT COVER ONLY", "60.00"),
]


def test_the_brbc_family_derives_one_candidate_the_same_way_8608_does():
    """The rule is a rule, not an 8608 special case."""
    candidates = derive_candidates(BRBC_FAMILY, taken_codes=set())

    assert [c.set_code for c in candidates] == ["BRBC2201-RL"]
    assert [m.product_code for m in candidates[0].members] == [
        "BRBCX2201-RL",
        "BRBCY2201",
        "BRBC2201-SC",
    ]
    assert [m.contributes_to_price for m in candidates[0].members] == [
        True,
        False,
        False,
    ]


def test_a_code_with_no_role_letter_and_no_accessory_token_proposes_nothing():
    """No X, no Y, no SC/FT/PS token in the tail - it declares no role at all."""
    rows = [_row("BRBCQ2202", "BRAVAT SOMETHING BRBCQ2202", "500.00")]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_a_code_with_no_digits_proposes_nothing():
    """`ROLE_INFIX` and `NO_INFIX` both require a 3-5 digit family number."""
    rows = [_row("BRBCXABCDE-RL", "BRAVAT PEDESTAL WITH NO NUMBER", "500.00")]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_a_brbc_cistern_with_no_anchor_proposes_nothing():
    """Half an assembly, the other way round: a Y with no X in its family."""
    rows = [_row("BRBCY2204", "BRAVAT CISTERN ONLY BRBCY2204", "0.00")]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_a_brbc_anchor_with_no_cistern_proposes_nothing():
    rows = [_row("BRBCX2205-RL", "BRAVAT PEDESTAL BRBCX2205-RL", "500.00")]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_brbc_and_8608_together_do_not_cross_pollinate():
    """Two different prefixes in the same pass produce two independent families."""
    candidates = derive_candidates(EIGHT_SIX_ZERO_EIGHT + BRBC_FAMILY, taken_codes=set())

    assert {c.family_key for c in candidates} == {"SRTWC8608", "BRBC2201"}
    brbc = next(c for c in candidates if c.family_key == "BRBC2201")
    assert {m.product_code for m in brbc.members} == {
        "BRBCX2201-RL",
        "BRBCY2201",
        "BRBC2201-SC",
    }


# --------------------------------------------------------- permission denial
#
# The `client` fixture above patches `check_user_has_permission` to always
# succeed, which proves the wiring but not the gate. These leave the real
# `UserPermissionService.check_user_has_permission` in place and force it to
# refuse, so the three routes' `require_permission_with_api_key(...)` calls are
# proven end to end rather than assumed from the CRUD routes' own suite.


@pytest.fixture()
def denied_client(db: Session, world, monkeypatch):
    """Same wiring as `client`, except the permission check always refuses."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, *a, **k: False
    )

    def _scope() -> None:
        pass

    actor = {"id": str(uuid.uuid4()), "email": "zzt-denied@example.com", "role": "viewer"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_get_proposals_is_403_without_the_view_permission(denied_client):
    response = denied_client.get(f"{BASE}/proposals")
    assert response.status_code == 403, response.text
    assert "master_data.product_sets.view" in response.json()["detail"]


def test_run_proposals_is_403_without_the_edit_permission(denied_client):
    response = denied_client.post(f"{BASE}/proposals")
    assert response.status_code == 403, response.text
    assert "master_data.product_sets.edit" in response.json()["detail"]


def test_apply_proposals_is_403_without_the_edit_permission(denied_client):
    response = denied_client.post(
        f"{BASE}/proposals/apply", json={"proposal_ids": []}
    )
    assert response.status_code == 403, response.text
    assert "master_data.product_sets.edit" in response.json()["detail"]


# --------------------------------------------------------- mixed-batch apply
#
# `apply` commits per success and rolls back per refusal (`self.db.rollback()`
# inside the `except AppException` branch). The risk this suite has not proven:
# that the rollback branch, hit in the MIDDLE of a batch, does not disturb a
# commit that already landed before it or one still to come after it.


@pytest.fixture()
def three_family_world(db: Session):
    """One company, three independent families, so a batch holds three proposals."""
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([category, uom])
    db.flush()

    company = Company(id=str(uuid.uuid4()), name=_uid("co"), code=_uid("C")[:20])
    db.add(company)
    db.flush()

    families = {}
    for key in ("keep1", "taken", "keep2"):
        number = _family()
        for role, code, price in (
            ("anchor", f"ZZTX{number}-RL", "500.00"),
            ("cistern", f"ZZTY{number}", "0.00"),
            ("seat", f"ZZT{number}-SC", "40.00"),
        ):
            db.add(
                Product(
                    id=str(uuid.uuid4()),
                    product_code=code,
                    product_name=_uid("name"),
                    description=f"ZZT ASSEMBLY PART {code}",
                    category_id=category.id,
                    base_uom_id=uom.id,
                    list_price=Decimal(price),
                    company_id=company.id,
                )
            )
        db.flush()
        families[key] = f"ZZT{number}-RL"

    return {"company": company, "families": families}


def test_apply_a_mixed_batch_lands_the_valid_ones_and_leaves_the_session_usable(
    db: Session, three_family_world
):
    """AC-H.3 - valid, stale and taken-between-propose-and-apply, all in one call.

    Order matters: the taken one sits BETWEEN the two valid ones, so a `commit()`
    that happened before it and one that happens after it both have to survive
    the `rollback()` its refusal triggers.
    """
    company = three_family_world["company"]
    families = three_family_world["families"]

    batch = _run(db, company)
    by_code = {p["set_code"]: p["id"] for p in batch["proposals"]}
    assert set(by_code) == set(families.values())

    # The code is taken between propose and apply - somebody typed it by hand.
    db.add(
        ProductSet(
            id=str(uuid.uuid4()),
            set_code=families["taken"],
            name="typed by hand",
            company_id=company.id,
        )
    )
    db.flush()

    stale_id = str(uuid.uuid4())
    ordered_ids = [
        by_code[families["keep1"]],
        stale_id,
        by_code[families["taken"]],
        by_code[families["keep2"]],
    ]

    result = _apply(db, company, ordered_ids)

    assert {row["set_code"] for row in result["applied"]} == {
        families["keep1"],
        families["keep2"],
    }
    refused_codes = {row["set_code"] for row in result["refused"]}
    assert families["taken"] in refused_codes
    assert len(result["refused"]) == 2  # the taken one AND the stale id

    # The session is still usable after the rollback branch fired in the
    # middle of the batch: both valid sets are really there, and a fresh query
    # on the same session does not raise on a poisoned transaction.
    created_codes = {
        row.set_code
        for row in db.query(ProductSet).filter(ProductSet.company_id == company.id).all()
    }
    assert families["keep1"] in created_codes
    assert families["keep2"] in created_codes
    assert families["taken"] in created_codes  # the hand-typed one, still there
    assert len(created_codes) == 3


def test_apply_the_same_proposal_id_twice_in_one_call_creates_it_once(
    db: Session, three_family_world
):
    """A duplicate id in the request must not create the same set twice.

    `apply` snapshots the batch's proposals into a dict ONCE before the loop, so
    a repeated id is still found on its second pass even though the first pass
    already deleted the stored proposal row - it is `ProductSetService.create`'s
    own "code already exists" guard that has to catch the repeat.
    """
    company = three_family_world["company"]
    families = three_family_world["families"]

    batch = _run(db, company)
    proposal_id = next(
        p["id"] for p in batch["proposals"] if p["set_code"] == families["keep1"]
    )

    result = _apply(db, company, [proposal_id, proposal_id])

    assert len(result["applied"]) == 1
    assert result["applied"][0]["set_code"] == families["keep1"]
    assert len(result["refused"]) == 1
    assert result["refused"][0]["set_code"] == families["keep1"]

    # Exactly one set exists for that code, never two.
    assert (
        db.query(ProductSet)
        .filter(ProductSet.company_id == company.id)
        .filter(ProductSet.set_code == families["keep1"])
        .count()
        == 1
    )


# ------------------------------------- a role LETTER does not outrank a part TOKEN
#
# Both of these are real codes, carried by both companies. `CWCX605-LID` wears an
# X and `CWCY605-FT` a Y, and neither is a half of the assembly: one is the lid,
# the other the cistern's fitting. Read letter-first, the lid was proposed as the
# anchor of a set called `CWC605-LID` and paired with the real cistern, and the
# fitting was classified a cistern and kept out of the members only by the
# shortest-code tiebreaker rather than by any rule.

CABANA_605 = [
    _row(
        "CWCX605",
        "CABANA CLOSE COUPLED WC - PAN WASH-DOWN FLUSHING. (S-TRAP 250MM )  CWCX605",
        "0.00",
    ),
    _row(
        "CWCX605-RL",
        "CABANA CLOSE COUPLED WC - PAN WASH DOWN -  RIMLESS  (S-TRAP 250MM )  CWCX605-RL",
        "396.00",
    ),
    _row(
        "CWCY605",
        "CABANA CLOSE COUPLED WC - CISTERN WASH-DOWN FLUSHING  CWCY605",
        "0.00",
    ),
    _row("CWCX605-LID", "CABANA WC LID ONLY (CWCX605-LID)", "0.00"),
    _row("CWCY605-FT", "CABANA WC FITTING ONLY (CWCY605)", "0.00"),
]


def test_a_lid_wearing_an_x_is_not_proposed_as_an_anchor():
    """`CWCX605-LID` is the lid of CWC605, so `CWC605-LID` is not a set."""
    candidates = derive_candidates(CABANA_605, taken_codes=set())

    assert [c.set_code for c in candidates] == ["CWC605", "CWC605-RL"]
    assert "CWC605-LID" not in {c.set_code for c in candidates}


def test_a_lid_and_a_fitting_are_never_members_of_the_assembly():
    """The lid is not the pan and the fitting is not the cistern.

    The fitting used to reach the cistern bucket and lose on the shortest-code
    tiebreaker, which is luck rather than a rule: `CWCY605` is one character
    shorter than `CWCY605-FT`. Now it is not in the bucket at all.
    """
    candidates = derive_candidates(CABANA_605, taken_codes=set())

    named = {m.product_code for c in candidates for m in c.members}
    assert "CWCX605-LID" not in named
    assert "CWCY605-FT" not in named
    assert named == {"CWCX605", "CWCX605-RL", "CWCY605"}


# ---------------------------------- a discontinued row is never PROPOSED at all
#
# A different question from D8, which governs a member that goes discontinued
# AFTER the set exists: that set survives, the member is flagged and complete
# sets reads 0. Here the set does not exist yet, and naming a retired placeholder
# instead of its live replacement just builds the wrong set.

SRTWC188_FAMILY = [
    _row(
        "SRTWCX188-P-180",
        "SORENTO CLOSE COUPLED PEDESTAL(P-TRAP180MM ) SRTWCX188-P-180",
        "1030.00",
    ),
    _row("SRTWCY188", "SORENTO CLOSE-COUPLED CISTERN ONLY  SRTWCY188", "0.00"),
    _row("SRTWCY188-P", "****PLS USE CODE  SRTWCY188", "0.00", discontinued=True),
    _row("SRTWC188-SC", "SORENTO WC188 SEAT COVER ONLY SRTWC188-SC", "0.00"),
]


def test_a_discontinued_cistern_loses_to_the_live_one_it_points_at():
    """`SRTWCY188-P` reads "PLS USE CODE SRTWCY188" and used to win on `-P`.

    Token overlap outranks everything in `_best_match`, so the retired row beat
    its own replacement precisely because the live one shares no `-P` with the
    anchor. It is not in the pool any more, so the question does not arise.
    """
    candidate = derive_candidates(SRTWC188_FAMILY, taken_codes=set())[0]

    assert candidate.set_code == "SRTWC188-P-180"
    assert [m.product_code for m in candidate.members] == [
        "SRTWCX188-P-180",
        "SRTWCY188",
        "SRTWC188-SC",
    ]


SRTWC8058_FAMILY = [
    _row(
        "SRTWCX8058-P",
        "****SORENTO CLOSE COUPLED PEDESTAL (P-TRAP) SRTWCX8058-P",
        "1060.00",
        discontinued=True,
    ),
    _row(
        "SRTWCX8058-S-150",
        "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 150MM) SRTWCX8058-S-150",
        "1060.00",
    ),
    _row(
        "SRTWCY8058",
        "SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP & P-TRAP). SRTWCY8058",
        "0.00",
    ),
    _row("SRTWCY8058-P", "****PLS USE NEW CODE SRTWCY8058", "0.00", discontinued=True),
]


def test_a_discontinued_anchor_proposes_no_set_of_its_own():
    """`SRTWCX8058-P` is retired, so `SRTWC8058-P` is not a set to create."""
    candidates = derive_candidates(SRTWC8058_FAMILY, taken_codes=set())

    assert [c.set_code for c in candidates] == ["SRTWC8058-S-150"]
    assert candidates[0].members[1].product_code == "SRTWCY8058"


def test_a_family_whose_only_cistern_is_discontinued_proposes_nothing():
    """No cistern left in the pool is no assembly, exactly like having none."""
    number = _family()
    rows = [
        _row(f"ZZTX{number}-RL", f"ZZT PEDESTAL ZZTX{number}-RL", "500.00"),
        _row(f"ZZTY{number}", f"ZZT CISTERN ZZTY{number}", "0.00", discontinued=True),
    ]
    assert derive_candidates(rows, taken_codes=set()) == []


def test_a_discontinued_seat_cover_is_not_offered_as_a_member():
    """The set still proposes; it just does not name a retired spare part."""
    number = _family()
    rows = [
        _row(f"ZZTX{number}-RL", f"ZZT PEDESTAL ZZTX{number}-RL", "500.00"),
        _row(f"ZZTY{number}", f"ZZT CISTERN ZZTY{number}", "0.00"),
        _row(f"ZZT{number}-SC", f"ZZT SEAT ZZT{number}-SC", "40.00", discontinued=True),
    ]
    candidate = derive_candidates(rows, taken_codes=set())[0]

    assert [m.product_code for m in candidate.members] == [
        f"ZZTX{number}-RL",
        f"ZZTY{number}",
    ]


def test_a_discontinued_product_is_left_out_of_the_pass_on_the_database_too(
    db: Session, world
):
    """The rule reaches the service, not only the pure derivation.

    `run()` builds its rows by hand, so a field the derivation reads and the
    service forgets to carry would be a silent no-op.
    """
    world["products"]["a"]["cistern"].is_discontinued = True
    db.flush()

    batch = _run(db, world["companies"]["a"])

    assert batch["proposal_count"] == 0


# ------------------------------------------- AC-H.4: one company, or no answer
#
# An `X-API-Key` principal carries no contact identity and resolves to the `None`
# scope, which means ALL companies. Under it the pass reads both catalogues at
# once, picks an arbitrary row per duplicated code, treats a family already set
# in one company as taken for the other, stamps the batch onto whichever company
# is incumbent, and can hand one company's set the other's product rows. Every
# other test in this file pins a single-company frozenset, so none of that shows.


def test_ac_h4_running_the_pass_across_all_companies_is_refused(db: Session, world):
    """The `db` fixture's own scope is `None`: all companies, and no answer."""
    from app.services.error_handler import AppException

    # An unscoped read sees every company's rows, and this database is a copy of
    # real data, so the count is only meaningful as a difference.
    before = db.query(ProductSetProposalBatch).count()

    with pytest.raises(AppException) as raised:
        ProductSetProposalService(db).run(created_by=None)

    assert raised.value.status_code == 400
    assert db.query(ProductSetProposalBatch).count() == before


def test_ac_h4_applying_across_all_companies_is_refused(db: Session, world):
    """A batch derived for one company must not be applied by an unscoped caller."""
    from app.services.error_handler import AppException

    batch = _run(db, world["companies"]["a"])
    before = db.query(ProductSet).count()

    with pytest.raises(AppException) as raised:
        ProductSetProposalService(db).apply(
            [batch["proposals"][0]["id"]], applied_by=None
        )

    assert raised.value.status_code == 400
    assert db.query(ProductSet).count() == before


def test_ac_h4_running_the_pass_across_two_companies_is_refused(db: Session, world):
    """Same guard as the `None` (all-companies) case above, pinned for the OTHER
    ambiguous shape: a frozenset naming two or more companies. `_require_one_company`
    covers both through `resolve_write_company_id`, but only the `None` case had a
    test - a regression that broke the multi-company branch specifically would pass
    the suite."""
    from app.services.error_handler import AppException

    before = db.query(ProductSetProposalBatch).count()
    scope = frozenset(
        {str(world["companies"]["a"].id), str(world["companies"]["b"].id)}
    )

    with company_scope(db, scope):
        with pytest.raises(AppException) as raised:
            ProductSetProposalService(db).run(created_by=None)

    assert raised.value.status_code == 400
    assert raised.value.detail["code"] == "company_scope_required"
    assert db.query(ProductSetProposalBatch).count() == before


def test_ac_h4_applying_across_two_companies_is_refused(db: Session, world):
    """Same as above, for `apply()`. A proposal exists to apply, so the refusal is
    proven to be the scope guard and not merely "there was nothing to apply"."""
    from app.services.error_handler import AppException

    batch = _run(db, world["companies"]["a"])
    before = db.query(ProductSet).count()
    scope = frozenset(
        {str(world["companies"]["a"].id), str(world["companies"]["b"].id)}
    )

    with company_scope(db, scope):
        with pytest.raises(AppException) as raised:
            ProductSetProposalService(db).apply(
                [batch["proposals"][0]["id"]], applied_by=None
            )

    assert raised.value.status_code == 400
    assert raised.value.detail["code"] == "company_scope_required"
    assert db.query(ProductSet).count() == before


@pytest.fixture()
def all_companies_client(db: Session, world, monkeypatch):
    """Same wiring as `client`, except the request resolves to EVERY company."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, *a, **k: True
    )

    def _scope() -> None:
        set_company_scope(db, None)

    actor = {"id": str(uuid.uuid4()), "email": "zzt-system@example.com", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_the_propose_route_refuses_an_all_companies_principal(all_companies_client, db):
    before = db.query(ProductSetProposalBatch).count()

    response = all_companies_client.post(f"{BASE}/proposals")

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "company_scope_required"
    assert db.query(ProductSetProposalBatch).count() == before


def test_the_apply_route_refuses_an_all_companies_principal(all_companies_client, db):
    response = all_companies_client.post(
        f"{BASE}/proposals/apply", json={"proposal_ids": [str(uuid.uuid4())]}
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "company_scope_required"
