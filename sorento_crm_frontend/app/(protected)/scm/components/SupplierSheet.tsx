'use client';

/**
 * The supplier document, ONE renderer (R9/R12). Extracted off the public page's own table
 * (`app/(public)/c/[company]/supplier-request/[token]/page.tsx`), which now imports this too,
 * so the read-only public page, the PDF-shaped preview inside the loading plan and any future
 * caller draw the same `SheetModel` the same way rather than three copies of one table.
 *
 * `editable` (R11) turns the qty-to-load and remark cells into inputs, writing back through
 * `onQtyChange` / `onRemarkChange`. Those two are always the LAST two columns of a sheet this
 * batch builds (`需装数量 / Qty to load` then `备注 / Remarks`) - safe positionally rather than
 * by field name because the wire shape (`SupplierSheetColumn`) carries only the printed
 * labels, the same as the public page always read it. A row with no `row_key` (an unmatched
 * line on the supplier's own sheet, or a document frozen before remarks existed) has nothing
 * to write an edit against, so it renders those two cells as plain text even in edit mode.
 *
 * R10: a cell's `fill` is either `'highlight'` (our own mark, painted on rows whose qty to
 * load is > 0 - AC-E3) or the legacy `'yellow'` a notice sent before this batch still carries
 * in its frozen `sheet_json`. Both are supported so an old sent document does not lose the
 * marks it went out with; every NEW document the backend builds only ever emits `'highlight'`.
 */

import { cn } from '@/lib/utils';
import { fmtInt } from '../lib/format';

export interface SupplierSheetColumn {
  /** Their heading, in their own words (or ours, on a no-file document). */
  label: string;
  /** Ours, as a second line under it. Null for a column we cannot name. */
  label_en: string | null;
}

export interface SupplierSheetCell {
  value: string | number | null;
  rowspan: number;
  colspan: number;
  /** True when a merge starting above or to the left covers this position: draw nothing. */
  covered: boolean;
  fill: 'yellow' | 'highlight' | null;
  red: boolean;
}

export interface SupplierSheetRow {
  cells: SupplierSheetCell[];
  /** How many of the sheet's rows this product family covers; 0 on a row that continues one. */
  family_span: number;
  /** True for a line we added because the supplier's own list never named the product. */
  appended: boolean;
  /** The plan row this line came from (R11), so an edit here can write back to
   *  `line_edits[row_key]`. Null on a row this sheet cannot attribute an edit to. */
  row_key?: string | null;
}

export interface SupplierSheetModel {
  title: string | null;
  columns: SupplierSheetColumn[];
  rows: SupplierSheetRow[];
  totals: SupplierSheetRow | null;
}

/** Empty stays empty: a dash would read as a value the supplier wrote (the reason `fmtInt`'s
 *  own em-dash-for-null is wrong here, so this is not a bare `fmtInt` call). */
function cellText(value: string | number | null): string {
  if (value === null || value === undefined) return '';
  return typeof value === 'number' ? fmtInt(value) : value;
}

function fillClass(fill: SupplierSheetCell['fill']): string | undefined {
  if (fill === 'highlight') return 'bg-[#fff2cc]';
  if (fill === 'yellow') return 'bg-[#ffff00] text-black';
  return undefined;
}

export function SupplierSheet({
  sheet,
  editable = false,
  onQtyChange,
  onRemarkChange,
}: {
  sheet: SupplierSheetModel;
  /** R11: the last two columns (qty to load, remark) become inputs. */
  editable?: boolean;
  onQtyChange?: (rowKey: string, qty: number) => void;
  onRemarkChange?: (rowKey: string, remark: string) => void;
}) {
  const qtyAt = sheet.columns.length - 2;
  const remarkAt = sheet.columns.length - 1;

  function cell(rowCell: SupplierSheetCell, colIndex: number, row: SupplierSheetRow) {
    if (rowCell.covered) return null;
    const isEditableCell = editable && !!row.row_key && (colIndex === qtyAt || colIndex === remarkAt);
    return (
      <td
        key={colIndex}
        rowSpan={rowCell.rowspan > 1 ? rowCell.rowspan : undefined}
        colSpan={rowCell.colspan > 1 ? rowCell.colspan : undefined}
        className={cn(
          'border border-border px-2 py-1.5 align-middle',
          fillClass(rowCell.fill),
          rowCell.red && 'text-red-600',
        )}
      >
        {isEditableCell && colIndex === qtyAt ? (
          <input
            type="number"
            min={0}
            aria-label="Qty to load"
            className="h-8 w-20 rounded-sm border border-input bg-background px-1.5 text-center tabular-nums"
            defaultValue={typeof rowCell.value === 'number' ? rowCell.value : ''}
            onChange={(e) => onQtyChange?.(row.row_key as string, Math.max(0, Number(e.target.value) || 0))}
          />
        ) : isEditableCell && colIndex === remarkAt ? (
          <input
            type="text"
            aria-label="Remarks"
            className="h-8 w-full rounded-sm border border-input bg-background px-1.5"
            defaultValue={typeof rowCell.value === 'string' ? rowCell.value : ''}
            onChange={(e) => onRemarkChange?.(row.row_key as string, e.target.value)}
          />
        ) : (
          cellText(rowCell.value)
        )}
      </td>
    );
  }

  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-[820px] border-collapse text-center text-xs">
        <thead>
          {sheet.title ? (
            <tr>
              <th
                colSpan={sheet.columns.length}
                className="border border-border px-2 py-2 text-center text-base font-semibold"
              >
                {sheet.title}
              </th>
            </tr>
          ) : null}
          <tr>
            {sheet.columns.map((column, index) => (
              <th
                key={`${column.label}-${index}`}
                className="border border-border px-2 py-1.5 text-center font-semibold"
              >
                {column.label}
                {column.label_en ? (
                  <span className="block text-2xs font-normal text-muted-foreground">
                    {column.label_en}
                  </span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sheet.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.cells.map((rowCell, colIndex) => cell(rowCell, colIndex, row))}
            </tr>
          ))}
        </tbody>
        {sheet.totals ? (
          <tfoot>
            <tr className="text-red-600">
              {sheet.totals.cells.map((rowCell, colIndex) => cell(rowCell, colIndex, sheet.totals as SupplierSheetRow))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

export default SupplierSheet;
