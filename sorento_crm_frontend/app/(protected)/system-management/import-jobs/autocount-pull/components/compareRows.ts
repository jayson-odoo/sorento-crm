/**
 * Pure helpers behind `PullCompareTab`'s differences grid + download
 * (PLAN-autocount-compare-tab-detail.md). No React, no DataGrid - kept separate so the
 * formatting/labelling/combining logic is unit-testable without rendering the table.
 */
import type {
  AutocountCompareDifference,
  AutocountComparePullResult,
  AutocountPullEntity,
} from '../types/autocountPull.types';

/** Booleans -> `Active`/`Inactive` (the only boolean field the compare service sends is
 *  `is_active`); `null`/`undefined`/`""` -> `-` (review S1: the backend sends `""` for a
 *  blank `description`/`item_group`/`item_brand`, which reads the same as "no value" as a
 *  missing field does); everything else -> its string form (`0` stays `"0"`, never a dash).
 *  Shared by the grid cells, their `title`, and the download rows, so what is shown is what
 *  is exported. */
export function formatCompareValue(value: string | number | boolean | null): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? 'Active' : 'Inactive';
  return String(value);
}

const FIELD_LABELS: Record<string, string> = {
  description: 'Description',
  item_group: 'Item Group',
  item_brand: 'Item Brand',
  price: 'Price',
  // Matches the manual template's own column header (captain ruling N7) - "Active" would
  // collide with the Active/Inactive VALUE cells next to it in the same row.
  is_active: 'Is Active',
  on_hand_qty: 'On Hand Qty',
  // The DO lines sheet's own column header (`compare_delivery_orders`).
  qty: 'Qty',
};

/** Human label for a backend field key (cursor rule: no snake_case in the UI). Unknown keys
 *  fall back to the raw key rather than throwing. */
export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

/** One row the differences grid renders and the download exports - values already formatted,
 *  the field already labelled. */
export interface CompareRow {
  item_code: string;
  /** Delivery orders only. */
  doc_no?: string;
  location?: string;
  field: string;
  excel: string;
  pull: string;
}

/** Stock only-in labels are `code|location` (`autocount_pull_compare.py`'s `_stock_pair_label`);
 *  delivery-orders labels are `docno|code|location` (`_do_label`), split on the FIRST and
 *  LAST `|` so an item code carrying one keeps it. Product only-in labels are the raw item
 *  code, never split (review S2: a product code can legitimately contain `|`, so splitting
 *  there would corrupt it). */
function splitOnlyInLabel(
  label: string,
  entity: AutocountPullEntity,
): { item_code: string; doc_no?: string; location?: string } {
  if (entity === 'delivery_orders') {
    const first = label.indexOf('|');
    const last = label.lastIndexOf('|');
    if (first === -1 || last === first) return { item_code: label };
    return {
      doc_no: label.slice(0, first),
      item_code: label.slice(first + 1, last),
      location: label.slice(last + 1),
    };
  }
  if (entity !== 'stock_balances') return { item_code: label };
  const separatorIndex = label.indexOf('|');
  if (separatorIndex === -1) return { item_code: label };
  return { item_code: label.slice(0, separatorIndex), location: label.slice(separatorIndex + 1) };
}

function differenceRow(difference: AutocountCompareDifference): CompareRow {
  return {
    item_code: difference.item_code,
    doc_no: difference.doc_no,
    location: difference.location,
    field: fieldLabel(difference.field),
    excel: formatCompareValue(difference.excel),
    pull: formatCompareValue(difference.pull),
  };
}

/** Combines `differences` + `only_in_excel` + `only_in_pull` into the ONE array the grid's
 *  `recordCount` and the download both use, so what is counted is what is downloaded (CT-4). */
export function buildCompareRows(result: AutocountComparePullResult, entity: AutocountPullEntity): CompareRow[] {
  const rows: CompareRow[] = result.differences.map(differenceRow);

  for (const label of result.only_in_excel) {
    const { item_code, doc_no, location } = splitOnlyInLabel(label, entity);
    rows.push({ item_code, doc_no, location, field: 'Only in your Excel', excel: 'Present', pull: 'Missing' });
  }
  for (const label of result.only_in_pull) {
    const { item_code, doc_no, location } = splitOnlyInLabel(label, entity);
    rows.push({ item_code, doc_no, location, field: 'Only in AutoCount', excel: 'Missing', pull: 'Present' });
  }

  return rows;
}
