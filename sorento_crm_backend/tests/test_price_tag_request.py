"""Price tag request tests: doc number, transitions, portal visibility, set guard, CRUD, debtor scoping.

Run with: pytest tests/test_price_tag_request.py -v

These tests exercise the service layer directly against a blank Postgres schema.
No sqlite. CI DB has no seed data - everything needed is created inline.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from tests._pg_fixture import blank_session, unique_code

# Models used for seeding.
from app.models.access import (
    ContactAccessType,
    RespondContact,
    respond_contact_access_types,
)
from app.models.order import Customer, Order
from app.models.price_tag import (
    ContactPortalFormOverride,
    PriceTagRequest,
    PriceTagRequestLine,
)
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.sales_agent import SalesAgent

# Service under test.
from app.services.price_tag_request_service import (
    PriceTagRequestService,
    STATUS_APPROVED,
    STATUS_CHANGES_REQUESTED,
    STATUS_DESIGNING,
    STATUS_NEW,
    STATUS_PROOF_READY,
    STATUS_READY,
    STATUS_REJECTED,
    STATUS_VOID,
    VALID_TRANSITIONS,
)
from app.services.portal_form_visibility_service import resolve_visible_form_types


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test."""
    with blank_session() as session:
        yield session


def _make_contact(db: Session, *, phone: str | None = None) -> RespondContact:
    """Seed a minimal RespondContact."""
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone or f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(c)
    db.flush()
    return c


def _make_access_type(
    db: Session,
    *,
    code: str | None = None,
    portal_form_types: list[str] | None = None,
) -> ContactAccessType:
    """Seed a ContactAccessType with given portal_form_types."""
    at = ContactAccessType(
        code=code or unique_code("at"),
        name=unique_code("Access Type"),
        portal_form_types=portal_form_types or [],
    )
    db.add(at)
    db.flush()
    return at


def _assign_access_type(db: Session, contact: RespondContact, access_type: ContactAccessType) -> None:
    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact.id,
            access_type_code=access_type.code,
        )
    )
    db.flush()


def _make_product(
    db: Session,
    *,
    class_label: str | None = None,
    product_code: str | None = None,
) -> Product:
    """Seed a Product with its required FK chain (category, brand, uom)."""
    cat = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("cat"),
        category_name=unique_code("Category"),
        class_label=class_label,
    )
    db.add(cat)
    db.flush()

    brand = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code("br"),
        brand_name=unique_code("Brand"),
    )
    db.add(brand)
    db.flush()

    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=unique_code("uom"),
        uom_name="Each",
    )
    db.add(uom)
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=product_code or unique_code("prod"),
        product_name=unique_code("Product"),
        category_id=cat.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=100.00,
    )
    db.add(product)
    db.flush()
    return product


def _make_sales_agent(
    db: Session,
    *,
    contact_id: str | None = None,
) -> SalesAgent:
    agent = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=unique_code("agent"),
        contact_id=contact_id,
    )
    db.add(agent)
    db.flush()
    return agent


def _make_customer(
    db: Session,
    *,
    sales_agent_id: str | None = None,
) -> Customer:
    cust = Customer(
        id=str(uuid.uuid4()),
        customer_code=unique_code("cust"),
        customer_name=unique_code("Customer"),
        sales_agent_id=sales_agent_id,
    )
    db.add(cust)
    db.flush()
    return cust


def _make_product_set(db: Session, *, member: Product | None = None) -> ProductSet:
    """Seed a ProductSet holding one member.

    A real row, not a fabricated uuid: ``price_tag_request_lines.product_set_id``
    is a foreign key, so an invented id is refused by Postgres before the guard
    under test ever runs.
    """
    product = member or _make_product(db, class_label="Bathroom Furniture")
    product_set = ProductSet(
        id=str(uuid.uuid4()),
        set_code=unique_code("set"),
        name=unique_code("Set"),
        company_id=_SORENTO_COMPANY_ID,
    )
    db.add(product_set)
    db.flush()

    db.add(
        ProductSetMember(
            id=str(uuid.uuid4()),
            product_set_id=product_set.id,
            product_id=product.id,
            quantity=1,
            contributes_to_price=True,
            sort_order=0,
        )
    )
    db.flush()
    return product_set


# ---------------------------------------------------------------------------
# 1. Doc number generation
# ---------------------------------------------------------------------------


