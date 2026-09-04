'use client';

import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { formatMoney2dp } from '@/lib/helpers';
import type { ReportColumn, ReportPivotLayout } from '@/services/reportService';

/**
 * Blank, not zero: an absent cell is a form that does not exist, not a form worth nothing.
 * A cell that IS zero reads the same way the detail grid and the client's own sheet read it
 * (AC-G5): "-", never 0.00, which would claim money that came to nothing.
 */
function measureText(value: string | undefined, measure: ReportColumn): string {
  if (value == null || value === '') return '';
  if (measure.type === 'money') return Number(value) === 0 ? '-' : formatMoney2dp(value, '');
  return value;
}

/**
 * The first column is pinned, so its background has to be OPAQUE: a `bg-muted/40` header
 * lets the columns scrolling underneath read straight through it, and the month labels
 * end up printed across the dimension name. The colour is the same tint the header row
 * carries, mixed against the page instead of layered over it.
 */
const PINNED_HEAD =
  'sticky start-0 z-(--z-sticky-content) min-w-40 bg-[color-mix(in_oklab,var(--muted)_40%,var(--background))]';
const PINNED_CELL = 'sticky start-0 z-(--z-sticky-content) min-w-40 bg-background';
const PINNED_FOOT =
  'sticky start-0 z-(--z-sticky-content) min-w-40 bg-[color-mix(in_oklab,var(--muted)_50%,var(--background))]';

/**
 * The pivot half of a report: row dimension down the side, column dimension across the
 * top, one sub-column per measure, and row / column / grand totals.
 *
 * Every number here is a string the engine computed. Nothing on this screen adds two
 * figures together, so the pivot and the exported workbook cannot disagree to the sen.
 */
export function ReportPivotTable({ layout }: { layout: ReportPivotLayout }) {
  const { measures, col_dim: colDim, row_values: rowValues } = layout;
  const columnLabel = (value: string) => colDim.value_labels?.[value] ?? value;

  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border">
      <Table className="border-separate border-spacing-0">
        <TableHeader>
          <TableRow className="bg-muted/40">
            <TableHead rowSpan={2} className={cn(PINNED_HEAD, 'border-b border-border align-bottom')}>
              {layout.row_dim.label}
            </TableHead>
            {colDim.values.map((value) => (
              <TableHead
                key={value}
                colSpan={measures.length}
                className="border-b border-s border-border text-center whitespace-nowrap"
              >
                {columnLabel(value)}
              </TableHead>
            ))}
            <TableHead
              colSpan={measures.length}
              className="border-b border-s border-border text-center font-medium text-foreground whitespace-nowrap"
            >
              Total
            </TableHead>
          </TableRow>
          <TableRow className="bg-muted/40">
            {colDim.values.map((value) =>
              measures.map((measure, index) => (
                <TableHead
                  key={`${value}-${measure.key}`}
                  className={cn(
                    'h-9 border-b border-border text-end whitespace-nowrap',
                    index === 0 && 'border-s',
                  )}
                >
                  {measure.label}
                </TableHead>
              )),
            )}
            {measures.map((measure, index) => (
              <TableHead
                key={`total-${measure.key}`}
                className={cn(
                  'h-9 border-b border-border text-end whitespace-nowrap',
                  index === 0 && 'border-s',
                )}
              >
                {measure.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>

        <TableBody>
          {rowValues.map((rowValue) => (
            <TableRow key={rowValue}>
              <TableCell className={cn(PINNED_CELL, 'border-b border-border font-medium')}>
                {rowValue}
              </TableCell>
              {colDim.values.map((colValue) =>
                measures.map((measure, index) => (
                  <TableCell
                    key={`${rowValue}-${colValue}-${measure.key}`}
                    className={cn(
                      'border-b border-border text-end tabular-nums whitespace-nowrap',
                      index === 0 && 'border-s',
                    )}
                  >
                    {measureText(layout.cells[rowValue]?.[colValue]?.[measure.key], measure)}
                  </TableCell>
                )),
              )}
              {measures.map((measure, index) => (
                <TableCell
                  key={`${rowValue}-total-${measure.key}`}
                  className={cn(
                    'border-b border-border text-end font-medium tabular-nums whitespace-nowrap',
                    index === 0 && 'border-s',
                  )}
                >
                  {measureText(layout.row_totals[rowValue]?.[measure.key], measure)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>

        <TableFooter>
          <TableRow>
            <TableCell className={cn(PINNED_FOOT, 'font-semibold')}>Total</TableCell>
            {colDim.values.map((colValue) =>
              measures.map((measure, index) => (
                <TableCell
                  key={`col-total-${colValue}-${measure.key}`}
                  className={cn(
                    'text-end font-semibold tabular-nums whitespace-nowrap',
                    index === 0 && 'border-s border-border',
                  )}
                >
                  {measureText(layout.col_totals[colValue]?.[measure.key], measure)}
                </TableCell>
              )),
            )}
            {measures.map((measure, index) => (
              <TableCell
                key={`grand-${measure.key}`}
                className={cn(
                  'text-end font-semibold tabular-nums whitespace-nowrap',
                  index === 0 && 'border-s border-border',
                )}
              >
                {measureText(layout.grand_total[measure.key], measure)}
              </TableCell>
            ))}
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}
