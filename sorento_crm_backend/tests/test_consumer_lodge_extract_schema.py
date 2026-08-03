"""S3 - what the extractor is told to read off a CONSUMER's receipt.

`portal.consumer_lodge` exists because `portal.complaint` reads the wrong document. That
form is the dealer/CS track: it asks for a Sorento delivery order number and for the BUYER
being billed. A consumer's attachment is the dealer's OWN invoice, and the S3-pre spike
measured exactly why the difference matters
(`documentation/plans/after-sales/S3-pre-extraction-accuracy.md`).

Three properties are asserted, and each one is a prompt instruction that cost a real
measurement:

1. **No delivery-order field on the consumer track** (AC-C12). Six dealer document numbers
   were tested against `orders` and every one was a NO MATCH: `KCS-2112-0054`, `CS002629`,
   `NV20-2-008850`, `IV01029`, `DO10-2-123494`, `CS40964`. A `delivery_order_number` field
   here would be populated with a dealer's number that matches nothing, and the first person
   to see the field name would join on it.

2. **The shop is the SELLER, not a buyer.** `portal.complaint` explicitly instructs the
   model that `customer_name` is the debtor being billed and NOT the company on the
   letterhead. On a consumer's receipt the company on the letterhead IS the answer. Reusing
   that instruction would reliably extract the wrong party, or nothing.

3. **A date must not be invented.** 97% of receipts print one, so the 3% matters more than
   it looks: a guessed purchase date silently becomes every warranty verdict computed from
   it, and on screen it is indistinguishable from one that was read. Malaysian receipts
   print DD/MM/YYYY, so the instruction has to say so or 16/10/2025 comes back as April.

Run: venv/bin/python -m pytest tests/test_consumer_lodge_extract_schema.py -q -p no:randomly
"""
from __future__ import annotations

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from app.services.ai_extract.extract_service import FORMS_WITH_LINE_ITEMS  # noqa: E402
from app.services.ai_extract.form_schema_registry import get_form_schema  # noqa: E402

FORM_KEY = "portal.consumer_lodge"


@pytest.fixture
def schema():
    fields = get_form_schema(FORM_KEY)
    assert fields, (
        f"{FORM_KEY} is not registered. Reusing portal.complaint would ask the model for a "
        "Sorento DO number that a dealer's receipt never carries, and for the buyer being "
        "billed rather than the shop that sold the item."
    )
    return {f.name: f for f in fields}


def test_the_consumer_track_never_asks_for_a_delivery_order_number(schema):
    """AC-C12. Six dealer document numbers, six no-matches against `orders`."""
    assert "delivery_order_number" not in schema, (
        "A delivery-order field on the consumer track gets filled with a dealer's own "
        "number, which matches nothing in `orders` - and the field name invites somebody "
        "to join on it anyway."
    )


def test_the_dealer_document_number_is_kept_verbatim_and_never_matched(schema):
    """It is evidence, not a key. Normalising it loses the thing a CS agent would quote
    back to the dealer when asking what was sold.
    """
    field = schema.get("dealer_document_number")
    assert field is not None, "The dealer's own number is the receipt's identity."
    note = (field.note or "").lower()
    assert "not a sorento order" in note or "never be matched" in note, (
        "The instruction must say this is not a Sorento order number. Without it the model "
        "reaches for whatever looks most like one."
    )


def test_the_shop_is_described_as_the_seller(schema):
    """The opposite instruction to `portal.complaint`'s customer_name, on purpose."""
    field = schema.get("shop_name")
    assert field is not None
    note = (field.note or "").lower()
    assert "sold" in note or "seller" in note
    assert "not a buyer" in note or "not a buyer being billed" in note, (
        "Without this the model applies the DO-form habit and returns the debtor, or "
        "nothing at all, from a document that has no debtor on it."
    )


def test_the_shop_instruction_forbids_answering_sorento(schema):
    """Measured: an unstripped "SORENTO SDN BHD" matched "SL & A SDN BHD" at 0.42 on the
    strength of the shared corporate suffix alone. Feeding the resolver "Sorento" from a
    dealer's receipt starts that chain.
    """
    note = (schema["shop_name"].note or "").lower()
    assert "sorento" in note


def test_the_branch_in_brackets_is_kept_rather_than_cleaned_up(schema):
    """The resolver strips branch qualifiers itself, on BOTH sides, and stripping lifted
    exact resolution from 23 to 26 of 38. If the extractor cleans them first, the resolver
    cannot tell a real branch from a name that never had one, and its own rule goes untested
    against live data.
    """
    note = (schema["shop_name"].note or "").lower()
    assert "bracket" in note or "as printed" in note


def test_a_date_that_cannot_be_read_is_left_empty(schema):
    """A guessed date is a guess wearing every verdict computed from it, and on screen it
    looks exactly like one that was read off the paper.
    """
    note = (schema["purchase_date"].note or "").lower()
    assert "nothing" in note or "leave" in note


def test_the_date_instruction_states_the_malaysian_order(schema):
    """DD/MM/YYYY. Without saying so, 16/10/2025 comes back as 2025-04-10 - a plausible
    date, seven months wrong, and silently inside the warranty window instead of outside it.
    """
    note = (schema["purchase_date"].note or "").lower()
    assert "dd/mm" in note


def test_the_total_is_never_spread_across_the_lines(schema):
    """Fork 4. A receipt does not say what each item cost; a per-line number we invented is
    indistinguishable on screen from one we read.
    """
    note = (schema["total_value"].note or "").lower()
    assert "never spread" in note or "never" in note


def test_the_sorento_order_number_is_the_dealer_track_only(schema):
    """AC-C13. `202604-0348` DOES match exactly one order, so the field is worth having -
    but only when Sorento issued the document. Offering the dealer's own number in its
    place is the failure this note exists to prevent.
    """
    field = schema.get("sorento_order_number")
    assert field is not None
    note = (field.note or "").lower()
    assert "only" in note
    assert "dealer" in note


def test_the_consumer_receipt_returns_product_lines(schema):
    """A shop and a date attached to nothing teaches the ledger nothing. The whole point of
    reading the receipt is learning WHICH products this person now owns.
    """
    assert FORM_KEY in FORMS_WITH_LINE_ITEMS


def test_nothing_on_the_consumer_track_is_required(schema):
    """AC-C14 reaching the schema. 24% of receipts print no usable shop name and every
    extracted value lands in an editable field, so a schema that could refuse would refuse
    a quarter of real traffic.
    """
    for field in schema.values():
        assert not getattr(field, "required", False), (
            f"{field.name} is required. Nothing extracted from a consumer's photo may "
            "block the report."
        )