class TestDocNumber:
    def test_first_doc_number_for_company(self, db: Session):
        """First request in the month gets sequence 0001."""
        doc = PriceTagRequestService.generate_doc_number(db, _SORENTO_COMPANY_ID)
        now = datetime.utcnow()
        expected_prefix = f"PT-{now.strftime('%Y%m')}-"
        assert doc.startswith(expected_prefix)
        assert doc.endswith("0001")

    def test_second_doc_number_increments(self, db: Session):
        """Second request same month same company gets 0002."""
        contact = _make_contact(db)
        # Create a first request to occupy sequence 1.
        PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Test Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [],
            },
        )
        db.flush()

        doc2 = PriceTagRequestService.generate_doc_number(db, _SORENTO_COMPANY_ID)
        assert doc2.endswith("0002")

    def test_the_month_sequence_is_global_not_per_company(self, db: Session):
        """A second company continues the month's sequence rather than restarting it.

        ``doc_number`` is UNIQUE across the whole table, so a per-company sequence
        hands the second company a number the first company already spent. The
        number is a document number, not a per-company counter.
        """
        # Create a second company.
        from app.models.company import Company

        company_b_id = str(uuid.uuid4())
        db.execute(
            Company.__table__.insert().values(
                id=company_b_id, name="Other Co", code="OTH", is_active=True,
            )
        )
        db.flush()

        contact = _make_contact(db)

        # Create a request under Sorento.
        first = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "D1",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [],
            },
        )
        db.flush()

        doc_b = PriceTagRequestService.generate_doc_number(db, company_b_id)
        assert doc_b != first.doc_number
        assert doc_b.endswith("0002")

    def test_a_second_company_can_actually_create_in_the_same_month(self, db: Session):
        """Two companies, one month, two creates: no unique violation.

        The per-company COUNT gave both companies ``-0001`` and the second insert
        died on ``price_tag_requests_doc_number_key`` with a 500.
        """
        from app.models.base import company_scope
        from app.models.company import Company

        company_b_id = str(uuid.uuid4())
        db.execute(
            Company.__table__.insert().values(
                id=company_b_id, name="Other Co 2", code="OTH2", is_active=True,
            )
        )
        db.flush()

        contact = _make_contact(db)
        first = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "D1", "lines": []},
        )
        db.flush()

        second = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=company_b_id,
            data={"debtor_name": "D2", "lines": []},
        )
        db.flush()

        assert first.doc_number != second.doc_number
        # And both rows really are in the table.
        with company_scope(db, None):
            numbers = {
                row.doc_number
                for row in db.query(PriceTagRequest)
                .filter(PriceTagRequest.id.in_([first.id, second.id]))
                .all()
            }
        assert numbers == {first.doc_number, second.doc_number}

    def test_a_deleted_draft_does_not_hand_its_number_to_the_next_request(
        self, db: Session
    ):
        """Create two, delete one, create again: the third gets a fresh number.

        A draft hard-deletes (D48b), so a sequence derived from a COUNT of the
        SURVIVING rows re-issues a number that is still spent as far as the unique
        index is concerned. The next create answered 500.
        """
        contact = _make_contact(db)
        first = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "D1", "lines": []},
        )
        second = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "D2", "lines": []},
        )
        db.flush()
        assert second.doc_number.endswith("0002")

        db.delete(first)
        db.flush()

        third = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "D3", "lines": []},
        )
        db.flush()
        assert third.doc_number.endswith("0003")
        assert third.doc_number != second.doc_number


