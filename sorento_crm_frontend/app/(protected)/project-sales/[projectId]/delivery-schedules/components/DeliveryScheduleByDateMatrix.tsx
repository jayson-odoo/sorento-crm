'use client';

import * as React from 'react';
import { ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { DateColumn } from '../lib/scheduleTotals';
import { sumQty } from '../lib/scheduleTotals';
import { formatQty } from '../../components/SalesOrderMoney';
import {
  PRODUCT_COL,
  ProductHeading,
  TOTAL_COL,
  TotalCell,
  TotalsHeading,
  UNRECONCILED_BG,
  Z_CORNER,
  Z_PINNED,
} from './DeliveryScheduleMatrix';
import type { ScheduleGridController } from './DeliveryScheduleMatrix';

/** Sized for a date plus up to two phase labels underneath it. */
const COLUMN = 'w-[160px] min-w-[160px] max-w-[160px]';

/**
 * The same schedule, turned round the OTHER way: one column per EFFECTIVE delivery date
 * rather than per phase (section 9.8).
 *
 * Accepting a re-date moves the quantity to the date it was accepted onto - the captain's
 * own question, 19 August: "instead of still remaining it at the original date cell, the
 * quantity should be moved to the new accepted date right?" `dateColumns` (scheduleTotals.ts)
 * is what does the moving; this component only lays out what it returns.
 *
 * READ-ONLY. The inputs live in the By phase view; a value edited there is what changes,
 * so nothing here pretends to take a keystroke.
 */
export function DeliveryScheduleByDateMatrix({
  controller,
  dateColumns,
}: {
  controller: ScheduleGridController;
  dateColumns: DateColumn[];
}) {
  const { columns } = controller;

  return (
    <div
      data-testid="schedule-by-date-matrix"
      className="relative max-h-[70vh] w-full overflow-auto overscroll-x-contain rounded-lg border border-border"
    >
      <table className="w-max border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th
              scope="col"
              className={cn(
                PRODUCT_COL,
                Z_CORNER,
                'sticky left-0 top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
              )}
            >
              Product
            </th>

            {dateColumns.map((dateColumn) => (
              <th
                key={dateColumn.date}
                scope="col"
                className={cn(
                  COLUMN,
                  Z_PINNED,
                  'sticky top-0 border-b border-e border-border border-s border-s-border bg-muted px-2 py-2 text-start align-bottom font-medium',
                )}
              >
                <span className="block truncate" title={formatDateInMalaysia(dateColumn.date)}>
                  {formatDateInMalaysia(dateColumn.date)}
                </span>
                <span
                  className="block truncate text-[11px] font-normal text-muted-foreground"
                  title={dateColumn.phaseLabels.join(' · ')}
                >
                  {dateColumn.phaseLabels.join(' · ')}
                </span>
              </th>
            ))}

            <TotalsHeading label="Our total" />
            <TotalsHeading label="Schedule TOTAL QTY" />
            <TotalsHeading label="PO quantity" />
          </tr>
        </thead>

        <tbody>
          {columns.map((column) => (
            <tr key={column.key}>
              <th
                scope="row"
                className={cn(
                  PRODUCT_COL,
                  Z_PINNED,
                  'sticky left-0 border-b border-e border-border px-2 py-2 text-start align-top font-normal',
                  column.reconciled ? 'bg-background' : UNRECONCILED_BG,
                )}
              >
                <ProductHeading column={column} controller={controller} />
              </th>

              {dateColumns.map((dateColumn) => {
                const cell = dateColumn.cells.get(column.key);
                const meta = cell ? controller.metaFor(cell.phaseId, column.key) : undefined;
                return (
                  <td
                    key={dateColumn.date}
                    style={
                      meta?.highlight
                        ? { backgroundColor: `color-mix(in oklab, ${meta.highlight} 35%, transparent)` }
                        : undefined
                    }
                    title={meta?.highlight ? 'Highlighted in the document' : undefined}
                    className={cn(
                      COLUMN,
                      'border-b border-e border-border border-s border-s-border px-2 py-1.5',
                      !meta?.highlight && (column.reconciled ? '' : 'bg-destructive/5'),
                    )}
                  >
                    {cell && (
                      <>
                        <p className="truncate text-end tabular-nums">{formatQty(cell.qty)}</p>
                        {/* Moved off its own phase's date: the was -> now this cell earned
                            by being accepted, same styling as the By phase view's override
                            line, so a reviewer reads the same thing in either axis. */}
                        {cell.wasDate && (
                          <p className="flex items-center justify-end gap-1 truncate text-[10px] tabular-nums text-muted-foreground">
                            <span className="line-through">
                              {formatDateInMalaysia(cell.wasDate)}
                            </span>
                            <ArrowRight className="size-2.5 shrink-0" aria-hidden />
                            <span className="font-medium text-foreground">
                              {formatDateInMalaysia(dateColumn.date)}
                            </span>
                          </p>
                        )}
                      </>
                    )}
                  </td>
                );
              })}

              <TotalCell column={column} value={column.ourTotal} emphasise />
              <TotalCell
                column={column}
                value={column.reportedTotal}
                missingLabel="Not printed"
                wrong={column.blockers.some((blocker) => blocker.code === 'reported_mismatch')}
              />
              <TotalCell
                column={column}
                value={column.poQty}
                missingLabel="Not on the PO"
                wrong={column.blockers.some(
                  (blocker) => blocker.code === 'po_mismatch' || blocker.code === 'not_on_po',
                )}
              />
            </tr>
          ))}
        </tbody>

        <tfoot>
          <tr>
            <th
              scope="row"
              className={cn(
                PRODUCT_COL,
                Z_CORNER,
                'sticky bottom-0 left-0 border-t border-e border-border bg-muted px-2 py-1.5 text-start text-[11px] font-semibold',
              )}
            >
              Our total for the date
            </th>
            {dateColumns.map((dateColumn) => (
              <td
                key={dateColumn.date}
                className={cn(
                  COLUMN,
                  Z_PINNED,
                  'sticky bottom-0 border-t border-e border-border border-s border-s-border bg-muted px-2 py-1.5 text-end font-semibold tabular-nums',
                )}
              >
                {sumQty(Array.from(dateColumn.cells.values()).map((cell) => cell.qty))}
              </td>
            ))}
            <td
              className={cn(
                TOTAL_COL,
                Z_PINNED,
                'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5 text-end font-semibold tabular-nums',
              )}
            >
              {sumQty(columns.map((column) => column.ourTotal))}
            </td>
            <td
              className={cn(
                TOTAL_COL,
                Z_PINNED,
                'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5',
              )}
            />
            <td
              className={cn(
                TOTAL_COL,
                Z_PINNED,
                'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5',
              )}
            />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
