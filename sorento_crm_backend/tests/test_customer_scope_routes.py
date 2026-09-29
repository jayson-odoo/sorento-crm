"""Phase 2 RED tests - the order routes refuse a scoped contact's foreign customers (D5).

`documentation/plans/chatbot/PLAN-chatbot-customer-scope-29sep.md` D5 and
`chatbot-customer-scope-29sep-acceptance-criteria.md` AC-CS-40 to AC-CS-46 (plus the route
half of AC-CS-05).

The contact arrives as `contact_id` + `space_id` exactly as `tests/test_top_selling_report.py`
sends it (`_as_contact`: the INTERNAL `respond_contacts.id` and a space id the null-workspace
fallback resolves), through the same fixtures (`db`, `client`, superadmin principal, company
scope {Sorento}) and seed helpers, imported rather than copied so the two files cannot drift.

A scoped contact is one with at least one `respond_contact_customers` row and no ACTIVE
office access type. Postgres only, every row seeded here.

Tester's choices: the outstanding report needs a subject (`subject_required`), so every call
below carries a real product code or a customer argument; otherwise a 422 the route already
gives would pass the identity test for the wrong reason.
"""
from __future__ import annotations

import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: F401,E402

from app.models.access import RespondContactCustomer
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import customer, order, order_line, seed_mocha, warehouse
from tests._pg_fixture import unique_code
from tests.test_top_selling_report import (  # noqa: F401  (fixtures are used by name)
    _access,
    _as_contact,
    _contact,
    _link,
    _product,
    client,
    db,
)

BASE = "/api/v1/order-management"
ORDERS = f"{BASE}/orders/"
DEBTORS = f"{BASE}/orders/debtors"
BY_PRODUCT = f"{BASE}/orders/by-product"
ANALYTICS = f"{BASE}/orders/analytics"
OUTSTANDING = f"{BASE}/outstanding-report"
SALES = f"{BASE}/sales-report"

OWN_NAME = "ZZT OWN LEDGER"
RIVAL_NAME = "ZZT RIVAL LEDGER"


class World:
    """Two customers with one DO each, a product on both, and a contact linked to `own`."""

    def __init__(self, db, *, link: bool = True, office: bool = False) -> None:
        self.own = customer(db, company_id=DEFAULT_COMPANY_ID, name=OWN_NAME)
        self.rival = customer(db, company_id=DEFAULT_COMPANY_ID, name=RIVAL_NAME)
        self.product = _product(db, unique_code("ZZTSKU"))
        wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
        self.own_order = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=self.own.id, number=unique_code("DO-OWN"))
        self.rival_order = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=self.rival.id, number=unique_code("DO-RIV"))
        self.own_order.debtor_name = OWN_NAME
        self.rival_order.debtor_name = RIVAL_NAME
        for row in (self.own_order, self.rival_order):
            order_line(
                db, company_id=DEFAULT_COMPANY_ID, order_id=row.id, product_id=self.product.id,
                warehouse_id=wh.id, quantity=3,
            )
        self.contact = _contact(db)
        if link:
            _link(db, self.contact, self.own)
        if office:
            _access(db, self.contact, "Sorento Office")
        db.commit()

    @property
    def me(self) -> dict:
        return _as_contact(self.contact)


def _numbers(resp) -> set[str]:
    return {row["order_number"] for row in resp.json()["data"]}


def _assert_refused(resp) -> None:
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "customer_not_permitted", resp.text
    assert "RIVAL" not in resp.text


# --------------------------------------------------------------------------- #
# AC-CS-40 - the orders list
# --------------------------------------------------------------------------- #


def test_orders_other_customer_ids_are_refused(client, db) -> None:
    """AC-CS-40: a scoped contact naming a customer outside its links is 403
    `customer_not_permitted`, and so is a mix of own and other."""
    w = World(db)
    _assert_refused(client.get(ORDERS, params={"customer_ids": w.rival.id, **w.me}))
    _assert_refused(client.get(ORDERS, params={"customer_ids": f"{w.own.id},{w.rival.id}", **w.me}))


def test_orders_no_customer_arg_is_forced_to_the_links(client, db) -> None:
    """AC-CS-40: no customer argument -> only the linked customer's rows; the other
    customer's DO is absent. Naming its own customer works."""
    w = World(db)
    resp = client.get(ORDERS, params=w.me)
    assert resp.status_code == 200, resp.text
    assert _numbers(resp) == {w.own_order.order_number}, resp.text
    named = client.get(ORDERS, params={"customer_ids": w.own.id, **w.me})
    assert named.status_code == 200, named.text
    assert _numbers(named) == {w.own_order.order_number}


