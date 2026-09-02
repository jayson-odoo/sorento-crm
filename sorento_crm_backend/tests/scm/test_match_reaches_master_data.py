"""S4 - a manual match reaches master data.

`PLAN-scm-loading-plan-feedback-2sep.md` section 3.4, AC-D1 to AC-D4.

TEST-FIRST: `_ensure_product_supplier_link` does not exist in
`app/services/scm/supplier_code_alias_service.py`, `container_request_service._linked_products`
does not yet union the SET half of an alias into the driver leg, and
`ProductSupplierSourcingTerms` / the by-product route do not carry `supplier_item_code`, so
every test here is expected to be red until Phase 2 lands.

The captain's ruling (section 2): "Does a manual match reach master data - Yes: link + show
code." A person who picks a product for a supplier's code is stating a sourcing fact, not just
labelling a code, and that fact has to reach the one table the reorder engine and the product's
own Suppliers tab both read - `product_suppliers` - without anybody re-typing it there by hand.
An AUTOMATIC (ladder) guess is not a person's statement and must never write it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.procurement import ProductSupplier
from app.models.scm import SupplierProductCodeAlias
from app.services.procurement_service import ProductSupplierService
from app.services.scm import supplier_code_alias_service as alias_svc
from app.services.scm import supplier_code_matcher
from tests._pg_fixture import pg_session
from tests.scm.test_supplier_code_matcher import World, _u


def _link(db, w: World, product, lead_time: int) -> ProductSupplier:
    row = ProductSupplier(
        id=_u(),
        product_id=product.id,
        supplier_id=w.supplier.id,
        standard_lead_time_days=lead_time,
    )
    db.add(row)
    db.flush()
    return row


def _link_for(db, w: World, product) -> ProductSupplier | None:
    return (
        db.query(ProductSupplier)
        .filter(
            ProductSupplier.product_id == product.id,
            ProductSupplier.supplier_id == w.supplier.id,
        )
        .first()
    )


# --------------------------------------------------------------------------------- #
# AC-D1 - the link, its lead time, and when none is written
# --------------------------------------------------------------------------------- #


def test_a_manual_match_upserts_the_link_at_the_mode_lead_time():
    with pg_session() as db:
        w = World(db)
        # Three existing links for this supplier: 30 appears twice, 45 once - the mode is 30.
        _link(db, w, w.product("A"), 30)
        _link(db, w, w.product("B"), 30)
        _link(db, w, w.product("C"), 45)
        target = w.product("NEW")

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        link = _link_for(db, w, target)
        assert link is not None
        assert link.standard_lead_time_days == 30
        assert link.is_primary_supplier is False


def test_a_tie_in_lead_times_picks_the_larger():
    with pg_session() as db:
        w = World(db)
        # 30 and 45 each appear once - a tie, broken toward the larger figure.
        _link(db, w, w.product("A"), 30)
        _link(db, w, w.product("B"), 45)
        target = w.product("NEW")

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        link = _link_for(db, w, target)
        assert link is not None
        assert link.standard_lead_time_days == 45


def test_a_supplier_with_no_existing_link_gets_no_row():
    """There is no honest lead time to invent - the alias alone (AC-D3) already carries the
    product into the universe, so a link is sourcing data on top of it, not a prerequisite."""
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")

        out = alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        assert out["product_id"] == str(target.id)
        assert _link_for(db, w, target) is None


def test_matching_a_code_to_a_product_already_linked_is_a_noop():
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        original = _link(db, w, target, 60)

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        link = _link_for(db, w, target)
        assert link is not None
        assert str(link.id) == str(original.id)
        assert link.standard_lead_time_days == 60


def test_a_set_match_writes_no_product_suppliers_row():
    """A set is not a row `product_suppliers` can hold - only the alias records it (S4 3.4)."""
    with pg_session() as db:
        w = World(db)
        driver = w.product("DRIVER")
        _link(db, w, w.product("A"), 30)
        product_set = w.product_set("WC", [(driver, 1, 0)])

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("SET-CODE"),
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )

        assert _link_for(db, w, driver) is None
        total_links = (
            db.query(ProductSupplier)
            .filter(ProductSupplier.supplier_id == w.supplier.id)
            .count()
        )
        assert total_links == 1  # only the seeded "A" link, nothing for the set/driver


def test_an_automatic_ladder_match_never_creates_a_link():
    """A guess is not a person's statement about what the supplier makes for us."""
    with pg_session() as db:
        w = World(db)
        _link(db, w, w.product("A"), 30)
        # An exact-code match resolves and remembers automatically, with no person deciding.
        product = w.product("SRTWC8357-RL")

        out = supplier_code_matcher.resolve(
            db, str(w.supplier.id), [w.supplier_code("SRTWC8357-RL")]
        )
        assert out[w.supplier_code("SRTWC8357-RL")].product_id == str(product.id)

        assert _link_for(db, w, product) is None


# --------------------------------------------------------------------------------- #
# AC-D4 - undo keeps the link
# --------------------------------------------------------------------------------- #


def test_undoing_a_manual_match_does_not_delete_the_link_it_created():
    with pg_session() as db:
        w = World(db)
        _link(db, w, w.product("A"), 30)
        target = w.product("NEW")

        written = alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )
        assert _link_for(db, w, target) is not None

        alias_svc.delete(db, written["id"], actor="Ms Tee")

        link = _link_for(db, w, target)
        assert link is not None, "Undo must not touch sourcing data it merely triggered"


# --------------------------------------------------------------------------------- #
# AC-D2 - the field on the route and on the response schema
# --------------------------------------------------------------------------------- #


def test_the_by_product_route_carries_their_code():
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        _link(db, w, target, 30)

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("THEIR-SPELLING"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        rows = ProductSupplierService(db).list_suppliers_for_product(str(target.id))
        assert len(rows) == 1
        assert rows[0].supplier_item_code == w.supplier_code("THEIR-SPELLING")


def test_a_link_with_no_alias_reports_no_code():
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        _link(db, w, target, 30)

        rows = ProductSupplierService(db).list_suppliers_for_product(str(target.id))
        assert len(rows) == 1
        assert rows[0].supplier_item_code is None


def test_the_newest_alias_wins_when_a_product_has_been_matched_on_two_codes():
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        _link(db, w, target, 30)

        old = alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("OLD-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )
        # Postgres `now()` does not advance within one transaction (`pg_session` runs the
        # whole test in one), so two rows written back to back here would tie on
        # `created_at` - backdate the older one explicitly rather than assert on a race
        # that only exists in production.
        db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.id == old["id"]
        ).update({"created_at": datetime.utcnow() - timedelta(minutes=5)})
        db.flush()
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        rows = ProductSupplierService(db).list_suppliers_for_product(str(target.id))
        assert rows[0].supplier_item_code == w.supplier_code("NEW-CODE")


def test_ac_d2_the_field_survives_the_response_model():
    """`response_model` silently drops undeclared fields - asserted explicitly, since a field
    that reaches the ORM row perfectly can still never reach the frontend."""
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        link = _link(db, w, target, 30)
        # The response model reads off an attribute, not a column - set exactly as the
        # by-product route's service method does before returning the row.
        link.supplier_item_code = w.supplier_code("THEIR-SPELLING")

        from app.schemas.procurement import ProductSupplierResponse

        serialized = ProductSupplierResponse.model_validate(link, from_attributes=True)

        dumped = serialized.model_dump()
        assert "supplier_item_code" in dumped
        assert dumped["supplier_item_code"] == w.supplier_code("THEIR-SPELLING")
