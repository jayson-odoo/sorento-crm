"""Where a sales order's demand class comes from, and what happens when it cannot be had.

`scm.priority_policy.demand_class_weights` is keyed on `sales_orders.demand_class`, so this
one column decides whose order is fulfilled first when stock is short. It is currently NULL
on every row in the dev database, which means the weighting is running on a field nobody
writes: every order is scoring identically and the policy is decorative.

The plan amendment of 4 Aug 2026 settled where the value comes from. `order_type` is the
field the business actually fills in (9 `project`, 5 `dealer`, 3 null), while
`customers.market_segment_code` is NULL on 3,276 of 3,284 customers. So the split is read
from `order_type` and STAMPED onto `demand_class` at import; the market segment survives
only as a fallback, and the loud failure moves onto an absent `order_type`.

These tests pin the four halves of that: the stamp, the fallback, the report, and the
promise that a later upload can never downgrade a classification it cannot improve on.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.access import MarketSegment
from app.models.order import Customer, SalesOrder
from app.services.scm import outstanding_import_service as svc
from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    MARKER,
    Codes,
    make_codes,
    seed_catalogue,
    workbook,
)

# Every column the SO aliases resolve that this scenario needs, and nothing else: the
# document, who it is for, what and how much, when and from where. Deliberately NOT the
# full extract header, because these tests are about one column's provenance and a wider
# file would only add rows that could fail for unrelated reasons.
HEADERS = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION")


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def codes() -> Codes:
    return make_codes()


@pytest.fixture()
def seeded(db, codes):
    """Products and warehouses under the exact codes this test's upload names."""
    seed_catalogue(db, codes)
    return codes


def _upload(codes: Codes, doc: str, debtor: str, *, qty: float = 40) -> bytes:
    """A one-line outstanding-SO extract for `doc`, stating `debtor` as its customer."""
    return workbook(
        [(doc, debtor, codes.item_rl, qty, date(2026, 7, 1), codes.loc_project)],
        headers=HEADERS,
    )


def _order_row(db, so_number: str, *, order_type=None, demand_class=None) -> str:
    """A sales-order header this test owns, in whatever state the scenario needs.

    Seeded rather than borrowed: the classification is read off the header, so a test that
    reused a real order would be asserting about production data.
    """
    oid = _u()
    db.add(SalesOrder(id=oid, so_number=so_number, status="open",
                      order_type=order_type, demand_class=demand_class))
    db.flush()
    return oid


def _demand_class(db, so_number: str):
    return db.execute(
        text("SELECT demand_class FROM sales_orders WHERE so_number = :n"),
        {"n": so_number},
    ).scalar()


def _customer_with_segment(db, stem: str) -> str:
    """A customer whose market segment code carries `stem`, returning its customer code.

    `_class_of` matches "project" / "contract" as a substring of the segment code,
    so a marker-prefixed code classifies exactly as a production one does while still
    belonging to this test.
    """
    seg = f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".lower()
    db.add(MarketSegment(id=_u(), code=seg, name=seg, is_active=True))
    db.flush()
    code = f"{MARKER}-C-{uuid.uuid4().hex[:8]}".upper()
    db.add(Customer(id=_u(), customer_code=code, customer_name=code,
                    market_segment_code=seg, is_active=True))
    db.flush()
    return code


def _reported(payload: dict) -> list[str]:
    """Everything this upload told a human about, flattened to searchable text.

    Row problems and resolution issues are two lists for good reasons upstream, but a test
    about "was anyone told" must not care which of the two carried the message, or it pins
    an implementation choice instead of the promise.
    """
    out: list[str] = []
    for item in list(payload.get("resolution_issues") or []) + list(
        payload.get("row_problems") or []
    ):
        out.append(" ".join(str(v) for v in item.values()))
    return out


# --------------------------------------------------------------------------- #
# 1. the stamp
# --------------------------------------------------------------------------- #

def test_a_project_order_is_stamped_project_from_its_order_type(db, seeded):
    """A project order that scores as retail is a project that loses its stock to a dealer.

    `order_type` is the only populated evidence of the split in this database, and nothing
    currently copies it onto the column the priority policy actually weighs, so today every
    project order arrives at the planner indistinguishable from a trade counter order.
    """
    _order_row(db, seeded.project_so, order_type="project")

    out = svc.apply(db, _upload(seeded, seeded.project_so, "300-T012"), SO)

    assert out["ok"]
    assert _demand_class(db, seeded.project_so) == "project"


