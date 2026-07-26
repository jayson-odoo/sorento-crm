"""AutoCount ingest Slice 3 — item packages (header + lines), bespoke adopter.

Same verdict contract as the flat masters, plus the parent+lines specifics:
  * every line's product_code must resolve to a real product; an unresolvable
    code makes the WHOLE package retryable (not failed, not half-written);
  * on re-push the lines are replaced wholesale (canonical PackageDTL is
    authoritative);
  * adopt-by-package_code; dry-run writes nothing; annotation survives re-sync.

blank_session (isolated scratch schema, create_savepoint join) so the bespoke
service's begin_nested savepoints and the annotation commit stay contained.
"""
import pytest

from app.models.item_package import ItemPackage, ItemPackageLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.autocount_mirror_service import MirrorReadService
from app.services.item_package_ingest_service import ItemPackageIngestService
from app.services.master_ingest_service import IngestOutcome
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return ItemPackageIngestService(db, integration_id=None)


@pytest.fixture()
def product(db):
    """A real product for lines to resolve against (products FKs are NOT NULL)."""
    cat = ProductCategory(category_code="ZZT-CAT", category_name="ZZT Cat")
    uom = UnitOfMeasure(uom_code="ZZT-PCS", uom_name="Pieces")
    db.add_all([cat, uom])
    db.flush()
    p = Product(product_code="ZZT-ITEM", product_name="ZZT Item",
                category_id=cat.id, base_uom_id=uom.id, list_price=0)
    db.add(p)
    db.flush()
    return p


def _pkg(code="ZZT-PKG", ref=None, lines=None, **extra):
    return {
        "source_ref": ref or f"PKG-{code}",
        "code": code,
        "description": "Bundle",
        "expiry_date": "2027/12/31",
        "user_uom": "PCS",
        "lines": lines if lines is not None else [
            {"product_code": "ZZT-ITEM", "uom": "PCS", "qty": 15, "unit_price": 15.99}
        ],
        **extra,
    }


class TestCreate:
    def test_creates_header_and_lines(self, db, svc, product):
        r = svc.ingest([_pkg()])
        assert r.records[0].outcome is IngestOutcome.CREATED
        pkg = db.query(ItemPackage).filter_by(package_code="ZZT-PKG").one()
        assert pkg.description == "Bundle"
        assert str(pkg.expiry_date) == "2027-12-31"
        assert len(pkg.lines) == 1
        assert pkg.lines[0].product_id == product.id
        assert str(pkg.lines[0].qty) == "15.0000"

    def test_unknown_field_rejected(self, svc, product):
        r = svc.ingest([_pkg(**{"PackageCode": "leaked"})])
        assert r.records[0].outcome is IngestOutcome.FAILED

    def test_dry_run_writes_nothing(self, db, svc, product):
        r = svc.ingest([_pkg()], dry_run=True)
        assert r.records[0].outcome is IngestOutcome.CREATED
        assert db.query(ItemPackage).count() == 0


class TestMissingProduct:
    def test_unresolvable_line_makes_whole_package_retryable(self, db, svc):
        # No product seeded -> the single line cannot resolve.
        r = svc.ingest([_pkg()])
        assert r.records[0].outcome is IngestOutcome.RETRYABLE
        # And nothing was written -- not even the header.
        assert db.query(ItemPackage).count() == 0

    def test_one_bad_line_aborts_the_whole_package(self, db, svc, product):
        r = svc.ingest([_pkg(lines=[
            {"product_code": "ZZT-ITEM"},          # resolves
            {"product_code": "ZZT-NOPE"},          # does not
        ])])
        assert r.records[0].outcome is IngestOutcome.RETRYABLE
        assert db.query(ItemPackageLine).count() == 0


class TestIdempotentAndReplace:
    def test_repush_updates_and_replaces_lines(self, db, svc, product):
        svc.ingest([_pkg(ref="PKG-1", lines=[
            {"product_code": "ZZT-ITEM", "qty": 1},
            {"product_code": "ZZT-ITEM", "qty": 2},
        ])])
        # Re-push with a single line: the old two must be replaced, not merged.
        r = svc.ingest([_pkg(ref="PKG-1", lines=[{"product_code": "ZZT-ITEM", "qty": 9}])])
        assert r.records[0].outcome is IngestOutcome.UPDATED
        assert db.query(ItemPackage).count() == 1
        lines = db.query(ItemPackageLine).all()
        assert len(lines) == 1
        assert str(lines[0].qty) == "9.0000"

    def test_adopts_by_package_code(self, db, svc, product):
        # Pre-existing package with the same code, no integration link.
        pre = ItemPackage(package_code="ZZT-PKG")
        db.add(pre)
        db.flush()
        r = svc.ingest([_pkg()])
        assert r.records[0].outcome is IngestOutcome.UPDATED
        assert r.records[0].entity_id == pre.id


class TestAnnotation:
    def test_note_survives_resync(self, db, svc, product):
        svc.ingest([_pkg(ref="PKG-1")])
        pkg = db.query(ItemPackage).filter_by(package_code="ZZT-PKG").one()
        MirrorReadService(db).annotate(
            ItemPackage, pkg.id, resource="Item Package",
            internal_note="verify pricing", follow_up=True,
            set_note=True, set_follow_up=True,
        )
        svc.ingest([_pkg(ref="PKG-1", description="Changed")])
        db.refresh(pkg)
        assert pkg.description == "Changed"
        assert pkg.internal_note == "verify pricing"
        assert pkg.follow_up is True
