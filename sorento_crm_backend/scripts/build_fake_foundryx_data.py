"""Builds full-size fake-FoundryX data files for the AutoCount pull lane's browser
pass (PLAN-autocount-pull-review.md "Local stack for the browser pass", SR4 fix round).
READ-ONLY against the database - never writes a row, never runs a migration.

    venv/bin/python scripts/build_fake_foundryx_data.py \
        --database-url postgresql://user:pass@host:5432/dbname \
        --company-code SRT \
        --xlsm /path/to/stock_export.xlsm \
        --out /path/to/fake-foundryx-data

Writes `<company-code>-products.json` (every product of the company, canonical row
shape - `source_ref`/`code`/`name`/`description`/`category_code`/`brand_code`
(omitted when the product has none)/`list_price`/`is_active`) and
`<company-code>-stock_balances.json` (the xlsm's `Master` sheet, summed to one row per
(item_code, location_code) pair, `On Hand Qty > 0` only) - the exact shape
`tests/support/fake_foundryx.py` reads when `FAKE_FOUNDRYX_DATA` points at `--out`.

`--database-url` is REQUIRED and used exactly as given - this never reads `DATABASE_URL`
from the environment. A worktree's own `.env` overrides whatever the shell exports
(LESSONS-LEARNT ".env overrides env"), so trusting the environment here risks silently
reading a different lane's database than the one the caller meant.

Table names checked against the models (`grep __tablename__`) before writing the SQL
below - they differ from the model class names in this codebase: `products`,
`product_categories`, `brands`, `companies`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text

_PRODUCTS_SQL = text(
    """
    SELECT p.product_code, p.product_name, p.description, p.list_price, p.is_active,
           c.category_code, b.brand_code
    FROM products p
    JOIN companies co ON co.id = p.company_id
    JOIN product_categories c ON c.id = p.category_id
    LEFT JOIN brands b ON b.id = p.brand_id
    WHERE co.code = :company_code
    ORDER BY p.product_code
    """
)

#: The four columns the xlsm's `Master` sheet must carry - the header row's position
#: is not assumed to be row 1, so it is located by matching these names.
_STOCK_HEADER_COLUMNS = ("Item Code", "Item Description", "Location", "On Hand Qty")


def _build_products(engine, company_code: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(_PRODUCTS_SQL, {"company_code": company_code}).mappings().all()

    products: list[dict] = []
    for row in rows:
        code = row["product_code"]
        name = row["product_name"]
        canonical = {
            "source_ref": f"AED_SORENTO:{code}",
            "code": code,
            "name": name,
            # Derived from the stored row, not re-parsed: description when the
            # product has one, else the name (D24-style: no synthetic content).
            "description": row["description"] or name,
            "category_code": row["category_code"],
            "list_price": str(row["list_price"]),
            "is_active": bool(row["is_active"]),
        }
        if row["brand_code"]:
            canonical["brand_code"] = row["brand_code"]
        products.append(canonical)
    return products


def _find_header_row(worksheet) -> tuple[int, dict[str, int]]:
    """The 1-based row index and 0-based column index of each of the four expected
    headers. Scans the first 50 rows - the sheet is expected to carry the header
    somewhere near the top, not necessarily row 1 (a title/branding row is common)."""
    for row_idx, row in enumerate(worksheet.iter_rows(min_row=1, max_row=50, values_only=True), start=1):
        cells = {str(value).strip(): i for i, value in enumerate(row) if value is not None}
        if all(header in cells for header in _STOCK_HEADER_COLUMNS):
            return row_idx, {header: cells[header] for header in _STOCK_HEADER_COLUMNS}
    raise SystemExit(
        f"Could not find a header row carrying all of {_STOCK_HEADER_COLUMNS!r} in the "
        f"'Master' sheet (checked the first 50 rows)."
    )


def _cell(row: tuple, columns: dict[str, int], header: str):
    index = columns[header]
    return row[index] if index < len(row) else None


def _build_stock(xlsm_path: Path) -> list[dict]:
    import openpyxl

    workbook = openpyxl.load_workbook(str(xlsm_path), read_only=True, data_only=True)
    if "Master" not in workbook.sheetnames:
        raise SystemExit(f"'Master' sheet not found in {xlsm_path} (have: {workbook.sheetnames})")
    worksheet = workbook["Master"]
    header_row, columns = _find_header_row(worksheet)

    # (item_code, location_code) -> the accumulating row - one row per pair, summed,
    # per the plan ("one row per (item_code, location_code) summed").
    totals: dict[tuple[str, str], dict] = {}
    for row in worksheet.iter_rows(min_row=header_row + 1, values_only=True):
        raw_item_code = _cell(row, columns, "Item Code")
        if raw_item_code is None or str(raw_item_code).strip() == "":
            continue
        item_code = str(raw_item_code).strip()

        raw_location = _cell(row, columns, "Location")
        location = str(raw_location).strip() if raw_location is not None else ""
        if not location:
            continue

        raw_description = _cell(row, columns, "Item Description")
        description = str(raw_description).strip() if raw_description is not None else ""

        raw_qty = _cell(row, columns, "On Hand Qty")
        try:
            qty = float(raw_qty) if raw_qty is not None else 0.0
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        key = (item_code, location)
        if key in totals:
            totals[key]["qty"] += qty
        else:
            totals[key] = {
                "source_ref": f"AED_SORENTO:{item_code}|{location}",
                "item_code": item_code,
                "item_description": description,
                "location_code": location,
                "qty": qty,
            }

    stock = list(totals.values())
    for entry in stock:
        # Every source cell reads as a float; AutoCount on-hand quantities are whole
        # units, matching the committed fixture's own shape (`"qty": 672`, not `672.0`).
        entry["qty"] = int(entry["qty"]) if float(entry["qty"]).is_integer() else entry["qty"]
    return stock


_DELIVERY_ORDERS_SQL = text(
    """
    SELECT o.id, o.order_number, o.order_date, o.created_time, o.debtor_code, o.debtor_name,
           o.agent, o.is_cancelled, o.remarks, o.subtotal_amount, o.tax_amount, o.total_amount
    FROM orders o
    JOIN companies co ON co.id = o.company_id
    WHERE co.code = :company_code
      AND o.deleted_at IS NULL
      AND o.order_date BETWEEN :date_from AND :date_to
    ORDER BY o.order_date, o.order_number
    """
)

_DELIVERY_ORDER_LINES_SQL = text(
    """
    SELECT l.order_id, l.line_sequence, l.quantity, l.unit_price, l.discount, l.total, l.tax,
           p.product_code, p.product_name, w.warehouse_code, u.uom_code
    FROM order_lines l
    JOIN products p ON p.id = l.product_id
    JOIN warehouses w ON w.id = l.warehouse_id
    LEFT JOIN units_of_measure u ON u.id = p.base_uom_id
    WHERE l.order_id = ANY(:order_ids)
    ORDER BY l.order_id, l.line_sequence
    """
)


def _num(value):
    return float(value) if value is not None else None


def _doc_key(order_number: str) -> int:
    """A deterministic synthetic DocKey per document number (the CRM's own DOs carry no
    AutoCount key): the same number builds the same key on every run, so a second pull of
    the same window answers `unchanged`, exactly as a real re-pull would."""
    import zlib

    return 700_000_000 + zlib.crc32(order_number.encode("utf-8")) % 100_000_000


def _build_delivery_orders(engine, company_code: str, date_from: str, date_to: str) -> list[dict]:
    """DO-PULL-CRM: the company's OWN delivery orders in a DocDate window, in the raw vendor
    record shape the DO ingest reads (`DocKey`, `DocNo`, `DocDate`, ..., `Details[]`) plus the
    contract's `source_ref`. Built from the CRM's rows, so a pull of this file adopts every
    document by number (the tracking columns stay) and matches every line - the adoption
    path on real numbers, with nothing invented. READ-ONLY."""
    from datetime import datetime

    with engine.connect() as conn:
        orders = conn.execute(
            _DELIVERY_ORDERS_SQL,
            {"company_code": company_code, "date_from": date_from, "date_to": date_to},
        ).mappings().all()
        order_ids = [str(o["id"]) for o in orders]
        lines_by_order: dict[str, list] = {}
        for chunk_start in range(0, len(order_ids), 500):
            chunk = order_ids[chunk_start:chunk_start + 500]
            for line in conn.execute(_DELIVERY_ORDER_LINES_SQL, {"order_ids": chunk}).mappings():
                lines_by_order.setdefault(str(line["order_id"]), []).append(line)

    now = datetime.now().replace(microsecond=0).isoformat()
    records: list[dict] = []
    for order in orders:
        doc_key = _doc_key(order["order_number"])
        details = []
        for index, line in enumerate(lines_by_order.get(str(order["id"]), []), start=1):
            details.append({
                "DocKey": doc_key,
                "DtlKey": doc_key * 100 + index,
                "Seq": int(line["line_sequence"] or index),
                "ItemCode": line["product_code"],
                "Description": line["product_name"],
                "Qty": _num(line["quantity"]),
                "FOCQty": 0.0,
                "UOM": line["uom_code"],
                "UnitPrice": _num(line["unit_price"]),
                "Discount": "",
                "DiscountAmt": _num(line["discount"]),
                "SubTotal": _num(line["total"]),
                "Tax": _num(line["tax"]),
                "Location": line["warehouse_code"],
                "BatchNo": None,
                "DeliveryDate": None,
                "ProjNo": None,
                "YourPONo": "",
                "YourPODate": None,
            })
        records.append({
            "source_ref": f"db1:DO:{doc_key}",
            "DocKey": doc_key,
            "DocNo": order["order_number"],
            "DocDate": f"{order['order_date'].isoformat()}T00:00:00",
            "DocStatus": "F",
            "Cancelled": "T" if order["is_cancelled"] else "F",
            "BranchCode": "",
            "DebtorCode": order["debtor_code"] or "",
            "DebtorName": order["debtor_name"] or "",
            "DeliverAddr1": "", "DeliverAddr2": "", "DeliverAddr3": "", "DeliverAddr4": "",
            "DeliverContact": "", "DeliverPhone1": "",
            "SalesAgent": order["agent"] or "",
            "ShipInfo": "", "ShipVia": "",
            "Ref": "", "RefDocNo": "",
            "Remark1": order["remarks"] or "", "Remark2": "", "Remark3": None, "Remark4": "",
            "Description": "DELIVERY ORDER",
            "CurrencyCode": "MYR", "CurrencyRate": 1.0,
            "Total": _num(order["subtotal_amount"]),
            "Tax": _num(order["tax_amount"]),
            "NetTotal": _num(order["total_amount"]),
            "LocalNetTotal": _num(order["total_amount"]),
            "CreatedTimeStamp": order["created_time"].isoformat() if order["created_time"] else None,
            "LastModified": now,
            "Details": details,
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", required=True, help="Full SQLAlchemy/psycopg URL - never read from env")
    parser.add_argument("--company-code", required=True, help="companies.code, e.g. SRT")
    parser.add_argument("--xlsm", type=Path, help="Path to the AutoCount stock export .xlsm (stock_balances file)")
    parser.add_argument("--do-from", help="DO-PULL-CRM: DocDate window start (YYYY-MM-DD) for the delivery_orders file")
    parser.add_argument("--do-to", help="DO-PULL-CRM: DocDate window end (YYYY-MM-DD) for the delivery_orders file")
    parser.add_argument("--out", required=True, type=Path, help="Directory to write the JSON files into")
    args = parser.parse_args()
    if bool(args.do_from) != bool(args.do_to):
        raise SystemExit("--do-from and --do-to go together")

    engine = create_engine(args.database_url)
    try:
        products = _build_products(engine, args.company_code)
        delivery_orders = (
            _build_delivery_orders(engine, args.company_code, args.do_from, args.do_to)
            if args.do_from else None
        )
    finally:
        engine.dispose()
    stock = _build_stock(args.xlsm) if args.xlsm else None

    args.out.mkdir(parents=True, exist_ok=True)
    products_path = args.out / f"{args.company_code}-products.json"
    products_path.write_text(json.dumps(products, indent=2))
    print(f"products: {len(products)} rows -> {products_path}")
    if stock is not None:
        stock_path = args.out / f"{args.company_code}-stock_balances.json"
        stock_path.write_text(json.dumps(stock, indent=2))
        print(f"stock_balances: {len(stock)} rows -> {stock_path}")
    if delivery_orders is not None:
        do_path = args.out / f"{args.company_code}-delivery_orders.json"
        do_path.write_text(json.dumps(delivery_orders, indent=2))
        lines = sum(len(r["Details"]) for r in delivery_orders)
        print(f"delivery_orders: {len(delivery_orders)} documents, {lines} lines -> {do_path}")


if __name__ == "__main__":
    main()