def test_a_dealer_order_is_stamped_the_default_class_from_its_order_type(db, seeded):
    """The other half of the same decision, and the one that keeps the vocabulary honest.

    The existing code already has a name for "not a project" (`DEFAULT_DEMAND_CLASS`), and
    the seeded `demand_class_weights` are keyed on it. A dealer order stamped with some new
    word like "dealer" would silently fall outside the weights map and score as nothing.
    """
    _order_row(db, seeded.dealer_so, order_type="dealer")

    out = svc.apply(db, _upload(seeded, seeded.dealer_so, "300-A031"), SO)

    assert out["ok"]
    assert _demand_class(db, seeded.dealer_so) == DEFAULT_DEMAND_CLASS


# --------------------------------------------------------------------------- #
# 2. the fallback
# --------------------------------------------------------------------------- #

def test_an_order_with_no_order_type_falls_back_to_the_customers_market_segment(db, seeded):
    """The segment is thin evidence, but it is evidence, and discarding it costs accuracy.

    Eight customers in this database do carry a segment. Where `order_type` is absent and
    the segment resolves, that answer is better than the default, and refusing to use it
    would report a problem we could actually have solved.
    """
    debtor = _customer_with_segment(db, "PROJECT")

    out = svc.apply(db, _upload(seeded, seeded.project_so, debtor), SO)

    assert out["ok"]
    assert _demand_class(db, seeded.project_so) == "project"


# --------------------------------------------------------------------------- #
# 3. the report
# --------------------------------------------------------------------------- #

def test_an_order_with_neither_an_order_type_nor_a_segment_is_reported(db, seeded):
    """Silently defaulting is how a project order ends up scored as retail for ever.

    Three orders in the dev database have no `order_type`, and they are exactly the rows a
    human has to fix. If the importer quietly writes the default instead of naming the
    document, nobody ever learns which orders are mis-prioritised, and the wrong answer is
    stable, so no later upload surfaces it either.
    """
    unknown = f"{MARKER}-NOCUST-{uuid.uuid4().hex[:8]}".upper()

    preview = svc.preview(db, _upload(seeded, seeded.project_so, unknown), SO).to_dict()
    applied = svc.apply(db, _upload(seeded, seeded.project_so, unknown), SO)

    assert any(seeded.project_so in text_ for text_ in _reported(preview)), (
        "the preview showed nothing about an order it cannot classify")
    assert any(seeded.project_so in text_ for text_ in _reported(applied)), (
        "the commit wrote an unclassifiable order without naming it")


# --------------------------------------------------------------------------- #
# 4. never downgraded
# --------------------------------------------------------------------------- #

def test_a_demand_class_already_set_survives_an_upload_that_cannot_resolve_one(db, seeded):
    """A weekly re-upload must never be able to make the planner's answer worse.

    The extract is re-uploaded every week over the same orders. If a later file whose
    customer no longer resolves overwrote a known classification with the default, a project
    would quietly demote itself to retail mid-fulfilment, and the only visible symptom would
    be that it stopped winning stock.
    """
    order = seeded.project_so
    _order_row(db, order, order_type="project")

    svc.apply(db, _upload(seeded, order, "300-T012"), SO)
    assert _demand_class(db, order) == "project", "the first upload never stamped it"

    # The business clears `order_type` on the header and the next extract names a customer
    # this company does not hold, so the second upload has nothing to resolve from.
    db.execute(text("UPDATE sales_orders SET order_type = NULL WHERE so_number = :n"),
               {"n": order})
    db.expire_all()
    unknown = f"{MARKER}-NOCUST-{uuid.uuid4().hex[:8]}".upper()

    svc.apply(db, _upload(seeded, order, unknown, qty=55), SO)

    assert _demand_class(db, order) == "project"


# --------------------------------------------------------------------------- #
# 5. guard: the existing segment reading is unchanged
# --------------------------------------------------------------------------- #

def test_a_customer_carrying_a_project_segment_still_reads_as_project(db, seeded):
    """The fallback is a demotion of this rule, not a rewrite of it.

    `_class_of` over `_segment_of` is the only place the segment vocabulary lives, and it
    stays the fallback's implementation. Green before the change and after: if it goes red,
    the fallback's meaning moved rather than its priority. There is no defaulting wrapper
    to call here any more (QP1): the import refuses what it cannot classify.
    """
    project = _customer_with_segment(db, "PROJECT")
    retail = _customer_with_segment(db, "RETAIL")

    assert svc._class_of(svc._segment_of(db, project)) == "project"
    assert svc._class_of(svc._segment_of(db, retail)) == "retail"
