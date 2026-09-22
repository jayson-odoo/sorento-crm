"""RED tests for the AutoCount pull preview perf lane (T1-T8).

Plan: documentation/plans/autocount/PLAN-autocount-pull-preview-perf.md
UAC:  documentation/plans/autocount/autocount-pull-preview-perf-acceptance-criteria.md

Nothing here exists yet: `MasterIngestService._diff` returning `{}`/populated on a
REAL (non dry-run) run, `_update` being skipped when the diff is empty, the
per-batch reference cache in `product_rules.ensure_reference` /
`resolve_default_uom`, and `_apply_products`' own `unchanged` summary count are
ALL the coder's deliverable for this slice.

Substrate: `tests._pg_fixture.blank_session()` (Postgres, own blank schema, own
seeded chain) for every test except T4, which drives `app.tasks.
autocount_pull_tasks._apply_products` directly and therefore reuses the
`task_db` / `_FakeFoundryX` / `_patch_foundryx` / `_canonical_row` / `_header`
substrate from `tests.test_autocount_pull_sr1` and `_seed_apply_job` /
`_set_rows_page` / `_job_rows` from `tests.test_autocount_pull_sr3` - both
proven fixtures, imported rather than copied.

Company/category/brand/uom/product chains are seeded fresh per test (own
company anchor `DEFAULT_COMPANY_ID`, own category/brand/uom/product rows) -
CI's database starts empty.

Confirmed by an actual red run (22 Sep 2026, `sorento_buc_ci`): T1, T2, T3, T4,
T5 and T8 are RED today, each for the feature this plan is about, not a fixture
bug:

* T1 - a real re-push of an unchanged product still issues one
  `UPDATE ... products SET updated_by=..., updated_at=...`; `_update` is not
  yet skipped on an empty diff.
* T2 - `RecordResult.diff` is `None` on a real (non dry-run) ingest; `_diff`
  still early-returns `None` unless `self._dry_run`.
* T3 - same root cause as T2, pinned for both the changed and unchanged case.
* T4 - `_apply_products`' summary counts the unchanged record inside
  `updated` (2, not 1) and has no `unchanged` key at all; the outcome writer
  also gives it a "Product updated" row today.
* T5 - `product_categories`/`brands` are each queried twice for two records
  sharing one code (once per record) - no per-batch reference cache exists
  yet in `product_rules.ensure_reference`.
* T8 - a 5-row dry-run of an all-unchanged batch issues 5 `UPDATE products`
  statements before rolling them all back at the very end - the whole
  perf problem this plan cuts.

T6 and T7 are GUARD tests: both already pass today, unaffected by this slice,
and are kept as regression fences for the coder's cache (T6: a category
created by a record that then fails must never be handed to the next record
from a cache; T7: adoption still links the reference even when nothing about
the row changes).
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal

import pytest
from sqlalchemy import event, text

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.integration_reference_service import IntegrationReferenceService
from app.services.master_ingest_service import IngestOutcome, MasterIngestService

from tests._pg_fixture import blank_session, unique_code
from tests.test_autocount_pull_sr1 import (  # noqa: F401 - task_db is a fixture
    _FakeFoundryX,
    _canonical_row,
    _header,
    _patch_foundryx,
    task_db,
)
from tests.test_autocount_pull_sr3 import _job_rows, _seed_apply_job, _set_rows_page

MARKER = "PVPERF"


@pytest.fixture(autouse=True)
def _listeners():
    """Both global listener sets, exactly as the app registers them at startup.

    Registered explicitly (rather than relying on some other test file having
    already imported `app.main` first in this process) so T1/T2/T8's audit
    assertions are meaningful whether this file runs alone or as part of the
    full suite.
    """
    register_company_scope_listeners()
    register_audit_listeners()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@contextmanager
def _capture_sql(db):
    """Every statement issued on `db`'s own connection while the block runs."""
    calls: list[str] = []
    connection = db.get_bind()

    def _capture(conn, cursor, statement, *_a, **_kw):
        calls.append(statement)

    event.listen(connection, "before_cursor_execute", _capture)
    try:
        yield calls
    finally:
        event.remove(connection, "before_cursor_execute", _capture)