# ---------------------------------------------------------------------------
# 2. Status transitions
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    def _create_request(self, db: Session, status: str = STATUS_NEW) -> PriceTagRequest:
        contact = _make_contact(db)
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [],
            },
        )
        if status != STATUS_NEW:
            req.status = status
            db.flush()
        return req

    def test_new_to_designing(self, db: Session):
        req = self._create_request(db, STATUS_NEW)
        result = PriceTagRequestService.transition_status(db, req.id, STATUS_DESIGNING)
        assert result.status == STATUS_DESIGNING

    def test_designing_to_proof_ready(self, db: Session):
        req = self._create_request(db, STATUS_DESIGNING)
        result = PriceTagRequestService.transition_status(db, req.id, STATUS_PROOF_READY)
        assert result.status == STATUS_PROOF_READY

    def test_proof_ready_to_approved(self, db: Session):
        req = self._create_request(db, STATUS_PROOF_READY)
        result = PriceTagRequestService.transition_status(db, req.id, STATUS_APPROVED)
        assert result.status == STATUS_APPROVED

    def test_approved_to_ready(self, db: Session):
        req = self._create_request(db, STATUS_APPROVED)
        result = PriceTagRequestService.transition_status(db, req.id, STATUS_READY)
        assert result.status == STATUS_READY

    def test_proof_ready_to_changes_requested(self, db: Session):
        req = self._create_request(db, STATUS_PROOF_READY)
        result = PriceTagRequestService.transition_status(db, req.id, STATUS_CHANGES_REQUESTED)
        assert result.status == STATUS_CHANGES_REQUESTED

    def test_changes_requested_to_designing(self, db: Session):
        req = self._create_request(db, STATUS_CHANGES_REQUESTED)
        result = PriceTagRequestService.transition_status(db, req.id, STATUS_DESIGNING)
        assert result.status == STATUS_DESIGNING

    def test_any_to_void(self, db: Session):
        for st in [STATUS_NEW, STATUS_DESIGNING, STATUS_PROOF_READY, STATUS_CHANGES_REQUESTED, STATUS_APPROVED]:
            req = self._create_request(db, st)
            result = PriceTagRequestService.transition_status(db, req.id, STATUS_VOID)
            assert result.status == STATUS_VOID

    def test_any_to_rejected(self, db: Session):
        for st in [STATUS_NEW, STATUS_DESIGNING, STATUS_PROOF_READY, STATUS_CHANGES_REQUESTED, STATUS_APPROVED]:
            req = self._create_request(db, st)
            result = PriceTagRequestService.transition_status(db, req.id, STATUS_REJECTED)
            assert result.status == STATUS_REJECTED

    def test_invalid_skip_new_to_approved(self, db: Session):
        """Cannot skip from new to approved."""
        req = self._create_request(db, STATUS_NEW)
        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.transition_status(db, req.id, STATUS_APPROVED)
        assert exc_info.value.status_code == 409

    def test_invalid_terminal_ready(self, db: Session):
        """Ready is terminal, cannot transition further."""
        req = self._create_request(db, STATUS_READY)
        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.transition_status(db, req.id, STATUS_DESIGNING)
        assert exc_info.value.status_code == 409

    def test_invalid_terminal_void(self, db: Session):
        """Void is terminal, cannot transition further."""
        req = self._create_request(db, STATUS_VOID)
        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.transition_status(db, req.id, STATUS_NEW)
        assert exc_info.value.status_code == 409

    def test_not_found_404(self, db: Session):
        """Transitioning a nonexistent request gives 404."""
        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.transition_status(db, str(uuid.uuid4()), STATUS_DESIGNING)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 3. Portal form visibility
# ---------------------------------------------------------------------------


class TestPortalFormVisibility:
    def test_dealer_access_type(self, db: Session):
        """Contact with a dealer access type sees price_tag_request + stock_inquiry."""
        contact = _make_contact(db)
        at = _make_access_type(db, portal_form_types=["price_tag_request", "stock_inquiry"])
        _assign_access_type(db, contact, at)

        visible = resolve_visible_form_types(db, contact.id)
        assert "price_tag_request" in visible
        assert "stock_inquiry" in visible

    def test_project_access_type(self, db: Session):
        """Contact with project access type sees project-oriented forms."""
        contact = _make_contact(db)
        at = _make_access_type(
            db,
            portal_form_types=[
                "stock_inquiry",
                "purchase_request",
                "sponsorship_form",
                "complaint",
            ],
        )
        _assign_access_type(db, contact, at)

        visible = resolve_visible_form_types(db, contact.id)
        assert "stock_inquiry" in visible
        assert "purchase_request" in visible
        assert "sponsorship_form" in visible
        assert "complaint" in visible
        assert "price_tag_request" not in visible

    def test_multiple_access_types_union(self, db: Session):
        """Contact with multiple access types gets the union."""
        contact = _make_contact(db)
        at_dealer = _make_access_type(db, portal_form_types=["price_tag_request", "stock_inquiry"])
        at_project = _make_access_type(db, portal_form_types=["purchase_request", "complaint"])
        _assign_access_type(db, contact, at_dealer)
        _assign_access_type(db, contact, at_project)

        visible = resolve_visible_form_types(db, contact.id)
        assert visible == {"price_tag_request", "stock_inquiry", "purchase_request", "complaint"}

    def test_override_enable_adds_type(self, db: Session):
        """Per-contact override with is_enabled=True adds a type."""
        contact = _make_contact(db)
        # No access types assigned at all.
        override = ContactPortalFormOverride(
            contact_id=contact.id,
            form_type="price_tag_request",
            is_enabled=True,
        )
        db.add(override)
        db.flush()

        visible = resolve_visible_form_types(db, contact.id)
        assert "price_tag_request" in visible

    def test_override_disable_removes_type(self, db: Session):
        """Per-contact override with is_enabled=False removes a type."""
        contact = _make_contact(db)
        at = _make_access_type(db, portal_form_types=["price_tag_request", "stock_inquiry"])
        _assign_access_type(db, contact, at)

        override = ContactPortalFormOverride(
            contact_id=contact.id,
            form_type="price_tag_request",
            is_enabled=False,
        )
        db.add(override)
        db.flush()

        visible = resolve_visible_form_types(db, contact.id)
        assert "price_tag_request" not in visible
        assert "stock_inquiry" in visible

    def test_no_access_types_empty(self, db: Session):
        """Contact with no access types and no overrides sees nothing."""
        contact = _make_contact(db)
        visible = resolve_visible_form_types(db, contact.id)
        assert visible == set()