def test_orders_foreign_order_ids_is_a_miss_not_an_error(client, db) -> None:
    """AC-CS-40 (Q4a): `order_ids` of another customer's order -> 200 and an empty `data`:
    the customer scope ANDs onto the ids, so a foreign DO number is a plain miss."""
    w = World(db)
    resp = client.get(ORDERS, params={"order_ids": w.rival_order.id, **w.me})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == [], resp.text
    own = client.get(ORDERS, params={"order_ids": w.own_order.id, **w.me})
    assert _numbers(own) == {w.own_order.order_number}


# --------------------------------------------------------------------------- #
# AC-CS-41 - the outstanding report
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("half", ["contact_id", "space_id"])
def test_outstanding_contact_identity_is_both_or_neither(client, db, half) -> None:
    """AC-CS-41: the report gains `contact_id` / `space_id`, both-or-neither: one alone is
    422 `contact_identity_required` (with a real subject, so `subject_required` cannot be
    the reason)."""
    w = World(db)
    resp = client.get(OUTSTANDING, params={"product_code": w.product.product_code, half: w.me[half]})
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "contact_identity_required", resp.text


def test_outstanding_other_customer_ids_are_refused(client, db) -> None:
    """AC-CS-41: the same three rules as AC-CS-40; other ids -> 403."""
    w = World(db)
    _assert_refused(client.get(OUTSTANDING, params={"customer_ids": w.rival.id, **w.me}))
    _assert_refused(
        client.get(OUTSTANDING, params={"product_code": w.product.product_code, "customer_ids": w.rival.id, **w.me})
    )


def test_outstanding_customer_query_matches_inside_the_links_only(client, db) -> None:
    """AC-CS-41: a `customer_query` naming only another customer is 403, and it is the SAME
    answer as a name that matches nobody (no name oracle); one matching its own ledger runs."""
    w = World(db)
    other = client.get(OUTSTANDING, params={"customer_query": "rival ledger", **w.me})
    nobody = client.get(OUTSTANDING, params={"customer_query": "zzt no such name", **w.me})
    _assert_refused(other)
    _assert_refused(nobody)
    assert other.json() == nobody.json()
    mine = client.get(OUTSTANDING, params={"customer_query": "own ledger", **w.me})
    assert mine.status_code == 200, mine.text


def test_outstanding_no_customer_arg_echoes_the_linked_customer(client, db) -> None:
    """AC-CS-22 (route half): a scoped contact sending no customer argument gets the report
    forced to its link, and the body's `customer_name` echo names it (the presenter prints
    the `Customer:` header from this field)."""
    w = World(db)
    resp = client.get(OUTSTANDING, params={"product_code": w.product.product_code, **w.me})
    assert resp.status_code == 200, resp.text
    assert resp.json()["customer_name"] == OWN_NAME, resp.text


def test_outstanding_own_customer_runs(client, db) -> None:
    """AC-CS-41: the contact's own customer is answered."""
    w = World(db)
    resp = client.get(OUTSTANDING, params={"customer_ids": w.own.id, "scope": "do", **w.me})
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# AC-CS-42 - the sales report
# --------------------------------------------------------------------------- #


def test_sales_report_other_customer_ids_are_refused(client, db) -> None:
    """AC-CS-42: same rules as AC-CS-41 (the contact holds `sales_orders.sales_report`, so
    the reveal gate is passed and the customer scope is the only thing refusing)."""
    w = World(db)
    _assert_refused(client.get(SALES, params={"customer_ids": w.rival.id, **w.me}))
    _assert_refused(client.get(SALES, params={"customer_query": "rival ledger", **w.me}))
    own = client.get(SALES, params={"customer_ids": w.own.id, **w.me})
    assert own.status_code == 200, own.text


# --------------------------------------------------------------------------- #
# AC-CS-43 - the debtors list
# --------------------------------------------------------------------------- #


def test_debtors_list_returns_only_the_linked_customer(client, db) -> None:
    """AC-CS-43: a scoped contact's "who are your customers" lists its own account only."""
    w = World(db)
    resp = client.get(DEBTORS, params=w.me)
    assert resp.status_code == 200, resp.text
    names = {row["debtor_name"] for row in resp.json()["data"]}
    assert names == {OWN_NAME}, names