def _row(**overrides) -> dict:
    code = overrides.pop("code", None) or unique_code(MARKER)
    defaults = {
        "source_ref": f"{MARKER}:{code}:{uuid.uuid4().hex[:6]}",
        "code": code,
        "name": f"{MARKER} name {code}",
        "description": f"{MARKER} description {code}",
        "category_code": unique_code(f"{MARKER}CAT"),
        "uom_code": unique_code(f"{MARKER}UOM"),
        "brand_code": unique_code(f"{MARKER}BRD"),
        "list_price": "10.00",
        "is_active": True,
    }
    defaults.update(overrides)
    return defaults


#: `blank_session()` runs every table through a `schema_translate_map`, so the
#: real SQL SQLAlchemy emits against the test schema names the table
#: `zzs_blank_<pid>_<hex>.products`, never bare `products` - matching helpers
#: below tolerate an optional `<schema>.` prefix so they see the same
#: statement shape this suite emits AND the unqualified one production's
#: default-schema connection emits. A previous, bare-`startswith("update
#: products")` version silently matched nothing against the qualified name and
#: passed for the wrong reason - caught by inspecting the raw captured SQL
#: before trusting any of these tests as red or green.
import re


def _update_statements(calls: list[str]) -> list[str]:
    pattern = re.compile(r"^\s*update\s+(?:\S+\.)?products\b", re.IGNORECASE)
    return [s for s in calls if pattern.match(s)]


def _audit_insert_statements(calls: list[str]) -> list[str]:
    pattern = re.compile(r"^\s*insert\s+into\s+(?:\S+\.)?audit_logs\b", re.IGNORECASE)
    return [s for s in calls if pattern.match(s)]


def _select_statements(calls: list[str], table: str) -> list[str]:
    pattern = re.compile(
        rf"^\s*select\b.*\bfrom\s+(?:\S+\.)?{re.escape(table)}\b",
        re.IGNORECASE | re.DOTALL,
    )
    return [s for s in calls if pattern.match(s)]


def _product_row(db, product_id) -> dict:
    return dict(
        db.execute(
            text(
                "SELECT description, list_price, updated_at, updated_by "
                "FROM products WHERE id = :id"
            ),
            {"id": product_id},
        ).mappings().first()
    )


def _audit_count(db, product_id) -> int:
    # Product.__audit_entity_type__ = "product" (singular) overrides the
    # __tablename__ default every other entity's audit rows use.
    return db.execute(
        text("SELECT count(*) FROM audit_logs WHERE entity_type = 'product' AND entity_id = :id"),
        {"id": str(product_id)},
    ).scalar()


# =================================================================== T1 / T3
class TestUnchangedRealIngestIsANoWrite:
    """PP-1: a real (non dry-run) ingest of a product whose incoming columns
    all equal the stored row must not touch it at all."""

    def test_t1_unchanged_real_ingest_issues_no_update_no_audit_row(self, db):
        row = _row()
        user_1 = str(uuid.uuid4())
        user_2 = str(uuid.uuid4())

        created = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID, stamp_user_id=user_1).ingest(
            "products", [row]
        )
        assert created.created == 1, created.as_dict()
        product_id = created.records[0].entity_id
        db.commit()

        before = _product_row(db, product_id)
        audit_before = _audit_count(db, product_id)

        with _capture_sql(db) as calls:
            again = MasterIngestService(
                db, company_id=DEFAULT_COMPANY_ID, stamp_user_id=user_2
            ).ingest("products", [dict(row)])

        entry = again.records[0]
        assert entry.outcome is IngestOutcome.UPDATED, entry
        assert _update_statements(calls) == [], calls

        after = _product_row(db, product_id)
        assert after["updated_at"] == before["updated_at"], (before, after)
        assert str(after["updated_by"]) == user_1, after
        assert _audit_count(db, product_id) == audit_before


