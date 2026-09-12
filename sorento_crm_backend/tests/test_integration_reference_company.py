"""RED tests for BL-056: `integration_references.company_id` (slice 2).

PLAN: documentation/plans/autocount/PLAN-autocount-brands-ingest.md section 8, D11-D16.
UAC:  documentation/plans/autocount/autocount-brands-ingest-acceptance-criteria.md
      AC-16, AC-17, AC-18 (AC-19/AC-19b/AC-20 are pinned in the edited siblings,
      not here).

`IntegrationReferenceService.__init__` takes only `db` today - no `company_id`
kwarg exists, so every test below that constructs the service with one fails
immediately with a `TypeError`, not a domain assertion. That IS the red this
file pins: the constructor shape D14 promises does not exist yet.

The table itself carries no `company_id` column and no partial unique indexes
yet either (migration 301 + the model, unchanged by this slice) - so a test
that reads the column via raw SQL fails with `UndefinedColumn`, and the two
partial-index-name assertions fail on "index not found" rather than a
behavioural mismatch.

Substrate: `tests._pg_fixture.blank_session()`, built from the CURRENT ORM
models - so it reflects "before this migration", which is exactly the state
these tests are pinned against. Every row is minted under a `ZZTREFCO` marker.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTREFCO"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def company_b(db) -> str:
    company = Company(id=str(uuid.uuid4()), name=f"{MARKER} B", code=unique_code(MARKER)[:10])
    db.add(company)
    db.flush()
    return str(company.id)


def _product(db, company_id: str):
    category = ProductCategory(category_code=unique_code(MARKER), category_name="cat")
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="unit")
    db.add_all([category, uom])
    db.flush()
    row = Product(
        product_code=unique_code(MARKER),
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _ref(stem: str) -> str:
    return f"{MARKER}:{stem}:{uuid.uuid4().hex[:8]}"


# ==================================================================== AC-17
class TestScopedConstructorAndPredicate:
    def test_the_service_accepts_a_company_id_keyword(self, db):
        # D14: IntegrationReferenceService(db, company_id=A). No such kwarg
        # exists today.
        IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID)

    def test_a_scoped_link_stores_the_anchor_company_id(self, db):
        product = _product(db, DEFAULT_COMPANY_ID)
        svc = IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID)
        source_ref = _ref("PROD")

        svc.link(entity_type="products", entity_id=str(product.id), source_ref=source_ref)

        stored = db.execute(
            text(
                "SELECT company_id FROM integration_references "
                "WHERE entity_type = 'products' AND source_ref = :r"
            ),
            {"r": source_ref},
        ).scalar()
        # Raw SQL comes back a uuid.UUID, not the str this fixture holds.
        assert str(stored) == DEFAULT_COMPANY_ID

    def test_a_shared_sales_agent_link_stores_null_company_id(self, db):
        agent = SalesAgent(sales_agent=f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
        db.add(agent)
        db.flush()
        svc = IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID)
        source_ref = _ref("AGENT")

        svc.link(entity_type="sales_agents", entity_id=str(agent.id), source_ref=source_ref)

        stored = db.execute(
            text(
                "SELECT company_id FROM integration_references "
                "WHERE entity_type = 'sales_agents' AND source_ref = :r"
            ),
            {"r": source_ref},
        ).scalar()
        assert stored is None

    def test_resolve_under_one_company_does_not_see_a_ref_linked_under_another(
        self, db, company_b
    ):
        theirs = _product(db, company_b)
        source_ref = _ref("XCO")
        IntegrationReferenceService(db, company_id=company_b).link(
            entity_type="products", entity_id=str(theirs.id), source_ref=source_ref
        )

        under_a = IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID).resolve(
            entity_type="products", source_ref=source_ref
        )
        assert under_a is None

        under_b = IntegrationReferenceService(db, company_id=company_b).resolve(
            entity_type="products", source_ref=source_ref
        )
        assert under_b == str(theirs.id)

    def test_a_scoped_call_with_no_anchor_raises_value_error(self, db):
        product = _product(db, DEFAULT_COMPANY_ID)
        svc = IntegrationReferenceService(db)  # no company_id at all

        with pytest.raises(ValueError):
            svc.link(
                entity_type="products", entity_id=str(product.id), source_ref=_ref("NOANCHOR")
            )

        with pytest.raises(ValueError):
            svc.resolve(entity_type="products", source_ref=_ref("NOANCHOR2"))


# ==================================================================== AC-18
class TestPerCompanyUniqueness:
    def test_the_same_ref_under_two_companies_links_two_different_entities(
        self, db, company_b
    ):
        a_product = _product(db, DEFAULT_COMPANY_ID)
        b_product = _product(db, company_b)
        source_ref = _ref("SHAREDREF")

        IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID).link(
            entity_type="products", entity_id=str(a_product.id), source_ref=source_ref
        )
        # Today this hits the GLOBAL uq_integration_ref_source and raises
        # ReferenceConflict - the exact behaviour AC-18/D12 changes.
        IntegrationReferenceService(db, company_id=company_b).link(
            entity_type="products", entity_id=str(b_product.id), source_ref=source_ref
        )

        rows = db.execute(
            text(
                "SELECT company_id, entity_id FROM integration_references "
                "WHERE entity_type = 'products' AND source_ref = :r"
            ),
            {"r": source_ref},
        ).mappings().all()
        # company_id comes back a uuid.UUID; key on str() to compare with the
        # fixture's own str ids.
        by_company = {str(row["company_id"]): row["entity_id"] for row in rows}
        assert by_company.get(DEFAULT_COMPANY_ID) == str(a_product.id)
        assert by_company.get(company_b) == str(b_product.id)

    def test_the_same_ref_linked_twice_under_one_company_still_conflicts(self, db):
        first = _product(db, DEFAULT_COMPANY_ID)
        second = _product(db, DEFAULT_COMPANY_ID)
        source_ref = _ref("DUPINA")
        svc = IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID)
        svc.link(entity_type="products", entity_id=str(first.id), source_ref=source_ref)

        with pytest.raises(ReferenceConflict):
            svc.link(entity_type="products", entity_id=str(second.id), source_ref=source_ref)


# =============================================== index-name assertions (AC-16/17)
class TestIndexShape:
    def test_the_two_partial_indexes_exist_and_the_global_one_is_gone(self, db):
        # schemaname = current_schema(): blank_session's SET LOCAL search_path
        # puts the scratch schema first, so this pins the MODEL's own
        # declaration - unfiltered, the same names on the REAL public table
        # would satisfy the assertion even if the model declared none of this.
        names = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'integration_references' "
                    "AND schemaname = current_schema()"
                )
            )
        }
        assert "uq_integration_ref_source_company" in names
        assert "uq_integration_ref_source_shared" in names
        assert "uq_integration_ref_source" not in names
