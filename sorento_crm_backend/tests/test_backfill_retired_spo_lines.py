"""RED tests for AC-H9: `scripts/backfill_retired_spo_lines.py`.

UAC: documentation/plans/autocount/hide-retired-spo-lines-acceptance-criteria.md
     AC-H9 ("Round 2", security review 2026-09-08).
PLAN: documentation/plans/autocount/PLAN-hide-retired-spo-lines.md, section 8
      ("Round 2 rulings"), ruling B1.

Round 2 REPLACES the round-1 evidence rule ("closed and never received").
Security review found four writers that close an `autocount` line without
retiring it - the outstanding book's absence sweep (goods ARRIVED, no receipt
written), a cancelled document (`force_closed`), the deletion service keeping
a referenced row, and a receipt - so "closed, never received" alone is not
evidence of retirement.

The new rule (B1): the backfill stamps a row only when it ALSO carries a
`source_ref` AND its `(company_id, spo_number, product_id,
upper(location_code))` group holds an OPEN row created STRICTLY LATER. That
later, open, same-group row is the replacement line AutoCount actually wrote
when it edited the original - the one piece of positive evidence "AutoCount
stopped naming this line" rather than "this line closed some other way".

Contract unchanged from round 1: `run(db, company_id, dry_run=True) -> dict`
(`documents` key at minimum), CLI `--company <code> [--dry-run|--apply]`,
`retired_at = coalesce(updated_at, now())`, one commit per document, a dry
run writes nothing.

The module does not exist yet (round 2 not landed), so the import happens
INSIDE each test body - collection of the rest of the suite must not fail
just because this script is still unbuilt / mid-rewrite.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.procurement import SPOAllocation
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.procurement_service import PickingHeaderService

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTBACKFILLRETIRE"

T0 = datetime(2026, 1, 1, 0, 0, 0)
T1 = datetime(2026, 2, 1, 0, 0, 0)  # strictly later than T0


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _seed_product(db) -> Product:
    category = ProductCategory(category_code=unique_code(MARKER), category_name="Cat")
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=unique_code(MARKER),
        product_name="Item",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("0"),
    )
    db.add(product)
    db.flush()
    return product


def _row(
    *,
    spo_number: str,
    line_no: int,
    product_id: str,
    location_code: str,
    line_status: str,
    created_at: datetime,
    source_ref: str | None,
    allocated: int = 10,
    updated_at: datetime | None = None,
    quantity_received: int = 0,
    receipt_status: str = "pending",
    stated_received: int | None = None,
) -> SPOAllocation:
    """One `autocount` row, closed-with-no-receipt (round 2/3's own shape,
    the defaults) or open, at a given `created_at` - the two things the
    group-membership evidence (B1) turns on. `quantity_received`/
    `receipt_status`/`stated_received` default to the round 1/2 "never
    received" shape but round 4's AC-H15/AC-H16 override them to prove the
    freeze and the fully-received exclusion.
    """
    return SPOAllocation(
        id=str(uuid.uuid4()),
        company_id=DEFAULT_COMPANY_ID,
        spo_number=spo_number,
        spo_line_number=line_no,
        product_id=product_id,
        location_code=location_code,
        allocated_quantity=allocated,
        quantity_received=quantity_received,
        receipt_status=receipt_status,
        line_status=line_status,
        source_system="autocount",
        source_ref=source_ref,
        created_at=created_at,
        retired_at=None,
        updated_at=updated_at,
        stated_received=stated_received,
    )


def _retired_at_by_id(db, row_ids: list[str]) -> dict[str, object]:
    db.expire_all()
    return {
        str(r["id"]): r["retired_at"]
        for r in db.execute(
            text("SELECT id, retired_at FROM spo_allocations WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": row_ids},
        )
        .mappings()
        .all()
    }


class TestAcH9BackfillEvidenceIsAReplacementSibling:
    # ------------------------------------------------------------------ #
    # (a) the motivating shape: closed + source_ref + a later OPEN sibling
    #     in the SAME (product, location) group -> STAMPED.
    # ------------------------------------------------------------------ #
    def test_a_closed_row_with_source_ref_and_a_later_open_sibling_is_stamped(self, db):
        """AC-H9(a). A closed autocount row carrying `source_ref`, with a
        later-created OPEN row for the same product and location under the
        same `spo_number`, is the replacement-line shape the backfill exists
        for: `--dry-run` writes nothing and names one document; `--apply`
        stamps only the closed row (never the open sibling itself); a second
        `--apply` reports zero.

        This is the positive shape round 1 already got right by accident
        (closed + receipt 0 alone was enough there); its role here is
        confirming the process (dry-run/apply/idempotent) still holds once
        B1's stricter evidence gate (`source_ref` + later OPEN sibling)
        replaces the old predicate. `test_b`..`test_e` below are the ones
        that pin B1 itself: rows round 1's own predicate would have WRONGLY
        stamped (closed + receipt 0, no sibling evidence at all) and that a
        correct implementation must leave alone.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"
        stamped_updated_at = datetime(2026, 8, 1, 3, 30, 0)

        closed_row = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=f"{MARKER}:REF1:{uuid.uuid4().hex[:8]}",
            updated_at=stamped_updated_at,
        )
        later_open_sibling = _row(
            spo_number=spo_number, line_no=2, product_id=product.id, location_code=location,
            line_status="open", created_at=T1, source_ref=f"{MARKER}:REF2:{uuid.uuid4().hex[:8]}",
        )
        db.add_all([closed_row, later_open_sibling])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 2 not landed

        summary1 = run(db, DEFAULT_COMPANY_ID, dry_run=True)
        by_id = _retired_at_by_id(db, [closed_row.id, later_open_sibling.id])
        assert by_id[closed_row.id] is None, "a dry run must write nothing"
        assert by_id[later_open_sibling.id] is None
        assert summary1.get("documents", 0) == 1, summary1

        summary2 = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary2.get("documents", 0) == 1, summary2
        by_id = _retired_at_by_id(db, [closed_row.id, later_open_sibling.id])
        assert by_id[closed_row.id] is not None, by_id
        assert by_id[later_open_sibling.id] is None, "the OPEN sibling itself is never stamped"

        stamped = by_id[closed_row.id]
        stamped_naive = stamped.replace(tzinfo=None) if stamped.tzinfo is not None else stamped
        assert abs((stamped_naive - stamped_updated_at).total_seconds()) < 24 * 3600, (
            stamped, stamped_updated_at,
        )

        summary3 = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary3.get("documents", 0) == 0, summary3

    # ------------------------------------------------------------------ #
    # (b) the outstanding book's absence sweep: closed, source_ref set,
    #     but its group has NO later row at all -> not stamped.
    # ------------------------------------------------------------------ #
    def test_b_a_closed_row_whose_group_has_no_later_sibling_is_not_stamped(self, db):
        """AC-H9(b). A closed autocount row with `source_ref`, alone in its
        `(product, location)` group - no sibling row of any kind. This is
        the shape the outstanding book's absence sweep leaves behind: the
        goods arrived, so nothing ever replaced the line. Not stamped.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"

        lone_closed = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=f"{MARKER}:REF:{uuid.uuid4().hex[:8]}",
        )
        db.add(lone_closed)
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 2 not landed

        run(db, DEFAULT_COMPANY_ID, dry_run=False)
        by_id = _retired_at_by_id(db, [lone_closed.id])
        assert by_id[lone_closed.id] is None, by_id

    # ------------------------------------------------------------------ #
    # (c) the cancelled-document shape: every line closed, the "later" one
    #     is closed too (no OPEN sibling anywhere) -> none stamped.
    # ------------------------------------------------------------------ #
    def test_c_a_cancelled_document_with_only_closed_siblings_is_not_stamped(self, db):
        """AC-H9(c). Two closed autocount rows, same product/location/
        `spo_number`, the second created strictly later than the first - the
        cancelled-document shape (`force_closed`): a document with no OPEN
        line anywhere. Neither row is stamped, because neither has an OPEN
        sibling - a later row existing is not enough on its own.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"

        earlier_closed = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=f"{MARKER}:REF1:{uuid.uuid4().hex[:8]}",
        )
        later_closed = _row(
            spo_number=spo_number, line_no=2, product_id=product.id, location_code=location,
            line_status="closed", created_at=T1, source_ref=f"{MARKER}:REF2:{uuid.uuid4().hex[:8]}",
        )
        db.add_all([earlier_closed, later_closed])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 2 not landed

        run(db, DEFAULT_COMPANY_ID, dry_run=False)
        by_id = _retired_at_by_id(db, [earlier_closed.id, later_closed.id])
        assert by_id[earlier_closed.id] is None, by_id
        assert by_id[later_closed.id] is None, by_id

    # ------------------------------------------------------------------ #
    # (d) source_ref NULL, even with a later OPEN sibling -> not stamped.
    # ------------------------------------------------------------------ #
    def test_d_a_closed_row_with_source_ref_null_is_not_stamped(self, db):
        """AC-H9(d). A closed row with NO `source_ref` (a pre-DtlKey, xlsx-
        era row) - even though a later OPEN row exists for the same product
        and location - is not stamped. `source_ref` is AutoCount's own line
        identity; without it there is nothing to say AutoCount ever edited
        THIS line specifically, only that some other line opened later.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"

        closed_no_ref = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=None,
        )
        later_open_sibling = _row(
            spo_number=spo_number, line_no=2, product_id=product.id, location_code=location,
            line_status="open", created_at=T1, source_ref=f"{MARKER}:REF:{uuid.uuid4().hex[:8]}",
        )
        db.add_all([closed_no_ref, later_open_sibling])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 2 not landed

        run(db, DEFAULT_COMPANY_ID, dry_run=False)
        by_id = _retired_at_by_id(db, [closed_no_ref.id])
        assert by_id[closed_no_ref.id] is None, by_id

    # ------------------------------------------------------------------ #
    # (e) the only later sibling is for a DIFFERENT product or location ->
    #     not stamped (the group key must match on both).
    # ------------------------------------------------------------------ #
    def test_e_a_closed_row_whose_later_sibling_is_a_different_product_or_location_is_not_stamped(
        self, db
    ):
        """AC-H9(e). Two independent documents, each with a closed autocount
        row (`source_ref` set) and a later-created OPEN row under the SAME
        `spo_number` - but the open row is for a DIFFERENT product in the
        first document, and a DIFFERENT location (same product) in the
        second. Neither closed row is stamped: the group key is
        `(company_id, spo_number, product_id, upper(location_code))`, and an
        open row outside that exact group is not evidence this particular
        line was replaced.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        location = f"{MARKER}-LOC"

        # -- different product -------------------------------------------------
        product_a = _seed_product(db)
        product_b = _seed_product(db)
        spo_diff_product = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        closed_diff_product = _row(
            spo_number=spo_diff_product, line_no=1, product_id=product_a.id,
            location_code=location, line_status="closed", created_at=T0,
            source_ref=f"{MARKER}:REF1:{uuid.uuid4().hex[:8]}",
        )
        open_other_product = _row(
            spo_number=spo_diff_product, line_no=2, product_id=product_b.id,
            location_code=location, line_status="open", created_at=T1,
            source_ref=f"{MARKER}:REF2:{uuid.uuid4().hex[:8]}",
        )

        # -- different location, same product -----------------------------------
        product_c = _seed_product(db)
        spo_diff_location = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        closed_diff_location = _row(
            spo_number=spo_diff_location, line_no=1, product_id=product_c.id,
            location_code=f"{location}-A", line_status="closed", created_at=T0,
            source_ref=f"{MARKER}:REF3:{uuid.uuid4().hex[:8]}",
        )
        open_other_location = _row(
            spo_number=spo_diff_location, line_no=2, product_id=product_c.id,
            location_code=f"{location}-B", line_status="open", created_at=T1,
            source_ref=f"{MARKER}:REF4:{uuid.uuid4().hex[:8]}",
        )

        db.add_all([
            closed_diff_product, open_other_product,
            closed_diff_location, open_other_location,
        ])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 2 not landed

        run(db, DEFAULT_COMPANY_ID, dry_run=False)
        by_id = _retired_at_by_id(db, [closed_diff_product.id, closed_diff_location.id])
        assert by_id[closed_diff_product.id] is None, by_id
        assert by_id[closed_diff_location.id] is None, by_id


