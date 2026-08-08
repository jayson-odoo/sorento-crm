"""Cost is what we last paid, and the cheapest supplier wins.

> "our cost should come from PO history, and we should pick the cheapest one if got multiple
> suppliers, then in the reorder planning ... should show the alternative supplier with its
> cost and why we chosen what we have chose because it is cheaper"

Two sources describe what a SKU costs. `product_suppliers.unit_cost` is a contracted or
quoted figure somebody typed; a purchase-order line is what we actually paid. The PO wins,
per supplier, most recent first, because it is the only one of the two that is evidence.

The zero case is its own rule and it is NOT the same as no rule at all:

* **no priced purchase order and no contract cost** -> the cost is UNKNOWN. The line cannot
  be budgeted and says so.
* **a purchase order that recorded 0** -> the cost IS zero. 637 lines in the customer's own
  order book are exactly this. A free item still has demand and still has to be planned; what
  stops us ordering the world is the order-up-to level, which is a quantity rule, not a money
  one.

None and 0.0 are therefore kept apart the whole way through, and every test below that says
"free" is checking that they did not get flattened into each other.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import (
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure

from app.services.scm import reorder_engine as eng
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTCST"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    cheap = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name=f"{MARKER} Cheap")
    dear = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name=f"{MARKER} Dear")
    db.add_all([product, cheap, dear])
    db.flush()
    return {"product": product, "cheap": cheap, "dear": dear}


def _contract(db, world, supplier, cost, *, primary=False, lead=30):
    db.add(ProductSupplier(
        id=_u(), product_id=world["product"].id, supplier_id=supplier.id,
        unit_cost=cost, currency="MYR", standard_lead_time_days=lead,
        is_primary_supplier=primary,
    ))
    db.flush()


def _po(db, world, supplier, cost, when: date, *, qty=10):
    po = PurchaseOrder(id=_u(), po_number=unique_code(MARKER), supplier_id=supplier.id,
                       status="closed", issue_date=when, currency="MYR")
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=world["product"].id,
        qty_ordered=qty, qty_received=qty, unit_cost=cost, currency="MYR",
        line_status="closed",
    ))
    db.flush()
    return po


def _candidates(db, world) -> dict[str, dict]:
    """Candidates keyed by supplier name, for readable assertions."""
    rows = eng.load_supplier_candidates(db, str(world["product"].id))
    return {c["supplier_name"]: c for c in rows}


# --------------------------------------------------------------------------- #
# where the cost comes from
# --------------------------------------------------------------------------- #

def test_the_last_purchase_order_beats_the_contract_price(db, world):
    """The contract says 10, we actually paid 8 last month. We cost the plan at 8."""
    _contract(db, world, world["cheap"], 10)
    _po(db, world, world["cheap"], 8, date(2026, 6, 1))

    cand = _candidates(db, world)[f"{MARKER} Cheap"]

    assert cand["unit_cost"] == 8.0
    assert cand["unit_cost_source"] == "last_po"


def test_the_most_recent_purchase_order_wins(db, world):
    _contract(db, world, world["cheap"], 10)
    _po(db, world, world["cheap"], 9, date(2026, 1, 1))
    _po(db, world, world["cheap"], 7, date(2026, 6, 1))

    assert _candidates(db, world)[f"{MARKER} Cheap"]["unit_cost"] == 7.0


def test_a_purchase_order_from_ANOTHER_supplier_does_not_price_this_one(db, world):
    """Pricing a buy against a supplier we are not buying from is worse than saying
    nothing: it reads as a real quote and it is not one."""
    _contract(db, world, world["cheap"], 10)
    _contract(db, world, world["dear"], None)
    _po(db, world, world["cheap"], 4, date(2026, 6, 1))

    cands = _candidates(db, world)
    assert cands[f"{MARKER} Cheap"]["unit_cost"] == 4.0
    assert cands[f"{MARKER} Dear"]["unit_cost"] is None


def test_the_contract_price_is_used_when_we_have_never_bought_from_them(db, world):
    _contract(db, world, world["dear"], 12)

    cand = _candidates(db, world)[f"{MARKER} Dear"]

    assert cand["unit_cost"] == 12.0
    assert cand["unit_cost_source"] == "contract"


def test_no_purchase_order_and_no_contract_price_leaves_the_cost_unknown(db, world):
    """Unknown, not zero. A zero would be budgeted as free and quietly funded."""
    _contract(db, world, world["dear"], None)

    cand = _candidates(db, world)[f"{MARKER} Dear"]

    assert cand["unit_cost"] is None
    assert cand["unit_cost_source"] is None


def test_the_purchase_order_number_and_date_travel_with_the_cost(db, world):
    """So the buyer can check the figure rather than take it on trust."""
    _contract(db, world, world["cheap"], 10)
    po = _po(db, world, world["cheap"], 8, date(2026, 6, 1))

    cand = _candidates(db, world)[f"{MARKER} Cheap"]

    assert cand["unit_cost_ref"] == po.po_number
    assert cand["unit_cost_at"] == date(2026, 6, 1)


# --------------------------------------------------------------------------- #
# zero is a price
# --------------------------------------------------------------------------- #

def test_a_purchase_order_recording_zero_is_a_price_of_zero(db, world):
    """637 lines in the customer's book are exactly this. Free, not unknown."""
    _po(db, world, world["cheap"], 0, date(2026, 6, 1))

    cand = _candidates(db, world)[f"{MARKER} Cheap"]

    assert cand["unit_cost"] == 0.0
    assert cand["unit_cost"] is not None, "free collapsed into unknown"
    assert cand["unit_cost_source"] == "last_po"