class TestDiffOnRealRun:
    """PP-3: `RecordResult.diff` is populated on real (non dry-run) runs too -
    `{}` for unchanged, a field map for changed."""

    def test_t3_diff_empty_when_unchanged_populated_when_changed(self, db):
        row = _row()
        MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest("products", [row])
        db.commit()

        unchanged = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest(
            "products", [dict(row)]
        )
        assert unchanged.records[0].diff == {}, unchanged.records[0].diff

        changed_row = dict(row)
        changed_row["list_price"] = "99.99"
        changed = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest(
            "products", [changed_row]
        )
        entry = changed.records[0]
        assert entry.diff, entry.diff
        assert entry.diff["list_price"]["incoming"] == Decimal("99.99"), entry.diff


# ========================================================================= T2
class TestChangedRealIngestStillWrites:
    """PP-2: a real ingest of a product with at least one differing column
    still updates it, bumps `updated_at`, stamps `updated_by` and writes the
    audit row - the ordinary write path must survive the T1 optimisation."""

    def test_t2_changed_real_ingest_updates_bumps_stamps_and_audits(self, db):
        row = _row()
        user_1 = str(uuid.uuid4())
        user_2 = str(uuid.uuid4())

        created = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID, stamp_user_id=user_1).ingest(
            "products", [row]
        )
        product_id = created.records[0].entity_id
        db.commit()

        changed_row = dict(row)
        changed_row["description"] = f"{row['description']} CHANGED"

        with _capture_sql(db) as calls:
            again = MasterIngestService(
                db, company_id=DEFAULT_COMPANY_ID, stamp_user_id=user_2
            ).ingest("products", [changed_row])

        entry = again.records[0]
        assert entry.outcome is IngestOutcome.UPDATED, entry
        assert entry.diff is not None and "description" in entry.diff, entry.diff
        assert entry.diff["description"]["incoming"] == changed_row["description"], entry.diff

        assert len(_update_statements(calls)) == 1, calls

        after = _product_row(db, product_id)
        assert after["description"] == changed_row["description"], after
        assert str(after["updated_by"]) == user_2, after

        audit_updates = db.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE entity_type = 'product' "
                "AND entity_id = :id AND action = 'UPDATE'"
            ),
            {"id": str(product_id)},
        ).scalar()
        assert audit_updates == 1, audit_updates


# ========================================================================= T5
class TestReferenceCachePerBatch:
    """PP-5: category / brand lookups are resolved once per distinct code per
    batch, not once per record."""

    def test_t5_category_and_brand_resolved_once_for_two_sharing_records(self, db):
        cat = ProductCategory(
            category_code=unique_code(MARKER), category_name="cat", company_id=DEFAULT_COMPANY_ID
        )
        brand = Brand(
            brand_code=unique_code(MARKER), brand_name="brand", company_id=DEFAULT_COMPANY_ID
        )
        uom = UnitOfMeasure(
            uom_code=unique_code(MARKER), uom_name="uom", company_id=DEFAULT_COMPANY_ID
        )
        db.add_all([cat, brand, uom])
        db.flush()
        db.commit()

        rows = [
            _row(category_code=cat.category_code, brand_code=brand.brand_code, uom_code=uom.uom_code),
            _row(category_code=cat.category_code, brand_code=brand.brand_code, uom_code=uom.uom_code),
        ]

        with _capture_sql(db) as calls:
            result = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest("products", rows)

        assert result.created == 2, result.as_dict()
        category_selects = _select_statements(calls, "product_categories")
        brand_selects = _select_statements(calls, "brands")
        assert len(category_selects) == 1, category_selects
        assert len(brand_selects) == 1, brand_selects