# ---------------------------------------------------------------------------
# 4. Set guard validation
# ---------------------------------------------------------------------------


class TestSetGuard:
    def test_bathroom_furniture_ala_carte_rejected(self, db: Session):
        """Product with class 'Bathroom Furniture' submitted as ala carte is rejected."""
        product = _make_product(db, class_label="Bathroom Furniture")
        contact = _make_contact(db)

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.submit_request(
                db,
                contact_id=contact.id,
                company_id=_SORENTO_COMPANY_ID,
                data={
                    "debtor_name": "Dealer",
                    "needed_by_date": date.today() + timedelta(days=7),
                    "lines": [
                        {
                            "line_type": "product",
                            "product_id": product.id,
                        },
                    ],
                },
            )
        assert exc_info.value.status_code == 422

    def test_bathroom_furniture_as_set_allowed(self, db: Session):
        """Product with class 'Bathroom Furniture' submitted as product_set line is allowed."""
        contact = _make_contact(db)
        product_set = _make_product_set(db)

        # No actual set guard check for product_set lines, so this should succeed.
        req = PriceTagRequestService.submit_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {
                        "line_type": "product_set",
                        "product_set_id": product_set.id,
                    },
                ],
            },
        )
        assert req.status == STATUS_NEW

    def test_non_bathroom_ala_carte_allowed(self, db: Session):
        """Product with class != 'Bathroom Furniture' is always allowed ala carte."""
        product = _make_product(db, class_label="Kitchen Sink")
        contact = _make_contact(db)

        req = PriceTagRequestService.submit_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": product.id,
                    },
                ],
            },
        )
        assert req.status == STATUS_NEW


# ---------------------------------------------------------------------------
# 5. Request CRUD
# ---------------------------------------------------------------------------


class TestRequestCRUD:
    def test_create_with_lines(self, db: Session):
        """Create a request with valid lines returns the request with doc_number."""
        contact = _make_contact(db)
        product = _make_product(db, class_label="Kitchen Sink")

        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Test Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": product.id,
                    },
                ],
            },
        )
        db.flush()

        assert req.doc_number is not None
        assert req.doc_number.startswith("PT-")
        assert req.contact_id == contact.id
        assert len(req.lines) == 1
        assert req.lines[0].product_id == product.id

    def test_create_invalid_line_both_null(self, db: Session):
        """A line with both product_id and product_set_id NULL fails validation."""
        contact = _make_contact(db)

        with pytest.raises(Exception):
            PriceTagRequestService.create_request(
                db,
                contact_id=contact.id,
                company_id=_SORENTO_COMPANY_ID,
                data={
                    "debtor_name": "Dealer",
                    "needed_by_date": date.today() + timedelta(days=7),
                    "lines": [
                        {
                            "line_type": "product",
                            # Both null - violates the check constraint.
                            "product_id": None,
                            "product_set_id": None,
                        },
                    ],
                },
            )
            db.flush()

    def test_get_request_by_id(self, db: Session):
        """Get request by id returns full data with lines."""
        contact = _make_contact(db)
        product = _make_product(db, class_label="Kitchen Sink")

        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Test Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": product.id,
                        "quantity": 3,
                    },
                ],
            },
        )
        db.flush()

        fetched = PriceTagRequestService.get_request(db, req.id)
        assert fetched is not None
        assert fetched.id == req.id
        assert fetched.debtor_name == "Test Dealer"
        assert len(fetched.lines) == 1
        assert fetched.lines[0].quantity == 3

    def test_list_requests_for_contact(self, db: Session):
        """List requests filtered by contact_id."""
        contact_a = _make_contact(db)
        contact_b = _make_contact(db)

        PriceTagRequestService.create_request(
            db,
            contact_id=contact_a.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Dealer A",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [],
            },
        )
        PriceTagRequestService.create_request(
            db,
            contact_id=contact_a.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Dealer B",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [],
            },
        )
        PriceTagRequestService.create_request(
            db,
            contact_id=contact_b.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "Dealer C",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [],
            },
        )
        db.flush()

        results = PriceTagRequestService.list_requests(db, contact_id=contact_a.id)
        assert len(results) == 2
        assert all(r.contact_id == contact_a.id for r in results)