# --------------------------------------------------------------------------- #
# AC-CS-44 - analytics and by-product
# --------------------------------------------------------------------------- #


def test_analytics_other_customer_ids_are_refused(client, db) -> None:
    """AC-CS-44: analytics with another customer's id -> 403."""
    w = World(db)
    _assert_refused(client.get(ANALYTICS, params={"metric": "count", "customer_ids": w.rival.id, **w.me}))


def test_analytics_none_is_forced_to_the_links(client, db) -> None:
    """AC-CS-44: with no customer argument the figures are the linked customer's only."""
    w = World(db)
    resp = client.get(ANALYTICS, params={"metric": "count", "group_by": "customer", **w.me})
    assert resp.status_code == 200, resp.text
    assert "RIVAL" not in resp.text, resp.text
    assert OWN_NAME in resp.text, resp.text


def test_by_product_other_customer_ids_are_refused(client, db) -> None:
    """AC-CS-44: by-product with another customer's id -> 403."""
    w = World(db)
    _assert_refused(
        client.get(BY_PRODUCT, params={"product_ids": w.product.id, "customer_ids": w.rival.id, **w.me})
    )


def test_by_product_none_is_forced_to_the_links(client, db) -> None:
    """AC-CS-44: with no customer argument only the linked customer's DOs come back."""
    w = World(db)
    resp = client.get(BY_PRODUCT, params={"product_ids": w.product.id, **w.me})
    assert resp.status_code == 200, resp.text
    assert w.rival_order.order_number not in resp.text, resp.text
    assert w.own_order.order_number in resp.text, resp.text


# --------------------------------------------------------------------------- #
# AC-CS-45 - staff and no identity are unchanged
# --------------------------------------------------------------------------- #


def _every_route(w: World) -> list[tuple[str, dict]]:
    return [
        (ORDERS, {}),
        (BY_PRODUCT, {"product_ids": w.product.id}),
        (OUTSTANDING, {"product_code": w.product.product_code}),
        (SALES, {}),
        (ANALYTICS, {"metric": "count"}),
        (DEBTORS, {}),
    ]


def test_staff_and_no_identity_unchanged(client, db) -> None:
    """AC-CS-45: an active office type (linked or not) naming another customer is 200 on
    every route, and so is a request with no contact identity at all."""
    w = World(db, office=True)
    for path, base in _every_route(w):
        staff = client.get(path, params={**base, "customer_ids": w.rival.id, **w.me})
        assert staff.status_code == 200, (path, staff.text)
        anonymous = client.get(path, params={**base, "customer_ids": w.rival.id})
        assert anonymous.status_code == 200, (path, anonymous.text)
    # A staff contact with no customer argument is not forced to its link either.
    both = client.get(ORDERS, params=w.me)
    assert _numbers(both) == {w.own_order.order_number, w.rival_order.order_number}, both.text


def test_unlinked_contact_is_unchanged_on_the_routes(client, db) -> None:
    """AC-CS-03 / AC-CS-45: a contact with no link is not scoped: no 403, no forcing."""
    w = World(db, link=False)
    resp = client.get(ORDERS, params={"customer_ids": w.rival.id, **w.me})
    assert resp.status_code == 200, resp.text
    assert _numbers(resp) == {w.rival_order.order_number}


# --------------------------------------------------------------------------- #
# AC-CS-46 - the link is read with company scope off
# --------------------------------------------------------------------------- #


def test_link_hidden_by_company_scope_still_scopes(client, db) -> None:
    """AC-CS-46: the request's company scope is {Sorento}; the contact's only link belongs
    to Mocha, so a scoped read would not see it and would treat the contact as unlinked
    (unscoped, everything allowed). The lookup reads with scope OFF, so the contact is still
    scoped and another customer is refused, on every customer-scoped route."""
    mocha = seed_mocha(db)
    hidden_own = customer(db, company_id=mocha.id, name="ZZT MOCHA OWN")
    rival = customer(db, company_id=DEFAULT_COMPANY_ID, name=RIVAL_NAME)
    rival_order = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=rival.id, number=unique_code("DO-RIV"))
    contact = _contact(db)
    db.add(
        RespondContactCustomer(
            id=str(uuid.uuid4()), contact_id=contact.id, customer_id=hidden_own.id, company_id=mocha.id,
        )
    )
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    me = _as_contact(contact)
    for path, base in ((ORDERS, {}), (OUTSTANDING, {}), (SALES, {})):
        _assert_refused(client.get(path, params={**base, "customer_ids": rival.id, **me}))
    assert rival_order.order_number  # seeded: the refusal above is the scope, not an empty book


