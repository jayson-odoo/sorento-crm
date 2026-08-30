"""`/customers/select` must not be eaten by `/customers/{customer_id}`.

Both routers mount at `/customers`, and `customers.router` carries `GET /{customer_id}`.
Registered first, it matched `/customers/select`, tried to read "select" as a customer id,
and answered `404 Customer not found. Someone might have deleted it already.` Every screen
carrying a customer dropdown then showed that toast on load - it reads as a data problem
("did somebody delete a customer?") when it is a routing one, so nobody goes looking in the
router.

FastAPI matches in registration order, so the literal path has to be registered before the
parameterised one. Asserted on the ROUTE TABLE rather than over HTTP, because the order is
the defect: a live request only proves today's data, while the order proves the rule, and it
needs no principal, no database and no seeded customer.

Same defect family as the SLA `/integration/escalate` shadowing.
"""
from __future__ import annotations

from app.main import app


def _paths_in_order() -> list[str]:
    return [getattr(r, "path", "") for r in app.routes]


def test_the_literal_select_path_is_registered_before_the_parameterised_one():
    paths = _paths_in_order()
    select = "/api/v1/order-management/customers/select"
    param = "/api/v1/order-management/customers/{customer_id}"

    assert select in paths, "the select endpoint is not mounted at all"
    assert param in paths, "the parameterised customer route moved; update this test"
    assert paths.index(select) < paths.index(param), (
        "/customers/{customer_id} is registered first, so it will match /customers/select "
        "and answer 404 'Customer not found' on every screen with a customer dropdown"
    )


def test_every_literal_customer_subpath_is_registered_before_the_id_route():
    """The rule, not just the one case that broke.

    Any other literal subpath under the same prefix would fail the same way. Asserting the
    rule means the next one somebody adds is covered without remembering to add a test for
    it.
    """
    paths = _paths_in_order()
    prefix = "/api/v1/order-management/customers/"
    param = f"{prefix}{{customer_id}}"
    param_at = paths.index(param)

    # The collection root (`/customers/`) has an EMPTY subpath and is not shadowed by
    # `/{customer_id}` - a path parameter never matches nothing - so it is excluded rather
    # than being a permanent false positive that trains people to ignore this test.
    shadowed = [
        p for i, p in enumerate(paths)
        if p.startswith(prefix) and p[len(prefix):] and "{" not in p[len(prefix):]
        and i > param_at
    ]
    assert not shadowed, (
        f"these literal paths are registered after {param} and will 404: {shadowed}"
    )