class TestTheMarketingQueueHoldsOnlySubmittedWork:
    """A portal draft belongs to the salesperson until they submit it.

    It used to appear in marketing's queue the moment it was saved, at status
    ``new`` like every submitted request, with nothing on the row to tell them
    apart. Marketing could claim a form somebody was still typing; the claim
    moved it to ``designing``, and the salesperson's Submit then set it straight
    back to ``new`` - wiping the claim, re-firing the form SLA and leaving the
    designer working on a request that no longer said it was theirs.
    """

    def _draft_and_submitted(self, db: Session):
        contact = _make_contact(db)
        draft = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "ZZT Draft"},
        )
        submitted = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "ZZT Submitted"},
        )
        submitted.portal_draft_at = None
        db.flush()
        return contact, draft, submitted

    def test_a_draft_is_not_in_the_marketing_queue(self, db: Session):
        _contact, draft, submitted = self._draft_and_submitted(db)

        rows = PriceTagRequestService.list_requests(db, include_drafts=False)

        ids = {row.id for row in rows}
        assert submitted.id in ids
        assert draft.id not in ids

    def test_the_portal_still_lists_the_contact_their_own_draft(self, db: Session):
        """The portal list is the other half: a draft is exactly what it is for."""
        contact, draft, submitted = self._draft_and_submitted(db)

        rows = PriceTagRequestService.list_requests(db, contact_id=contact.id)

        ids = {row.id for row in rows}
        assert {draft.id, submitted.id} <= ids

    def test_a_draft_cannot_be_claimed(self, db: Session):
        _contact, draft, _submitted = self._draft_and_submitted(db)

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_claimable(draft)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "NOT_SUBMITTED"

    def test_a_submitted_request_can_be_claimed(self, db: Session):
        _contact, _draft, submitted = self._draft_and_submitted(db)

        PriceTagRequestService.validate_claimable(submitted)  # does not raise

    def test_a_request_already_being_designed_cannot_be_claimed_again(
        self, db: Session
    ):
        _contact, _draft, submitted = self._draft_and_submitted(db)
        submitted.status = STATUS_DESIGNING
        db.flush()

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_claimable(submitted)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "INVALID_STATE"


# ---------------------------------------------------------------------------
# 6. Debtor lookup scoping
# ---------------------------------------------------------------------------


class TestDebtorLookup:
    def test_contact_linked_to_agent_with_customers(self, db: Session):
        """Contact linked to SalesAgent who has customers.sales_agent_id returns those customers."""
        contact = _make_contact(db)
        agent = _make_sales_agent(db, contact_id=contact.id)
        cust = _make_customer(db, sales_agent_id=agent.id)

        debtors = PriceTagRequestService.lookup_debtors_for_agent(db, contact.id)
        codes = [d["customer_code"] for d in debtors]
        assert cust.customer_code in codes

    def test_contact_linked_to_agent_with_orders(self, db: Session):
        """Contact linked to SalesAgent who has orders returns debtors from those orders."""
        contact = _make_contact(db)
        agent = _make_sales_agent(db, contact_id=contact.id)
        # Create an order with debtor info, linked via agent name.
        order = Order(
            id=str(uuid.uuid4()),
            order_number=unique_code("ord"),
            debtor_code="D-001",
            debtor_name="Some Dealer",
            agent=agent.sales_agent,
            order_date=date.today() - timedelta(days=30),
        )
        db.add(order)
        db.flush()

        debtors = PriceTagRequestService.lookup_debtors_for_agent(db, contact.id)
        codes = [d["debtor_code"] for d in debtors if d.get("debtor_code")]
        assert "D-001" in codes

    def test_contact_not_linked(self, db: Session):
        """Contact not linked to any SalesAgent returns empty list."""
        contact = _make_contact(db)

        debtors = PriceTagRequestService.lookup_debtors_for_agent(db, contact.id)
        assert debtors == []


