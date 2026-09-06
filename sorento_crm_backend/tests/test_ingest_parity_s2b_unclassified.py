"""RED test for ingest parity standardisation, Phase S2b (D23, captain 2026-09-06).

UAC: documentation/plans/autocount/ingest-parity-standardisation-acceptance-criteria.md
     Phase S2b, AC-P2-8.
PLAN: documentation/plans/autocount/PLAN-ingest-parity-standardisation.md D23.

D23 reverses QP1 (captain, 26 Aug 2026, `outstanding_import_service._classify_demand`'s own
docstring): an unclassifiable document no longer refuses the whole file. It lands on BOTH
channels with `demand_class` NULL - the ESB already does this today (`WARN_UNCLASSIFIED_DEMAND`
in `app/services/document_ingest_service.py`); only the outstanding upload still refuses
(`outstanding_import_service.apply`, `if plan.unclassified: return {"ok": False, ...}` before
any write - confirmed by reading the code, `app/tasks/import_tasks.py`'s
`_missing_columns_message` turns that into the job-failure toast at ~3660-3670).

Substrate: `tests._pg_fixture.pg_session()` (needs the migration-seeded `import_field_alias`
"AGENT" alias, migration 357 - ABSENT from a `blank_session()` scratch schema) for the upload
half, exactly as `tests/test_ingest_parity_s2_documents.py` already does; `pg_session()` again
for the ESB half so both channels write into ONE database the parity assertion can diff,
matching that same file's `TestAcP27UploadVsEsbParity` pattern (constructs
`DocumentIngestService` directly, bypassing the HTTP route - parity is about the DATA, not
about post-commit hooks).

Facts verified in code before relying on them:

* `_BINDINGS[SO].agent_fk = "sales_agent_id"`; the outstanding SO reader's `agent` field is
  read from the header aliases `AGENT`/`SALES AGENT`/`SALESMAN`/`SALESPERSON`
  (`alembic/versions/357_scm_so_agent_aliases.py`, doc_type `outstanding_so`) - present on
  the real (migration-seeded) database, so `pg_session()` is required, not `blank_session()`.
* `outstanding_import_service._classify_demand`'s ladder, in order: stored order_type, stated
  order_type, agent's `demand_class`, customer's market segment. This test's fixture states
  none of the four for its one document: no `ORDER TYPE` column at all (so nothing is
  stated), a brand-new agent code (never held, so `agent_classes.get(code)` is `None`) and a
  brand-new debtor code+name (so the back-created customer's `market_segment_code` is NULL) -
  every rung of the ladder answers `None`, which is what makes this document unclassifiable
  today (`plan.unclassified` non-empty) rather than by chance.
* `PreviewResult.ok` (`app/services/scm/outstanding_import_service.py`) is currently
  `not self.missing_columns and not self.unclassified_documents` - a non-empty
  `unclassified_documents` list makes `ok` False, which IS the refusal AC-P2-8 removes.
  `apply()` returns `{"ok": False, "unclassified_documents": [...], "counts": {}}` BEFORE any
  write when `plan.unclassified` is non-empty (line ~2513) - no row lands today.
* No key resembling `unclassified_documents_numbers` (or any other capped-list companion to a
  count) exists anywhere in `outstanding_import_service.py` (grep, zero hits) - only the raw
  `list[str]` on `PreviewResult.unclassified_documents` and `plan.unclassified` exist today,
  neither shaped as "count + capped numbers".
* `app/services/document_ingest_service.py::_apply_demand_class` (the private method behind
  D4's classification, ~line 899) already never refuses: it falls through to
  `warnings.append(WARN_UNCLASSIFIED_DEMAND)` (`app/services/master_ref_resolver
  .WARN_UNCLASSIFIED_DEMAND = "unclassified_demand"`) and leaves `demand_class` unset (NULL).
  This half of the test is a REGRESSION GUARD (already true today, kept as the parity anchor
  per the coordinator's brief) rather than a red assertion - flagged explicitly in the test's
  own docstring and in the report, not silently mixed in with the red ones.

**Chosen shape for the still-to-be-built response** (the UAC says "count + capped document
numbers, same shape as `suppliers_created_codes`" but does not name the second key): this test
asserts `unclassified_documents` becomes an INT COUNT and a new `unclassified_documents_numbers`
key carries the capped list, mirroring `suppliers_created`/`suppliers_created_codes` exactly
(base name for the count, `_codes`-style suffix for the list) with `numbers` in place of `codes`
because the values are order NUMBERS, not codes. This is the tester's own justified choice for
an unstated name, the same way `tests/test_ingest_parity_s2_documents.py` chose to assert the
concrete `order_inquiry_conflicts` table over an unstated function name - the coder is free to
implement the shape differently, in which case this assertion (and only this one) needs
updating to match, not the rest of the test.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.services.scm import outstanding_import_service as outstanding_svc
from app.services.scm.outstanding_reader import SO

from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTIP2B"


def _workbook(rows: list[tuple], headers: tuple[str, ...]) -> bytes:
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Outstanding SO"
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# No ORDER TYPE column at all - the file states nothing on that rung of the ladder. Column
# order is arbitrary; the reader resolves by header NAME via `import_field_alias`, not position.
_HEADERS = (
    "S/O NO", "SO DATE", "DEBTOR CODE", "PROJECT/CUSTOMER", "ITEM CODE", "UOM", "QTY",
    "DELIVERY DATE", "STOCK LOCATION", "AGENT",
)


def _seed_catalogue(db) -> tuple[str, str]:
    """One product and one warehouse this document's line names, and nothing else."""
    from app.models.inventory import Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    cat = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code(MARKER)[:40],
        category_name=f"{MARKER} category",
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_code=unique_code(MARKER)[:20], uom_name="pcs"
    )
    db.add_all([cat, uom])
    db.flush()
    item_code = unique_code(MARKER)[:40]
    warehouse_code = unique_code(MARKER)[:40]
    db.add(Product(
        id=str(uuid.uuid4()), product_code=item_code, product_name=item_code,
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    ))
    db.add(Warehouse(
        id=str(uuid.uuid4()), warehouse_code=warehouse_code, warehouse_name=warehouse_code,
        is_active=True,
    ))
    db.flush()
    return item_code, warehouse_code