# --------------------------------------------------------------------------- #
# AC-CS-05 - the top selling route reads the shared function
# --------------------------------------------------------------------------- #


def test_top_selling_dealer_scope_reads_the_shared_function(db, monkeypatch) -> None:
    """AC-CS-05: `orders._top_selling_dealer_scope` decides through
    `app.services.contact_customer_scope.contact_customer_scope` (patched through its module,
    so the caller must reference it as a module attribute). Red today as an ImportError."""
    import app.services.contact_customer_scope as scope_mod
    from app.api.v1.order_management.orders import _top_selling_dealer_scope

    own = customer(db, company_id=DEFAULT_COMPANY_ID, name=OWN_NAME)
    contact = _contact(db)
    _link(db, contact, own)
    db.commit()
    real = scope_mod.contact_customer_scope
    seen: list = []

    def _spy(*args, **kwargs):
        seen.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(scope_mod, "contact_customer_scope", _spy)
    assert _top_selling_dealer_scope(db, contact.id) == [str(own.id)]
    assert seen, "_top_selling_dealer_scope never asked the shared scope function"


# --------------------------------------------------------------------------- #
# AC-CS-47 - the complaints list
# --------------------------------------------------------------------------- #

COMPLAINTS = "/api/v1/complaints-management/complaints/"


class TestComplaintsListScope:
    """AC-CS-47: `GET /complaints-management/complaints/` gains `contact_id` / `space_id`
    (both-or-neither). A scoped contact sees only complaints whose `customer_name` equals a
    linked customer's name, trimmed and case-insensitive (complaints carry a name, no id).
    Staff and a request with no contact params see every row. The complaints carry no
    `contact_id` of their own here, so the filter is the customer name, nothing else."""

    def _seed(self, db, *, office: bool = False):
        from app.models.complaints import Complaint

        own = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT OWN A")
        contact = _contact(db)
        _link(db, contact, own)
        if office:
            _access(db, contact, "Sorento Office")
        mine = Complaint(
            id=str(uuid.uuid4()), complaint_number=unique_code("CMP-OWN"), customer_name=" zzt own a ",
            status="new",
        )
        other = Complaint(
            id=str(uuid.uuid4()), complaint_number=unique_code("CMP-OTH"), customer_name="ZZT OTHER B",
            status="new",
        )
        db.add_all([mine, other])
        db.commit()
        return contact, mine, other

    @staticmethod
    def _numbers(resp) -> set[str]:
        return {row["complaint_number"] for row in resp.json()["data"]}

    @pytest.mark.parametrize("half", ["contact_id", "space_id"])
    def test_contact_identity_is_both_or_neither(self, client, db, half) -> None:
        """AC-CS-47: one of the pair alone is 422 `contact_identity_required`."""
        contact, _mine, _other = self._seed(db)
        resp = client.get(COMPLAINTS, params={half: _as_contact(contact)[half]})
        assert resp.status_code == 422, resp.text
        assert resp.json().get("code") == "contact_identity_required", resp.text

    def test_scoped_contact_sees_only_its_own_customers_complaints(self, client, db) -> None:
        """AC-CS-47: name match is trimmed and case-insensitive; the other row is absent."""
        contact, mine, other = self._seed(db)
        resp = client.get(COMPLAINTS, params=_as_contact(contact))
        assert resp.status_code == 200, resp.text
        assert self._numbers(resp) == {mine.complaint_number}, resp.text
        assert "OTHER B" not in resp.text

    def test_staff_and_no_identity_get_both_rows(self, client, db) -> None:
        """AC-CS-47: an active office type, and a request with no contact params, are unchanged."""
        contact, mine, other = self._seed(db, office=True)
        both = {mine.complaint_number, other.complaint_number}
        staff = client.get(COMPLAINTS, params=_as_contact(contact))
        assert staff.status_code == 200, staff.text
        assert both <= self._numbers(staff)
        anonymous = client.get(COMPLAINTS)
        assert anonymous.status_code == 200, anonymous.text
        assert both <= self._numbers(anonymous)