# =================================================================================== #
# AC-H15 (round 4): the backfill freezes stated_received before stamping retired_at
# =================================================================================== #


class TestAcH15BackfillFreezesStatedReceivedBeforeStamping:
    def test_apply_freezes_stated_received_to_the_quantity_received_floor(self, db):
        """AC-H15. A candidate row (closed, `source_ref`, later OPEN
        sibling) carrying `quantity_received 25` and `stated_received` NULL:
        after `--apply` it reads `stated_received 25` (not NULL) AND
        `retired_at` set - the freeze happens BEFORE the stamp, the same
        order the ingest's leftover sweep and the dedupe use. A following
        `sync_received_for_spo_number` (no picking line anywhere, nothing
        released - AC-H14's own ownership gate skips it either way) leaves
        `quantity_received` at 25.

        RED today at the `stated_received` assertion: the backfill stamps
        `retired_at` and touches nothing else, so `stated_received` stays
        NULL - a later recompute that DOES reach this row (picked against or
        released) would then float on `compute_received_for_allocation`
        alone with no floor under it, exactly the D28 defect class round 4
        exists to close.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"

        closed_row = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=f"{MARKER}:REF1:{uuid.uuid4().hex[:8]}",
            allocated=30, quantity_received=25, receipt_status="pending",
        )
        later_open_sibling = _row(
            spo_number=spo_number, line_no=2, product_id=product.id, location_code=location,
            line_status="open", created_at=T1, source_ref=f"{MARKER}:REF2:{uuid.uuid4().hex[:8]}",
        )
        db.add_all([closed_row, later_open_sibling])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 4 not landed

        run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        stored = db.execute(
            text(
                "SELECT retired_at, stated_received, quantity_received "
                "FROM spo_allocations WHERE id = :id"
            ),
            {"id": closed_row.id},
        ).mappings().first()
        assert stored["retired_at"] is not None, stored
        assert stored["stated_received"] == 25, stored

        PickingHeaderService(db).sync_received_for_spo_number(spo_number)
        db.expire_all()
        after = db.execute(
            text("SELECT quantity_received FROM spo_allocations WHERE id = :id"),
            {"id": closed_row.id},
        ).mappings().first()
        assert after["quantity_received"] == 25, after


# =================================================================================== #
# AC-H16 (round 4): a fully-received row is NEVER stamped, sibling or not
# =================================================================================== #


class TestAcH16FullyReceivedRowNeverStamped:
    def test_a_fully_received_row_with_a_later_open_sibling_is_not_stamped(self, db):
        """AC-H16. A line closed at 100 of 100
        (`receipt_status='fully_received'`) that AutoCount still names, with
        a later-created OPEN sibling for the same product and location
        (round 2's own sibling evidence, fully satisfied): still NOT
        stamped. A received line is visible under R2 whether marked or not,
        so retiring it buys nothing and would wrongly drop it out of its
        group's receipt sharing.

        RED today: `_candidate_rows` (round 2/3) tests only
        `line_status == 'closed'` + `source_ref IS NOT NULL` + the sibling -
        no `receipt_status` guard at all - so this fully-received row is
        wrongly stamped.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"

        fully_received_row = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=f"{MARKER}:REF1:{uuid.uuid4().hex[:8]}",
            allocated=100, quantity_received=100, receipt_status="fully_received",
        )
        later_open_sibling = _row(
            spo_number=spo_number, line_no=2, product_id=product.id, location_code=location,
            line_status="open", created_at=T1, source_ref=f"{MARKER}:REF2:{uuid.uuid4().hex[:8]}",
        )
        db.add_all([fully_received_row, later_open_sibling])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 4 not landed

        run(db, DEFAULT_COMPANY_ID, dry_run=False)
        by_id = _retired_at_by_id(db, [fully_received_row.id])
        assert by_id[fully_received_row.id] is None, by_id