class TestAcP28UnclassifiedDemandLandsOnBothChannels:
    """D23/AC-P2-8: a document nothing can classify lands, on both channels, with
    `demand_class` NULL - it is reported, never refused."""

    def test_upload_preview_does_not_refuse_an_unclassifiable_document(self):
        with pg_session() as db:
            item_code, location = _seed_catalogue(db)
            so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}".upper()
            debtor_code = f"{MARKER}-DEB-{uuid.uuid4().hex[:8]}".upper()
            debtor_name = f"{MARKER} Brand New Sdn Bhd"
            agent_code = f"{MARKER}-AGT-{uuid.uuid4().hex[:8]}".upper()
            file = _workbook(
                [(so_number, date(2026, 5, 4), debtor_code, debtor_name, item_code, "PCS",
                  10, date(2026, 7, 1), location, agent_code)],
                headers=_HEADERS,
            )

            result = outstanding_svc.preview(db, file, SO)

            assert result.ok is True, (
                "D23: an unclassifiable document must not refuse the preview - "
                f"missing_columns={result.missing_columns} "
                f"unclassified_documents={result.unclassified_documents}"
            )
            assert so_number in result.unclassified_documents, result.unclassified_documents

    def test_upload_apply_lands_the_order_with_demand_class_null_and_reports_it(self):
        with pg_session() as db:
            item_code, location = _seed_catalogue(db)
            so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}".upper()
            debtor_code = f"{MARKER}-DEB-{uuid.uuid4().hex[:8]}".upper()
            debtor_name = f"{MARKER} Brand New Sdn Bhd"
            agent_code = f"{MARKER}-AGT-{uuid.uuid4().hex[:8]}".upper()
            file = _workbook(
                [(so_number, date(2026, 5, 4), debtor_code, debtor_name, item_code, "PCS",
                  10, date(2026, 7, 1), location, agent_code)],
                headers=_HEADERS,
            )

            result = outstanding_svc.apply(db, file, SO)

            assert result.get("applied", {}).get("added") == 1, (
                "D23: the order must land (this is what QP1's refusal used to prevent), "
                f"not stay un-imported: {result}"
            )
            demand_class = db.execute(
                text("SELECT demand_class FROM sales_orders WHERE so_number = :n"),
                {"n": so_number},
            ).scalar()
            assert demand_class is None, (
                "an order nothing can classify lands with demand_class NULL, never a guess"
            )
            # Chosen shape (see module docstring): a count under the existing key name, a
            # capped list of document numbers under a new, `_codes`-mirroring key.
            assert result.get("unclassified_documents") == 1, result
            assert result.get("unclassified_documents_numbers") == [so_number], result

    def test_esb_push_of_the_same_unclassifiable_shape_already_lands_with_a_warning(self):
        """REGRESSION GUARD, not red: `DocumentIngestService` already never refuses on an
        unclassifiable document - it lands with `demand_class` NULL and
        `WARN_UNCLASSIFIED_DEMAND`. Kept as the parity anchor the coordinator asked for -
        AC-P2-8 needs the upload to reach the SAME end state, not the ESB to change."""
        with pg_session() as db:
            from app.models.base import set_company_scope
            from app.models.product import Product, ProductCategory, UnitOfMeasure
            from app.services.company_scope import DEFAULT_COMPANY_ID
            from app.services.document_ingest_service import DocumentIngestService
            from app.services.master_ingest_service import IngestOutcome

            set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
            category = ProductCategory(
                category_code=unique_code(MARKER), category_name="Cat"
            )
            uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
            db.add_all([category, uom])
            db.flush()
            product = Product(
                product_code=unique_code(MARKER), product_name="Item",
                category_id=category.id, base_uom_id=uom.id, list_price=0,
            )
            db.add(product)
            db.flush()
            svc = DocumentIngestService(db, integration_id=None, company_id=DEFAULT_COMPANY_ID)
            product_ref = f"DK-{product.product_code}"
            svc.refs.link(entity_type="products", entity_id=product.id, source_ref=product_ref)

            debtor_code = f"{MARKER}-EDEB-{uuid.uuid4().hex[:8]}".upper()
            debtor_name = f"{MARKER} ESB Brand New Sdn Bhd"
            agent_code = f"{MARKER}-EAGT-{uuid.uuid4().hex[:8]}".upper()
            so_number = f"{MARKER}-ESO-{uuid.uuid4().hex[:8]}".upper()

            result = svc.ingest(
                "sales_orders",
                [
                    {
                        "source_ref": f"DK-{so_number}",
                        "so_number": so_number,
                        "status": "open",
                        "customer_code": debtor_code,
                        "customer_name": debtor_name,
                        "agent_code": agent_code,
                        "lines": [
                            {
                                "source_ref": f"DK-{so_number}-L1",
                                "product_ref": product_ref,
                                "qty_ordered": "10",
                            }
                        ],
                    }
                ],
            )
            record = result.records[0]
            assert record.outcome is IngestOutcome.CREATED, record.errors
            assert "unclassified_demand" in record.warnings, record.warnings
            demand_class = db.execute(
                text("SELECT demand_class FROM sales_orders WHERE so_number = :n"),
                {"n": so_number},
            ).scalar()
            assert demand_class is None