# ========================================================================= T6
class TestFailedRecordNeverPoisonsTheCache:
    """PP-6: a reference CREATED inside a record that then fails must never be
    served to the next record from the cache - the create was rolled back
    with the rest of that record's savepoint, so the id is dead.

    GUARD: already green today (no cache exists yet to poison) - kept as a
    regression fence for the coder's per-batch cache."""

    def test_t6_category_created_by_a_failed_record_is_resolved_fresh_by_the_next(self, db):
        existing_cat = ProductCategory(
            category_code=unique_code(MARKER), category_name="existing", company_id=DEFAULT_COMPANY_ID
        )
        uom = UnitOfMeasure(
            uom_code=unique_code(MARKER), uom_name="uom", company_id=DEFAULT_COMPANY_ID
        )
        db.add_all([existing_cat, uom])
        db.flush()

        claimed_code = unique_code(MARKER)
        claimed_product = Product(
            product_code=claimed_code,
            product_name=claimed_code,
            category_id=existing_cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
            company_id=DEFAULT_COMPANY_ID,
        )
        db.add(claimed_product)
        db.flush()
        IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID).link(
            entity_type="products",
            entity_id=str(claimed_product.id),
            source_ref=f"{MARKER}:othersys:{uuid.uuid4().hex[:6]}",
            source_system="othersys",
        )
        db.commit()

        shared_new_cat_code = unique_code(f"{MARKER}NEWCAT")
        # Record A: adopts `claimed_product` by code, but it is claimed under a
        # DIFFERENT source system -> ReferenceConflict, raised AFTER
        # `_product_columns` has already created + flushed `shared_new_cat_code`
        # inside this record's own savepoint.
        record_a = _row(code=claimed_code, category_code=shared_new_cat_code, uom_code=uom.uom_code)
        # Record B: a genuinely new product, sharing the SAME (now rolled-back)
        # category code - must resolve/create it again, never be handed A's
        # dead id.
        record_b = _row(category_code=shared_new_cat_code, uom_code=uom.uom_code)

        result = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest(
            "products", [record_a, record_b]
        )

        entry_a, entry_b = result.records
        assert entry_a.outcome is IngestOutcome.FAILED, entry_a
        assert "source_ref" in entry_a.errors, entry_a.errors
        assert entry_b.outcome is IngestOutcome.CREATED, entry_b

        cat_row = db.execute(
            text("SELECT id FROM product_categories WHERE category_code = :c"),
            {"c": shared_new_cat_code},
        ).mappings().first()
        assert cat_row is not None, "record B must have (re)created the category"

        product_b_row = db.execute(
            text("SELECT category_id FROM products WHERE id = :id"), {"id": entry_b.entity_id}
        ).mappings().first()
        assert str(product_b_row["category_id"]) == str(cat_row["id"])


# ========================================================================= T7
class TestAdoptionLinksEvenWithNoColumnChanges:
    """PP-7: adoption (ref miss, code hit, no origin) still links the
    reference even when nothing about the row actually changes.

    GUARD: already green today (`_link` runs unconditionally in the adopt
    branch) - kept as a regression fence against a C1 change that skips
    linking along with the write when the diff is empty."""

    def test_t7_adoption_links_the_reference_on_an_unchanged_row(self, db):
        cat = ProductCategory(
            category_code=unique_code(MARKER), category_name="cat", company_id=DEFAULT_COMPANY_ID
        )
        uom = UnitOfMeasure(
            uom_code=unique_code(MARKER), uom_name="uom", company_id=DEFAULT_COMPANY_ID
        )
        db.add_all([cat, uom])
        db.flush()

        code = unique_code(MARKER)
        description = f"{MARKER} description {code}"
        product = Product(
            product_code=code,
            product_name=code,
            description=description,
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("10.00"),
            company_id=DEFAULT_COMPANY_ID,
        )
        db.add(product)
        db.commit()

        new_ref = f"{MARKER}:{uuid.uuid4().hex[:8]}"
        row = {
            "source_ref": new_ref,
            "code": code,
            "name": code,
            "description": description,
            "list_price": "10.00",
        }

        result = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest("products", [row])

        entry = result.records[0]
        assert entry.outcome is IngestOutcome.UPDATED, entry
        assert entry.entity_id == str(product.id), entry

        ref_row = db.execute(
            text(
                "SELECT entity_id FROM integration_references "
                "WHERE source_ref = :r AND entity_type = 'products'"
            ),
            {"r": new_ref},
        ).mappings().first()
        assert ref_row is not None, "adoption must link the reference even on an empty diff"
        assert str(ref_row["entity_id"]) == str(product.id)

        after = db.execute(
            text("SELECT description, list_price FROM products WHERE id = :id"), {"id": product.id}
        ).mappings().first()
        assert after["description"] == description
        assert after["list_price"] == Decimal("10.00")


