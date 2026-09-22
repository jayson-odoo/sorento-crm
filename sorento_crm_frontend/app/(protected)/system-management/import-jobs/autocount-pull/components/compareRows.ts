/**
 * Pure helpers behind `PullCompareTab`'s differences grid + download
 * (PLAN-autocount-compare-tab-detail.md). No React, no DataGrid - kept separate so the
 * formatting/labelling/combining logic is unit-testable without rendering the table.
 */
import type { AutocountCompareDifference, AutocountComparePullResult } from '../types/autocountPull.types';

/** `is_active` -> `Active`/`Inactive` (the only boolean field the compare service sends);
 *  `null`/`undefined` -> `-`; everything else -> its string form. Shared by the grid cells,
 *  their `title`, and the download rows, so what is shown is what is exported. */
export function formatCompareValue(field: string, value: string | number | boolean | null): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'Active' : 'Inactive';
  return String(value);
}

const FIELD_LABELS: Record<string, string> = {
  description: 'Description',
  item_group: 'Item Group',
  item_brand: 'Item Brand',
  price: 'Price',
  is_active: 'Active',
  on_hand_qty: 'On Hand Qty',
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
  location?: string;
  field: string;
  excel: string;
  pull: string;
}

/** Stock only-in labels are `code|location` (`autocount_pull_compare.py`'s `_stock_pair_label`);
 *  a plain product code has no `|` and comes back with no location. */
function splitOnlyInLabel(label: string): { item_code: string; location?: string } {
  const separatorIndex = label.indexOf('|');
  if (separatorIndex === -1) return { item_code: label };
  return { item_code: label.slice(0, separatorIndex), location: label.slice(separatorIndex + 1) };
}

function differenceRow(difference: AutocountCompareDifference): CompareRow {
  return {
    item_code: difference.item_code,
    location: difference.location,
    field: fieldLabel(difference.field),
    excel: formatCompareValue(difference.field, difference.excel),
    pull: formatCompareValue(difference.field, difference.pull),
  };
}

/** Combines `differences` + `only_in_excel` + `only_in_pull` into the ONE array the grid's
 *  `recordCount` and the download both use, so what is counted is what is downloaded (CT-4). */
export function buildCompareRows(result: AutocountComparePullResult): CompareRow[] {
  const rows: CompareRow[] = result.differences.map(differenceRow);

  for (const label of result.only_in_excel) {
    const { item_code, location } = splitOnlyInLabel(label);
    rows.push({ item_code, location, field: 'Only in your Excel', excel: 'Present', pull: 'Missing' });
  }
  for (const label of result.only_in_pull) {
    const { item_code, location } = splitOnlyInLabel(label);
    rows.push({ item_code, location, field: 'Only in AutoCount', excel: 'Missing', pull: 'Present' });
  }

  return rows;
}
