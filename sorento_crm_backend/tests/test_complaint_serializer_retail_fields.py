"""A retail complaint rendered as a page of dashes.

`complaints` has carried the after-sales columns since S1 - `reported_by_role`, the
site address and its parts, the pin - and `_serialize_complaint` has always put every
one of them in its dict, because it builds that dict from the mapper's column
attributes. `ComplaintResponse` simply never declared them, so Pydantic dropped the
lot on the way out. The staff detail screen for a complaint lodged through the consumer
portal therefore had no address, no pin, and no way to tell a retail case from a
project one.

Product lines were worse than dropped: the serializer never emitted the key at all, so
the response model filled in its `[]` default and the frontend fell back to splitting
the denormalised `product_code` CSV - a column the consumer journey never writes. A
complaint with a product line showed no products.

These tests pin the serializer, not the schema, because the schema is where the fields
were missing and a schema-only assertion would pass against a serializer that stopped
emitting them.

Run: venv/bin/python -m pytest tests/test_complaint_serializer_retail_fields.py -q -p no:randomly
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.complaints import Complaint, ComplaintProductLine
from app.schemas.complaints import ComplaintResponse
from app.services.complaints_service import ComplaintService
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _complaint(db, **overrides) -> Complaint:
    row = Complaint(
        complaint_number=unique_code("CMP"),
        status="submitted",
        **overrides,
    )
    db.add(row)
    db.flush()
    return row


def _line(db, complaint, **overrides) -> ComplaintProductLine:
    line = ComplaintProductLine(
        complaint_id=complaint.id,
        product_code=overrides.pop("product_code", unique_code("SKU")),
        **overrides,
    )
    db.add(line)
    db.flush()
    db.refresh(complaint)
    return line


class TestTheSiteAndTheReporter:
    def test_a_consumer_complaint_carries_its_site_address_in_parts(self, db):
        complaint = _complaint(
            db,
            reported_by_role="end_user",
            site_address="5 Jalan Impiana 1A, Taman Bukit Impiana, 43000 Kajang, Selangor, Malaysia",
            site_address_line1="5 Jalan Impiana 1A",
            site_address_line2="Taman Bukit Impiana",
            site_postcode="43000",
            site_city="Kajang",
            site_state="Selangor",
            site_country="Malaysia",
        )
        data = ComplaintService(db)._serialize_complaint(complaint)
        response = ComplaintResponse(**data)

        assert response.reported_by_role == "end_user"
        assert response.site_address_line1 == "5 Jalan Impiana 1A"
        assert response.site_postcode == "43000"
        assert response.site_city == "Kajang"
        assert response.site_state == "Selangor"
        assert response.site_country == "Malaysia"

    def test_the_pin_survives_the_response_model_as_a_decimal(self, db):
        # A float does not round-trip a coordinate copied between systems, and this is
        # what a technician navigates to.
        complaint = _complaint(
            db,
            reported_by_role="end_user",
            latitude=Decimal("3.1184313"),
            longitude=Decimal("101.6020993"),
        )
        response = ComplaintResponse(**ComplaintService(db)._serialize_complaint(complaint))
        assert response.latitude == Decimal("3.1184313")
        assert response.longitude == Decimal("101.6020993")

    def test_a_project_complaint_still_serializes_its_own_fields(self, db):
        # The point of keeping one entity: the project path must not lose anything.
        complaint = _complaint(
            db,
            delivery_order_number="DO-ZZT-1",
            customer_type="Project",
            salesperson="Ahmad",
            project_title="Tower B refit",
        )
        response = ComplaintResponse(**ComplaintService(db)._serialize_complaint(complaint))
        assert response.delivery_order_number == "DO-ZZT-1"
        assert response.project_title == "Tower B refit"
        assert response.salesperson == "Ahmad"
        # And it asserts nothing about who reported it, which is the honest value.
        assert response.reported_by_role is None
        assert response.site_address is None


class TestProductLines:
    def test_a_line_reaches_the_response_at_all(self, db):
        complaint = _complaint(db, reported_by_role="end_user")
        _line(db, complaint, product_code="ZZT-SRTWC8152", quantity="1")

        response = ComplaintResponse(**ComplaintService(db)._serialize_complaint(complaint))
        assert [line.product_code for line in response.product_lines] == ["ZZT-SRTWC8152"]

    def test_both_halves_of_the_line_survive(self, db):
        """`product_code` is what CS types; `claimed_text` is what the consumer said.

        Neither substitutes for the other: a code like SRTWC8152 matches three real
        variants and resolves to none of them (AC-C17), so the verbatim words are the
        only thing an agent can act on when resolution fails.
        """
        complaint = _complaint(db, reported_by_role="end_user")
        _line(
            db,
            complaint,
            product_code="ZZT-SRTWC8152",
            claimed_text="the toilet in the guest bathroom",
            fault_description="Cistern leaking from the base.",
        )
        response = ComplaintResponse(**ComplaintService(db)._serialize_complaint(complaint))
        line = response.product_lines[0]
        assert line.claimed_text == "the toilet in the guest bathroom"
        assert line.fault_description == "Cistern leaking from the base."

    def test_a_line_with_nothing_resolved_reports_nothing_rather_than_failing(self, db):
        # The ordinary consumer line: no matched variant, no kind, no receipt yet.
        complaint = _complaint(db, reported_by_role="end_user")
        _line(db, complaint, product_code="ZZT-UNKNOWN")
        line = ComplaintResponse(
            **ComplaintService(db)._serialize_complaint(complaint)
        ).product_lines[0]
        assert line.kind_name is None
        assert line.product_name is None
        assert line.defect_type_name is None
        assert line.purchase_number is None
        assert line.purchase_date is None

    def test_ids_are_resolved_to_names_because_the_ui_may_not_show_a_uuid(self, db):
        from app.models.warranty import WarrantyProductKind

        kind = WarrantyProductKind(code=unique_code("KIND"), name="Water Closet")
        db.add(kind)
        db.flush()

        complaint = _complaint(db, reported_by_role="end_user")
        _line(db, complaint, product_code="ZZT-SRTWC8152", kind_id=kind.id)

        line = ComplaintResponse(
            **ComplaintService(db)._serialize_complaint(complaint)
        ).product_lines[0]
        assert line.kind_name == "Water Closet"

    def test_the_purchase_a_line_is_covered_by_comes_through_as_number_and_date(self, db):
        from app.models.consumers import (
            ConsumerProfile,
            ConsumerPurchase,
            ConsumerPurchaseLine,
        )

        profile = ConsumerProfile(consent_purpose="warranty")
        db.add(profile)
        db.flush()
        purchase = ConsumerPurchase(
            purchase_number=unique_code("CP"),
            consumer_profile_id=profile.id,
            purchase_date=date(2026, 8, 3),
        )
        db.add(purchase)
        db.flush()
        purchase_line = ConsumerPurchaseLine(
            purchase_id=purchase.id,
            kind_code="water_closet",
        )
        db.add(purchase_line)
        db.flush()

        complaint = _complaint(db, reported_by_role="end_user")
        _line(
            db,
            complaint,
            product_code="ZZT-SRTWC8152",
            consumer_purchase_line_id=purchase_line.id,
        )

        line = ComplaintResponse(
            **ComplaintService(db)._serialize_complaint(complaint)
        ).product_lines[0]
        assert line.purchase_number == purchase.purchase_number
        assert line.purchase_date == date(2026, 8, 3)


class TestTheBatchedPath:
    def test_a_caller_that_batched_lookups_gets_the_same_answer(self, db):
        """The list path resolves names once for the whole page.

        A per-row resolve would be four queries per line per row; the override exists
        so a 50-row page does not fan out. It has to produce identical output to the
        detail path, or the list and the detail screen disagree about the same line.
        """
        from app.models.warranty import WarrantyProductKind

        kind = WarrantyProductKind(code=unique_code("KIND"), name="Basin")
        db.add(kind)
        db.flush()

        complaint = _complaint(db, reported_by_role="end_user")
        _line(db, complaint, product_code="ZZT-BASIN", kind_id=kind.id)

        service = ComplaintService(db)
        per_row = service._serialize_complaint(complaint)["product_lines"]
        batched = service._serialize_complaint(
            complaint,
            line_lookups_override=service._batch_product_line_lookups([complaint]),
        )["product_lines"]
        assert per_row == batched
        assert batched[0]["kind_name"] == "Basin"

    def test_an_empty_batch_is_a_total_function(self, db):
        # A page whose rows carry no lines must not KeyError halfway through.
        complaint = _complaint(db)
        service = ComplaintService(db)
        lookups = service._batch_product_line_lookups([complaint])
        assert service._serialize_complaint(
            complaint, line_lookups_override=lookups
        )["product_lines"] == []