def test_a_free_item_still_beats_an_unknown_one_when_choosing(db, world):
    """Nothing about a free item stops it being planned. Only quantity rules do that."""
    _contract(db, world, world["dear"], None)
    _po(db, world, world["cheap"], 0, date(2026, 6, 1))
    _contract(db, world, world["cheap"], None)

    sel = eng.select_supplier(list(_candidates(db, world).values()), selection="lowest_cost")

    assert sel["chosen"]["supplier_name"] == f"{MARKER} Cheap"


# --------------------------------------------------------------------------- #
# the cheapest supplier, and why
# --------------------------------------------------------------------------- #

def test_the_cheapest_supplier_is_chosen_by_default(db, world):
    """> "we should pick the cheapest one if got multiple suppliers" - so cost leads, and
    `is_primary` becomes the tiebreak rather than the rule."""
    _contract(db, world, world["dear"], 12, primary=True)
    _contract(db, world, world["cheap"], 8)

    sel = eng.select_supplier(list(_candidates(db, world).values()))

    assert sel["chosen"]["supplier_name"] == f"{MARKER} Cheap"


def test_the_choice_says_why_and_by_how_much(db, world):
    """The popup has to explain itself: "cheaper" is the reason, and the gap is the proof."""
    _contract(db, world, world["dear"], 12)
    _contract(db, world, world["cheap"], 8)

    sel = eng.select_supplier(list(_candidates(db, world).values()))

    assert sel["reason"]["basis"] == "lowest_cost"
    assert sel["reason"]["saving_per_unit"] == 4.0
    assert sel["reason"]["runner_up"] == f"{MARKER} Dear"


def test_a_supplier_with_no_cost_never_wins_on_price(db, world):
    """An unknown cost is not a cheap one. Otherwise the least-known supplier always wins."""
    _contract(db, world, world["dear"], None)
    _contract(db, world, world["cheap"], 8)

    sel = eng.select_supplier(list(_candidates(db, world).values()))

    assert sel["chosen"]["supplier_name"] == f"{MARKER} Cheap"


def test_the_only_supplier_is_chosen_without_claiming_it_was_cheapest(db, world):
    """With nothing to compare against, "chosen because cheaper" would be a fabrication."""
    _contract(db, world, world["cheap"], 8)

    sel = eng.select_supplier(list(_candidates(db, world).values()))

    assert sel["chosen"]["supplier_name"] == f"{MARKER} Cheap"
    assert sel["reason"]["basis"] == "only_supplier"
    assert sel["reason"].get("saving_per_unit") is None


def test_the_alternatives_carry_their_own_cost(db, world):
    _contract(db, world, world["dear"], 12)
    _contract(db, world, world["cheap"], 8)

    sel = eng.select_supplier(list(_candidates(db, world).values()))

    assert [a["unit_cost"] for a in sel["alternatives"]] == [12.0]
