"""OI-UX-FILTER-SNAPSHOT security review: `so_parties` and company scope.

An so_number is unique per company only (`uq_sales_orders_company_so_number`), so the same
number can name two orders. A company-scoped session must read its own order's customer and
project, never the other company's. An all-company read (an API key with no contact) that finds
one number in two companies cannot tell which order the caller meant: it names nobody (a dash on
screen) rather than whichever row came back first.
"""
from __future__ import annotations

from app.models.base import company_scope
from app.models.order import SalesOrder
from app.services.scm.so_party import EMPTY_PARTY, fill_party, so_parties
from tests.test_finance_billing_documents_api import world  # noqa: F401

PARTY_A = {"customer_name": "ZZT Debtor A", "project_label": "ZZT Tower A"}
PARTY_B = {"customer_name": "ZZT Debtor B", "project_label": "ZZT Tower B"}


def _twin(world):
    """Company A's `world.so` plus an order with the same number in company B."""
    world.so.debtor_name = PARTY_A["customer_name"]
    world.so.project_label = PARTY_A["project_label"]
    with company_scope(world.db, None):
        twin = SalesOrder(
            so_number=world.so.so_number,
            company_id=world.company_b,
            source_system="autocount",
            debtor_name=PARTY_B["customer_name"],
            project_label=PARTY_B["project_label"],
        )
        world.db.add(twin)
        world.db.flush()
    return world.so.so_number, twin


def test_a_company_session_reads_its_own_order_never_the_twin(world):
    number, twin = _twin(world)
    # `world` yields inside company A's scope.
    parties = so_parties(world.db, numbers=[number])
    assert parties[number] == PARTY_A
    assert str(twin.id) not in parties
    by_id = so_parties(world.db, ids=[str(twin.id)])
    assert str(twin.id) not in by_id


def test_an_all_company_read_of_a_shared_number_names_nobody(world):
    number, twin = _twin(world)
    with company_scope(world.db, None):
        by_number = so_parties(world.db, numbers=[number])
        by_id = so_parties(world.db, ids=[str(world.so.id), str(twin.id)])
    assert by_number[number] == EMPTY_PARTY
    assert by_id[number] == EMPTY_PARTY
    # Read by id, each order still answers for itself.
    assert by_id[str(world.so.id)] == PARTY_A
    assert by_id[str(twin.id)] == PARTY_B


def test_an_all_company_read_of_a_unique_number_still_names_it(world):
    world.so2.debtor_name = PARTY_A["customer_name"]
    world.so2.project_label = PARTY_A["project_label"]
    world.db.flush()
    with company_scope(world.db, None):
        parties = so_parties(world.db, numbers=[world.so2.so_number])
    assert parties[world.so2.so_number] == PARTY_A


def test_fill_party_keeps_a_half_the_row_already_names():
    """Seam rule (audit round): a row from an order inquiry already knows its project (and
    sometimes its customer), the way the OI worklist prints them. The sales order fills only
    a blank half; a missing or nameless order never erases what the row knew."""
    parties = {"SO1": {"customer_name": "ZZT Debtor", "project_label": "ZZT SO Label"}}
    row = {"customer_name": None, "project_label": "ZZT Project Title"}
    assert fill_party(row, parties, "SO1") == {
        "customer_name": "ZZT Debtor", "project_label": "ZZT Project Title",
    }
    row = {"customer_name": None, "project_label": None}
    assert fill_party(row, parties, "SO1") == parties["SO1"]
    row = {"customer_name": "ZZT Issuer", "project_label": "ZZT Project Title"}
    assert fill_party(row, {}, "SO-MISSING") == {
        "customer_name": "ZZT Issuer", "project_label": "ZZT Project Title",
    }
    row = {"customer_name": None, "project_label": "ZZT Project Title"}
    assert fill_party(row, {"SO1": dict(EMPTY_PARTY)}, "SO1") == {
        "customer_name": None, "project_label": "ZZT Project Title",
    }