# ========================================================================= T8
class TestDryRunUnchangedBatchIsAlsoANoWrite:
    """PP-1's dry-run half: a preview of an all-unchanged batch must not
    issue writes it is only going to roll back anyway."""

    def test_t8_dry_run_of_five_unchanged_products_issues_no_writes(self, db):
        rows = [_row() for _ in range(5)]
        created = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest("products", rows)
        assert created.created == 5, created.as_dict()
        db.commit()

        with _capture_sql(db) as calls:
            preview = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest(
                "products", [dict(r) for r in rows], dry_run=True
            )

        assert preview.dry_run is True
        assert all(r.outcome is IngestOutcome.UPDATED for r in preview.records), preview.as_dict()
        assert all(r.diff == {} for r in preview.records), preview.as_dict()

        assert _update_statements(calls) == [], calls
        assert _audit_insert_statements(calls) == [], calls


# ========================================================================= T4
class TestApplyProductsSummaryDistinguishesUnchanged:
    """PP-4: the pull apply summary distinguishes `updated` from `unchanged`,
    and an unchanged record gets no "Product updated" outcome row."""

    def test_t4_one_changed_one_unchanged_one_created(self, task_db, monkeypatch):
        from app.models.job import ImportJob
        from app.tasks.autocount_pull_tasks import _apply_products

        db, _factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake, db)

        job_user = str(uuid.uuid4())
        created_code = f"{MARKER}-T4CREATED-{uuid.uuid4().hex[:6]}"
        changed_code = f"{MARKER}-T4CHANGED-{uuid.uuid4().hex[:6]}"
        unchanged_code = f"{MARKER}-T4UNCHANGED-{uuid.uuid4().hex[:6]}"

        changed_row = _canonical_row(changed_code, list_price="10.00")
        unchanged_row = _canonical_row(unchanged_code, list_price="20.00")

        # Seed the "changed" and "unchanged" products with a REAL prior ingest -
        # `unchanged_row` will be re-pushed byte-identical below, `changed_row`
        # with one different value.
        MasterIngestService(db, company_id=DEFAULT_COMPANY_ID).ingest(
            "products", [changed_row, unchanged_row]
        )
        db.commit()

        changed_row_pushed = dict(changed_row)
        changed_row_pushed["list_price"] = "15.00"
        created_row = _canonical_row(created_code)

        rows = [created_row, changed_row_pushed, dict(unchanged_row)]
        snapshot_id = f"{MARKER}-snap-{uuid.uuid4().hex[:8]}"
        fake.status = (200, {**_header(rows), "snapshotId": snapshot_id})
        _set_rows_page(fake, snapshot_id, rows)

        job_id = _seed_apply_job(
            db, user_id=job_user, company_id=DEFAULT_COMPANY_ID, entity="products",
            snapshot_id=snapshot_id,
        )
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()

        summary = _apply_products(db, job, snapshot_id)

        assert summary["created"] == 1, summary
        assert summary["updated"] == 1, summary
        assert summary["unchanged"] == 1, summary

        written = _job_rows(db, job_id)
        outcomes = sorted(w["outcome"] for w in written)
        assert outcomes == ["created", "updated"], written