# ---------------------------------------------------------------------------
# Merged item lookup (D47)
#
# The lines table asks ONE dropdown for both sets and products, because a dealer
# does not know which of the two a thing is. It has to answer with the real
# `products.id` / `product_sets.id`: `price_tag_request_lines.product_id` is a
# uuid foreign key, and the portal's own product lookup returns no id at all, so
# the form was posting a product CODE into it.
# ---------------------------------------------------------------------------


class TestTagItemLookup:
    def test_lookup_returns_sets_and_products_together(self, db: Session):
        product = _make_product(db, product_code="ZZTLOOKUP-P")
        product_set = _make_product_set(db)

        items = PriceTagRequestService.lookup_tag_items(db, None, limit=50)

        by_id = {i["id"]: i for i in items}
        assert product.id in by_id
        assert product_set.id in by_id
        assert by_id[product.id]["kind"] == "product"
        assert by_id[product.id]["code"] == "ZZTLOOKUP-P"
        assert by_id[product_set.id]["kind"] == "product_set"
        assert by_id[product_set.id]["code"] == product_set.set_code

    def test_lookup_ids_are_the_real_row_ids(self, db: Session):
        """What the picker returns is what a line's foreign key stores.

        A code here is refused by Postgres on the insert, which is exactly the
        bug this endpoint exists to remove.
        """
        product = _make_product(db, product_code="ZZTLOOKUP-FK")
        contact = _make_contact(db)

        item = next(
            i
            for i in PriceTagRequestService.lookup_tag_items(db, "ZZTLOOKUP-FK")
            if i["code"] == "ZZTLOOKUP-FK"
        )

        request = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": item["id"],
                        "quantity": 2,
                    }
                ],
            },
        )
        db.flush()
        assert request.lines[0].product_id == product.id

    def test_lookup_honours_the_query(self, db: Session):
        _make_product(db, product_code="ZZTFINDME-P")
        _make_product(db, product_code="ZZTOTHER-P")

        codes = [i["code"] for i in PriceTagRequestService.lookup_tag_items(db, "ZZTFINDME")]
        assert codes == ["ZZTFINDME-P"]


# ---------------------------------------------------------------------------
# 8. A draft saves with nothing in it; SUBMIT is where completeness is enforced
#    (D48a, AC-M.17 / AC-M.18)
#
# The salesperson types a form over several sittings. Refusing to store what is
# there so far is what pushed them into pressing Submit to find out what was
# missing, which is the round this suite grew out of.
# ---------------------------------------------------------------------------


class TestDraftWithoutRequiredFields:
    def test_draft_with_nothing_but_one_line(self, db: Session):
        """No debtor, no date: the row stores both as NULL and keeps the line."""
        contact = _make_contact(db)
        product = _make_product(db, class_label="Kitchen Sink")

        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "lines": [{"line_type": "product", "product_id": product.id}],
            },
        )
        db.flush()

        assert req.debtor_name is None
        assert req.needed_by_date is None
        assert req.portal_draft_at is not None
        assert len(req.lines) == 1

    def test_draft_with_nothing_but_a_debtor(self, db: Session):
        contact = _make_contact(db)

        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={"debtor_name": "ZZT Half A Form"},
        )
        db.flush()

        assert req.debtor_name == "ZZT Half A Form"
        assert req.needed_by_date is None
        assert req.lines == []

    def test_a_saved_draft_still_lists(self, db: Session):
        """A null debtor must not break the list the landing reads."""
        contact = _make_contact(db)
        PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={},
        )
        db.flush()

        rows = PriceTagRequestService.list_requests(db, contact_id=contact.id)
        assert len(rows) == 1
        assert rows[0].debtor_name is None


