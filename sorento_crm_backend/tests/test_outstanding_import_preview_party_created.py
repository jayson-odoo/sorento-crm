"""AC-P2-1 (guide-writer code check, 2026-09-06): the outstanding SO upload PREVIEW
reports the customer back-create count, not only `apply`.

`PreviewResult` reported `unclassified_documents`/`activated_documents`/`unmapped_agents`
- everything the confirm screen needs to show BEFORE the write - but not the debtor
back-create count `apply`'s response already carries under `customers_created`/
`customers_created_codes`. This is the gap: a brand-new debtor code+name (D8 - the
CRM back-creates it) showed the operator nothing on the confirm screen, then a new
customer appeared as a side effect of pressing Confirm.

Substrate + fixture lifted byte-for-byte from `tests/test_ingest_parity_s2b_unclassified.py`
(same `pg_session()` reason: `import_field_alias` header aliases for the outstanding-SO
doc type are migration-seeded, absent from a `blank_session()` scratch schema).
"""
from __future__ import annotations

import uuid
from datetime import date

from app.services.scm import outstanding_import_service as outstanding_svc
from app.services.scm.outstanding_reader import SO

from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTIP21"

_HEADERS = (
    "S/O NO", "SO DATE", "DEBTOR CODE", "PROJECT/CUSTOMER", "ITEM CODE", "UOM", "QTY",
    "DELIVERY DATE", "STOCK LOCATION", "AGENT",
)


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


class TestAcP21PreviewReportsThePartyBackCreateCount:
    def test_preview_reports_customers_created_for_a_brand_new_debtor_code_and_name(self):
        with pg_session() as db:
            item_code, location = _seed_catalogue(db)
            so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}".upper()
            debtor_code = f"{MARKER}-DEB-{uuid.uuid4().hex[:8]}".upper()
            debtor_name = f"{MARKER} Brand New Sdn Bhd"
            file = _workbook(
                [(so_number, date(2026, 5, 4), debtor_code, debtor_name, item_code, "PCS",
                  10, date(2026, 7, 1), location, "")],
                headers=_HEADERS,
            )

            preview = outstanding_svc.preview(db, file, SO).to_dict()

            assert preview["customers_created"] == 1, preview
            assert preview["customers_created_codes"] == [debtor_code], preview

            # Preview WRITES NOTHING - the customer must not actually exist yet.
            from app.models.order import Customer

            assert (
                db.query(Customer).filter(Customer.customer_code == debtor_code).first() is None
            ), "preview must never create the row it reports would be created"

            applied = outstanding_svc.apply(db, file, SO)

            assert applied["customers_created"] == 1, applied
            assert applied["customers_created_codes"] == [debtor_code], applied
            assert (
                db.query(Customer).filter(Customer.customer_code == debtor_code).first()
                is not None
            ), "apply must actually create the row preview only reported"

    def test_preview_reports_nothing_created_for_an_already_known_debtor(self):
        with pg_session() as db:
            from app.models.order import Customer

            item_code, location = _seed_catalogue(db)
            so_number = f"{MARKER}-SO2-{uuid.uuid4().hex[:8]}".upper()
            debtor_code = f"{MARKER}-DEB2-{uuid.uuid4().hex[:8]}".upper()
            db.add(Customer(
                id=str(uuid.uuid4()), customer_code=debtor_code,
                customer_name=f"{MARKER} Existing Sdn Bhd", is_active=True,
            ))
            db.flush()
            file = _workbook(
                [(so_number, date(2026, 5, 4), debtor_code, "Existing Sdn Bhd", item_code, "PCS",
                  10, date(2026, 7, 1), location, "")],
                headers=_HEADERS,
            )

            preview = outstanding_svc.preview(db, file, SO).to_dict()

            assert preview["customers_created"] == 0, preview
            assert preview["customers_created_codes"] == [], preview
