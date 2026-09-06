import type { ContainerRequestRow } from '../../services/fulfilmentService';
import type {
  SupplierSheetCell,
  SupplierSheetModel,
  SupplierSheetRow,
} from '../../components/SupplierSheet';

/**
 * Phase 1 stand-in for `POST /api/v1/scm/container-requests/preview` (R9): a real `SheetModel`
 * shape, built client-side off the same rows the plan table already has, so the preview's
 * layout is real before the backend endpoint exists. Phase 2 deletes this file and swaps in
 * the real service call - nothing else about `LoadingPlanView` changes, since both return the
 * same `SupplierSheetModel`.
 *
 * Only rows with a qty > 0 are included - the same filter `requestLinesFrom` applies, since
 * this is a preview of what would actually be SENT. Every included row is highlighted: once
 * the real endpoint answers, only rows with qty > 0 carry it (R10), and every row here has one
 * by construction.
 */
function cell(value: string | number | null, highlight: boolean): SupplierSheetCell {
  return {
    value,
    rowspan: 1,
    colspan: 1,
    covered: false,
    fill: highlight ? 'highlight' : null,
    red: false,
  };
}

export function mockSupplierSheet(
  rows: ContainerRequestRow[],
  qtyFor: (row: ContainerRequestRow) => number,
  remarkFor: (row: ContainerRequestRow) => string,
): SupplierSheetModel {
  const included = rows.filter((r) => qtyFor(r) > 0);

  const sheetRows: SupplierSheetRow[] = included.map((row, index) => {
    const qty = qtyFor(row);
    const remark = remarkFor(row);
    return {
      row_key: row.row_key,
      family_span: 1,
      appended: false,
      cells: [
        cell(index + 1, true),
        cell(row.item_code, true),
        cell(row.product_name, true),
        cell(row.holding_qty, true),
        cell(qty, true),
        cell(remark || null, true),
      ],
    };
  });

  const totalQty = included.reduce((sum, row) => sum + qtyFor(row), 0);
  const totals: SupplierSheetRow = {
    family_span: 0,
    appended: false,
    cells: [
      { value: '合计：', rowspan: 1, colspan: 3, covered: false, fill: null, red: false },
      { value: null, rowspan: 1, colspan: 1, covered: true, fill: null, red: false },
      { value: null, rowspan: 1, colspan: 1, covered: true, fill: null, red: false },
      cell(null, false),
      cell(totalQty, false),
      cell(null, false),
    ],
  };

  return {
    title: '配柜要求 / Container request',
    columns: [
      { label: '序号', label_en: 'No.' },
      { label: '型号', label_en: 'Model' },
      { label: '品名', label_en: 'Description' },
      { label: '包装好库存', label_en: 'Packed' },
      { label: '需装数量', label_en: 'Qty to load' },
      { label: '备注', label_en: 'Remarks' },
    ],
    rows: sheetRows,
    totals: included.length ? totals : null,
  };
}

export default mockSupplierSheet;
