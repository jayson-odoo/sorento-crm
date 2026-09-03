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

from app.models.procurement import ProductSupplier, Supplier
from app.models.scm import SupplierProductCodeAlias
from app.models.user import SystemSetting
from app.services.procurement_service import ProductSupplierService
from app.services.scm import supplier_code_alias_service as alias_svc
from app.services.scm import supplier_code_matcher
from tests._pg_fixture import pg_session
from tests.scm.test_supplier_code_matcher import World, _u

import scripts.backfill_manual_alias_links as backfill


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


def test_a_supplier_with_no_existing_link_falls_back_to_the_products_own_link():
    """AC-G1 (S8, issue #605): a supplier whose whole universe came from the stock list has
    ZERO `product_suppliers` rows of its own, so the ladder falls to what the PRODUCT already
    waits on across its other suppliers - here DEFAULT at 90 - rather than leaving the row
    unwritten. The alias alone (AC-D3) already carried the product into the universe; this
    link is the sourcing fact the manual match is supposed to state."""
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        other_supplier = Supplier(
            id=_u(), supplier_code=f"{w.tag}-OTHER", supplier_name="DEFAULT", is_active=True
        )
        db.add(other_supplier)
        db.flush()
        db.add(
            ProductSupplier(
                id=_u(), product_id=target.id, supplier_id=other_supplier.id,
                standard_lead_time_days=90,
            )
        )
        db.flush()

        out = alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        assert out["product_id"] == str(target.id)
        link = _link_for(db, w, target)
        assert link is not None
        assert link.standard_lead_time_days == 90
        assert link.is_primary_supplier is False


def test_a_supplier_and_product_with_no_links_falls_back_to_the_system_default():
    """AC-G2: neither the supplier nor the product has a book to read a lead time off, so the
    last rung is the system default (`system_settings.default_product_standard_lead_time_days`,
    90 when unset). Set explicitly here so the assertion does not depend on whatever this
    shared database happens to hold."""
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        row = db.query(SystemSetting).first()
        if row is not None:
            row.default_product_standard_lead_time_days = 21
        else:
            db.add(SystemSetting(id=_u(), name="ZZT test", default_product_standard_lead_time_days=21))
        db.flush()

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=w.supplier_code("NEW-CODE"),
            product_id=str(target.id),
            actor="Ms Tee",
        )

        link = _link_for(db, w, target)
        assert link is not None
        assert link.standard_lead_time_days == 21
        assert link.is_primary_supplier is False


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


def test_the_write_schemas_do_not_offer_a_field_they_would_drop():
    """S4 review: `ProductSupplierCreate` / `Update` inherited `supplier_item_code` from the
    shared sourcing terms and dropped it silently.

    `product_suppliers` has no such column - the alias table is the single writer (AC-D2) -
    so a payload field nothing reads back is a promise the API cannot keep. The declaration
    belongs on the RESPONSE, which is the only side that answers it.
    """
    from app.schemas.procurement import (
        ProductSupplierCreate,
        ProductSupplierResponse,
        ProductSupplierUpdate,
    )

    assert "supplier_item_code" not in ProductSupplierCreate.model_fields
    assert "supplier_item_code" not in ProductSupplierUpdate.model_fields
    assert "supplier_item_code" in ProductSupplierResponse.model_fields


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


# --------------------------------------------------------------------------------- #
# AC-G5 - the repair script for rows written before the ladder had this fallback
# --------------------------------------------------------------------------------- #


def _simulate_pre_fix_orphan(db, w: World, target) -> None:
    """The state the old code left on disk: a manual alias whose link was never written
    because the supplier had no book of its own. Built by calling the real match path and
    then deleting the link it wrote, rather than constructing the alias row by hand, so the
    fixture stays honest about what a real orphan looks like."""
    alias_svc.create(
        db,
        supplier_id=str(w.supplier.id),
        supplier_code=w.supplier_code("NEW-CODE"),
        product_id=str(target.id),
        actor="Ms Tee",
    )
    db.query(ProductSupplier).filter(
        ProductSupplier.product_id == target.id,
        ProductSupplier.supplier_id == w.supplier.id,
    ).delete()
    db.flush()


def test_a_dry_run_reports_the_orphan_and_writes_nothing():
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        _simulate_pre_fix_orphan(db, w, target)
        assert _link_for(db, w, target) is None

        candidates = backfill.find_candidates(db)
        pairs = {(str(c.product_id), str(c.supplier_id)) for c in candidates}
        assert (str(target.id), str(w.supplier.id)) in pairs

        summary = backfill.run(db, apply=False)

        assert _link_for(db, w, target) is None
        # Fix round (Opus review): a dry-run has no link row to read the lead time back off,
        # so it must be COMPUTED, not `None` - the same ladder `--apply` would write.
        reported = {
            (row["product_id"], row["supplier_id"]): row["lead_time"] for row in summary["rows"]
        }
        lead_time = reported[(str(target.id), str(w.supplier.id))]
        assert isinstance(lead_time, int)
        assert lead_time == alias_svc.lead_time_for_link(db, str(w.supplier.id), str(target.id))


def test_apply_writes_the_link_and_a_second_apply_is_a_noop():
    with pg_session() as db:
        w = World(db)
        target = w.product("NEW")
        _simulate_pre_fix_orphan(db, w, target)

        backfill.run(db, apply=True)

        link = _link_for(db, w, target)
        assert link is not None
        assert link.is_primary_supplier is False
        first_link_id = str(link.id)

        # No more an orphan, so a second pass does not touch it.
        candidates = backfill.find_candidates(db)
        pairs = {(str(c.product_id), str(c.supplier_id)) for c in candidates}
        assert (str(target.id), str(w.supplier.id)) not in pairs

        backfill.run(db, apply=True)

        link_again = _link_for(db, w, target)
        assert str(link_again.id) == first_link_id
        assert link_again.standard_lead_time_days == link.standard_lead_time_days