# =================================================================================== #
# AC-H18 (round 4 addition): the dry-run report is per-ROW evidence, not a bare count
# =================================================================================== #


class TestAcH18DryRunReportsPerRowEvidence:
    def test_dry_run_prints_the_row_id_and_the_justifying_sibling_s_source_ref(
        self, db, capsys
    ):
        """AC-H18. The dry-run report names, per candidate ROW: the
        allocation id, `source_ref`, `source_doc_ref`, `created_at`,
        `quantity_received` and `receipt_status`, plus the `created_at` and
        `source_ref` of the OPEN sibling that justified the stamp - not a
        bare per-document count, so the evidence for WHY a specific row was
        chosen is auditable before anyone runs `--apply`.

        RED today: the report prints one line per DOCUMENT
        (`f"  {spo_number}: {len(doc_rows)} row(s) to retire"`), naming
        neither the row's own id nor the sibling that justified it - this
        test's two `assert ... in output` calls are checking for text the
        current report never prints.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        location = f"{MARKER}-LOC"
        sibling_ref = f"{MARKER}:SIBREF:{uuid.uuid4().hex[:8]}"

        closed_row = _row(
            spo_number=spo_number, line_no=1, product_id=product.id, location_code=location,
            line_status="closed", created_at=T0, source_ref=f"{MARKER}:REF1:{uuid.uuid4().hex[:8]}",
        )
        later_open_sibling = _row(
            spo_number=spo_number, line_no=2, product_id=product.id, location_code=location,
            line_status="open", created_at=T1, source_ref=sibling_ref,
        )
        db.add_all([closed_row, later_open_sibling])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - round 4 not landed

        capsys.readouterr()  # discard anything already buffered
        run(db, DEFAULT_COMPANY_ID, dry_run=True)
        output = capsys.readouterr().out

        assert closed_row.id in output, output
        assert sibling_ref in output, output
