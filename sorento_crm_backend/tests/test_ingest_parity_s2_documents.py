"""Tests for ingest parity standardisation, Phase S2 (sales order and purchase
order rules). Several of these now PASS against the shipped code (`customer_segment`/
`customer_region`/`region` exist on the schemas and models, `order_inquiry_conflicts`
now exists) - each such test/class says so in its own docstring rather than
carrying a stale "not yet" name; a handful of real gaps remain and are still red
(see `tests/test_ingest_parity_review_guards.py` for the ones the reviewer pass
found with no guard at all, e.g. the SO push half of customer_segment/region
never actually threading through to a back-create).

UAC: documentation/plans/_archive/autocount/ingest-parity-standardisation-acceptance-criteria.md
     Phase S2, AC-P2-1 .. AC-P2-7.
PLAN: documentation/plans/_archive/autocount/PLAN-ingest-parity-standardisation.md sections 2.2, 2.6, 2.7.

Two substrates, chosen per AC by what each driver actually needs:

* **The outstanding upload** (`app.services.scm.outstanding_import_service.preview`/
  `apply`) needs `import_field_alias` rows, which are migration-seeded and
  therefore ABSENT from a `blank_session()` scratch schema (`create_all` skips
  migration bodies). Every upload-driven test below uses `tests._pg_fixture
  .pg_session()` (the real, rolled-back dev-copy DB) plus
  `tests.scm._outstanding_workbooks` for headers/codes, exactly as the existing
  `tests/scm/test_outstanding_import_*.py` suite does.
* **The ESB document/masters ingest** needs no migration-seeded reference
  data, so document-level tests reuse the `env` fixture (`blank_session()` +
  a real `TestClient(app)`) from `tests/test_ingest_documents.py` byte for
  byte - the same substrate `tests/test_ingest_documents_v2_hooks.py` reuses,
  so `_run_document_hooks` (only reachable through the route) is exercised
  for real rather than re-implemented.
* **AC-P2-7's parity test** needs BOTH channels writing into ONE database it
  can then diff, so it uses `pg_session()` for both sides and constructs
  `DocumentIngestService` directly (bypassing the HTTP route - parity is
  about the DATA the two channels write, not about post-commit hooks).

Model facts verified in code before relying on them:

* `_BINDINGS[SO].party_back_create` is explicitly `False` today, with its own
  comment explaining why ("a back-created customer with no segment would
  only make WORSE") - `outstanding_import_service.py` never imports
  `customer_back_create` at all. `apply()`'s return dict has no
  `customers_created` key.
* `app/services/master_ref_resolver.py` (`MasterRefResolver`, shared by
  `DocumentIngestService`) ALREADY implements more of the S2 ladder than the
  UAC's own framing suggests: an unresolved warehouse ref/code ALREADY
  returns `None` + `warehouse_unresolved` on the ESB side (D10 is done); an
  unresolved customer CODE (no ref) ALREADY returns `None` +
  `customer_unresolved` (not retryable); a customer CODE+NAME pair ALREADY
  back-creates via `customer_back_create.get_or_create`. Only an unresolved
  PRODUCT still raises `MissingReference`, which `_ingest_one` catches at the
  DOCUMENT level - the whole record goes RETRYABLE, never a per-line drop.
  Tests below do NOT re-test the parts that already work (that would be a
  false green); only the product-drop gap is tested on the ESB side.
* `outstanding_import_service._resolve` (the upload) ALREADY skips a line
  with an unresolvable ITEM CODE and reports it (`ResolutionIssue`) - matches
  AC-P2-3's product half already; not re-tested. Its STOCK LOCATION handling
  is the opposite of what AC-P2-3 wants: `test_outstanding_import_po.py`'s
  own docstring calls skipping-on-unresolved-location "the judgement call" -
  today it SKIPS the line the same as an unresolvable item, where S2 wants
  it KEPT with `warehouse_id` NULL and a warning, matching the ESB.
* `Customer` (in `app/models/order.py`) now has BOTH `market_segment_code` and
  `region`; `CanonicalSalesOrder` now carries `customer_segment`/
  `customer_region` too (`app/schemas/canonical_documents.py`) - all shipped.
  What is NOT wired: `document_ingest_service.py` never reads
  `payload.customer_segment`/`customer_region` at all, even though
  `customer_rules.back_create_customer` already accepts `segment`/`region`
  kwargs - see `tests/test_ingest_parity_review_guards.py::TestB5...` for the
  still-red test.
* `planning_change_service.build_batch` (`app/services/planning_change_service.py` -
  NOT under `app/services/scm/`) and its tables
  (`app.models.planning_change.PlanningChangeBatch`/`PlanningChangeRow`, the
  `projects.planning_change_batches`/`planning_change_rows` tables) already
  exist, wired ONLY to `outstanding_import_service.apply()`'s own `Diff`.
  `app/api/v1/external/ingest.py::_run_document_hooks` never calls it for
  `sales_orders` today (only `_run_plan_exception_hook` does) - confirmed by
  the EXISTING, deliberately-passing guard
  `tests/test_ingest_documents_v2_hooks.py::TestPlanningChangeIsNotRunByIngest`,
  whose own docstring calls this "deferred by D7" and says it "would only
  turn red if some future change wired it in by mistake". This UAC's D10 is
  that future change (BL-058) - the guard test itself is untouched here (not
  mine to edit), but making AC-P2-4 green will require updating it.
* `OrderInquiryConflict` (`order_inquiry_conflicts`, migration 476) now
  exists and is recorded by `_sync_lines`' by-ref branch when the ESB states a
  DIFFERENT warehouse than an already-resolved line carries. The ref-less
  ADOPTION path (`_adopt_lines`) does not yet record it - see
  `tests/test_ingest_parity_review_guards.py::TestB4...` for the still-red
  test.

Every behavioural test below drives the real, already-existing service and
fails on an assertion; only the two pure-function tests (`derive_document_status`,
the shared status derivation) import the not-yet-existing
`app.services.rules.document_rules` inside the test body, where a
`ModuleNotFoundError` today is the correct red for a function not yet
extracted.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import inspect, text

from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.master_ingest_service import IngestOutcome, MasterIngestService
from app.services.scm import outstanding_import_service as outstanding_svc
from app.services.scm.outstanding_reader import PO, SO

from tests._pg_fixture import pg_session, unique_code
from tests.scm._outstanding_workbooks import (
    HEADERS as SO_FULL_HEADERS,
    Codes,
    make_codes,
    seed_catalogue,
    so_headers,
    so_row,
    workbook,
)
from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER as DOC_MARKER,
    _po_line,
    _po_record,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]

MARKER = "ZZTIP2"


# --------------------------------------------------------------------- upload
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
    return codes


def _new_debtor_row(name, doc, so_date, debtor, item, qty, when, location,
                     order_type="DEALER"):
    """One row of the FULL SO export shape (`_outstanding_workbooks.HEADERS`),
    naming a debtor CODE and a NAME (`PROJECT/CUSTOMER`) neither of which the
    catalogue holds yet."""
    return (name, doc, so_date, debtor, item, "PCS", qty, when, location, order_type, None)


class TestAcP21UploadBackCreatesCustomerOnCodeAndName:
    """D8: the outstanding SO upload back-creates a customer when the debtor
    code AND name are both present, via the same `customer_back_create
    .get_or_create` the ESB already calls (D2's rule already exists on the
    ESB path). The upload's own binding, `_BINDINGS[SO]`, sets
    `party_back_create=False` for exactly this feature - AC-P2-1 flips it."""

    def test_debtor_code_and_name_back_creates_the_customer_and_links_the_order(
        self, seeded, db
    ):
        codes = seeded
        debtor_code = f"{MARKER}-NEWDEB-{uuid.uuid4().hex[:8]}".upper()
        debtor_name = f"{MARKER} Brand New Sdn Bhd"
        so_number = f"{MARKER}-NEWSO-{uuid.uuid4().hex[:8]}".upper()
        file = workbook(
            [
                _new_debtor_row(
                    debtor_name, so_number, date(2026, 5, 4), debtor_code,
                    codes.item_rl, 10, date(2026, 7, 1), codes.loc_project,
                )
            ],
            headers=SO_FULL_HEADERS,
        )

        out = outstanding_svc.apply(db, file, SO)

        assert out["applied"]["added"] == 1, out
        customer = db.execute(
            text(
                "SELECT customer_code, customer_name FROM customers "
                "WHERE upper(customer_code) = :c"
            ),
            {"c": debtor_code},
        ).first()
        assert customer == (debtor_code, debtor_name), "the customer must be back-created"
        linked = db.execute(
            text("SELECT customer_id FROM sales_orders WHERE so_number = :n"),
            {"n": so_number},
        ).scalar()
        assert linked is not None, "the order must link to the back-created customer"
        assert out.get("customers_created", 0) == 1, "apply must report the back-create count"


class TestAcP22CustomerSegmentAndRegion:
    """D8/D16: the ESB customer payload gains `market_segment_code` + `region`;
    the SO payload gains `customer_segment`/`customer_region`, used only on
    back-create."""

    def test_customer_masters_payload_accepts_segment_and_region(self, env):
        code = unique_code(DOC_MARKER)
        svc = MasterIngestService(env.db, integration_id=None, company_id=env.company_a)
        result = svc.ingest(
            "customers",
            [
                {
                    "source_ref": _ref("SEG"),
                    "code": code,
                    "name": "Segment Co",
                    "market_segment_code": "DEALER",
                    "region": "Klang Valley",
                }
            ],
        )
        record = result.records[0]
        assert record.outcome is IngestOutcome.CREATED, record.errors

    def test_customers_table_has_no_region_column_yet(self):
        from app.models.order import Customer

        assert "region" in Customer.__table__.columns, (
            "S2 must add customers.region (AutoCount Debtor.AreaCode) - "
            "confirmed absent by reading app/models/order.py"
        )

    def test_so_payload_accepts_customer_segment_and_region(self, env):
        record = _so_record(
            env, customer_segment="DEALER", customer_region="Klang Valley"
        )
        res = env.post(INGEST_SO, [record])
        body = res.json()["records"][0]
        assert body["outcome"] == "created", body


class TestAcP23UnknownProductDroppedUnknownLocationKept:
    """D9: a line whose product does not resolve is DROPPED and reported, the
    rest of the document lands (ESB gap - today the whole document goes
    retryable); a line whose location does not resolve is KEPT with
    `warehouse_id` NULL and a warning (upload gap - today the whole LINE is
    skipped, matching an unresolvable item instead of being kept).

    The ESB's location-unresolved case and the upload's item-unresolved case
    are BOTH already correct and are deliberately not re-tested here.
    """

    def test_esb_unknown_product_line_is_dropped_not_the_whole_document(self, env):
        good_line = _so_line(env)
        # NOT `_so_line(env, product_ref=None, ...)` - the helper's own
        # `product_ref or env.product_ref` silently falls back to the valid
        # ref for a `None`, which resolves fine and defeats the point. Built
        # by hand so `product_ref` is genuinely ABSENT and only the unknown
        # `product_code` is sent.
        bad_line = {
            "source_ref": _ref("SOL"),
            "product_code": f"{DOC_MARKER}-NOSUCHITEM",
            "qty_ordered": 10,
        }
        record = _so_record(env, lines=[good_line, bad_line])

        res = env.post(INGEST_SO, [record])
        body = res.json()["records"][0]

        assert body["outcome"] == "created", body
        assert body.get("lines", {}).get("dropped") == 1, body
        header = env.header("sales_orders", record["source_ref"])
        assert header is not None
        assert len(env.so_lines(header["id"])) == 1, "only the resolvable line should land"

    def test_upload_unknown_location_keeps_the_line_instead_of_skipping_it(self, seeded, db):
        codes = seeded
        unknown_loc = f"{MARKER}-LOCX-{uuid.uuid4().hex[:8]}".upper()
        headers = so_headers("S/O NO", "SO DATE", "DEBTOR CODE", "ITEM CODE", "QTY",
                              "DELIVERY DATE", "STOCK LOCATION")
        so_number = f"{MARKER}-LOCSO-{uuid.uuid4().hex[:8]}".upper()
        file = workbook(
            [
                so_row(
                    so_number, date(2026, 5, 4), f"{MARKER}-DEBTOR",
                    codes.item_rl, 20, date(2026, 7, 1), unknown_loc,
                )
            ],
            headers=headers,
        )

        out = outstanding_svc.apply(db, file, SO)

        assert out["applied"]["added"] == 1, (
            "an unresolvable location must keep the line (warehouse NULL), not skip it: "
            f"{out}"
        )
        warehouse_id = db.execute(
            text(
                "SELECT sol.warehouse_id FROM sales_order_lines sol "
                "JOIN sales_orders so ON so.id = sol.sales_order_id "
                "WHERE so.so_number = :n"
            ),
            {"n": so_number},
        ).scalar()
        assert warehouse_id is None


class TestAcP24PlanningChangeBatchOnEsbSalesOrderBatch:
    """D10 (BL-058): a non-dry ESB `sales_orders` batch must call
    `planning_change_service.build_batch`, exactly as `outstanding_import_service
    .apply()` already does after its own diff. Today `_run_document_hooks`
    calls only `_run_plan_exception_hook` for `sales_orders` -
    `build_batch` is never called at all (see the module docstring for the
    existing guard test this flips).
    """

    def test_non_dry_esb_so_batch_calls_build_batch(self, env, monkeypatch):
        from app.services import planning_change_service

        calls: list[dict] = []
        monkeypatch.setattr(
            planning_change_service, "build_batch", lambda *a, **kw: calls.append(kw)
        )

        record = _so_record(env)
        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        assert calls, "AC-P2-4/D10: a non-dry ESB sales_orders batch must call build_batch"


class TestAcP25StatusOptionalAndDerived:
    """D20: `status` becomes optional on the SO/PO payload; absent means the
    shared `derive_document_status(lines, existing)` decides. Today `status`
    is `Field(..., ...)` (required) on `_CanonicalDocument` - omitting it is a
    validation failure, not a derivation."""

    def test_esb_so_payload_status_is_optional(self, env):
        record = _so_record(env)
        del record["status"]

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text

    def test_esb_po_payload_status_is_optional(self, env):
        record = _po_record(env)
        del record["status"]

        res = env.post(INGEST_PO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text

    def test_derive_document_status_golden_cases(self):
        from app.services.rules.document_rules import derive_document_status

        # (ordered, delivered, existing_status) -> derived status.
        cases = [
            ((10, 10), "closed"),   # all lines settled
            ((10, 4), "open"),      # some outstanding
            ((10, 0), "open"),      # nothing delivered
        ]
        for (ordered, delivered), expected in cases:
            lines = [{"qty_ordered": ordered, "qty_delivered": delivered}]
            assert derive_document_status(lines, existing=None) == expected


class TestAcP26OrderInquiryWarehouseCollision:
    """D22: an ESB push naming no location must not clear a warehouse the
    Order Inquiry sheet (stood in for here by the warehouse the line already
    resolved to) already set; a push naming a DIFFERENT location must record
    the disagreement so the worklist can render it."""

    def test_esb_push_without_a_location_must_not_clear_an_existing_warehouse(self, env):
        so_ref = _ref("SO")
        line_ref = _ref("SOL")
        record = _so_record(
            env, ref=so_ref,
            lines=[_so_line(env, ref=line_ref, warehouse_ref=env.warehouse_ref)],
        )
        res = env.post(INGEST_SO, [record])
        assert res.json()["records"][0]["outcome"] == "created", res.text

        header = env.header("sales_orders", so_ref)
        before = env.so_lines(header["id"])
        assert before[0]["warehouse_id"] is not None, "fixture sanity: warehouse must be set"

        record2 = _so_record(
            env, ref=so_ref, number=record["so_number"],
            lines=[_so_line(env, ref=line_ref)],
        )
        res2 = env.post(INGEST_SO, [record2])
        assert res2.json()["records"][0]["outcome"] == "updated", res2.text

        after = env.so_lines(header["id"])
        assert after[0]["warehouse_id"] is not None, (
            "an ESB push naming no location must not clear a warehouse already set"
        )

    def test_order_inquiry_conflicts_table_does_not_exist_yet(self, env):
        assert inspect(env.db.get_bind()).has_table("order_inquiry_conflicts"), (
            "S2 must add somewhere to record an ESB warehouse overwrite so the "
            "Order Inquiry worklist can render it (PLAN 2.7) - chosen shape here: "
            "a queryable table named order_inquiry_conflicts, not a JSON blob"
        )


class TestAcP27UploadVsEsbParity:
    """A scaled-down stand-in for the UAC's 30-document SO/PO fixture (the
    full fixture, covering every status mix, is left for the coder/reviewer
    pass): one SO naming a NEW debtor (code+name, not yet in the catalogue)
    through the outstanding upload into company A, and the same document
    through the ESB into company B - the two channels must resolve the
    customer link identically. Today they do not, because of the exact gap
    AC-P2-1 names (the upload never back-creates)."""

    def test_new_customer_linkage_diverges_between_upload_and_esb(self, seeded, db):
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.product import Product, ProductCategory, UnitOfMeasure
        from app.services.document_ingest_service import DocumentIngestService

        codes = seeded
        other = Company(id=str(uuid.uuid4()), name=f"{MARKER} B", code=unique_code(MARKER)[:10])
        db.add(other)
        db.flush()
        company_b = str(other.id)

        debtor_code = f"{MARKER}-PARDEB-{uuid.uuid4().hex[:8]}".upper()
        debtor_name = f"{MARKER} Parity Sdn Bhd"

        # Upload half, into company A (the ambient default in pg_session).
        so_number_a = f"{MARKER}-PARSO-{uuid.uuid4().hex[:8]}".upper()
        file = workbook(
            [
                _new_debtor_row(
                    debtor_name, so_number_a, date(2026, 5, 4), debtor_code,
                    codes.item_rl, 5, date(2026, 7, 1), codes.loc_project,
                )
            ],
            headers=SO_FULL_HEADERS,
        )
        outstanding_svc.apply(db, file, SO)
        customer_id_a = db.execute(
            text("SELECT customer_id FROM sales_orders WHERE so_number = :n"),
            {"n": so_number_a},
        ).scalar()

        # ESB half, into company B, same debtor code + name - its OWN category/uom/
        # product, seeded fresh under company B rather than reusing company A's
        # (both are company-scoped rows, so they cannot be shared across the anchor).
        set_company_scope(db, frozenset({company_b}))
        category = ProductCategory(category_code=unique_code(MARKER), category_name="Cat")
        uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
        db.add_all([category, uom])
        db.flush()
        product = Product(
            product_code=codes.item_rl, product_name=codes.item_rl,
            category_id=category.id, base_uom_id=uom.id, list_price=0,
        )
        db.add(product)
        db.flush()
        esb = DocumentIngestService(db, integration_id=None, company_id=company_b)
        product_ref = f"DK-{codes.item_rl}-B"
        esb.refs.link(entity_type="products", entity_id=product.id, source_ref=product_ref)

        so_number_b = f"{MARKER}-PARSO-{uuid.uuid4().hex[:8]}".upper()
        result = esb.ingest(
            "sales_orders",
            [
                {
                    "source_ref": f"DK-{so_number_b}",
                    "so_number": so_number_b,
                    "status": "open",
                    "customer_code": debtor_code,
                    "customer_name": debtor_name,
                    "lines": [
                        {
                            "source_ref": f"DK-{so_number_b}-L1",
                            "product_ref": product_ref,
                            "qty_ordered": "5",
                        }
                    ],
                }
            ],
        )
        assert result.records[0].outcome is IngestOutcome.CREATED, result.records[0].errors
        customer_id_b = db.execute(
            text("SELECT customer_id FROM sales_orders WHERE so_number = :n"),
            {"n": so_number_b},
        ).scalar()

        assert (customer_id_a is None) == (customer_id_b is None), (
            "the two channels must resolve the same (code, name) customer identically: "
            f"upload={customer_id_a!r} esb={customer_id_b!r}"
        )