class TestAcP28Parity:
    """The same unclassified document through both channels yields identical rows -
    scaled to the header-level facts D23 actually decides (`demand_class`, and that the
    order lands at all), the same reduction-in-scope pattern every parity test in this
    UAC already documents in its own docstring."""

    def test_same_unclassifiable_document_lands_identically_on_both_channels(self):
        with pg_session() as db:
            from app.models.base import set_company_scope
            from app.models.company import Company
            from app.models.product import Product, ProductCategory, UnitOfMeasure
            from app.services.document_ingest_service import DocumentIngestService
            from app.services.master_ingest_service import IngestOutcome

            other = Company(
                id=str(uuid.uuid4()), name=f"{MARKER} B", code=unique_code(MARKER)[:10]
            )
            db.add(other)
            db.flush()
            company_b = str(other.id)

            debtor_code = f"{MARKER}-PDEB-{uuid.uuid4().hex[:8]}".upper()
            debtor_name = f"{MARKER} Parity Brand New Sdn Bhd"
            agent_code = f"{MARKER}-PAGT-{uuid.uuid4().hex[:8]}".upper()

            # Upload half, into the ambient default company.
            item_code, location = _seed_catalogue(db)
            so_number_a = f"{MARKER}-PSOA-{uuid.uuid4().hex[:8]}".upper()
            file = _workbook(
                [(so_number_a, date(2026, 5, 4), debtor_code, debtor_name, item_code, "PCS",
                  10, date(2026, 7, 1), location, agent_code)],
                headers=_HEADERS,
            )
            upload_result = outstanding_svc.apply(db, file, SO)
            # Checked BEFORE the demand_class read: today `apply()` refuses and writes
            # nothing, so a bare `demand_class IS NULL` read would pass for the wrong
            # reason (no row at all, not a row with NULL) - this is the assertion that
            # actually turns red today.
            assert upload_result.get("applied", {}).get("added") == 1, (
                "D23: the upload must land this document, not refuse it: "
                f"{upload_result}"
            )
            demand_class_a = db.execute(
                text("SELECT demand_class FROM sales_orders WHERE so_number = :n"),
                {"n": so_number_a},
            ).scalar()

            # ESB half, into company B, same debtor code + name + agent code.
            set_company_scope(db, frozenset({company_b}))
            category = ProductCategory(category_code=unique_code(MARKER), category_name="Cat")
            uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
            db.add_all([category, uom])
            db.flush()
            product = Product(
                product_code=item_code, product_name=item_code,
                category_id=category.id, base_uom_id=uom.id, list_price=0,
            )
            db.add(product)
            db.flush()
            esb = DocumentIngestService(db, integration_id=None, company_id=company_b)
            product_ref = f"DK-{item_code}-B"
            esb.refs.link(entity_type="products", entity_id=product.id, source_ref=product_ref)

            so_number_b = f"{MARKER}-PSOB-{uuid.uuid4().hex[:8]}".upper()
            result = esb.ingest(
                "sales_orders",
                [
                    {
                        "source_ref": f"DK-{so_number_b}",
                        "so_number": so_number_b,
                        "status": "open",
                        "customer_code": debtor_code,
                        "customer_name": debtor_name,
                        "agent_code": agent_code,
                        "lines": [
                            {
                                "source_ref": f"DK-{so_number_b}-L1",
                                "product_ref": product_ref,
                                "qty_ordered": "10",
                            }
                        ],
                    }
                ],
            )
            assert result.records[0].outcome is IngestOutcome.CREATED, result.records[0].errors
            demand_class_b = db.execute(
                text("SELECT demand_class FROM sales_orders WHERE so_number = :n"),
                {"n": so_number_b},
            ).scalar()

            assert demand_class_a == demand_class_b, (
                "both channels must land the same unclassifiable document with the same "
                f"(NULL) demand_class: upload={demand_class_a!r} esb={demand_class_b!r}"
            )