class TestTheDebtorLookupIsDeterministic:
    """Two agents linked to one contact must not answer differently per call.

    ``sales_agents.contact_id`` carries no unique constraint, and the lookup took
    ``.first()`` off an unordered query: Postgres is free to return either row,
    so the same salesperson could open the form twice and be offered two
    different debtor books with nothing on screen to explain it.
    """

    def test_the_same_contact_answers_the_same_agent_every_time(self, db: Session):
        contact = _make_contact(db)
        first = _make_sales_agent(db, contact_id=contact.id)
        second = _make_sales_agent(db, contact_id=contact.id)
        _make_customer(db, sales_agent_id=first.id)
        _make_customer(db, sales_agent_id=second.id)

        answers = [
            {
                row["customer_code"]
                for row in PriceTagRequestService.lookup_debtors_for_agent(
                    db, contact.id
                )
            }
            for _ in range(3)
        ]

        assert answers[0] == answers[1] == answers[2]
        # And it is the ordering the code names, not whichever row came back.
        expected = min([first, second], key=lambda agent: (agent.sales_agent, agent.id))
        customers = {
            row["customer_code"]
            for row in PriceTagRequestService.lookup_debtors_for_agent(db, contact.id)
        }
        assert customers == {
            customer.customer_code
            for customer in db.query(Customer)
            .filter(Customer.sales_agent_id == expected.id)
            .all()
        }


class TestSubmitCompleteness:
    def test_submit_names_every_missing_field(self, db: Session):
        contact = _make_contact(db)
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={},
        )
        db.flush()

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_submittable(req)

        err = exc_info.value
        assert err.status_code == 422
        assert err.detail["code"] == "SUBMIT_INCOMPLETE"
        # The FE routes each key to the field it belongs to, so all three are named.
        assert err.detail["detail"] == "debtor_name,needed_by_date,lines"
        assert "dealer" in err.detail["message"]

    def test_submit_names_only_what_is_missing(self, db: Session):
        contact = _make_contact(db)
        product = _make_product(db, class_label="Kitchen Sink")
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "ZZT Dealer",
                "lines": [{"line_type": "product", "product_id": product.id}],
            },
        )
        db.flush()

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_submittable(req)

        assert exc_info.value.detail["detail"] == "needed_by_date"

    def test_submit_refuses_a_request_with_no_lines(self, db: Session):
        contact = _make_contact(db)
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
            },
        )
        db.flush()

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_submittable(req)

        assert exc_info.value.detail["detail"] == "lines"

    def test_a_complete_request_passes(self, db: Session):
        contact = _make_contact(db)
        product = _make_product(db, class_label="Kitchen Sink")
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [{"line_type": "product", "product_id": product.id}],
            },
        )
        db.flush()

        # No exception is the assertion.
        PriceTagRequestService.validate_submittable(req)

    def test_the_set_guard_names_the_line_it_refused(self, db: Session):
        """The message goes on the ROW, so the refusal has to say which row."""
        contact = _make_contact(db)
        ok_product = _make_product(db, class_label="Kitchen Sink")
        bad_product = _make_product(db, class_label="Bathroom Furniture")
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {"line_type": "product", "product_id": ok_product.id},
                    {"line_type": "product", "product_id": bad_product.id},
                ],
            },
        )
        db.flush()

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_set_guard(db, req)

        err = exc_info.value
        assert err.status_code == 422
        assert err.detail["code"] == "SET_GUARD_VIOLATION"
        assert err.detail["detail"] == "line:1"
        assert bad_product.product_code in err.detail["message"]

    def test_the_set_guard_names_every_line_it_refused(self, db: Session):
        contact = _make_contact(db)
        first = _make_product(db, class_label="Bathroom Furniture")
        second = _make_product(db, class_label="Bathroom Furniture")
        req = PriceTagRequestService.create_request(
            db,
            contact_id=contact.id,
            company_id=_SORENTO_COMPANY_ID,
            data={
                "debtor_name": "ZZT Dealer",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {"line_type": "product", "product_id": first.id},
                    {"line_type": "product", "product_id": second.id},
                ],
            },
        )
        db.flush()

        with pytest.raises(Exception) as exc_info:
            PriceTagRequestService.validate_set_guard(db, req)

        assert exc_info.value.detail["detail"] == "line:0,line:1"
