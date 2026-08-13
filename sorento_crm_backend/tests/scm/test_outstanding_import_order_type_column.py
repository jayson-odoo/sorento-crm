"""What happens when the sales-order extract DOES carry an order-type column.

The classification lives on `sales_orders.order_type` and is stamped onto `demand_class`,
which is what `scm.priority_policy.demand_class_weights` weighs. Today's AutoCount extract
carries no such column, so a document the upload CREATES has no evidence of the split
anywhere and takes the customer-segment fallback, which is NULL for 3,276 of 3,284
customers. That is a real gap, and the fix is deliberately DATA rather than code: an
`import_field_alias` row plus one reader field, so onboarding an export that does carry the
column is an INSERT and not a release.

These tests pin the three halves of that promise: the column resolves through the alias
table at all, a document the upload creates is classified from it, and a value a person
already set on the header is never overwritten by a weekly re-upload.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.order import SalesOrder
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import MARKER, Codes, make_codes, seed_catalogue, workbook

# The columns of the red suite plus the one this file is about. The header wording is the
# seeded alias, not the canonical field name, because resolving a HUMAN's spelling is the
# whole reason the reader goes through the alias table.
HEADERS = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION",
           "ORDER TYPE")


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def codes() -> Codes:
    return make_codes()


@pytest.fixture()
def seeded(db, codes) -> Codes:
    seed_catalogue(db, codes)
    _require_order_type_alias(db)
    return codes


def _require_order_type_alias(db) -> None:
    """Fail loudly, never skip, when the order-type alias is absent.

    It is reference data seeded by migration 311 and replayed by `scripts/bootstrap_env`, so
    an empty result means this database was built without the seed rather than that these
    tests do not apply to it. A skip here would delete the file from the run, and a suite
    that vanishes reads exactly like a suite that passed.
    """
    if not db.execute(text(
        "SELECT 1 FROM import_field_alias "
        "WHERE doc_type = 'outstanding_so' AND field = 'order_type' LIMIT 1"
    )).scalar():
        pytest.fail("no outstanding_so order_type row in import_field_alias: this database "
                    "was built without the SCM alias seed (migration 311 / bootstrap_env)")


def _upload(codes: Codes, doc: str, order_type, *, debtor: str = "") -> bytes:
    """A one-line extract for `doc` stating `order_type` in the file itself."""
    return workbook(
        [(doc, debtor, codes.item_rl, 40, date(2026, 7, 1), codes.loc_project, order_type)],
        headers=HEADERS,
    )


def _header(db, so_number: str):
    return db.execute(
        text("SELECT order_type, demand_class FROM sales_orders WHERE so_number = :n"),
        {"n": so_number},
    ).first()


def test_an_order_type_column_in_the_file_resolves_through_the_alias_table(db, seeded):
    """If the header does not map, everything else here is theatre.

    An unresolved column is reported as unmapped and its value never reaches the write path,
    which would look exactly like a classification bug rather than a missing seed row.
    """
    res = svc.preview(db, _upload(seeded, seeded.project_so, "PROJECT"), SO)

    assert res.ok
    assert "ORDER TYPE" not in res.unmapped_headers


def test_a_file_stating_project_classifies_an_order_the_upload_creates(db, seeded):
    """The gap this column closes: no header exists yet, so the file is the only evidence.

    Without it this document has no order type anywhere and no customer segment, and the
    importer can only report it. With it the order arrives at the planner already carrying
    the class the fulfilment policy weighs.
    """
    out = svc.apply(db, _upload(seeded, seeded.project_so, "PROJECT"), SO)

    assert out["ok"]
    order_type, demand_class = _header(db, seeded.project_so)
    assert demand_class == "project"
    assert order_type == "PROJECT", "the stated split was not kept on the document"
    assert not any(seeded.project_so in " ".join(str(v) for v in p.values())
                   for p in out["row_problems"]), (
        "an order the file classified was still reported as unclassifiable")


def test_a_dealer_file_classifies_as_the_default_class(db, seeded):
    """The other half, keeping the vocabulary inside the seeded weights map.

    `demand_class_weights` holds `project` and `retail`; a document stamped `dealer` would
    fall outside it and score as nothing, which is worse than the default it replaced.
    """
    out = svc.apply(db, _upload(seeded, seeded.dealer_so, "DEALER"), SO)

    assert out["ok"]
    assert _header(db, seeded.dealer_so)[1] == svc.DEFAULT_DEMAND_CLASS


def test_the_file_never_overwrites_an_order_type_someone_set(db, seeded):
    """The extract is not the record of a decision a person made in the CRM.

    The same file is re-uploaded every week. If it restated the split instead of filling it,
    one stale export would silently reclassify a document that had been corrected by hand,
    and the only symptom would be the order winning or losing stock it should not.
    """
    db.add(SalesOrder(id=str(uuid.uuid4()), so_number=seeded.project_so, status="open",
                      order_type="dealer"))
    db.flush()

    out = svc.apply(db, _upload(seeded, seeded.project_so, "PROJECT"), SO)

    assert out["ok"]
    order_type, demand_class = _header(db, seeded.project_so)
    assert order_type == "dealer", "the file overwrote a split someone had set by hand"
    assert demand_class == svc.DEFAULT_DEMAND_CLASS, (
        "the class was stamped from the file rather than from the document")


def test_a_blank_order_type_cell_leaves_the_document_unclassified(db, seeded):
    """A column present but empty is not evidence, and must not read as retail.

    Half-filled columns are how these exports actually arrive. Treating the blank as "not a
    project" would classify the row silently and stably, and nobody would ever learn which
    documents were guessed at.
    """
    unknown = f"{MARKER}-NOCUST-{uuid.uuid4().hex[:8]}".upper()

    out = svc.apply(db, _upload(seeded, seeded.project_so, None, debtor=unknown), SO)

    assert out["ok"]
    assert _header(db, seeded.project_so)[1] is None
    assert any(seeded.project_so in " ".join(str(v) for v in p.values())
               for p in out["row_problems"]), (
        "a blank order type was accepted without telling anyone")
